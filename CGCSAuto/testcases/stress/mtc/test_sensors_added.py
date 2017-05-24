#!/usr/bin/env python3

"""
BMC Sensor Testing

Copyright (c) 2017 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.

This module verifies that the sensors were correctly added.
"""

from pytest import mark, skip, fixture

from utils.tis_log import LOG
from utils.ssh import ControllerClient

from consts.cgcs import EventLogID, HostTask
from consts.timeout import HostTimeout
from keywords import system_helper, host_helper, bmc_helper
from testfixtures.recover_hosts import HostsToRecover


# Configure the connection to a BMC server
# The following BMC servers are available: yow-cgcs-quanta-1 to yow-cgcs-quanta-5
mac_addr = "2C:60:0C:AD:9A:A3"
ip_addr = '128.224.151.124'   # -- yow-cgcs-quanta-5
bm_type = 'quanta'
bm_username = 'admin'
bm_password = 'admin'

HOST = ''
SUPPRESSED = False


@fixture(scope='module', autouse=True)
def sensor_data_fit(request):
    LOG.fixture_step("Get hosts with sensor enabled")
    hosts = system_helper.get_hostnames()
    bmc_hosts = []
    for host in hosts:
        if bmc_helper.get_sensors_table(host=host)['values']:
            bmc_hosts.append(host)
    
    if not bmc_hosts:
        skip("No sensor added for any host in system")
    
    LOG.fixture_step("(module) touch /var/run/fit/sensor_data")
    con_ssh = ControllerClient.get_active_controller()
    con_ssh.exec_sudo_cmd('mkdir -p /var/run/fit/', fail_ok=False)
    con_ssh.exec_sudo_cmd('touch /var/run/fit/sensor_data', fail_ok=False)

    def _revert():
        LOG.fixture_step("(module) rm /var/run/fit/sensor_data")
        con_ssh = ControllerClient.get_active_controller()
        con_ssh.exec_sudo_cmd('rm /var/run/fit/sensor_data', fail_ok=False)
    # request.addfinalizer(_revert)
    
    return bmc_hosts


@fixture(scope='function', autouse=True)
def cleanup_on_failure(request):
    global HOST
    HOST = ''

    def cleanup():
        if HOST:
            bmc_helper.clear_events(HOST)

            system_helper.wait_for_alarm_gone(alarm_id=EventLogID.BMC_SENSOR_ACTION, entity_id=HOST, strict=False,
                                              timeout=30)

        global SUPPRESSED
        if SUPPRESSED:
            host = SUPPRESSED
            for sensorgroup_name in bmc_helper.get_sensorgroup_name(host):
                bmc_helper.unsuppress_sensorgroup(sensorgroup_name, host)
            SUPPRESSED = False
    request.addfinalizer(cleanup)


# @fixture(scope='module')
# @mark.parametrize('host', [
#     'controller-1'
# ])
# def bmc_test_prep(request, host):
#     LOG.fixture_step("Enable the BMC connections on the host: {}".format(host))
# 
#     bmc_helper.clear_events(host)
#     cli.system('host-update', '{} bm_mac={}    bm_ip={} bm_type={} bm_username={} bm_password={}'.
#                format(host, mac_addr, ip_addr, bm_type, bm_username, bm_password), fail_ok=True, rtn_list=True)
# 
#     def teardown():
#         LOG.fixture_step("Disable all BMC connections")
# 
#         bmc_helper.clear_events(host)
#         cli.system('host-update', '{} bm_type={} bm_username={} bm_password={}'.
#                    format(host, 'None', bm_username, bm_password), fail_ok=True, rtn_list=True)
# 
#     request.addfinalizer(teardown)
#     return


# # @mark.usefixtures('bmc_test_prep')
# @mark.parametrize('host', [
#     'controller-1'
# ])
# def _test_sensors_found(host, sensor_data_fit):
#     """
#     Get the list of sensors added after BMC enabled.
#
#     Test Steps:
#         - Get the list of every unlocked host
#         - Connect to a specified host and list the sensors enabled on it
#
#     """
#     bmc_hosts = sensor_data_fit
#     if host not in bmc_hosts:
#         skip("{} is not configured with BMC sensor".format(host))
#
#     LOG.tc_step("Listing the sensors found on {}".format(host))
#     LOG.info("{} state: {}".format(host, host_helper.get_hostshow_value(host, field='administrative')))
#     res, out = cli.system('host-sensor-list', host, fail_ok=True, rtn_list=True)
#
#     assert res == 0, "FAIL: No sensors for {} were found".format(host)
#
#
# # @mark.usefixtures('bmc_test_prep')
# @mark.parametrize('host', [
#     'controller-1'
# ])
# def _test_sensorgroups_found(host, sensor_data_fit):
#     """
#     Get the list of sensor groups added after BMC enabled.
#
#     Test Steps:
#         - Creates a list of every unlocked host
#         - Connect to a specified host and list the sensors enabled on it
#
#     """
#     bmc_hosts = sensor_data_fit
#     if host not in bmc_hosts:
#         skip("{} is not configured with BMC sensor".format(host))
#
#     LOG.tc_step("Listing the sensorgroups found on {}".format(host))
#     res, out = cli.system('host-sensorgroup-list', host, fail_ok=True, rtn_list=True)
#
#     assert res == 0, "FAIL: No sensorgroups for {} were found".format(host)


