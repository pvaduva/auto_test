import configparser
import os
import re
import threading
import time

import setups
from consts.auth import HostLinuxCreds, SvcCgcsAuto
from consts.auth import Tenant, CliAuth
# from consts.build_server import DEFAULT_BUILD_SERVER, BUILD_SERVERS
from consts.cgcs import HostAvailState, HostAdminState, Prompt, PREFIX_BACKUP_FILE, TITANIUM_BACKUP_FILE_PATTERN,\
    IMAGE_BACKUP_FILE_PATTERN, CINDER_VOLUME_BACKUP_FILE_PATTERN, BACKUP_FILE_DATE_STR, BackupRestore, \
    PREFIX_CLONED_IMAGE_FILE, PLATFORM_CONF_PATH
from consts.filepaths import WRSROOT_HOME, TiSPath, BuildServerPath, LogPath
from consts.proj_vars import InstallVars, ProjVar, RestoreVars
from consts.timeout import HostTimeout, ImageTimeout, InstallTimeout
from consts.vlm import VlmAction
from consts.bios import NODES_WITH_KERNEL_BOOT_OPTION_SPACING
from consts.build_server import Server
from keywords import system_helper, host_helper, vm_helper, patching_helper, cinder_helper, common, network_helper, \
    vlm_helper
from utils import telnet as telnetlib, exceptions, cli, table_parser, lab_info, multi_thread, menu
from utils.clients.ssh import SSHClient, ControllerClient
from utils.clients.telnet import TelnetClient, LOGIN_REGEX
from utils.clients.local import LocalHostClient
from utils.node import create_node_boot_dict, create_node_dict, Node
from utils.tis_log import LOG


UPGRADE_LOAD_ISO_FILE = "bootimage.iso"
UPGRADE_LOAD_SIG_FILE = "bootimage.sig"
BACKUP_USB_MOUNT_POINT = '/media/wrsroot'
TUXLAB_BARCODES_DIR = "/export/pxeboot/vlm-boards/"
CENTOS_INSTALL_REL_PATH = "export/dist/isolinux/"

outputs_restore_system_conf = ("Enter 'reboot' to reboot controller: ", "compute-config in progress ...")

lab_ini_info = {}
__local_client = None


def local_client():
    global __local_client
    if not __local_client:
        __local_client = LocalHostClient(connect=True)

    return __local_client


def get_ssh_public_key():
    return local_client().get_ssh_key()


def get_current_system_version():
    return system_helper.get_system_software_version(use_existing=False)


def check_system_health_for_upgrade():
    # system_helper.source_admin()
    return system_helper.get_system_health_query_upgrade()


def download_upgrade_license(lab, server, license_path):

    cmd = "test -h " + license_path
    assert server.ssh_conn.exec_cmd(cmd)[0] == 0,  'Upgrade license file not found in {}:{}'.format(
            server.name, license_path)
    pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.get_password())

    if 'vbox' in lab['name']:
        if 'external_ip' in lab.keys():
            external_ip = lab['external_ip']
            external_port = lab['external_port']
            server.ssh_conn.rsync("-L " + license_path, external_ip,
                                  os.path.join(WRSROOT_HOME, "upgrade_license.lic"),
                                  pre_opts=pre_opts, ssh_port=external_port)
        else:
            temp_path = '/tmp'
            local_pre_opts = 'sshpass -p "{0}"'.format(lab['local_password'])
            local_ip = lab['local_ip']

            server.ssh_conn.rsync("-L " + license_path, local_ip,
                                  os.path.join(temp_path, "upgrade_license.lic"),
                                  dest_user=lab['local_user'], dest_password=lab['local_password'],
                                  pre_opts=local_pre_opts)

            common.scp_from_localhost_to_active_controller(source_path=os.path.join(temp_path, "upgrade_license.lic"),
                                                           dest_path=os.path.join(WRSROOT_HOME, "upgrade_license.lic"))

            # server.ssh_conn.rsync("-L " + license_path, external_ip,
            #                       os.path.join(temp_path, "upgrade_license.lic"),
            #                       dest_user=lab['local_user'], dest_password=lab['local_password'],
            #                       pre_opts=local_pre_opts)
            #
            # common.scp_to_active_controller(source_path=os.path.join(temp_path, "upgrade_license.lic"),
            #                                 dest_path=os.path.join(WRSROOT_HOME, "upgrade_license.lic"))
    else:
        server.ssh_conn.rsync("-L " + license_path, lab['controller-0 ip'],
                            os.path.join(WRSROOT_HOME, "upgrade_license.lic"),
                            pre_opts=pre_opts)


# TODO: to replace download_upgrade_license
def download_license(lab, server, license_path, dest_name="upgrade_license"):

    cmd = "test -h " + license_path
    assert server.ssh_conn.exec_cmd(cmd)[0] == 0,  '{} file not found in {}:{}'.format(dest_name.capitalize(),
                                                                                       server.name, license_path)
    pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.get_password())
    dest_path = os.path.join(WRSROOT_HOME, "{}.lic".format(dest_name))

    if 'vbox' in lab['name']:
        if 'external_ip' in lab.keys():
            external_ip = lab['external_ip']
            external_port = lab['external_port']
            server.ssh_conn.rsync("-L " + license_path, external_ip, dest_path,
                              pre_opts=pre_opts, ssh_port=external_port)
        else:
            temp_path = '/tmp'
            local_pre_opts = 'sshpass -p "{0}"'.format(lab['local_password'])
            local_ip = lab['local_ip']
            dest_path = os.path.join(temp_path, "{}.lic".format(dest_name))

            server.ssh_conn.rsync("-L " + license_path, local_ip, dest_path,
                                  dest_user=lab['local_user'], dest_password=lab['local_password'],
                                  pre_opts=local_pre_opts)

            common.scp_from_localhost_to_active_controller(source_path=os.path.join(temp_path, "{}.lic".format(dest_name)),
                                            dest_path=os.path.join(WRSROOT_HOME, "{}.lic".format(dest_name)))

            # server.ssh_conn.rsync("-L " + license_path, external_ip,
            #                       os.path.join(temp_path, "upgrade_license.lic"),
            #                       dest_user=lab['local_user'], dest_password=lab['local_password'],
            #                       pre_opts=local_pre_opts)
            #
            # common.scp_to_active_controller(source_path=os.path.join(temp_path, "upgrade_license.lic"),
            #                                 dest_path=os.path.join(WRSROOT_HOME, "upgrade_license.lic"))
    else:
        server.ssh_conn.rsync("-L " + license_path, lab['controller-0 ip'], dest_path, pre_opts=pre_opts)

    return dest_path


def download_upgrade_load(lab, server, load_path, upgrade_ver):

    # Download licens efile
    cmd = "test -e " + load_path
    assert server.ssh_conn.exec_cmd(cmd, rm_date=False)[0] == 0,  'Upgrade build iso file not found in {}:{}'.format(
            server.name, load_path)
    iso_file_path = os.path.join(load_path, "export", UPGRADE_LOAD_ISO_FILE)
    sig_file_path = os.path.join(load_path, "export", UPGRADE_LOAD_SIG_FILE)
    pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.get_password())

    if 'vbox' in lab['name']:

        if 'external_ip' in lab.keys():
            external_ip = lab['external_ip']
            external_port = lab['external_port']
            server.ssh_conn.rsync(iso_file_path,
                          external_ip,
                          os.path.join(WRSROOT_HOME, "bootimage.iso"), pre_opts=pre_opts, ssh_port=external_port)
        else:
            temp_path = '/tmp'
            local_ip = lab['local_ip']
            local_pre_opts = 'sshpass -p "{0}"'.format(lab['local_password'])
            server.ssh_conn.rsync(iso_file_path, local_ip,
                                  os.path.join(temp_path, "bootimage.iso"), dest_user=lab['local_user'],
                                  dest_password=lab['local_password'], pre_opts=local_pre_opts)
            common.scp_from_localhost_to_active_controller(source_path=os.path.join(temp_path, "bootimage.iso"),
                                                           dest_path=os.path.join(WRSROOT_HOME, "bootimage.iso"))

    else:
        server.ssh_conn.rsync(iso_file_path,
                              lab['controller-0 ip'],
                              os.path.join(WRSROOT_HOME, "bootimage.iso"), pre_opts=pre_opts)
        if upgrade_ver >= '17.07':
           server.ssh_conn.rsync(sig_file_path,
                               lab['controller-0 ip'],
                               os.path.join(WRSROOT_HOME, "bootimage.sig"), pre_opts=pre_opts)


def get_mgmt_boot_device(node):
    boot_device = {}
    boot_interfaces = system_helper.get_host_mgmt_pci_address(node.name)
    for boot_interface in boot_interfaces:
        a1, a2, a3 = boot_interface.split(":")
        boot_device[node.name] = a2 + "0" + a3.split(".")[1]
        if len(boot_device) is 1:
            break
    if len(boot_device) is 0:
        LOG.error("Unable to get the mgmt boot device for host {}".format(node.name))
    return boot_device


def open_vlm_console_thread(hostname, lab=None, boot_interface=None, upgrade=False, vlm_power_on=False,
                            close_telnet_conn=True, small_footprint=None, wait_for_thread=False, security=None,
                            low_latency=None, boot_usb=None):

    if lab is None:
        lab = InstallVars.get_install_var("LAB")
    node = lab[hostname]
    if node is None:
        err_msg = "Failed to get node object for hostname {} in the Install parameters".format(hostname)
        LOG.error(err_msg)
        raise exceptions.InvalidStructure(err_msg)

    boot_device = boot_interface
    if boot_interface is None:
        boot_device = {hostname: get_mgmt_boot_device(node)}

    LOG.info("Mgmt boot device for {} is {}".format(node.name, boot_device))

    LOG.info("Opening a vlm console for {}.....".format(hostname))
    rc, output = vlm_helper._reserve_vlm_console(node.barcode)
    if rc > 0:
        err_msg = "Failed to reserve vlm console for {}  barcode {}: {}"\
            .format(node.name, node.barcode, output)
        LOG.error(err_msg)
        raise exceptions.InvalidStructure(err_msg)

    node_thread = threading.Thread(target=bring_node_console_up,
                                   name=node.name,
                                   args=(node, boot_device),
                                   kwargs={'upgrade': upgrade, 'vlm_power_on': vlm_power_on, 'lab': lab,
                                           'close_telnet_conn': close_telnet_conn, 'small_footprint': small_footprint,
                                           'security': security, 'low_latency': low_latency, 'boot_usb': boot_usb})

    LOG.info("Starting thread for {}".format(node_thread.name))
    node_thread.start()
    if wait_for_thread:
        node_thread.join(InstallTimeout.INSTALL_LOAD)
        if node_thread.is_alive():
            err_msg = "Host {} failed to install within the {} seconds".format(node.name, InstallTimeout.INSTALL_LOAD)
            LOG.error(err_msg)
            raise exceptions.InvalidStructure(err_msg)

    return node_thread


def bring_node_console_up(node, boot_device,
                          boot_usb=None,
                          low_latency=None,
                          upgrade=False,
                          vlm_power_on=False,
                          close_telnet_conn=True,
                          small_footprint=None,
                          security=None,
                          lab=None,):
    """
    Initiate the boot and installation operation.

    Args:
        node:
        boot_device:
        boot_usb:
        low_latency:
        upgrade:
        vlm_power_on:
        close_telnet_conn:
        small_footprint:
        security:
        lab:

    Returns:

    """
    LOG.info("Opening node vlm console for {}; vlm_power = {}, upgrade= {}".format(node.name, vlm_power_on, upgrade))
    if len(boot_device) == 0:
        LOG.error("Cannot bring vlm console for {} without valid mgmt boot device: {}".format(node.name, boot_device))
        return 1

    if node.telnet_conn is None:
        node.telnet_conn = open_telnet_session(node)

    try:
        if vlm_power_on:
            LOG.info("Powering on {}".format(node.name))
            power_on_host(node.name, lab=lab, wait_for_hosts_state_=False)

        install_node(node, boot_device_dict=boot_device, low_latency=low_latency, small_footprint=small_footprint,
                     security=security, usb=boot_usb)
    finally:
        if close_telnet_conn:
            node.telnet_conn.close()


def get_non_controller_system_hosts():

    hosts = system_helper.get_hostnames()
    controllers = sorted([h for h in hosts if "controller" in h])
    storages = sorted([h for h in hosts if "storage" in h])
    computes = sorted([h for h in hosts if h not in storages and h not in controllers])
    return storages + computes


def open_telnet_session(node_obj):
    _telnet_conn = TelnetClient(host=node_obj.telnet_ip, port=int(node_obj.telnet_port), hostname=node_obj.name)
    # if node_obj.telnet_login_prompt:
    _telnet_conn.write(b"\r\n")
    try:
        index = _telnet_conn.expect(["Login:", LOGIN_REGEX], timeout=5)
        if index == 0:
            _telnet_conn.write(b"\r\n")
        elif index == 1:
            _telnet_conn.login()
    except exceptions.TelnetTimeout:
        pass
    except exceptions.TelnetError as e:
        if "Unable to login to {} credential {}/{}".format(node_obj.name, HostLinuxCreds.get_user(),
                                                           HostLinuxCreds.get_password()) in e.message:
            _telnet_conn.login(reset=True)

    return _telnet_conn


