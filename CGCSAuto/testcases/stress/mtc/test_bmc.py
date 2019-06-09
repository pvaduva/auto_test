#!/usr/bin/env python3

"""
BMC Sensor Testing

Copyright (c) 2017 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.

This module verifies that the sensors were correctly added.
"""

import random

from pytest import mark, skip, fixture

from consts.cgcs import EventLogID, HostTask, HostAdminState, HostAvailState, HostOperState
from consts.timeout import HostTimeout
from keywords import system_helper, host_helper, bmc_helper, common
from testfixtures.recover_hosts import HostsToRecover
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG


@fixture(scope='function', autouse=True)
def check_alarms():
    pass


HOST = ''


@fixture(scope='module', autouse=True)
def sensor_data_fit(request):
    LOG.fixture_step("Get hosts with sensor enabled")
    hosts = system_helper.get_hosts()
    bmc_hosts = []
    for host in hosts:
        if bmc_helper.get_sensors_table(host=host)['values']:
            bmc_hosts.append(host)
    
    if not bmc_hosts:
        skip("No sensor added for any host in system")

    con_ssh = ControllerClient.get_active_controller()
    LOG.fixture_step("(module) Save healthy sensor data files")
    bmc_helper.backup_sensor_data_files(bmc_hosts, con_ssh=con_ssh)

    LOG.fixture_step("(module) touch /var/run/fit/sensor_data")
    con_ssh.exec_sudo_cmd('mkdir -p /var/run/fit/', fail_ok=False)
    con_ssh.exec_sudo_cmd('touch /var/run/fit/sensor_data', fail_ok=False)

    def _revert():
        LOG.fixture_step("(module) rm /var/run/fit/sensor_data")
        con_ssh_ = ControllerClient.get_active_controller()
        con_ssh_.exec_sudo_cmd('rm /var/run/fit/sensor_data', fail_ok=False)
    request.addfinalizer(_revert)
    
    return bmc_hosts


@fixture(scope='function', autouse=True)
def cleanup_on_failure(request):
    global HOST
    HOST = ''

    def cleanup():
        if HOST:
            bmc_helper.clear_events(HOST)
            system_helper.wait_for_alarm_gone(alarm_id=EventLogID.BMC_SENSOR_ACTION, entity_id=HOST, strict=False,
                                              timeout=60)
    request.addfinalizer(cleanup)


