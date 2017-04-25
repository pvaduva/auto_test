#!/usr/bin/env python3

'''
BMC Sensor Testing

Copyright (c) 2017 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.

This module verifies that the sensors were correctly added.
'''

'''
modification history:
---------------------
02a,04apr17,amf  cleanup and include additional comments
01a,29feb17,amf  written

'''

from pytest import mark
from pytest import fixture
from utils.tis_log import LOG
from keywords import system_helper, host_helper, bmc_helper
from utils import table_parser, cli, exceptions


# Configure the connection to a BMC server
# The following BMC servers are available: yow-cgcs-quanta-1 to yow-cgcs-quanta-5
mac_addr = "2C:60:0C:AD:9A:A3"
ip_addr = '128.224.151.124'   #-- yow-cgcs-quanta-5
bm_type = 'quanta'
bm_username = 'admin'
bm_password = 'admin'

@fixture(scope='module')
@mark.parametrize('host', [
    'controller-1'
])
def bmc_test_prep(request, host):
    LOG.fixture_step("Enable the BMC connections on the host: {}".format(host))

    bmc_helper.clear_events(host)
    code, out = cli.system('host-update',
                           '{} bm_mac={} bm_ip={} bm_type={} bm_username={} bm_password={}'.
                           format(host, mac_addr, ip_addr, bm_type, bm_username, bm_password),
                                                   fail_ok=True, rtn_list=True)

    def teardown():
        LOG.fixture_step("Disable all BMC connections")

        bmc_helper.clear_events(host)
        code, out = cli.system('host-update',
                               '{} bm_type={} bm_username={} bm_password={}'.
                               format(host, 'None', bm_username, bm_password),
                               fail_ok=True, rtn_list=True)

    request.addfinalizer(teardown)
    return


@mark.parametrize('host', [
    'controller-1'
])
def test_sensors_found(bmc_test_prep, host):
    """
    Get the list of sensors added after BMC enabled.

    Test Steps:
        - Get the list of every unlocked host
        - Connect to a specified host and list the sensors enabled on it

    """

    LOG.tc_step("Listing the sensors found on {}".format(host))
    LOG.info("{} state: {}".format(host, host_helper.get_hostshow_value(host, field='administrative')))
    res, out = cli.system('host-sensor-list', host, fail_ok=True, rtn_list=True)

    assert res == 0, "FAIL: No sensors for {} were found".format(host)


@mark.parametrize('host', [
    'controller-1'
])
def test_sensorgroups_found(bmc_test_prep, host):
    """
    Get the list of sensor groups added after BMC enabled.

    Test Steps:
        - Creates a list of every unlocked host
        - Connect to a specified host and list the sensors enabled on it

    """

    LOG.tc_step("Listing the sensorgroups found on {}".format(host))
    res, out = cli.system('host-sensorgroup-list', host, fail_ok=True, rtn_list=True)

    assert res == 0, "FAIL: No sensorgroups for {} were found".format(host)


@mark.parametrize('host', [
    'controller-1'
])
def test_suppress_unsuppress_sensors(host):
    """
    Validate that each sensor can be suppressed and unsuppressed.

    Test Steps:
        - Check the state of the host
        - Iterate through each sensor on the host and suppress/unsuppress each sensor

    """

    LOG.tc_step("Suppressing and Unsuppressing sensors found on {}".format(host))
    LOG.info("{} state: {}".format(host, host_helper.get_hostshow_value(host, field='administrative')))

    # Suppress each sensor
    for sensor_name in bmc_helper.get_sensor_name(host):
        LOG.tc_step("Validating that sensor: {} "
                    "can be suppressed.".format(sensor_name))
        res = bmc_helper.suppress_sensor(sensor_name, host)
        assert res == True, "FAIL: Sensor suppression " \
                            "fail for sensor:{} on {}".format(sensor_name, host)

    # Unsupress each sensor
    for sensor_name in bmc_helper.get_sensor_name(host):
        LOG.tc_step("Validating that sensor: {} "
                    "can be unsuppressed.".format(sensor_name))
        res = bmc_helper.unsuppress_sensor(sensor_name, host)
        assert res == True, "FAIL: Sensor unsuppression " \
                            "fail for sensor:{} on {}".format(sensor_name, host)


