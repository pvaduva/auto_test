import re
from utils.ssh import ControllerClient
from utils.tis_log import LOG
from consts.cgcs import UUID
from keywords import system_helper
from utils import cli, table_parser
# This test case is  to verify the query alarm and logs using event list.
# Mainly it starts on with generating alarm alarm id 300.005 Critical major minot and not applicable and query them.


def test_alarm_suppression():
    """
       Test logs is to verify log generation of Critical Major Minor of alarms and logs
       Args:
           test_event_list event_option and Severity

       Test Setup:
           - Generate alarms according to severity
       Test Steps:
           - Query alarms/logs with severity
           - Verify generated alarm was success.
       Test Teardown:
           - None
    """
    limit = 1
    alarmid = '300.005'
    LOG.tc_step('Generate alarms.')
    con_ssh_act = ControllerClient.get_active_controller()
    alarm_log_generate_str = "fmClientCli -c  \"### ###" + alarmid + "###set###system.vm###host=compute-0.vm=$i### ###"\
                             "critical### ###processing-error###Automation Generate### ###True###True###\""
    alarm_generate_succ = generate_alarm_log(con_ssh=con_ssh_act,alarm_str=alarm_log_generate_str,maxi=int(limit))
    assert alarm_generate_succ, "Alarm Generated"
    query_active_alarm = system_helper.get_alarms(con_ssh=con_ssh_act,query_key='alarm_id',query_value=alarmid,
                                                  query_type='string')
    assert len(query_active_alarm) > 1, "Alarm " + alarmid + " not found in active list  "
    LOG.tc_step('Alarm Suppressed .')
    assert suppress_unsuppress_alarm(alarm_id=alarmid, con_ssh=con_ssh_act,suppress=True), "Alarm suppressed for " \
                                                                                              "alarm ID " + alarmid
    query_active_alarm = system_helper.get_alarms(con_ssh=con_ssh_act, query_key='alarm_id', query_value=alarmid,
                                                  query_type='string')
    assert bool(query_active_alarm), "Alarm ID " + alarmid + "found in Active list"
    LOG.tc_step('Alarm Unsuppressed .')
    assert suppress_unsuppress_alarm(alarm_id=alarmid, con_ssh=con_ssh_act, suppress=False), "Alarm suppressed for " \
                                                                                             "alarm  ID  " + alarmid


def suppress_unsuppress_alarm(alarm_id=None, con_ssh=None, suppress=True):
    """
        suppress alarm by uuid
        Args:
            alarm_id: string
            con_ssh (SSHClient):
            suppress booolean Ture or false (If true suppress false unsuppress)

    Returns:
        success/failure
    """
    if not alarm_id :
        return False
    query_alarm_suppress_list = system_helper.get_suppressed_alarms(uuid=True, con_ssh=con_ssh)
    if suppress:
        alarm_idx = {"SuppressedAlarm ID's": alarm_id, 'Status': 'unsuppressed'}
        clistr = 'alarm-suppress --alarm_id'
    else:
        alarm_idx = {"SuppressedAlarm ID's": alarm_id, 'Status': 'suppressed'}
        clistr = 'alarm-unsuppress --alarm_id'
    get_uuid = table_parser.get_values(table_=query_alarm_suppress_list, target_header='UUID', strict=True, **alarm_idx)
    if len(get_uuid) == 1:
        output = cli.system(clistr, positional_args=get_uuid, ssh_client=con_ssh)
        invalid_input = re.search('Invalid input for field', output)
        if invalid_input:
            return False
        else:
            return True
    else:
        return True


def generate_alarm_log(con_ssh = None , alarm_str='', maxi=0):
    con_ssh = ControllerClient.get_active_controller()
    for i in range(maxi):
        rtn_code, output = con_ssh.exec_cmd(cmd=alarm_str)
        # check UUID returned.
        uuid_in_output = re.search(UUID, output)
        if not uuid_in_output:
            return False
    else:
        return True

