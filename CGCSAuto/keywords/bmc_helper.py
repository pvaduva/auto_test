#!/usr/bin/env python3
"""
BMC Testing Helper Routines

Copyright (c) 2017 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.

This module dispatches the various states and actions that a BMC
system can take a node, and verifies that it is correct.
"""
import re
import ast

from consts.auth import Tenant
from consts.filepaths import SYSADMIN_HOME, BMCPath
from keywords import system_helper
from utils import table_parser, cli, exceptions
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG


def suppress_sensor(sensorgroup_name, host):
    """Suppress a sensor."""

    return _suppress_unsuppress_sensor(sensorgroup_name, host, set_suppress='True')


def suppress_sensorgroup(sensorgroup_name, host):
    """Suppress a sensor."""

    return _suppress_unsuppress_sensor(sensorgroup_name, host, set_suppress='True', sensor_group=True)


def unsuppress_sensor(sensor_name, host):
    """Unsuppress a sensor."""

    return _suppress_unsuppress_sensor(sensor_name, host, set_suppress='False')


def unsuppress_sensorgroup(sensor_name, host):
    """Unsuppress a sensor."""

    return _suppress_unsuppress_sensor(sensor_name, host, set_suppress='False', sensor_group=True)


def _suppress_unsuppress_sensor(sensor_name, host, set_suppress='False', sensor_group=False):
    """main suppress/unsuppress routine."""

    # Get the uuid of the sensor to be suppressed
    res = 0
    sensor_uuid = get_sensor_uuid(sensor_name, host, sensor_group)

    # Check if the sensor is already suppressed
    sensor_showtable = get_sensor_showtable(sensor_uuid, host, sensor_group)
    sensor_suppression_value = table_parser.get_value_two_col_table(sensor_showtable, 'suppress')
    print('Suppression: {}'.format(sensor_suppression_value))

    if sensor_group is True:
        sysinv_action = 'host-sensorgroup-modify'
    else:
        sysinv_action = 'host-sensor-modify'

    # If not already suppressed, then suppress the sensor or sensor group
    if sensor_suppression_value != set_suppress:
        # The sensor is not suppressed/unsuppressed, so execute the action
        res, out = cli.system(sysinv_action, '{} {} suppress={}'.format(host, sensor_uuid, set_suppress), fail_ok=True)

    print('Result: {}'.format(res))
    return res == 0


def set_sensorgroup_audit_interval(sensorgroup_name, host, audit_value=10):
    """Modify the sensor action."""

    return set_sensor_audit_interval(sensorgroup_name, host, audit_value, sensor_group=True)


def set_sensor_audit_interval(sensor_name, host, audit_value=10, sensor_group=False):
    """main suppress/unsuppress routine."""

    # Get the uuid of the sensor to be suppressed
    sensor_uuid = get_sensor_uuid(sensor_name, host, sensor_group)

    if sensor_group is True:
        sysinv_action = 'host-sensorgroup-modify'
        audit_action = 'audit_interval_group'
    else:
        sysinv_action = 'host-sensor-modify'
        audit_action = 'audit_interval'

    # Set the audit interval
    res, out = cli.system(sysinv_action, '{} {} {}={}'.format(host, sensor_uuid, audit_action, audit_value),
                          fail_ok=True)

    return res == 0


def get_sensor_audit_interval(sensorgroup_name, host):
    """ get sensor audit interval value."""

    # Get the value of the sensor audit interval
    sensor_uuid = get_sensor_uuid(sensorgroup_name, host, True)

    sysinv_action = 'host-sensorgroup-show'

    # Set the audit interval
    res, out = cli.system('{}'.format(sysinv_action), '{} {}'.
                          format(host, sensor_uuid), fail_ok=True)

    table = table_parser.table(out)
    audit_interval = table_parser.get_value_two_col_table(table, 'audit_interval_group')

    return audit_interval


def set_sensorgroup_action(sensorgroup_name, host, event_level='actions_critical', action='ignore'):
    """Modify the sensor action."""

    return set_sensor_action(sensorgroup_name, host, event_level, action, sensor_group=True)


