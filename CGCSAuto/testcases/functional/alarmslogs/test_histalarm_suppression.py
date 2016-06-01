from utils.tis_log import LOG
from keywords import system_helper
from utils import cli, table_parser

# This test case is  to verify Alarm Suppression on Event alarm list (US77193 –FM: Alarm Suppression)
def test_hist_alarm_suppression():
    """
       Verify suppression and unsuppression of active alarm and query alarms.

       Test Setup:
           - Unsuppress all the alarm
       Test Steps:
            Suppress alarms in event list
            Verify alarm supressed
            Unsuppressed  all alarm
            Verify unsuppressed in event list.
       Test Teardown:
           - None

    """
    LOG.tc_step('Test setup')
    system_helper.unsuppress_all(fail_ok=True)
    query_alarm_history = system_helper.get_events(num=100, uuid=True, show_only='alarms')
    alarm_id_list = table_parser.get_column(query_alarm_history, 'Event Log ID')
    get_suppress_list = system_helper.get_suppressed_alarms(uuid=True)
    uuid_list=[]
    for alarm_id in set(alarm_id_list):
        uuid_list.append(table_parser.get_values(table_=get_suppress_list, target_header='UUID', strict=True,
                                                 **{"Suppressed Alarm ID's": alarm_id, 'Status': 'unsuppressed'}))
    uuid_str = ''.join(str(e) for e in uuid_list)
    uuid_str = (uuid_str.strip("[\'").strip("]\'").replace('\'][\'', ','))
    LOG.tc_step('Test setup')
    output = cli.system('alarm-suppress --alarm_id', positional_args=uuid_str)
    suppressed_list= table_parser.get_values(table_=system_helper.get_suppressed_alarms(uuid=True),
                                             target_header='UUID', strict=True,**{'Status': 'suppressed'})
    assert len(uuid_list) == len(suppressed_list), "Alarm id is not suppressed Error" + output
    assert system_helper.unsuppress_all() == 0, " Un suppress all failed"

