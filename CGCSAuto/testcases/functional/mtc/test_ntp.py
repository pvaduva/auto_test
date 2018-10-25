from utils.tis_log import LOG
from utils import cli, table_parser
from consts.cgcs import NtpPool
from keywords import host_helper, system_helper


def test_ntp_alarm_in_sync_with_ntpq_stats():
    for host in system_helper.get_controllers():
        LOG.tc_step("Check ntp alarm and 'ntpq -pn'")
        host_helper.wait_for_ntp_sync(host=host, fail_ok=False)


def test_system_ntp_modify():
    """
    Test that ntp servers were initially configured and can be reconfigured

    Test Steps:
        - Execute system ntp-show
        - Verify that ntpservers field contains a list of 3 ntp servers
        - Update ntp with new ntp servers
        - Lock/unlock controllers to get rid of config out of date alarm
        - After lock and unlock verify that alarms cleared
    """

    LOG.tc_step("Check 'system ntp-show' contains expected fields")
    table_ = table_parser.table(cli.system('ntp-show'))
    expt_sub_fields = ['uuid', 'ntpservers', 'isystem_uuid', 'created_at', 'updated_at']

    actual_fields = table_parser.get_column(table_, 'Property')
    LOG.tc_step("Actual ntp fields Names are {}".format(actual_fields))
    assert set(expt_sub_fields) <= set(actual_fields), "Some expected fields are not included in system show table."

    LOG.tc_step("Modify 'system ntp-modify' and verify that it contains expected fields")
    ntp_pool = NtpPool.NTP_POOL_1
    if sorted(system_helper.get_ntp_vals(rtn_val='ntpservers')[0].split(',')) == sorted(ntp_pool.split(',')):
        ntp_pool = NtpPool.NTP_POOL_2

    system_helper.modify_ntp(ntp_servers=ntp_pool)


def test_system_ntp_modify_reject_too_many_servers():
    """
    Test that attempting to configure more than 3 ntp servers is rejected

    Test Steps:
        - Attempt to configure more than 3 ntp servers
        - Verify that the operation is rejected and that
        - system ntp-modify exits with return code 1
    """

    LOG.tc_step("Test system ntp-modify is rejected if more than 3 NTP servers defined in the list")
    code, output = system_helper.modify_ntp(ntp_servers=NtpPool.NTP_POOL_TOO_LONG, fail_ok=True,
                                            wait_with_best_effort=True)

    assert 1 == code, 'Expect ntp-modify is not rejected with more than 3 NPT servers defined'


def test_system_ntp_modify_reject_server_name_too_long():
    """
    Test that attempting to configure more than 3 ntp servers is rejected

    Test Steps:
        - Attempt to configure ntp server with longer than 255 characters
        - Verify that the operation is rejected and that
        - system ntp-modify exits with return code 1
    """

    LOG.tc_step("Test system ntp-modify is rejected if server name is > than 255 characters")
    code, output = system_helper.modify_ntp(ntp_servers=NtpPool.NTP_NAME_TOO_LONG, fail_ok=True,
                                            wait_with_best_effort=True)

    assert 1 == code, 'Expect ntp-modify is not rejected with server name longer than 255 characters'