@mark.parametrize('host', [
    'controller-1'
])
def _test_suppress_unsuppress_sensors(host, sensor_data_fit):
    """
    Validate that each sensor can be suppressed and unsuppressed.

    Test Steps:
        - Check the state of the host
        - Iterate through each sensor on the host and suppress/unsuppress each sensor

    """
    bmc_hosts = sensor_data_fit
    if host not in bmc_hosts:
        skip("{} is not configured with BMC sensor".format(host))
        
    LOG.tc_step("Suppressing and Unsuppressing sensors found on {}".format(host))
    LOG.info("{} state: {}".format(host, host_helper.get_hostshow_value(host, field='administrative')))

    # Suppress each sensor
    for sensor_name in bmc_helper.get_sensor_name(host):
        LOG.tc_step("Validating that sensor: {} "
                    "can be suppressed.".format(sensor_name))
        res = bmc_helper.suppress_sensor(sensor_name, host)
        assert res is True, "FAIL: Sensor suppression " \
                            "fail for sensor:{} on {}".format(sensor_name, host)

    # Unsuppress each sensor
    for sensor_name in bmc_helper.get_sensor_name(host):
        LOG.tc_step("Validating that sensor: {} "
                    "can be unsuppressed.".format(sensor_name))
        res = bmc_helper.unsuppress_sensor(sensor_name, host)
        assert res is True, "FAIL: Sensor unsuppression " \
                            "fail for sensor:{} on {}".format(sensor_name, host)


@mark.parametrize('host', [
    'controller-1'
])
def _test_suppress_unsuppress_sensorgroups(host, sensor_data_fit):
    """
    Validate that each sensorgroup can be suppressed and unsuppressed.

    Test Steps:
        - Check the state of the host
        - Iterate through each sensorgroup and suppress/unsuppress it

    """
    bmc_hosts = sensor_data_fit
    if host not in bmc_hosts:
        skip("{} is not configured with BMC sensor".format(host))

    LOG.tc_step("Suppressing and Unsuppressing sensorgroups found on {}".format(host))

    for sensorgroup_name in bmc_helper.get_sensorgroup_name(host):
        LOG.tc_step("Validating that sensorgroup: {} "
                    "can be suppressed.".format(sensorgroup_name))
        res = bmc_helper.suppress_sensorgroup(sensorgroup_name, host)
        assert res is True, "FAIL: Sensor suppression " \
                            "fail for sensor:{} on {}".format(sensorgroup_name, host)

    for sensorgroup_name in bmc_helper.get_sensorgroup_name(host):
        LOG.tc_step("Validating that sensorgroup: {} "
                    "can be unsuppressed.".format(sensorgroup_name))
        res = bmc_helper.unsuppress_sensorgroup(sensorgroup_name, host)
        assert res is True, "FAIL: Sensor unsuppression " \
                            "fail for sensor:{} on {}".format(sensorgroup_name, host)

#
# @mark.parametrize('host', [
#     'controller-1'
# ])
# def _test_sensor_alarm_status(host, sensor_data_fit):
#     """
#     Validate that the appropriate alarm is raised for the appropriate sensor action.
#
#     Test Steps:
#         - Creates a list of every unlocked host
#         - Iterate through each host and list the sensors associated with it
#
#     """
#     bmc_hosts = sensor_data_fit
#     if host not in bmc_hosts:
#         skip("{} is not configured with BMC sensor".format(host))
#
#     alarm_generated = False
#     LOG.tc_step("Getting the sensor active alarm status on {}".format(host))
#
#     for sensor_name in bmc_helper.get_sensor_name(host):
#         (alarm_generated, alarm_uuid, alarm_id, alarm_severity) = bmc_helper.get_sensor_alarm(host, sensor_name)
#         print('Alarm Generated: {} UUID: {} ID: {} Severity: {}'.
#               format(alarm_generated, alarm_uuid, alarm_id, alarm_severity))
#         if alarm_generated:
#             break
#
#     assert alarm_generated is True, "FAIL: No alarms found for sensor on {}".format(host)

