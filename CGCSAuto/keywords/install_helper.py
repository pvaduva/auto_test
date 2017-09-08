import os
import telnetlib
import threading
import time
from contextlib import contextmanager

from consts.auth import HostLinuxCreds, SvcCgcsAuto, Tenant
from consts.build_server import DEFAULT_BUILD_SERVER, BUILD_SERVERS
from consts.timeout import HostTimeout
from consts.cgcs import HostAvailabilityState, Prompt
from consts.filepaths import WRSROOT_HOME, TiSPath, BuildServerPath
from consts.proj_vars import InstallVars, ProjVar
from consts.vlm import VlmAction
from keywords import system_helper, host_helper, vm_helper
# from keywords.vlm_helper import bring_node_console_up
from utils import exceptions, local_host
from utils import local_host, cli
from utils import telnet as telnetlib
from utils.ssh import SSHClient, ControllerClient
from utils.tis_log import LOG


UPGRADE_LOAD_ISO_FILE = "bootimage.iso"


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

    pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.PASSWORD)
    server.ssh_conn.rsync("-L " + license_path, lab['controller-0 ip'],
                          os.path.join(WRSROOT_HOME, "upgrade_license.lic"),
                          pre_opts=pre_opts)


def download_upgrade_load(lab, server, load_path):

    # Download licens efile
    cmd = "test -e " + load_path
    assert server.ssh_conn.exec_cmd(cmd, rm_date=False)[0] == 0,  'Upgrade build iso file not found in {}:{}'.format(
            server.name, load_path)
    iso_file_path = os.path.join(load_path, "export", UPGRADE_LOAD_ISO_FILE)
    pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.PASSWORD)
    #server.ssh_conn.rsync(iso_file_path,
    #                      lab['controller-0 ip'],
    #                      WRSROOT_HOME, pre_opts=pre_opts)
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


def open_vlm_console_thread(hostname, boot_interface=None):

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
                                   args=(node, boot_device, output_dir))

    LOG.info("Starting thread for {}".format(node_thread.name))
    node_thread.start()


def bring_node_console_up(node, boot_device, install_output_dir, close_telnet_conn=True):
    """
    Initiate the boot and installation operation.
    Args:
        node:
        boot_device:
        install_output_dir:
        close_telnet_conn:

    Returns:
    """

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

    node.telnet_conn.install(node, boot_device, upgrade=True)
    if close_telnet_conn:
        node.telnet_conn.close()


def get_non_controller_system_hosts():

    hosts = system_helper.get_hostnames()
    controllers = sorted([h for h in hosts if "controller" in h])
    storages = sorted([h for h in hosts if "storage" in h])
    computes = sorted([h for h in hosts if h not in storages and h not in controllers])
    return storages + computes


def wipe_disk_hosts(hosts):

    lab = InstallVars.get_install_var("LAB")
    output_dir = ProjVar.get_var('LOG_DIR')

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
    Perform a wipedisk operation on the lab before booting a new load into
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

    # Check that the node is accessible for wipedisk to run.
    # If we cannot successfully ping the interface of the node, then it is
    # expected that the login will fail. This may be due to the node not
    # being left in an installed state.
    cmd = "ping -w {} -c 4 {}".format(HostTimeout.PING_TIMEOUT, node.host_ip)
    if (node.telnet_conn.exec_cmd(cmd, timeout=HostTimeout.PING_TIMEOUT +
                                  HostTimeout.TIMEOUT_BUFFER)[0] != 0):
        err_msg = "Node {} not responding. Skipping wipedisk process".format(node.name)
        LOG.info(err_msg)
        return 1
    else:
        node.telnet_conn.login()

    node.telnet_conn.write_line("sudo -k wipedisk")
    node.telnet_conn.get_read_until(Prompt.PASSWORD_PROMPT)
    node.telnet_conn.write_line(HostLinuxCreds.PASSWORD)
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
    pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.PASSWORD)
    server.ssh_conn.rsync(guest_path,
                          lab['controller-0 ip'],
                          TiSPath.IMAGES, pre_opts=pre_opts)


def download_heat_templates(lab, server, load_path):

    heat_path = load_path  + BuildServerPath.HEAT_TEMPLATES

    cmd = "test -e " + heat_path
    assert server.ssh_conn.exec_cmd(cmd, rm_date=False)[0] == 0,  'Heat template path not found in {}:{}'.format(
            server.name, load_path)

    pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.PASSWORD)
    server.ssh_conn.rsync(heat_path + "/*",
                          lab['controller-0 ip'],
                          TiSPath.HEAT, pre_opts=pre_opts)


def download_lab_config_files(lab, server, load_path):

    lab_name = lab['name']
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

    pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.PASSWORD)
    server.ssh_conn.rsync(config_path + "/*",
                          lab['controller-0 ip'],
                          WRSROOT_HOME, pre_opts=pre_opts)

    server.ssh_conn.rsync(script_path + "/*",
                          lab['controller-0 ip'],
                          WRSROOT_HOME, pre_opts=pre_opts)


def download_lab_config_file(lab, server, load_path, config_file='lab_setup.conf'):

    lab_name = lab['name']
    if "yow" in lab_name:
        lab_name = lab_name[4:]

    config_path = "{}{}/yow/{}/{}".format(load_path, BuildServerPath.CONFIG_LAB_REL_PATH , lab_name, config_file)

    cmd = "test -e " + config_path
    assert server.ssh_conn.exec_cmd(cmd, rm_date=False)[0] == 0, ' lab config path not found in {}:{}'.format(
            server.name, config_path)

    pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.PASSWORD)
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
        cmd = "test -e {}/{}.conf".format( WRSROOT_HOME, script)
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
