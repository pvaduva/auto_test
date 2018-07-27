import re

from pytest import mark

from consts.cgcs import UUID
from keywords import system_helper
from utils import cli
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG


# This test case is  to verify the query alarm and logs using event list.
# Mainly it starts on with generating alarm alarm id 300.005 Critical major minot and not applicable and query them.
# US24127,US36505 and US36506 US70391 –FM: Merge Query/Display of Historical Alarms and Customer Logs


@mark.parametrize(
    ("event_option", "severity"), [
        ('alarms', 'critical'),
        ('alarms', 'major'),
        ('alarms', 'minor'),
        ('logs', 'not-applicable'),
        ('logs', 'critical')])
def test_event_list(event_option, severity):
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
    limit = 5
    LOG.tc_step('Generate alarms.')
    if event_option == 'alarms':
        alarm_log_generate_str = "fmClientCli -c  \"### ###300.005###set###system.vm### ### ###" + \
                         severity + "###Automation Test Alarm ### ###Automation Generate### ###True###True###\""
        alarm_id="300.005"
    else:
        alarm_id = "600.005"
        alarm_log_generate_str = "fmClientCli -c  \"### ###600.005###msg###system.vm###host=compute-0.vm=$i### ### " + \
                        severity + "###'oam' Test###Automation Generate###cpu-cycles-limit-" \
                                   "exceeded### ###True###True### \""
    alarm_generate_succ = generate_alarm_log(alarm_log_generate_str, int(limit))
    assert alarm_generate_succ, "Alarm / LOG Generated"

    LOG.tc_step('Query ' + event_option + ' ' + severity)
    query_tab = system_helper.get_events_table(num=limit, show_only=event_option,
                                               query_key='severity', query_value=severity)

    LOG.tc_step('Verify test result')
    check_flag = query_check(len(query_tab['values']), int(limit) - 1)
    assert check_flag != 1, " Test Failed "
    active_alarm_uuid = system_helper.get_alarms_table(uuid=True, query_key='alarm_id', query_value=alarm_id,
                                                       query_type='string')
    if event_option == 'alarms':
        uuid_val = active_alarm_uuid['values'][0][0]
        retcode, output = delete_alarm_log(uuid=uuid_val)
        assert retcode == 0, output


def query_check(length, local_limit):
    flag = 0
    if local_limit < length:
        flag = 0
    if local_limit == length:
        flag = 1
    if local_limit > length:
        flag = 1
    return flag


def generate_alarm_log(alarm_str, maxi=0):
    con_ssh = ControllerClient.get_active_controller()
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
