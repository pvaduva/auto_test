from utils.tis_log import LOG
from keywords import host_helper, system_helper
from pytest import mark

from utils import cli, table_parser

from consts.cgcs import EventLogID, NtpPool
from time import sleep


def test_ntp_alarm_in_sync_with_ntpq_stats():
    for host in system_helper.get_controllers():
        LOG.tc_step("Check ntp alarm and 'ntpq -pn'")
        host_helper.wait_for_ntp_sync(host=host, fail_ok=False)


def test_system_ntp_modify():
    """
    Test that ntp servers were initially configured

    Args:
        none

    Setups:
        none

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

    actual_fields = table_parser.get_column(table_, 'Value')
    LOG.tc_step("Actual ntp fields Values are {}".format(actual_fields))

    LOG.tc_step("Modify 'system ntp-modify' and verify that it contains expected fields")
    new_ntp_ = "ntpservers={}".format(NtpPool.NTP_POOL_2)
    exitcode, output = cli.system('ntp-modify', new_ntp_, rtn_list=True, fail_ok=False)
    LOG.tc_step("ntp-modify exitcode:{} output:{}".format(exitcode,output))
    assert exitcode == 0 , "system ntp-modify did not exit with 0"

    sleep(5)
    LOG.tc_step ("Checking config status of controllers and lock/unlock to clear")
    if host_helper.get_hostshow_value('controller-0', 'config_status') == 'Config out-of-date':
        host_helper.lock_unlock_controllers()

    LOG.tc_step("Verifying that config out of date alarms cleared...")
    system_helper.wait_for_alarms_gone([EventLogID.CONFIG_OUT_OF_DATE, ], fail_ok=False)



def test_system_ntp_modify_reject_too_many_servers():
    """
    Test that attempting to configure more than 3 ntp servers is rejected

    Args:
        none

    Setups:
        none

    Test Steps:
        - Attempt to configure more than 3 ntp servers
        - Verify that the operation is rejected and that
        - system ntp-modify exits with return code 1
    """

    LOG.tc_step("Test system ntp-modify is rejected if more than 3 NTP servers defined in the list")
    new_ntp_ = "ntpservers={}".format(NtpPool.NTP_POOL_TOO_LONG)
    exitcode, output = cli.system('ntp-modify', new_ntp_, rtn_list=True, fail_ok=True)
    LOG.tc_step("ntp-modify exitcode:{} output:{}\r".format(exitcode,output))
    assert exitcode == 1 , "system ntp-modify did not exit with 1"



def test_system_ntp_modify_reject_server_name_too_long():
    """
    Test that attempting to configure more than 3 ntp servers is rejected

    Args:
        none

    Setups:
        none

    Test Steps:
        - Attempt to configure ntp server with longer than 255 characters
        - Verify that the operation is rejected and that
        - system ntp-modify exits with return code 1
    """

    LOG.tc_step("Test system ntp-modify is rejected if server name is > than 255 characters")
    new_ntp_ = "ntpservers={}".format(NtpPool.NTP_NAME_TOO_LONG)
    exitcode, output = cli.system('ntp-modify', new_ntp_, rtn_list=True, fail_ok=True)
    LOG.tc_step("ntp-modify exitcode:{} output:{}".format(exitcode, output))
    assert exitcode == 1, "system ntp-modify did not exit with 1"











