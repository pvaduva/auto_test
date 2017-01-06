import os
from consts.proj_vars import ProjVar, InstallVars
from consts.auth import Host, SvcCgcsAuto
from consts.cgcs import HostAvailabilityState, Prompt
from utils import cli, table_parser, exceptions
from utils.tis_log import LOG
from keywords import system_helper, host_helper
from utils.ssh import SSHClient
from utils import telnet as telnetlib
from utils import local_host
import threading
from consts.filepaths import WRSROOT_HOME
from consts.timeout import HostTimeout
from contextlib import contextmanager
from consts.build_server import DEFAULT_BUILD_SERVER, BUILD_SERVERS



UPGRADE_LOAD_ISO_FILE = "bootimage.iso"
PUBLIC_SSH_KEY = local_host.get_ssh_key()

def get_current_system_version():
    return system_helper.get_system_software_version()


def check_system_health_for_upgrade():
    # system_helper.source_admin()
    return system_helper.get_system_health_query_upgrade()


def download_upgrade_license(lab, server, license_path):

    cmd = "test -h " + license_path
    assert server.ssh_conn.exec_cmd(cmd)[0] == 0,  'Upgrade license file not found in {}:{}'.format(
            server.name, license_path)

    pre_opts = 'sshpass -p "{0}"'.format(Host.PASSWORD)
    server.ssh_conn.rsync("-L " + license_path, lab['controller-0 ip'],
                          os.path.join(WRSROOT_HOME, "upgrade_license.lic"),
                          pre_opts=pre_opts)


def download_upgrade_load(lab, server, load_path):

    # Download licens efile
    cmd = "test -e " + load_path
    assert server.ssh_conn.exec_cmd(cmd, rm_date=False)[0] == 0,  'Upgrade build iso file not found in {}:{}'.format(
            server.name, load_path)
    iso_file_path = os.path.join(load_path, "export", UPGRADE_LOAD_ISO_FILE)
    pre_opts = 'sshpass -p "{0}"'.format(Host.PASSWORD)
    server.ssh_conn.rsync(iso_file_path,
                          lab['controller-0 ip'],
                          WRSROOT_HOME, pre_opts=pre_opts)


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


def open_vlm_console_thread(hostname):

    lab = InstallVars.get_install_var("LAB")
    node = lab[hostname]
    if node is None:
        err_msg = "Failed to get node object for hostname {} in the Install parameters".format(hostname)
        LOG.error(err_msg)
        raise exceptions.InvalidStructure(err_msg)

    output_dir = ProjVar.get_var('LOG_DIR')
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
    ''' Initiate the boot and installation operation.
    '''

    if len(boot_device) == 0:
        LOG.error("Cannot bring vlm console for {} without valid mgmt boot device: {}".format(node.name, boot_device))
        return 1

    if node.telnet_conn is None:
        node.telnet_conn = telnetlib.connect(node.telnet_ip,
                                             int(node.telnet_port),
                                             negotiate=node.telnet_negotiate,
                                             port_login=True if node.telnet_login_prompt else False,
                                             vt100query=node.telnet_vt100query,
                                             log_path=install_output_dir + "/"\
                                               + node.name + ".telnet.log")

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
    ''' Perform a wipedisk operation on the lab before booting a new load into
        it.
    '''

    if node.telnet_conn is None:
        node.telnet_conn = telnetlib.connect(node.telnet_ip, \
                                            int(node.telnet_port), \
                                            negotiate=node.telnet_negotiate,\
                                            vt100query=node.telnet_vt100query,\
                                            log_path=install_output_dir + "/"\
                                            + node.name + ".telnet.log", \
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
    node.telnet_conn.write_line(Host.PASSWORD)
    node.telnet_conn.get_read_until("[y/n]")
    node.telnet_conn.write_line("y")
    node.telnet_conn.get_read_until("confirm")
    node.telnet_conn.write_line("wipediskscompletely")
    node.telnet_conn.get_read_until("The disk(s) have been wiped.", HostTimeout.WIPE_DISK_TIMEOUT)

    LOG.info("Disk(s) have been wiped on: " + node.name)
    if close_telnet_conn:
        node.telnet_conn.close()



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

        rc, output = local_host.vlm_exec_cmd(local_host.VLM_TURNOFF. node.barcode)
        if rc != 0:
            err_msg = "Failed to power off nod {}  barcode {}: {}"\
                .format(node.name, node.barcode, output)
            LOG.error(err_msg)
            raise exceptions.InvalidStructure(err_msg)
        LOG.info("Node {} is turned off".format(node.name))

def power_on_host(hosts):

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

        rc, output = local_host.vlm_exec_cmd(local_host.VLM_TURNON. node.barcode)
        if rc != 0:
            err_msg = "Failed to power on node {}  barcode {}: {}"\
                .format(node.name, node.barcode, output)
            LOG.error(err_msg)
            raise exceptions.InvalidStructure(err_msg)
        LOG.info("Node {} is turned on".format(node.name))


    wait_for_hosts_state(hosts)

def wait_for_hosts_state(hosts, state=HostAvailabilityState.ONLINE):

    if len(hosts) > 0:
        locked_hosts_in_states = host_helper._wait_for_hosts_states(hosts,  availability=[state])
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
