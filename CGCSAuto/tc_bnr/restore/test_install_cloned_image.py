import re
import time

import pytest

from consts.auth import SvcCgcsAuto
from consts.build_server import Server, get_build_server_info
from consts.cgcs import HostAvailState, HostOperState, HostAdminState, Prompt
from consts.filepaths import BuildServerPath
from consts.proj_vars import InstallVars, ProjVar
from keywords import install_helper, host_helper, system_helper
from utils import node, local_host
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG


@pytest.fixture(scope='session')
def install_clone_setup():

    LOG.tc_func_start("CLONE_INSTALL_TEST")
    lab = InstallVars.get_install_var('LAB')
    LOG.info("Lab info; {}".format(lab))
    install_cloned_info = {'usb_verified': False,
                           'build_server': None,
                           'hostnames': [k for k, v in lab.items() if isinstance(v, node.Node)],
                           'system_mode': 'duplex' if len(lab['controller_nodes']) == 2 else "simplex"
                           }

    controller_node = lab['controller-0']
    controller_conn = None
    extra_controller_prompt = Prompt.TIS_NODE_PROMPT_BASE.format(lab['name'].split('_')[0]) + '|' + Prompt.CONTROLLER_0
    if local_host.ping_to_host(controller_node.host_ip):
        try:
            controller_conn = install_helper.establish_ssh_connection(controller_node.host_ip,
                                                              initial_prompt=extra_controller_prompt,  fail_ok=True)
        except:
            LOG.info("SSH connection to {} not yet avaiable yet ..".format(controller_node.name))

    if controller_conn:
        LOG.info("Connection established with controller-0 ....")
        ControllerClient.set_active_controller(ssh_client=controller_conn)
        if verify_usb(controller_conn):
            install_cloned_info['usb_verified'] = True

    bld_server = get_build_server_info(InstallVars.get_install_var('BUILD_SERVER'))

    LOG.info("Connecting to Build Server {} ....".format(bld_server['name']))
    bld_server_attr = dict()
    bld_server_attr['name'] = bld_server['name']
    bld_server_attr['server_ip'] = bld_server['ip']
    bld_server_attr['prompt'] = r'{}@{}\:(.*)\$ '.format(SvcCgcsAuto.USER, bld_server['name'])

    bld_server_conn = install_helper.establish_ssh_connection(bld_server_attr['name'], user=SvcCgcsAuto.USER,
                                password=SvcCgcsAuto.PASSWORD, initial_prompt=bld_server_attr['prompt'])

    bld_server_conn.exec_cmd("bash")
    bld_server_conn.set_prompt(bld_server_attr['prompt'])
    bld_server_conn.deploy_ssh_key(install_helper.get_ssh_public_key())
    bld_server_attr['ssh_conn'] = bld_server_conn
    bld_server_obj = Server(**bld_server_attr)

    install_cloned_info['build_server'] = bld_server_obj

    return install_cloned_info


