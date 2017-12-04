import os
import re
import threading
import time
from contextlib import contextmanager

from consts.auth import HostLinuxCreds, SvcCgcsAuto
from consts.build_server import DEFAULT_BUILD_SERVER, BUILD_SERVERS
from consts.timeout import HostTimeout
from consts.cgcs import HostAvailabilityState, Prompt, PREFIX_BACKUP_FILE, TITANIUM_BACKUP_FILE_PATTERN, \
    IMAGE_BACKUP_FILE_PATTERN, CINDER_VOLUME_BACKUP_FILE_PATTERN, BACKUP_FILE_DATE_STR, BackupRestore, \
    PREFIX_CLONED_IMAGE_FILE, HostAdminState, HostOperationalState, EventLogID
from consts.filepaths import WRSROOT_HOME, TiSPath, BuildServerPath
from consts.proj_vars import InstallVars, ProjVar
from consts.vlm import VlmAction
from keywords import system_helper, host_helper, vm_helper, patching_helper, cinder_helper, vlm_helper, common
from utils import telnet as telnetlib, exceptions, local_host, cli, table_parser
from utils.ssh import SSHClient, ControllerClient
from utils.tis_log import LOG
from consts.auth import Tenant, CliAuth
import setups
import configparser


UPGRADE_LOAD_ISO_FILE = "bootimage.iso"
BACKUP_USB_MOUNT_POINT = '/media/wrsroot'
TUXLAB_BARCODES_DIR = "/export/pxeboot/vlm-boards/"
CENTOS_INSTALL_REL_PATH = "export/dist/isolinux/"

outputs_restore_system_conf = ("Enter 'reboot' to reboot controller: ", "compute-config in progress ...")

lab_ini_info = {}

def get_ssh_public_key():
    return local_host.get_ssh_key()


def get_current_system_version():
    return system_helper.get_system_software_version()


def check_system_health_for_upgrade():
    # system_helper.source_admin()
    return system_helper.get_system_health_query_upgrade()


def download_upgrade_license(lab, server, license_path):

    cmd = "test -h " + license_path
    assert server.ssh_conn.exec_cmd(cmd)[0] == 0,  'Upgrade license file not found in {}:{}'.format(
            server.name, license_path)
    pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.get_password())

    if 'vbox' in lab['name']:
        external_ip = lab['external_ip']
        external_port = lab['external_port']
        temp_path = '/tmp'
        local_pre_opts = 'sshpass -p "{0}"'.format(lab['local_password'])

        server.ssh_conn.rsync("-L " + license_path, external_ip,
                              os.path.join(temp_path, "upgrade_license.lic"),
                              dest_user=lab['local_user'], dest_password=lab['local_password'],
                              pre_opts=local_pre_opts)

        common.scp_to_active_controller(source_path=os.path.join(temp_path, "upgrade_license.lic"),
                                        dest_path=os.path.join(WRSROOT_HOME, "upgrade_license.lic"))

        server.ssh_conn.rsync("-L " + license_path, external_ip,
                              os.path.join(temp_path, "upgrade_license.lic"),
                              dest_user=lab['local_user'], dest_password=lab['local_password'],
                              pre_opts=local_pre_opts)

        common.scp_to_active_controller(source_path=os.path.join(temp_path, "upgrade_license.lic"),
                                        dest_path=os.path.join(WRSROOT_HOME, "upgrade_license.lic"))
        # server.ssh_conn.rsync("-L " + license_path, external_ip,
        #                       os.path.join(WRSROOT_HOME, "upgrade_license.lic"),
        #                       pre_opts=pre_opts, ssh_port=external_port)
    else:
        server.ssh_conn.rsync("-L " + license_path, lab['controller-0 ip'],
                            os.path.join(WRSROOT_HOME, "upgrade_license.lic"),
                            pre_opts=pre_opts)


def download_upgrade_load(lab, server, load_path):

    # Download licens efile
    cmd = "test -e " + load_path
    assert server.ssh_conn.exec_cmd(cmd, rm_date=False)[0] == 0,  'Upgrade build iso file not found in {}:{}'.format(
            server.name, load_path)
    iso_file_path = os.path.join(load_path, "export", UPGRADE_LOAD_ISO_FILE)
    pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.get_password())

    if 'vbox' in lab['name']:

        external_ip = lab['external_ip']
        external_port = lab['external_port']
        temp_path = '/tmp'
        local_pre_opts = 'sshpass -p "{0}"'.format(lab['local_password'])
        server.ssh_conn.rsync("-L " + iso_file_path, external_ip,
                              os.path.join(temp_path, "bootimage.iso"), dest_user=lab['local_user'],
                              dest_password=lab['local_password'], pre_opts=local_pre_opts)

        common.scp_to_active_controller(source_path=os.path.join(temp_path, "bootimage.iso"),
                                        dest_path=os.path.join(WRSROOT_HOME, "bootimage.iso"))

        server.ssh_conn.rsync("-L " + iso_file_path,
                          external_ip,
                          os.path.join(WRSROOT_HOME, "bootimage.iso"), pre_opts=pre_opts, ssh_port=external_port)
    else:
        server.ssh_conn.rsync("-L " + iso_file_path,
                              lab['controller-0 ip'],
                              os.path.join(WRSROOT_HOME, "bootimage.iso"), pre_opts=pre_opts)


def get_mgmt_boot_device(node):
    boot_device = {}
    boot_interfaces = system_helper.get_host_port_pci_address_for_net_type(node.name)
    for boot_interface in boot_interfaces:
        a1, a2, a3 = boot_interface.split(":")
        boot_device[node.name] = a2 + "0" + a3.split(".")[1]
        if len(boot_device) is 1:
            break
    if len(boot_device) is 0:
        LOG.error("Unable to get the mgmt boot device for host {}".format(node.name))
    return boot_device


def open_vlm_console_thread(hostname, boot_interface=None, upgrade=False, vlm_power_on=False, close_telnet_conn=True,
                            small_footprint=False, wait_for_thread=False):

    lab = InstallVars.get_install_var("LAB")
    node = lab[hostname]
    if node is None:
        err_msg = "Failed to get node object for hostname {} in the Install parameters".format(hostname)
        LOG.error(err_msg)
        raise exceptions.InvalidStructure(err_msg)

    output_dir = ProjVar.get_var('LOG_DIR')
    boot_device = boot_interface
    if boot_interface is None:
        boot_device = get_mgmt_boot_device(node)

    LOG.info("Mgmt boot device for {} is {}".format(node.name, boot_device))

    LOG.info("Opening a vlm console for {}.....".format(hostname))
    rc, output = local_host.reserve_vlm_console(node.barcode)
    if rc != 0:
        err_msg = "Failed to reserve vlm console for {}  barcode {}: {}"\
            .format(node.name, node.barcode, output)
        LOG.error(err_msg)
        raise exceptions.InvalidStructure(err_msg)

    node_thread = threading.Thread(target=bring_node_console_up,
                                   name=node.name,
                                   args=(node, boot_device, output_dir),
                                   kwargs={'upgrade': upgrade, 'vlm_power_on': vlm_power_on,
                                           'close_telnet_conn': close_telnet_conn,'small_footprint':small_footprint})

    LOG.info("Starting thread for {}".format(node_thread.name))
    node_thread.start()
    if wait_for_thread:
        node_thread.join(HostTimeout.SYSTEM_RESTORE)
        if node_thread.is_alive():
            err_msg = "Host {} failed to install within the {} seconds".format(node.name, HostTimeout.SYSTEM_RESTORE)
            LOG.error(err_msg)
            raise exceptions.InvalidStructure(err_msg)


def bring_node_console_up(node, boot_device, install_output_dir, boot_usb=False, upgrade=False,  vlm_power_on=False,
                          close_telnet_conn=True, small_footprint=False, clone_install=False):
    """
    Initiate the boot and installation operation.
    Args:
        node(Node object):
        boot_device:
        install_output_dir:
        close_telnet_conn:

    Returns:
    """
    LOG.info("Opening node vlm console for {}; vlm_power = {}, upgrade= {}".format(node.name, vlm_power_on, upgrade))
    if len(boot_device) == 0:
        LOG.error("Cannot bring vlm console for {} without valid mgmt boot device: {}".format(node.name, boot_device))
        return 1

    if node.telnet_conn is None:
        node.telnet_conn = telnetlib.connect(node.telnet_ip,
                                             int(node.telnet_port),
                                             negotiate=node.telnet_negotiate,
                                             port_login=True if node.telnet_login_prompt else False,
                                             vt100query=node.telnet_vt100query,
                                             log_path=install_output_dir + "/" + node.name + ".telnet.log")

    if vlm_power_on:
        LOG.info("Powering on {}".format(node.name))
        power_on_host(node.name, wait_for_hosts_state_=False)


    node.telnet_conn.install(node, boot_device, usb=boot_usb, upgrade=upgrade, small_footprint=small_footprint,
                             clone_install=clone_install)
    if close_telnet_conn:
        node.telnet_conn.close()


def get_non_controller_system_hosts():

    hosts = system_helper.get_hostnames()
    controllers = sorted([h for h in hosts if "controller" in h])
    storages = sorted([h for h in hosts if "storage" in h])
    computes = sorted([h for h in hosts if h not in storages and h not in controllers])
    return storages + computes


def open_telnet_session(node_obj, install_output_dir):

    _telnet_conn = telnetlib.connect(node_obj.telnet_ip,
                                      int(node_obj.telnet_port),
                                      negotiate=node_obj.telnet_negotiate,
                                      port_login=True if node_obj.telnet_login_prompt else False,
                                      vt100query=node_obj.telnet_vt100query,\
                                      log_path=install_output_dir + "/" + node_obj.name +\
                                      ".telnet.log", debug=False)

    return _telnet_conn


def wipe_disk_hosts(hosts):


    lab = InstallVars.get_install_var("LAB")
    output_dir = ProjVar.get_var('LOG_DIR')
    LOG.info("LAB info:  {}".format(lab))
    if len(hosts) < 1:
        err_msg = "The hosts list referred is empty: {}".format(hosts)
        LOG.info(err_msg)
        return
    threads = []
    nodes = []
    for hostname in hosts:
        node = lab[hostname]
        if node is None:
            err_msg = "Failed to get node object for hostname {} in the Install parameters".format(hostname)
            LOG.error(err_msg)
            raise exceptions.InvalidStructure(err_msg)
        nodes.append(node)

        LOG.info("Opening a vlm console for {}.....".format(hostname))
        rc, output = local_host.reserve_vlm_console(node.barcode)
        if rc != 0:
            err_msg = "Failed to reserve vlm console for {}  barcode {}: {}"\
                .format(node.name, node.barcode, output)
            LOG.error(err_msg)
            raise exceptions.InvalidStructure(err_msg)

        node_thread = threading.Thread(target=wipe_disk,
                                       name=node.name,
                                       args=(node, output_dir))
        threads.append(node_thread)
        LOG.info("Starting thread for {}".format(node_thread.name))
        node_thread.start()

    for thread in threads:
        thread.join()


def wipe_disk(node, install_output_dir, close_telnet_conn=True):
    """
    Perform a wipedisk_via_helper operation on the lab before booting a new load into
        it.
    Args:
        node:
        install_output_dir:
        close_telnet_conn:

    Returns:

    """

    if node.telnet_conn is None:
        node.telnet_conn = telnetlib.connect(node.telnet_ip,
                                             int(node.telnet_port),
                                             negotiate=node.telnet_negotiate,
                                             vt100query=node.telnet_vt100query,
                                             log_path=install_output_dir + "/"
                                             + node.name + ".telnet.log",
                                             debug=False)

    # Check that the node is accessible for wipedisk_via_helper to run.
    # If we cannot successfully ping the interface of the node, then it is
    # expected that the login will fail. This may be due to the node not
    # being left in an installed state.
    node.telnet_conn.login()
    # cmd = "ping -w {} -c 4 {}".format(HostTimeout.PING_TIMEOUT, node.host_ip)
    # if (node.telnet_conn.exec_cmd(cmd, timeout=HostTimeout.PING_TIMEOUT +
    #                               HostTimeout.TIMEOUT_BUFFER)[0] != 0):
    #     err_msg = "Node {} not responding. Skipping wipedisk_via_helper process".format(node.name)
    #     LOG.info(err_msg)
    #     return 1
    # else:
    #     node.telnet_conn.login()

    node.telnet_conn.write_line("sudo -k wipedisk_via_helper")
    node.telnet_conn.get_read_until(Prompt.PASSWORD_PROMPT)
    node.telnet_conn.write_line(HostLinuxCreds.get_password())
    node.telnet_conn.get_read_until("[y/n]")
    node.telnet_conn.write_line("y")
    node.telnet_conn.get_read_until("confirm")
    node.telnet_conn.write_line("wipediskscompletely")
    node.telnet_conn.get_read_until("The disk(s) have been wiped.", HostTimeout.WIPE_DISK_TIMEOUT)

    LOG.info("Disk(s) have been wiped on: " + node.name)
    if close_telnet_conn:
        node.telnet_conn.close()