@mark.parametrize('host', [
    'controller-1'
])
def test_suppress_unsuppress_sensorgroups(host):
    """
    Validate that each sensorgroup can be suppressed and unsuppressed.

    Test Steps:
        - Check the state of the host
        - Iterate through each sensorgroup and suppress/unsuppress it

    """

    LOG.tc_step("Suppressing and Unsuppressing sensorgroups found on {}".format(host))

    for sensorgroup_name in bmc_helper.get_sensorgroup_name(host):
        LOG.tc_step("Validating that sensorgroup: {} "
                    "can be suppressed.".format(sensorgroup_name))
        res = bmc_helper.suppress_sensorgroup(sensorgroup_name, host)
        assert res == True, "FAIL: Sensor suppression " \
                            "fail for sensor:{} on {}".format(sensorgroup_name, host)

    for sensorgroup_name in bmc_helper.get_sensorgroup_name(host):
        LOG.tc_step("Validating that sensorgroup: {} "
                    "can be unsuppressed.".format(sensorgroup_name))
        res = bmc_helper.unsuppress_sensor(sensorgroup_name, host)
        assert res == True, "FAIL: Sensor unsuppression " \
                            "fail for sensor:{} on {}".format(sensorgroup_name, host)


@mark.parametrize('host', [
    'controller-1'
])
def test_sensor_alarm_status(host):
    """
    Validate that the appropriate alarm is raised for the appropriate sensor action.

    Test Steps:
        - Creates a list of every unlocked host
        - Iterate through each host and list the sensors associated with it

    """

    res = True
    alarm_generated = False
    LOG.tc_step("Getting the sensor active alarm status on {}".format(host))

    for sensor_name in bmc_helper.get_sensor_name(host):
        (alarm_generated, alarm_uuid, alarm_id, alarm_severity) = bmc_helper.get_sensor_alarm(host, sensor_name)
        print('Alarm Generated: {} UUID: {} ID: {} Severity: {}'.format(alarm_generated, alarm_uuid, alarm_id, alarm_severity))
        if alarm_generated:
            break

    assert alarm_generated == True, "FAIL: No alarms found for sensor on {}".format(host)


@mark.parametrize('host', [
    'controller-1'
])
def test_sensorgroup_alarm_status(host):
    """
    Get the list of sensors added after BMC enabled.

    Test Steps:
        - Creates a list of every unlocked host
        - Iterate through each host and list the sensors associated with it

    """

    res = True
    alarm_generated = False
    LOG.tc_step("Getting the sensor active alarm status on {}".format(host))

    for sensor_groupname in bmc_helper.get_sensorgroup_name(host):
        (alarm_generated, alarm_uuid, alarm_id, alarm_severity) = \
            bmc_helper.get_sensor_alarm(host, sensor_groupname)
        print('Sensorgroup name: {}'.format(sensor_groupname))
        print('Alarm Generated: {} UUID: {} ID: {} Severity: {}'.format
              (alarm_generated, alarm_uuid, alarm_id, alarm_severity))
        if alarm_generated:
            break

    assert alarm_generated == True, "FAIL: No alarms found for " \
                                    "sensor on {}".format(host)


