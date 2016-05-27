import re
from pytest import mark
from utils.ssh import ControllerClient
from utils.tis_log import LOG
from consts.cgcs import UUID
from keywords import system_helper
from consts.auth import Tenant
from utils import cli, table_parser
# This test case is  to verify the query alarm and logs using event list.
# Mainly it starts on with generating alarm alarm id 300.005 Critical major minot and not applicable and query them.


@mark.parametrize(
    ("suppress"),[
        'clear_alarm',
        'set_alarm'])


def test_alarm_suppression(suppress):
    """
       Verify suppression and unsuppression of active alarm and query alarms.

       Test Setup:
           - Generate alarms according to severity
       Test Steps:
            Suppress alarms
            Verify alarm supressed
            Unsuppressed alarm
            Verify unsuppressed in active alarm list.
       Test Teardown:
           - None

    """
    limit = 1
    alarmid = '300.005'
    LOG.tc_step('Test setup')
    con_ssh_act = ControllerClient.get_active_controller()
    alarm_log_generate_str = "fmClientCli -c  \"### ###" + alarmid + "###set###system.vm###host=compute-0.vm=$i### ###"\
                             "critical### ###processing-error###Automation Generate### ###True###True###\""
    #alarm_generate_succ = generate_alarm_log(con_ssh=con_ssh_act, alarm_str=alarm_log_generate_str, maxi=int(limit))
    #assert alarm_generate_succ, "Alarm Generated"
    query_alarm_history = system_helper.get_events(con_ssh=con_ssh_act,show_only='alarms')
    alarm_id_list = table_parser.get_column(query_alarm_history, 'Event Log ID')
    print(alarm_id_list)
    print('###################')
    print(set(alarm_id_list))
    exit()
    assert len(query_alarm_history) > 1, "Alarm " + alarmid + " not found in active list  "
    LOG.tc_step('Alarm Suppressed .')
    assert suppress_unsuppress_alarm(alarm_id=alarmid, con_ssh=con_ssh_act, suppress=True), "Alarm suppressed for " \
                                                                                            "alarm ID " + alarmid
    query_active_alarm = system_helper.get_alarms(con_ssh=con_ssh_act, query_key='alarm_id', query_value=alarmid,
                                                  query_type='string')
    assert bool(query_active_alarm), "Alarm ID " + alarmid + "found in Active list"
    LOG.tc_step('Alarm Unsuppressed .')
    assert suppress_unsuppress_alarm(alarm_id=alarmid, con_ssh=con_ssh_act, suppress=False), "Alarm suppressed for " \
                                                                                             "alarm  ID  " + alarmid


def get_alarm_suppress_list(uuid=True, query_type=None, con_ssh=None, auth_info=Tenant.ADMIN):

    """
        Get a list of suppressed alarm ids.
        Args:
            uuid (bool): whether to show uuid
            con_ssh (SSHClient):
            auth_info (dict):

    Returns:
        dict: events table in format: {'headers': <headers list>, 'values': <list of table rows>}
    """
    args = ''
    if uuid:
        args += ' --uuid'
    args += ' --nowrap --nopaging'
    table_ = table_parser.table(cli.system('alarm-suppress-list', args, ssh_client=con_ssh, auth_info=auth_info))
    return table_


def suppress_unsuppress_alarm(alarm_id=None,con_ssh=None,suppress=True):
    """
        suppress alarm by uuid
        Args:
            uuid : string
            con_ssh (SSHClient):
            suppress booolean Ture or false (If true suppress false unsuppress)


    Returns:
        success/failure
    """
    if not alarm_id :
        return False
    query_alarm_suppress_list = get_alarm_suppress_list(con_ssh)
    if suppress:
        alarm_idx = {"SuppressedAlarm ID's": alarm_id, 'Status': 'unsuppressed'}
        clistr = 'alarm-suppress --alarm_id'
    else:
        alarm_idx = {"SuppressedAlarm ID's": alarm_id, 'Status': 'suppressed'}
        clistr = 'alarm-unsuppress --alarm_id'

    get_uuid = table_parser.get_values(table_=query_alarm_suppress_list, target_header='UUID', strict=True,
                                           **alarm_idx)
    print(get_uuid)
    if len(get_uuid) == 1:
        output = cli.system(clistr, positional_args=get_uuid, ssh_client=con_ssh)
        print(output)
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