# TODO: To be replaced by function in vlm_helper
def power_off_host(hosts):

    if isinstance(hosts, str):
        hosts = [hosts]
    lab = InstallVars.get_install_var("LAB")
    for host in hosts:
        node = lab[host]
        if node is None:
            err_msg = "Failed to get node object for hostname {} in the Install parameters".format(host)
            LOG.error(err_msg)
            raise exceptions.InvalidStructure(err_msg)

        rc, output = local_host.reserve_vlm_console(node.barcode)
        if rc != 0:
            err_msg = "Failed to reserve vlm console for {}  barcode {}: {}"\
                .format(node.name, node.barcode, output)
            LOG.error(err_msg)
            raise exceptions.InvalidStructure(err_msg)

        LOG.info("node.barcode:{}".format(node.barcode))
        LOG.info("node:{}".format(node))

        rc, output = local_host.vlm_exec_cmd(VlmAction.VLM_TURNOFF, node.barcode)

        if rc != 0:
            err_msg = "Failed to power off nod {}  barcode {}: {}"\
                .format(node.name, node.barcode, output)
            LOG.error(err_msg)
            raise exceptions.InvalidStructure(err_msg)
        LOG.info("Node {} is turned off".format(node.name))

# TODO: To be replaced by function in vlm_helper
def power_on_host(hosts, wait_for_hosts_state_=True):

    if isinstance(hosts, str):
        hosts = [hosts]
    lab = InstallVars.get_install_var("LAB")
    for host in hosts:
        node = lab[host]
        if node is None:
            err_msg = "Failed to get node object for hostname {} in the Install parameters".format(host)
            LOG.error(err_msg)
            raise exceptions.InvalidStructure(err_msg)

        rc, output = local_host.reserve_vlm_console(node.barcode)
        if rc != 0:
            err_msg = "Failed to reserve vlm console for {}  barcode {}: {}"\
                .format(node.name, node.barcode, output)
            LOG.error(err_msg)
            raise exceptions.InvalidStructure(err_msg)

        rc, output = local_host.vlm_exec_cmd(VlmAction.VLM_TURNON, node.barcode)
        if rc != 0:
            err_msg = "Failed to power on node {}  barcode {}: {}"\
                .format(node.name, node.barcode, output)
            LOG.error(err_msg)
            raise exceptions.InvalidStructure(err_msg)
        LOG.info("Node {} is turned on".format(node.name))

    if wait_for_hosts_state_:
        wait_for_hosts_state(hosts)


# TODO: To be replaced by function in vlm_helper
def wait_for_hosts_state(hosts, state=HostAvailabilityState.ONLINE):

    if len(hosts) > 0:
        locked_hosts_in_states = host_helper.wait_for_hosts_states(hosts, availability=[state])
        LOG.info("Host(s) {} are online".format(locked_hosts_in_states))


def lock_hosts(hosts):
    if isinstance(hosts, str):
        hosts = [hosts]
    for host in hosts:
        host_helper.lock_host(host)


@contextmanager
def ssh_to_build_server(bld_srv=DEFAULT_BUILD_SERVER, user=SvcCgcsAuto.USER, password=SvcCgcsAuto.PASSWORD,
                        prompt=None):
    """
    ssh to given build server.
    Usage: Use with context_manager. i.e.,
        with ssh_to_build_server(bld_srv=cgts-yow3-lx) as bld_srv_ssh:
            # do something
        # ssh session will be closed automatically

    Args:
        bld_srv (str|dict): build server ip, name or dictionary (choose from consts.build_serve.BUILD_SERVERS)
        user (str): svc-cgcsauto if unspecified
        password (str): password for svc-cgcsauto user if unspecified
        prompt (str|None): expected prompt. such as: svc-cgcsauto@yow-cgts4-lx.wrs.com$

    Yields (SSHClient): ssh client for given build server and user

    """
    # Get build_server dict from bld_srv param.
    if isinstance(bld_srv, str):
        for bs in BUILD_SERVERS:
            if bs['name'] in bld_srv or bs['ip'] == bld_srv:
                bld_srv = bs
                break
        else:
            raise exceptions.BuildServerError("Requested build server - {} is not found. Choose server ip or "
                                              "server name from: {}".format(bld_srv, BUILD_SERVERS))
    elif bld_srv not in BUILD_SERVERS:
        raise exceptions.BuildServerError("Unknown build server: {}. Choose from: {}".format(bld_srv, BUILD_SERVERS))

    prompt = prompt if prompt else Prompt.BUILD_SERVER_PROMPT_BASE.format(user, bld_srv['name'])
    bld_server_conn = SSHClient(bld_srv['ip'], user=user, password=password, initial_prompt=prompt)
    bld_server_conn.connect()

    try:
        yield bld_server_conn
    finally:
        bld_server_conn.close()


def download_image(lab, server, guest_path):

    cmd = "test -e " + guest_path
    assert server.ssh_conn.exec_cmd(cmd, rm_date=False)[0] == 0,  'Image file not found in {}:{}'.format(
            server.name, guest_path)
    pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.get_password())

    if 'vbox' in lab['name']:
        external_ip = lab['external_ip']
        temp_path = '/tmp'
        image_file = os.path.basename(guest_path)
        local_pre_opts = 'sshpass -p "{0}"'.format(lab['local_password'])
        server.ssh_conn.rsync(guest_path, external_ip, os.path.join(temp_path, image_file),
                              dest_user=lab['local_user'],
                              dest_password=lab['local_password'], pre_opts=local_pre_opts)

        common.scp_to_active_controller(source_path=os.path.join(temp_path, image_file),
                                        dest_path=TiSPath.IMAGES)
    else:
        server.ssh_conn.rsync(guest_path,
                              lab['controller-0 ip'],
                              TiSPath.IMAGES, pre_opts=pre_opts)


def download_heat_templates(lab, server, load_path):

    heat_path = load_path  + BuildServerPath.HEAT_TEMPLATES

    cmd = "test -e " + heat_path
    assert server.ssh_conn.exec_cmd(cmd, rm_date=False)[0] == 0,  'Heat template path not found in {}:{}'.format(
            server.name, load_path)

    pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.get_password())
    if 'vbox' in lab['name']:
        return
    else:

        server.ssh_conn.rsync(heat_path + "/*",
                              lab['controller-0 ip'],
                              TiSPath.HEAT, pre_opts=pre_opts)


def download_lab_config_files(lab, server, load_path):

    lab_name = lab['name']
    if 'vbox' in lab_name:
        return

    if "yow" in lab_name:
        lab_name = lab_name[4:]
    config_path = load_path + BuildServerPath.CONFIG_LAB_REL_PATH + "/yow/" + lab_name
    script_path = load_path + BuildServerPath.CONFIG_LAB_REL_PATH + "/scripts"

    cmd = "test -e " + config_path
    assert server.ssh_conn.exec_cmd(cmd, rm_date=False)[0] == 0, ' lab config path not found in {}:{}'.format(
            server.name, config_path)

    cmd = "test -e " + script_path
    assert server.ssh_conn.exec_cmd(cmd, rm_date=False)[0] == 0, ' lab scripts path not found in {}:{}'.format(
            server.name, script_path)

    pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.get_password())
    server.ssh_conn.rsync(config_path + "/*",
                          lab['controller-0 ip'],
                          WRSROOT_HOME, pre_opts=pre_opts)

    server.ssh_conn.rsync(script_path + "/*",
                          lab['controller-0 ip'],
                          WRSROOT_HOME, pre_opts=pre_opts)


def download_lab_config_file(lab, server, load_path, config_file='lab_setup.conf'):

    lab_name = lab['name']
    if 'vbox' in lab_name:
        return

    if "yow" in lab_name:
        lab_name = lab_name[4:]

    config_path = "{}{}/yow/{}/{}".format(load_path, BuildServerPath.CONFIG_LAB_REL_PATH , lab_name, config_file)

    cmd = "test -e " + config_path
    assert server.ssh_conn.exec_cmd(cmd, rm_date=False)[0] == 0, ' lab config path not found in {}:{}'.format(
            server.name, config_path)

    pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.get_password())
    server.ssh_conn.rsync(config_path,
                          lab['floating ip'],
                          WRSROOT_HOME, pre_opts=pre_opts)

def bulk_add_hosts(lab, hosts_xml_file):
    controller_ssh = ControllerClient.get_active_controller(lab["short_name"])
    cmd = "test -f {}/{}".format(WRSROOT_HOME, hosts_xml_file)
    if controller_ssh.exec_cmd(cmd)[0] == 0:
        rc, output = cli.system("host-bulk-add", hosts_xml_file, fail_ok=True)
        if rc != 0 or  "Configuration failed" in output:
            msg = "system host-bulk-add failed"
            return rc, None, msg
        hosts = system_helper.get_hosts_by_personality()
        return 0, hosts, ''


def add_storages(lab, server, load_path, ):
    lab_name = lab['name']
    if "yow" in lab_name:
        lab_name = lab_name[4:]

    if 'storage_nodes' not in lab:
        return 1, "Lab {} does not have storage nodes.".format(lab_name)

    storage_nodes = lab['storage_nodes']

    download_lab_config_files(lab, server, load_path)

    controller_ssh = ControllerClient.get_active_controller(lab['short_name'])
    cmd = "test -e {}/hosts_bulk_add.xml".format(WRSROOT_HOME )
    rc = controller_ssh.exec_cmd(cmd)[0]

    if rc != 0:
        msg = "The hosts_bulk_add.xml file missing from active controller"
        return rc, msg

    # check if the hosts_bulk_add.xml contains storages in mujltiple of 2
    cmd = "grep storage {}/hosts_bulk_add.xml".format(WRSROOT_HOME)
    rc, output = controller_ssh.exec_cmd(cmd)
    if rc == 0:
        output = output.split('\n')
        count = 0
        for line in output:
            if "personality" in line:
                count += 1
        if count < 2 or  count % 2 != 0:
            # invalid host_bulk_add.xml file
            msg = "Invalid hosts_bulk_add.xml file. Contains {} storages".format(count)
            return 1, msg
           # system host-bulk-add to add the storages. ignore the error case
        rc, hosts, msg = bulk_add_hosts(lab, "hosts_bulk_add.xml")
        if rc != 0 or hosts is None:
            return rc, msg
        if len(hosts[2]) != count:
            msg = "Unexpected  number of storage nodes: {}; exepcted are {}".format(len(hosts[2]), count)
            return 1, msg
    else:
        msg = "No storages in the hosts_bulk_add.xml or file not found"
        return rc, msg

    # boot storage nodes
    boot_interface_dict = lab['boot_device_dict']

    storage_hosts = system_helper.get_storage_nodes()
    storage_pairs = [storage_hosts[x:x+2] for x in range(0, len(storage_hosts), 2)]

    for pairs in storage_pairs:
        LOG.tc_step("Powering on storage hosts: {} ...".format(pairs))
        power_on_host(pairs, wait_for_hosts_state_=False)
        for host in pairs:
            open_vlm_console_thread(host, boot_interface=boot_interface_dict)
        wait_for_hosts_state(pairs)

    LOG.info("Storage hosts installed successfully......")

    # configure storages
    rc, msg = run_lab_setup(con_ssh=controller_ssh)
    if rc != 0:
        return rc, msg

    LOG.info("Unlocking Storage hosts {}.....".format(storage_hosts))
    host_helper.unlock_hosts(storage_hosts)
    LOG.info("Storage hosts unlocked ......")

    return 0, "Storage hosts {} installed successfully".format(storage_hosts)


def run_lab_setup(con_ssh=None, timeout=3600):
    return run_setup_script(script="lab_setup", config=True)


def run_infra_post_install_setup():
    return run_setup_script(script="lab_infra_post_install_setup", config=True)


def run_setup_script(script="lab_setup", config=False, con_ssh=None, timeout=3600):
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()
    if config:
        cmd = "test -e {}/{}.conf".format(WRSROOT_HOME, script)
        rc = con_ssh.exec_cmd(cmd)[0]

        if rc != 0:
            msg = "The {}.conf file missing from active controller".format(script)
            return rc, msg

    cmd = "test -e {}/{}.sh".format(WRSROOT_HOME, script)
    rc = con_ssh.exec_cmd(cmd, )[0]

    if rc != 0:
        msg = "The {}.sh file missing from active controller".format(script)
        return rc, msg

    cmd = "cd; source /etc/nova/openrc; ./{}.sh".format(script)
    con_ssh.set_prompt(Prompt.ADMIN_PROMPT)
    rc, msg = con_ssh.exec_cmd(cmd, expect_timeout=timeout)
    if rc != 0:
        msg = " {} run failed: {}".format(script, msg)
        LOG.warning(msg)
        return rc, msg
    con_ssh.set_prompt()
    return 0, "{} run successfully".format(script)


