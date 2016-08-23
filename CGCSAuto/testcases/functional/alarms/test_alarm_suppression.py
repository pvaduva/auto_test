import re
from utils.ssh import ControllerClient
from utils.tis_log import LOG
from utils import cli,table_parser
from consts.cgcs import UUID
from keywords import system_helper
# This test case is  to verify Alarm Suppression on Active alarm list (US77193 –FM: Alarm Suppression)

#jira CGTS-4489 need to be fixed Test will fail.
def test_alarm_suppression():
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
    system_helper.unsuppress_all(fail_ok=True)
    LOG.tc_step("Generate ALARM")
    assert alarm_generate_succ, "Alarm Generated"
    query_active_alarm = system_helper.get_alarms_table(query_key='alarm_id', query_value=alarm_id,
                                                        query_type='string')
    assert len(query_active_alarm) > 1, "Alarm " + alarm_id + " not found in active list  "
    LOG.tc_step(alarm_id+' Alarm Suppressed .')
    suppress_=system_helper.get_suppressed_alarms(uuid=True)
    ### Convert ALARMID to UUID
    # TODO: Update after Jira fix.CGTS-4356 No need to conver after jira fix
    alarm_id_uuid = table_parser.get_values(table_= suppress_, target_header='UUID',
                                            **{"Suppressed Alarm ID's": alarm_id})
    retcode, output = system_helper.suppress_alarm(alarm_id=alarm_id)
    assert retcode == 0, output
    query_active_alarm = system_helper.get_alarms_table(query_key='alarm_id', query_value=alarm_id,
                                                        query_type='string')
    assert bool(query_active_alarm), "Alarm ID " + alarm_id + " found in Active list"
    LOG.tc_step('Generate Alarm again .and Verify not in the Active list')
    alarm_generate_succ = generate_alarm_log(alarm_str=alarm_log_generate_str, maxi=int(limit))
    assert alarm_generate_succ, "Active Alarm Generated again "
    query_active_alarm = system_helper.get_alarms_table(query_key='alarm_id', query_value=alarm_id,
                                                        query_type='string')
    assert bool(query_active_alarm), "Alarm ID " + alarm_id + "found in Active list"
    LOG.tc_step('Alarm Unsuppressed .')
    retcode, output = system_helper.unsuppress_alarm(alarm_id=alarm_id)
    assert retcode == 0, output
    active_alarm_uuid = system_helper.get_alarms_table(uuid=True, query_key='alarm_id', query_value=alarm_id,
                                                       query_type='string')
    uuid_val = active_alarm_uuid['values'][0][0]
    retcode, output = delete_alarm_log(uuid=uuid_val)
    assert retcode == 0, output


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


def delete_alarm_log(con_ssh=None, uuid=None):
    if uuid is None:
        return 1
    cli.system(cmd="alarm-delete", positional_args=uuid, ssh_client=con_ssh)
    query_active_alarm = system_helper.get_alarms_table(query_key='UUID', query_value=uuid, query_type='string')
    if not bool(query_active_alarm):
        return 1, "Alarm " + uuid + " was not deleted"
    return 0, "Alarm ID " + uuid + " was deleted"
