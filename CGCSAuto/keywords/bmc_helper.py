#!/usr/bin/env python3

'''


BMC Testing Helper Routines

Copyright (c) 2017 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.

This module dispatches the various states and actions that a BMC
system can take a node, and verifies that it is correct.
'''

'''
modification history:
---------------------
02a,04apr17,amf  cleanup and include additional comments
01a,29feb17,amf  written

'''

import os
import sys
from pytest import fixture
from utils.tis_log import LOG
from utils.ssh import ControllerClient
from utils import table_parser, cli, exceptions
from keywords import system_helper, host_helper
from consts.auth import Tenant


def suppress_sensor(sensorgroup_name, host):
    '''Suppress a sensor.'''

    return _suppress_unsuppress_sensor(sensorgroup_name, host, set_suppress='True')


def suppress_sensorgroup(sensorgroup_name, host):
    '''Suppress a sensor.'''

    return _suppress_unsuppress_sensor(sensorgroup_name, host, set_suppress='True', sensor_group=True)


def unsuppress_sensor(sensor_name, host):
    '''Unsuppress a sensor.'''

    return _suppress_unsuppress_sensor(sensor_name, host, set_suppress='False')


def unsuppress_sensorgroup(sensor_name, host):
    '''Unsuppress a sensor.'''

    return _suppress_unsuppress_sensor(sensor_name, host, set_suppress='False', sensor_group=True)


def _suppress_unsuppress_sensor(sensor_name, host, set_suppress='False', sensor_group=False):
    '''main suppress/unsuppress routine.'''

    # Get the uuid of the sensor to be suppressed
    res = 1
    sensor_uuid = get_sensor_uuid(sensor_name, host, sensor_group)

    # Check if the sensor is already suppressed
    sensor_showtable = get_sensor_showtable(sensor_uuid, host, sensor_group)
    sensor_suppression_value = table_parser.get_value_two_col_table(sensor_showtable, 'suppress')
    print('Suppression: {}'.format(sensor_suppression_value))

    if sensor_group == True:
        sysinv_action = 'host-sensorgroup-modify'
    else:
        sysinv_action = 'host-sensor-modify'

    # If not already suppressed, then suppress the sensor or sensor group
    if (sensor_suppression_value != set_suppress):
        # The sensor is not suppressed/unsuppressed, so execute the action
        res, out = cli.system('{}'.format(sysinv_action), '{} {} suppress={}'.format(host, sensor_uuid, set_suppress), fail_ok=True, rtn_list=True)

    print('Result: {}'.format(res))
    return (res == 0)


def set_sensorgroup_audit_interval(sensorgroup_name, host, audit_value=10):
    '''Modify the sensor action.'''

    return set_sensor_audit_interval(sensorgroup_name, host, audit_value, sensor_group=True)


def set_sensor_audit_interval(sensor_name, host, audit_value=10, sensor_group=False):
    '''main suppress/unsuppress routine.'''

    # Get the uuid of the sensor to be suppressed
    res = 1
    sensor_uuid = get_sensor_uuid(sensor_name, host, sensor_group)

    if sensor_group == True:
        sysinv_action = 'host-sensorgroup-modify'
        audit_action = 'audit_interval_group'
    else:
        sysinv_action = 'host-sensor-modify'
        audit_action = 'audit_interval'

    # Set the audit interval
    res, out = cli.system('{}'.format(sysinv_action), '{} {} {}={}'.
                          format(host, sensor_uuid, audit_action, audit_value), fail_ok=True, rtn_list=True)

    return (res == 0)


def get_sensor_audit_interval(sensorgroup_name, host):
    ''' get sensor audit interval value.'''

    # Get the value of the sensor audit interval
    sensor_uuid = get_sensor_uuid(sensorgroup_name, host, True)

    sysinv_action = 'host-sensorgroup-show'

    # Set the audit interval
    res, out = cli.system('{}'.format(sysinv_action), '{} {}'.
                          format(host, sensor_uuid), fail_ok=True, rtn_list=True)

    table = table_parser.table (out)
    audit_interval = table_parser.get_value_two_col_table(table, 'audit_interval_group')

    return audit_interval


