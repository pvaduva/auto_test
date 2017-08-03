##############################
# OAM Network Firewall tests #
##############################
from keywords import host_helper, system_helper, common
from utils.tis_log import LOG
from utils import cli
from consts.cgcs import EventLogID
from pytest import skip
from consts.filepaths import TestServerPath, WRSROOT_HOME


def test_config_iptables_reboot():
    """
    Test iptables status after reboot of controller

    Test Steps:
        - Stop iptables service
        - Confirm iptables service has stopped
        - Reboot the controller being tested
        - Confirm iptables service is online
    """
    LOG.tc_step("Getting the controller(s)")
    controllers = system_helper.get_controllers()
    for controller in controllers:
        with host_helper.ssh_to_host(controller) as con_ssh:
            LOG.tc_step("Stopping iptables service")
            cmd = 'service iptables stop'
            con_ssh.exec_sudo_cmd(cmd)
            LOG.tc_step("checking iptables status")
            cmd = 'service iptables status'
            code, output = con_ssh.exec_sudo_cmd(cmd)
            assert 'Active: inactive' or 'Active: failed' in output, "iptables service did not stop running on host {}"\
                .format(controller)

        LOG.tc_step("Rebooting {}".format(controller))
        host_helper.reboot_hosts(controller)

        with host_helper.ssh_to_host(controller) as con_ssh:
            LOG.tc_step("Checking iptables status on host {} after reboot".format(controller))
            cmd = 'service iptables status | grep Active'
            code, output = con_ssh.exec_sudo_cmd(cmd)
            assert 'active' in output, "iptables service did not start after reboot on host {}".format(controller)


def test_default_iptables_rules():
    """
    Test default iptables rules (ensuring the ports are open)

    Test Steps:
        - If controller is not active, swact activity towards the controller being tested
        - Confirm iptables service is running
        - Check if https or http is running; Add the corresponding port to the default port list
        - Confirm the default ports are open
    """
    expected_open_ports = [123, 161, 199, 5000, 6080, 6385, 8000, 8003, 8004, 8773, 8774, 8776, 8777, 9292, 9696,
                           15491, 35357]
    expected_open_ports_failed = []

    LOG.tc_step("Get the controller(s)")
    controllers = system_helper.get_controllers()
    for controller in controllers:

        LOG.tc_step("Ensure {} is active".format(controller))
        active_con = system_helper.get_active_controller_name()
        if controller != active_con:
            LOG.tc_step("{} is not active; Swacting {}".format(controller, active_con))
            host_helper.swact_host(active_con)

        with host_helper.ssh_to_host(controller) as con_ssh:
            LOG.tc_step("Check if iptables is running")
            cmd = 'service iptables status | grep Active'
            code, output = con_ssh.exec_sudo_cmd(cmd)
            assert 'active' in output, "iptables service is not running on host {}".format(controller)

            LOG.tc_step("Add HTTPS to the port list if it is enabled otherwise add HTTP")
            cmd = 'grep /opt/platform/config/17.00/cgcs_config -e "ENABLE_HTTPS="'
            code, output = con_ssh.exec_cmd(cmd)
            if output is 'ENABLE_HTTPS=False':
                expected_open_ports.append(80)
            elif output is 'ENABLE_HTTPS=True':
                expected_open_ports.append(443)

            LOG.tc_step("Ensure default ports are open")
            for port in expected_open_ports:
                cmd = 'netstat -lntu | grep -w {}'.format(port)
                code, output = con_ssh.exec_cmd(cmd)
                if output is '':
                    expected_open_ports_failed.append(port)

        if len(expected_open_ports_failed) > 0:
            assert 0, "The following ports were closed when they should have been open by default: {}" \
                .format(expected_open_ports_failed)


def _test_custom_iptables_rules():
    """
    Test custom iptables rules (ensuring the ports are open)

    Skip Condition:
        - N/A

    Test Steps:
        - If controller is not active, swact activity towards the controller being tested
        - Install custom iptables rules
        - Confirm the custom ports are open
        - Remove custom iptables rules
        - Confirm the custom ports are closed
    """
    custom_ports = [1111, 1996, 1998, 1545]
    custom_ports_failed_to_open = []
    custom_ports_failed_to_close = []

    LOG.tc_step("SCP iptables.rules file from the test server")
    file_name = 'iptables.rules'
    source = TestServerPath.TEST_SCRIPT + file_name
    destination = WRSROOT_HOME
    common.scp_from_test_server_to_active_controller(source_path=source, dest_dir=destination)

    controllers = system_helper.get_controllers()
    out_of_date_alarms = []
    for controller in controllers:
        out_of_date_alarms.append((EventLogID.CONFIG_OUT_OF_DATE, 'host={}'.format(controller)))

    LOG.tc_step("Installing custom firewall rules")
    iptables_path = WRSROOT_HOME + file_name
    code, output = cli.system('firewall-rules-install', iptables_path, fail_ok=True)
    if "Could not open file" in output:
        skip("Failed to find {}. SCP may have failed.".format(iptables_path))
    system_helper.wait_for_alarms_gone(out_of_date_alarms)

    LOG.tc_step("Verify custom ports are open")
    for controller in controllers:
        LOG.info("Ensure {} is active".format(controller))
        active_con = system_helper.get_active_controller_name()
        if controller != active_con:
            LOG.info("{} is not active; Swacting {}".format(controller, active_con))
            host_helper.swact_host(active_con)
        with host_helper.ssh_to_host(controller) as con_ssh:
            LOG.info("Verify custom ports are open on the active controller")
            for port in custom_ports:
                cmd = 'iptables -nvL | grep -w {}'.format(port)
                code, output = con_ssh.exec_sudo_cmd(cmd)
                if output is '':
                    custom_ports_failed_to_open.append(port)

    LOG.tc_step("Removing custom firewall rules")
    empty_iptables_path = WRSROOT_HOME + "iptables-empty.rules"
    with host_helper.ssh_to_host(system_helper.get_active_controller_name()) as con_ssh:
        con_ssh.exec_cmd("touch {}".format(empty_iptables_path))
    cli.system('firewall-rules-install', empty_iptables_path)
    system_helper.wait_for_alarms_gone(out_of_date_alarms)

    LOG.tc_step("Verify custom ports are no longer open")
    for controller in controllers:
        LOG.info("Ensure {} is active".format(controller))
        active_con = system_helper.get_active_controller_name()
        if controller != active_con:
            LOG.info("{} is not active; Swacting {}".format(controller, active_con))
            host_helper.swact_host(active_con)
        with host_helper.ssh_to_host(controller) as con_ssh:
            LOG.info("Verify custom ports are closed on the active controller")
            for port in custom_ports:
                cmd = 'iptables -nvL | grep -w {}'.format(port)
                code, output = con_ssh.exec_sudo_cmd(cmd)
                if output is '':
                    custom_ports_failed_to_close.append(port)

    assert not custom_ports_failed_to_open and not custom_ports_failed_to_close
