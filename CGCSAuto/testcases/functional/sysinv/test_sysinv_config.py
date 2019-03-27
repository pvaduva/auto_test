import random
import string
import time
from functools import wraps

from pytest import fixture
from pytest import mark, skip

from consts.auth import Tenant
from consts.cgcs import SystemType
from consts.timeout import SysInvTimeout
from consts.proj_vars import ProjVar
from keywords import network_helper
from keywords import system_helper
from utils import cli, table_parser
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG


def id_gen(val):
    if isinstance(val, (list, tuple)):
        val = '_'.join([str(val_).replace('::', ':_') for val_ in val])

    return val


def repeat_checking(repeat_times=20, wait_time=6):
    def actual_decorator(func):
        @wraps(func)
        def wrapped_func(*args, **kwargs):
            cnt, output = 0, ''
            while cnt < repeat_times:
                cnt += 1
                code, output = func(*args, **kwargs)
                if code == 0:
                    return code, output
                time.sleep(wait_time)
            return -1, output

        return wrapped_func
    return actual_decorator


@mark.p3
def test_system_type():
    """
    Verify the System Type can be retrieved from SysInv and is correct

    Test Steps:
        - Determine the System Type based on whether the system is CPE or not
        - Retrieve the System Type information from SystInv
        - Compare the types and verify they are the same, fail the test case otherwise

    Notes:
        - Covers SysInv test-cases:
            66) Query the product type on CPE system using CLI
            67) Query the product type on STD system using CLI
    """

    LOG.tc_step('Determine the real System Type the lab')
    if system_helper.is_small_footprint():
        expt_system_type = SystemType.CPE
    else:
        expt_system_type = SystemType.STANDARD

    LOG.tc_step('Get System Type from system inventory')
    table_ = table_parser.table(cli.system('show'))
    displayed_system_type = table_parser.get_value_two_col_table(table_, 'system_type')

    LOG.tc_step('Verify the expected System Type is the same as that from System Inventory')
    assert expt_system_type == displayed_system_type, 'Expected system_type is: {}; Displayed system type: {}.'. \
        format(expt_system_type, displayed_system_type)


@mark.p3
def test_system_type_is_readonly():
    """
    Verify System Type is readonly

    Test Steps:
        - Determine the System Type based on whether the system is CPE or not
        - Attempt to modify the System Type to a different type
        - Compare the types and verify they are the same, fail the test case otherwise

    Notes:
        - Covers SysInv test-case
            71) Verify the system type is read-only and cannot be changed via CLI
    """

    LOG.tc_step('Determine the real System Type for the lab')
    if system_helper.is_small_footprint():
        cur_system_type = SystemType.CPE
    else:
        cur_system_type = SystemType.STANDARD

    LOG.tc_step('Attempt to modify System Type')
    change_to_system_type = SystemType.CPE
    if cur_system_type == SystemType.CPE:
        change_to_system_type = SystemType.STANDARD
    code, msg = system_helper.modify_system(fail_ok=True, con_ssh=None, auth_info=Tenant.get('admin'),
                                            system_mode='{}'.format(change_to_system_type))

    LOG.tc_step('Verify system rejected to change System Type to {}'.format(change_to_system_type))
    assert 1 == code, msg