def launch_vms_post_install():
    """
    Launchs VMs using the launch scripts generated after running lab_setup.sh post install. Verifies the created
    VMs are pingable.
    Returns(list): list of VM ids that are generated

    """
    vms = vm_helper.get_any_vms(all_tenants=True)
    existing_vms_count = len(vms)

    if existing_vms_count > 0:
        LOG.info("VMs exist; may be already launched as part of install: {} ".format(vms))
    else:
        # check if vm launch scripts exist in the lab
        active_controller = ControllerClient.get_active_controller()
        cmd = "test -e {}/instances_group0/launch_instances.sh".format(WRSROOT_HOME)
        rc = active_controller.exec_cmd(cmd)[0]
        if rc != 0:
            LOG.info("VM Launching scripts do not exist in lab..... ")
        else:

            LOG.info("Launching VMs using the launch script .... ")

            tenants = ['tenant1', 'tenant2']
            for tenant in tenants:
                LOG.info("Launching {} VMs".format(tenant))
                cmd = "~/instances_group0/./launch_{}_instances.sh".format(tenant)
                rc, output = active_controller.exec_cmd(cmd)
                time.sleep(10)

    vms = vm_helper.get_any_vms(all_tenants=True)

    if len(vms) > 0:
        LOG.info("Verifying VMs are pingable : {} ".format(vms))
        vm_helper.ping_vms_from_natbox(vm_ids=vms)
        LOG.info("VMs launched successfully post install")
    return vms


def get_usb_device_name(con_ssh=None):
    """
    Gets the USB disk device name from the system. Not the partition devices
    Args:
        con_ssh:

    Returns:

    """

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    usb_device = None
    # check if a USB is plugged in
    cmd = "\ls -lrtd /dev/disk/by-id/usb*"
    rc, output = con_ssh.exec_cmd(cmd)
    if rc != 0:
        msg = "No USB found in lab node. Please plug in usb ."
        LOG.info(msg)
    else:
        usb_ls = output.strip().splitlines()[0].split("->").pop()

        LOG.info("USB found: {}".format(usb_ls))
        usb_device = usb_ls.strip().split("/").pop()
        LOG.info("USB found: {}".format(usb_device))
        usb_device = usb_device[0:3]
        LOG.info("USB device is: {}".format(usb_device))

    LOG.info("USB device is: {}".format(usb_device))
    if 'sd' not in usb_device or len(usb_device) != 3:
        return None
    return usb_device


def get_usb_device_partition_info(usb_device=None, con_ssh=None):
    """
    Gets the partition of usb as dict with values device name, size, type and mountpoint.
    {<device_name> : [<device_name, <size>, <type>, <mountpoint>]}
    where:
        device_name is the device name like sdc, sdd
        size is the size of partition/disk
        type - whether it is partition or disk
        mountpoint - the mounting point of the partition if there is any
    Args:
        con_ssh:

    Returns: dict

    """

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()
    usb_partition_info = {}

    if usb_device is None:
        usb_device = get_usb_device_name(con_ssh=con_ssh)

    if usb_device is None:
        msg = "No USB found in lab node. Please plug in usb ."
        LOG.info(msg)

    else:
        # check if a USB is plugged in
        cmd = "\lsblk -l | \grep {} | awk ' {{ print $1 \" \" $4\" \" $6\" \"$7}}'".format(usb_device)
        rc, output = con_ssh.exec_cmd(cmd)
        if rc != 0:
            msg = "command failed to get USB partition info: {}".format(output)
            LOG.info(msg)
            return None
        else:
            usb_part_ls = output.splitlines()
            for line in usb_part_ls:
                info = line.strip().split()
                usb_partition_info[info[0]] = info

        LOG.info("USB device partition info is: {}".format(usb_partition_info))

    return usb_partition_info


def get_usb_disk_size(usb_device, con_ssh=None):
    """
    Gets the total USB disk size
    Args:
        usb_device:
        con_ssh:

    Returns:

    """

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    if usb_device is None:
        raise ValueError("USB  device name must be supplied")

    parts_info = get_usb_device_partition_info(usb_device=usb_device, con_ssh=con_ssh)

    for k, v in parts_info.items():
       if k == usb_device and v[2] == 'disk':
           return float(v[1][:-1])
    else:
       LOG.info("USB device {} has no partition: {}".format(usb_device, parts_info))
       return -1


def get_usb_partition_size(usb_device, con_ssh=None):
    """
    Gets the usb partition size
    Args:
        usb_device:
        con_ssh:

    Returns:

    """

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    if usb_device is None:
        raise ValueError("USB partition device name must be supplied")

    parts_info = get_usb_device_partition_info(con_ssh=con_ssh)

    for k, v in parts_info.items():

       if k == usb_device and v[2] == 'part':
           LOG.info("device = {}; size {}".format(k, float(v[1][:-1])))
           return float(v[1][:-1])
    else:
       LOG.info("USB device {} has no partition: {}".format(usb_device, parts_info))
       return -1


def get_usb_mount_point(usb_device=None, con_ssh=None):
    """
    Gets the mounting point of usb
    Args:
        usb_device:
        con_ssh:

    Returns:

    """

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    if usb_device is None:
        usb_device = get_usb_device_name(con_ssh=con_ssh)

    if usb_device is None:
        msg = "No USB found in lab node. Please plug in usb ."
        LOG.info(msg)
        return None

    usb_partition_info = get_usb_device_partition_info(con_ssh=con_ssh)

    for k, v in usb_partition_info.items():
        if usb_device == k and len(v) == 4:
            return v[3]
    return None


def partition_usb(con_ssh=None, **kwargs):

    """
    Creates partition on the uSB. The number of partions must be specified through kwargs dictionary
    as part1=<size1>, part2=<size2>, ... part<n>=default.  e.g for creating two partion with first size  2G and  the
    second with the rest:  part1=2, part2='default'
    Args:
        con_ssh:
        **kwargs: partition sizes as  art1=<size1>, part2=<size2>, ... part<n>='default'

    Returns:

    """

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    #TODO: work for generic function


def usb_create_partition_for_backup(usb_device=None, con_ssh=None):
    """
    Creates two partitions on USB for backup. The first is bootable with  2G in size for iso file.
    The second partition is non-bootable for backup files. Both are formatted with ext4 fs.

    Args:
        con_ssh:

    Returns:

    """


    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    usb_partition_info = {}
    if usb_device is None:
        usb_device = get_usb_device_name(con_ssh=con_ssh)

    if usb_device is None:
        msg = "No USB found in lab node. Please plug in usb ."
        LOG.info(msg)
        return None
    # check if usb is mount. If yes unmount the usb device

    current_parts = get_usb_device_partition_info(usb_device=usb_device, con_ssh=con_ssh)

    for k, v in current_parts.items():
        if len(v) == 4:
            con_ssh.exec_sudo_cmd("umount {}".format(k))

    FDISK_COMMAND_PROMPT = "Command \(m for help\)\: "
    FDISK_PART_SELECT_PROMPT = "Select \(default p\)\: "
    FDISK_PART_NUM_PROMPT = "Partition number(.*)\: "
    FDISK_FIRST_SECTOR_PROMPT = "First sector(.*)\: "
    FDISK_LAST_SECTOR_PROMPT = "Last sector(.*)\: "

    fdisk_prompts = [FDISK_COMMAND_PROMPT, FDISK_PART_SELECT_PROMPT, FDISK_PART_NUM_PROMPT,
                     FDISK_FIRST_SECTOR_PROMPT, FDISK_LAST_SECTOR_PROMPT ]

    prompts = [con_ssh.prompt]
    prompts.extend(fdisk_prompts)
    prompts.append(Prompt.SUDO_PASSWORD_PROMPT)

    con_ssh.send("sudo fdisk /dev/{}".format(usb_device), flush=True)
    index = con_ssh.expect(prompts)

    if index == prompts.index(Prompt.SUDO_PASSWORD_PROMPT):
        con_ssh.send(HostLinuxCreds.get_password())
        prompts.remove(Prompt.SUDO_PASSWORD_PROMPT)
        index = con_ssh.expect(prompts)

    if index != prompts.index(FDISK_COMMAND_PROMPT):
        msg = "Unexpeced out from fdisk command; expecting: {}".format(FDISK_COMMAND_PROMPT)
        LOG.info(msg)
        return False, msg


    con_ssh.send("o", flush=True)
    index = con_ssh.expect(prompts)
    if index != prompts.index(FDISK_COMMAND_PROMPT):
        msg = "Unexpeced output from fdisk command; expecting: {}".format(FDISK_COMMAND_PROMPT)
        LOG.info(msg)
        return False, msg

    con_ssh.send("n", flush=True)
    #prompts.remove(FDISK_COMMAND_PROMPT)
    #prompts.append(FDISK_PART_SELECT_PROMPT)
    index = con_ssh.expect(prompts)
    if index != prompts.index(FDISK_PART_SELECT_PROMPT):
        msg = "Unexpeced output from fdisk command; expecting: {}".format(FDISK_PART_SELECT_PROMPT)
        LOG.info(msg)
        return False, msg

    con_ssh.send("p", flush=True)
    #prompts.remove(FDISK_PART_SELECT_PROMPT)
    #prompts.append(FDISK_PART_NUM_PROMPT)
    index = con_ssh.expect(prompts)
    if index != prompts.index(FDISK_PART_NUM_PROMPT):
        msg = "Unexpeced output from fdisk command; expecting: {}".format(FDISK_PART_NUM_PROMPT)
        LOG.info(msg)
        return False, msg


    con_ssh.send("1", flush=True)
    index = con_ssh.expect(prompts)
    if index != prompts.index(FDISK_FIRST_SECTOR_PROMPT):
        msg = "Unexpeced output from fdisk command; expecting: {}".format(FDISK_FIRST_SECTOR_PROMPT)
        LOG.info(msg)
        return False, msg

    con_ssh.send("\n", flush=True)
    index = con_ssh.expect(prompts)
    if index != prompts.index(FDISK_LAST_SECTOR_PROMPT):
        msg = "Unexpeced output from fdisk command; expecting: {}".format(FDISK_LAST_SECTOR_PROMPT)
        LOG.info(msg)
        return False, msg

    con_ssh.flush()
    con_ssh.send(str(b'2097152'), flush=True)
    index = con_ssh.expect(prompts)
    if index != prompts.index(FDISK_COMMAND_PROMPT):
        msg = "Unexpeced output from fdisk command; expecting: {}".format(FDISK_LAST_SECTOR_PROMPT)
        LOG.info(msg)
        return False, msg

    code, output = con_ssh.proecess_cmd_result(r'+' + '2G', get_exit_code=False)
    expected = "Partition 1 of type Linux and size 2 GiB is set"
    if not bool(re.search(expected, output)):
        msg = "Unexpeced out from fdisk last sector command : {}".format(output)
        LOG.info(msg)
        return False, msg


    con_ssh.send("n")
    index = con_ssh.expect(prompts)
    if index != prompts.index(FDISK_PART_SELECT_PROMPT):
        msg = "Unexpeced output from fdisk command; expecting: {}".format(FDISK_PART_SELECT_PROMPT)
        LOG.info(msg)
        return False, msg

    con_ssh.send("p")
    index = con_ssh.expect(prompts)
    if index != prompts.index(FDISK_PART_NUM_PROMPT):
        msg = "Unexpeced output from fdisk command; expecting: {}".format(FDISK_PART_NUM_PROMPT)
        LOG.info(msg)
        return False, msg


    con_ssh.send("2")
    index = con_ssh.expect(prompts)
    if index != prompts.index(FDISK_FIRST_SECTOR_PROMPT):
        msg = "Unexpeced output from fdisk command; expecting: {}".format(FDISK_FIRST_SECTOR_PROMPT)
        LOG.info(msg)
        return False, msg


    con_ssh.send("\n")
    index = con_ssh.expect(prompts)
    if index != prompts.index(FDISK_LAST_SECTOR_PROMPT):
        msg = "Unexpeced output from fdisk command; expecting: {}".format(FDISK_LAST_SECTOR_PROMPT)
        LOG.info(msg)
        return False, msg


    con_ssh.send("\n")
    if index != prompts.index(FDISK_COMMAND_PROMPT):
        msg = "Unexpeced output from fdisk command; expecting: {}".format(FDISK_LAST_SECTOR_PROMPT)
        LOG.info(msg)
        return False, msg

    code, output = con_ssh.proecess_cmd_result("+2000M", get_exit_code=False)
    expected = "Partition 2 of type Linux and size \d(.*)GiB is set"
    if not bool(re.search(expected, output)):
        msg = "Unexpeced out from fdisk last sector command : {}".format(output)
        LOG.info(msg)
        return False, msg

    con_ssh.send("a")
    index = con_ssh.expect(prompts)
    if index != prompts.index(FDISK_PART_NUM_PROMPT):
        msg = "Unexpeced output from fdisk command; expecting: {}".format(FDISK_PART_NUM_PROMPT)
        LOG.info(msg)
        return False, msg


    con_ssh.send("1")
    if index != prompts.index(FDISK_COMMAND_PROMPT):
        msg = "Unexpeced output from fdisk command; expecting: {}".format(FDISK_LAST_SECTOR_PROMPT)
        LOG.info(msg)
        return False, msg

    con_ssh.send("w")
    if index != prompts.index(con_ssh.prompt):
        msg = "Unexpeced output from fdisk command; expecting: {}".format(FDISK_LAST_SECTOR_PROMPT)
        LOG.info(msg)
        return False, msg

    # cmd2 = 'echo -e "o\nn\np\n1\n\n+2000M\nn\np\n2\n\n\na\n1\nw" | sudo fdisk /dev/{}'.format(usb_device)
    # # cmd = """\
    # # fdisk /dev/{} <<EOF
    # # n
    # # p
    # # 1
    # #
    # # +2000M
    # # n
    # # p
    # # 2
    # #
    # #
    # # a
    # # 1
    # # w
    # # EOF""".format(usb_device)
    #
    # rc, output = con_ssh.exec_sudo_cmd(cmd2)
    # if rc != 0:
    #     msg = "command failed to get USB partition info: {}".format(output)
    #     LOG.info(msg)
    #     return False, None

    part_info = get_usb_device_partition_info(con_ssh=con_ssh)

    if len(part_info) != 3:
        error_msg = "Unexpected partition in usb: {}".format(part_info)
        return False, error_msg
    for k, v in part_info.items():
        if usb_device not in k:
            error_msg = "Unexpected device names in partition/disk: {}".format(part_info)
            return False, error_msg

    # create fs on partitions
    cmd1 = "mkfs -t ext4 /dev/{}"
    for k, v in part_info.items():
        if "part" in v[2]:
            cmd = cmd1.format(k)
            rc, output = con_ssh.exec_sudo_cmd(cmd)
            if rc != 0:
                return False, "Fail to format {}: {}".format(k, output)

    return True, part_info