def set_sensorgroup_action(sensorgroup_name, host, event_level='actions_critical', action='ignore'):
    '''Modify the sensor action.'''

    return set_sensor_action(sensorgroup_name, host, event_level, action, sensor_group=True)


def set_sensor_action(sensor_name, host, event_level='actions_critical', action='ignore', sensor_group=False):
    '''Modify the sensor action.'''

    # Get the uuid of the sensor to be suppressed

    res = 1
    if sensor_group == True:
        sysinv_action = 'host-sensorgroup-modify'
    else:
        sysinv_action = 'host-sensor-modify'

    sensor_uuid = get_sensor_uuid(sensor_name, host, sensor_group)

    # Check if the sensor action is already set
    sensor_action = get_sensors_action(sensor_uuid, host, event_level, sensor_group)

    # If not already set, then set the value
    if (sensor_action != event_level):
        res, out = cli.system('{}'.format(sysinv_action), '{} {} {}={}'.format(host, sensor_uuid, event_level, action), fail_ok=True, rtn_list=True)

    return (res == 0)


def get_sensors_action(sensor_uuid, host, event_level='actions_critical', sensor_group=False):
    """

    Args:
        sensor_uuid : UUID of the sensor.
        host : node that the sensor belongs to
        event_level : level of action expected
        sensor_group : group tht the sensor belongs to
    Returns:

    """
    res = 1

    # Get the sensor action from the sensor show table
    sensor_showtable = get_sensor_showtable(sensor_uuid, host, sensor_group)
    sensor_action = table_parser.get_value_two_col_table(sensor_showtable, event_level)

    return sensor_action


def get_sensors_table(host=None, sensor_group=False):
    """

    Args:
        host : node that the sensor belongs to
        sensor_group : group tht the sensor belongs to
    Returns:
        table_ : A table of sensors belonging to that group
    """

    if sensor_group == True:
        sysinv_action = 'host-sensorgroup-list'
    else:
        sysinv_action = 'host-sensor-list'

    res, out = cli.system('{}'.format(sysinv_action), '{} --nowrap'.format(host), fail_ok=True, rtn_list=True)
    table_ = table_parser.table(out)

    return table_


def get_sensor_uuid(sensor_name, host, sensor_group=False):
    """

    Args:
        sensor_name: Name of the sensor to find
        host: Host to query

    Returns:
        the sensor uuid
    """

    sensor_table = get_sensors_table(host, sensor_group)

    sensor_uuid = table_parser.get_values(sensor_table, 'uuid', Name=sensor_name)[0]

    return sensor_uuid


def get_sensorgroup_name(host):
    """

    Args:
        host: Host to query

    Returns:
        the sensor group name
    """

    return get_sensor_name(host=host, sensor_group=True)


def get_sensor_name(host, sensor_group=False):
    """

    Args:
        host: Host to query

    Returns:
        the sensor name
    """

    sensor_table = get_sensors_table(host, sensor_group)

    for i in range(len(sensor_table['values'])):
        row = sensor_table['values'][i]
        sensor_name = row[1]
        yield sensor_name


def get_first_sensor_from_sensorgroup(sensor_groupname, host):
    """

    Args:
        host: Host to query

    Returns:
        the sensor name
    """

    sensorgroup_table = get_sensors_table(host, True)

    for i in range(len(sensorgroup_table['values'])):
        row = sensorgroup_table['values'][i]
        if row[1] == sensor_groupname:
            sensor_list = row[3].replace("'",'')
            sensor_list = sensor_list.replace("[u",'').split(',')
            sensor_name = sensor_list[0]
            return sensor_name


def get_sensor_showtable(sensor_uuid, host, sensor_group=False):
    """

    Args:
        sensor_uuid : UUID of the sensor.
        host : node that the sensor belongs to
        event_level : level of action expected
        sensor_group : group tht the sensor belongs to
    Returns:

    """

    if sensor_group == True:
        sysinv_action = 'host-sensorgroup-show'
    else:
        sysinv_action = 'host-sensor-show'

    res, out = cli.system('{}'.format(sysinv_action), '{} {}'.format(host, sensor_uuid), fail_ok=True, rtn_list=True)
    table_ = table_parser.table(out)

    return table_