@mark.p3
class TestRetentionPeriod:
    """
    Test modification of Retention Period of the TiS system
    """

    # PM_SETTING_FILE = '/etc/ceilometer/ceilometer.conf'  # file where the Retention Period is stored
    PM_SETTING_FILE = '/etc/panko/panko.conf'  # file where the Retention Period is stored
    MIN_RETENTION_PERIOD = 3600  # seconds of 1 hour, minimum value allowed
    MAX_RETENTION_PERIOD = 31536000  # seconds of 1 year, maximum value allowed
    SEARCH_KEY_FOR_RENTION_PERIOD = r'event_time_to_live'
    retention_period = 0

    @fixture(scope='class', autouse=True)
    def backup_restore_rention_period(self, request):
        """
        Fixture to save the current retention period and restore it after test

        Args:
            request: request passed in to the fixture.

        """
        LOG.info('Backup Retention Period')
        TestRetentionPeriod.retention_period = system_helper.get_retention_period_k8s()
        LOG.info('Current Retention Period is {}'.format(TestRetentionPeriod.retention_period))

        def restore_retention_period():
            LOG.info('Restore Retention Period to its orignal value {}'.format(TestRetentionPeriod.retention_period))
            system_helper.set_retention_period_k8s(int(TestRetentionPeriod.retention_period), fail_ok=True)

        request.addfinalizer(restore_retention_period)

    @mark.parametrize(
        "new_retention_period", [
            -1,
            MIN_RETENTION_PERIOD - 1,
            # random.randrange(MIN_RETENTION_PERIOD, MAX_RETENTION_PERIOD + 1),
            24828899,
            MAX_RETENTION_PERIOD + 1,
        ])
    def test_modify_ceilometer_event_retention_period(self, new_retention_period):
        """
        Test change the 'retention period for ceilometer event' to new values.

        Args:
            new_retention_period(int):

        Test Setups:
            - Do nothing, and delegate to the class-scope fixture to save the currently in-use Retention Period

        Test Steps:
            - Change the Retention Period with CLI

        Test Teardown:
            - Do nothing, and delegate to the class-scope fixture to restore the original value of Retention Period
            before test

        Notes:
            - Covers SysInv test-case
                38) Change the retention period via CLI
            - We can determine the range of accepted values on the running system in stead of parameterizing
                on hardcoded values
        """
        name = 'event_time_to_live'

        LOG.tc_step('Check if the modification attempt will fail based on the input value')
        if new_retention_period < self.MIN_RETENTION_PERIOD or new_retention_period > self.MAX_RETENTION_PERIOD:
            expect_fail = True
        else:
            expect_fail = False
        LOG.tc_step('Attempt to change to new value:{}'.format(new_retention_period))
        code, output = system_helper.set_retention_period_k8s(
            new_retention_period, fail_ok=expect_fail, name=name, check_first=False)

        if expect_fail:
            assert code != 0, 'Expecting failed to change retention period, but the request went through'

        LOG.tc_step('Wait for {} seconds'.format(SysInvTimeout.RETENTION_PERIOD_SAVED))
        time.sleep(SysInvTimeout.RETENTION_PERIOD_SAVED)

        LOG.tc_step('Verify new value:{} was set for {}'.format(new_retention_period, name))
        cmd = 'cat ' + self.PM_SETTING_FILE

        changed = system_helper.verify_config_changed('panko', cmd, fail_ok=expect_fail, **{name: new_retention_period})
        if expect_fail:
            assert not changed, \
                'Change request should be rejected, but actually not. old value:{0}, new value:{1} '.format(
                    TestRetentionPeriod.retention_period, new_retention_period)
            LOG.info('OK, the value for {0} did not change correctly, old value {1} remains'.format(
                name, TestRetentionPeriod.retention_periodd))
        else:
            assert changed, 'Retention period was successfully changed to {0}, old value {1}'.format(
                new_retention_period, TestRetentionPeriod.retention_period)
            LOG.info('OK, the value for {0} was successfully changed to {1}, old value {2}'.format(
                name, new_retention_period, TestRetentionPeriod.retention_period))