@mark.parametrize(('host','eventlevel','action'),[
    ('controller-1','actions_critical','alarm'),
    ('controller-1','actions_critical','log'),
    ('controller-1','actions_critical','ignore'),
    ('controller-1','actions_critical','powercycle'),
    ('controller-1','actions_critical','reset'),
    ('controller-1','actions_major','alarm'),
    ('controller-1','actions_major','log'),
    ('controller-1','actions_major','ignore'),
    ('controller-1','actions_major','powercycle'),
    ('controller-1','actions_major','reset'),
    ('controller-1','actions_minor','alarm'),
    ('controller-1','actions_minor','log'),
    ('controller-1','actions_minor','ignore'),
    ('controller-1','actions_minor','powercycle'),
    ('controller-1','actions_minor','reset'),
])
def test_set_sensor_action(host, eventlevel, action):
    """
    This test case verifies that it is possible to successfully set the sensor
    action to one of the acceptable values: log, alarm, power-cycle, reset,
    and ignore.

    Currently it is executed on one node but can be expanded to validate all nodes
    in a system.

    Test Steps:
        - Check the state of the host
        - Iterate through each sensor on the host
        - Test the ability to configure the action for each sensor

    """

    LOG.tc_step("Modifying the sensor action on {}".format(host))
    LOG.info("{} state: {}".format(host,
                                   host_helper.get_hostshow_value(host,
                                                                  field='administrative')))

    for sensor_name in bmc_helper.get_sensor_name(host):
        LOG.tc_step("Validating that sensor: {} "
                    "can be set to sensor action: {} "
                    "for event level: {}".format(sensor_name, action,
                                                 eventlevel))
        res = bmc_helper.set_sensor_action(sensor_name, host,
                                           event_level=eventlevel,
                                           action=action)

        assert res == True, "FAIL: Modifying sensor action failed for sensor on {}".format(host)


@mark.parametrize(('host','eventlevel','action'),[
    ('controller-1','actions_critical_group','log'),
    ('controller-1','actions_critical_group','ignore'),
    ('controller-1','actions_critical_group','power-cycle'),
    ('controller-1','actions_critical_group','reset'),
    ('controller-1','actions_critical_group','alarm'),
    ('controller-1','actions_major_group','alarm'),
    ('controller-1','actions_major_group','ignore'),
    ('controller-1','actions_major_group','log'),
    ('controller-1','actions_minor_group','alarm'),
    ('controller-1','actions_minor_group','log'),
    ('controller-1','actions_minor_group','ignore'),
])
def test_set_sensorgroup_action(host, eventlevel, action):
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

    LOG.tc_step("Modifying the sensorgroup action on {}".format(host))

    for sensorgroup_name in bmc_helper.get_sensorgroup_name(host):
        LOG.tc_step("Validating that sensorgroup: {} "
                    "can be set to sensor action: {} "
                    "for event level: {}".format(sensorgroup_name, action,
                                                 eventlevel))
        res = bmc_helper.set_sensorgroup_action(sensorgroup_name, host,
                                           eventlevel,
                                           action)

        assert res == True, "FAIL: Modifying sensor action failed for sensor on {}".format(host)


