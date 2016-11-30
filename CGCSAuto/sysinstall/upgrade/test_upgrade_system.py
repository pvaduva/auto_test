import os
import time
from utils.ssh import SSHClient
from utils import telnet as telnetlib
from consts.build_server import Server
from consts.proj_vars import ProjVar, InstallVars, UpgradeVars
from utils.tis_log import LOG
from keywords import system_helper, host_helper
from utils import local_host
import threading
from consts.build_server import get_build_server_info
from consts.cgcs import Prompt

# wrsroot user
WRSROOT_USERNAME = "wrsroot"
WRSROOT_DEFAULT_PASSWORD = WRSROOT_USERNAME
WRSROOT_PASSWORD = "Li69nux*"
WRSROOT_HOME_DIR = "/home/wrsroot"


UPGRADE_LOAD_ISO_FILE = "bootimage.iso"
PUBLIC_SSH_KEY = local_host.get_ssh_key()


def get_current_system_version():
    return system_helper.get_system_software_version()


def check_system_health_for_upgrade():
    # system_helper.source_admin()
    return system_helper.get_system_health_query_upgrade()


def test_system_upgrade():

    LOG.tc_func_start("UPGRADE_TEST")

    lab = InstallVars.get_install_var('LAB')
    license_path = UpgradeVars.get_upgrade_var('UPGRADE_LICENSE')
    bld_server = get_build_server_info(UpgradeVars.get_upgrade_var('BUILD_SERVER'))
    load_path = UpgradeVars.get_upgrade_var('TIS_BUILD_DIR')
    output_dir = ProjVar.get_var('LOG_DIR')
    upgrade_version = UpgradeVars.get_upgrade_var('UPGRADE_VERSION')
    current_version = get_current_system_version()

    bld_server_attr = {}
    bld_server_attr['name'] = bld_server['name']
    bld_server_attr['server_ip'] = bld_server['ip']
    bld_server_attr['prompt'] = '.*yow\-cgts[34]\-lx\:~\$ '

    bld_server_conn = SSHClient(bld_server_attr['name'], user=UpgradeVars.get_upgrade_var('USERNAME'),
                                password=UpgradeVars.get_upgrade_var('PASSWORD'), initial_prompt=".*\$ ")

    bld_server_conn.connect()
    bld_server_conn.exec_cmd("bash")
    bld_server_conn.set_prompt(bld_server_attr['prompt'])
    bld_server_conn.deploy_ssh_key(PUBLIC_SSH_KEY)
    bld_server_attr['ssh_conn'] = bld_server_conn

    bld_server_obj = Server(**bld_server_attr)


    # establish ssh connection with controller-0
    controller0_conn = SSHClient(lab['controller-0 ip'])
    controller0_conn.connect()

    # # get upgrade license file for release
    LOG.info("Dowloading the license {}:{} for target release {}".format(bld_server_obj.name,
                                                                         license_path, upgrade_version))
    download_upgrade_license(lab, bld_server_obj, license_path)

    LOG.tc_step("Checking if target release license is downloaded......")
    cmd = "test -e " + os.path.join(WRSROOT_HOME_DIR, "upgrade_license.lic")
    assert controller0_conn.exec_cmd(cmd)[0] == 0, "Upgrade license file not present in Controller-0"


    # get upgrade load iso file
    LOG.info("Dowloading the {} target release  load iso image file {}:{}".format(upgrade_version, bld_server_obj.name,
                                                                         license_path, load_path))
    download_upgrade_load(lab, bld_server_obj, load_path)
    upgrade_load_path = os.path.join(WRSROOT_HOME_DIR, UPGRADE_LOAD_ISO_FILE)

    LOG.tc_step("Checking if target release load is downloaded......")
    cmd = "test -e {}".format(upgrade_load_path)
    assert controller0_conn.exec_cmd(cmd)[0] == 0, "Upgrade build iso image file {} not present " \
                                                   "in Controller-0".format(upgrade_load_path)


    #Install the license file for release
    LOG.info("Installing the target release {} license file".format(upgrade_version))
    rc = install_upgrade_license(controller0_conn)
    LOG.tc_step("Checking if target release license is installed......")
    assert rc == 0, "Unable to install upgrade license file in Controller-0"

    # Run the load_import command to import the new release iso image build
    LOG.info("Importing the target release {} load iso file".format(upgrade_version))
    output = system_helper.import_load(upgrade_load_path, fail_ok=True)

    if output[0] != 0 and "Imported load exists." not in output[1].splitlines():
        assert False, "Unable to import upgrade release on Controller-0"

    # check if upgrade load software is imported successfully
    if output[0] == 0:
        ver = output[2]
    else:
        ver = (system_helper.get_imported_load_version()).pop()

    LOG.tc_step("Checking if target release load is imported......")
    assert upgrade_version in ver, "Import error. Expected " \
                                                     "version {} not found in imported load list" \
                                                     "{}".format(upgrade_version, ver)
    # Apply patches if required
    # TODO:

    # Check system health for upgrade
    rc, health = system_helper.get_system_health_query_upgrade()
    LOG.tc_step("Checking if system health is OK to start upgrade......")
    assert rc == 0, "System health query upgrade failed: {}".format(health)

    # run system upgrade-start
    # must be run in controller-0
    active_controller = system_helper.get_active_controller_name()
    LOG.tc_step("Checking if active controller is controller-0......")
    assert "controller-0" in active_controller, "The active controller is not " \
                                                "controller-0. Make controller-0 " \
                                                "active before starting upgrade"

    LOG.info("Starting upgrade from release {} to target release {}".format(current_version, upgrade_version))
    rc, output = system_helper.system_upgrade_start()
    LOG.tc_step("Checking if upgrade started successfully......")
    assert rc == 0, "system upgrade-start return error: {}".format(output)

    # upgrade standby controller
    LOG.info("Upgrading controller-1")
    rc, output = host_helper.host_upgrade("controller-1", fail_ok=True)
    LOG.tc_step("Checking if controller-1 is upgraded successfully......")
    assert rc == 0, "Failed to upgrade controller-1: {}".format(output)
    LOG.info("controller-1 is upgraded successfully")



    # Swact to standby controller-1
    LOG.info("Swacting to controller-1 .....")
    rc, output = host_helper.swact_host(hostname="controller-0", fail_ok=True)
    LOG.tc_step("Checking  if controller-1 has become active......")
    assert rc == 0, "Failed to swact: {}".format(output)

    active_controller = system_helper.get_active_controller_name()
    # Upgrade other hosts starting with controller-0
    hosts = system_helper.get_hostnames()
    hosts.remove(active_controller)

    controllers = [h for h in hosts if "controller" in h]
    controllers.sort()
    storages = [h for h in hosts if "storage" in h]
    storages.sort()
    computes = [h for h in hosts if "compute" in h]
    computes.sort()
    upgrade_hosts = controllers + storages + computes

    # upgrade  controller-0
    LOG.info("Starting upgrading  controller-0")

    controller0 = lab['controller-0']
    boot_device = get_mgmt_boot_device(controller0)
    LOG.info("Mgmt boot device for {} is {}".format(controller0.name, boot_device))

    LOG.info("Checking if  controller-0 is provisioned.....")
    if not host_helper.is_host_provisioned("controller-0"):
        LOG.info("controller-0 is not provisioned; Performing lock/unlock on controller-0.....")
        if (host_helper.lock_unlock_host("controller-0", fail_ok=True))[0] != 0:
            assert False, "Failed to lock/unlock controller-0"
        assert host_helper.is_host_provisioned("controller-0"), "controller-0 is still not provisioned" \
                                                                " after lock/unlock"

    # open vlm console for controller-0 for boot through mgmt interface
    LOG.info("Opening a vlm console for controller-0 .....")
    rc, output = local_host.reserve_vlm_console(controller0.barcode)
    if rc != 0:
        LOG.error("Failed to reserve vlm console for {}  barcode {}: {}"
                  .format(controller0.name, controller0.barcode, output))

    node_thread = threading.Thread(target=controller_console_up,
                                   name=controller0.name,
                                   args=(controller0, boot_device, output_dir))

    LOG.info("Starting thread for {}".format(node_thread.name))
    node_thread.start()

    rc, output = host_helper.host_upgrade("controller-0", fail_ok=True)

    LOG.tc_step("Checking  if controller-0 is upgraded successfully.....")
    assert rc == 0, "Failed to upgrade controller-0: {}".format(output)

    # upgrade  remaining hosts, if present
    upgrade_hosts.remove('controller-0')

    LOG.info("Starting upgrade of the other system hosts: {}".format(upgrade_hosts))

    rc, output = host_helper.hosts_upgrade(upgrade_hosts, fail_ok=True)
    LOG.tc_step("Checking  hosts {} are upgraded successfully.....".format(upgrade_hosts))
    assert rc == 0, "Failed to upgrade hosts: {}".format(output)

    # Activate the upgrade
    LOG.info("Activating upgrade")
    rc, ouput = system_helper.activate_upgrade()
    LOG.tc_step("Checking  if upgrade is activated.....")
    assert rc == 0, "Failed to activate upgrade"

    # Make controller-0 the active controller
    # Swact to standby controller-0
    LOG.info("Making controller-0 active")
    rc, output = host_helper.swact_host(hostname="controller-1", fail_ok=True)
    LOG.tc_step("Checking  if controller-0 has become active......")
    assert rc == 0, "Failed to swact: {}".format(output)

    # Complete upgrade
    LOG.info("Completing upgrade from  {} to {}".format(current_version, upgrade_version))
    rc, output = system_helper.complete_upgrade()
    LOG.tc_step("Checking  if upgrade is complete......")
    assert rc == 0, "Failed to complete upgrade: {}".format(output)

    LOG.info("Lab: {} upgraded successfully".format(lab['name']))