@mark.p3
class TestDnsSettings:
    """
    Test modifying the settings about DNS servers
    """

    DNS_SETTING_FILE = '/etc/resolv.conf'

    @repeat_checking(repeat_times=10, wait_time=6)
    def wait_for_dns_changed(self, expected_ip_addres):
        ip_addr_list = expected_ip_addres if expected_ip_addres is not None else []

        controller_ssh = ControllerClient.get_active_controller()

        cmd_get_saved_dns = 'cat {}'.format(TestDnsSettings.DNS_SETTING_FILE)
        code, output = controller_ssh.exec_cmd(cmd_get_saved_dns, expect_timeout=20)

        assert 0 == code, 'Failed to get saved DNS settings: {}'.format(cmd_get_saved_dns)

        LOG.info('Find saved DNS servers:\n{}\n'.format(output))
        saved_dns = []
        for line in output.splitlines():
            if line.strip().startswith('nameserver'):
                _, ip = line.strip().split()
                if ip and not ip.startswith('192.168'):
                    saved_dns.append(ip)

        LOG.info('Verify all input DNS servers are saved, expecting:{}'.format(expected_ip_addres))
        if set(ip_addr_list).issubset(set(saved_dns)):
            return 0, saved_dns
        else:
            return 1, 'Saved DNS servers are different from the input DNS servers\nActual:{}\nExpected:{}\n'\
                .format(saved_dns, ip_addr_list)

    @fixture(scope='class', autouse=True)
    def backup_restore_dns_settings(self, request):
        """
        Fixture to save the current DNS servers and restore them after test

        Args:
            request: request passed in by py.test system

        """
        if ProjVar.get_var('IS_DC'):
            skip("Distributed Cloud has different procedure for DNS configuration.")

        self.dns_servers = system_helper.get_dns_servers(con_ssh=None)
        LOG.info('Save current DNS-servers:{}'.format(self.dns_servers))

        def restore_dns_settings():
            LOG.info('Restore the DNS-servers to the original:{}'.format(self.dns_servers))
            system_helper.set_dns_servers(fail_ok=False, con_ssh=None, auth_info=Tenant.get('admin'),
                                          nameservers=self.dns_servers)
            # nameservers=','.join(self.dns_servers))

        request.addfinalizer(restore_dns_settings)

    @mark.parametrize(
        ('new_dns_servers', 'with_action_option'),
        [
            (('128.224.144.130', '147.11.57.128', '147.11.57.133'), None),
            (('8.8.8.8', '8.8.4.4'), 'apply'),
            (('fd00:0:0:21::5', '2001:db8::'), 'apply'),
            (('10.10.10.3', '10.256.0.1', '8.8.8.8'), None),
            (('8.8.8.8', '8.8.4.4'), 'RANDOM'),
            (('128.224.144.130', '147.11.57.128', '147.11.57.133'), 'apply'),
        ],
        ids=id_gen
    )
    def test_change_dns_settings(self, new_dns_servers, with_action_option):
        """
        Test changing the DNS servers of the system under test


        Args:
            - new_dns_servers(list): IP addresses of new DNS servers to change to.
                Both IPv4 and IPv6 are supported.

        Test Setups:
            - Do nothing, and delegate to the class-scope fixture to save the currently in-use DNS servers

        Test Steps:
            - Set the new DNS servers via CLI
            - Verify the DNS settings are successfully changed
            - Check the changes are saved to persistent storage

        Test Teardown:
            - Do nothing, and delegate to the class-scope fixture to restore the original DNS servers

        Notes:
            - This TC covers SysInv 5) Change the DNS server IP addresses using CLI
        """

        LOG.tc_step('Validate the input IPs')
        ip_addr_list = []
        expect_fail = False
        for server in new_dns_servers:
            ip_addr = network_helper.get_ip_address_str(server)
            if not ip_addr:
                # we know it will fail, for invalid IPs will be rejected
                LOG.info('Found invalid IP:{}'.format(server))
                ip_addr_list.append(server)
                expect_fail = True
                continue
            ip_addr_list.append(ip_addr)

        if not ip_addr_list:
            skip('No valid IPs input for DNS servers, skip the test')
            return

        LOG.tc_step('\nSave the current DNS servers')
        old_dns_servers = system_helper.get_dns_servers()
        LOG.info('OK, current DNS servers: "{}" are saved\n'.format(old_dns_servers))

        if with_action_option is not None and with_action_option.upper() == 'RANDOM':
            with_action_option = ''.join(random.choice(string.ascii_lowercase) for _ in range(6))

        LOG.tc_step('\nAttempt to change the DNS servers to: {}'.format(ip_addr_list))
        code, msg = system_helper.set_dns_servers(fail_ok=expect_fail,
                                                  auth_info=Tenant.get('admin'),
                                                  nameservers=ip_addr_list,
                                                  with_action_option=with_action_option,
                                                  con_ssh=None)

        if expect_fail:
            assert 1 == code, 'Request to change DNS servers to invalid IP: "{}" should be rejected, msg:"{}"'.format(
                ip_addr_list, msg)

            LOG.info('OK, attempt was rejected as expected to change DNS to: "{}"\n'.format(ip_addr_list))

            LOG.tc_step('Verify DNS servers remain UNCHANGED as old: "{}"'.format(old_dns_servers))
            code, output = self.wait_for_dns_changed(old_dns_servers)
            assert code == 0, \
                'In configuration DNS servers should remain unchanged:\nbefore: "{}"\nnow: "{}"'.format(
                    old_dns_servers, output)
        else:
            assert 0 == code, 'Failed to change DNS servers to: "{}", msg: "{}"'.format(msg, ip_addr_list)

            LOG.tc_step('Verify in DB changed to new servers: {}'.format(ip_addr_list))
            acutal_dns_servers = system_helper.get_dns_servers()

            assert list(acutal_dns_servers) == list(ip_addr_list), \
                'DNS servers were not changed, \nexpected:"{}"\nactual:"{}"\n'.format(ip_addr_list, acutal_dns_servers)

            LOG.info('OK, in DB, DNS servers changed to new IPs: "{}"\n'.format(ip_addr_list))

            LOG.tc_step('Verify in configuration, DNS should change after wait {} seconds'.format(
                SysInvTimeout.DNS_SERVERS_SAVED))

            LOG.info('Check if DNS changed or not in configuration\n')

            if with_action_option is None or with_action_option == 'apply':
                LOG.info('In this case, configuration should be updated with new DNS:{}'.format(ip_addr_list))
                code, output = self.wait_for_dns_changed(ip_addr_list)
                assert code == 0, \
                    'DNS in configuration is different from requested:\ninput:"{}"\n"in config: {}"'.format(
                        ip_addr_list, output)
            else:
                LOG.info('In this case, configuration should remain UNCHANGED as old: "{}"'.format(old_dns_servers))
                code, output = self.wait_for_dns_changed(old_dns_servers)
                assert code == 0, \
                    'Saved DNS servers should remain unchanged:\nbefore: "{}"\nnow: "{}"'.format(
                        old_dns_servers, output)

        LOG.info('OK, test setting DNS to "{}" passed'.format(ip_addr_list))