def modify_sensorgroup(host, sensor_group, value='name', action_critical=None, action_major=None, action_minor=None,
                       suppress=None, audit_interval=None, datatype=None,
                       fail_ok=False, auth_info=Tenant.get('admin_platform'), con_ssh=None):
    args_dict = {
        'actions_critical_group': action_critical,
        'actions_major_group': action_major,
        'actions_minor_group': action_minor,
        'audit_interval_group': audit_interval,
        'suppress': suppress,
        'datatype': datatype
    }

    args = ''
    validate_dict = {}
    for key, val in args_dict.items():
        if val is not None:
            args += ' {}={}'.format(key, val)
            validate_dict[key] = val

    if not args:
        raise ValueError("At least one field should be specified: {}".format(args_dict.keys()))

    if value == 'name':
        sensor_group_uuid = get_sensor_uuid(sensor_group, host, sensor_group=True)
    else:
        sensor_group_uuid = sensor_group

    args = ' '.join([host, sensor_group_uuid, args.strip()])

    code, out = cli.system('host-sensorgroup-modify', args, ssh_client=con_ssh, fail_ok=fail_ok, auth_info=auth_info)
    if code == 1:
        return code, out

    post_mod_tab = table_parser.table(out)
    failed_to_mod = ''
    for key, val in validate_dict.items():
        post_val = table_parser.get_value_two_col_table(post_mod_tab, field=key)
        if not str(val) == post_val:
            failed_to_mod += '\n{} val is {} instead of {} after modify'.format(key, post_val, val)

    if failed_to_mod:
        raise exceptions.SysinvError("Failed to modify sensorgroup to specified value. {}".format(failed_to_mod))

    LOG.info("{} sensorgroup {} successfully modified to: {}".format(host, sensor_group, validate_dict))
    return 0, "{} sensorgroup {} successfully modified".format(host, sensor_group)


def set_sensor_action(sensor_name, host, event_level='actions_critical', action='ignore', audit_interval=None,
                      sensor_group=False):
    """Modify the sensor action."""

    # Get the uuid of the sensor to be suppressed

    if sensor_group is True:
        sysinv_action = 'host-sensorgroup-modify'
        audit_param = 'audit_interval_group'
    else:
        sysinv_action = 'host-sensor-modify'
        audit_param = 'audit_interval'

    sensor_uuid = get_sensor_uuid(sensor_name, host, sensor_group)

    # Check if the sensor action is already set
    sensor_action = get_sensors_action(sensor_uuid, host, event_level, sensor_group)

    # If not already set, then set the value
    args = ''
    if sensor_action != action:
        args += ' {}={}'.format(event_level, action)

    if audit_interval is not None:
        args += ' {}={}'.format(audit_param, audit_interval)

    if not args:
        return True

    res, out = cli.system(sysinv_action, '{} {} {}'.format(host, sensor_uuid, args.strip()), fail_ok=True)

    post_sensor_action = get_sensors_action(sensor_uuid, host, event_level, sensor_group)

    LOG.info("Set sensor action res: {}\n {} setting: {}".format(res, sensor_name, post_sensor_action))
    return res == 0 and post_sensor_action == action


def get_sensors_action(sensor_uuid, host, event_level='actions_critical', sensor_group=False):
    """

    Args:
        sensor_uuid : UUID of the sensor.
        host : node that the sensor belongs to
        event_level : level of action expected
        sensor_group : group tht the sensor belongs to
    Returns:

    """

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

    if sensor_group is True:
        sysinv_action = 'host-sensorgroup-list'
    else:
        sysinv_action = 'host-sensor-list'

    res, out = cli.system('{}'.format(sysinv_action), '{} --nowrap'.format(host), fail_ok=True)
    table_ = table_parser.table(out)

    return table_


