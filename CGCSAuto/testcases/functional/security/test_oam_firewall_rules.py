##############################
# OAM Network Firewall tests #
##############################
import time

from consts.cgcs import EventLogID, Prompt
from consts.filepaths import TestServerPath, WRSROOT_HOME
from keywords import host_helper, system_helper, common, html_helper, keystone_helper
from testfixtures.recover_hosts import HostsToRecover
from utils import cli
from utils.multi_thread import MThread
from utils.tis_log import LOG
from utils.ssh import ControllerClient, NATBoxClient


def test_status_firewall_reboot():
    """
    Test iptables status after reboot of controller

    Test Steps:
        - Stop iptables service
        - Confirm iptables service has stopped
        - Reboot the controller being tested
        - Confirm iptables service is online
        - Repeat for second controller
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
        HostsToRecover.add(controller)
        host_helper.reboot_hosts(controller)

        with host_helper.ssh_to_host(controller) as con_ssh:
            LOG.tc_step("Checking iptables status on host {} after reboot".format(controller))
            cmd = 'service iptables status | grep --color=never Active'
            code, output = con_ssh.exec_sudo_cmd(cmd)
            assert 'active' in output, "iptables service did not start after reboot on host {}".format(controller)


def test_firewall_rules_default():
    """
    Verify default ports are open.

    Test Steps:
        - Confirm iptables service is running on active controller
        - Check if lab is http(s), add corresponding port to check
        - Confirm the default ports are open
        - Swact and repeat the above steps
    """
    # Cannot test connecting to the ports as they are in use.
    default_ports = [123, 161, 199, 5000, 6080, 6385, 8000, 8003, 8004, 8773, 8774, 8776, 8777, 9292, 9696, 15491,
                     35357]
    default_ports.append(443) if keystone_helper.is_https_lab() else default_ports.append(80)

    active_controller = system_helper.get_active_controller_name()
    con_ssh = ControllerClient.get_active_controller()

    _verify_iptables_status(con_ssh, active_controller)
    _check_ports_with_netstat(con_ssh, active_controller, default_ports)

    LOG.tc_step("Swact {}".format(active_controller))
    host_helper.swact_host(active_controller)
    active_controller = system_helper.get_active_controller_name()
    con_ssh = ControllerClient.get_active_controller()

    _verify_iptables_status(con_ssh, active_controller)
    _check_ports_with_netstat(con_ssh, active_controller, default_ports)


def _verify_iptables_status(con_ssh, active_controller):
    LOG.tc_step("Check if iptables is running on {}".format(active_controller))
    cmd = 'service iptables status | grep --color=never Active'
    code, output = con_ssh.exec_sudo_cmd(cmd)
    assert 'active' in output, "iptables service is not running on host {}".format(active_controller)


def _check_ports_with_netstat(con_ssh, active_controller, ports):

    LOG.tc_step("Verify ports on {}".format(active_controller))
    for port in ports:
        cmd = 'netstat -lntu | grep --color=never -w {}'.format(port)
        code, output = con_ssh.exec_cmd(cmd)
        assert output is not '', "Port {} is not listed in netstat. Expected to be open.".format(port)


def test_firewall_rules_custom():
    """
    Verify specified ports from the custom firewall rules are open and non-specified ports are closed.

    Skip Condition:
        - N/A

    Test Setup:
        - SCP iptables.rules from test server to lab

    Test Steps:
        - Install custom firewall rules
        - Check ports that should be both open and closed based on the custom firewall rules
        - Swact and check ports that should be both open and closed based on the custom firewall rules
        - Remove custom firewall rules
        - Check ports that are in the custom firewall rules are no longer open
        - Swact and check ports that are in the custom firewall rules are no longer open
    """
    # The following ports must be in the iptables.rules file or the test will fail
    custom_ports = [1111, 1996, 1998, 1545]

    LOG.tc_step("SCP iptables.rules file from the test server")
    file_name = 'iptables.rules'
    source = TestServerPath.TEST_SCRIPT + file_name
    destination = WRSROOT_HOME
    firewall_rules_path = common.scp_from_test_server_to_active_controller(source_path=source, dest_dir=destination)
    assert firewall_rules_path is not None

    LOG.tc_step("Installing custom firewall rules")
    _modify_firewall_rules(firewall_rules_path)

    active_controller = system_helper.get_active_controller_name()
    con_ssh = ControllerClient.get_active_controller()

    LOG.tc_step("Verify custom ports on {}".format(active_controller))
    for port in custom_ports:
        # Verifying ports that are in the iptables file are open
        _verify_port_from_natbox(con_ssh, port, port_expected_open=True)

        # Verifying ports that are not in the iptables file are still closed
        _verify_port_from_natbox(con_ssh, port + 1, port_expected_open=False)

    LOG.tc_step("Swact {}".format(active_controller))
    host_helper.swact_host(active_controller)
    active_controller = system_helper.get_active_controller_name()
    con_ssh = ControllerClient.get_active_controller()

    LOG.tc_step("Verify custom ports on {}".format(active_controller))
    for port in custom_ports:
        # Verifying ports that are in the iptables file are open after swact
        _verify_port_from_natbox(con_ssh, port, port_expected_open=True)

        # Verifying ports that are not in the iptables file are still closed after swact
        _verify_port_from_natbox(con_ssh, port + 1, port_expected_open=False)

    LOG.tc_step("Removing custom firewall rules")
    empty_firewall_rules_path = WRSROOT_HOME + "iptables-empty.rules"
    con_ssh.exec_cmd("touch {}".format(empty_firewall_rules_path))
    _modify_firewall_rules(empty_firewall_rules_path)

    LOG.tc_step("Verify custom ports on {}".format(active_controller))
    for port in custom_ports:
        # Verifying ports that are in the iptables file are closed
        _verify_port_from_natbox(con_ssh, port, port_expected_open=False)

    LOG.tc_step("Swact {}".format(active_controller))
    host_helper.swact_host(active_controller)
    active_controller = system_helper.get_active_controller_name()
    con_ssh = ControllerClient.get_active_controller()

    LOG.tc_step("Verify custom ports on {}".format(active_controller))
    for port in custom_ports:
        # Verifying ports that are in the iptables file are closed after swact
        _verify_port_from_natbox(con_ssh, port, port_expected_open=False)


def _modify_firewall_rules(firewall_rules_path):
    """
    :param firewall_rules_path: Path to the firewalls rules file (including the file name)
    """
    start_time = common.get_date_in_format()
    cli.system('firewall-rules-install', firewall_rules_path)
    system_helper.wait_for_events(start=start_time, fail_ok=False,
                                  **{'Entity Instance ID': 'host=controller-0',
                                     'Event Log ID': EventLogID.CONFIG_OUT_OF_DATE, 'State': 'set'})
    system_helper.wait_for_events(start=start_time, fail_ok=False,
                                  **{'Entity Instance ID': 'host=controller-1',
                                     'Event Log ID': EventLogID.CONFIG_OUT_OF_DATE, 'State': 'set'})
    system_helper.wait_for_events(start=start_time, fail_ok=False,
                                  **{'Entity Instance ID': 'host=controller-0',
                                     'Event Log ID': EventLogID.CONFIG_OUT_OF_DATE, 'State': 'clear'})
    system_helper.wait_for_events(start=start_time, fail_ok=False,
                                  **{'Entity Instance ID': 'host=controller-1',
                                     'Event Log ID': EventLogID.CONFIG_OUT_OF_DATE, 'State': 'clear'})
    # Ensures iptables has enough time to populate the list with new ports
    time.sleep(10)


def _verify_port_from_natbox(con_ssh, port, port_expected_open):
    """
    :param con_ssh: Controller ssh client
    :param port: (number) Port to test
    :param port_expected_open: (boolean)
    """
    lab_ip = html_helper.get_ip_addr()

    LOG.info("Verify port {} is listed in iptables".format(port))
    cmd = 'iptables -nvL | grep --color=never -w {}'.format(port)
    output = con_ssh.exec_sudo_cmd(cmd, get_exit_code=False)[1]
    if port_expected_open:
        if output is '':
            assert 0, "Port {} is not listed in iptables. Expected to be open.".format(port)
    else:
        if output is not '':
            assert 0, "Port {} is listed in iptables. Expected to be closed.".format(port)

    LOG.info("Open listener on port {}".format(port))
    listener_thread = MThread(_listen_on_port, port)
    listener_thread.start_thread(timeout=30, keep_alive=True)
    if port_expected_open:
        if not _wait_for_listener(con_ssh, port):
            assert 0, "Port {} does not show listening in netstat. Expected to be listening.".format(port)

    LOG.info("Verify port {} can be accessed from natbox".format(port))
    natbox_ssh = NATBoxClient.get_natbox_client()
    output = natbox_ssh.exec_cmd("nc -v -w 2 {} {}".format(lab_ip, port), get_exit_code=False)[1]
    listener_thread.end_thread()
    listener_thread.wait_for_thread_end()

    try:
        if port_expected_open:
            if 'succeeded' not in output:
                raise ValueError("Natbox failed to connect to port {}. Expected to succeed.".format(port))
        else:
            if 'succeeded' in output:
                raise ValueError("Natbox connected to port {}. Expected to fail.".format(port))
    except ValueError as error:
        assert 0, error
    finally:
        con_ssh.send_control('c')
        con_ssh.expect(Prompt.CONTROLLER_PROMPT)


def _listen_on_port(port):
    """
    :param port: (int) Port to listen on
    """
    con_ssh = ControllerClient.get_active_controller()
    con_ssh.send('nc -l {}'.format(port))
    con_ssh.expect("")


def _wait_for_listener(con_ssh, port):
    """
    :param con_ssh: Controller ssh client
    :param port: (int) Port to check for listener
    """
    timeout = time.time() + 60
    while time.time() < timeout:
        code = con_ssh.exec_sudo_cmd("netstat -lntu | grep --color=never :{}".format(port), fail_ok=True)[0]
        if code == 0:
            return True
        time.sleep(5)
    return False
