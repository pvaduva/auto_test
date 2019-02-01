import time
from datetime import datetime
from pytest import fixture, mark, skip
from consts.reasons import SkipHypervisor
from consts.timeout import HostTimeout
from consts.cgcs import EventLogID, HostAvailState
from keywords import system_helper, host_helper, vlm_helper, common
from utils.tis_log import LOG
from testfixtures.vlm_fixtures import reserve_unreserve_all_hosts_module, unreserve_hosts_module


@fixture(scope='module', autouse=True)
def default_parameters(request):
    """
    Args:
        request:
    Test steps:
            1. Hypervisory check for more than 2 computes
            2  Capture default mnfa_threshold and mnfa_timeout
            3. Check any config out alarm or change in defaults
            3. Restore the parameters based on check

    Returns:

    """
    if system_helper.is_small_footprint():
        skip("SKIP Cannout execute this test on simplex or AIO duplex system ")
    mnfa_threshold_default_val = system_helper.get_service_parameter_values(service='platform', section='maintenance',
                                                                            name='mnfa_threshold')
    mnfa_timeout_default_val = system_helper.get_service_parameter_values(service='platform', section='maintenance',
                                                                          name='mnfa_timeout')

    def restore_default_parameters():
        LOG.info('Restoring service parameter values ')
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


@mark.parametrize(('mnfa_timeout_val', 'mnfa_threshold_val'), [
    ('120', '2'),
    ('150', '3'),
    ('300', '5'),
])
@mark.usefixtures('check_alarms')
def test_multi_node_failure_avoidance(reserve_unreserve_all_hosts_module, mnfa_timeout_val, mnfa_threshold_val):
    """
    Test multi node failure avoidance
    Args:
        mnfa_timeout_val
        mnfa_threshold_val
        reserve_unreserve_all_hosts_module: test fixture to reserve unreserve all vlm nodes for lab under test

    Setups:
        - Reserve all nodes in vlm

    Test Steps:

        - Power off all compute nodes in vlm using multi-processing to simulate a power outage on computes
        - Power on all nodes compute nodes
        - Wait for nodes to become degraded state during the mnfa mode
        - Wait for nodes to become active state
        - Check new event is are created for multi node failure
        - Verify the time differences between multi node failure enter and exit in the event log equal to configured
          mnfa thereshold value.

    """

    hypervisors = host_helper.get_up_hypervisors()
    if len(hypervisors) < int(mnfa_threshold_val):
        skip(SkipHypervisor.LESS_THAN_TWO_HYPERVISORS)

    LOG.tc_step('Capture current time')
    start_time = common.get_date_in_format(date_format='%Y-%m-%d %T')

    LOG.tc_step('Modify mnfa_timeout parameter to {}'.format(mnfa_timeout_val))
    system_helper.modify_service_parameter(service='platform', section='maintenance',
                                           name='mnfa_timeout', apply=True, value=mnfa_timeout_val)
    system_helper.modify_service_parameter(service='platform', section='maintenance',
                                           name='mnfa_threshold', apply=True, value=mnfa_threshold_val)
    hosts = system_helper.get_hostnames(availability=['available', 'online'], personality=('worker', 'storage'))
    hosts_to_check = system_helper.get_hostnames(availability=['available', 'online'], hosts=hosts)
    LOG.info("Online or Available hosts before power-off: {}".format(hosts_to_check))

    LOG.tc_step("Powering off hosts in multi-processes to simulate power outage: {}".format(hosts))
    try:
        vlm_helper.power_off_hosts_simultaneously(hosts=hosts)
    finally:
        LOG.tc_step("Wait for 10 seconds and power on hosts: {}".format(hosts))
        time.sleep(10)
        LOG.tc_step("Check all hosts switched to degraded state ")
        degraded_hosts = system_helper.get_hostnames(availability=[HostAvailState.DEGRADED], hosts=hosts_to_check)
        LOG.info("Hosts to check after power-on with degraded state: {}".format(hosts_to_check))
        vlm_helper.power_on_hosts(hosts=hosts, reserve=False, reconnect_timeout=HostTimeout.REBOOT+HostTimeout.REBOOT,
                                  hosts_to_check=hosts_to_check)

    LOG.tc_step("Check all power off hosts are switched to degraded state {}.format(hosts_to_check) ")
    assert set(degraded_hosts) == set(hosts_to_check), 'Power off hosts {} are not degraded ' \
                                                       'Not the actual degraded hosts {}'.format(degraded_hosts,
                                                                                                   hosts_to_check)

    LOG.tc_step("Check MNFA entered and exited")
    active_host_name = system_helper.get_active_controller_name()
    entity_instance_id = 'host=' + active_host_name + '\.event=mnfa_enter'
    first_event = system_helper.wait_for_events(num=1, timeout=70, start=start_time, fail_ok=True, strict=False,
                                                event_log_id=EventLogID.MNFA_MODE, rtn_val='Time Stamp',
                                                entity_instance_id=entity_instance_id)
    entity_instance_id = 'host=' + active_host_name + '\.event=mnfa_exit'
    second_event = system_helper.wait_for_events(num=1, timeout=70, start=start_time, fail_ok=False, strict=False,
                                                 event_log_id=EventLogID.MNFA_MODE, rtn_val='Time Stamp',
                                                 entity_instance_id=entity_instance_id)
    pattern = '%Y-%m-%dT%H:%M:%S'
    time_diff = datetime.strptime(second_event[0][:-7], pattern) - datetime.strptime(first_event[0][:-7], pattern)
    LOG.tc_step("Check Event tiem {} is equal to mnfa timeout value {}".format(time_diff.total_seconds(),
                                                                               mnfa_timeout_val))
    assert round(time_diff.total_seconds()) == int(mnfa_timeout_val), 'Timeout for MNFA is not equal to MNFA ' \
                                                                      'event enter exit difference'.format(
                                                                       mnfa_timeout_val, time_diff.total_seconds())