@mark.parametrize(('host', 'eventlevel', 'action',
                   'expected_host_state',
                   'expected_alarm_state',
                   'event_type',
                   'suppressionlevel'), [
    ('compute-1', 'action_critical', 'alarm', 'degraded', 'yes_alarm', 'cr', 'unsuppressed'),
    ('compute-1', 'action_critical', 'ignore', 'available', 'no_log', 'cr', 'unsuppressed'),
    ('compute-1', 'action_critical', 'log', 'available', 'yes_log', 'cr', 'unsuppressed'),
    ('compute-1', 'action_critical', 'ignore', 'available', 'no_log', 'cr', 'unsuppressed'),
    ('controller-1', 'action_critical', 'alarm', 'available', 'no_log', 'cr', 'suppressed'),
    ('compute-1', 'action_critical', 'power-cycle', 'power-off', 'yes_alarm', 'cr', 'unsuppressed'),
    ('compute-0', 'action_critical', 'reset', 'offline', 'yes_alarm', 'nr', 'unsuppressed'),
    ('controller-1', 'action_critical', 'alarm', 'degraded', 'yes_alarm', 'nr', 'unsuppressed'),
    ('controller-1', 'action_major', 'alarm', 'degraded', 'yes_alarm', 'nc', 'unsuppressed'),
    ('controller-1', 'action_major', 'ignore', 'available', 'no_log', 'nc', 'unsuppressed'),
    ('controller-1', 'action_major', 'log', 'available', 'yes_log', 'nc', 'unsuppressed'),
    ('controller-1', 'action_minor', 'alarm', 'available', 'yes_alarm', 'mn', 'unsuppressed'),
    ('controller-1', 'action_minor', 'log', 'available', 'yes_log', 'mn', 'unsuppressed'),
    ('controller-1', 'action_minor', 'ignore', 'available', 'no_log', 'mn', 'unsuppressed'),
    ('compute-1', 'action_critical', 'alarm', 'available', 'no_log', 'cr', 'suppressed'),
    ('controller-1', 'action_critical', 'log', 'available', 'no_log', 'cr', 'suppressed'),
    ('controller-1', 'action_critical', 'ignore', 'available', 'no_log', 'cr', 'suppressed'),
    ('controller-1', 'action_major', 'alarm', 'available', 'no_log', 'nc', 'suppressed'),
    ('compute-1', 'action_major', 'log', 'available', 'no_log', 'nc', 'suppressed'),
    ('compute-1', 'action_minor', 'alarm', 'available', 'no_log', 'mn', 'suppressed'),
    ('controller-1', 'action_minor', 'log', 'available', 'no_log', 'mn', 'suppressed'),

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
        # global SUPPRESSED
        # SUPPRESSED = host
        suppress = True
    else:
        suppress = False

    expt_severity = eventlevel.split('_')[-1] if 'yes' in expected_alarm_state else None

    # Get a sensor to validate
    sensorgroup_name = random.choice(bmc_helper.get_sensor_names(host, sensor_group=True))
    LOG.tc_step("Validating that sensorgroup: {} "
                "can be set to sensor action: {} "
                "for event level: {}".format(sensorgroup_name, action,
                                             eventlevel))

    # Set the event level and action
    bmc_helper.modify_sensorgroup(host, sensorgroup_name, value='name', suppress=suppress, audit_interval=10,
                                  **{eventlevel: action})

    # Get a sensor that is part of the sensorgroup
    sensor_name = bmc_helper.get_first_sensor_from_sensorgroup(sensorgroup_name, host)
    entity_id = 'host={}.sensor={}'.format(host, sensor_name)

    LOG.tc_step("Trigger event for sensorgroup: {} and sensor name: {}".
                format(sensorgroup_name, sensor_name))
    if action in ['power-cycle', 'reset']:
        HostsToRecover.add(host)

    start_time = common.get_date_in_format()
    bmc_helper.trigger_event(host, sensor_name, event_type)

    LOG.tc_step("Check sensor status and alarm for {}".format(sensor_name))
    if expected_alarm_state == 'yes_alarm':
        system_helper.wait_for_alarm(alarm_id=EventLogID.BMC_SENSOR_ACTION, entity_id=entity_id,
                                     severity=expt_severity, timeout=60, strict=False, fail_ok=False)
    else:
        events = system_helper.wait_for_events(timeout=60, num=10, event_log_id=EventLogID.BMC_SENSOR_ACTION,
                                               entity_instance_id=entity_id, start=start_time, state='log',
                                               severity=expt_severity, fail_ok=True, strict=False)
        if expected_alarm_state == 'yes_log':
            assert events, "No event log found for {} {} {} event".format(host, sensorgroup_name, eventlevel)
        else:
            assert not events, "Event logged unexpectedly for sensor on {}".format(host)
            system_helper.wait_for_alarm_gone(EventLogID.BMC_SENSOR_ACTION, entity_id=entity_id, strict=False,
                                              timeout=5, fail_ok=False)

    LOG.tc_step("Check the host status for sensor: {}".format(sensor_name))
    host_state_timeout = 120
    if action == 'reset':
        host_state_timeout = 1080    # 15 min reset interval in between two reset triggers
    system_helper.wait_for_host_values(host, timeout=host_state_timeout, fail_ok=False,
                                                availability=expected_host_state)
    if action == 'power-cycle':
        system_helper.wait_for_host_values(host, timeout=20, task=HostTask.POWER_CYCLE, strict=False)

    LOG.tc_step("Check the alarm clears and host in available state after clearing events")
    bmc_helper.clear_events(host)
    system_helper.wait_for_alarm_gone(alarm_id=EventLogID.BMC_SENSOR_ACTION, entity_id=host, strict=False,
                                      timeout=60)
    wait_time = 3000 if action == 'power-cycle' else HostTimeout.REBOOT
    system_helper.wait_for_host_values(host, fail_ok=False, timeout=wait_time, availability='available')

    HOST = ''


@mark.parametrize(('host', 'eventlevel', 'action',
                   'expected_host_state',
                   'expected_alarm_state',
                   'event_type',
                   'suppressionlevel'), [
                      ('compute-1', 'action_critical', 'power-cycle', 'power-off', 'yes_alarm', 'cr', 'unsuppressed'),
                      ('compute-0', 'action_critical', 'reset', 'offline', 'yes_alarm', 'nr', 'unsuppressed'),
                  ])
def test_sensorgroup_power_cycle(host,
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
        # global SUPPRESSED
        # SUPPRESSED = host
        suppress = True
    else:
        suppress = False

    expt_severity = eventlevel.split('_')[-1] if 'yes' in expected_alarm_state else None

    # Get a sensor to validate
    sensorgroup_name = random.choice(bmc_helper.get_sensor_names(host, sensor_group=True))
    for i in range(4):
        LOG.info("################## iter {} #########################".format(i+1))
        LOG.tc_step("Validating that sensorgroup: {} "
                    "can be set to sensor action: {} "
                    "for event level: {}".format(sensorgroup_name, action,
                                                 eventlevel))

        # Set the event level and action
        bmc_helper.modify_sensorgroup(host, sensorgroup_name, value='name', suppress=suppress, audit_interval=10,
                                      **{eventlevel: action})

        # Get a sensor that is part of the sensorgroup
        sensor_name = bmc_helper.get_first_sensor_from_sensorgroup(sensorgroup_name, host)
        entity_id = 'host={}.sensor={}'.format(host, sensor_name)

        LOG.tc_step("Trigger event for sensorgroup: {} and sensor name: {}".
                    format(sensorgroup_name, sensor_name))
        if action in ['power-cycle', 'reset']:
            HostsToRecover.add(host)

        start_time = common.get_date_in_format()
        bmc_helper.trigger_event(host, sensor_name, event_type)

        LOG.tc_step("Check sensor status and alarm for {}".format(sensor_name))
        if expected_alarm_state == 'yes_alarm':
            system_helper.wait_for_alarm(alarm_id=EventLogID.BMC_SENSOR_ACTION, entity_id=entity_id,
                                         severity=expt_severity, timeout=60, strict=False, fail_ok=False)
        else:
            events = system_helper.wait_for_events(timeout=60, num=10, event_log_id=EventLogID.BMC_SENSOR_ACTION,
                                                   entity_instance_id=entity_id, start=start_time, state='log',
                                                   severity=expt_severity, fail_ok=True, strict=False)
            if expected_alarm_state == 'yes_log':
                assert events, "No event log found for {} {} {} event".format(host, sensorgroup_name, eventlevel)
            else:
                assert not events, "Event logged unexpectedly for sensor on {}".format(host)
                system_helper.wait_for_alarm_gone(EventLogID.BMC_SENSOR_ACTION, entity_id=entity_id, strict=False,
                                                  timeout=5, fail_ok=False)

        LOG.tc_step("Check the host status for sensor: {}".format(sensor_name))
        host_state_timeout = 120
        if action == 'reset':
            host_state_timeout = 1080  # 15 min reset interval in between two reset triggers
        system_helper.wait_for_host_values(host, timeout=host_state_timeout, fail_ok=False,
                                                    availability=expected_host_state)
        if action == 'power-cycle':
            system_helper.wait_for_host_values(host, timeout=20, task=HostTask.POWER_CYCLE, strict=False)

        LOG.tc_step("Check the alarm clears and host in available state after clearing events")
        bmc_helper.clear_events(host)
        system_helper.wait_for_alarm_gone(alarm_id=EventLogID.BMC_SENSOR_ACTION, entity_id=host, strict=False,
                                          timeout=60)
        wait_time = 3000 if action == 'power-cycle' else HostTimeout.REBOOT
        expt_states = {'availability': 'available'}
        strict = True
        if action == 'power-cycle' and i == 3:
            wait_time = 1200
            strict = False
            expt_states = {'availability': HostAvailState.POWER_OFF,
                           'operational': HostOperState.DISABLED,
                           'administrative': HostAdminState.UNLOCKED,
                           'task': HostTask.POWER_DOWN}

        system_helper.wait_for_host_values(host, fail_ok=False, timeout=wait_time, strict=strict, **expt_states)

    LOG.tc_step("Power on {} after test ends".format(host))
    host_helper.lock_host(host=host)
    host_helper.power_on_host(host=host)
    HOST = ''


# @mark.usefixtures('bmc_test_prep')
@mark.parametrize(('host', 'event_type', 'action_level', 'action', 'suppression', 'expt_alarm', 'expt_host_avail',
                   'new_action', 'new_suppression', 'new_expt_alarm', 'new_expt_host_avail'), [
    ('compute-0', 'cr', 'action_critical', 'alarm', 'unsuppressed', 'yes_alarm', 'degraded', 'ignore', None, 'no_log', 'available'),
    ('compute-0', 'cr', 'action_critical', 'log', 'unsuppressed', 'yes_log', 'available', 'alarm', None, 'yes_alarm', 'degraded'),
    ('compute-0', 'cr', 'action_critical', 'ignore', 'unsuppressed', 'no_log', 'available', 'log', None, 'yes_log', 'available'),
    ('compute-0', 'nr', 'action_critical', 'ignore', 'unsuppressed', 'no_log', 'available', 'alarm', None, 'yes_alarm', 'degraded'),
    ('compute-0', 'nr', 'action_critical', 'alarm', 'suppressed', 'no_log', 'available', 'reset', None, 'no_log', 'available'),
    ('compute-0', 'nr', 'action_critical', 'log', 'suppressed', 'no_log', 'available', None, 'unsuppressed', 'yes_log', 'available'),
    ('controller-0', 'nc', 'action_major', 'alarm', 'unsuppressed', 'yes_alarm', 'degraded', 'ignore', 'unsuppressed', 'no_log', 'available'),
    ('controller-0', 'nc', 'action_major', 'alarm', 'suppressed', 'no_alarm', 'available', None, 'unsuppressed', 'yes_alarm', 'degraded'),
    ('controller-0', 'nc', 'action_major', 'log', 'unsuppressed', 'yes_log', 'available', 'alarm', 'unsuppressed', 'yes_alarm', 'degraded'),
    ('controller-0', 'nc', 'action_major', 'ignore', 'unsuppressed', 'no_log', 'available', 'log', 'unsuppressed', 'yes_log',   'available'),
    ('controller-0', 'nc', 'action_major', 'ignore', 'unsuppressed', 'no_log', 'available', 'alarm', 'unsuppressed', 'yes_alarm', 'degraded'),
    ('controller-0', 'mn', 'action_minor', 'alarm', 'unsuppressed', 'yes_alarm', 'available', 'ignore', 'unsuppressed', 'no_log', 'available'),
    ('controller-0', 'mn', 'action_minor', 'log', 'unsuppressed', 'yes_log', 'available', 'alarm', 'unsuppressed', 'yes_alarm', 'available'),
    ('controller-0', 'mn', 'action_minor', 'ignore', 'unsuppressed', 'no_log', 'available', 'log', 'unsuppressed', 'yes_log', 'available'),
    ('controller-0', 'mn', 'action_minor', 'ignore', 'unsuppressed', 'no_log', 'available', 'alarm', 'unsuppressed', 'yes_alarm', 'available'),
    ('controller-0', 'cr', 'action_critical', 'alarm', 'unsuppressed', 'yes_alarm', 'degraded', None, 'suppressed', 'no_log', 'available'),
    ('compute-0', 'nc', 'action_major', 'alarm', 'unsuppressed', 'yes_alarm', 'degraded', None, 'suppressed', 'no_log', 'available'),
    ('controller-0', 'nc', 'action_major', 'alarm', 'unsuppressed', 'yes_alarm', 'degraded', 'log', None, 'yes_log', 'available'),
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
    expt_severity = action_level.split('_')[-1] if 'yes' in expt_alarm else None
    new_expt_severity = action_level.split('_')[-1] if 'yes' in new_expt_alarm else None

    if suppression is not None:
        suppression = True if suppression == 'suppressed' else False
    if new_suppression is not None:
        new_suppression = True if new_suppression == 'suppressed' else False

    for sensorgroup_name in bmc_helper.get_sensorgroup_name(host):
        LOG.tc_step("Validating that sensorgroup: {} can be set to sensor action: {} for event level: {}".
                    format(sensorgroup_name, action, action_level))

        # Set the sensorgroup action, suppress state, and audit interval
        bmc_helper.modify_sensorgroup(host, sensorgroup_name, value='name', audit_interval=10, suppress=suppression,
                                      **{action_level: action})

        # Get a sensor that is part of the sensorgroup
        sensor_name = bmc_helper.get_first_sensor_from_sensorgroup(sensorgroup_name, host)
        entity_id = 'host={}.sensor={}'.format(host, sensor_name)

        LOG.tc_step("Trigger event for sensorgroup: {} and sensor name: {}".format(sensorgroup_name, sensor_name))
        bmc_helper.trigger_event(host, sensor_name, event_type)

        LOG.tc_step("Check the alarm status for sensor: {}".format(sensor_name))
        res = system_helper.wait_for_alarm(alarm_id=EventLogID.BMC_SENSOR_ACTION, timeout=60, entity_id=entity_id,
                                           severity=expt_severity, strict=False, fail_ok=True)[0]

        if expt_alarm == 'yes_alarm':
            assert res, "FAIL: Alarm expected but no alarms found for sensor on {}".format(host)
        else:
            assert not res, "FAIL: Alarm raised but no alarms were expected for sensor on {}".format(host)

        LOG.tc_step("Check the host status for sensor: {}".format(sensor_name))
        system_helper.wait_for_host_values(host, timeout=90, availability=expt_host_avail, fail_ok=False)

        start_time = common.get_date_in_format()
        # modify sensorgroup with new action/suppression level
        LOG.tc_step("Transition sensorgroup: {} from current sensor action: {} to new sensor action: {} "
                    "for event level: {}".format(sensorgroup_name, action, new_action, action_level))

        bmc_helper.modify_sensorgroup(host, sensorgroup_name, value='name', suppress=new_suppression,
                                      **{action_level: new_action})

        # Verify the new action is taken
        LOG.tc_step("Check alarm status after transition from {} to {} for {}".format(action, new_action, sensor_name))

        if new_expt_alarm == 'yes_alarm':
            system_helper.wait_for_alarm(alarm_id=EventLogID.BMC_SENSOR_ACTION, entity_id=entity_id,
                                         severity=new_expt_severity, timeout=60, strict=False, fail_ok=False)
        else:
            events = system_helper.wait_for_events(timeout=60, num=10, event_log_id=EventLogID.BMC_SENSOR_ACTION,
                                                   entity_instance_id=entity_id, start=start_time, state='log',
                                                   fail_ok=True, strict=False, severity=new_expt_severity)
            if new_expt_alarm == 'yes_log':
                assert events, "No event log found for {} {} {} event".format(host, sensorgroup_name, action_level)
            else:
                assert not events, "Event logged unexpectedly for sensor on {}".format(host)
                system_helper.wait_for_alarm_gone(EventLogID.BMC_SENSOR_ACTION, entity_id=entity_id, strict=False,
                                                  timeout=5, fail_ok=False)

        LOG.tc_step("Check the host status for sensor: {}".format(sensor_name))
        system_helper.wait_for_host_values(host, timeout=90, availability=new_expt_host_avail, fail_ok=False)

        LOG.tc_step("Check the alarm clears and host in available state after clearing events")
        bmc_helper.clear_events(host)
        system_helper.wait_for_alarm_gone(alarm_id=EventLogID.BMC_SENSOR_ACTION, entity_id=host, strict=False,
                                          timeout=60)
        system_helper.wait_for_host_values(host, fail_ok=False, availability='available')

    HOST = ''


# Following test removed due to update audit interval already covered in above testcases
@mark.parametrize(('host', 'auditvalue'), [
    ('compute-1', '5'),
    ('compute-1', '55'),
    ('compute-1', '3600'),
])
def _test_set_audit_level_values(host, auditvalue, sensor_data_fit):
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