def download_upgrade_license(lab, server, license_path):

    cmd = "test -h " + license_path
    assert server.ssh_conn.exec_cmd(cmd)[0] == 0,  'Upgrade license file not found in {}:{}'.format(
            server.name, license_path)

    pre_opts = 'sshpass -p "{0}"'.format(WRSROOT_PASSWORD)
    server.ssh_conn.rsync("-L " + license_path, lab['controller-0 ip'],
                          os.path.join(WRSROOT_HOME_DIR, "upgrade_license.lic"),
                          pre_opts=pre_opts)


def download_upgrade_load(lab, server, load_path):

    # Download licens efile
    cmd = "test -e " + load_path
    assert server.ssh_conn.exec_cmd(cmd, rm_date=False)[0] == 0,  'Upgrade build iso file not found in {}:{}'.format(
            server.name, load_path)
    iso_file_path = os.path.join(load_path, "export", UPGRADE_LOAD_ISO_FILE)
    pre_opts = 'sshpass -p "{0}"'.format(WRSROOT_PASSWORD)
    server.ssh_conn.rsync(iso_file_path,
                          lab['controller-0 ip'],
                          WRSROOT_HOME_DIR, pre_opts=pre_opts)


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


def controller_console_up(node, boot_device, install_output_dir, close_telnet_conn=True):
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


def install_upgrade_license(controller0_conn, timeout=30):

    cmd = " sudo license-install " + os.path.join(WRSROOT_HOME_DIR, "upgrade_license.lic")
    controller0_conn.send(cmd)
    end_time = time.time() + timeout
    rc = 1
    while time.time() < end_time:
        index = controller0_conn.expect([controller0_conn.prompt, Prompt.PASSWORD_PROMPT, Prompt.Y_N_PROMPT], timeout=timeout)
        if index == 2:
            controller0_conn.send('y')

        if index == 1:
            controller0_conn.send(WRSROOT_PASSWORD)

        if index == 0:
            rc = controller0_conn.exec_cmd("echo $?")[0]
            break

    return rc