@mark.parametrize(('host', 'eventlevel', 'action',
                   'expected_host_state',
                   'expected_alarm_state',
                   'suppressionlevel'), [
    ('controller-1', 'actions_critical', 'log', 'degraded', 'yes_alarm', 'unsuppressed'),
    ('controller-1', 'actions_critical', 'ignore', 'available', 'no_alarm', 'unsuppressed'),
    ('controller-1', 'actions_critical', 'powercycle', 'degraded', 'yes_alarm', 'unsuppressed'),
    ('controller-1', 'actions_critical', 'reset', 'degraded', 'yes_alarm', 'unsuppressed'),
    ('controller-1', 'actions_critical', 'alarm', 'degraded', 'yes_alarm', 'unsuppressed'),
    ('controller-1', 'actions_major', 'alarm', 'degraded', 'yes_alarm', 'unsuppressed'),
    ('controller-1', 'actions_major', 'ignore', 'available', 'no_alarm', 'unsuppressed'),
    ('controller-1', 'actions_major', 'log', 'degraded', 'no_alarm', 'unsuppressed'),
    ('controller-1', 'actions_minor', 'alarm', 'degraded', 'no_alarm', 'unsuppressed'),
    ('controller-1', 'actions_minor', 'log', 'available', 'no_alarm', 'unsuppressed'),
    ('controller-1', 'actions_minor', 'ignore', 'available', 'no_alarm', 'unsuppressed'),
])
def test_sensor_action_taken(host,
                       eventlevel,
                       action,
                       expected_host_state,
                       expected_alarm_state,
                       suppressionlevel):
    """
    Verify that the sensor action taken for an event is valid.

    Test Steps:
        - Get a sensor to test
        - Set the event level and expected action
        - trigger an out-of-scope event for that sensor
        - verify that the expected action is taken

    """

    # Get a sensor to validate
    for sensor_name in bmc_helper.get_sensor_name(host):
        LOG.tc_step("Validating that sensor: {} "
                    "can be set to sensor action: {} "
                    "for event level: {}".format(sensor_name, action,
                                                 eventlevel))

        # Set the event level and action
        res = bmc_helper.set_sensor_action(sensor_name, host,
                                           event_level=eventlevel,
                                           action=action)

        assert res == True, "FAIL: Modifying sensor action failed for " \
                            "sensor on {}".format(host)

        LOG.tc_step("Trigger event for sensor: {}".format(sensor_name))
        bmc_helper.trigger_event(host, sensor_name, 'cr')

        LOG.tc_step("Check the alarm status for sensor: {}".format(sensor_name))
        (alarm_generated, alarm_uuid, alarm_id, alarm_severity) = \
            bmc_helper.get_sensor_alarm(host, sensor_name)

        if expected_alarm_state == 'yes_alarm':
            assert alarm_generated == True, "FAIL: Alarm expected but no " \
                                            "alarms found for " \
                                            "sensor on {}".format(host)
        else:
            assert alarm_generated == False, "FAIL: Alarm raised but no " \
                                             "alarms were expected " \
                                             "for sensor on {}".format(host)

        LOG.tc_step("Check the host status for sensor: {}".format(sensor_name))
        admin_state = bmc_helper.check_host_state(host)
        if suppressionlevel is 'suppressed':
            expected_host_state = "available"

        assert admin_state == expected_host_state, "FAIL: Unexpected host state on host {}".format(host)


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
    ('controller-1', 'actions_critical_group', 'powercycle', 'degraded', 'yes_alarm', 'cr', 'unsuppressed'),
    ('controller-1', 'actions_critical_group', 'reset', 'degraded', 'yes_alarm', 'cr', 'unsuppressed'),
    ('controller-1', 'actions_critical_group', 'alarm', 'degraded', 'yes_alarm', 'cr', 'unsuppressed'),
    ('controller-1', 'actions_major_group', 'alarm', 'degraded', 'yes_alarm', 'cr', 'unsuppressed'),
    ('controller-1', 'actions_major_group', 'ignore', 'available', 'no_alarm', 'cr', 'unsuppressed'),
    ('controller-1', 'actions_major_group', 'log', 'degraded', 'no_alarm', 'cr', 'unsuppressed'),
    ('controller-1', 'actions_minor_group', 'alarm', 'degraded', 'no_alarm', 'cr', 'unsuppressed'),
    ('controller-1', 'actions_minor_group', 'log', 'available', 'no_alarm', 'cr', 'unsuppressed'),
    ('controller-1', 'actions_minor_group', 'ignore', 'available', 'no_alarm', 'cr', 'unsuppressed'),
])
def test_sensorgroup_action_taken(host,
                       eventlevel,
                       action,
                       expected_host_state,
                       expected_alarm_state,
                       event_type,
                       suppressionlevel):
    """
    Verify that the sensorgroup action taken for an event is valid.

    Test Steps:
        - Get a sensorgroup to test
        - Set the event level and expected action
        - trigger an out-of-scope event for that sensorgroup
        - verify that the expected action is taken

    """


    # Get a sensor to validate
    for sensorgroup_name in bmc_helper.get_sensorgroup_name(host):
        LOG.tc_step("Validating that sensorgroup: {} "
                    "can be set to sensor action: {} "
                    "for event level: {}".format(sensorgroup_name, action,
                                                 eventlevel))

        # Set the event level and action
        res = bmc_helper.set_sensorgroup_action(sensorgroup_name, host,
                                           event_level=eventlevel,
                                           action=action)

        assert res == True, "FAIL: Modifying sensorgroup action failed for " \
                            "sensor on {}".format(host)

        # Get a sensor that is part of the sensorgroup
        sensor_name = bmc_helper.get_first_sensor_from_sensorgroup(sensorgroup_name, host)

        LOG.tc_step("Trigger event for sensorgroup: {} and sensor name: {}".
                    format(sensorgroup_name, sensor_name))

        bmc_helper.set_sensorgroup_audit_interval(sensorgroup_name, host, audit_value=11)
        bmc_helper.trigger_event(host, sensor_name, event_type)

        (alarm_generated, alarm_uuid, alarm_id, alarm_severity) = \
            bmc_helper.get_sensor_alarm(host, sensor_name)

        if expected_alarm_state == 'yes_alarm':
            LOG.tc_step("Check the alarm status for sensor: {}".format(sensor_name))
            res = system_helper.wait_for_alarm(entity_id='host={}.sensor={}'.
                                               format(host, sensor_name),
                                               reason='{}'.format(sensor_name),
                                               timeout=90,
                                               regex=True, strict=False)[0]
            assert alarm_generated == True, "FAIL: Alarm expected but no " \
                                            "alarms found for " \
                                            "sensor on {}".format(host)
        else:
            assert alarm_generated == False, "FAIL: Alarm raised but no " \
                                             "alarms were expected " \
                                             "for sensor on {}".format(host)

        LOG.tc_step("Check the host status for sensor: {}".format(sensor_name))
        if suppressionlevel is 'suppressed':
            expected_host_state = "available"
        admin_status = bmc_helper.check_host_state(host, expected_host_state)

        assert admin_status == True, "FAIL: Unexpected host state on host {}".format(host)

    bmc_helper.clear_events(host)