#
# @mark.parametrize('host', [
#     'controller-1'
# ])
# def _test_sensorgroup_alarm_status(host, sensor_data_fit):
#     """
#     Get the list of sensors added after BMC enabled.
#
#     Test Steps:
#         - Creates a list of every unlocked host
#         - Iterate through each host and list the sensors associated with it
#
#     """
#     bmc_hosts = sensor_data_fit
#     if host not in bmc_hosts:
#         skip("{} is not configured with BMC sensor".format(host))
#     alarm_generated = False
#     LOG.tc_step("Getting the sensor active alarm status on {}".format(host))
#
#     for sensor_groupname in bmc_helper.get_sensorgroup_name(host):
#         (alarm_generated, alarm_uuid, alarm_id, alarm_severity) = \
#             bmc_helper.get_sensor_alarm(host, sensor_groupname)
#         print('Sensorgroup name: {}'.format(sensor_groupname))
#         print('Alarm Generated: {} UUID: {} ID: {} Severity: {}'.format
#               (alarm_generated, alarm_uuid, alarm_id, alarm_severity))
#         if alarm_generated:
#             break
#
#     assert alarm_generated is True, "FAIL: No alarms found for sensor on {}".format(host)
#
#
# @mark.parametrize(('host', 'eventlevel', 'action'), [
#     ('controller-1', 'actions_critical', 'alarm'),
#     ('controller-1', 'actions_critical', 'log'),
#     ('controller-1', 'actions_critical', 'ignore'),
#     ('controller-1', 'actions_critical', 'power-cycle'),
#     ('controller-1', 'actions_critical', 'reset'),
#     ('controller-1', 'actions_major', 'alarm'),
#     ('controller-1', 'actions_major', 'log'),
#     ('controller-1', 'actions_major', 'ignore'),
#     ('controller-1', 'actions_major', 'power-cycle'),
#     ('controller-1', 'actions_major', 'reset'),
#     ('controller-1', 'actions_minor', 'alarm'),
#     ('controller-1', 'actions_minor', 'log'),
#     ('controller-1', 'actions_minor', 'ignore'),
#     ('controller-1', 'actions_minor', 'power-cycle'),
#     ('controller-1', 'actions_minor', 'reset'),
# ])
# def _test_set_sensor_action(host, eventlevel, action, sensor_data_fit):
#     """
#     This test case verifies that it is possible to successfully set the sensor
#     action to one of the acceptable values: log, alarm, power-cycle, reset,
#     and ignore.
#
#     Currently it is executed on one node but can be expanded to validate all nodes
#     in a system.
#
#     Test Steps:
#         - Check the state of the host
#         - Iterate through each sensor on the host
#         - Test the ability to configure the action for each sensor
#
#     """
#     bmc_hosts = sensor_data_fit
#     if host not in bmc_hosts:
#         skip("{} is not configured with BMC sensor".format(host))
#
#     LOG.tc_step("Modifying the sensor action on {}".format(host))
#     LOG.info("{} state: {}".format(host, host_helper.get_hostshow_value(host, field='administrative')))
#
#     for sensor_name in bmc_helper.get_sensor_name(host):
#         LOG.tc_step("Validating that sensor: {}  can be set to sensor action: {} "
#                     "for event level: {}".format(sensor_name, action, eventlevel))
#         res = bmc_helper.set_sensor_action(sensor_name, host, event_level=eventlevel, action=action)
#
#         assert res is True, "FAIL: Modifying sensor action failed for sensor on {}".format(host)


@mark.parametrize(('host', 'eventlevel', 'action'), [
    ('controller-1', 'actions_critical_group', 'log'),
    ('controller-1', 'actions_critical_group', 'ignore'),
    ('controller-1', 'actions_critical_group', 'power-cycle'),
    ('controller-1', 'actions_critical_group', 'reset'),
    ('controller-1', 'actions_critical_group', 'alarm'),
    ('controller-1', 'actions_major_group', 'alarm'),
    ('controller-1', 'actions_major_group', 'ignore'),
    ('controller-1', 'actions_major_group', 'log'),
    ('controller-1', 'actions_minor_group', 'alarm'),
    ('controller-1', 'actions_minor_group', 'log'),
    ('controller-1', 'actions_minor_group', 'ignore'),
])
def _test_set_sensorgroup_action(host, eventlevel, action, sensor_data_fit):
    """
    This test case verifies that it is possible to successfully set the
    sensorgroup action to one of the acceptable values: log, alarm,
    power-cycle, reset, and ignore.

    Currently this test is parameterized to execute on one node but can be expanded to
    validate all nodes in a system.


    Test Steps:
        - Check the state of the host
        - Iterate through each sensorgroup on the host
        - Test the ability to configure the action for each sensorgroup

    """
    bmc_hosts = sensor_data_fit
    if host not in bmc_hosts:
        skip("{} is not configured with BMC sensor".format(host))

    LOG.tc_step("Modifying the sensorgroup action on {}".format(host))

    for sensorgroup_name in bmc_helper.get_sensorgroup_name(host):
        LOG.tc_step("Validating that sensorgroup: {} "
                    "can be set to sensor action: {} "
                    "for event level: {}".format(sensorgroup_name, action, eventlevel))
        res = bmc_helper.set_sensorgroup_action(sensorgroup_name, host, eventlevel, action)

        assert res is True, "FAIL: Modifying sensor action failed for sensor on {}".format(host)