def is_usb_mounted(usb_device, con_ssh=None):
    """
    Checkes if a USB is mounted or not. If yes, returns the mount point
    Args:
        usb_device:

    Returns:

    """

    if usb_device is None:
        LOG.info("No usb device name is specified")
        return False, None
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    mount_pt = get_usb_mount_point(usb_device, con_ssh=con_ssh)
    if mount_pt:
        return True, mount_pt
    else:
        return False, None

# def get_usb_info(con_ssh=None):
#     """
#     Gets the USB info if present. Mounts USB if not already mounted.
#     Returns:
#
#     """
#
#     usb_info = {}
#     usb_device = get_usb_device_name(con_ssh=con_ssh)
#     if not usb_device:
#         msg = "No USB device found in active controller"
#         LOG.info(msg)
#         return None
#     LOG.info("USB device name is {}".format(usb_device))
#     usb_info['device'] = usb_device
#     result, mount_dir = is_usb_mounted(usb_device, con_ssh=con_ssh)
#     if not result:
#         # usb not mounted,  mount the usb to /media/wrsroot
#         mount_dir=BACKUP_USB_MOUNT_POINT
#         if not mount_usb(usb_device, mount=mount_dir, con_ssh=con_ssh):
#            LOG.info("Fail to mount the usb /dev/{} to {}".format(usb_device, BACKUP_USB_MOUNT_POINT))
#            return None
#
#     usb_info['mount'] = mount_dir
#
#     return usb_info


def delete_backup_files_from_usb(usb_device, con_ssh=None):
    """
    Deletes backup files from the usb to make it ready for next backup.
    Args:
        usb_info:
        con_ssh:

    Returns (bool):

    """

    if not con_ssh:
        con_ssh = ControllerClient.get_active_controller()

    if not usb_device:
        raise ValueError("usb device name must be provided")

    rc, mout_pt = is_usb_mounted(usb_device, con_ssh=con_ssh)
    if not rc:
        LOG.warning("USB partition is not mount")
        return False

    mount_pt = get_usb_mount_point(usb_device=usb_device, con_ssh=con_ssh)

    if con_ssh.exec_sudo_cmd("test -e {}/backups".format(mount_pt))[0] == 0:
        con_ssh.exec_sudo_cmd("rm -f {}/backups/*".format(mount_pt))
        LOG.info("Verifying all backup files are deleted from {}/backups".format(mount_pt))
        rc, output = con_ssh.exec_cmd("ls {}/backups | wc -l".format(mount_pt))
        if int(output) > 0:
            LOG.warning("Fail to delete all  backup files from {}/backups. There are {} files still in USB"
                    .format(mount_pt, output))
            return False
        else:
            LOG.info(" USB is cleaned successfully. Ready for new backup files")

    return True


def mount_usb (usb_device, mount=None, unmount=True, format_=False, con_ssh=None):
    """
    Mounts USB to a mounting point specified by mount or the default /media/wrsroot
    Args:
        usb_device(str): the USB device name
        mount(str): is the path to the mount point
        unmount(bool): if enabled,  the USB is unmounted before mount. Default is enabled

    Returns (bool):
        True - successfully mounted
        False - Fail to mount

    """

    if mount is None:
        mount = BACKUP_USB_MOUNT_POINT

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    if is_usb_mounted(usb_device, con_ssh=con_ssh)[0]:
        if not unmount:
            LOG.info("USB is already mounted")
            return True
        else:
            # unmount the usb first
            cmd = "umount -l /dev/{}".format(usb_device)
            con_ssh.exec_sudo_cmd(cmd)
    if con_ssh.exec_cmd("test -e {}".format(mount)) [0] != 0:
        con_ssh.exec_sudo_cmd("mkdir {}".format(mount),strict_passwd_prompt=True)

    cmd = "mount /dev/{} {}".format(usb_device, mount)
    rc, output = con_ssh.exec_sudo_cmd(cmd)
    if rc != 0:
        LOG.info("Fail to mount usb {} to mount point {}: {}".format(usb_device, mount, output))
        return False
    return True


def restore_controller_system_config(system_backup, tel_net_session=None, con_ssh=None, is_aio=False, fail_ok=False):
    """
    Restores the controller system config for system restore.
    Args:
        system_backup(str): The system config backup file
        tel_net_session:
        fail_ok:

    Returns (tuple): rc, text message
        0 - Success
        1 - Execution of restore command failed
        2 - Patches not applied after system reboot
        3 - Unexpected result after system resotre

    """

    if system_backup is None or not os.path.abspath(system_backup):
        msg = "Full path of the system backup file must be provided: {}".format(system_backup)
        LOG.info(msg)
        raise ValueError(msg)

    lab = InstallVars.get_install_var("LAB")
    output_dir = ProjVar.get_var('LOG_DIR')
    controller0_node = lab['controller-0']

    if controller0_node.telnet_conn is None:
        controller0_node.telnet_conn = open_telnet_session(controller0_node, output_dir)
        controller0_node.telnet_conn.login()

    connection = controller0_node.telnet_conn
    cmd = 'echo "{}" | sudo -S config_controller --restore-system {}'.format(HostLinuxCreds.get_password(),
                                                                             system_backup)
    os.environ["TERM"] = "xterm"

    rc, output = connection.exec_cmd(cmd, extra_expects=outputs_restore_system_conf, timeout=HostTimeout.SYSTEM_RESTORE)
    compute_configured = False
    if rc == 0:
        if 'compute-config in progress' in output:
            if not is_aio:
                LOG.fatal('Not an AIO lab, but the system IS configuring compute functionality')
            else:
                LOG.info('No need to do compute-config-complete, which is a new behavior after 2017-11-27.')
                LOG.info('Instead, we will have to wait the node self-boot and boot up to ready states.')

            connection.find_prompt(prompt='controller\-[01] login:')

            LOG.info('Find login prompt, try to login')
            connection.login()

            compute_configured = True
            # todo: just be consistent with other codes, maybe not the correct type
            os.environ["TERM"] = "xterm"

            LOG.warn('checking system states')

            cmd = 'cd; source /etc/nova/openrc'
            rc, output = connection.exec_cmd(cmd)
            assert rc == 0, \
                'Failed to source the openrc after restore system configuration, rc:{}, output:\n{}'.format(rc, output)
            LOG.info('OK to source openrc')

            cmd = 'system host-list'
            rc, output = connection.exec_cmd(cmd)
            assert rc == 0, \
                'Failed to run {}, rc:{}, output:\n{}'.format(cmd, rc, output)

            cmd = 'openstack endpoint list'
            rc, output = connection.exec_cmd(cmd)
            assert rc == 0, \
                'Failed to run {}, rc:{}, output:\n{}'.format(cmd, rc, output)

            LOG.info('OK to get hosts list\n{}\n'.format(output))

        elif 'reboot controller' in output:
            LOG.info('Prompted to reboot, reboot now')
            msg = 'System WAS patched, and now is restored to the previous patch-level, but still needs a reboot'
            LOG.info(msg)

            reboot_cmd = 'echo "{}" | sudo -S reboot'.format(HostLinuxCreds.get_password())

            rc, output = connection.exec_cmd(reboot_cmd, alt_prompt=' login: ', timeout=HostTimeout.REBOOT)
            if rc != 0:
                msg = '{} failed, rc:{}\noutput:\n{}'.format(reboot_cmd, rc, output)
                LOG.error(msg)
                raise exceptions.RestoreSystem
            LOG.info('OK, system reboot after been patched to previous level')

            LOG.info('re-login')
            connection.login()
            os.environ["TERM"] = "xterm"

            LOG.info('re-run cli:{}'.format(cmd))
            rc, output = connection.exec_cmd(cmd, timeout=HostTimeout.SYSTEM_RESTORE)

            if "System restore complete" in output:
                msg = "System restore completed successfully"
                LOG.info(msg)
                return 0, msg, compute_configured

    else:
        err_msg = "{} execution failed: {} {}".format(cmd, rc, output)
        LOG.error(err_msg)
        if fail_ok:
            return 1, err_msg, compute_configured
        else:
            raise exceptions.CLIRejected(err_msg)

    return rc, output, compute_configured


def restore_controller_system_images(images_backup, tel_net_session=None, fail_ok=False):
    """
    Restores the controller system images for system restore.
    Args:
        images_backup(str): The system image backup file
        tel_net_session:
        fail_ok:

    Returns (tuple): rc, text message
        0 - Success
        1 - Execution of restore command failed
        2 - System image restore did not complete

    """

    if images_backup is None or not os.path.abspath(images_backup):
        msg = "Full path of the system backup file must be provided: {}".format(images_backup)
        LOG.info(msg)
        raise ValueError(msg)

    lab = InstallVars.get_install_var("LAB")
    output_dir = ProjVar.get_var('LOG_DIR')
    controller0_node = lab['controller-0']
    if tel_net_session is None:

        if controller0_node.telnet_conn is None:
            controller0_node.telnet_conn = open_telnet_session(controller0_node, output_dir)
            controller0_node.telnet_conn.login()

        tel_net_session = controller0_node.telnet_conn

    cmd = "echo " + HostLinuxCreds.get_password() + " | sudo -S config_controller --restore-images {}".format(images_backup)
    os.environ["TERM"] = "xterm"

    rc, output = tel_net_session.exec_cmd(cmd, timeout=HostTimeout.SYSTEM_RESTORE)
    if rc != 0:
        err_msg = "{} failed: {} {}".format(cmd, rc, output)
        LOG.error(err_msg)
        if fail_ok:
            return 1, err_msg
        else:
            raise exceptions.CLIRejected(err_msg)

    # Checking  if images restore succeeds
    if "Images restore complete" in output:
        # images restored
        msg = "Images restore completed successfully"
        LOG.info(msg)
        return 0, msg
    else:
        err_msg = "Unexpected result from images restore: {}".format(output)

        if fail_ok:
            return 2, err_msg
        else:
            raise exceptions.RestoreSystem(err_msg)


def get_backup_files_from_usb(pattern, usb_device=None, con_ssh=None):
    """
    Gets the backup files that match the specified pattern
    Args:
        pattern:
        usb_device:
        con_ssh:

    Returns(list): list of backup files

    """

    LOG.info("Getting backup files with pattern {} from usb".format(pattern))

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()
    if usb_device is None:
        usb_device = get_usb_device_name(con_ssh=con_ssh)

    found_backup_files = []

    if not usb_device:
        LOG.info("No USB found in active controller")
    else:
        usb_part_info = get_usb_device_partition_info(usb_device=usb_device, con_ssh=con_ssh)
        mount_dir = ''
        for k, v in usb_part_info.items():
            if len(v) == 4 and get_usb_partition_size(usb_device=k, con_ssh=con_ssh) > 8:
                mount_dir = v[3]

        backup_path = "{}/backups".format(mount_dir)

        cmd = 'test -e {}'.format(backup_path)

        if con_ssh.exec_cmd(cmd)[0] == 0 and pattern:

            rc, backup_files = con_ssh.exec_cmd("\ls {}/*.tgz".format(backup_path))
            if rc == 0:
                files_list = backup_files.split()
                for file in files_list:
                    file = os.path.basename(file.strip())
                    if re.match(pattern, file):
                        LOG.info("Found matching backup file: {}".format(file))
                        found_backup_files.append(file)
        else:
            LOG.warn("The path {} does not exist in controller-0".format(backup_path))

    return found_backup_files