@mark.parametrize(('host', 'eventlevel', 'action',
                   'expected_host_state',
                   'expected_alarm_state',
                   'suppressionlevel'), [
    ('compute-0', 'actions_critical', 'log', 'degraded', 'yes_alarm', 'unsuppressed'),
                  ])
def test_sensor_value_find(host,
                       eventlevel,
                       action,
                       expected_host_state,
                       expected_alarm_state,
                       suppressionlevel):
    """
    Verify that the sensor action taken for an event is valid.

    Test Steps:
        - Get a sensor to test
        - Set the event level and expected action
        - trigger an out-of-scope event for that sensor
        - verify that the expected action is taken
    """

    # Get a sensor to validate
    for sensor_name in bmc_helper.get_sensor_name(host):
        LOG.tc_step("Validating that sensor: {} "
                    "can be set to sensor action: {} "
                    "for event level: {}".format(sensor_name, action,
                                                 eventlevel))

        LOG.tc_step("Lower the audit level for sensor: {}".format(sensor_name))
        bmc_helper.set_sensor_audit_interval(sensor_name, host, audit_value=11)

        LOG.tc_step("Trigger event for sensor: {}".format(sensor_name))
        bmc_helper.trigger_event(host, sensor_name, 'major')


@mark.parametrize(('host', 'sensorstate', 'action',
                   'expected_host_state',
                   'expected_alarm_state',
                   'newaction',
                   'new_expected_host_state',
                   'new_expected_alarm_state',
                   'event_type',
                   'suppressionlevel'), [
    ('compute-0', 'actions_critical_group', 'alarm', 'degraded', 'yes_alarm', 'ignore', 'available', 'no_alarm', 'cr', 'unsuppressed'),
    ('compute-0', 'actions_critical_group', 'log',   'available', 'no_alarm', 'alarm',  'degraded',  'yes_alarm', 'cr', 'unsuppressed'),
    ('compute-0', 'actions_critical_group', 'ignore', 'available', 'no_alarm', 'log',   'available', 'no_alarm', 'cr', 'unsuppressed'),
    ('compute-0', 'actions_critical_group', 'ignore', 'available', 'no_alarm', 'alarm', 'degraded', 'yes_alarm', 'cr', 'unsuppressed'),
    ('controller-0', 'actions_major_group', 'alarm', 'degraded', 'yes_alarm', 'ignore', 'available', 'no_alarm', 'nc', 'unsuppressed'),
    ('controller-0', 'actions_major_group', 'log', 'available', 'no_alarm', 'alarm', 'degraded', 'yes_alarm', 'nc', 'unsuppressed'),
    ('controller-0', 'actions_major_group', 'ignore', 'available', 'no_alarm', 'log',   'available', 'no_alarm', 'nc', 'unsuppressed'),
    ('controller-0', 'actions_major_group', 'ignore', 'available', 'no_alarm', 'alarm', 'degraded', 'yes_alarm', 'nc', 'unsuppressed'),
    ('controller-0', 'actions_minor_group', 'alarm', 'available', 'yes_alarm', 'ignore', 'available', 'no_alarm', 'lna', 'unsuppressed'),
    ('controller-0', 'actions_minor_group', 'log', 'available', 'no_alarm', 'alarm', 'available', 'yes_alarm', 'lna', 'unsuppressed'),
    ('controller-0', 'actions_minor_group', 'ignore', 'available', 'no_alarm', 'log', 'available', 'no_alarm', 'lna', 'unsuppressed'),
    ('controller-0', 'actions_minor_group', 'ignore', 'available', 'no_alarm', 'alarm', 'available', 'yes_alarm', 'lna', 'unsuppressed'),
])
def test_transition_sensorgroup_actions(bmc_test_prep, host,
                       sensorstate,
                       action,
                       expected_host_state,
                       expected_alarm_state,
                       newaction,
                       new_expected_host_state,
                       new_expected_alarm_state,
                       event_type,
                       suppressionlevel):
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


    # Get a sensor to validate
    for sensorgroup_name in bmc_helper.get_sensorgroup_name(host):
        LOG.tc_step("Validating that sensorgroup: {} "
                    "can be set to sensor action: {} "
                    "for event level: {}".format(sensorgroup_name, action,
                                                 sensorstate))

        # Set the event level and action
        res = bmc_helper.set_sensorgroup_action(sensorgroup_name, host,
                                           event_level=sensorstate,
                                           action=action)

        assert res == True, "FAIL: Modifying sensorgroup action failed for " \
                            "sensor on {}".format(host)

        # Get a sensor that is part of the sensorgroup
        sensor_name = bmc_helper.get_first_sensor_from_sensorgroup(sensorgroup_name, host)

        LOG.tc_step("Trigger event for sensorgroup: {} and sensor name: {}".
                    format(sensorgroup_name, sensor_name))

        bmc_helper.set_sensorgroup_audit_interval(sensorgroup_name, host, audit_value=11)
        bmc_helper.trigger_event(host, sensor_name, event_type)

        LOG.tc_step("Check the alarm status for sensor: {}".format(sensor_name))

        if action == 'ignore' or action == 'log':
            expected_host_state = "available"
        else:
            res = system_helper.wait_for_alarm(entity_id='host={}.sensor={}'.
                                               format(host, sensor_name),
                                               reason='{}'.format(sensor_name),
                                               timeout=90,
                                               regex=True, strict=False)[0]

            alarm_generated, alarm_uuid, alarm_id, alarm_severity = \
                bmc_helper.get_sensor_alarm(host, sensor_name)

            if expected_alarm_state == 'yes_alarm':
                assert alarm_generated == True, "FAIL: Alarm expected but no " \
                                                "alarms found for " \
                                                "sensor on {}".format(host)
            else:
                assert alarm_generated == False, "FAIL: Alarm raised but no " \
                                                 "alarms were expected " \
                                                 "for sensor on {}".format(host)

        LOG.tc_step("Check the host status for sensor: {}".format(sensor_name))
        if suppressionlevel is 'suppressed':
            expected_host_state = "available"
        admin_status = bmc_helper.check_host_state(host, expected_host_state)

        assert admin_status == True, "FAIL: Unexpected host state on host {}".format(host)

        LOG.tc_step("Transition sensorgroup: {} "
                    "from current sensor action: {} "
                    "to new sensor action: {} "
                    "for event level: {}".format(sensorgroup_name, action, newaction,
                                                 sensorstate))

        # Set set a new action for the same event level
        res = bmc_helper.set_sensorgroup_action(sensorgroup_name, host,
                                                event_level=sensorstate,
                                                action=newaction)
        assert res == True, "FAIL: Modifying sensorgroup action failed for " \
                            "sensor on {}".format(host)

        # Verify the new action is taken
        if new_expected_alarm_state == 'yes_alarm':
            res = system_helper.wait_for_alarm(entity_id='host={}.sensor={}'.
                                               format(host, sensor_name),
                                               reason='{}'.format(sensor_name),
                                               timeout=90,
                                               regex=True, strict=False)[0]

            alarm_generated, alarm_uuid, alarm_id, alarm_severity = \
                bmc_helper.get_sensor_alarm(host, sensor_name)

            assert alarm_generated == True, "FAIL: Alarm was not " \
                                            "raised for " \
                                            "sensor on {}".format(host)
        else:
            LOG.tc_step("Wait for the alarm for sensor: {} to be cleared.".format(sensor_name))

            res = system_helper.wait_for_alarm_gone('200.007', entity_id='host={}.sensor={}'.
                                                    format(host, sensor_name), strict=False)

            (alarm_generated, alarm_uuid, alarm_id, alarm_severity) = \
                bmc_helper.get_sensor_alarm(host, sensor_name)


            assert alarm_generated == False, "FAIL: Alarm was not " \
                                             "cleared as expected " \
                                             "for sensor on {}".format(host)

        LOG.tc_step("Check the host status for sensor: {}".format(sensor_name))
        if suppressionlevel is 'suppressed':
            new_expected_host_state = "available"
        admin_status = bmc_helper.check_host_state(host, new_expected_host_state)

        assert admin_status == True, "FAIL: Unexpected host state on host {}".format(host)

        bmc_helper.clear_events(host)