#
# @mark.parametrize(('host', 'eventlevel', 'action',
#                    'expected_host_state',
#                    'expected_alarm_state',
#                    'suppressionlevel'), [
#     ('controller-1', 'actions_critical', 'log', 'degraded', 'yes_alarm', 'unsuppressed'),
#     ('controller-1', 'actions_critical', 'ignore', 'available', 'no_alarm', 'unsuppressed'),
#     ('controller-1', 'actions_critical', 'power-cycle', 'degraded', 'yes_alarm', 'unsuppressed'),
#     ('controller-1', 'actions_critical', 'reset', 'degraded', 'yes_alarm', 'unsuppressed'),
#     # ('controller-1', 'actions_critical', 'alarm', 'degraded', 'yes_alarm', 'unsuppressed'),
#     ('controller-1', 'actions_major', 'alarm', 'degraded', 'yes_alarm', 'unsuppressed'),
#     # ('controller-1', 'actions_major', 'ignore', 'available', 'no_alarm', 'unsuppressed'),
#     ('controller-1', 'actions_major', 'log', 'degraded', 'no_alarm', 'unsuppressed'),
#     ('controller-1', 'actions_minor', 'alarm', 'degraded', 'no_alarm', 'unsuppressed'),
#     ('controller-1', 'actions_minor', 'log', 'available', 'no_alarm', 'unsuppressed'),
#     # ('controller-1', 'actions_minor', 'ignore', 'available', 'no_alarm', 'unsuppressed'),
# ])
# def _test_sensor_action_taken(host,
#                              eventlevel,
#                              action,
#                              expected_host_state,
#                              expected_alarm_state,
#                              suppressionlevel, sensor_data_fit):
#     """
#     Verify that the sensor action taken for an event is valid.
#
#     Test Steps:
#         - Get a sensor to test
#         - Set the event level and expected action
#         - trigger an out-of-scope event for that sensor
#         - verify that the expected action is taken
#
#     """
#     bmc_hosts = sensor_data_fit
#     if host not in bmc_hosts:
#         skip("{} is not configured with BMC sensor".format(host))
#
#     global HOST
#     HOST = host
#
#     # Get a sensor to validate
#     if eventlevel == 'actions_critical':
#         sensor_stat = 'cr'
#     elif eventlevel == 'actions_major':
#         sensor_stat = 'nc'
#     elif eventlevel == 'actions_minor':
#         sensor_stat = 'lna'
#     else:
#         raise ValueError("invalid eventlevel: {}".format(eventlevel))
#
#     for sensor_name in bmc_helper.get_sensor_name(host):
#         LOG.tc_step("Validating that sensor: {} can be set to sensor action: {} for event level: {}".
#                     format(sensor_name, action, eventlevel))
#
#         # Set the event level and action
#         res = bmc_helper.set_sensor_action(sensor_name, host, event_level=eventlevel, action=action, audit_interval=11)
#
#         assert res is True, "FAIL: Modifying sensor action failed for " \
#                             "sensor on {}".format(host)
#
#         entity_id = 'host={}.sensor={}'.format(host, sensor_name)
#
#         LOG.tc_step("Trigger event for sensor: {}".format(sensor_name))
#         bmc_helper.trigger_event(host, sensor_name, sensor_stat)
#
#         res = system_helper.wait_for_alarm(alarm_id=EventLogID.BMC_SENSOR_ACTION, timeout=30, entity_id=entity_id,
#                                            strict=False, fail_ok=True)[0]
#         LOG.tc_step("Check the alarm status for sensor: {}".format(sensor_name))
#         # alarm_generated, alarm_uuid, alarm_id, alarm_severity = bmc_helper.get_sensor_alarm(host, sensor_name)
#
#         if expected_alarm_state == 'yes_alarm':
#             assert res, "FAIL: Alarm expected but no alarms found for sensor on {}".format(host)
#         else:
#             assert not res, "FAIL: Alarm raised unexpectedly for sensor on {}".format(host)
#
#         LOG.tc_step("Check the host status for sensor: {}".format(sensor_name))
#         if suppressionlevel is 'suppressed':
#             expected_host_state = "available"
#
#         assert bmc_helper.check_host_state(host, expected_host_state=expected_host_state)
#
#         LOG.tc_step("Clear event for sensor: {}".format(sensor_name))
#         bmc_helper.clear_events(host)
#         LOG.tc_step("Check the alarm clears for sensor: {}".format(sensor_name))
#
#         system_helper.wait_for_alarm_gone(alarm_id=EventLogID.BMC_SENSOR_ACTION, entity_id=entity_id, strict=False,
#                                           timeout=30)
#     HOST = ''