def test_install_cloned_image(install_clone_setup):

    controller1 = 'controller-1'
    controller0 = 'controller-0'

    lab = InstallVars.get_install_var('LAB')
    install_output_dir = ProjVar.get_var('LOG_DIR')

    controller0_node = lab['controller-0']
    hostnames = install_clone_setup['hostnames']
    system_mode = install_clone_setup['system_mode']
    lab_name = lab['name']
    LOG.info("Starting install-clone on AIO lab {} .... ".format(lab_name))
    LOG.tc_step("Booting controller-0 ... ")

    if controller0_node.telnet_conn is None:
        controller0_node.telnet_conn = install_helper.open_telnet_session(controller0_node)
        try:
            controller0_node.telnet_conn.login()
        except:
            LOG.info("Telnet Login failed. Attempting to reset password")
            try:
                controller0_node.telnet_conn.login(reset=True)
            except:
                if controller0_node.telnet_conn:
                    controller0_node.telnet_conn.close()
                    controller0_node.telnet_conn = None

    if controller0_node.telnet_conn:
        install_helper.wipe_disk_hosts(hostnames,  close_telnet_conn=False)

    # power off hosts
    LOG.tc_step("Powring off system hosts ... ")
    install_helper.power_off_host(hostnames)

    install_helper.boot_controller(boot_usb=True, small_footprint=True, clone_install=True)

    # establish telnet connection with controller
    LOG.tc_step("Establishing telnet connection with controller-0 after install-clone ...")

    node_name_in_ini = '{}.*\~\$ '.format(controller0_node.host_name)
    normalized_name = re.sub(r'([^\d])0*(\d+)', r'\1\2', node_name_in_ini)

    # controller_prompt = Prompt.TIS_NODE_PROMPT_BASE.format(lab['name'].split('_')[0]) \
    #                     + '|' + Prompt.CONTROLLER_0 \
    #                     + '|{}'.format(node_name_in_ini) \
    #                     + '|{}'.format(normalized_name)

    if controller0_node.telnet_conn:
        controller0_node.telnet_conn.close()

    output_dir = ProjVar.get_var('LOG_DIR')
    controller0_node.telnet_conn = install_helper.open_telnet_session(controller0_node)
    controller0_node.telnet_conn.login()
    controller0_node.telnet_conn.exec_cmd("xterm")

    LOG.tc_step ("Verify install-clone status ....")
    install_helper.check_clone_status(tel_net_session=controller0_node.telnet_conn)

    LOG.info("Source Keystone user admin environment ...")

    #controller0_node.telnet_conn.exec_cmd("cd; source /etc/nova/openrc")

    LOG.tc_step ("Checking controller-0 hardware ....")
    install_helper.check_cloned_hardware_status('controller-0')

    if system_mode == 'duplex':
        LOG.tc_step("Booting controller-1 ... ")
        boot_interfaces = lab['boot_device_dict']
        install_helper.open_vlm_console_thread('controller-1', boot_interface=boot_interfaces, vlm_power_on=True,
                                               wait_for_thread=True)

        LOG.info("waiting for {} to boot ...".format(controller1))

        LOG.info("Verifying {} is Locked, Disabled and Online ...".format(controller1))
        host_helper.wait_for_hosts_states(controller1, check_interval=20, use_telnet=True,
                                          con_telnet=controller0_node.telnet_conn,
                                          administrative=HostAdminState.LOCKED,
                                          operational=HostOperState.DISABLED,
                                          availability=HostAvailState.ONLINE)

        LOG.info("Unlocking {} ...".format(controller1))

        rc, output = host_helper.unlock_host(controller1, use_telnet=True,
                                             con_telnet=controller0_node.telnet_conn)
        assert rc == 0, "Host {} unlock failed: {}".format(controller1, output)

        LOG.info("Host {} unlocked successfully ...".format(controller1))

        LOG.info("Host controller-1  booted successfully... ")

        LOG.tc_step ("Checking controller-1 hardware ....")
        install_helper.check_cloned_hardware_status(controller1)
    #
    LOG.tc_step ("Customizing the cloned system ....")
    LOG.info("Changing the OAM IP configuration ... ")
    install_helper.update_oam_for_cloned_system(system_mode=system_mode)

    LOG.tc_step ("Downloading lab specific license, config and scripts ....")
    software_version = system_helper.get_system_software_version()
    load_path = BuildServerPath.LATEST_HOST_BUILD_PATHS[software_version]
    install_helper.download_lab_config_files(lab, install_clone_setup['build_server'], load_path)

    LOG.tc_step ("Running lab cleanup to removed source attributes ....")
    install_helper.run_setup_script(script='lab_cleanup')

    LOG.tc_step ("Running lab setup script to upadate cloned system attributes ....")
    rc, output = install_helper.run_lab_setup()
    assert rc == 0, "Lab setup run failed: {}".format(output)

    time.sleep(30)
    LOG.tc_step ("Checking config status of controller-0 and perform lock/unlock if necessary...")
    if host_helper.get_hostshow_value('controller-0', 'config_status') == 'Config out-of-date':
        rc, output = host_helper.lock_unlock_controllers()
        assert rc == 0, "Failed to lock/unlock controller: {}".format(output)

    LOG.tc_step("Verifying system health after restore ...")
    system_helper.wait_for_all_alarms_gone(timeout=300)
    rc, failed = system_helper.get_system_health_query()
    assert rc == 0, "System health not OK: {}".format(failed)


def verify_usb(conn_ssh):

    if conn_ssh is None:
        conn_ssh = ControllerClient.get_active_controller()

    if conn_ssh:
        LOG.tc_step("Checking if a USB flash drive with cloned image file is plugged in... ")
        usb_device_name = install_helper.get_usb_device_name(con_ssh=conn_ssh)
        assert usb_device_name, "No USB found "

        LOG.tc_step("USB flash drive found, checking for cloned image iso file ... ")
        cmd = "mount | grep {}  | awk \' {{ print $3}}\'".format(usb_device_name + " ")
        mount_point = conn_ssh.exec_cmd(cmd)[1]
        if not mount_point:
            LOG.info("Mounting USB device to /media/wrsroot ....")
            install_helper.mount_usb(usb_device_name, mount="/media/wrsroot", con_ssh=conn_ssh)

        rc, output = conn_ssh.exec_sudo_cmd("ls /media/wrsroot")
        clone_files = ['boot.cat', 'clone-archive', 'install_clone']
        if rc == 0 and output:
            if all(f in output for f in clone_files):
                return True
            else:
                LOG.info("Plugged USB {} does not appear to contain cloned image iso file".format(usb_device_name))
                return False
    else:
        LOG.info(" SSH connection with controller-0 is not available; USB cannot be checked ....")
        return False
