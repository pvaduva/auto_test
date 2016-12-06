import re
from pytest import fixture
from utils.ssh import ControllerClient
from utils.tis_log import LOG
from utils import cli,table_parser
from consts.cgcs import UUID
from keywords import system_helper
# This test case is  to verify Alarm Suppression on Active alarm list (US77193 –FM: Alarm Suppression)

@fixture
def cleanup_alarms(request):

    def delete_alarms():
        # clear 300.005 alarm and unsuppress them if they aren't already
        alarm_id = '300.005'
        system_helper.unsuppress_alarm(alarm_id=alarm_id, check_first=True)
        active_alarm_uuid = system_helper.get_alarms_table(query_key='alarm_id', query_value='300.005',
                                                           query_type='string')
        uuid = active_alarm_uuid['values'][0][0]
        if uuid is None:
            return 1
        cli.system(cmd="alarm-delete", positional_args=uuid)
        query_active_alarm = system_helper.get_alarms_table(uuid=True, query_key='UUID',
                                                            query_value=uuid, query_type='string')
        if query_active_alarm['values']:
            LOG.info("Alarm " + uuid + " was not deleted")
        LOG.info("Alarm ID " + uuid + " was deleted")

    request.addfinalizer(delete_alarms)


#jira CGTS-4489 need to be fixed Test will fail.
def test_alarm_suppression(cleanup_alarms):
    """
       Verify suppression and unsuppression of active alarm and query alarms.

       Test Setup:
           - Generate alarms according to severity
       Test Steps:
            Suppress alarms
            Verify alarm supressed
            Generate alarm again
            Verify suppressed alarms no in active
            Unsuppressed alarm
            Verify unsuppressed in active alarm list.
            Delete Active alarm and verify
       Test Teardown:
           - None
    """
    limit = 1
    alarm_id = "300.005"
    LOG.tc_step('Generate alarms.')
    alarm_log_generate_str = "fmClientCli -c  \"### ###" + alarm_id + "###set###system.vm###Automation=### " \
                                                                      "###"\
                             "critical### ###processing-error###Automation Generate### ###True###True###\""
    alarm_generate_succ = generate_alarm_log(alarm_str=alarm_log_generate_str, maxi=int(limit))
    system_helper.unsuppress_all_events(fail_ok=True)
    LOG.tc_step("Generate ALARM")
    assert alarm_generate_succ, "Alarm Generated"
    query_active_alarm = system_helper.get_alarms_table(query_key='alarm_id', query_value=alarm_id,
                                                        query_type='string')
    assert len(query_active_alarm) > 1, "Alarm " + alarm_id + " not found in active list  "
    LOG.tc_step("Suppressing {} Alarm".format(alarm_id))
    suppress_=system_helper.get_suppressed_alarms(uuid=True)
    assert not suppress_['values'], "There are suppressed events"

    ### Convert ALARMID to UUID
    # TODO: Update after Jira fix.CGTS-4356 No need to conver after jira fix
    retcode, output = system_helper.suppress_alarm(alarm_id=alarm_id)
    assert retcode == 0, output
    query_active_alarm = system_helper.get_alarms_table(query_key='alarm_id', query_value=alarm_id,
                                                        query_type='string')
    assert not query_active_alarm['values'], "Alarm ID " + alarm_id + " found in Active list"
    LOG.tc_step('Generate Alarm again .and Verify not in the Active list')
    alarm_generate_succ = generate_alarm_log(alarm_str=alarm_log_generate_str, maxi=int(limit))
    assert alarm_generate_succ, "Active Alarm Generated again "
    query_active_alarm = system_helper.get_alarms_table(query_key='alarm_id', query_value=alarm_id,
                                                        query_type='string')
    assert not query_active_alarm['values'], "Alarm ID " + alarm_id + " found in Active list"
    LOG.tc_step('Unsuppress Alarm 300.005.')
    retcode, output = system_helper.unsuppress_alarm(alarm_id=alarm_id)
    assert retcode == 0, output

    query_active_alarm = system_helper.get_alarms_table(query_key='alarm_id', query_value=alarm_id,
                                                        query_type='string')
    assert len(query_active_alarm) > 1, "Alarm ID " + alarm_id + " not found in Active list"


def generate_alarm_log(con_ssh=None, alarm_str='', maxi=0):
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()
    if alarm_str == ' ':
        return False
    for i in range(maxi):
        rtn_code, output = con_ssh.exec_cmd(cmd=alarm_str)
        # check UUID returned.
        uuid_in_output = re.search(UUID, output)
        if not uuid_in_output:
            return False
    else:
        return True