def wipe_disk_hosts(hosts, lab=None, close_telnet_conn=True):

    if not lab:
        lab = InstallVars.get_install_var("LAB")

    LOG.info("LAB info:  {}".format(lab))
    if len(hosts) < 1:
        err_msg = "The hosts list referred is empty: {}".format(hosts)
        LOG.info(err_msg)
        return

    if isinstance(hosts, str):
        hosts = [hosts]

    controller0_node = lab['controller-0']
    if not controller0_node:
        err_msg = "The controller-0 node object is missing: {}".format(lab)
        LOG.info(err_msg)
        return

    if controller0_node.telnet_conn is None:
        controller0_node.telnet_conn = open_telnet_session(controller0_node)
        controller0_node.telnet_conn.login()
    # Check if controller is online
    if local_client().ping_server(controller0_node.host_ip, fail_ok=True)[0] == 100:
        LOG.warning("Host controller-0 is not reachable, cannot wipedisk for hosts {}".format(hosts))
        return
    # try:
    #    controller0_node.telnet_conn.send()
    #    controller0_node.telnet_conn.expect(timeout=3)
    # except exceptions.TelnetTimeout:
    #    LOG.info("Host controller-0 is not reachable, cannot wipedisk for hosts {}".format(hosts))
    #    return

    if controller0_node.telnet_conn:
        # Run the wipedisk_via_helper utility if the nodes are accessible
        cmd = "test -f " + "/home/wrsroot/wipedisk_helper "
        if controller0_node.telnet_conn.exec_cmd(cmd, blob=controller0_node.telnet_conn.prompt, fail_ok=True)[0] == 0:
            cmd = "chmod 755 wipedisk_helper"
            controller0_node.telnet_conn.exec_cmd(cmd)
            for hostname in hosts:
                cmd = "./wipedisk_helper {}".format(hostname)
                if controller0_node.telnet_conn.exec_cmd(cmd, fail_ok=True)[0] == 0:
                    LOG.info("All disks wiped for host {}".format(hostname))
        else:
            LOG.info("wipedisk_via_helper files are not on the load, will use  wipedisk command directly")
            for hostname in hosts:
                node_obj = lab[hostname]
                if node_obj:

                    prompt = '.*{}\:~\$ ' + '|' + Prompt.TIS_NODE_PROMPT_BASE.format(node_obj.host_name)
                else:
                    prompt = Prompt.TIS_NODE_PROMPT_BASE.format(hostname)
                if hostname == controller0_node.name:
                    hostname = node_obj.host_ip

                cmd = "ping -w {} -c 4 {}".format(HostTimeout.PING_TIMEOUT, hostname)
                if (controller0_node.telnet_conn.exec_cmd(cmd, expect_timeout=HostTimeout.PING_TIMEOUT +
                                              HostTimeout.TIMEOUT_BUFFER)[0] != 0):
                    LOG.info("Node {} not responding. Skipping wipedisk process".format(hostname))

                else:
                    try:
                        with host_helper.ssh_to_remote_node(hostname, prompt=prompt, use_telnet=True,
                                                            telnet_session=controller0_node.telnet_conn) as host_ssh:
                            host_ssh.send("sudo wipedisk")
                            prompts = [Prompt.PASSWORD_PROMPT, "\[y/n\]", "wipediskscompletely"]
                            index = host_ssh.expect(prompts)

                            if index == 0:
                                host_ssh.send(HostLinuxCreds.get_password())
                                prompts.remove(Prompt.PASSWORD_PROMPT)
                                index = host_ssh.expect(prompts)

                            host_ssh.send("y")
                            index = host_ssh.expect("wipediskscompletely")
                            host_ssh.send("wipediskscompletely")
                            host_ssh.expect("The disk(s) have been wiped.")
                    except:
                        LOG.info("Unable to ssh to {}; Skipping wipedisk ..".format(hostname))
    else:
        LOG.info("Host controller-0 is not reachable, cannot wipedisk for hosts {}".format(hosts))


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

        rc, output = vlm_helper._reserve_vlm_console(node.barcode)
        if rc > 0:
            err_msg = "Failed to reserve vlm console for {}  barcode {}: {}"\
                .format(node.name, node.barcode, output)
            LOG.error(err_msg)
            raise exceptions.InvalidStructure(err_msg)

        LOG.info("node.barcode:{}".format(node.barcode))
        LOG.info("node:{}".format(node))

        rc, output = vlm_helper._vlm_exec_cmd(VlmAction.VLM_TURNOFF, node.barcode)

        if rc != 0:
            err_msg = "Failed to power off node {}  barcode {}: {}"\
                .format(node.name, node.barcode, output)
            LOG.error(err_msg)
            raise exceptions.InvalidStructure(err_msg)
        LOG.info("Node {} is turned off".format(node.name))


# TODO: To be replaced by function in vlm_helper
def power_on_host(hosts, lab=None, wait_for_hosts_state_=True):

    if isinstance(hosts, str):
        hosts = [hosts]
    if not lab:
        lab = InstallVars.get_install_var("LAB")
    for host in hosts:
        node = lab[host]
        if node is None:
            err_msg = "Failed to get node object for hostname {} in the Install parameters".format(host)
            LOG.error(err_msg)
            raise exceptions.InvalidStructure(err_msg)

        rc, output = vlm_helper._reserve_vlm_console(node.barcode)
        if rc > 0:
            err_msg = "Failed to reserve vlm console for {}  barcode {}: {}"\
                .format(node.name, node.barcode, output)
            LOG.error(err_msg)
            raise exceptions.InvalidStructure(err_msg)

        rc, output = vlm_helper._vlm_exec_cmd(VlmAction.VLM_TURNON, node.barcode)
        if rc != 0:
            err_msg = "Failed to power on node {}  barcode {}: {}"\
                .format(node.name, node.barcode, output)
            LOG.error(err_msg)
            raise exceptions.InvalidStructure(err_msg)
        LOG.info("Node {} is turned on".format(node.name))

    if wait_for_hosts_state_:
        wait_for_hosts_state(hosts)


# TODO: To be replaced by function in vlm_helper
def wait_for_hosts_state(hosts, state=HostAvailState.ONLINE):

    if len(hosts) > 0:
        locked_hosts_in_states = host_helper.wait_for_hosts_states(hosts, availability=[state])
        LOG.info("Host(s) {} are online".format(locked_hosts_in_states))


def lock_hosts(hosts):
    if isinstance(hosts, str):
        hosts = [hosts]
    for host in hosts:
        host_helper.lock_host(host)


def download_image(lab, server, guest_path):

    cmd = "test -e " + guest_path
    assert server.ssh_conn.exec_cmd(cmd, rm_date=False)[0] == 0,  'Image file not found in {}:{}'.format(
            server.name, guest_path)
    pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.get_password())

    if 'vbox' in lab['name']:
        if 'external_ip' in lab.keys():
            external_ip = lab['external_ip']
            external_port = lab['external_port']
            server.ssh_conn.rsync(guest_path, external_ip, TiSPath.IMAGES, pre_opts=pre_opts, ssh_port=external_port)
        else:
            temp_path = '/tmp'
            image_file = os.path.basename(guest_path)
            local_ip = lab['local_ip']
            local_pre_opts = 'sshpass -p "{0}"'.format(lab['local_password'])
            server.ssh_conn.rsync(guest_path, local_ip, os.path.join(temp_path, image_file),
                              dest_user=lab['local_user'],
                              dest_password=lab['local_password'], pre_opts=local_pre_opts, timeout=ImageTimeout.CREATE)

            common.scp_from_localhost_to_active_controller(source_path=os.path.join(temp_path, image_file),
                                                           dest_path=TiSPath.IMAGES)
    else:
        server.ssh_conn.rsync(guest_path,
                              lab['controller-0 ip'],
                              TiSPath.IMAGES, pre_opts=pre_opts, timeout=ImageTimeout.CREATE)


def download_heat_templates(lab, server, load_path, heat_path=None):

    if 'vbox' in lab['name']:
        LOG.info("Skip download heat files for vbox")
        return

    if not heat_path:
        sys_version = extract_software_version_from_string_path(load_path)
        sys_version = sys_version if sys_version in BuildServerPath.HEAT_TEMPLATES_EXTS else 'default'
        heat_path = os.path.join(load_path, BuildServerPath.HEAT_TEMPLATES_EXTS[sys_version])
    else:
        heat_path = heat_path

    cmd = "test -e " + heat_path
    if server.ssh_conn.exec_cmd(cmd, rm_date=False)[0] != 0:
        LOG.warning('heat template path does not exist: {}. Skip download heat files.'.format(heat_path))
        return

    pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.get_password())
    server.ssh_conn.rsync(heat_path + "/*", lab['controller-0 ip'], TiSPath.HEAT, pre_opts=pre_opts)


def download_lab_config_files(lab, server, load_path, conf_server=None, lab_file_dir=None):

    if 'vbox' in lab["name"]:
        return
    if not lab_file_dir:
        lab_file_dir = InstallVars.get_install_var("LAB_SETUP_PATH")

    if not os.path.isabs(lab_file_dir):
        raise ValueError("Abs path required for {}".format(lab_file_dir))

    lab_name = lab['name']
    lab_name = lab_name.split('yow-', maxsplit=1)[-1]

    if not conf_server:
        conf_server = server

    sys_version = extract_software_version_from_string_path(load_path)
    sys_version = sys_version if sys_version in BuildServerPath.DEFAULT_LAB_CONFIG_PATH_EXTS else 'default'
    default_lab_config_path = os.path.join(load_path, BuildServerPath.DEFAULT_LAB_CONFIG_PATH_EXTS[sys_version])

    if lab_file_dir:
        lab_file_dir = os.path.abspath(lab_file_dir)
        if os.path.basename(lab_file_dir) == 'yow':
            lab_file_dir += '/{}'.format(lab_name)

        #script_path = lab_file_dir
        if '/lab/yow/' in lab_file_dir:
            script_path = os.path.join(lab_file_dir.rsplit('/lab/yow/', maxsplit=1)[0], 'lab/scripts')
        else:
            script_path = os.path.join(default_lab_config_path, "scripts")
    else:
        lab_file_dir = default_lab_config_path + "/yow/{}".format(lab['name'])
        script_path = os.path.join(default_lab_config_path, "scripts")

    LOG.info("Getting lab config file from specified path: {}".format(lab_file_dir))

    pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.get_password())

    cmd = "test -e " + script_path
    server.ssh_conn.exec_cmd(cmd, rm_date=False, fail_ok=False)
    server.ssh_conn.rsync(script_path + "/*",
                               lab['controller-0 ip'],
                               WRSROOT_HOME, pre_opts=pre_opts)

    cmd = "test -e " + lab_file_dir
    conf_server.ssh_conn.exec_cmd(cmd, rm_date=False, fail_ok=False)
    conf_server.ssh_conn.rsync(lab_file_dir + "/*",
                               lab['controller-0 ip'],
                               WRSROOT_HOME, pre_opts=pre_opts if not isinstance(conf_server, Node) else '')

    # WK around for copying the stein lab_setup.sh file
    if "k8s_lab_config" in lab_file_dir:

            k8s_lab_setup_script_path = os.path.split(lab_file_dir)[0] + "/lab_setup_stein.sh"
            cmd = "test -e {}".format(k8s_lab_setup_script_path)
            conf_server.ssh_conn.exec_cmd(cmd, rm_date=False, fail_ok=False)
            conf_server.ssh_conn.rsync(k8s_lab_setup_script_path,
                                   lab['controller-0 ip'],
                                   WRSROOT_HOME + "lab_setup.sh", pre_opts='sshpass -p "Li69nux*"')



def download_lab_config_file(lab, server, load_path, config_file='lab_setup.conf'):

    lab_name = lab['name']
    if 'vbox' in lab_name:
        return

    if "yow" in lab_name:
        lab_name = lab_name[4:]

    config_path = "{}{}/yow/{}/{}".format(load_path, BuildServerPath.LAB_CONF_DIR_PREV, lab_name, config_file)

    cmd = "test -e " + config_path
    assert server.ssh_conn.exec_cmd(cmd, rm_date=False)[0] == 0, ' lab config path not found in {}:{}'.format(
            server.name, config_path)

    pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.get_password())
    server.ssh_conn.rsync(config_path,
                          lab['floating ip'],
                          WRSROOT_HOME, pre_opts=pre_opts)


def bulk_add_hosts(lab, hosts_xml_file, con_ssh=None):
    if con_ssh is None:
        controller_ssh = ControllerClient.get_active_controller(lab["short_name"])
    else:
        controller_ssh=con_ssh

    cmd = "test -f {}/{}".format(WRSROOT_HOME, hosts_xml_file)
    if controller_ssh.exec_cmd(cmd)[0] == 0:
        rc, output = cli.system("host-bulk-add", hosts_xml_file, fail_ok=True, ssh_client=con_ssh)
        if rc != 0 or "Configuration failed" in output:
            msg = "system host-bulk-add failed"
            return rc, None, msg
        hosts = system_helper.get_hostnames_per_personality(con_ssh=con_ssh, rtn_tuple=True)
        return 0, hosts, ''
    else:
        msg = "{} file not found in {}".format(hosts_xml_file, WRSROOT_HOME)
        LOG.warning(msg)
        return 1, None, msg


def download_hosts_bulk_add_xml_file(lab, server, file_path):

    if not lab or not server or not file_path:
        raise ValueError(" Values must be provided.")

    cmd = "test -e " + file_path
    assert server.ssh_conn.exec_cmd(cmd, rm_date=False)[0] == 0, ' lab hosts bulk add xml path not found in {}:{}'\
        .format(server.name, file_path)
    pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.get_password())

    server.ssh_conn.rsync(file_path + "/hosts_bulk_add.xml",
                          lab['controller-0 ip'],
                          WRSROOT_HOME, pre_opts=pre_opts)




def add_storages(lab, server, load_path):
    lab_name = get_git_name(lab['name'])

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


def run_lab_setup(script='lab_setup', conf_file=None, con_ssh=None, timeout=3600):
    return run_setup_script(script=script, config=True, conf_file=conf_file, con_ssh=con_ssh, timeout=timeout)


def run_infra_post_install_setup():
    return run_setup_script(script="lab_infra_post_install_setup", config=True)


