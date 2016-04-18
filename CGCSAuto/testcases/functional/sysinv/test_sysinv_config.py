from pytest import mark
from pytest import fixture
from utils import cli, table_parser
from utils.tis_log import LOG
from consts.auth import Tenant
from consts.cgcs import SystemType
from setup_consts import LAB_NAME
from keywords import system_helper


def test_system_type():
    """
    Verify the System Type can be retrieved from SysInv and is correct

    Args:

    Skip conditions:

    Prerequisites:

    Test Setups:

    Test Steps:
        - Determine the System Type based on whether the system is CPE or not
        - Retrieve the System Type information from SystInv
        - Compare the types and verify they are the same, fail the test case otherwise

    Test Teardown:

    """

    LOG.tc_step('Determine the real System Type for {}'.format(LAB_NAME))
    if system_helper.is_small_footprint():
        expt_system_type = SystemType.CPE
    else:
        expt_system_type = SystemType.STANDARD

    LOG.tc_step('Get System Type from system inventory')
    table_ = table_parser.table(cli.system('show'))
    displayed_system_type = table_parser.get_value_two_col_table(table_, 'system_type')

    LOG.tc_step('Verify the expected System Type is the same as that from System Inventory')
    assert expt_system_type == displayed_system_type, 'Expected system_type is: {}; Displayed system type: {}.'.\
        format(expt_system_type, displayed_system_type)


def test_system_type_is_readonly():
    """
    Verify System Type is readonly

    Args:

    Skip conditions:

    Prerequisites:

    Test Setups:

    Test Steps:
        - Determine the System Type based on whether the system is CPE or not
        - Attempt to modify the System Type to a different type
        - Compare the types and verify they are the same, fail the test case otherwise

    Test Teardown:

    """

    LOG.tc_step('Determine the real System Type for {}'.format(LAB_NAME))
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
    assert code == 1, msg


class TestRetentionPeriod:
    """
    Test modification of Retention Period of the TiS system
    """

    MIN_RETENTION_PERIOD = 3600
    MAX_RETENTION_PERIOD = 31536000

    @fixture(scope='class', autouse=True)
    def backup_restore_rention_period(self, request):
        """
        Fixture to save the current retention period and restore it after test

        Args:
            request: request passed in to the fixture.

        Test Steps:
            - Retrieve and save the Retention Period value during setup

        Test Teardown:
            - Restore the Retention Period to the saved (orignal) value during teardown

        """

        LOG.info('Backup Retention Period')
        table_ = table_parser.table(cli.system('pm-show'))
        self.retention_period = table_parser.get_value_two_col_table(table_, 'retention_secs')
        LOG.info('Current Retention Prioid is {}'.format(self.retention_period))

        def restore_rention_period():
            LOG.info('Restore Retention Period to its orignal value {}'.format(self.retention_period))
            system_helper.set_retention_period(fail_ok=True, con_ssh=None, retention_period=self.retention_period)

        request.addfinalizer(restore_rention_period)


    @mark.parametrize(
            "new_retention_period", [
                -1,
                MIN_RETENTION_PERIOD-1,
                4567,
                MAX_RETENTION_PERIOD + 1,
            ])
    def test_modify_retention_period(self, new_retention_period):
        """
        Test change the 'retention period' to new values.

        Args:
            new_retention_period(int):

        Skip Conditions:
            -

        Prerequisites:
            -

        Test Setups:
            - Do nothing, and delegate to the class-scope fixture to save the currently in-use Retention Period

        Test Steps:
            - Change the Retention Period with CLI

        Test Teardown:
            - Do nothing, and delegate to the class-scope fixture to restore the original value of Retention Period
            before test

        Notes:
            - We can determine the range of accepted values on the running system in stead of parameterizing
            on hardcoded values
        """

        LOG.tc_step('Check if the modification attempt will fail based on the input value')
        if new_retention_period < self.MIN_RETENTION_PERIOD or new_retention_period > self.MAX_RETENTION_PERIOD:
            expect_fail = True
        else:
            expect_fail = False
        code, msg = system_helper.set_retention_period(fail_ok=expect_fail, con_ssh=None, auth_info=Tenant.ADMIN,
                                                       retention_period=new_retention_period)


