import re
from pytest import mark
from utils.ssh import ControllerClient
from utils.tis_log import LOG
from consts.cgcs import UUID
from keywords import system_helper
# This test case is  to verify the query alarm and logs using event list.
# Mainly it starts on with generating alarm alarm id 300.005 Critical major minot and not applicable and query them.
#US24127,US36505 and US36506 US70391 –FM: Merge Query/Display of Historical Alarms and Customer Logs

@mark.parametrize(
    ("event_option", "severity"), [
        ('alarms', 'critical'),
        ('alarms', 'major'),
        ('alarms', 'minor'),
        ('logs', 'not-applicable'),
        ('logs', 'critical')])
def test_event_list_vms(event_option, severity):
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
        alarm_log_generate_str = "fmClientCli -c  \"### ###300.005###set###system.vm###host=compute-0.vm=$i### ###" + \
                         severity + "### ###processing-error###Automation Generate### ###True###True###\""
    else:
        alarm_log_generate_str = "fmClientCli -c  \"### ###600.005###msg###system.vm###host=compute-0.vm=$i### ### " + \
                        severity + "###'oam' Test###Automation Generate###cpu-cycles-limit-" \
                                   "exceeded### ###True###True### \""
    alarm_generate_succ = generate_alarm_log(alarm_log_generate_str, int(limit))
    assert alarm_generate_succ, "Alarm / LOG Generated"

    LOG.tc_step('Query ' + event_option + ' ' + severity)
    query_tab = system_helper.get_events(num=limit, show_only=event_option, query_key='severity', query_value=severity)

    LOG.tc_step('Verify test result')
    check_flag = query_check(len(query_tab['values']), int(limit) - 1)
    assert check_flag != 1, " Test Failed "


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