def run_setup_script(script="lab_setup", config=False, conf_file=None,  con_ssh=None, timeout=3600, fail_ok=True):
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    if config:
        if not conf_file:
            conf_file = script + '.conf'
        else:
             if os.path.splitext(conf_file)[1] == '':
                conf_file += '.conf'

        cmd = "test -e {}".format(WRSROOT_HOME + conf_file)
        rc = con_ssh.exec_cmd(cmd, fail_ok=fail_ok)[0]

        if rc != 0:
            msg = "The {} file missing from active controller".format(conf_file)
            if fail_ok:
                return rc, msg
            else:
                raise exceptions.InstallError(msg)

    cmd = "test -e {}/{}.sh".format(WRSROOT_HOME, script)
    rc = con_ssh.exec_cmd(cmd, fail_ok=fail_ok)[0]

    if rc != 0:
        msg = "The {}.sh file missing from active controller".format(script)
        if fail_ok:
            return rc, msg
        else:
            raise exceptions.InstallError(msg)

    if conf_file:
        cmd = "cd; source /etc/nova/openrc; ./{}.sh -f {}".format(script, conf_file)
    else:
        cmd = "cd; source /etc/nova/openrc; ./{}.sh".format(script)

    con_ssh.set_prompt(Prompt.ADMIN_PROMPT)
    rc, msg = con_ssh.exec_cmd(cmd, expect_timeout=timeout, fail_ok=fail_ok)
    if rc != 0:
        msg = " {} run failed: {}".format(script, msg)
        LOG.warning(msg)
        scp_logs_to_log_dir([LogPath.LAB_SETUP_LOG, LogPath.HEAT_SETUP_LOG], con_ssh=con_ssh)
        if fail_ok:
           return rc, msg
        else:
            raise exceptions.InstallError(msg)
    # con_ssh.set_prompt()
    return 0, "{} run successfully".format(script)


def scp_logs_to_log_dir(log_paths, con_ssh=None, log_dir=None):
    if isinstance(log_paths, str):
        log_paths = [log_paths]
    if not log_dir:
        log_dir = ProjVar.get_var('LOG_DIR')
    if not con_ssh:
        con_ssh = ControllerClient.get_active_controller()

    for log in log_paths:
        log_exists = con_ssh.exec_cmd('test -f {}'.format(log))[0] == 0
        if log_exists:
            LOG.info("Copying {} to {}".format(log, log_dir))
            common.scp_to_local(source_path=log, source_ip=con_ssh.host, dest_path=log_dir)


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
        return ''
    else:
        usb_ls = output.strip().splitlines()[0].split("->").pop()

        LOG.info("USB found: {}".format(usb_ls))
        usb_device = usb_ls.strip().split("/").pop()
        LOG.info("USB found: {}".format(usb_device))
        usb_device = usb_device[0:3]
        LOG.info("USB device is: {}".format(usb_device))

    LOG.info("USB device is: {}".format(usb_device))
    if usb_device and 'sd' not in usb_device or len(usb_device) != 3:
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
        usb_device:
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
    controller0_node = lab['controller-0']

    if controller0_node.telnet_conn is None:
        controller0_node.telnet_conn = open_telnet_session(controller0_node)
        controller0_node.telnet_conn.login()

    connection = controller0_node.telnet_conn

    if RestoreVars.get_restore_var('REINSTALL_STORAGE'):
        storage_opt = 'include-storage-reinstall'
    else:
        storage_opt = 'exclude-storage-reinstall'

    cmd = 'echo "{}" | sudo -S config_controller --restore-system {} {}'.format(HostLinuxCreds.get_password(),
        storage_opt,
        system_backup)

    os.environ["TERM"] = "xterm"

    blob = list(outputs_restore_system_conf)
    blob.append(connection.prompt)

    rc, output = connection.exec_cmd(cmd, blob=blob,
                                     expect_timeout=InstallTimeout.SYSTEM_RESTORE)
    compute_configured = False
    if rc == 0:
        if 'compute-config in progress' in output:
            if not is_aio:
                LOG.fatal('Not an AIO lab, but the system IS configuring compute functionality')
            else:
                LOG.info('No need to do compute-config-complete, which is a new behavior after 2017-11-27.')
                LOG.info('Instead, we will have to wait the node self-boot and boot up to ready states.')

            connection.expect(['controller\-[01] login:'], timeout=HostTimeout.REBOOT)

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

            rc, output = connection.exec_cmd(reboot_cmd, blob=[' login: '], expect_timeout=HostTimeout.REBOOT)
            if rc != 0:
                msg = '{} failed, rc:{}\noutput:\n{}'.format(reboot_cmd, rc, output)
                LOG.error(msg)
                raise exceptions.RestoreSystem
            LOG.info('OK, system reboot after been patched to previous level')

            LOG.info('re-login')
            connection.login()
            os.environ["TERM"] = "xterm"

            LOG.info('re-run cli:{}'.format(cmd))

            rc, output = connection.exec_cmd(cmd, blob=[' login: '],
                                             expect_timeout=InstallTimeout.SYSTEM_RESTORE)
            LOG.debug('rc:{}, output:{}'.format(rc, output))

        if "System restore complete" in output:
            msg = "System restore completed successfully"
            LOG.info(msg)
            return 0, msg, compute_configured

        else: # elif ' login: ' in output:
            # Again?! The system behaviors changed without any clue?
            msg = "system behaviors changed again without notice again"
            LOG.warn(msg)
            LOG.info('re-login')
            connection.login()
            os.environ["TERM"] = "xterm"

    else:
        err_msg = "{} execution failed: {} {}".format(cmd, rc, output)
        LOG.error(err_msg)
        if fail_ok:
            return 1, err_msg, compute_configured
        else:
            raise exceptions.CLIRejected(err_msg)

    return rc, output, compute_configured


def upgrade_controller_simplex(system_backup, tel_net_session=None, fail_ok=False):
    """
    Restores the controller system config for system restore.
    Args:
        system_backup(str): The system config backup file
        tel_net_session:
        fail_ok:

    Returns (tuple): rc, text message
        0 - Success
        1 - Execution of upgrade command failed
        2 - Patches not applied after system reboot
        3 - Unexpected result after system restore
    """

    if system_backup is None or not os.path.abspath(system_backup):
        msg = "Full path of the system backup file must be provided: {}".format(system_backup)
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

    cmd = 'echo "{}" | sudo -S upgrade_controller_simplex {}'.format(HostLinuxCreds.get_password(),
                                                                     system_backup)
    os.environ["TERM"] = "xterm"
    outputs_conf = ("Data restore complete", "login:")
    rc, output = tel_net_session.exec_cmd(cmd, extra_expects=outputs_conf, timeout=InstallTimeout.SYSTEM_RESTORE,
                                          will_reboot=True)
    if rc == 0:
        if output in 'System restore complete':
            msg = "System restore completed successfully"
            LOG.info(msg)
            return 0, msg
        else:
            msg = 'This controller has been patched'
            LOG.warn("Controller is patched")
            LOG.info('re-login to re-excute the upgrade_controller_simplex')
            tel_net_session.login()
            rc, output = tel_net_session.exec_cmd(cmd, extra_expects=outputs_conf,
                                                  timeout=InstallTimeout.SYSTEM_RESTORE, alt_prompt='login:',
                                                  will_reboot=True)
            if output in 'System restore complete':
                msg = "System restore completed successfully"
                LOG.info(msg)
                return 0, msg
            else:
                LOG.debug('rc:{}, output:{}'.format(rc, output))

    err_msg = "{} execution failed: {} {}".format(cmd, rc, output)
    LOG.error(err_msg)

    if fail_ok:
        return 1, err_msg
    raise exceptions.CLIRejected(err_msg)


def restore_compute(tel_net_session=None, fail_ok=False):
    """
    Restores the controller system compute for system restore.
    Args:
       tel_net_session:
        fail_ok:

    Returns (tuple): rc, text message
        0 - Success
        1 - Execution of restore command failed
        2 - System compute restore did not complete

    """

    lab = InstallVars.get_install_var("LAB")
    output_dir = ProjVar.get_var('LOG_DIR')
    controller0_node = lab['controller-0']
    if tel_net_session is None:

        if controller0_node.telnet_conn is None:
            controller0_node.telnet_conn = open_telnet_session(controller0_node, output_dir)
            controller0_node.telnet_conn.login()

        tel_net_session = controller0_node.telnet_conn

    cmd = "echo " + HostLinuxCreds.get_password() + " | sudo -S config_controller --restore-compute"
    os.environ["TERM"] = "xterm"
    outputs_conf = ('controller-0','login:')
    rc, output = tel_net_session.exec_cmd(cmd,extra_expects=outputs_conf, timeout=InstallTimeout.SYSTEM_RESTORE,
                                          will_reboot=True)
    if rc != 0:
        err_msg = "{} failed: {} {}".format(cmd, rc, output)
        LOG.error(err_msg)
        if fail_ok:
            return 1, err_msg
        else:
            raise exceptions.CLIRejected(err_msg)
    LOG.info('re-login to re-excute the upgrade_controller_simplex')  ####/Commented due to promot issue need to be fixed in library
    time.sleep(HostTimeout.REBOOT)
    tel_net_session.login()
    LOG.info('Waiting for the simplex to reconnect')
    host_helper._wait_for_simplex_reconnect(timeout=HostTimeout.REBOOT)
    if not host_helper.wait_for_host_values('controller-0', timeout=HostTimeout.CONTROLLER_UNLOCK,
                                            check_interval=10, availability=[HostAvailState.AVAILABLE]):
        err_msg = "Host did not become online  after downgrade"
        if fail_ok:
            return 2, err_msg
        else:
            raise exceptions.HostError(err_msg)

    # compute restored
    msg = "compute restore completed successfully"
    LOG.info(msg)
    return 0, msg


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
            controller0_node.telnet_conn = open_telnet_session(controller0_node)
            controller0_node.telnet_conn.login()

        tel_net_session = controller0_node.telnet_conn

    cmd = "echo " + HostLinuxCreds.get_password() + " | sudo -S config_controller --restore-images {}".format(images_backup)
    os.environ["TERM"] = "xterm"

    rc, output = tel_net_session.exec_cmd(cmd, expect_timeout=InstallTimeout.SYSTEM_RESTORE)
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
        pattern = r'titanium_backup_(\.\w)*.+_(.*)_(system|images)\.tgz'
    found_backup_files = []

    backup_files = get_backup_files_from_usb(pattern=pattern, usb_device=usb_device, con_ssh=con_ssh)

    lab = InstallVars.get_install_var("LAB")
    system_name = lab['name'].strip()
    for file in backup_files:
        if system_name in file:
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


def restore_cinder_volumes_from_backup(con_ssh=None, fail_ok=False):
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

        restored_cinder_volumes, volumes_in_db = import_volumes_from_backup(cinder_volume_backups, con_ssh=con_ssh)

        LOG.info("Restored volumes: {}".format(restored_cinder_volumes))
        restored = len(restored_cinder_volumes)

        if restored != len(volumes_in_db):
            LOG.info("NOT all volumes were restored, restored:{}, should to be restored:{}".format(restored, len(volumes_in_db)))
            return -1, restored_cinder_volumes

        elif restored > 0:
            LOG.info("All volumes restored successfully")
            return 0, restored_cinder_volumes

        else:
            LOG.info("OK, no volumes recorded in DB hence none needs to be restored")
            return 0, []


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
                LOG.warning("The volume {} does not exist; cannot be imported, volume_backup:{}".format(vol_id, volume_backup_path))
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

    return imported_volumes, volumes


def export_cinder_volumes(backup_dest='usb', backup_dest_path=BackupRestore.USB_BACKUP_PATH, dest_server=None,
                          copy_to_usb=None, delete_backup_file=True, con_ssh=None, fail_ok=False, cinder_backup=False):
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
        volumes_exported.extend(cinder_helper.export_volumes(cinder_backup=cinder_backup, con_ssh=con_ssh)[1])

        if len(volumes_exported) > 0:
            LOG.info("Cinder volumes exported: {}".format(volumes_exported))
            if len(current_volumes) > len(volumes_exported):
                LOG.warn("Not all current cinder volumes are  exported; Unexported volumes: {}"
                         .format(set(current_volumes) - set(volumes_exported)))

            if cinder_backup:
                container = 'cinder'
                is_dir = True
                src_files = "/opt/backups/{}".format(container)
            else:
                is_dir = False
                src_files = "/opt/backups/volume-*.tgz"

            if backup_dest == 'local':
                if dest_server:
                    if dest_server.ssh_conn.exec_cmd("test -e  {}".format(backup_dest_path))[0] != 0:
                        dest_server.ssh_conn.exec_cmd("mkdir -p {}".format(backup_dest_path))
                else:
                    if local_client().exec_cmd("test -e {}".format(backup_dest_path))[0] != 0:
                        local_client().exec_cmd("mkdir -p {}".format(backup_dest_path))

                common.scp_from_active_controller_to_test_server(src_files,
                                                                 backup_dest_path,
                                                                 is_dir=is_dir,
                                                                 multi_files=True)

                LOG.info("Verifying if backup files are copied to destination")
                if dest_server:
                    rc, output = dest_server.ssh_conn.exec_cmd("ls {}".format(backup_dest_path))
                else:
                    rc, output = local_client().exec_cmd("ls {}".format(backup_dest_path))

                if rc != 0:
                    err_msg = "Failed to scp cinder backup files {} to local destination: {}".format(backup_dest_path,
                                                                                                     output)
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
                    con_ssh.exec_sudo_cmd(cp_cmd, expect_timeout=InstallTimeout.SYSTEM_RESTORE)
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
                  timeout=InstallTimeout.SYSTEM_BACKUP, copy_to_usb=None, delete_backup_file=True,
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
    backup_file_name = "{}{}_{}_{}".format(backup_file_prefix, date, build_id, lab_system_name)
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
            if local_client().exec_cmd("test -e {}".format(backup_dest_path))[0] != 0:
                local_client().exec_cmd("mkdir -p {}".format(backup_dest_path))

        src_files = "{} {}".format(backup_files[0].strip(), backup_files[1].strip())
        common.scp_from_active_controller_to_test_server(src_files, backup_dest_path, is_dir=False, multi_files=True)

        LOG.info("Verifying if backup files are copied to destination")
        if dest_server:
            rc, output = dest_server.ssh_conn.exec_cmd("ls {}/{}*.tgz".format(backup_dest_path, backup_file_name ))
        else:
            rc, output = local_client().exec_cmd("ls {}/{}*.tgz".format(backup_dest_path, backup_file_name))

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
            con_ssh.exec_sudo_cmd(cp_cmd,expect_timeout=InstallTimeout.BACKUP_COPY_USB)

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
            if local_client().exec_cmd("test -e {}".format(backup_dest_path))[0] != 0:
                local_client().exec_cmd("mkdir -p {}".format(backup_dest_path))

        common.scp_from_active_controller_to_test_server(src_file, backup_dest_path, is_dir=False, multi_files=True)

        LOG.info("Verifying if image backup files are copied to destination")
        base_name_src = os.path.basename(src_file)
        if dest_server:
            rc, output = dest_server.ssh_conn.exec_cmd("ls {}/{}".format(backup_dest_path, base_name_src))
        else:
            rc, output = local_client().exec_cmd("ls {}/{}".format(backup_dest_path, base_name_src))

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


