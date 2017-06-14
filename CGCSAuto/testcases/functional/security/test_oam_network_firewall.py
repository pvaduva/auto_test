##############################
# OAM Network Firewall tests #
##############################
from keywords import host_helper, system_helper
from utils.tis_log import LOG
from pytest import skip


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


def test_custom_iptables_rules():
    """
    Test custom iptables rules (ensuring the ports are open)

    Skip Condition:
        - If a custom iptables.rules file is not used

    Test Steps:
        - If controller is not active, swact activity towards the controller being tested
        - Confirm iptables service is running
        - Confirm the custom ports are open
    """
    custom_ports = [1111, 1996, 1998, 1545]
    custom_ports_failed = []

    with host_helper.ssh_to_host(system_helper.get_active_controller_name()) as con_ssh:
        LOG.tc_step("Check for custom firewall rules")
        cmd = 'grep /opt/platform/config/17.06/cgcs_config -e "FIREWALL_RULES_FILE="'
        code, output = con_ssh.exec_cmd(cmd)
        if output is '':
            skip("No custom firewall rules are used. Cannot test customs rules.")

    LOG.tc_step("Get the controller(s)")
    controllers = system_helper.get_controllers()
    for controller in controllers:
        LOG.tc_step("Ensure {} is active".format(controller))
        active_con = system_helper.get_active_controller_name()
        if controller != active_con:
            LOG.tc_step("{} is not active; Swacting {}".format(controller, active_con))
            host_helper.swact_host(active_con)
        with host_helper.ssh_to_host(controller) as con_ssh:
            LOG.tc_step("Check to ensure custom ports are open")
            for port in custom_ports:
                cmd = 'iptables -nvL | grep -w {}'.format(port)
                code, output = con_ssh.exec_sudo_cmd(cmd)
                if output is '':
                    custom_ports_failed.append(port)

        if len(custom_ports_failed) > 0:
            assert 0, "The following custom ports were closed when they should have been open: {}" \
                .format(custom_ports_failed)