def get_backup_files(pattern, backup_src_path, src_conn_ssh):
    """

    Args:
        pattern:
        backup_src_path:
        src_conn_ssh:

    Returns:

    """

    if pattern is None or backup_src_path is None or src_conn_ssh is None:
        raise ValueError("pattern, backup_src_path and src_conn_ssh must be specified; cannot be None.")

    src_host = src_conn_ssh.exec_cmd("hostname")[1]
    LOG.info("Getting backup files with pattern {} from src {}: {}".format(pattern, src_host, backup_src_path))

    found_backup_files = []
    cmd = 'test -e {}'.format(backup_src_path)
    if src_conn_ssh.exec_cmd(cmd)[0] == 0:
        rc, backup_files = src_conn_ssh.exec_cmd("\ls {}/*.tgz".format(backup_src_path))
        if rc == 0:
            files_list = backup_files.split()
            for file in files_list:
                file = os.path.basename(file.strip())
                if re.match(pattern, file):
                    LOG.info("Found matching backup file: {}".format(file))
                    found_backup_files.append(file)
    else:
        LOG.warn("The path {} does not exist in source {}".format(backup_src_path, src_host))

    return found_backup_files


def get_titanium_backup_filenames_usb(pattern=None, usb_device=None, con_ssh=None):
    """
    Gets the titanium system backup files from USB
    Args:
        pattern:
        con_ssh:

    Returns:

    """

    if pattern is None:
        pattern = TITANIUM_BACKUP_FILE_PATTERN
    found_backup_files = []

    backup_files = get_backup_files_from_usb(pattern=pattern, usb_device=usb_device, con_ssh=con_ssh)

    lab = InstallVars.get_install_var("LAB")
    system_name = lab['name']
    for file in backup_files:
        if system_name.strip() in file:
            LOG.info("Found matching backup file: {}".format(file))
            found_backup_files.append(file)

    LOG.info(" Lab {} backup files: {}".format(system_name, found_backup_files))

    return found_backup_files


def get_image_backup_filenames_usb(pattern=None, usb_device=None, con_ssh=None):
    """
    Gets the image backup files from USB
    Args:
        pattern:
        con_ssh:

    Returns:

    """

    if pattern is None:
        pattern = IMAGE_BACKUP_FILE_PATTERN

    return get_backup_files_from_usb(pattern=pattern, usb_device=usb_device, con_ssh=con_ssh)


def import_image_from_backup(image_backup_files, con_ssh=None, fail_ok=False):
    """
    Imports images from backup files for system restore
    Args:
        image_backup_files:
        con_ssh:
        fail_ok:

    Returns:

    """

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()
    if isinstance(image_backup_files, str):
        image_backup_files = [image_backup_files]

    images_imported = []
    images_failed = []
    cmd = 'image-backup import '
    for file in image_backup_files:
        if not os.path.abspath(file):
            # msg = "Full path of the image backup file must be provided: {}".format(file)
            # LOG.info(msg)
            # if fail_ok:
            #     return 1, msg
            # else:
            #     raise ValueError(msg)
            file = TiSPath.BACKUPS + '/' + file
        rc, output = con_ssh.exec_sudo_cmd(cmd + file, expect_timeout=300)
        if rc != 0:
            msg = "Image import not successfull for image file: {}".format(file)
            LOG.info(msg)
            images_failed.append(file)
        else:
            if 'Importing image: 100% complete...done' in output:
                msg = "Image import  successfull for image file: {}".format(file)
                LOG.info(msg)
                images_imported.append(file)
            else:
                msg = "Incomplete image import;  command returned success code for image file: {}".format(file)
                LOG.info(msg)
                images_failed.append(file)

    return images_imported


def get_cinder_volume_backup_filenames_usb(pattern=None, con_ssh=None):

    if pattern is None:
        pattern = CINDER_VOLUME_BACKUP_FILE_PATTERN

    return get_backup_files_from_usb(pattern=pattern, con_ssh=con_ssh)


def restore_cinder_volumes_from_backup( con_ssh=None, fail_ok=False):
    """
    Restores cinder volumes from backup files for system restore. If volume snaphot exist for a volume, it will be
    deleted before restoring the volume
    Args:
        con_ssh:
        fail_ok:

    Returns (tuble): rc, error message/
        0 - success

    """

    # get the cinder volume backup files from source drive; assuming all backup files are available from usb drive
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    cinder_volume_backups = get_backup_files(CINDER_VOLUME_BACKUP_FILE_PATTERN, TiSPath.BACKUPS, con_ssh)

    if len(cinder_volume_backups) == 0:
        msg = "No cinder volume backup files found from the {} drive".format(TiSPath.BACKUPS)
        LOG.info(msg)
        return 1, None
    else:

        # Checking for any snaphsots of the cinder volumes to be restored.
        # As per the Software management guide, the cinder volume restore fails if a snapshot of that volume exist.
        LOG.info("Checking if cinder volumes have snapshots ... ")
        vol_snap_ids = cinder_helper.get_volume_snapshot_list(con_ssh=con_ssh)
        if len(vol_snap_ids):
            for id in vol_snap_ids:
                LOG.info(" snapshot id {} found; deleting ... ".format(id))
                if cinder_helper.delete_volume_snapshots(id, con_ssh=con_ssh, force=True)[0] == 0:
                    LOG.info(" Deleted snapshot id {} ... ".format(id))

        restored_cinder_volumes = import_volumes_from_backup(cinder_volume_backups, con_ssh=con_ssh)

        LOG.info("Restored volumes: {}".format(restored_cinder_volumes))
        restored = len(restored_cinder_volumes)

        if restored > 0:
            if restored == len(cinder_volume_backups):
                LOG.info("All volumes restored successfully")
                return 0, restored_cinder_volumes
            else:
                LOG.info("NOT all volumes were restored")
                return -1, restored_cinder_volumes
        else:
            LOG.info("Fail to restore any of the volumes")
            return 2, None


def import_volumes_from_backup(cinder_volume_backups, con_ssh=None):
    """
    Imports cinder volumes from backup files in /opt/backups for system restore.
    Args:
        cinder_volume_backups(list): List of cinder volume backup files to restore
        con_ssh:

    Returns(list): list of successfully imported volumes.

    """

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    imported_volumes = []

    volumes = cinder_helper.get_volumes(con_ssh=con_ssh)

    if len(cinder_volume_backups) == 0:
        msg = "The cinder volume backup file list specified is empty".format(cinder_volume_backups)
        LOG.info(msg)
    else:
        for volume_backup_path in cinder_volume_backups:
            volume_backup = os.path.basename(volume_backup_path)
            vol_id = volume_backup[7:-20]
            if vol_id not in volumes:
                LOG.warning("The volume {} does not exist; cannot be imported".format(vol_id))
                continue

            LOG.info("Importing Volume id={} ...".format(vol_id))
            rc, output = cinder_helper.import_volume(volume_backup, vol_id=vol_id, con_ssh=con_ssh, fail_ok=True)
            if rc == 2:
                # attempt to import volume one more time
                rc, output = cinder_helper.import_volume(volume_backup, vol_id=vol_id, con_ssh=con_ssh, fail_ok=True)
            if rc != 0:
                err_msg = "Fail to import volume {} from backup file {}".format(vol_id, volume_backup)
                LOG.error(err_msg)
                raise exceptions.CinderError(err_msg)

            imported_volumes.append(vol_id)
            LOG.info("Volume id={} imported successfully\n".format(vol_id))

    return imported_volumes


def export_cinder_volumes(backup_dest='usb', backup_dest_path=BackupRestore.USB_BACKUP_PATH, dest_server=None, copy_to_usb=None,
                          delete_backup_file=True, con_ssh=None, fail_ok=False):
    """
    Exports all available and in-use cinder volumes for system backup.
    Args:
        backup_file_prefix(str): The prefix to the generated system backup files. The default is "titanium_backup_"
        backup_dest(str): usb or local - the destination of backup files; choices are usb or local (test server)
        backup_dest_path(str): is the path at destination where the backup files are saved. The defaults are:
            /media/wrsroot/backups for backup_dest=usb and /sandbox/backups for backup_dest=local.
        copy_to_usb(str): usb_device name where the volume backup files are transferred. Default is None
        delete_backup_file(bool): if enabled, deletes the volume backup files after transfer to USB. Default is enabled
        con_ssh:

    Returns(list): list of exported volume ids

    """
    if backup_dest == 'usb' and backup_dest_path != BackupRestore.USB_BACKUP_PATH:
        raise ValueError("If backup file destination is usb then the path must be {}".
                         format(BackupRestore.USB_BACKUP_PATH))
    if backup_dest != 'usb' and backup_dest != "local":
        raise ValueError("Invalid destination {} specified; Valid options are 'usb' and 'local'".format(backup_dest))

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    volumes_exported = []
    current_volumes = cinder_helper.get_volumes()

    if len(current_volumes) > 0:
        LOG.info("Exporting Cinder volumes {}".format(current_volumes))
        volumes_exported.extend(cinder_helper.export_volumes()[1])

        if len(volumes_exported) > 0:
            LOG.info("Cinder volumes exported: {}".format(volumes_exported))
            if len(current_volumes) > len(volumes_exported):
                LOG.warn("Not all current cinder volumes are  exported; Unexported volumes: {}"
                         .format(set(current_volumes) - set(volumes_exported)))

            src_files = "/opt/backups/volume-*.tgz"

            if backup_dest == 'local':
                if dest_server:
                    if dest_server.ssh_conn.exec_cmd("test -e  {}".format(backup_dest_path))[0] != 0:
                        dest_server.ssh_conn.exec_cmd("mkdir -p {}".format(backup_dest_path))
                else:
                    if local_host.exec_cmd(["test", '-e',  "{}".format(backup_dest_path)])[0] != 0:
                        local_host.exec_cmd(["mkdir -p {}".format(backup_dest_path)])

                common.scp_from_active_controller_to_test_server(src_files, backup_dest_path, is_dir=False, multi_files=True)

                LOG.info("Verifying if backup files are copied to destination")
                if dest_server:
                    rc, output = dest_server.ssh_conn.exec_cmd("ls {}".format(backup_dest_path))
                else:
                    rc, output = local_host.exec_cmd(["ls {}".format(backup_dest_path)])

                if rc != 0:
                    err_msg = "Failed to scp cinder backup files {} to local destination: {}".format(backup_dest_path, output)
                    LOG.info(err_msg)
                    if fail_ok:
                        return 2, err_msg
                    else:
                        raise exceptions.BackupSystem(err_msg)

                LOG.info("Cinder volume backup files {} are copied to local destination successfully".format(output))

            else:
                # copy backup files to USB
                if copy_to_usb is None:
                    raise ValueError("USB device name must be provided, if destination is USB")

                LOG.tc_step("Transfer volume tgz file to usb flash drive" )
                results = mount_usb(usb_device=copy_to_usb)
                mount_pt = get_usb_mount_point(copy_to_usb)

                if mount_pt:

                    LOG.info("USB is plugged and is mounted to {}".format(mount_pt))
                    if con_ssh.exec_cmd("test -e {}/backups".format(mount_pt))[0] != 0:
                        con_ssh.exec_sudo_cmd("mkdir -p {}/backups".format(mount_pt))

                    cp_cmd = "cp /opt/backups/volume-*.tgz {}/backups/".format(mount_pt)
                    con_ssh.exec_sudo_cmd(cp_cmd, expect_timeout=HostTimeout.SYSTEM_RESTORE)
                    LOG.info("Verifying if cinder volume backup files are copied to USB")
                    rc, output = con_ssh.exec_cmd("ls  {}/backups/volume-*.tgz".format(mount_pt ))
                    copied_list = output.split()
                    not_list = []
                    for v_id in volumes_exported:
                        if not any(v_id in f for f in copied_list):
                           not_list.append(v_id)
                    if len(not_list) > 0:
                        LOG.warn("Following list not copied to usb: {}".format(not_list))

                else:
                    err_msg = "USB {} does not have mount point; cannot copy  backup files {} to USB"\
                        .format(copy_to_usb, src_files)
                    LOG.info(err_msg)
                    if fail_ok:
                        return 2, err_msg
                    else:
                        raise exceptions.BackupSystem(err_msg)

            if delete_backup_file:
                LOG.info("delete volume tgz file from tis server /opt/backups folder ")
                con_ssh.exec_sudo_cmd("rm -f /opt/backups/volume-*.tgz")

            LOG.info("Volumes exported successfully")

    return volumes_exported