@mark.parametrize(('host', 'eventlevel', 'action',
                   'expected_host_state',
                   'expected_alarm_state',
                   'event_type',
                   'suppressionlevel'), [
    ('compute-0', 'actions_critical_group', 'alarm', 'degraded', 'yes_alarm', 'cr', 'unsuppressed'),
    ('compute-0', 'actions_critical_group', 'ignore', 'available', 'no_alarm', 'cr', 'unsuppressed'),
    ('compute-0', 'actions_critical_group', 'log', 'available', 'no_alarm', 'cr', 'unsuppressed'),
    ('compute-0', 'actions_critical_group', 'ignore', 'available', 'no_alarm', 'cr', 'unsuppressed'),
    ('controller-0', 'actions_critical_group', 'alarm', 'degraded', 'yes_alarm', 'cr', 'unsuppressed'),
    ('controller-1', 'actions_critical_group', 'power-cycle', 'power-off', 'yes_alarm', 'cr', 'unsuppressed'),
    ('controller-1', 'actions_critical_group', 'reset', 'offline', 'yes_alarm', 'nr', 'unsuppressed'),
    ('controller-1', 'actions_critical_group', 'alarm', 'degraded', 'yes_alarm', 'nr', 'unsuppressed'),
    ('controller-1', 'actions_major_group', 'alarm', 'degraded', 'yes_alarm', 'nc', 'unsuppressed'),
    ('controller-1', 'actions_major_group', 'ignore', 'available', 'no_alarm', 'nc', 'unsuppressed'),
    ('controller-1', 'actions_major_group', 'power-cycle', 'degraded', 'yes_alarm', 'nc', 'unsuppressed'),
    ('controller-1', 'actions_major_group', 'log', 'degraded', 'no_alarm', 'nc', 'unsuppressed'),
    ('controller-1', 'actions_minor_group', 'alarm', 'degraded', 'no_alarm', 'minor', 'unsuppressed'),
    ('controller-1', 'actions_minor_group', 'log', 'available', 'no_alarm', 'minor', 'unsuppressed'),
    ('controller-1', 'actions_minor_group', 'ignore', 'available', 'no_alarm', 'minor', 'unsuppressed'),
])
def test_sensorgroup_action_taken(host,
                                  eventlevel,
                                  action,
                                  expected_host_state,
                                  expected_alarm_state,
                                  event_type,
                                  suppressionlevel, sensor_data_fit):
    """
    Verify that the sensorgroup action taken for an event is valid.

    Test Steps:
        - Get a sensorgroup to test
        - Set the event level and expected action
        - trigger an out-of-scope event for that sensorgroup
        - verify that the expected action is taken

    """
    bmc_hosts = sensor_data_fit
    if host not in bmc_hosts:
        skip("{} is not configured with BMC sensor".format(host))
        
    global HOST
    HOST = host

    if suppressionlevel == 'suppressed':
        global SUPPRESSED
        SUPPRESSED = host

    # Get a sensor to validate
    for sensorgroup_name in bmc_helper.get_sensorgroup_name(host):
        LOG.tc_step("Validating that sensorgroup: {} "
                    "can be set to sensor action: {} "
                    "for event level: {}".format(sensorgroup_name, action,
                                                 eventlevel))

        # Set the event level and action
        res = bmc_helper.set_sensorgroup_action(sensorgroup_name, host, event_level=eventlevel, action=action)

        assert res is True, "FAIL: Modifying sensorgroup action failed for " \
                            "sensor on {}".format(host)

        # Get a sensor that is part of the sensorgroup
        sensor_name = bmc_helper.get_first_sensor_from_sensorgroup(sensorgroup_name, host)
        entity_id = 'host={}.sensor={}'.format(host, sensor_name)

        LOG.tc_step("Trigger event for sensorgroup: {} and sensor name: {}".
                    format(sensorgroup_name, sensor_name))

        bmc_helper.set_sensorgroup_audit_interval(sensorgroup_name, host, audit_value=10)

        if event_type in ['power-cycle', 'reset']:
            HostsToRecover.add(host)

        bmc_helper.trigger_event(host, sensor_name, event_type)

        res = system_helper.wait_for_alarm(alarm_id=EventLogID.BMC_SENSOR_ACTION, entity_id=entity_id,
                                           timeout=45, strict=False, fail_ok=True)[0]

        LOG.tc_step("Check sensor status and alarm for {}".format(sensor_name))

        if expected_alarm_state == 'yes_alarm':
            assert res, "FAIL: Alarm expected but no alarms found for sensor on {}".format(host)
        else:
            assert not res, "FAIL: Alarm raised but no alarms were expected for sensor on {}".format(host)

        LOG.tc_step("Check the host status for sensor: {}".format(sensor_name))
        if suppressionlevel is 'suppressed':
            expected_host_state = "available"

        host_helper.wait_for_host_states(host, timeout=120, fail_ok=False, availability=expected_host_state)
        if event_type == 'power-cycle':
            host_helper.wait_for_host_states(host, timeout=20, task='Critical Event Power-Cycle', strict=False)

        LOG.tc_step("Check the alarm clears and host in available state after clearing events")
        bmc_helper.clear_events(host)
        system_helper.wait_for_alarm_gone(alarm_id=EventLogID.BMC_SENSOR_ACTION, entity_id=host, strict=False,
                                          timeout=45)
        wait_time = 1800 if event_type == 'power-cycle' else HostTimeout.REBOOT
        host_helper.wait_for_host_states(host, fail_ok=False, timeout=wait_time, availability='available')

    HOST = ''

#
# @mark.parametrize(('host', 'eventlevel', 'action', 'expected_host_state', 'expected_alarm_state', 'suppressionlevel'), [
#     ('compute-0', 'actions_critical', 'log', 'degraded', 'yes_alarm', 'unsuppressed'),
# ])
# def _test_sensor_value_find(host,
#                            eventlevel,
#                            action,
#                            expected_host_state,
#                            expected_alarm_state,
#                            suppressionlevel, sensor_data_fit):
#     """
#     Verify that the sensor action taken for an event is valid.
#
#     Test Steps:
#         - Get a sensor to test
#         - Set the event level and expected action
#         - trigger an out-of-scope event for that sensor
#         - verify that the expected action is taken
#     """
#     bmc_hosts = sensor_data_fit
#     if host not in bmc_hosts:
#         skip("{} is not configured with BMC sensor".format(host))
#
#     # Get a sensor to validate
#     for sensor_name in bmc_helper.get_sensor_name(host):
#         LOG.tc_step("Validating that sensor: {} "
#                     "can be set to sensor action: {} "
#                     "for event level: {}".format(sensor_name, action,
#                                                  eventlevel))
#
#         LOG.tc_step("Lower the audit level for sensor: {}".format(sensor_name))
#         bmc_helper.set_sensor_audit_interval(sensor_name, host, audit_value=11)
#
#         LOG.tc_step("Trigger event for sensor: {}".format(sensor_name))
#         bmc_helper.trigger_event(host, sensor_name, 'major')