def get_sensor_alarm(host, sensor_name):
    '''Verify that the correct sensor action occurs for the triggered 
    event and configured sensor action.'''

    alarm_generated = False
    alarm_uuid = None
    alarm_id = None
    alarm_severity = None

    query_value = 'host={}'.format(host)
    alarms_table = system_helper.get_alarms_table(query_key='entity_instance_id',
                                              query_value=query_value,
                                              query_type='string')

    for alarm in alarms_table['values']:
        if sensor_name in alarm[2]:
            alarm_generated = True
            alarm_uuid = alarm[0]
            alarm_id = alarm[1]
            alarm_severity = alarm[4]
            break

    return (alarm_generated, alarm_uuid, alarm_id, alarm_severity)


def check_host_state(host, expected_host_state):
    ''' Return the state that the host enters after the
    triggered event and configured sensor action.'''

    con_ssh = ControllerClient.get_active_controller()

    return host_helper.wait_for_hosts_states(host, timeout=90, check_interval=10,
                                            con_ssh=con_ssh, availability=['{}'.format(expected_host_state)])


def trigger_event(host, sensor_name, sensor_value):
    '''Trigger an event that would cause a sensor action to take place.

    Args:
        host: The host that the event should be triggered on
        sensor_name: The sensor whose event should be triggered
        value: Event level to set
    Description:
        This routine will get the sensordata file, search for the sensor
        to be updated and then set the event level to be triggered.

    '''

    LOG.fixture_step("Update the sensordata file "
                     "/var/run/ipmitool/{}_sensor_data to trigger the "
                     "sensor: {}".format(host, sensor_name))

    #sensor_data_file = "/var/run/ipmitool/{}_sensor_data".format(host)
    sensor_data_file = "/home/wrsroot/nokia_sensor_data_simulator".format(host)

    tmp_sensor_datafile = "/tmp/{}_sensor_data".format(host)
    print('sensor_data_file: {}'.format(sensor_data_file))

    con_ssh = ControllerClient.get_active_controller()

    # First create a backup of the original sensor data file
    #rc, output = con_ssh.exec_sudo_cmd(cmd='cp {} {}.bkup'.format(sensor_data_file,
    #                                                          sensor_data_file),
    #                               fail_ok=False)

    # Update the sensor value in the data file
    expression = "sed 's#{}.*       | .*   | .*      | ok#{}       | na   | na      | {}#'".\
        format(sensor_name, sensor_name, sensor_value)
    rc, output = con_ssh.exec_sudo_cmd(cmd='{} < {} > {}'.
                                   format(expression, sensor_data_file, tmp_sensor_datafile),
                                   fail_ok=False)
    print('RetCode1: {}'.format(rc))
    rc, output = con_ssh.exec_sudo_cmd(cmd='cp {} {}'.
                                   format(tmp_sensor_datafile, sensor_data_file),
                                   fail_ok=False)
    print('RetCode2: {}'.format(rc))


def clear_events(host):
    '''Clear an event and restore all sensors to original values.

    Args:
        host: The host that should be restored
    '''

    LOG.fixture_step("Restore the sensordata file "
                     "/var/run/ipmitool/{}_sensor_data to original.".format(host))

    sensor_data_file = "/home/wrsroot/nokia_sensor_data_simulator".format(host)
    #original_sensor_datafile = "/var/run/ipmitool/nokia_sensor_data.ok"
    original_sensor_datafile = "/home/wrsroot/nokia_sensor_data.ok"

    con_ssh = ControllerClient.get_active_controller()

    # Restore the original sensor data file
    output = con_ssh.exec_sudo_cmd(cmd='cp {} {}'.format(original_sensor_datafile,
                                                         sensor_data_file),
                                   fail_ok=False)[1]