@mark.parametrize(('host', 'eventlevel', 'action', 'newaction',
                   'expected_host_state',
                   'expected_alarm_state',
                   'suppressionlevel'), [
    ('compute-0', 'actions_critical_group', 'alarm', 'ignore','degraded', 'yes_alarm', 'unsuppressed'),
    ('compute-0', 'actions_critical_group', 'log', 'alarm','degraded', 'yes_alarm', 'unsuppressed'),
    ('compute-0', 'actions_critical_group', 'ignore', 'log','available', 'no_alarm', 'unsuppressed'),
    # FIXME: Comment out following params for now as pytest is throwing exception on them due to missing param
    # ('controller-1', 'actions_critical_group', 'ignore', 'available', 'no_alarm', 'unsuppressed'),
    # ('controller-1', 'actions_critical_group', 'powercycle', 'degraded', 'yes_alarm', 'unsuppressed'),
    # ('controller-1', 'actions_critical_group', 'reset', 'degraded', 'yes_alarm', 'unsuppressed'),
])
def test_sensorgroup_ignore_action_transition(bmc_test_prep, host,
                       eventlevel,
                       action,
                       newaction,
                       expected_host_state,
                       expected_alarm_state,
                       suppressionlevel):
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


    # Get a sensor to validate
    for sensorgroup_name in bmc_helper.get_sensorgroup_name(host):
        LOG.tc_step("Validating that sensorgroup: {} "
                    "can be set to sensor action: {} "
                    "for event level: {}".format(sensorgroup_name, action,
                                                 eventlevel))

        # Set the event level and action
        res = bmc_helper.set_sensorgroup_action(sensorgroup_name, host,
                                           event_level=eventlevel,
                                           action=action)

        assert res == True, "FAIL: Modifying sensorgroup action failed for " \
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
            res = system_helper.wait_for_alarm(entity_id='host={}.sensor={}'.
                                               format(host, sensor_name),
                                               reason='{}'.format(sensor_name),
                                               timeout=90,
                                               regex=True, strict=False)[0]

            alarm_generated, alarm_uuid, alarm_id, alarm_severity = \
                bmc_helper.get_sensor_alarm(host, sensor_name)

            if expected_alarm_state == 'yes_alarm':
                assert alarm_generated == True, "FAIL: Alarm expected but no " \
                                                "alarms found for " \
                                                "sensor on {}".format(host)
            else:
                assert alarm_generated == False, "FAIL: Alarm raised but no " \
                                                 "alarms were expected " \
                                                 "for sensor on {}".format(host)

        LOG.tc_step("Check the host status for sensor: {}".format(sensor_name))
        if suppressionlevel is 'suppressed':
            expected_host_state = "available"
        admin_status = bmc_helper.check_host_state(host, expected_host_state)

        assert admin_status == True, "FAIL: Unexpected host state on host {}".format(host)

        LOG.tc_step("Transition sensorgroup: {} "
                    "from current sensor action: {} "
                    "to new sensor action: {} "
                    "for event level: {}".format(sensorgroup_name, action, newaction,
                                                 eventlevel))

        # Set set a new action for the same event level
        res = bmc_helper.set_sensorgroup_action(sensorgroup_name, host,
                                                event_level=eventlevel,
                                                action=newaction)
        assert res == True, "FAIL: Modifying sensorgroup action failed for " \
                            "sensor on {}".format(host)

        # Verify the new action is taken
        if newaction == 'ignore' or newaction == 'log':
            expected_host_state = "available"

            LOG.tc_step("Wait for the alarm for sensor: {} to be cleared.".format(sensor_name))

            (alarm_generated, alarm_uuid, alarm_id, alarm_severity) = \
                bmc_helper.get_sensor_alarm(host, sensor_name)

            if expected_alarm_state == 'yes_alarm':
                assert alarm_generated == True, "FAIL: Alarm was not " \
                                                "cleared for " \
                                                "sensor on {}".format(host)
            else:
                assert alarm_generated == False, "FAIL: Alarm raised but no " \
                                                 "alarms were expected " \
                                                 "for sensor on {}".format(host)
        else:
            LOG.tc_step("Wait for the alarm for sensor: {} to be raised.".format(sensor_name))

            res = system_helper.wait_for_alarm(entity_id='host={}.sensor={}'.
                                               format(host, sensor_name),
                                               reason='{}'.format(sensor_name),
                                               timeout=90,
                                               regex=True, strict=False)[0]

            alarm_generated, alarm_uuid, alarm_id, alarm_severity = \
                bmc_helper.get_sensor_alarm(host, sensor_name)

            if expected_alarm_state == 'yes_alarm':
                expected_host_state = "degraded"
                assert alarm_generated == True, "FAIL: Alarm expected but no " \
                                                "alarms found for " \
                                                "sensor on {}".format(host)
            else:
                expected_host_state = "available"
                assert alarm_generated == False, "FAIL: Alarm raised but no " \
                                                 "alarms were expected " \
                                                 "for sensor on {}".format(host)

        LOG.tc_step("Check the host status for sensor: {}".format(sensor_name))
        if suppressionlevel is 'suppressed':
            expected_host_state = "available"
        admin_status = bmc_helper.check_host_state(host, expected_host_state)

        assert admin_status == True, "FAIL: Unexpected host state on host {}".format(host)

        bmc_helper.clear_events(host)


@mark.parametrize(('host', 'auditvalue'), [
    ('compute-0', '5'),
    ('compute-0', '55'),
    ('compute-0', '3600'),
])
def test_set_audit_level_values(host,
                       auditvalue):
    """
    Verify various settings for the audit level.

    Test Steps:
        - Get a sensorgroup to test
        - Set the audit interval value
        - verify the new audit interval value is set

    """

    # Get a sensor to validate
    for sensorgroup_name in bmc_helper.get_sensorgroup_name(host):
        LOG.tc_step("Validating that the audit value for sensorgroup: {} "
                    "can be set to new value: {}".format(sensorgroup_name,
                                                 auditvalue))

        # Set the audit interval value
        bmc_helper.set_sensorgroup_audit_interval(sensorgroup_name, host, auditvalue)

        # Verify that the audit interval value has been updated
        sensor_audit_interval = bmc_helper.get_sensor_audit_interval(sensorgroup_name, host)

        assert sensor_audit_interval == auditvalue, "FAIL: Modifying sensor audit interval failed for " \
                            "sensor on {}".format(host)
