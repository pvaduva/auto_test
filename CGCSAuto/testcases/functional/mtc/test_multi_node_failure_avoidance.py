import time
from datetime import datetime

from pytest import fixture, mark, skip

from utils.tis_log import LOG
from consts.stx import EventLogID, HostAvailState
from keywords import system_helper, vlm_helper, common
from testfixtures.vlm_fixtures import reserve_unreserve_all_hosts_module, unreserve_hosts_module    # Used in fixture


@fixture(scope='module', autouse=True)
def revert(request):
    """ Revert to pre-test mnfa parameters after test """
    #skip("Force reboot hosts not ready to test")

    if system_helper.is_aio_system():
        skip("Not applicable on small systems")

    mnfa_threshold_default_val = system_helper.get_service_parameter_values(service='platform', section='maintenance',
                                                                            name='mnfa_threshold')
    mnfa_timeout_default_val = system_helper.get_service_parameter_values(service='platform', section='maintenance',
                                                                          name='mnfa_timeout')

    def restore_default_parameters():
        LOG.fixture_step('Check MNFA service parameter values and revert if needed')
        mnfa_threshold_current_val = system_helper.get_service_parameter_values(service='platform',
                                                                                section='maintenance',
                                                                                name='mnfa_threshold')
        mnfa_timeout_default_current_val = system_helper.get_service_parameter_values(service='platform',
                                                                                      section='maintenance',
                                                                                      name='mnfa_timeout')
        alarms = system_helper.get_alarms(alarm_id=EventLogID.CONFIG_OUT_OF_DATE)
        if alarms or mnfa_threshold_current_val != mnfa_threshold_default_val or mnfa_timeout_default_val != \
                mnfa_timeout_default_current_val:
            system_helper.modify_service_parameter(service='platform', section='maintenance', name='mnfa_threshold',
                                                   apply=False, value=mnfa_threshold_default_val[0])
            system_helper.modify_service_parameter(service='platform', check_first=False, section='maintenance',
                                                   name='mnfa_timeout', apply=True, value=mnfa_timeout_default_val[0])

    request.addfinalizer(restore_default_parameters)


@mark.parametrize(('mnfa_timeout', 'mnfa_threshold'), [
    (120, 2),
    # (150, 3),
    (300, 5),
])
@mark.trylast
def test_multi_node_failure_avoidance(reserve_unreserve_all_hosts_module, mnfa_timeout, mnfa_threshold):
    """
    Test multi node failure avoidance
    Args:
        mnfa_timeout
        mnfa_threshold
        reserve_unreserve_all_hosts_module: test fixture to reserve unreserve all vlm nodes for lab under test

    Setups:
        - Reserve all nodes in vlm

    Test Steps:

        - Power off compute/storage nodes in vlm using multi-processing to simulate a power outage on computes
        - Power on all nodes compute nodes
        - Wait for nodes to become degraded state during the mnfa mode
        - Wait for nodes to become active state
        - Check new event is are created for multi node failure
        - Verify the time differences between multi node failure enter and exit in the event log equal to configured
          mnfa thereshold value.

    """

    hosts_to_check = system_helper.get_hosts(availability=(HostAvailState.AVAILABLE, HostAvailState.ONLINE))
    hosts_to_test = [host for host in hosts_to_check if 'controller' not in host]

    if len(hosts_to_test) < mnfa_threshold:
        skip("Compute and storage host count smaller than mnfa threshhold value")
    elif len(hosts_to_test) > mnfa_threshold+1:
        hosts_to_test = hosts_to_test[:mnfa_threshold+1]

    LOG.info("Online or Available hosts before power-off: {}".format(hosts_to_check))
    start_time = common.get_date_in_format(date_format='%Y-%m-%d %T')

    LOG.tc_step('Modify mnfa_timeout parameter to {}'.format(mnfa_timeout))
    system_helper.modify_service_parameter(service='platform', section='maintenance',
                                           name='mnfa_timeout', apply=True, value=str(mnfa_timeout))
    system_helper.modify_service_parameter(service='platform', section='maintenance',
                                           name='mnfa_threshold', apply=True, value=str(mnfa_threshold))

    try:
        LOG.tc_step("Power off hosts and check for degraded state: {}".format(hosts_to_test))
        vlm_helper.power_off_hosts_simultaneously(hosts=hosts_to_test)
        time.sleep(20)
        degraded_hosts = system_helper.get_hosts(availability=HostAvailState.DEGRADED, hostname=hosts_to_check)
    finally:
        LOG.tc_step("Power on hosts and ensure they are recovered: {}".format(hosts_to_test))
        vlm_helper.power_on_hosts(hosts=hosts_to_test, reserve=False, hosts_to_check=hosts_to_check, check_interval=20)

    assert sorted(degraded_hosts) == sorted(hosts_to_test), 'Degraded hosts mismatch with powered-off hosts'

    LOG.tc_step("Check MNFA duration is the same as MNFA timeout value via system event log")
    active_con = system_helper.get_active_controller_name()
    entity_instance_id = 'host={}.event=mnfa_enter'.format(active_con)
    first_event = system_helper.wait_for_events(num=1, timeout=70, start=start_time, fail_ok=True, strict=False,
                                                event_log_id=EventLogID.MNFA_MODE, field='Time Stamp',
                                                entity_instance_id=entity_instance_id)
    entity_instance_id = 'host={}.event=mnfa_exit'.format(active_con)
    second_event = system_helper.wait_for_events(num=1, timeout=70, start=start_time, fail_ok=False, strict=False,
                                                 event_log_id=EventLogID.MNFA_MODE, field='Time Stamp',
                                                 entity_instance_id=entity_instance_id)
    pattern = '%Y-%m-%dT%H:%M:%S'
    event_duration = datetime.strptime(second_event[0][:-7], pattern) - datetime.strptime(first_event[0][:-7], pattern)
    event_duration = event_duration.total_seconds()
    assert abs(event_duration - mnfa_timeout) <= 1, 'MNFA event duration {} is different than MNFA timeout value {}'.\
        format(event_duration, mnfa_timeout)