def set_network_boot_feed(bld_server_conn, load_path, lab=None, boot_server=None, skip_cfg=False):
    """
    Sets the network feed for controller-0 in default taxlab
    Args:
        bld_server_conn:
        load_path:
        lab:
        skip_cfg:

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

    if not lab:
        lab = InstallVars.get_install_var("LAB")

    tuxlab_server = boot_server if boot_server else InstallVars.get_install_var("BOOT_SERVER")
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

    feed_path = tuxlab_barcode_dir + "/" + tuxlab_sub_dir
    LOG.info("Copy load into {}".format(feed_path))
    tuxlab_conn.exec_cmd("mkdir -p " + tuxlab_sub_dir)
    tuxlab_conn.exec_cmd("chmod 755 " + tuxlab_sub_dir)

    cfg_link = tuxlab_conn.exec_cmd("readlink pxeboot.cfg")[1]
    if cfg_link != "pxeboot.cfg.gpt" and not skip_cfg:
        LOG.info("Changing pxeboot.cfg symlink to pxeboot.cfg.gpt")
        tuxlab_conn.exec_cmd("ln -s pxeboot.cfg.gpt pxeboot.cfg")

    # LOG.info("Installing Centos load to feed path: {}".format(feed_path))
    # bld_server_conn.exec_cmd("cd " + load_path)
    pre_opts = 'sshpass -p "{0}"'.format(SvcCgcsAuto.PASSWORD)
    bld_server_conn.rsync(load_path + "/" + CENTOS_INSTALL_REL_PATH + "/", tuxlab_server, feed_path,
                          dest_user=SvcCgcsAuto.USER, dest_password=SvcCgcsAuto.PASSWORD,
                          extra_opts=["--delete", "--force", "--chmod=Du=rwx"], pre_opts=pre_opts,
                          timeout=InstallTimeout.INSTALL_LOAD)
    bld_server_conn.rsync(load_path + "/" + "export/extra_cfgs/yow*", tuxlab_server, feed_path, dest_user=SvcCgcsAuto.USER,
                          dest_password=SvcCgcsAuto.PASSWORD, extra_opts=["--chmod=Du=rwx"], pre_opts=pre_opts,
                          timeout=InstallTimeout.INSTALL_LOAD)
    LOG.info("Create new symlink to {}".format(feed_path))
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


def boot_controller(lab=None, bld_server_conn=None, patch_dir_paths=None, boot_usb=False, low_latency=None,
                    small_footprint=None, security=None, clone_install=False, system_restore=False):
    """
    Boots controller-0 either from tuxlab or USB.
    Args:
        bld_server_conn:
        patch_dir_paths:
        boot_usb:
        small_footprint:
        low_latency:
        security:
        clone_install:
        system_restore:

    Returns:

    """

    if lab is None:
        lab = InstallVars.get_install_var("LAB")

    controller0 = lab["controller-0"]
    if controller0.telnet_conn is None:
        controller0.telnet_conn = open_telnet_session(controller0)

    boot_interfaces = lab['boot_device_dict']
    LOG.info("Opening a vlm console for {}.....".format(controller0.name))
    rc, output = vlm_helper._reserve_vlm_console(controller0.barcode)
    if rc > 0:
        err_msg = "Failed to reserve vlm console for {}  barcode {}: {}"\
            .format(controller0.name, controller0.barcode, output)
        raise exceptions.VLMError(err_msg)

    bring_node_console_up(controller0, boot_interfaces,
                          boot_usb=boot_usb,
                          small_footprint=small_footprint,
                          low_latency=low_latency,
                          security=security,
                          vlm_power_on=True,
                          close_telnet_conn=False,
                          lab=lab)

    LOG.info("Initial login and password set for " + controller0.name)
    if boot_usb:
        controller0.telnet_conn.set_prompt(r'(-[\d]+)|(localhost):~\$ ')
    else:
        controller0.telnet_conn.set_prompt(r'-[\d]+:~\$ ')

    controller0.telnet_conn.login(handle_init_login=True)

    if boot_usb:
        setup_networking(controller0)

    if not system_restore and (patch_dir_paths and bld_server_conn):
        time.sleep(40)
        apply_patches(lab, bld_server_conn, patch_dir_paths)
        controller0.telnet_conn.send("echo " + HostLinuxCreds.get_password() + " | sudo -S reboot")
        LOG.info("Patch application requires a reboot.")
        LOG.info("Controller0 reboot has started")

        controller0.telnet_conn.expect(Prompt.LOGIN_PROMPT, HostTimeout.REBOOT)
        # Reconnect telnet session
        LOG.info("Found login prompt. Controller0 reboot has completed")
        controller0.telnet_conn.login()
        LOG.info("Removing patches")
        remove_patches(lab)
        if boot_usb:
            setup_networking(controller0)

        # controller0.ssh_conn.disconnect()
        # controller0.ssh_conn = establish_ssh_connection(controller0, install_output_dir)


def setup_networking(controller0, conf_server=None, conf_dir=None):
    if not controller0.host_nic:
        controller0.host_nic = get_nic_from_config(conf_server=conf_server)
    nic_interface = controller0.host_nic
    if not controller0.telnet_conn:
        controller0.telnet_conn = open_telnet_session(controller0)

    controller0.telnet_conn.exec_cmd("echo {} | sudo -S ip addr add {}/23 dev {}".format(controller0.telnet_conn.password,
                                                                                             controller0.host_ip,
                                                                                             nic_interface))
    controller0.telnet_conn.exec_cmd("echo {} | sudo -S ip link set dev {} up".format(controller0.telnet_conn.password,
                                                                                          nic_interface))
    controller0.telnet_conn.exec_cmd("echo {} | sudo -S route add default gw 128.224.150.1".format(
                                     controller0.telnet_conn.password))
    ping = network_helper.ping_server(server="8.8.8.8", ssh_client=controller0.telnet_conn, num_pings=4, fail_ok=True)
    if not ping:
        time.sleep(120)
        network_helper.ping_server(server="8.8.8.8", ssh_client=controller0.telnet_conn, num_pings=4, fail_ok=False)

    return 0


def get_nic_from_config(conf_server=None, conf_dir=None, delete_server=False):
    if not conf_server:
        conf_server = setups.initialize_server(InstallVars.get_install_var("FILES_SERVER"))
        delete_server = True
    conf_dir = conf_dir if conf_dir else InstallVars.get_install_var("LAB_SETUP_PATH")
    oam_interface = None
    nic = None
    count = 0
    conf_file = conf_dir + "/TiS_config.ini_centos"

    rc, output = conf_server.ssh_conn.exec_cmd("cat {}".format(conf_file))
    sections = output.split("\n\n")
    while nic is None:
        count += 1
        for section in sections:
            if not oam_interface and "[OAM_NETWORK]" in section:
                lines = section.split("\n")
                for line in lines:
                    if "LOGICAL_INTERFACE" in line:
                        oam_interface = "[" + line[line.find("=") + 1:].strip() + "]"
            if oam_interface and oam_interface in section:
                lines = section.split("\n")
                for line in lines:
                    if "INTERFACE_PORTS" in line:
                        nic_ports = line[line.find("=") + 1:].strip()
                        nic = nic_ports[:nic_ports.find(",")]
            if count > 2:
                raise ValueError("could not parse nic from {}".format(conf_file))

    if delete_server:
        conf_server.ssh_conn.close()
        del conf_server

    return nic


def apply_patches(lab, build_server, patch_dir):
    """

    Args:
        lab:
        build_server:
        patch_dir:

    Returns:

    """
    patch_names = []
    controller0_node = lab["controller-0"]
    if controller0_node.ssh_conn:
        con_ssh = controller0_node.ssh_conn
    elif controller0_node.telnet_conn:
        con_ssh = controller0_node.telnet_conn
    else:
        con_ssh = None
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

        patch_dest_dir = WRSROOT_HOME + "patches/"

        pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.get_password())
        # build_server.ssh_conn.rsync(patch_dir + "/*.patch", lab['controller-0 ip'], patch_dest_dir, pre_opts=pre_opts)
        build_server.rsync(patch_dir + "/*.patch", lab['controller-0 ip'], patch_dest_dir, pre_opts=pre_opts,
                           timeout=InstallTimeout.INSTALL_LOAD)

        avail_patches = " ".join(patch_names)
        LOG.info("List of patches:\n {}".format(avail_patches))

        LOG.info("Uploading  patches ... ")
        assert patching_helper.run_patch_cmd("upload-dir", args=patch_dest_dir, con_ssh=con_ssh)[0] == 0, \
            "Failed to upload  patches : {}".format(avail_patches)

        LOG.info("Querying patches ... ")
        assert patching_helper.run_patch_cmd("query", con_ssh=con_ssh)[0] == 0, "Failed to query patches"

        LOG.info("Applying patches ... ")
        rc = patching_helper.run_patch_cmd("apply", args='--all', con_ssh=con_ssh)[0]
        assert rc == 0, "Failed to apply patches"

        LOG.info("Installing Patches ... ")
        assert patching_helper.run_patch_cmd("install-local", con_ssh=con_ssh)[0] == 0, "Failed to install patches"

        LOG.info("Querying patches ... ")
        assert patching_helper.run_patch_cmd("query", con_ssh=con_ssh)[0] == 0, "Failed to query patches"


def remove_patches(lab):
    patch_dir = WRSROOT_HOME + "patches/"
    controller0_node = lab["controller-0"]
    if controller0_node.ssh_conn:
        con_ssh = controller0_node.ssh_conn
    elif controller0_node.telnet_conn:
        con_ssh = controller0_node.telnet_conn
    else:
        con_ssh = None
    rc, output = con_ssh.exec_cmd("ls -1 --color=none {}".format(patch_dir))
    if rc != 0:
        msg = 'No patch directory'
        LOG.debug(msg)
        return 1, msg

    if output is not None:
        for patch in output.splitlines():
            rc, output = con_ssh.exec_cmd("rm {}".format(patch_dir + patch))
            if rc != 0:
                LOG.debug("Failed to remove {}".format(patch))

    return 0, ''


def establish_ssh_connection(host, user=HostLinuxCreds.get_user(), password=HostLinuxCreds.get_password(),
                             initial_prompt=Prompt.CONTROLLER_PROMPT, retry=False, fail_ok=False):

    try:
        _ssh_conn = SSHClient(host, user=user, password=password, initial_prompt=initial_prompt, timeout=360)
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


def update_auth_url(ssh_con, region=None, use_telnet=False, con_telnet=None, fail_ok=True):
    """

    Args:
        ssh_con:
        region:

    Returns:

    CGTS-8190
    """

    LOG.info('Attempt to update OS_AUTH_URL from openrc')

    CliAuth.set_vars(**setups.get_auth_via_openrc(con_ssh=ssh_con, use_telnet=use_telnet, con_telnet=con_telnet ))
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

    if controller0_node.telnet_conn is None:
        controller0_node.telnet_conn = open_telnet_session(controller0_node)
        controller0_node.telnet_conn.login()

    controller0_node.telnet_conn.exec_cmd("cd; source /etc/nova/openrc")

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
            hosts = host_helper.system_helper.get_hostnames()
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
        except exceptions.TelnetError as e:
            LOG.warn('got error:{}'.format(e))

        LOG.info('{} is not ready yet, failed to source /etc/nova/openrc, continue to wait'.format(controller0))
        time.sleep(15)

    LOG.info('closing the telnet connnection to node:{}'.format(controller0))
    controller0_node.telnet_conn.close()

    LOG.info('waiting for node:{} to be ready'.format(controller0))
    host_helper.wait_for_hosts_ready(controller0)
    LOG.info('OK, {} is up and ready'.format(controller0))


def create_cloned_image(cloned_image_file_prefix=PREFIX_CLONED_IMAGE_FILE, lab_system_name=None,
                  timeout=InstallTimeout.SYSTEM_BACKUP, dest_labs=None, delete_cloned_image_file=True,
                  con_ssh=None, fail_ok=False):
    """
    Creates system cloned image for AIO systems and copy the iso image to to USB.
    Args:
        cloned_image_file_prefix(str): The prefix to the generated system cloned image iso file.
            The default is "titanium_backup_"
        lab_system_name(str): is the lab system name
        timeout(inst): is the timeout value the system clone is expected to finish.
        dest_labs (str/list): list of labs the cloned image iso file is scped. Default is local.
        delete_cloned_image_file(bool): if USB is available, the cloned image iso file is deleted from system to
            save disk space.
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
        err_msg = "Command {} failed execution: {}".format(cmd, output)
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

    cloned_image_file_name += ".iso"
    LOG.info("System cloned image iso file is created in /opt/backups folder: {} ".format(cloned_image_file_name))

    return 0, cloned_image_file_name


