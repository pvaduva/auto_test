from pytest import fixture

from utils.tis_log import LOG
from utils import table_parser

from keywords import system_helper

#############################################################################################################
# This test case is  to verify Alarm Suppression on Active alarm list (US77193 ▒~@~SFM: Alarm Suppression)  #
#############################################################################################################


@fixture(scope='module')
def alarm_test_prep(request):
    LOG.fixture_step("Unsuppress all events")
    system_helper.unsuppress_all_events(fail_ok=True)

    alarm_id = '300.005'
    LOG.fixture_step("Generate an system event {}".format(alarm_id))
    alarm_uuid = system_helper.generate_event(event_id=alarm_id)

    def teardown():
        LOG.fixture_step("Unsuppress all events")
        system_helper.unsuppress_all_events(fail_ok=True)

        LOG.fixture_step("Delete 300.005 alarm(s)")
        active_alarm_tab = system_helper.get_alarms_table(query_key='alarm_id', query_value='300.005')
        alarm_uuids = table_parser.get_column(active_alarm_tab, 'UUID')
        system_helper.delete_alarms(alarm_uuids)
    request.addfinalizer(teardown)

    return alarm_uuid


def test_alarm_suppression(alarm_test_prep):
    """
       Verify suppression and unsuppression of active alarm and query alarms.

       Test Setup:
           - Unsuppress all alarms
             Generate alarms
       Test Steps:

            Suppress alarms
            Verify alarm supressed
            Generate alarm again
            Verify suppressed alarms no in active
            Unsuppressed alarm
            Verify unsuppressed in active alarm list.
            Delete last active alarm
       Test Teardown:
           - Unsuppress all alarms
    """
    LOG.tc_step('Suppress generated alarm and Verify it is suppressed')
    alarm_uuid = alarm_test_prep
    query_active_alarm = system_helper.get_alarms_table(query_key='uuid', query_value=alarm_uuid)
    alarm_id = table_parser.get_values(table_=query_active_alarm, target_header='Alarm ID', **{"UUID": alarm_uuid})[0]
    assert '300.005' == alarm_id
    # alarm_id = ''.join(alarm_id)
    system_helper.suppress_event(alarm_id=alarm_id)

    LOG.tc_step('Generate Alarm again and Verify not in the Active list')
    system_helper.generate_event(event_id=alarm_id)
    alarms = system_helper.get_alarms(alarm_id=alarm_id)
    assert not alarms, "300.005 alarm appears in the active alarms table after regenerating"

    LOG.tc_step('UnSuppress alarm and verify it is unsuppressed')
    system_helper.unsuppress_event(alarm_id=alarm_id)
