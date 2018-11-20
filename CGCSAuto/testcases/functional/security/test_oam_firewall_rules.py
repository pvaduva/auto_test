##############################
# OAM Network Firewall tests #
##############################
import time

from pytest import fixture, mark

from utils import cli
from utils.tis_log import LOG
from utils.multi_thread import MThread, Events
from utils.clients.ssh import ControllerClient, NATBoxClient, get_cli_client
from consts.cgcs import EventLogID, MULTI_REGION_MAP
from consts.filepaths import TestServerPath
from consts.proj_vars import ProjVar
from consts.auth import CliAuth, Tenant
from keywords import host_helper, system_helper, common, dc_helper
from testfixtures.recover_hosts import HostsToRecover


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

    default_ports = [123, 161, 199, 5000, 6080, 6385, 8000, 8003, 8004, 8041, 8774, 8776, 8778, 9292, 9696, 15491]

    from consts.proj_vars import ProjVar
    region = ProjVar.get_var('REGION')
    if region != 'RegionOne' and region in MULTI_REGION_MAP:
        default_ports.remove(5000)
        default_ports.remove(9292)

    default_ports.append(443) if CliAuth.get_var('HTTPS') else default_ports.append(80)

    active_controller = system_helper.get_active_controller_name()
    con_ssh = ControllerClient.get_active_controller()

    _verify_iptables_status(con_ssh, active_controller)
    _check_ports_with_netstat(con_ssh, active_controller, default_ports)

    active_controller, new_active = system_helper.get_active_standby_controllers()
    if new_active:
        LOG.tc_step("Swact {} and verify firewall rules".format(active_controller))
        host_helper.swact_host(active_controller)
        con_ssh = ControllerClient.get_active_controller()

        _verify_iptables_status(con_ssh, new_active)
        _check_ports_with_netstat(con_ssh, new_active, default_ports)


def _verify_iptables_status(con_ssh, active_controller):
    LOG.tc_step("Check if iptables is running on {}".format(active_controller))
    cmd = 'service iptables status | grep --color=never Active'
    code, output = con_ssh.exec_sudo_cmd(cmd)
    assert 'active' in output, "iptables service is not running on host {}".format(active_controller)


def _check_ports_with_netstat(con_ssh, active_controller, ports):
    LOG.tc_step("Verify ports on {}".format(active_controller))
    end_time = time.time() + 5
    failed_ports = []
    while time.time() < end_time:
        failed_ports = []
        for port in ports:
            cmd = 'netstat -lntu | grep --color=never -w {}'.format(port)
            code, output = con_ssh.exec_cmd(cmd)
            if not output:
                failed_ports.append(port)

        if not failed_ports:
            LOG.info("Ports {} are listed in netstat".format(ports))
            return

        time.sleep(3)

    assert False, "Timed out waiting for ports {} to be listed in netstat. Expected to be open.".format(failed_ports)


@fixture(scope='module')
def get_custom_firewall_rule():
    custom_name = 'iptables.rules'
    source = TestServerPath.TEST_SCRIPT + custom_name
    user_file_dir = ProjVar.get_var('USER_FILE_DIR')
    custom_path = common.scp_from_test_server_to_user_file_dir(source_path=source, dest_dir=user_file_dir,
                                                               dest_name=custom_name, central_region=True)
    assert custom_path is not None

    return custom_path


@fixture()
def delete_file(get_custom_firewall_rule, request):
    user_file_dir = ProjVar.get_var('USER_FILE_DIR')
    invalid_rules_file = '{}iptables.rules.invalid.file'.format(user_file_dir)
    invalid_rules_path = '{}iptables.rules.invalid'.format(user_file_dir)
    firewall_rules_path = get_custom_firewall_rule
    cli_client = get_cli_client()

    def teardown():
        LOG.fixture_step("Cleanup Remove file: {}".format(invalid_rules_file))
        cli_client.exec_cmd("rm {}".format(invalid_rules_file))
    request.addfinalizer(teardown)

    return invalid_rules_file, invalid_rules_path, firewall_rules_path, cli_client