def backup_system(backup_file_prefix=PREFIX_BACKUP_FILE, backup_dest='usb',
                  backup_dest_path=BackupRestore.USB_BACKUP_PATH, dest_server=None, lab_system_name=None,
                  timeout=HostTimeout.SYSTEM_BACKUP, copy_to_usb=None, delete_backup_file=True,
                  con_ssh=None, fail_ok=False):
    """
    Performs system backup  with option to transfer the backup files to USB.
    Args:
        backup_file_prefix(str): The prefix to the generated system backup files. The default is "titanium_backup_"
        backup_dest(str): usb or local - the destination of backup files; choices are usb or local (test server)
        backup_dest_path(str): is the path at destination where the backup files are saved. The defaults are:
            /media/wrsroot/backups for backup_dest=usb and /sandbox/backups for backup_dest=local.
        lab_system_name(str): is the lab system name
        timeout(inst): is the timeout value the system backup is expected to finish.
        copy_to_usb(str): usb device name, if specified,the backup files are copied to. Applicable when backup_dest=usb
        delete_backup_file(bool): if USB is available, the backup files are deleted from system to save disk space.
         Default is enabled
        con_ssh:
        fail_ok:

    Returns(tuple): rc, error message
        0 - Success
        1 - Fail to create system backup files
        2 - system backup files generated, but fail to transfer to USB


    """

    if backup_dest == 'usb' and backup_dest_path != BackupRestore.USB_BACKUP_PATH:
        raise ValueError("If backup file destination is usb then the path must be {}".
                         format(BackupRestore.USB_BACKUP_PATH))
    if backup_dest != 'usb' and backup_dest != "local":
        raise ValueError("Invalid destination {} specified; Valid options are 'usb' and 'local'".format(backup_dest))

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()
    lab = InstallVars.get_install_var("LAB")
    if lab_system_name is None:
        lab_system_name = lab['name']

    # execute backup command
    LOG.info("Create backup system and image tgz files under /opt/backups")
    if copy_to_usb:
        LOG.info("The backup system and image tgz file will be copied to {}:{}"
                 .format(copy_to_usb, get_usb_mount_point(usb_device=copy_to_usb)))
    date = time.strftime(BACKUP_FILE_DATE_STR)
    build_id = ProjVar.get_var('BUILD_ID')
    backup_file_name = "{}{}_{}_{}".format(PREFIX_BACKUP_FILE, date, build_id, lab_system_name)
    cmd = 'config_controller --backup {}'.format(backup_file_name)

    # max wait 1800 seconds for config controller backup to finish
    con_ssh.exec_sudo_cmd(cmd, expect_timeout=timeout)
    # verify the actual backup file are created
    rc, output = con_ssh.exec_cmd("\ls /opt/backups/{}*.tgz".format(backup_file_name))
    if rc != 0:
        err_msg = "Failed to create system backup files: {}".format(output)
        LOG.info(err_msg)
        if fail_ok:
            return 1, err_msg
        else:
            raise exceptions.BackupSystem(err_msg)
    backup_files = output.split()
    LOG.info("System backup files are created in /opt/backups folder: {} ".format(backup_files))
    if backup_dest == 'local':
        if os.path.basename(backup_dest_path) != lab['short_name']:
            backup_dest_path = backup_dest_path + "/{}".format(lab['short_name'])

        if dest_server:
            if dest_server.ssh_conn.exec_cmd("test -e {}".format(backup_dest_path))[0] != 0:
                dest_server.ssh_conn.exec_cmd("mkdir -p {}".format(backup_dest_path))
        else:
            if local_host.exec_cmd(["test", '-e',  "{}".format(backup_dest_path)])[0] != 0:
                local_host.exec_cmd(["mkdir -p {}".format(backup_dest_path)])

        src_files = "{} {}".format(backup_files[0].strip(), backup_files[1].strip())
        common.scp_from_active_controller_to_test_server(src_files, backup_dest_path, is_dir=False, multi_files=True)

        LOG.info("Verifying if backup files are copied to destination")
        if dest_server:
            rc, output = dest_server.ssh_conn.exec_cmd("ls {}/{}*.tgz".format(backup_dest_path, backup_file_name ))
        else:
            rc, output = local_host.exec_cmd(["ls {}/{}*.tgz".format(backup_dest_path, backup_file_name)])

        if rc != 0:
            err_msg = "Failed to scp system backup files {} to local destination: {}".format(backup_files, output)
            LOG.info(err_msg)
            if fail_ok:
                return 2, err_msg
            else:
                raise exceptions.BackupSystem(err_msg)

        LOG.info("The system backup files {} are copied to local destination successfully".format(output))

    else:
        # copy backup file to usb
        if copy_to_usb is None:
            raise ValueError("USB device name must be provided, if destination is USB")

        LOG.tc_step("Transfer system and image tgz file to usb flash drive" )
        result = mount_usb(copy_to_usb)
        mount_pt = get_usb_mount_point(usb_device=copy_to_usb)
        if mount_pt:
            if mount_pt not in backup_dest_path:
                raise ValueError("If USB is specified as destination, the destination path must be {}"
                                 .format(BackupRestore.USB_BACKUP_PATH))

            LOG.info("USB is plugged and is mounted to {}".format(mount_pt))
            if con_ssh.exec_cmd("test -e {}/backups".format(mount_pt))[0] != 0:
                con_ssh.exec_sudo_cmd("mkdir -p {}/backups".format(mount_pt))

            cp_cmd = "cp {} {} {}/backups/".format(backup_files[0].strip(), backup_files[1].strip(), mount_pt)
            con_ssh.exec_sudo_cmd(cp_cmd,expect_timeout=HostTimeout.BACKUP_COPY_USB)

            LOG.info("Verifying if backup files are copied to destination")
            rc, output = con_ssh.exec_cmd("ls {}/backups/{}*.tgz".format(mount_pt, backup_file_name ))
            if rc != 0:
                err_msg = "Failed to copy system backup files {} to USB: {}".format(backup_files, output)
                LOG.info(err_msg)
                if fail_ok:
                    return 2, err_msg
                else:
                    raise exceptions.BackupSystem(err_msg)
            LOG.info("The system backup files {} are copied to USB successfully".format(output))
        else:
            err_msg = "USB {} does not have mount point; cannot copy  backup files {} to USB"\
                .format(copy_to_usb, backup_files)
            LOG.info(err_msg)
            if fail_ok:
                return 2, err_msg
            else:
                raise exceptions.BackupSystem(err_msg)

    if delete_backup_file:
        LOG.info("Deleting system and image tgz file from tis server /opt/backups folder ")
        con_ssh.exec_sudo_cmd("rm -f /opt/backups/{}*.tgz".format(backup_file_name))

    LOG.info("Backup completed successfully")
    return 0, None


def export_image(image_id, backup_dest='usb', backup_dest_path=BackupRestore.USB_BACKUP_PATH, dest_server=None,
                 copy_to_usb=None,  delete_backup_file=True, con_ssh=None, fail_ok=False):
    """
    Exports image for backup/restore and copies the image backup file  to USB flash drive if present. T
    he generated image file is deleted from /opt/backups to save disk space after transferring the file to USB.
    Args:
        image_id (str): the image id to be backuped up.
        backup_dest(str): usb or local - the destination of backup files; choices are usb or local (test server)
        backup_dest_path(str): is the path at destination where the backup files are saved. The defaults are:
            /media/wrsroot/backups for backup_dest=usb and /sandbox/backups for backup_dest=local.
        copy_to_usb(str): usb device to copy the backups. if specified, the backup_dest_path is compared with the usb
        mount point. This is applicable when usb is specified for backup_dest.   Default is None
        delete_backup_file(bool): if set, deletes the image backup file from /opt/backups after transferring the file
        to USB.
        con_ssh:
        fail_ok:

    Returns(tuple):
        0 - Success
        2 - Image backup file generated, but fail to transfer to USB


    """
    if backup_dest == 'usb' and backup_dest_path != BackupRestore.USB_BACKUP_PATH:
        raise ValueError("If backup file destination is usb then the path must be {}".
                         format(BackupRestore.USB_BACKUP_PATH))
    if backup_dest != 'usb' and backup_dest != "local":
        raise ValueError("Invalid destination {} specified; Valid options are 'usb' and 'local'".format(backup_dest))

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    lab = InstallVars.get_install_var("LAB")

    if not image_id:
        raise ValueError("Image Id must be provided")

    img_backup_cmd = 'image-backup export ' + image_id
    # temp sleep wait for image-backup to complete
    con_ssh.exec_sudo_cmd(img_backup_cmd, expect_timeout=300)
    src_file = "/opt/backups/image_{}*.tgz".format(image_id)
    if backup_dest == 'local':
        if dest_server:
            if dest_server.ssh_conn.exec_cmd("test -e {}".format(backup_dest_path))[0] != 0:
                dest_server.ssh_conn.exec_cmd("mkdir -p {}".format(backup_dest_path))
        else:
            if local_host.exec_cmd(["test", '-e',  "{}".format(backup_dest_path)])[0] != 0:
                local_host.exec_cmd("mkdir -p {}".format(backup_dest_path))

        common.scp_from_active_controller_to_test_server(src_file, backup_dest_path, is_dir=False, multi_files=True)

        LOG.info("Verifying if image backup files are copied to destination")
        base_name_src = os.path.basename(src_file)
        if dest_server:
            rc, output = dest_server.ssh_conn.exec_cmd("ls {}/{}".format(backup_dest_path, base_name_src))
        else:
            rc, output = local_host.exec_cmd("ls {}/{}".format(backup_dest_path, base_name_src))

        if rc != 0:
            err_msg = "Failed to scp image backup files {} to local destination: {}".format(src_file, output)
            LOG.info(err_msg)
            if fail_ok:
                return 2, err_msg
            else:
                raise exceptions.BackupSystem(err_msg)

        LOG.info("The image backup files {} are copied to local destination successfully".format(output))
    else:
        # copy to usb
        if copy_to_usb is None:
            raise ValueError("USB device name must be provided, if destination is USB")

        LOG.tc_step("Transfer image tgz file to usb flash drive" )
        result = mount_usb(copy_to_usb)
        mount_pt = get_usb_mount_point(usb_device=copy_to_usb)
        if mount_pt:
            if mount_pt not in backup_dest_path:
                raise ValueError("If USB is specified as destination, the destination path must be {}"
                                 .format(BackupRestore.USB_BACKUP_PATH))

            LOG.info("USB is plugged and is mounted to {}".format(mount_pt))
            if con_ssh.exec_cmd("test -e {}/backups".format(mount_pt))[0] != 0:
                con_ssh.exec_sudo_cmd("mkdir -p {}/backups".format(mount_pt))

            cp_cmd = "cp /opt/backups/image_{}*.tgz {}/backups/".format(image_id, mount_pt)
            con_ssh.exec_sudo_cmd(cp_cmd)
            LOG.info("Verifying if image files are copied to USB")
            if con_ssh.exec_cmd("test -e {}/backups/image_{}*.tgz".format(mount_pt, image_id ))[0] != 0:
                err_msg = "Failed to copy image file image_{}.tgz to USB".format(image_id)
                LOG.info(err_msg)
                if fail_ok:
                    return 2, err_msg
                else:
                    raise exceptions.CommonError(err_msg)
        else:
            err_msg = "USB {} does not have mount point; cannot copy  backup files {} to USB"\
                .format(copy_to_usb, src_file)
            LOG.info(err_msg)
            if fail_ok:
                return 2, err_msg
            else:
                raise exceptions.BackupSystem(err_msg)

    if delete_backup_file:
        LOG.info("delete image tgz file from tis server /opt/backups folder ")
        con_ssh.exec_sudo_cmd("rm -f /opt/backups/image_{}*.tgz".format(image_id))

    LOG.info("Image export completed successfully")
    return 0, None