# @mark.usefixtures('bmc_test_prep')
@mark.parametrize(('host', 'event_type', 'action_level', 'action', 'suppression', 'expt_alarm', 'expt_host_avail',
                   'new_action', 'new_suppression', 'new_expt_alarm', 'new_expt_host_avail'), [
    ('compute-0', 'cr', 'action_critical', 'alarm', 'unsuppressed', 'yes_alarm', 'degraded', 'ignore', None, 'no_alarm', 'available'),
    ('compute-0', 'cr', 'action_critical', 'log', 'unsuppressed', 'yes_alarm', 'available', 'alarm', None, 'yes_alarm', 'degraded'),
    ('compute-0', 'cr', 'action_critical', 'ignore', 'unsuppressed', 'no_alarm', 'available', 'log', None, 'yes_alarm', 'available'),
    ('compute-0', 'nr', 'action_critical', 'ignore', 'unsuppressed', 'no_alarm', 'available', 'alarm', None, 'yes_alarm', 'degraded'),
    ('compute-0', 'nr', 'action_critical', 'alarm', 'suppressed', 'no_alarm', 'available', 'reset', None, 'no_alarm', 'available'),
    ('compute-0', 'nr', 'action_critical', 'log', 'suppressed', 'no_alarm', 'available', None, 'unsuppressed', 'yes_alarm', 'available'),
    ('controller-0', 'nc', 'action_major', 'alarm', 'unsuppressed', 'yes_alarm', 'degraded', 'ignore', 'unsuppressed', 'no_alarm', 'available'),
    ('controller-0', 'nc', 'action_major', 'alarm', 'suppressed', 'no_alarm', 'available', None, 'unsuppressed', 'yes_alarm', 'degraded'),
    ('controller-0', 'nc', 'action_major', 'log', 'unsuppressed', 'no_alarm', 'available', 'alarm', 'unsuppressed', 'yes_alarm', 'degraded'),
    ('controller-0', 'nc', 'action_major', 'ignore', 'unsuppressed', 'no_alarm', 'available', 'log', 'unsuppressed', 'no_alarm',   'available'),
    ('controller-0', 'nc', 'action_major', 'ignore', 'unsuppressed', 'no_alarm', 'available', 'alarm', 'unsuppressed', 'yes_alarm', 'degraded'),
    ('controller-0', 'mnc', 'action_minor', 'alarm', 'unsuppressed', 'yes_alarm', 'available', 'ignore', 'unsuppressed', 'no_alarm', 'available'),
    ('controller-0', 'mnc', 'action_minor', 'log', 'unsuppressed', 'no_alarm', 'available', 'alarm', 'unsuppressed', 'yes_alarm', 'available'),
    ('controller-0', 'mnc', 'action_minor', 'ignore', 'unsuppressed', 'no_alarm', 'available', 'log', 'unsuppressed', 'no_alarm', 'available'),
    ('controller-0', 'mnc', 'action_minor', 'ignore', 'unsuppressed', 'no_alarm', 'available', 'alarm', 'unsuppressed', 'yes_alarm', 'available'),
])
def test_transition_sensorgroup_actions(host,
                                        event_type,
                                        action_level,
                                        action,
                                        suppression,
                                        expt_alarm,
                                        expt_host_avail,
                                        new_action,
                                        new_suppression,
                                        new_expt_alarm,
                                        new_expt_host_avail,
                                        sensor_data_fit):
    """
    Verify the sensorgroup can properly transition from one action to another when
    an event remains unchanged.

    Test Steps:
        - Get a sensorgroup to test
        - Set the event level and expected action
        - trigger an out-of-scope event for that sensorgroup
        - verify that the expected action is taken
        - transition the sensorgroup action
        - verify the new action is taken
    """
    bmc_hosts = sensor_data_fit
    if host not in bmc_hosts:
        skip("{} is not configured with BMC sensor".format(host))
        
    global HOST
    HOST = host
    # Get a sensor to validate
    for sensorgroup_name in bmc_helper.get_sensorgroup_name(host):
        LOG.tc_step("Validating that sensorgroup: {} can be set to sensor action: {} for event level: {}".
                    format(sensorgroup_name, action, action_level))

        # Set the sensorgroup action, suppress state, and audit interval
        suppress = True if suppression == 'suppressed' else False
        bmc_helper.modify_sensorgroup(host, sensorgroup_name, value='name', audit_interval=10, suppress=suppress,
                                      **{action_level: action})

        # Get a sensor that is part of the sensorgroup
        sensor_name = bmc_helper.get_first_sensor_from_sensorgroup(sensorgroup_name, host)
        entity_id = 'host={}.sensor={}'.format(host, sensor_name)

        LOG.tc_step("Trigger event for sensorgroup: {} and sensor name: {}".format(sensorgroup_name, sensor_name))
        bmc_helper.trigger_event(host, sensor_name, event_type)

        LOG.tc_step("Check the alarm status for sensor: {}".format(sensor_name))
        res = system_helper.wait_for_alarm(alarm_id=EventLogID.BMC_SENSOR_ACTION, entity_id=entity_id,
                                           timeout=45, regex=True, strict=False, fail_ok=True)[0]

        if expt_alarm == 'yes_alarm':
            assert res, "FAIL: Alarm expected but no alarms found for sensor on {}".format(host)
        else:
            assert not res, "FAIL: Alarm raised but no alarms were expected for sensor on {}".format(host)

        LOG.tc_step("Check the host status for sensor: {}".format(sensor_name))
        host_helper.wait_for_host_states(host, timeout=90, availability=expt_host_avail, fail_ok=False)

        # modify sensorgroup with new action/suppression level
        LOG.tc_step("Transition sensorgroup: {} from current sensor action: {} to new sensor action: {} "
                    "for event level: {}".format(sensorgroup_name, action, new_action, action_level))
        new_suppress = True if new_suppression == 'suppressed' else False
        bmc_helper.modify_sensorgroup(host, sensorgroup_name, value='name', suppress=new_suppress,
                                      **{action_level: new_action})

        # Verify the new action is taken
        LOG.tc_step("Check alarm status after transition from {} to {} for {}".format(action, new_action, sensor_name))
        if expt_alarm == 'yes_alarm':
            is_gone = system_helper.wait_for_alarm_gone(EventLogID.BMC_SENSOR_ACTION, entity_id=entity_id,
                                                        strict=False, fail_ok=True, timeout=45)
            if new_expt_alarm == 'yes_alarm':
                assert not is_gone, "Expect alarm stays after transition from {} to {} for {}".\
                    format(action, new_action, sensor_name)
            else:
                assert is_gone, "Expect alarm gone after transition from {} to {} for {}".\
                    format(action, new_action, sensor_name)

        else:
            is_shown = system_helper.wait_for_alarm(alarm_id=EventLogID.BMC_SENSOR_ACTION, entity_id=entity_id,
                                                    timeout=45, regex=True, strict=False, fail_ok=True)[0]
            if new_expt_alarm == 'yes_alarm':
                assert is_shown, "Expect alarm after transition from {} to {} for {}".\
                    format(action, new_action, sensor_name)
            else:
                assert not is_shown, "Expect stay as no alarm after {} to {} for {}".\
                    format(action, new_action, sensor_name)

        LOG.tc_step("Check the host status for sensor: {}".format(sensor_name))
        host_helper.wait_for_host_states(host, timeout=90, availability=new_expt_host_avail, fail_ok=False)

        LOG.tc_step("Check the alarm clears and host in available state after clearing events")
        bmc_helper.clear_events(host)
        system_helper.wait_for_alarm_gone(alarm_id=EventLogID.BMC_SENSOR_ACTION, entity_id=host, strict=False,
                                          timeout=45)
        host_helper.wait_for_host_states(host, fail_ok=False, availability='available')

    HOST = ''