def test_invalid_firewall_rules(delete_file):
    """
    Verify invalid firewall install files name & invalid file
    Test Setup:
        - SCP iptables.rules from test server to lab

    Test Steps:
        - Install custom firewall rules with invalid file path
        - Verify install failed with valid reason
        - Install custom firewall rules with invalid file
        - Verify install failed with valid reason

    """
    invalid_rules_file, invalid_rules_path, firewall_rules_path, cli_client = delete_file
    LOG.info("firewall rules path {}".format(firewall_rules_path))

    LOG.tc_step("Install firewall rules with invalid file name {}".format(invalid_rules_path))
    code, output = cli.system('firewall-rules-install', invalid_rules_path, fail_ok=True, rtn_list=True)

    LOG.tc_step("Verify Install firewall rules failed with invalid file name")
    LOG.info("Invalid fireall rules return code:[{}] & output: [{}]".format(code, output))

    assert 'Could not open file' in output, "Unexpected error"
    assert code == 1, "Invalid firewall rules install expected to fail, reason received {}".format(output)

    LOG.tc_step("Install firewall rules with invalid file")
    cmd = "cp {} {}".format(firewall_rules_path, invalid_rules_file)
    code, output = cli_client.exec_cmd(cmd)
    LOG.info("Code: {} output: {}".format(code, output))
    cli_client.exec_cmd("sed -e '3i invalid' -i {}".format(invalid_rules_file))

    LOG.tc_step("Install firewall rules with invalid file name {}".format(invalid_rules_file))
    code, output = cli.system('firewall-rules-install', invalid_rules_file, fail_ok=True, rtn_list=True)
    LOG.info("Invalid firewall rules return code:[{}] & output: [{}]".format(code, output))

    assert 'Error in custom firewall rule file' in output, "Unexpected output"
    assert code == 1, "Invalid firewall rules exit code"


@fixture()
def remove_custom_firewall(get_custom_firewall_rule, request):
    firewall_rules_path = get_custom_firewall_rule
    custom_ports = [1111, 1996, 1998, 1545]

    def remove():
        LOG.fixture_step("Removing custom firewall rules")
        user_file_dir = ProjVar.get_var('USER_FILE_DIR')
        empty_path = user_file_dir + "iptables-empty.rules"
        client = get_cli_client(central_region=True)
        client.exec_cmd('touch {}'.format(empty_path))
        _modify_firewall_rules(empty_path)

        active, standby = system_helper.get_active_standby_controllers()
        con_ssh = ControllerClient.get_active_controller()
        LOG.fixture_step("Verify custom ports on {}".format(active))
        for port in custom_ports:
            # Verifying ports that are in the iptables file are closed
            _verify_port_from_natbox(con_ssh, port, port_expected_open=False)

        if standby:
            LOG.fixture_step("Swact {}".format(active))
            host_helper.swact_host(active)

            LOG.fixture_step("Verify custom ports on {}".format(standby))
            for port in custom_ports:
                # Verifying ports that are in the iptables file are closed after swact
                _verify_port_from_natbox(con_ssh, port, port_expected_open=False)

    request.addfinalizer(remove)

    return custom_ports, firewall_rules_path


@mark.dc
def test_firewall_rules_custom(remove_custom_firewall):
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
    custom_ports, firewall_rules_path = remove_custom_firewall

    LOG.tc_step("Installing custom firewall rules")
    _modify_firewall_rules(firewall_rules_path)

    active_controller, standby_controller = system_helper.get_active_standby_controllers()
    con_ssh = ControllerClient.get_active_controller()

    LOG.tc_step("Verify custom ports on {}".format(active_controller))
    for port in custom_ports:
        # Verifying ports that are in the iptables file are open
        _verify_port_from_natbox(con_ssh, port, port_expected_open=True)

        # Verifying ports that are not in the iptables file are still closed
        _verify_port_from_natbox(con_ssh, port + 1, port_expected_open=False)

    if standby_controller:
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