def set_network_boot_feed(bld_server_conn, load_path):
    """
    Sets the network feed for controller-0 in default taxlab
    Args:
        bld_server_conn:
        load_path:

    Returns:

    """


    if load_path is None:
        load_path = BuildServerPath.DEFAULT_HOST_BUILD_PATH

    if bld_server_conn is None:
        raise ValueError("Build server connection must be provided")

    if load_path[-1:] == '/':
        load_path = load_path[:-1]

    tis_bld_dir = os.path.basename(load_path)
    if tis_bld_dir == 'latest_build':
        cmd = "readlink " + load_path
        load_path = bld_server_conn.exec_cmd(cmd)[1]

    LOG.info("Load path is {}".format(load_path))
    cmd = "test -d " + load_path
    if bld_server_conn.exec_cmd(cmd)[0] != 0:
        msg = "Load path {} not found".format(load_path)
        LOG.error(msg)
        return False

    lab = InstallVars.get_install_var("LAB")

    tuxlab_server = InstallVars.get_install_var("BOOT_SERVER")
    controller0 = lab["controller-0"]
    LOG.info("Set feed for {} network boot".format(controller0.barcode))
    tuxlab_sub_dir = SvcCgcsAuto.USER + '/' + os.path.basename(load_path)
    tuxlab_prompt = '{}@{}\:(.*)\$ '.format(SvcCgcsAuto.USER, tuxlab_server)

    tuxlab_conn = establish_ssh_connection(tuxlab_server, user=SvcCgcsAuto.USER, password=SvcCgcsAuto.PASSWORD,
                                           initial_prompt=tuxlab_prompt)
    tuxlab_conn.deploy_ssh_key()

    tuxlab_barcode_dir = TUXLAB_BARCODES_DIR + str(controller0.barcode)

    if tuxlab_conn.exec_cmd("cd " + tuxlab_barcode_dir)[0] != 0:
        msg = "Failed to cd to: " + tuxlab_barcode_dir
        LOG.error(msg)
        return False

    LOG.info("Copy load into feed directory")
    feed_path = tuxlab_barcode_dir + "/" + tuxlab_sub_dir
    tuxlab_conn.exec_cmd("mkdir -p " + tuxlab_sub_dir)
    tuxlab_conn.exec_cmd("chmod 755 " + tuxlab_sub_dir)

    LOG.info("Installing Centos load to feed path: {}".format(feed_path))
    bld_server_conn.exec_cmd("cd " + load_path)
    pre_opts = 'sshpass -p "{0}"'.format(SvcCgcsAuto.PASSWORD)
    bld_server_conn.rsync(CENTOS_INSTALL_REL_PATH + "/", tuxlab_server, feed_path, dest_user=SvcCgcsAuto.USER,
                          dest_password=SvcCgcsAuto.PASSWORD, extra_opts=["--delete", "--force"], pre_opts=pre_opts)
    bld_server_conn.rsync("export/extra_cfgs/yow*", tuxlab_server, feed_path, dest_user=SvcCgcsAuto.USER,
                          dest_password=SvcCgcsAuto.PASSWORD, pre_opts=pre_opts )
    #extra_opts=["--delete", "--force"]
    LOG.info("Create new symlink to feed directory")
    if tuxlab_conn.exec_cmd("rm -f feed")[0] != 0:
        msg = "Failed to remove feed"
        LOG.error(msg)
        return False

    if tuxlab_conn.exec_cmd("ln -s " + tuxlab_sub_dir + "/" + " feed")[0] != 0:
        msg = "Failed to set VLM target {} feed symlink to: " + tuxlab_sub_dir
        LOG.error(msg)
        return False

    tuxlab_conn.close()

    return True


def boot_controller( bld_server_conn=None, patch_dir_paths=None, boot_usb=False, lowlat=False, small_footprint=False,
                     clone_install=False, system_restore=False):
    """
    Boots controller-0 either from tuxlab or USB.
    Args:
        bld_server_conn:
        load_path:
        patch_dir_paths:
        boot_usb:
        cpe:
        lowlat:

    Returns:

    """

    lab = InstallVars.get_install_var("LAB")

    controller0 = lab["controller-0"]
    install_output_dir = ProjVar.get_var("LOG_DIR")

    if controller0.telnet_conn is None:
        controller0.telnet_conn = open_telnet_session(controller0, install_output_dir)

    boot_interfaces = lab['boot_device_dict']

    LOG.info("Opening a vlm console for {}.....".format(controller0.name))
    rc, output = local_host.reserve_vlm_console(controller0.barcode)
    if rc != 0:
        err_msg = "Failed to reserve vlm console for {}  barcode {}: {}"\
            .format(controller0.name, controller0.barcode, output)
        LOG.error(err_msg)
        raise exceptions.InvalidStructure(err_msg)

    bring_node_console_up(controller0, boot_interfaces, install_output_dir, boot_usb=boot_usb, vlm_power_on=True,
                           close_telnet_conn=False, small_footprint=small_footprint, clone_install=clone_install)

    LOG.info("Initial login and password set for " + controller0.name)
    reset = True
    if clone_install:
        reset = False

    controller0.telnet_conn.login(reset=reset)

    time.sleep(60)

    if not system_restore and (patch_dir_paths and bld_server_conn):
        apply_patches(lab, bld_server_conn, patch_dir_paths)
        controller0.telnet_conn.write_line("echo " + HostLinuxCreds.get_password() + " | sudo -S reboot")
        LOG.info("Patch application requires a reboot.")
        LOG.info("Controller0 reboot has started")

        controller0.telnet_conn.get_read_until(Prompt.LOGIN_PROMPT, HostTimeout.REBOOT)
        # Reconnect telnet session
        LOG.info("Found login prompt. Controller0 reboot has completed")
        controller0.telnet_conn.login()

        # controller0.ssh_conn.disconnect()
        # controller0.ssh_conn = establish_ssh_connection(controller0, install_output_dir)


def apply_patches(lab, build_server, patch_dir):
    """

    Args:
        lab:
        server:
        patch_dir:

    Returns:

    """
    patch_names = []
    # rc = build_server.ssh_conn.exec_cmd("test -d " + patch_dir)[0]
    rc = build_server.exec_cmd("test -d " + patch_dir)[0]
    assert rc == 0, "Patch directory path {} not found".format(patch_dir)

    # rc, output = build_server.ssh_conn.exec_cmd("ls -1 --color=none {}/*.patch".format(patch_dir))
    rc, output = build_server.exec_cmd("ls -1 --color=none {}/*.patch".format(patch_dir))
    assert rc == 0, "Failed to list patch files in directory path {}.".format(patch_dir)

    # LOG.info("No path found in {} ".format(patch_dir))

    if output is not None:
        for item in output.splitlines():
            # Remove ".patch" extension
            patch_name = os.path.splitext(item)[0]
            LOG.info("Found patch named: " + patch_name)
            patch_names.append(patch_name)

        patch_dest_dir = WRSROOT_HOME + "upgrade_patches/"

        pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.get_password())
        # build_server.ssh_conn.rsync(patch_dir + "/*.patch", lab['controller-0 ip'], patch_dest_dir, pre_opts=pre_opts)
        build_server.rsync(patch_dir + "/*.patch", lab['controller-0 ip'], patch_dest_dir, pre_opts=pre_opts)

        avail_patches = " ".join(patch_names)
        LOG.info("List of patches:\n {}".format(avail_patches))

        LOG.info("Uploading  patches ... ")
        assert patching_helper.run_patch_cmd("upload-dir", args=patch_dest_dir)[0] == 0, \
            "Failed to upload  patches : {}".format(avail_patches)

        LOG.info("Querying patches ... ")
        assert patching_helper.run_patch_cmd("query")[0] == 0, "Failed to query patches"

        LOG.info("Applying patches ... ")
        rc = patching_helper.run_patch_cmd("apply", args='--all')[0]
        assert rc == 0, "Failed to apply patches"

        LOG.info("Querying patches ... ")
        assert patching_helper.run_patch_cmd("query")[0] == 0, "Failed to query patches"


def establish_ssh_connection(host, user=HostLinuxCreds.get_user(), password=HostLinuxCreds.get_password(),
                             initial_prompt=Prompt.CONTROLLER_PROMPT, retry=False, fail_ok=False):

    try:
        _ssh_conn = SSHClient(host, user=user, password=password, initial_prompt=initial_prompt)
        _ssh_conn.connect(retry=retry)
        return _ssh_conn

    except Exception as e:
        LOG.error("Fail to establish ssh connection with {}: {}".format(host, str(e) ))
        if fail_ok:
            return None
        else:
            raise


def wipedisk_via_helper(ssh_con):
    """
    A light-weight tool to wipe disks in order to AVOID booting from hard disks

    Args:
        ssh_con:

    Returns:

    """
    cmd = "test -f wipedisk_helper && test -f wipedisk_automater"
    if ssh_con.exec_cmd(cmd)[0] == 0:
        cmd = "chmod 755 wipedisk_helper"
        ssh_con.exec_cmd(cmd)

        cmd = "chmod 755 wipedisk_automater"
        ssh_con.exec_cmd(cmd)

        cmd = "./wipedisk_automater"
        ssh_con.exec_cmd(cmd)

    else:
        LOG.info("wipedisk_via_helper files are not on the load, will not do wipedisk_via_helper")


def update_auth_url(ssh_con, region=None, fail_ok=True):
    """

    Args:
        ssh_con:
        region:

    Returns:

    CGTS-8190
    """

    LOG.info('Attempt to update OS_AUTH_URL from openrc')

    CliAuth.set_vars(**setups.get_auth_via_openrc(ssh_con))
    Tenant.set_url(CliAuth.get_var('OS_AUTH_URL'))
    Tenant.set_region(CliAuth.get_var('OS_REGION_NAME'))


def get_lab_info(barcode):
    global lab_ini_info

    if lab_ini_info and barcode in lab_ini_info:
        return lab_ini_info[barcode]

    ini_file_dir = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, 'sanityrefresh/labinstall/node_info')

    ini_file = os.path.join(os.path.realpath(ini_file_dir), '{}.ini'.format(barcode))
    LOG.debug('ini file:{}, barcode:{}'.format(ini_file, barcode))

    conf_parser = configparser.ConfigParser()
    conf_parser.read(ini_file)

    settings = dict(conf_parser.defaults())
    for ss in conf_parser.sections():
        settings.update(dict(conf_parser[ss]))

    LOG.debug('settings in ini file:{}'.format(settings))

    lab_ini_info[barcode] = settings

    return settings


def run_cpe_compute_config_complete(controller0_node, controller0):
    output_dir = ProjVar.get_var('LOG_DIR')

    controller0_node.telnet_conn.exec_cmd("cd; source /etc/nova/openrc")

    if controller0_node.telnet_conn is None:
        controller0_node.telnet_conn = open_telnet_session(controller0_node, output_dir)
        controller0_node.telnet_conn.login()

    telnet_client = controller0_node.telnet_conn

    cmd = 'system compute-config-complete'
    LOG.info('To run CLI:{}'.format(cmd))

    LOG.info('execute CLI:{}'.format(cmd))
    rc, output = telnet_client.exec_cmd(cmd)
    if rc != 0:
        msg = '{} failed, rc:{}\noutput:\n{}'.format(cmd, rc, output)
        LOG.error(msg)
        raise exceptions.RestoreSystem

    LOG.info('wait controller reboot after CLI:{}'.format(cmd))
    time.sleep(30)
    for count in range(50):
        try:
            hosts = host_helper.get_hosts()
            if hosts:
                LOG.debug('hosts:{}'.format(hosts))
        except:
            break

        time.sleep(10)

    LOG.info('SSH connectiong is down, wait 120 seconds and reconnect with telnet')
    time.sleep(120)

    LOG.info('re-login')
    controller0_node.telnet_conn.login()
    os.environ["TERM"] = "xterm"

    for _ in range(40):
        try:
            controller0_node.telnet_conn.exec_cmd('source /etc/nova/openrc')
            if rc == 0:
                rc, output = controller0_node.telnet_conn.exec_cmd('system host-show {}'.format(controller0))
                if rc == 0 and output.strip():
                    LOG.info('System is ready, {} status: {}'.format(controller0, output))
                    break
        except exceptions.TelnetException as e:
            LOG.warn('got error:{}'.format(e))

        LOG.info('{} is not ready yet, failed to source /etc/nova/openrc, continue to wait'.format(controller0))
        time.sleep(15)

    LOG.info('closing the telnet connnection to node:{}'.format(controller0))
    controller0_node.telnet_conn.close()

    LOG.info('waiting for node:{} to be ready'.format(controller0))
    host_helper.wait_for_hosts_ready(controller0)
    LOG.info('OK, {} is up and ready'.format(controller0))