def get_sensor_uuid(sensor_name, host, sensor_group=False):
    """

    Args:
        sensor_name: Name of the sensor to find
        host: Host to query
        sensor_group

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

    return get_sensor_names(host=host, sensor_group=True)


def get_sensor_names(host, sensor_group=False):
    """

    Args:
        host: Host to query
        sensor_group

    Returns:
        the sensor name
    """

    sensor_table = get_sensors_table(host, sensor_group)
    names = table_parser.get_column(sensor_table, 'name')
    return names


def get_first_sensor_from_sensorgroup(sensor_groupname, host):
    """

    Args:
        sensor_groupname
        host: Host to query

    Returns:
        the sensor name
    """
    sensorgroup_table = get_sensors_table(host, sensor_group=True)
    sensors = ast.literal_eval(table_parser.get_values(sensorgroup_table, 'sensors', name=sensor_groupname)[0])
    return sensors[0]


def get_sensor_showtable(sensor_uuid, host, sensor_group=False):
    """

    Args:
        sensor_uuid : UUID of the sensor.
        host : node that the sensor belongs to
        sensor_group : group tht the sensor belongs to
    Returns:

    """

    if sensor_group is True:
        sysinv_action = 'host-sensorgroup-show'
    else:
        sysinv_action = 'host-sensor-show'

    res, out = cli.system('{}'.format(sysinv_action), '{} {}'.format(host, sensor_uuid), fail_ok=True)
    table_ = table_parser.table(out)

    return table_


def get_sensor_alarm(host, sensor_name):
    """Verify that the correct sensor action occurs for the triggered 
    event and configured sensor action."""

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

    return alarm_generated, alarm_uuid, alarm_id, alarm_severity


def check_host_state(host, expected_host_state):
    """ Return the state that the host enters after the
    triggered event and configured sensor action."""

    con_ssh = ControllerClient.get_active_controller()

    return system_helper.wait_for_hosts_states(host, timeout=90, check_interval=10,
                                               con_ssh=con_ssh, availability=['{}'.format(expected_host_state)])


def trigger_event(host, sensor_name, sensor_value):
    """
    Trigger an event that would cause a sensor action to take place.
    Args:
        host (str): The host that the event should be triggered on
        sensor_name (str): The sensor whose event should be triggered
        sensor_value (str): Event level to set

    Description:
        This routine will get the sensordata file, search for the sensor
        to be updated and then set the event level to be triggered.

    """
    clear_events(host)
    sensor_data_file_name = "hwmond_{}_sensor_data".format(host)

    LOG.info("Update the sensordata file /var/run/ipmitool/{} to trigger the sensor: {}".
             format(sensor_data_file_name, sensor_name))

    sensor_data_file = "/var/run/ipmitool/{}".format(sensor_data_file_name)

    tmp_sensor_datafile = "/tmp/{}".format(sensor_data_file_name)
    print('sensor_data_file: {}'.format(sensor_data_file))

    con_ssh = ControllerClient.get_active_controller()

    # First create a backup of the original sensor data file
    # rc, output = con_ssh.exec_sudo_cmd(cmd='cp {} {}.bkup'.format(sensor_data_file,
    #                                                          sensor_data_file),
    #                               fail_ok=False)

    # Update the sensor value in the data file
    sensor_name = sensor_name.replace('/', r'\/')
    expression = r"sed 's/\({}.* | .* | .* |\) ok/\1 {}/'".format(sensor_name, sensor_value)

    con_ssh.exec_sudo_cmd(cmd='{} < {} > {}'.format(expression, sensor_data_file, tmp_sensor_datafile), fail_ok=False)
    # con_ssh.exec_sudo_cmd(cmd='{} < {} > {}'.format(expression, sensor_data_file, sensor_data_file), fail_ok=False)

    con_ssh.exec_sudo_cmd(cmd='cp {} {}'.format(tmp_sensor_datafile, sensor_data_file), fail_ok=False)

    LOG.info("Check sed sensor status successful")
    output = con_ssh.exec_sudo_cmd(cmd='grep "{}" {}'.format(sensor_name, sensor_data_file), fail_ok=False)[1]

    escaped_name = re.escape(sensor_name)
    assert re.search(r'{} .* \| {}'.format(escaped_name, sensor_value), output), "sed unsuccessful"
    LOG.info("Sensor data updated successfully")


def clear_events(host):
    """Clear an event and restore all sensors to original values.

    Args:
        host: The host that should be restored
    """

    LOG.info("Restore the sensordata file /var/run/ipmitool/hwmond_{}_sensor_data to original.".format(host))

    sensor_data_file = '/var/run/ipmitool/hwmond_{}_sensor_data'.format(host)

    # original_sensor_datafile = "/var/run/ipmitool/nokia_sensor_data.ok"
    original_sensor_datafile = "{}/hwmond_{}_sensor_data".format(SYSADMIN_HOME, host)

    con_ssh = ControllerClient.get_active_controller()

    # Restore the original sensor data file
    con_ssh.exec_sudo_cmd(cmd='cp {} {}'.format(original_sensor_datafile, sensor_data_file), fail_ok=False)


def backup_sensor_data_files(hosts=None, con_ssh=None):
    if hosts is None:
        hosts = system_helper.get_hosts()
    elif isinstance(hosts, str):
        hosts = [hosts]

    LOG.info("Check and ensure sensor data files for {} are copied to {} if available".format(hosts, SYSADMIN_HOME))

    hosts_with_file = []
    con_ssh = ControllerClient.get_active_controller() if not con_ssh else con_ssh
    for host in hosts:
        dest_path = "{}/hwmond_{}_sensor_data".format(SYSADMIN_HOME, host)
        if con_ssh.file_exists(dest_path):
            hosts_with_file.append(host)
        else:
            source_path = BMCPath.SENSOR_DATA_FILE_PATH.format(BMCPath.SENSOR_DATA_DIR, host)
            if con_ssh.file_exists(source_path):
                con_ssh.exec_sudo_cmd('cp {} {}'.format(source_path, dest_path), fail_ok=False)
                hosts_with_file.append(host)

    LOG.info("Sensor data files for {} are copied to {}".format(hosts, SYSADMIN_HOME))
    return hosts
