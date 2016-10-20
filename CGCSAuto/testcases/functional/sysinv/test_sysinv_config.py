from random import randrange
import time

from pytest import mark
from pytest import fixture

from utils import cli, table_parser
from utils.tis_log import LOG
from utils.ssh import ControllerClient
from consts.auth import Tenant
from consts.cgcs import SystemType
from consts.timeout import SysInvTimeout
from keywords import system_helper
from keywords import network_helper


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
    code, msg = system_helper.set_system_info(fail_ok=True, con_ssh=None, auth_info=Tenant.ADMIN,
                                              system_type='"' + change_to_system_type + '"')

    LOG.tc_step('Verify system rejected to change System Type to {}'.format(change_to_system_type))
    assert 1 == code, msg


class TestRetentionPeriod:
    """
    Test modification of Retention Period of the TiS system
    """

    PM_SETTING_FILE = '/etc/ceilometer/ceilometer.conf'  # file where the Retention Period is stored
    MIN_RETENTION_PERIOD = 3600  # seconds of 1 hour, minimum value allowed
    MAX_RETENTION_PERIOD = 31536000  # seconds of 1 year, maximum value allowed
    SEARCH_KEY_FOR_RENTION_PERIOD = r'_time_to_live'

    @fixture(scope='class', autouse=True)
    def backup_restore_rention_period(self, request):
        """
        Fixture to save the current retention period and restore it after test

        Args:
            request: request passed in to the fixture.

        """

        LOG.info('Backup Retention Period')
        table_ = table_parser.table(cli.system('pm-show'))
        self.retention_period = table_parser.get_value_two_col_table(table_, 'retention_secs')
        LOG.info('Current Retention Period is {}'.format(self.retention_period))

        def restore_rention_period():
            LOG.info('Restore Retention Period to its orignal value {}'.format(self.retention_period))
            system_helper.set_retention_period(fail_ok=True, con_ssh=None, period=int(self.retention_period))

        request.addfinalizer(restore_rention_period)


    @mark.parametrize(
        "new_retention_period", [
            -1,
            MIN_RETENTION_PERIOD - 1,
            randrange(MIN_RETENTION_PERIOD, MAX_RETENTION_PERIOD + 1),
            MAX_RETENTION_PERIOD + 1,
        ])
    def test_modify_retention_period(self, new_retention_period):
        """
        Test change the 'retention period' to new values.

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

        LOG.tc_step('Check if the modification attempt will fail based on the input value')
        if new_retention_period < self.MIN_RETENTION_PERIOD or new_retention_period > self.MAX_RETENTION_PERIOD:
            expect_fail = True
        else:
            expect_fail = False
        LOG.tc_step('Attempt to change to new value:{}'.format(new_retention_period))
        code, msg = system_helper.set_retention_period(fail_ok=expect_fail, auth_info=Tenant.ADMIN,
                                                       period=new_retention_period)
        LOG.tc_step('Check if CLI succeeded')
        if expect_fail:
            assert 1 == code, msg
            return  # we're done here when expecting failing
        else:
            assert 0 == code, 'Failed to change Retention Period to {}'.format(new_retention_period)

        LOG.tc_step('Wait for {} seconds'.format(SysInvTimeout.RETENTION_PERIOD_SAVED))
        time.sleep(SysInvTimeout.RETENTION_PERIOD_SAVED)

        LOG.tc_step('Verify the new value is saved into correct file:{}'.format(self.PM_SETTING_FILE))
        controller_ssh = ControllerClient.get_active_controller()

        cmd_get_saved_retention_periods = "fgrep --color='never' {} {}". \
            format(self.SEARCH_KEY_FOR_RENTION_PERIOD, self.PM_SETTING_FILE)
        code, output = controller_ssh.exec_sudo_cmd(cmd_get_saved_retention_periods, expect_timeout=20)

        LOG.info('Cmd={}\nRetention periods in-use:\n{}'.format(cmd_get_saved_retention_periods, output))
        assert 0 == code, 'Failed to get Retention Period from file: {}'.format(self.PM_SETTING_FILE)

        for line in output.splitlines():
            rec = line.strip()
            if rec and not rec.startswith('#'):
                saved_period = int(rec.split('=')[1])
                assert new_retention_period == saved_period, \
                    'Failed to update Retention Period for {}, expected:{}, saved in file:{} '. \
                        format(rec.split('=')[0], new_retention_period, saved_period)


class TestDnsSettings:
    """
    Test modifying the settings about DNS servers
    """

    DNS_SETTING_FILE = '/etc/resolv.conf'

    @fixture(scope='class', autouse=True)
    def backup_restore_dns_settings(self, request):
        """
        Fixture to save the current DNS servers and restore them after test

        Args:
            request: request passed in by py.test system

        """
        self.dns_servers = system_helper.get_dns_servers(con_ssh=None)
        LOG.info('Save current DNS-servers:{}'.format(self.dns_servers))

        def restore_dns_settings():
            LOG.info('Restore the DNS-servers to the original:{}'.format(self.dns_servers))
            system_helper.set_dns_servers(fail_ok=False, con_ssh=None, auth_info=Tenant.ADMIN,
                                          nameservers=self.dns_servers)
            # nameservers=','.join(self.dns_servers))

        request.addfinalizer(restore_dns_settings)


    @mark.parametrize(
        'new_dns_servers', [
            ('128.224.144.130', '147.11.57.128', '147.11.57.133'),
            ('10.10.10.3', '10.256.0.1', '8.8.8.8'),
            ('fd00:0:0:21::5', '2001:db8::'),
            (3232235521, 333333, 333),
            (3232235521, b'\xC0\xA8\x00\x01'),
        ]
    )
    def test_change_dns_settings(self, new_dns_servers):
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
                break
            ip_addr_list.append(ip_addr)

        LOG.tc_step('Attempt to change the DNS servers to: {}'.format(new_dns_servers))
        code, msg = system_helper.set_dns_servers(fail_ok=expect_fail, con_ssh=None, auth_info=Tenant.ADMIN,
                                                  nameservers=ip_addr_list)

        if expect_fail:
            assert 1 == code, msg
            return
        else:
            assert 0 == code, 'Failed to change DNS setting, msg={}'.format(msg)

        LOG.tc_step('Wait {} seconds'.format(SysInvTimeout.DNS_SERVERS_SAVED))
        time.sleep(SysInvTimeout.DNS_SERVERS_SAVED)

        LOG.tc_step('Check if the changes are saved into persistent storage')
        controller_ssh = ControllerClient.get_active_controller()

        cmd_get_saved_dns = 'cat {}'.format(self.DNS_SETTING_FILE)
        code, output = controller_ssh.exec_cmd(cmd_get_saved_dns, expect_timeout=20)
        assert 0 == code, 'Failed to get saved DNS settings: {}'.format(cmd_get_saved_dns)

        LOG.info('Find saved DNS servers:{}'.format(output))
        saved_dns = []
        for line in output.splitlines():
            if line.strip().startswith('nameserver'):
                saved_dns.append(line.strip().split()[1])

        LOG.info('Verify all input DNS servers are saved')
        assert set(ip_addr_list).issubset(set(saved_dns)), \
            'Saved DNS servers are different from the input DNS servers'