def create_cloned_image(cloned_image_file_prefix=PREFIX_CLONED_IMAGE_FILE, lab_system_name=None,
                  timeout=HostTimeout.SYSTEM_BACKUP, usb_device=None, delete_cloned_image_file=True,
                  con_ssh=None, fail_ok=False):
    """
    Creates system cloned image for AIO systems and copy the iso image to to USB.
    Args:
        cloned_image_file_prefix(str): The prefix to the generated system cloned image iso file. The default is "titanium_backup_"
        lab_system_name(str): is the lab system name
        timeout(inst): is the timeout value the system clone is expected to finish.
        usb_device(str): usb device name, if specified,the cloned image iso file is copied to.
        delete_cloned_image_file(bool): if USB is available, the cloned image iso file is deleted from system to save disk space.
         Default is enabled
        con_ssh:
        fail_ok:

    Returns(tuple): rc, error message
        0 - Success
        1 - Fail to create system cloned image iso file
        2 - Creating cloneed image file succeeded, but the iso file is not found in /opt/backups folder
        3 - Creating cloned image file succeeded, but failed to copy the iso file to USB


    """

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()
    lab = InstallVars.get_install_var("LAB")
    if lab_system_name is None:
        lab_system_name = lab['name']

    # execute backup command
    LOG.info("Create cloned image iso file under /opt/backups")

    date = time.strftime(BACKUP_FILE_DATE_STR)

    cloned_image_file_name = "{}_{}".format(cloned_image_file_prefix, date)
    cmd = 'config_controller --clone-iso {}'.format(cloned_image_file_name)

    # max wait 1800 seconds for config controller backup to finish
    rc, output = con_ssh.exec_sudo_cmd(cmd, expect_timeout=timeout)
    if rc != 0 or (output and "Cloning complete" not in output):
        err_msg = "Command {} failed execution: {}".format(output)
        LOG.info(err_msg)
        if fail_ok:
            return 1, err_msg
        else:
            raise exceptions.BackupSystem(err_msg)

    # verify the actual backup file are created
    rc, output = con_ssh.exec_cmd("\ls /opt/backups/{}.iso".format(cloned_image_file_name))
    if rc != 0:
        err_msg = "Failed to get the cloned image iso file: {}".format(output)
        LOG.info(err_msg)
        if fail_ok:
            return 2, err_msg
        else:
            raise exceptions.BackupSystem(err_msg)

    LOG.info("System cloned image iso file is created in /opt/backups folder: {} ".format(cloned_image_file_name))
    cloned_iso_path = "/opt/backups/{}.iso".format(cloned_image_file_name)

    # copy cloned image iso file to usb
    if usb_device is None:
        usb_device = get_usb_device_name(con_ssh=con_ssh)

    if usb_device:
        LOG.tc_step("Buring the system cloned image iso file to usb flash drive {}".format(usb_device))

        # Write the ISO to USB
        cmd = "echo {} | sudo -S dd if={} of=/dev/{} bs=1M oflag=direct; sync"\
            .format(HostLinuxCreds.get_password(), cloned_iso_path, usb_device)

        rc,  output = con_ssh.exec_cmd(cmd, expect_timeout=900)
        if rc != 0:
            err_msg = "Failed to copy the cloned image iso file to USB {}: {}".format(usb_device, output)
            LOG.info(err_msg)
            if fail_ok:
                return 3, err_msg
            else:
                raise exceptions.BackupSystem(err_msg)

        LOG.info(" The cloned image iso file copied to USB for restore. {}".format(output))

        if delete_cloned_image_file:
            LOG.info("Deleting system cloned image iso file from tis server /opt/backups folder ")
            con_ssh.exec_sudo_cmd("rm -f /opt/backups/{}.iso".format(cloned_image_file_name))

        LOG.info("Clone completed successfully")
    else:
        LOG.info(" No USB flash drive found. The cloned image iso file are saved in folder {}".format(cloned_iso_path))

    return 0, None


def check_clone_status( tel_net_session=None, con_ssh=None, fail_ok=False):
    """
    Checks the install-clone status after system is booted from cloned image.
    Args:
        tel_net_session:
        con_ssh:
        fail_ok:

    Returns (tuple): rc, text message
        0 - Success
        1 - Execution of clone status command failed
    """

    lab = InstallVars.get_install_var("LAB")
    output_dir = ProjVar.get_var('LOG_DIR')
    controller0_node = lab['controller-0']

    if controller0_node.telnet_conn is None:
        LOG.info("Setting up telnet connection ...")
        controller0_node.telnet_conn = open_telnet_session(controller0_node, output_dir)
        controller0_node.telnet_conn.login()
        controller0_node.telnet_conn.exec_cmd("xterm")

    cmd = 'config_controller --clone-status'.format(HostLinuxCreds.get_password())
    os.environ["TERM"] = "xterm"

    rc, output = tel_net_session.exec_sudo_cmd(cmd, timeout=HostTimeout.INSTALL_CLONE_STATUS)

    if rc == 0 and all(m in output for m in ['Installation of cloned image', 'was successful at']):
        msg = 'System was installed from cloned image successfully: {}'.format(output)
        LOG.info(msg)
        return 0, None
    else:
        err_msg = "{} execution failed: {} {}".format(cmd, rc, output)
        LOG.error(err_msg)
        if fail_ok:
            return 1, err_msg
        else:
            raise exceptions.RestoreSystem(err_msg)


def check_cloned_hardware_status(host, fail_ok=False):
    """
     Checks the hardware of the cloned controller host bye executing the following cli commands:
         system show
         system host-show <host>
         system host-ethernet-port-list <host>
         system host-if-list <host>
         system host-disk-list <host>

    Args:
        host:
        fail_ok:

    Returns:

    """
    lab = InstallVars.get_install_var("LAB")
    system_mode = 'duplex' if len(lab['controller_nodes']) > 1 else 'simplex'
    log_dir = ProjVar.get_var('LOG_DIR')
    controller_0_node = lab["controller-0"]
    node = lab[host]
    if node is None:
        err_msg = "Failed to get node object for hostname {} in the Install parameters".format(host)
        LOG.error(err_msg)
        raise exceptions.InvalidStructure(err_msg)


    if controller_0_node.telnet_conn is None:
        controller_0_node.telnet_conn = open_telnet_session(controller_0_node, log_dir)

    LOG.info("Executing system show on cloned system")
    table_ = table_parser.table(cli.system('show', use_telnet=True, con_telnet=controller_0_node.telnet_conn))
    system_name = table_parser.get_value_two_col_table(table_, 'name')
    assert "Cloned_system" in system_name, "Unexpected system name {} after install-clone".format(system_name)

    system_type = table_parser.get_value_two_col_table(table_, 'system_type')
    assert "All-in-one" in system_type, "Unexpected system type {} after install-clone".format(system_type)

    system_desc = table_parser.get_value_two_col_table(table_, 'description')
    assert "Cloned_from" in system_desc, "Unexpected system description {} after install-clone".format(system_desc)

    software_version = table_parser.get_value_two_col_table(table_, 'software_version')

    LOG.info("Executing system host show on cloned system host".format(host))
    table_ = table_parser.table(cli.system('host-show {}'.format(host), use_telnet=True,
                                           con_telnet=controller_0_node.telnet_conn))
    host_name = table_parser.get_value_two_col_table(table_, 'hostname')
    assert host == host_name, "Unexpected hostname {} after install-clone".format(host_name)
    if system_mode == 'duplex':
        host_mgmt_ip = table_parser.get_value_two_col_table(table_, 'mgmt_ip')
        assert "192.168" in host_mgmt_ip, "Unexpected mgmt_ip {} in host {} after install-clone"\
            .format(host_mgmt_ip, host)

    host_mgmt_mac = table_parser.get_value_two_col_table(table_, 'mgmt_mac')

    host_software_load = table_parser.get_value_two_col_table(table_, 'software_load')
    assert host_software_load == software_version, "Unexpected software load {} in host {} after install-clone"\
        .format(host_software_load, host)

    LOG.info("Executing system host ethernet port list on cloned system host {}".format(host))
    table_ = table_parser.table(cli.system('host-ethernet-port-list {} --nowrap'.format(host), use_telnet=True,
                                           con_telnet=controller_0_node.telnet_conn))
    assert len(table_['values']) >= 2, "Fewer ethernet ports listed than expected for host {}: {}".format(host, table_)
    if system_mode == 'duplex':
        assert len(table_parser.filter_table(table_, **{'mac address': host_mgmt_mac})['values']) >= 1, \
            "Host {} mgmt mac address {} not match".format(host, host_mgmt_mac)

    LOG.info("Executing system host interface list on cloned system host {}".format(host))
    table_ = table_parser.table(cli.system('host-if-list {} --nowrap'.format(host), use_telnet=True,
                                           con_telnet=controller_0_node.telnet_conn))
    assert len(table_parser.filter_table(table_, **{'network type':'data'})['values']) >= 1, \
        "No data interface type found in Host {} after system clone-install".format(host)
    assert len(table_parser.filter_table(table_, **{'network type':'mgmt'})['values']) >= 1, \
        "No mgmt interface type found in Host {} after system clone-install".format(host)
    assert len(table_parser.filter_table(table_, **{'network type':'oam'})['values']) >= 1, \
        "No oam interface type found in Host {} after system clone-install".format(host)

    LOG.info("Executing system host disk list on cloned system host {}".format(host))
    table_ = table_parser.table(cli.system('host-disk-list {} --nowrap'.format(host), use_telnet=True,
                                           con_telnet=controller_0_node.telnet_conn))
    assert len(table_['values']) >= 2, "Fewer disks listed than expected for host {}: {}".format(host, table_)


def update_oam_for_cloned_system( system_mode='duplex', fail_ok=False):

    lab = InstallVars.get_install_var("LAB")
    output_dir = ProjVar.get_var('LOG_DIR')
    controller0_node = lab['controller-0']

    if controller0_node.telnet_conn is None:
        controller0_node.telnet_conn = open_telnet_session(controller0_node, output_dir)
        controller0_node.telnet_conn.login()

    host = 'controller-1' if system_mode == 'duplex' else 'controller-0'
    LOG.info("Locking {} for  oam IP configuration update".format(host))
    host_helper.lock_host(host, use_telnet=True, con_telnet=controller0_node.telnet_conn)

    cmd = "oam-modify oam_gateway_ip=128.224.150.1 oam_subnet=128.224.150.0/23"
    if host == 'controller-1':
        cmd += " oam_c0_ip={}".format(controller0_node.host_ip)
        cmd += " oam_c1_ip={}".format(lab['controller-1'].host_ip)
        cmd += " oam_floating_ip={}".format(controller0_node.host_floating_ip)
    else:
        cmd += " oam_ip={}".format(controller0_node.host_ip)

    LOG.info("Modifying oam IP configuration: {}".format(cmd))
    rc, output = cli.system(cmd, use_telnet=True, con_telnet=controller0_node.telnet_conn, fail_ok=True)
    if rc != 0:
        err_msg = "{} execution failed: rc = {}; {}".format(cmd, rc, output)
        LOG.error(err_msg)
        if fail_ok:
            return 1, err_msg
        else:
            raise exceptions.RestoreSystem(err_msg)

    LOG.info("The oam IP configuration modified successfully: {}".format(output))
    LOG.info("Unlocking {} after  oam IP configuration update".format(host))
    host_helper.unlock_host(host, use_telnet=True, con_telnet=controller0_node.telnet_conn)

    LOG.info("Unlocked {} successfully after oam IP configuration update".format(host))

    if system_mode == 'duplex':
        LOG.info("Swacting to controller-0 for oam IP configuration update")

        host_helper.swact_host(controller0_node.name, use_telnet=True, con_telnet=controller0_node.telnet_conn)

        controller_prompt = Prompt.CONTROLLER_1 + '|' + Prompt.ADMIN_PROMPT

        ssh_conn = establish_ssh_connection(lab['controller-1'].host_ip, initial_prompt=controller_prompt)
        ssh_conn.deploy_ssh_key()
        ControllerClient.set_active_controller(ssh_conn)

        LOG.info(" The controller is successfully swacted.")

        LOG.info(" Locking controller-0 for oam ip config update.")
        host_helper.lock_host("controller-0", con_ssh=ssh_conn)

        LOG.info(" Unlocking controller-0 for oam ip config update.")
        host_helper.unlock_host("controller-0", con_ssh=ssh_conn, available_only=True)

        LOG.info(" Unlocked controller-0 successfully.")

        LOG.info(" Swacting back to controller-0 ...")

        # re-establish ssh connection
        ssh_conn.close()
        controller_prompt = Prompt.CONTROLLER_PROMPT + '|' + Prompt.ADMIN_PROMPT
        ssh_conn = establish_ssh_connection(controller0_node.host_floating_ip,
                                                        initial_prompt=controller_prompt)
        ssh_conn.deploy_ssh_key()
        ControllerClient.set_active_controller(ssh_client=ssh_conn)

        host_helper.swact_host('controller-1')

        LOG.info(" Swacted back to controller-0  successfully ...")

    else:
        controller_prompt = Prompt.CONTROLLER_0 + '|' + Prompt.ADMIN_PROMPT
        if controller0_node.ssh_conn:
            controller0_node.ssh_conn.close()

        ssh_conn = establish_ssh_connection(controller0_node.host_ip, initial_prompt=controller_prompt)
        ssh_conn.deploy_ssh_key()
        ControllerClient.set_active_controller(ssh_conn)


def update_system_info_for_cloned_system( system_mode='duplex', fail_ok=False):

    lab = InstallVars.get_install_var("LAB")

    system_info = {
        'description': None,
        'name': lab['name'],
    }

    system_helper.set_system_info(**system_info)