def _modify_firewall_rules(firewall_rules_path):
    """
    :param firewall_rules_path: Path to the firewalls rules file (including the file name)
    """
    dc_region = 'RegionOne' if ProjVar.get_var('IS_DC') else None

    ssh_client = ControllerClient.get_active_controller(name=dc_region)
    LOG.info("Install firewall rules: {}".format(firewall_rules_path))
    auth_info = Tenant.get('admin', dc_region=dc_region)
    start_time = common.get_date_in_format(ssh_client=ssh_client)
    time.sleep(1)
    cli.system('firewall-rules-install', firewall_rules_path, auth_info=auth_info, ssh_client=ssh_client)

    def _wait_for_config_apply(auth_info_, con_ssh_=None):
        controllers = system_helper.get_controllers(auth_info=auth_info_, con_ssh=con_ssh_)
        for controller in controllers:
            system_helper.wait_for_events(start=start_time, fail_ok=False, timeout=60,
                                          entity_instance_id='host=controller',
                                          event_log_id=EventLogID.CONFIG_OUT_OF_DATE,
                                          auth_info=auth_info_, con_ssh=con_ssh_,
                                          **{'Entity Instance ID': 'host={}'.format(controller),
                                             'State': 'set'})
            # Extend timeout for controller-1 config-out-date clear to 5min due to CGTS-8497
            system_helper.wait_for_events(start=start_time, fail_ok=False, timeout=300,
                                          entity_instance_id='host=controller',
                                          event_log_id=EventLogID.CONFIG_OUT_OF_DATE,
                                          auth_info=auth_info_, con_ssh=con_ssh_,
                                          **{'Entity Instance ID': 'host={}'.format(controller),
                                             'State': 'clear'})

    LOG.info("Wait for config to apply on both controllers")
    _wait_for_config_apply(auth_info_=auth_info, con_ssh_=ssh_client)

    if ProjVar.get_var('IS_DC'):
        subcloud = ProjVar.get_var('PRIMARY_SUBCLOUD')
        LOG.info("Wait for sync audit for {} in dcmanager.log".format(subcloud))
        dc_helper.wait_for_sync_audit(subclouds=subcloud)

        LOG.info("Wait for config apply on {}".format(subcloud))
        _wait_for_config_apply(auth_info_=Tenant.get('admin'))

    # Ensures iptables has enough time to populate the list with new ports
    time.sleep(10)


def _verify_port_from_natbox(con_ssh, port, port_expected_open):
    """
    :param con_ssh: Controller ssh client
    :param port: (number) Port to test
    :param port_expected_open: (boolean)
    """
    if ProjVar.get_var('IS_DC'):
        subcloud = ProjVar.get_var('PRIMARY_SUBCLOUD')
        lab_ip = ProjVar.get_var('LAB')[subcloud]['floating ip']
    else:
        lab_ip = ProjVar.get_var('LAB')['floating ip']

    cli.system('show', source_openrc=True, force_source=True)

    LOG.info("Check if port {} is listed in iptables".format(port))
    cmd = 'iptables -nvL | grep --color=never -w {}'.format(port)
    end_time = time.time() + 90
    while time.time() < end_time:
        output = con_ssh.exec_sudo_cmd(cmd, get_exit_code=False)[1]
        if (port_expected_open and output) or (not port_expected_open and not output):
            LOG.info("Port {} is {}listed in iptables as expected".format(port, '' if port_expected_open else 'not '))
            break
        time.sleep(5)
    else:
        assert 0, "Port {} is {}listed in iptables. ".format(port, 'not ' if port_expected_open else '')

    end_event = Events('Packet received')
    LOG.info("Open listener on port {}".format(port))
    listener_thread = MThread(_listen_on_port, port, end_event=end_event, ssh_name=ProjVar.get_var('PRIMARY_SUBCLOUD'))
    listener_thread.start_thread(timeout=300)

    extra_str = 'succeeded' if port_expected_open else 'rejected'
    LOG.info("Verify access to port {} from natbox is {}".format(port, extra_str))
    try:
        wait_for_port_to_listen(con_ssh, port)
        natbox_ssh = NATBoxClient.get_natbox_client()
        end_time = time.time() + 60
        while time.time() < end_time:
            output = natbox_ssh.exec_cmd("nc -v -w 2 {} {}".format(lab_ip, port), get_exit_code=False)[1]
            if (port_expected_open and 'succeeded' in output) or (not port_expected_open and 'succeeded' not in output):
                LOG.info("Access via port {} {} as expected".format(port, extra_str))
                return
        else:
            assert False, "Access via port {} is not {}".format(port, extra_str)
    finally:
        end_event.set()
        listener_thread.wait_for_thread_end(timeout=10)
        con_ssh.send_control('c')
        con_ssh.expect(con_ssh.get_prompt())


def _listen_on_port(port, end_event, ssh_name=None, timeout=300):
    """

    Args:
        port (int|str):
        end_event (Events):
        ssh_name:
        timeout (int):

    Returns:

    """
    con_ssh = ControllerClient.get_active_controller(name=ssh_name)
    con_ssh.send('nc -l {}'.format(port))
    con_ssh.expect("")

    end_time = time.time() + timeout
    while time.time() < end_time:
        if end_event.is_set():
            return
        time.sleep(1)

    assert 0, "End event is not set within timeout, check automation code"


def wait_for_port_to_listen(con_ssh, port):
    """

    Args:
        con_ssh:
        port:

    Returns:

    """
    timeout = time.time() + 120
    while time.time() < timeout:
        code = con_ssh.exec_sudo_cmd("netstat -lntu | grep --color=never :{}".format(port), fail_ok=True)[0]
        if code == 0:
            return True

        time.sleep(10)

    assert 0, "Port {} is not listening".format(port)