# @mark.usefixtures('bmc_test_prep')
@mark.parametrize(('host', 'eventlevel', 'action', 'newaction',
                   'expected_host_state',
                   'expected_alarm_state',
                   'suppressionlevel'), [
    ('compute-0', 'actions_critical_group', 'alarm', 'ignore', 'degraded', 'yes_alarm', 'unsuppressed'),
    ('compute-0', 'actions_critical_group', 'log', 'alarm', 'degraded', 'yes_alarm', 'unsuppressed'),
    ('compute-0', 'actions_critical_group', 'ignore', 'log', 'available', 'no_alarm', 'unsuppressed'),
    ('controller-1', 'actions_critical_group', 'ignore', 'alarm', 'available', 'no_alarm', 'unsuppressed'),
    ('controller-1', 'actions_critical_group', 'alarm', 'power-cycle', 'degraded', 'yes_alarm', 'unsuppressed'),
    ('controller-1', 'actions_critical_group', 'alarm', 'reset', 'degraded', 'yes_alarm', 'unsuppressed'),
])
def _test_sensorgroup_ignore_action_transition(host,
                                              eventlevel,
                                              action,
                                              newaction,
                                              expected_host_state,
                                              expected_alarm_state,
                                              suppressionlevel, sensor_data_fit):
    """
    Verify the sensorgroup can properly transition from one action to another while
    an event remains valid.

    Test Steps:
        - Get a sensorgroup to test
        - Set the event level and expected action
        - trigger an out-of-scope event for that sensorgroup
        - verify that the expected action is taken
        - transition the sensorgroup action
        - verify the new action is taken

    """
    bmc_hosts = sensor_data_fit
    if host not in bmc_hosts:
        skip("{} is not configured with BMC sensor".format(host))
    # Get a sensor to validate
    for sensorgroup_name in bmc_helper.get_sensorgroup_name(host):
        LOG.tc_step("Validating that sensorgroup: {} "
                    "can be set to sensor action: {} "
                    "for event level: {}".format(sensorgroup_name, action,
                                                 eventlevel))

        # Set the event level and action
        res = bmc_helper.set_sensorgroup_action(sensorgroup_name, host, event_level=eventlevel, action=action)

        assert res is True, "FAIL: Modifying sensorgroup action failed for " \
                            "sensor on {}".format(host)

        # Get a sensor that is part of the sensorgroup
        sensor_name = bmc_helper.get_first_sensor_from_sensorgroup(sensorgroup_name, host)

        LOG.tc_step("Trigger event for sensorgroup: {} and sensor name: {}".
                    format(sensorgroup_name, sensor_name))

        bmc_helper.set_sensorgroup_audit_interval(sensorgroup_name, host, audit_value=11)
        bmc_helper.trigger_event(host, sensor_name, 'nr')

        LOG.tc_step("Check the alarm status for sensor: {}".format(sensor_name))

        if action == 'ignore' or action == 'log':
            expected_host_state = "available"
        else:
            system_helper.wait_for_alarm(entity_id='host={}.sensor={}'.format(host, sensor_name),
                                         reason='{}'.format(sensor_name),
                                         timeout=90, regex=True, strict=False)

            alarm_generated, alarm_uuid, alarm_id, alarm_severity = \
                bmc_helper.get_sensor_alarm(host, sensor_name)

            if expected_alarm_state == 'yes_alarm':
                assert alarm_generated is True, "FAIL: Alarm expected but no " \
                                                "alarms found for " \
                                                "sensor on {}".format(host)
            else:
                assert alarm_generated is False, "FAIL: Alarm raised but no " \
                                                 "alarms were expected " \
                                                 "for sensor on {}".format(host)

        LOG.tc_step("Check the host status for sensor: {}".format(sensor_name))
        if suppressionlevel is 'suppressed':
            expected_host_state = "available"
        admin_status = bmc_helper.check_host_state(host, expected_host_state)

        assert admin_status is True, "FAIL: Unexpected host state on host {}".format(host)

        LOG.tc_step("Transition sensorgroup: {} "
                    "from current sensor action: {} "
                    "to new sensor action: {} "
                    "for event level: {}".format(sensorgroup_name, action, newaction,
                                                 eventlevel))

        # Set set a new action for the same event level
        res = bmc_helper.set_sensorgroup_action(sensorgroup_name, host,
                                                event_level=eventlevel,
                                                action=newaction)
        assert res is True, "FAIL: Modifying sensorgroup action failed for " \
                            "sensor on {}".format(host)

        # Verify the new action is taken
        if newaction == 'ignore' or newaction == 'log':
            expected_host_state = "available"

            LOG.tc_step("Wait for the alarm for sensor: {} to be cleared.".format(sensor_name))

            (alarm_generated, alarm_uuid, alarm_id, alarm_severity) = \
                bmc_helper.get_sensor_alarm(host, sensor_name)

            if expected_alarm_state == 'yes_alarm':
                assert alarm_generated is True, "FAIL: Alarm was not " \
                                                "cleared for " \
                                                "sensor on {}".format(host)
            else:
                assert alarm_generated is False, "FAIL: Alarm raised but no " \
                                                 "alarms were expected " \
                                                 "for sensor on {}".format(host)
            # assert alarm_generated is False, "FAIL: Alarm was not cleared for sensor on {}".format(host)
        else:
            LOG.tc_step("Wait for the alarm for sensor: {} to be raised.".format(sensor_name))

            system_helper.wait_for_alarm(entity_id='host={}.sensor={}'.format(host, sensor_name),
                                         reason='{}'.format(sensor_name),
                                         timeout=90, regex=True, strict=False)

            alarm_generated, alarm_uuid, alarm_id, alarm_severity = \
                bmc_helper.get_sensor_alarm(host, sensor_name)

            if expected_alarm_state == 'yes_alarm':
                expected_host_state = "degraded"
                assert alarm_generated is True, "FAIL: Alarm expected but no " \
                                                "alarms found for " \
                                                "sensor on {}".format(host)
            else:
                expected_host_state = "available"
                assert alarm_generated is False, "FAIL: Alarm raised but no " \
                                                 "alarms were expected " \
                                                 "for sensor on {}".format(host)

        LOG.tc_step("Check the host status for sensor: {}".format(sensor_name))
        if suppressionlevel is 'suppressed':
            expected_host_state = "available"
        admin_status = bmc_helper.check_host_state(host, expected_host_state)

        assert admin_status is True, "FAIL: Unexpected host state on host {}".format(host)

        bmc_helper.clear_events(host)


@mark.parametrize(('host', 'auditvalue'), [
    ('compute-1', '5'),
    ('compute-1', '55'),
    ('compute-1', '3600'),
])
def test_set_audit_level_values(host, auditvalue, sensor_data_fit):
    """
    Verify various settings for the audit level.

    Test Steps:
        - Get a sensorgroup to test
        - Set the audit interval value
        - verify the new audit interval value is set

    """
    bmc_hosts = sensor_data_fit
    if host not in bmc_hosts:
        skip("{} is not configured with BMC sensor".format(host))

    # Get a sensor to validate
    for sensorgroup_name in bmc_helper.get_sensorgroup_name(host):
        LOG.tc_step("Validating that the audit value for sensorgroup: {} "
                    "can be set to new value: {}".format(sensorgroup_name, auditvalue))

        # Set the audit interval value
        bmc_helper.set_sensorgroup_audit_interval(sensorgroup_name, host, auditvalue)

        # Verify that the audit interval value has been updated
        sensor_audit_interval = bmc_helper.get_sensor_audit_interval(sensorgroup_name, host)

        assert sensor_audit_interval == auditvalue, "FAIL: Modifying sensor audit interval failed for sensor on " \
                                                    "{}".format(host)