def check_clone_status(tel_net_session=None, con_ssh=None, fail_ok=False):
    """
    Checks the fresh_install-clone status after system is booted from cloned image.
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
        controller0_node.telnet_conn = open_telnet_session(controller0_node)
        controller0_node.telnet_conn.login()
        controller0_node.telnet_conn.exec_cmd("xterm")

    cmd = 'config_controller --clone-status'.format(HostLinuxCreds.get_password())
    os.environ["TERM"] = "xterm"

    rc, output = tel_net_session.exec_sudo_cmd(cmd, timeout=InstallTimeout.INSTALL_CLONE_STATUS)

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
         system host-if-show <host> <if>
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
        controller_0_node.telnet_conn = open_telnet_session(controller_0_node)
        controller_0_node.telnet_conn.login()

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
    assert table_parser.get_values(table_, target_header='name', **{'class': 'data'}), \
        "No data interface type found in Host {} after system clone-install".format(host)
    platform_ifs = table_parser.get_values(table_, target_header='name', **{'class': 'platform'})
    net_types = ['mgmt', 'oam']
    for pif in platform_ifs:
        host_if_show_tab = table_parser.table(cli.system('host-if-show', '{} {}'.format(host, pif), use_telnet=True,
                                                         con_telnet=controller_0_node.telnet_conn))
        net_type = table_parser.get_value_two_col_table(host_if_show_tab, 'networks')
        if net_type in net_types:
            net_types.remove(net_type)
    assert not net_types, "No {} interface found in Host {} after system clone-install".format(net_types, host)

    LOG.info("Executing system host disk list on cloned system host {}".format(host))
    table_ = table_parser.table(cli.system('host-disk-list {} --nowrap'.format(host), use_telnet=True,
                                           con_telnet=controller_0_node.telnet_conn))
    assert len(table_['values']) >= 2, "Fewer disks listed than expected for host {}: {}".format(host, table_)


def update_oam_for_cloned_system( system_mode='duplex', fail_ok=False):

    lab = InstallVars.get_install_var("LAB")
    output_dir = ProjVar.get_var('LOG_DIR')
    controller0_node = lab['controller-0']

    if controller0_node.telnet_conn is None:
        controller0_node.telnet_conn = open_telnet_session(controller0_node)
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


def update_system_info_for_cloned_system(system_mode='duplex', fail_ok=False):

    lab = InstallVars.get_install_var("LAB")

    system_info = {
        'description': None,
        'name': lab['name'],
    }

    system_helper.modify_system(**system_info)


def scp_cloned_image_to_labs(dest_labs, clone_image_iso_filename, boot_lab=True,  clone_image_iso_path=None,
                             con_ssh=None, fail_ok=False):
    """

    Args:
        dest_labs (dict/list): list of AIO lab dictionaries similar to the src_lab that the cloned image is scped.
        boot_lab(bool): Whether to boot the lab if not accessible; default is true
        src_lab(dict): is the current lab where the clone image iso is created. Default is current lab
        clone_image_iso_path(str): -The path to the cloned image iso file in source lab controller-0.
        The default is /opt/backups.
        con_ssh:

    Returns:

    """
    if dest_labs is None or (isinstance(dest_labs, list) and len(dest_labs) == 0):
        raise ValueError("A list lab dictionary object must be provided")
    if isinstance(dest_labs, str):
        dest_labs = [dest_labs]

    src_lab = ProjVar.get_var("LAB")
    if 'system_type' not in  src_lab.keys() or  src_lab['system_type'] != 'CPE':
        err_msg = "Lab {} is not AIO; System clone is only supported for AIO systems only".format(src_lab['name'])
        if fail_ok:
            return 1, err_msg
        else:
            raise ValueError(err_msg)
    src_lab_name = src_lab['short_name']
    verified_dest_labs = []
    # check if labs are AIO systems
    for lab_ in dest_labs:
        if lab_.replace('-', '_').lower() == src_lab_name:
            verified_dest_labs.append(src_lab)
            continue

        lab_dict = lab_info.get_lab_dict(lab_)
        if 'system_type' in lab_dict.keys():
            if lab_dict['system_type'] == 'CPE' and lab_dict['system_mode'] == src_lab['system_mode']:
                verified_dest_labs.append(lab_dict)
            else:
                LOG.warn("Lab {} has not the same TiS system configuration as source lab {}".
                         format(lab_['short_name'], lab_info._get_sys_type(src_lab_name)))

    if len(verified_dest_labs) == 0:
        err_msg = "None of the specified labs match the system type and mode of the source lab {} ".\
            format(src_lab['name'])
        if fail_ok:
            return 2, err_msg
        else:
            raise ValueError(err_msg)

    for lab_dict in verified_dest_labs:
        if lab_dict['short_name'] == src_lab_name:
            continue
        lab_dict.update(create_node_dict(lab_dict['controller_nodes'], 'controller'))

        lab_dict['boot_device_dict'] = create_node_boot_dict(lab_dict['name'])

    if clone_image_iso_path is None:
        clone_image_iso_path = "/opt/backups"

    clone_image_iso_full_path = "{}/{}".format(clone_image_iso_path, clone_image_iso_filename)
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    if con_ssh.exec_cmd("ls {}".format(clone_image_iso_full_path))[0] != 0:
        err_msg = "The cloned image iso file {} does not exist in the  {}"\
            .format(clone_image_iso_full_path, con_ssh.get_hostname())
        if fail_ok:
            return 3, err_msg
        else:
            raise exceptions.BackupSystem(err_msg)

    boot_lab = True
    threads = {}
    clone_install_ready_labs = []
    for lab_dict in verified_dest_labs:
        lab_name = lab_dict['short_name']
        thread = multi_thread.MThread(scp_cloned_image_to_another, lab_dict, boot_lab=boot_lab,
                                      clone_image_iso_full_path=clone_image_iso_full_path)

        LOG.info("Starting thread for {}".format(thread.name))

        threads[lab_name] = thread
        try:
            thread.start_thread(timeout=InstallTimeout.INSTALL_CONTROLLER)
        except:
            LOG.warn("SCP to lab {} encountered error".format(lab_name))

    for k, v in threads.items():
        v.wait_for_thread_end()

    result = 0
    for k, v in threads.items():
        rc = v.get_output()
        if rc[0] == 0:
            clone_install_ready_labs.append(k)
            LOG.info("Transfer of cloned image iso file to Lab {} successful".format(k))
        else:
            result = 4
            LOG.info("Transfer of cloned image iso file to Lab {} not completed: {}".format(k, rc))

    return result, clone_install_ready_labs


def scp_cloned_image_to_another(lab_dict, boot_lab=True, clone_image_iso_full_path=None, con_ssh=None,
                             fail_ok=False):
    if lab_dict is None or not isinstance(lab_dict, dict):
        raise ValueError("The Lab atribute value dictionary must be provided")
    if 'controller-0' not in lab_dict.keys():
        raise ValueError("The Lab controller-0 node object must be provided")

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()
    clone_image_iso_dest_path = clone_image_iso_full_path
    src_lab = ProjVar.get_var("LAB")
    dest_lab_name = lab_dict['short_name']
    controller0_node = lab_dict['controller-0']

    if src_lab['short_name'] != dest_lab_name:
        LOG.info("Transferring cloned image iso file to lab: {}".format(dest_lab_name))
        clone_image_iso_dest_path = WRSROOT_HOME + os.path.basename(clone_image_iso_full_path)
        if local_client().ping_server(controller0_node.host_ip, fail_ok=True)[0] == 100:
            msg = "The destination lab {} controller-0 is not reachable.".format(dest_lab_name)
            if boot_lab:
                LOG.info("{} ; Attempting to boot lab {}:controller-0".format(msg, dest_lab_name))
                boot_controller(lab=lab_dict)
                if local_client().ping_server(controller0_node.host_ip, fail_ok=fail_ok)[0] == 100:
                    err_msg = "Cannot ping destination lab {} controller-0 after install".format(dest_lab_name)
                    LOG.warn(err_msg)
                    return 1, err_msg

                LOG.info("Lab {}: controller-0  booted successfully".format(dest_lab_name))
            else:
                LOG.warn(msg)
                if fail_ok:
                    return 1, msg
                else:
                    raise exceptions.BackupSystem(msg)

        log_file_prefix = ''
        install_output_dir = ProjVar.get_var("LOG_DIR")
        log_file_prefix += "{}_".format(dest_lab_name)

        con_ssh.scp_files(clone_image_iso_full_path, clone_image_iso_dest_path, dest_server=controller0_node.host_ip,
                          dest_password=HostLinuxCreds.get_password(), dest_user=HostLinuxCreds.get_user())


    with host_helper.ssh_to_remote_node(controller0_node.host_ip, prompt=Prompt.CONTROLLER_PROMPT, ssh_client=con_ssh) \
            as node_ssh:

        if node_ssh.exec_cmd("ls {}".format(clone_image_iso_dest_path))[0] != 0:
            err_msg = "The cloned image iso file {} does not exist in the lab {} {}"\
                .format(clone_image_iso_dest_path, dest_lab_name, node_ssh.get_hostname())
            if fail_ok:
                return 2, err_msg
            else:
                raise exceptions.BackupSystem(err_msg)

        # Burn the iso image file to USB
        usb_device = get_usb_device_name(con_ssh=node_ssh)

        if usb_device:
            LOG.info("Burning the system cloned image iso file to usb flash drive {}".format(usb_device))

            # Write the ISO to USB
            cmd = "echo {} | sudo -S dd if={} of=/dev/{} bs=1M oflag=direct; sync"\
                .format(HostLinuxCreds.get_password(), clone_image_iso_dest_path, usb_device)

            rc,  output = node_ssh.exec_cmd(cmd, expect_timeout=900)
            if rc != 0:
                err_msg = "Failed to copy the cloned image iso file to USB {}: {}".format(usb_device, output)
                LOG.info(err_msg)
                if fail_ok:
                    return 3, err_msg
                else:
                    raise exceptions.BackupSystem(err_msg)

            LOG.info(" The cloned image iso file copied to USB for restore. {}".format(output))

            LOG.info("Deleting system cloned image iso file from the dest lab folder ")
            node_ssh.exec_sudo_cmd("rm -f {}".format(clone_image_iso_dest_path))

            LOG.info("Cloned image iso file transfer to dest lab {} completed successfully".format(lab_dict['short_name']))

        else:
            err_msg = "No USB device found in destination lab {}".format(dest_lab_name)
            LOG.info(err_msg)
            if fail_ok:
                return 4, err_msg
            else:
                raise exceptions.BackupSystem(err_msg)

    return 0, None


def get_git_name(lab_name):
    """
    Args:
        lab_name: Str name of the lab

    Returns: the name of the lab as it is stored in the git repo

    """
    lab_name = lab_name.replace('\n', '')
    lab_name = lab_name.replace('yow-', '')
    try:
        lab_name.index('cgcs-')
    except ValueError:
        lab_name = 'cgcs-{}'.format(lab_name)
    # Workaround for pv0 lab name
    if len(lab_name.split('-')) < 3:
        last_letter = -1
        while lab_name[last_letter].isdigit():
            last_letter -= 1
        lab_name = '{}-{}'.format(lab_name[:last_letter+1], lab_name[last_letter+1:])

    return lab_name


def controller_system_config(con_telnet=None, config_file="TiS_config.ini_centos", lab=None, close_telnet=False,
                             banner=True, branding=True, kubernetes=False, subcloud=False):
    """
    Runs the config_controller command on the active_controller host
    Args:
        telnet_conn: The telnet connection to the active controller

    Returns:

    """
    if lab is None:
        lab = InstallVars.get_install_var("LAB")

    controller0 = lab["controller-0"]
    if con_telnet is None:
        con_telnet = open_telnet_session(controller0)
        con_telnet.login()
        close_telnet = True

    try:
        if banner:
            apply_banner(telnet_conn=con_telnet, fail_ok=True)
        if branding:
            apply_branding(telnet_conn=con_telnet, fail_ok=True)

        con_telnet.exec_cmd("unset TMOUT")
        histime_format_cmd = 'export HISTTIMEFORMAT="%Y-%m-%d %T "'
        bashrc_path = '{}/.bashrc'.format(WRSROOT_HOME)
        if con_telnet.exec_cmd("grep '{}' {}".format(histime_format_cmd, bashrc_path))[0] == 1:
            con_telnet.exec_cmd("""echo '{}'>> {}""".format(histime_format_cmd, bashrc_path))
            con_telnet.exec_cmd("source {}".format(bashrc_path))
        con_telnet.exec_cmd("export USER=wrsroot")
        con_telnet.exec_cmd("test -f {}".format(config_file), fail_ok=False)
        config_cmd = "config_region" if InstallVars.get_install_var("MULTI_REGION") \
            else "config_controller {}--config-file".format('--kubernetes ' if kubernetes else '') if not subcloud \
            else "config_subcloud"
        cmd = 'echo "{}" | sudo -S {} {}'.format(HostLinuxCreds.get_password(), config_cmd, config_file)
        os.environ["TERM"] = "xterm"
        rc, output = con_telnet.exec_cmd(cmd, expect_timeout=InstallTimeout.CONFIG_CONTROLLER_TIMEOUT, fail_ok=True)

        if "failed" in output:
            err_msg = "{} execution failed: {} {}".format(cmd, rc, output)
            LOG.error(err_msg)
            scp_logs_to_log_dir([LogPath.CONFIG_CONTROLLER_LOG], con_ssh=con_telnet)
            raise exceptions.CLIRejected(err_msg)

        LOG.info("Controller configured")
        admin_prompt = r"\[.*\(keystone_admin\)\]\$ "
        con_telnet.set_prompt(admin_prompt)
        con_telnet.exec_cmd('source /etc/nova/openrc')
        update_auth_url(ssh_con=None, use_telnet=True, con_telnet=con_telnet)
        host_helper.wait_for_hosts_states(controller0.name,
                                          availability=[HostAvailState.ONLINE, HostAvailState.DEGRADED],
                                          use_telnet=True, con_telnet=con_telnet)
        # if kubernetes:
        #     LOG.info("Setting DNS server ...")
        #     system_helper.set_dns_servers(["8.8.8.8"], with_action_option='apply', use_telnet=True,
        #                                   con_telnet=con_telnet)

    finally:
        if close_telnet:
            con_telnet.close()

    return rc, output


def apply_banner(telnet_conn, fail_ok=True):
    LOG.info("Applying banner files")
    banner_dir = "{}/banner/".format(WRSROOT_HOME)
    rc = telnet_conn.exec_cmd("test -d {}".format(banner_dir), fail_ok=fail_ok)[0]

    if rc != 0:
        err_msg = "Banner files not found"
        LOG.info(err_msg)
        return 1, err_msg
    else:
        rc = telnet_conn.exec_cmd("echo {} | sudo -S mv {} /opt/".format(HostLinuxCreds.get_password(), banner_dir),
                              fail_ok=fail_ok)[0]
        if rc != 0:
            err_msg = 'Banner application failed'
            LOG.info(err_msg)
            return 2, err_msg

    return 0, ''


def apply_branding(telnet_conn, fail_ok=True):
    LOG.info("Applying branding files")
    branding_dir = "{}/branding".format(WRSROOT_HOME)
    branding_dest = "/opt/branding"
    rc = telnet_conn.exec_cmd("test -d {}".format(branding_dir), fail_ok=fail_ok)[0]

    if rc != 0:
        err_msg = "Branding directory does not exist"
        LOG.info(err_msg)
        return 1, err_msg
    else:
        cmd = "echo {} | sudo -S cp -r {}/* {}".format(HostLinuxCreds.get_password(), branding_dir, branding_dest)
        rc = telnet_conn.exec_cmd(cmd)[0]
        if rc != 0:
            err_msg = "failed to copy branding files from {} to {}".format(branding_dir, branding_dest)
            LOG.info(err_msg)
            return 2, err_msg

    return 0, ''


def post_install(controller0_node=None):
    """
    runs post install scripts if there are any
    Args:
        controller0_node: a Node object representing the active controller of the lab.

    Returns tuple of a return code a message
    -1: Unable to execute one of the scripts
    0: succesfully ran post install scripts
    1: there was no directory containing any post install scripts to run
    2: The post install directory was empty


    """
    lab = InstallVars.get_install_var("LAB")
    if controller0_node is None:
        controller0_node = lab["controller-0"]
    if controller0_node.ssh_conn is not None:
        connection = controller0_node.ssh_conn
    else:
        connection = ControllerClient.get_active_controller()

    rc, msg = connection.exec_cmd("test -d /home/wrsroot/postinstall/")
    if rc == 0:
        scripts = connection.exec_cmd('ls -1 --color=none /home/wrsroot/postinstall/')[1].splitlines()
        if len(scripts) > 0:
            for script in scripts:
                LOG.info("Attempting to run {}".format(script))
                connection.exec_cmd("chmod 755 /home/wrsroot/postinstall/{}".format(script))
                rc = connection.exec_cmd("/home/wrsroot/postinstall/{} {}".format(script, controller0_node.host_name),
                                         expect_timeout=InstallTimeout.POST_INSTALL_SCRIPTS)[0]
                if rc != 0:
                    rc, msg = -1, 'Unable to execute {}'.format(script)
                    break
        else:
            rc, msg = 2, "No post install scripts in the directory"
    else:
        rc, msg = 1, "No post install directory"

    return rc, msg


# def unlock_controller(host, lab=None, timeout=HostTimeout.CONTROLLER_UNLOCK, available_only=True, fail_ok=False,
#                       con_ssh=None, use_telnet=False, con_telnet=None, auth_info=Tenant.ADMIN, check_first=True):
#
#     if check_first:
#         if host_helper.get_hostshow_value(host, 'availability', con_ssh=con_ssh, use_telnet=use_telnet,
#                               con_telnet=con_telnet,) in [HostAvailState.OFFLINE, HostAvailState.FAILED]:
#             LOG.info("Host is offline or failed, waiting for it to go online, available or degraded first...")
#             host_helper.wait_for_hosts_states(host, availability=[HostAvailState.AVAILABLE, HostAvailState.ONLINE,
#                                                      HostAvailState.DEGRADED], con_ssh=con_ssh,
#                                  use_telnet=use_telnet, con_telnet=con_telnet, fail_ok=False)
#
#         if host_helper.get_hostshow_value(host, 'administrative', con_ssh=con_ssh, use_telnet=use_telnet,
#                               con_telnet=con_telnet) == HostAdminState.UNLOCKED:
#             message = "Host already unlocked. Do nothing"
#             LOG.info(message)
#             return -1, message
#
#     sys_mode = system_helper.get_system_value(field="system_mode",  con_ssh=con_ssh, use_telnet=use_telnet,
#                                                       con_telnet=con_telnet, auth_info=auth_info)

    # exitcode, output = cli.system('host-unlock', host, ssh_client=con_ssh, use_telnet=use_telnet,
    #                               con_telnet=con_telnet, auth_info=auth_info, rtn_list=True, fail_ok=fail_ok,
    #                               timeout=60)
    # if exitcode == 1:
    #     return 1, output
    # if not lab:
    #     lab = InstallVars.get_install_var('LAB')
    #
    # if not len(lab['controller_nodes']) > 1:
    #     LOG.info("This is simplex lab; Waiting for controller reconnection after unlock")
    #     host_helper._wait_for_simplex_reconnect(con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet,
    #                                             duplex_direct=True if sys_mode == "duplex-direct" else False)
    #
    # if not host_helper.wait_for_hosts_states(host, timeout=60, administrative=HostAdminState.UNLOCKED, con_ssh=con_ssh,
    #                             use_telnet=use_telnet, con_telnet=con_telnet, fail_ok=fail_ok):
    #     return 2, "Host is not in unlocked state"
    #
    # if not host_helper.wait_for_hosts_states(host, timeout=timeout, fail_ok=fail_ok, check_interval=10, con_ssh=con_ssh,
    #                             use_telnet=use_telnet, con_telnet=con_telnet,
    #                             availability=[HostAvailState.AVAILABLE, HostAvailState.DEGRADED]):
    #     return 3, "Host state did not change to available or degraded within timeout"
    #
    # if sys_mode != 'duplex-direct':
    #     if not host_helper.wait_for_host_values(host, timeout=HostTimeout.TASK_CLEAR, fail_ok=fail_ok, con_ssh=con_ssh,
    #                                 use_telnet=use_telnet, con_telnet=con_telnet, task=''):
    #         return 5, "Task is not cleared within {} seconds after host goes available".format(HostTimeout.TASK_CLEAR)
    #
    # if host_helper.get_hostshow_value(host, 'availability', con_ssh=con_ssh, use_telnet=use_telnet,
    #                       con_telnet=con_telnet) == HostAvailState.DEGRADED:
    #     if not available_only:
    #         LOG.warning("Host is in degraded state after unlocked.")
    #         return 4, "Host is in degraded state after unlocked."
    #     else:
    #         if not host_helper.wait_for_hosts_states(host, timeout=timeout, fail_ok=fail_ok, check_interval=10, con_ssh=con_ssh,
    #                                     use_telnet=use_telnet, con_telnet=con_telnet,
    #                                     availability=HostAvailState.AVAILABLE):
    #             err_msg = "Failed to wait for host to reach Available state after unlocked to Degraded state"
    #             LOG.warning(err_msg)
    #             return 8, err_msg
    #
    # LOG.info("Host {} is successfully unlocked and in available state".format(host))
    # return 0, "Host is unlocked and in available state."


def enter_bios_option(node_obj, bios_option, reboot=False, expect_prompt=True):
    if node_obj.telnet_conn is None and not expect_prompt:
        node_obj.telnet_conn = open_telnet_session(node_obj)

    if reboot:
        vlm_helper.power_off_hosts(node_obj.name)
        power_on_host(node_obj.name, wait_for_hosts_state_=False)

    if expect_prompt:
        node_obj.telnet_conn.expect([re.compile(bios_option.name.encode(), re.IGNORECASE)], 360)

    for i in range(3):
        bios_option.enter(node_obj.telnet_conn)
        time.sleep(1)


def select_boot_device(node_obj, boot_device_menu, boot_device_dict, usb=None, fail_ok=False, boot_device_pattern=None,
                       expect_prompt=True):
    # if usb is None:
    #     usb = "burn" in InstallVars.get_install_var("BOOT_TYPE") or "usb" in InstallVars.get_install_var("BOOT_TYPE")
    if boot_device_pattern:
        boot_device_regex = boot_device_pattern
    elif usb:
        LOG.info("Looking for USB device")
        boot_device_regex = "USB|Kingston|JetFlash|SanDisk|Verbatim"
    else:
        boot_device_regex = next((value for key, value in boot_device_dict.items()
                                  if key == node_obj.name or key == node_obj.personality), None)
    if boot_device_regex is None:
        msg = "Failed to determine boot device for: " + node_obj.name
        LOG.error(msg)
        if fail_ok:
            return False
        else:
            raise exceptions.TelnetError(msg)
    LOG.info("Boot device is: " + str(boot_device_regex))

    if expect_prompt:
        node_obj.telnet_conn.expect([boot_device_menu.get_prompt()], 60)
    boot_device_menu.select(node_obj.telnet_conn, pattern=re.compile(boot_device_regex))


def select_install_option(node_obj, boot_menu, index=None, low_latency=False, security="standard", usb=None,
                          small_footprint=False, expect_prompt=True):
    type = "cpe" if small_footprint else "standard"
    if low_latency:
        type = "lowlat"
    tag = {"os": "centos", "security": security, "type": type, "console": "serial"}
    if index:
        index = index if isinstance(index, list) else [index]

    if expect_prompt:
        node_obj.telnet_conn.expect([boot_menu.get_prompt()], 120)
    boot_type = InstallVars.get_install_var("BOOT_TYPE")
    curser_move = 1
    if boot_type != 'feed':
        curser_move = 2 if "wolfpass" in node_obj.host_name or node_obj.host_name in NODES_WITH_KERNEL_BOOT_OPTION_SPACING\
            else 1
    boot_menu.select(telnet_conn=node_obj.telnet_conn, index=index[0] if index else None,
                     tag=tag if not index else None, curser_move=curser_move)
    time.sleep(2)

    if boot_menu.sub_menus:
        sub_menu_prompts = list([sub_menu.prompt for sub_menu in boot_menu.sub_menus])

        try:
            sub_menus_navigated = 0

            while len(sub_menu_prompts) > 0:
                LOG.info("submenu prompt = {}".format(sub_menu_prompts))
                prompt_index = node_obj.telnet_conn.expect(sub_menu_prompts, 5, fail_ok=True)
                LOG.info("submenu index = {}".format(prompt_index))
                sub_menu = boot_menu.sub_menus[prompt_index + sub_menus_navigated]
                LOG.info("submenu  {}".format(sub_menu.name))
                if sub_menu.name == "Controller Configuration":
                    sub_menu.find_options(node_obj.telnet_conn, option_identifier=sub_menu.option_identifier.encode())
                    LOG.info("Selecting for  {}".format(sub_menu.name))
                    sub_menu.select(node_obj.telnet_conn, index=index[sub_menus_navigated + 1] if index else None,
                                    pattern="erial" if not index else None)
                    time.sleep(5)

                elif sub_menu.name == "Console":

                    # sub_menu.find_options(node_obj.telnet_conn, option_identifier=b'\x1b.*([\w]+\s)+\s+',
                    #                       end_of_menu=b"Standard Security Profile Enabled (default setting)",
                    #                       newline=b'(\x1b\[\d+;\d+H)+')
                    sub_menu.find_options(node_obj.telnet_conn, option_identifier=sub_menu.option_identifier.encode())
                    LOG.info("Selecting for  {}".format(sub_menu.name))
                    sub_menu.select(node_obj.telnet_conn, index=index[sub_menus_navigated + 1] if index else None,
                                    pattern=security.upper() if not index else None)
                else:
                    LOG.info("Selecting for  unknown")
                    boot_menu.select(telnet_conn=node_obj.telnet_conn, index=index[sub_menus_navigated + 1] if index else None,
                                     tag=tag if not index else None)
                sub_menu_prompts.pop(prompt_index)
                sub_menus_navigated += 1
        except exceptions.TelnetTimeout:
            pass
        except IndexError:
            LOG.error("Not enough indexes were given for the menu. {} indexes was given for {} amount of menus".format(
                str(len(index)), str(len(boot_menu.sub_menus + 1))))
            raise


    # if index:
    #     index = None
    # pattern = None
    # while option.sub_menu is not None:
    #     sub_menu_prompt = option.sub_menu.prompt
    #     LOG.info("Submenu prompt: {} sub_menu {}".format(sub_menu_prompt, option.sub_menu.name))
    #
    #     try:
    #
    #         node_obj.telnet_conn.expect(sub_menu_prompt.encode(), 60)
    #         if 'Console' in option.sub_menu.name:
    #             LOG.info("Console sub menu output: {}".format(node_obj.telnet_conn.cmd_output.encode()))
    #         option.sub_menu.find_options(node_obj.telnet_conn, option_identifier=b'([\w]+\s)+\s+> ',
    #                                      end_of_menu=b'(\x1b\[01;00H){1,}',
    #                                      newline=b'(\x1b\[\d+;\d+H)+')
    #         LOG.info("Submenu Options : {}".format(option.sub_menu.options))
    #         if "Controller Configuration" in option.sub_menu.name:
    #             pattern = "erial"
    #             LOG.info("Controller configuration On submenu {}".format(option.sub_menu.name))
    #         elif "Console" in option.sub_menu.name:
    #             LOG.info("Console On submenu {}".format(option.sub_menu.name))
    #             pattern = security
    #         else:
    #             index = 0
    #             LOG.info("Unlknwon On submenu {}".format(option.sub_menu.name))
    #         option = option.sub_menu.select(node_obj.telnet_conn, index=index, pattern=pattern)
    #
    #     except exceptions.TelnetTimeout:
    #         pass
    #     except IndexError:
    #         LOG.error("Invalid index {} or pattern {} was given for the options sub menu {} "
    #                   .format(index, pattern,option.sub_menu.name))
    #         raise

    return 0


def install_node(node_obj, boot_device_dict, small_footprint=None, low_latency=None, security=None, usb=None,
                 pxe_host='controller-0'):
    bios_menu = menu.BiosMenu(lab_name=node_obj.host_name)
    bios_option = bios_menu.get_boot_option()
    boot_device_menu = menu.BootDeviceMenu()
    boot_device_regex = next((value for key, value in boot_device_dict.items()
                              if key == node_obj.name or key == node_obj.personality), None)
    boot_type = InstallVars.get_install_var("BOOT_TYPE")
    if boot_device_regex:
        uefi = "UEFI" in boot_device_regex or re.search("r\d+", node_obj.host_name)
    else:
        uefi = re.search("r\d+", node_obj.host_name) or "ml350" in node_obj.host_name

    if small_footprint is None:
        sys_type = ProjVar.get_var("SYS_TYPE")
        LOG.debug("SYS_TYPE: {}".format(sys_type))
        small_footprint = "AIO" in sys_type
    if low_latency is None:
        low_latency = InstallVars.get_install_var('LOW_LATENCY')
    if security is None:
        security = InstallVars.get_install_var("SECURITY")
    if usb is None and node_obj == 'controller-0':
        usb = "burn" in boot_type or "usb" in boot_type
    if usb:
        LOG.debug("creating USB boot menu")
        kickstart_menu = menu.USBBootMenu(host_name=node_obj.host_name)
    elif 'pxe_iso' in boot_type:
        LOG.debug("creating PXE ISO boot menu")
        kickstart_menu = menu.PXEISOBootMenu(host_name=node_obj.host_name)
    else:
        LOG.debug("creating {} boot menu".format("UEFI" if uefi else "PXE"))
        kickstart_menu = menu.KickstartMenu(uefi=uefi)
    if node_obj.telnet_conn is None:
        node_obj.telnet_conn = open_telnet_session(node_obj)

    bios_boot_option = bios_option.name.encode()
    telnet_conn = node_obj.telnet_conn
    LOG.info('Waiting for BIOS boot option: {}'.format(bios_boot_option))
    telnet_conn.expect([re.compile(bios_boot_option, re.IGNORECASE)], 300)
    enter_bios_option(node_obj, bios_option, expect_prompt=False)
    LOG.info('BIOS option entered')

    expt_prompts = [boot_device_menu.prompt]
    if node_obj.name == pxe_host:
        expt_prompts.append(kickstart_menu.prompt)

    index = telnet_conn.expect(expt_prompts, 360)
    if index == 0:
        LOG.info('In boot device menu')
        select_boot_device(node_obj, boot_device_menu, boot_device_dict, usb=usb, expect_prompt=False)
        LOG.info('Boot device selected')

        expt_prompts.pop(0)
        if node_obj.name == pxe_host:
            # expt_prompts.append("(\x1b\[0;1;36;44m\s{45,60})")
            expt_prompts.append("\x1b.*\*{56,60}")
        if len(expt_prompts) > 0:
            LOG.info('In Kickstart menu expected promts = {}'.format(expt_prompts))

            telnet_conn.read_until(kickstart_menu.prompt)
            #ind = telnet_conn.expect(expt_prompts, 360)
            #LOG.info('In Kickstart menu index = {}'.format(ind))
            #time.sleep(2)
            select_install_option(node_obj, kickstart_menu, small_footprint=small_footprint, low_latency=low_latency,
                                  security=security, usb=usb, expect_prompt=False)
    LOG.info('Kick start option selected')

    LOG.info("Waiting for {} to boot".format(node_obj.name))
    node_obj.telnet_conn.expect([str.encode("ogin:")], 2400)
    LOG.info("Found login prompt. {} installation has completed".format(node_obj.name))


def burn_image_to_usb(iso_host, iso_full_path=None, lab_dict=None, boot_lab=True, fail_ok=False, close_conn=False):
    if lab_dict is None:
        lab_dict = InstallVars.get_install_var("LAB")
    if 'controller-0' not in lab_dict.keys():
        raise ValueError("The Lab controller-0 node object must be provided")
    if iso_full_path is None:
        iso_full_path = InstallVars.get_install_var("ISO_PATH")

    iso_dest_path = WRSROOT_HOME + os.path.basename(iso_full_path)
    dest_lab_name = lab_dict['short_name']
    controller0_node = lab_dict['controller-0']

    LOG.info("Transferring boot image iso file to lab: {}".format(dest_lab_name))
    if local_client().ping_server(controller0_node.host_ip, fail_ok=True)[0] == 100:
        msg = "The destination lab {} controller-0 is not reachable.".format(dest_lab_name)
        if boot_lab:
            LOG.info("{}. Attempting to boot lab {}:controller-0".format(msg, dest_lab_name))
            boot_controller(lab=lab_dict)
            if local_client().ping_server(controller0_node.host_ip, fail_ok=fail_ok)[0] == 100:
                err_msg = "Cannot ping destination lab {} controller-0 after boot".format(dest_lab_name)
                LOG.warn(err_msg)
                return 1, err_msg

            LOG.info("Lab {}: controller-0  booted successfully".format(dest_lab_name))
        else:
            LOG.warn(msg)
            if fail_ok:
                return 1, msg
            else:
                raise exceptions.BackupSystem(msg)

    cmd = "test -f " + iso_full_path
    assert iso_host.ssh_conn.exec_cmd(cmd)[0] == 0, 'image not found in {}:{}'.format(iso_host.name, iso_full_path)
    node_ssh = controller0_node.ssh_conn
    if node_ssh is None:
        node_ssh = SSHClient(lab_dict['controller-0 ip'], initial_prompt=".*\$ ")
        node_ssh.connect(retry=True, retry_timeout=30)
        close_conn = True

    node_ssh.exec_cmd("ls")
    # Burn the iso image file to USB
    usb_device = get_usb_device_name(con_ssh=node_ssh)

    if usb_device:
        LOG.info("Burning the system cloned image iso file to usb flash drive {}".format(usb_device))

        iso_host.ssh_conn.rsync(iso_full_path, controller0_node.host_ip, iso_dest_path,
                                dest_user=HostLinuxCreds.get_user(), dest_password=HostLinuxCreds.get_password(),
                                timeout=600,)

        # Write the ISO to USB
        cmd = "echo {} | sudo -S dd if={} of=/dev/{} bs=1M oflag=direct; sync"\
            .format(HostLinuxCreds.get_password(), iso_dest_path, usb_device)

        rc,  output = node_ssh.exec_cmd(cmd, expect_timeout=900)
        if rc != 0:
            err_msg = "Failed to copy the cloned image iso file to USB {}: {}".format(usb_device, output)
            LOG.info(err_msg)
            if fail_ok:
                return 3, err_msg
            else:
                raise exceptions.BackupSystem(err_msg)

        LOG.info(" The cloned image iso file copied to USB: {}".format(output))

        LOG.info("Deleting system cloned image iso file from the dest lab folder ")
        node_ssh.exec_sudo_cmd("rm -f {}".format(iso_dest_path, expect_timeout=120))

        LOG.info("Cloned image iso file transfer to dest lab {} completed successfully".format(lab_dict['short_name']))

    else:
        err_msg = "No USB device found in destination lab {}".format(dest_lab_name)
        LOG.info(err_msg)
        if fail_ok:
            return 4, err_msg
        else:
            raise exceptions.BackupSystem(err_msg)

    if close_conn:
        node_ssh.close()

    return 0, None


def rsync_image_to_boot_server(iso_host, iso_full_path=None, lab_dict=None, fail_ok=False):
    if iso_full_path is None:
        iso_full_path = InstallVars.get_install_var("ISO_PATH")
    if lab_dict is None:
        lab_dict = InstallVars.get_install_var("LAB")
    barcode = lab_dict["controller_nodes"][0]
    iso_dest_path = "/tmp/iso/{}/bootimage.iso".format(barcode)
    tuxlab_server = InstallVars.get_install_var("BOOT_SERVER")
    tuxlab_prompt = '{}@{}\:(.*)\$ '.format(SvcCgcsAuto.USER, tuxlab_server)

    tuxlab_conn = establish_ssh_connection(tuxlab_server, user=SvcCgcsAuto.USER, password=SvcCgcsAuto.PASSWORD,
                                           initial_prompt=tuxlab_prompt)
    tuxlab_conn.deploy_ssh_key()

    LOG.info("Transferring boot image iso file to boot server: {}".format(tuxlab_server))
    if local_client().ping_server(tuxlab_server, fail_ok=fail_ok) == 100:
        msg = "{} is not reachable.".format(tuxlab_server)
        LOG.warn(msg)
        return 1, msg

    cmd = "rm -rf /tmp/iso/{}; mkdir -p /tmp/iso/{}; sudo chmod -R 777 /tmp/iso/".format(barcode, barcode)
    tuxlab_conn.exec_sudo_cmd(cmd)

    cmd = "test -f " + iso_full_path
    assert iso_host.ssh_conn.exec_cmd(cmd)[0] == 0, 'image not found in {}:{}'.format(iso_host.name, iso_full_path)
    iso_host.ssh_conn.rsync(iso_full_path, tuxlab_server, iso_dest_path, timeout=InstallTimeout.INSTALL_LOAD,
                            dest_user=SvcCgcsAuto.USER, dest_password=SvcCgcsAuto.PASSWORD)
    tuxlab_conn.close()
    return 0, None


def mount_boot_server_iso(lab_dict=None, tuxlab_conn=None):
    if lab_dict is None:
        lab_dict = InstallVars.get_install_var("LAB")
    barcode = lab_dict["controller_nodes"][0]
    tuxlab_server = InstallVars.get_install_var("BOOT_SERVER")
    tuxlab_prompt = '{}@{}\:(.*)\$ '.format(SvcCgcsAuto.USER, tuxlab_server)

    if not tuxlab_conn:
        tuxlab_conn = establish_ssh_connection(tuxlab_server, user=SvcCgcsAuto.USER, password=SvcCgcsAuto.PASSWORD,
                                               initial_prompt=tuxlab_prompt)
        tuxlab_conn.deploy_ssh_key()

    cmd = "chmod -R 777 /tmp/iso/{}".format(barcode)
    tuxlab_conn.exec_sudo_cmd(cmd, fail_ok=False)
    cmd = "umount /media/iso/{}; echo if we fail we ignore it".format(barcode)
    tuxlab_conn.exec_sudo_cmd(cmd, fail_ok=False)
    cmd = "rm -rf /media/iso/{}".format(barcode)
    tuxlab_conn.exec_sudo_cmd(cmd, fail_ok=False)
    cmd = "mkdir -p /media/iso/{}".format(barcode)
    tuxlab_conn.exec_cmd(cmd, fail_ok=False)
    cmd = "mount -o loop /tmp/iso/{}/bootimage.iso /media/iso/{}".format(barcode, barcode)
    tuxlab_conn.exec_sudo_cmd(cmd, fail_ok=False)
    cmd = "mount -o remount,exec,dev /media/iso/{}".format(barcode)
    tuxlab_conn.exec_sudo_cmd(cmd, fail_ok=False)
    cmd = "rm -rf /export/pxeboot/pxeboot.cfg/{}".format(barcode)
    tuxlab_conn.exec_sudo_cmd(cmd, fail_ok=False)
    cmd = "/media/iso/{}/pxeboot_setup.sh -u http://128.224.150.110/umalab/{} -t /export/pxeboot/pxeboot.cfg/{}".format(
        barcode, barcode, barcode)
    tuxlab_conn.exec_cmd(cmd, fail_ok=False)
    cmd = "umount /media/iso/{}".format(barcode)
    tuxlab_conn.exec_sudo_cmd(cmd, fail_ok=False)

    tuxlab_conn.close()

    return 0, None


def set_up_feed_from_boot_server_iso(server, lab_dict=None,  tuxlab_conn=None, iso_path=None, skip_cfg=False):

    if lab_dict is None:
        lab_dict = InstallVars.get_install_var("LAB")
    if iso_path is None:
        iso_path = InstallVars.get_install_var("ISO_PATH")
    barcode = lab_dict["controller_nodes"][0]

    tuxlab_server = InstallVars.get_install_var("BOOT_SERVER")
    tuxlab_prompt = '{}@{}\:(.*)\$ '.format(SvcCgcsAuto.USER, tuxlab_server)

    if not tuxlab_conn:
        tuxlab_conn = establish_ssh_connection(tuxlab_server, user=SvcCgcsAuto.USER, password=SvcCgcsAuto.PASSWORD,
                                               initial_prompt=tuxlab_prompt)
        tuxlab_conn.deploy_ssh_key()

     # connect to test server to mount USB iso
    test_server_attr = dict()
    test_server_attr['name'] = SvcCgcsAuto.HOSTNAME.split('.')[0]
    test_server_attr['server_ip'] = SvcCgcsAuto.SERVER
    test_server_attr['prompt'] = r'\[{}@{} {}\]\$ '\
        .format(SvcCgcsAuto.USER, test_server_attr['name'], SvcCgcsAuto.USER)

    test_server_conn = establish_ssh_connection(test_server_attr['name'], user=SvcCgcsAuto.USER,
                                                password=SvcCgcsAuto.PASSWORD,
                                                initial_prompt=test_server_attr['prompt'])

    test_server_conn.set_prompt(test_server_attr['prompt'])
    test_server_conn.deploy_ssh_key(get_ssh_public_key())
    test_server_attr['ssh_conn'] = test_server_conn
    test_server_obj = Server(**test_server_attr)
    media_iso_path = "/media/iso/{}".format(barcode)
    temp_iso_path = "/tmp/iso/{}".format(barcode)
    if test_server_conn.exec_cmd("test -f {}".format(temp_iso_path)) == 0:
        test_server_conn.exec_sudo_cmd("rm -rf {}/*".format(temp_iso_path))
    else:
        test_server_conn.exec_sudo_cmd("mkdir -p {}".format(temp_iso_path))
        test_server_conn.exec_sudo_cmd("chmod -R 777 {}".format(temp_iso_path), fail_ok=False)

    pre_opts = 'sshpass -p "{0}"'.format(SvcCgcsAuto.PASSWORD)
    server.ssh_conn.rsync(iso_path, test_server_obj.server_ip, temp_iso_path,
                          dest_user=SvcCgcsAuto.USER, dest_password=SvcCgcsAuto.PASSWORD,
                          extra_opts=["--delete", "--force", "--chmod=Du=rwx"], pre_opts=pre_opts,
                          timeout=InstallTimeout.INSTALL_LOAD)

    cmd = "umount {}; echo if we fail we ignore it".format(media_iso_path)
    test_server_conn.exec_sudo_cmd(cmd, fail_ok=True)
    cmd = "rm -rf {}".format(media_iso_path)
    test_server_conn.exec_sudo_cmd(cmd, fail_ok=False)
    cmd = "mkdir -p {}".format(media_iso_path)
    test_server_conn.exec_sudo_cmd(cmd, fail_ok=False)
    cmd = "mount -o loop {}/bootimage.iso {}".format(temp_iso_path, media_iso_path)
    test_server_conn.exec_sudo_cmd(cmd, fail_ok=False)

    controller0 = lab_dict["controller-0"]
    LOG.info("Set feed for {} network boot".format(barcode))
    tuxlab_sub_dir = SvcCgcsAuto.USER + '/' + os.path.basename(iso_path.split('/outputs')[0])

    tuxlab_barcode_dir = TUXLAB_BARCODES_DIR + str(controller0.barcode)

    if tuxlab_conn.exec_cmd("cd " + tuxlab_barcode_dir)[0] != 0:
        msg = "Failed to cd to: " + tuxlab_barcode_dir
        LOG.error(msg)
        return False

    feed_path = tuxlab_barcode_dir + "/" + tuxlab_sub_dir
    LOG.info("Copy load into {}".format(feed_path))
    tuxlab_conn.exec_cmd("mkdir -p " + tuxlab_sub_dir)
    tuxlab_conn.exec_cmd("chmod 755 " + tuxlab_sub_dir)

    cfg_link = tuxlab_conn.exec_cmd("readlink pxeboot.cfg")[1]
    if cfg_link != "pxeboot.cfg.gpt":
        LOG.info("Changing pxeboot.cfg symlink to pxeboot.cfg.gpt")
        tuxlab_conn.exec_cmd("ln -s pxeboot.cfg.gpt pxeboot.cfg")

    # LOG.info("Installing Centos load to feed path: {}".format(feed_path))
    # bld_server_conn.exec_cmd("cd " + load_path)

    test_server_conn.rsync(media_iso_path + "/", tuxlab_server, feed_path,
                          dest_user=SvcCgcsAuto.USER, dest_password=SvcCgcsAuto.PASSWORD,
                          extra_opts=["--delete", "--force", "--chmod=Du=rwx"], pre_opts=pre_opts,
                          timeout=InstallTimeout.INSTALL_LOAD)

    LOG.info("Updating pxeboot kickstart files")
    update_pxeboot_ks_files(lab_dict, tuxlab_conn, feed_path)

    LOG.info("Create new symlink to {}".format(feed_path))
    if tuxlab_conn.exec_cmd("rm -f feed")[0] != 0:
        msg = "Failed to remove feed"
        LOG.error(msg)
        return False

    if tuxlab_conn.exec_cmd("ln -s " + tuxlab_sub_dir + "/" + " feed")[0] != 0:
        msg = "Failed to set VLM target {} feed symlink to: " + tuxlab_sub_dir
        LOG.error(msg)
        return False

    tuxlab_conn.close()

    cmd = "umount {}".format(media_iso_path)
    test_server_conn.exec_sudo_cmd(cmd, fail_ok=False)
    LOG.info("Deleting the bootimage.iso from /tmp/iso/{}".format(barcode))
    test_server_conn.exec_sudo_cmd("rm -f /tmp/iso/{}/*.iso".format(barcode), fail_ok=False)

    test_server_conn.close()

    return 0, None


def update_pxeboot_ks_files(lab, tuxlab_conn, feed_path):

    controller0_node = lab['controller-0']
    lab_name = controller0_node.host_name
    LOG.info("Controller-0 node name is {}".format(lab_name))
    if re.search("\-0\d$", lab_name):
        lab_name = lab_name.replace('-0', '-')
    LOG.info("Controller-0 node name is {}".format(lab_name))
    base_url = "http://128.224.151.254/umalab/{}_feed".format(lab_name)
    tuxlab_conn.exec_cmd("chmod 755 {}/*.cfg".format(feed_path), fail_ok=False)

    cmd = '''
        sed -i "s#xxxHTTP_URLxxx#{}#g;s#xxxHTTP_URL_PATCHESxxx#{}/patches#g;s#NUM_DIRS#2#g" {}/pxeboot/*.cfg'''\
        .format( base_url, base_url, feed_path)

    tuxlab_conn.exec_cmd(cmd, fail_ok=False)
    cmd = "cp {}/pxeboot/pxeboot_controller.cfg {}/yow-tuxlab2_controller.cfg".format(feed_path, feed_path)
    tuxlab_conn.exec_cmd(cmd, fail_ok=False)
    cmd = "cp {}/pxeboot/pxeboot_smallsystem.cfg {}/yow-tuxlab2_smallsystem.cfg".format(feed_path, feed_path)
    tuxlab_conn.exec_cmd(cmd, fail_ok=False)
    cmd = "cp {}/pxeboot/pxeboot_smallsystem_lowlatency.cfg {}/yow-tuxlab2_smallsystem_lowlatency.cfg"\
        .format(feed_path, feed_path)
    tuxlab_conn.exec_cmd(cmd, fail_ok=False)


def setup_heat(con_ssh=None, telnet_conn=None, fail_ok=True, yaml_files=None):
    if con_ssh:
        connection = con_ssh
    elif telnet_conn:
        connection = telnet_conn
    else:
        connection = ControllerClient.get_active_controller()
    if yaml_files is None:
        yaml_files = [WRSROOT_HOME + "lab_setup-admin-resources.yaml",
                      WRSROOT_HOME + "lab_setup-tenant1-resources.yaml",
                      WRSROOT_HOME + "lab_setup-tenant2-resources.yaml",]
    expected_files = [WRSROOT_HOME + ".heat_resources", WRSROOT_HOME + "launch_stacks.sh"] + yaml_files

    for file in expected_files:
        if not connection.file_exists(file):
            err_msg = "{} not found".format(file)
            LOG.warning(err_msg)
            assert fail_ok, err_msg
            return 1, err_msg

    cmd = WRSROOT_HOME + "./create_resource_stacks.sh"
    rc, output = connection.exec_cmd(cmd, fail_ok=fail_ok)
    if rc != 0:
        err_msg = "Failure when creating resource stacks skipping heat setup"
        LOG.warning(err_msg)
        return 2, err_msg

    connection.exec_cmd("chmod 755 /home/wrsroot/launch_stacks.sh", fail_ok=fail_ok)
    connection.exec_cmd(WRSROOT_HOME + "launch_stacks.sh lab_setup.conf", fail_ok=fail_ok)
    rc, output = connection.exec_cmd(cmd)
    if rc != 0:
        err_msg = "Heat stack launch failed"
        LOG.warning(err_msg)
        return 2, err_msg

    return 0, output


def is_valid_builds_dir_name(dir_name):
        return hasattr(BuildServerPath.BldsDirNames, dir_name.upper().replace('.', '_') if dir_name else '')


def get_default_latest_build_path(version=None, builds_dir_name=None):

    if builds_dir_name and not is_valid_builds_dir_name(builds_dir_name):
        raise ValueError(" The  builds dir name {} is not valid".format(builds_dir_name))

    path = None
    if version is None and builds_dir_name is None:
        raise ValueError("Either version or tis_build_dir must be specified")

    elif builds_dir_name:
        path = os.path.join(BuildServerPath.DEFAULT_WORK_SPACE, builds_dir_name, BuildServerPath.LATEST_BUILD)

    elif version:
        paths = BuildServerPath.LATEST_HOST_BUILD_PATHS[version]
        if paths is not None and isinstance(paths, list):
            path = paths[0]
        else:
            path = paths

    LOG.info("The default path to latest build: {}".format(path))
    return path


def get_default_lab_config_files_path(builds_dir_name):
    """
    Gets the path for lab configuration files in default build server
    Args:
        builds_dir_name (str): indicates the builds dir name like Titanium_R6_build, StarlingX_18.10, etc.

    Returns:

    """
    if is_valid_builds_dir_name(builds_dir_name):
        LOG.info("Getting the default path for {} builds".format(builds_dir_name))
        sys_version = ProjVar.get_var('SW_VERSION')

        if not sys_version:
            sys_version = extract_software_version_from_string_path(builds_dir_name)
        else:
            sys_version = sys_version[0]

        sys_version = sys_version if sys_version in BuildServerPath.DEFAULT_LAB_CONFIG_PATH_EXTS else 'default'
        return os.path.join(get_default_latest_build_path(version=sys_version, builds_dir_name=builds_dir_name),
                            BuildServerPath.DEFAULT_LAB_CONFIG_PATH_EXTS[sys_version]) if sys_version else None
    else:
        raise ValueError(" The  builds dir name {} is not valid".format(builds_dir_name))


def extract_software_version_from_string_path(path):

    version = None
    if path:
        if re.compile(BuildServerPath.BldsDirNames.R2_VERSION_SEARCH_REGEX).search(path):
            version = '15.12'
        elif re.compile(BuildServerPath.BldsDirNames.R3_VERSION_SEARCH_REGEX).search(path):
            version = '16.10'
        elif re.compile(BuildServerPath.BldsDirNames.R4_VERSION_SEARCH_REGEX).search(path):
            version = '17.06'
        elif re.compile(BuildServerPath.BldsDirNames.R5_VERSION_SEARCH_REGEX).search(path):
            version = '18.03'
        elif re.compile(BuildServerPath.BldsDirNames.R6_VERSION_SEARCH_REGEX).search(path):
            version = 'default'

    LOG.info("Version extracted from {} is {}".format(path, version))
    return version


def is_simplex(lab):
     if not lab:
         lab = InstallVars.get_install_var("LAB")
     if 'system_mode' in lab:
         return lab['system_mode'] == 'simplex'
     else:
         return len(lab['controller_nodes']) == 1


def copy_files_to_subcloud(subcloud):
    dc_lab = InstallVars.get_install_var("LAB")
    lab = dc_lab[subcloud]
    central_lab = dc_lab['central_region']
    central_controller0_node = central_lab['controller-0']
    if not central_controller0_node.ssh_conn:
        central_controller0_node.ssh_conn = establish_ssh_connection(central_controller0_node.host_ip)

    subcloud_controller_node = lab['controller-0']

    if not subcloud_controller_node.ssh_conn:
        subcloud_controller_node.ssh_conn = establish_ssh_connection(subcloud_controller_node.host_ip)

    pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.get_password())

    central_controller0_node.ssh_conn.rsync(WRSROOT_HOME + "*.conf",
                          subcloud_controller_node.host_ip,
                          WRSROOT_HOME, pre_opts=pre_opts)



def run_config_subcloud(subcloud, con_ssh=None, lab=None, fail_ok=True):


    if not lab:
        lab = InstallVars.get_install_var("LAB")

    if not con_ssh:
        subcloud_controller_node = lab['controller-0']
        if subcloud_controller_node.ssh_conn:
            con_ssh = subcloud_controller_node.ssh_conn
        else:
            subcloud_controller_node.ssh_conn = establish_ssh_connection(subcloud_controller_node.host_ip)
            con_ssh = subcloud_controller_node.ssh_conn

    subcloud_config = subcloud.replace('-', '') + '.config'

    cmd = "test -e {}/{}".format(WRSROOT_HOME, subcloud_config)
    rc = con_ssh.exec_cmd(cmd, fail_ok=fail_ok)[0]
    if rc != 0:
        msg = "The subcloud config file {}  missing from active controller".format(subcloud_config)
        return rc, msg

    cmd = "config_subcloud {}".format(subcloud_config)
    rc, msg = con_ssh.exec_sudo_cmd(cmd, expect_timeout=InstallTimeout.CONFIG_CONTROLLER_TIMEOUT)
    if rc != 0:
        msg = " {} run failed: {}".format(subcloud_config, msg)
        LOG.warning(msg)
        return rc, msg
    # con_ssh.set_prompt()
    return 0, "{} run successfully".format(subcloud_config)


def get_host_install_uuid(host, host_ssh, lab=None):
    if lab is None:
        lab = InstallVars.get_install_var('LAB')
    if host_ssh is None:
        raise ValueError("Host ssh client connection must be provided")

    if host_ssh.exec_cmd("test -f {}".format(PLATFORM_CONF_PATH))[0] != 0:
        msg = "The {} file is missing in host {}".format(PLATFORM_CONF_PATH, host)
        raise exceptions.InstallError(msg)
    cmd = 'cat {}'.format(PLATFORM_CONF_PATH)
    exitcode, output = host_ssh.exec_cmd(cmd, rm_date=True)
    if exitcode != 0:
        raise exceptions.SSHExecCommandFailed("Command {} failed to execute.".format(cmd))

    install_uuid_line = [l for l in output.splitlines() if "INSTALL_UUID" in l]
    if len(install_uuid_line) == 0:
        raise exceptions.InstallError("The install uuid does not exist in {} file: {}"
                                      .format(PLATFORM_CONF_PATH, output))
    install_uuid = install_uuid_line[0].split("=")[1].strip()
    LOG.info("The install uuid from host {} is {}".format(host, install_uuid))
    return install_uuid


def reset_telnet_port(telnet_conn):
    telnet_conn.send_control("\\")
    index = telnet_conn.expect(["anonymous:.+:PortCommand> ", "Login:"], timeout=5)
    if index == 1:
        telnet_conn.write(b"\r\n")

    telnet_conn.send("resetport")
    telnet_conn.login()


def download_stx_helm_charts(lab, server, stx_helm_charts_path=None):
    """
    Downloads the stx helm charts from build server
    Args:
        lab:
        server:
        stx_helm_charts_path:

    Returns:

    """
    if lab is None or server is None:
        raise ValueError("The lab dictionary and build server object must be specified")

    if stx_helm_charts_path is None:
        stx_helm_charts_path = os.path.join(BuildServerPath.STX_HOST_BUILDS_DIR, BuildServerPath.LATEST_BUILD,
                                            BuildServerPath.STX_HELM_CHARTS)

    cmd = "test -e " + stx_helm_charts_path
    assert server.ssh_conn.exec_cmd(cmd, rm_date=False)[0] == 0, ' STX Helm charts path not found in {}:{}'.format(
            server.name, stx_helm_charts_path)

    pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.get_password())
    server.ssh_conn.rsync(stx_helm_charts_path + "/*.tgz",
                          lab['controller-0 ip'],
                          WRSROOT_HOME, pre_opts=pre_opts)
