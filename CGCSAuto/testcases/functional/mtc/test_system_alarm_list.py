# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

import time
import re
import sys
from pytest import fixture, mark, skip, raises, fail
from utils.tis_log import LOG
from utils import cli, exceptions
from utils.ssh import ControllerClient, ssh_to_controller0
from keywords import vm_helper, nova_helper, system_helper, host_helper, cinder_helper, glance_helper

CONTROLLER_PROMPT = '.*controller\-[01].*\$ '

def get_column_value_from_multiple_columns(table, match_header_key,
                                           match_col_value, search_header_key):
    """
    Function for getting column value from multiple columns

    """
    column_value = None
    col_index = None
    match_index = None
    for header_key in table["headers"]:
        if header_key == match_header_key:
            match_index = table["headers"].index(header_key)
    for header_key in table["headers"]:
        if header_key == search_header_key:
            col_index = table["headers"].index(header_key)

    if col_index is not None and match_index is not None:
        for col_value in table['values']:
            print("col value= %s" % col_value)
            if match_col_value in col_value[match_index]:
                column_value = col_value[col_index]
    return column_value


def get_column_value(table, search_value):
    """
    Function for getting column value

    Get value from table with two column
    :table param: parse table with two colums (dictionary)
    :search_value param: value in column for checking
    """
    column_value = None
    for col_value in table['values']:
        if search_value == col_value[0]:
            column_value = col_value[1]
    return column_value


def table(output_lines):
    """Parse single table from cli output.

    Return dict with list of column names in 'headers' key and
    rows in 'values' key.
    """
    table_ = {'headers': [], 'values': []}
    columns = None

    delimiter_line = re.compile('^\+\-[\+\-]+\-\+$')

    def _table_columns(first_table_row):
        """Find column ranges in output line.

        Return list of tuples (start,end) for each column
        detected by plus (+) characters in delimiter line.
        """
        positions = []
        start = 1  # there is '+' at 0
        while start < len(first_table_row):
            end = first_table_row.find('+', start)
            if end == -1:
                break
            positions.append((start, end))
            start = end + 1
        return positions

    if not isinstance(output_lines, list):
        output_lines = output_lines.split('\n')

    if not output_lines[-1]:
        # skip last line if empty (just newline at the end)
        output_lines = output_lines[:-1]

    for line in output_lines:
        if delimiter_line.match(line):
            columns = _table_columns(line)
            continue
        if '|' not in line:
            continue
        row = []
        for col in columns:
            row.append(line[col[0]:col[1]].strip())
        if table_['headers']:
            table_['values'].append(row)
        else:
            table_['headers'] = row

    return table_


def cmd_execute(action, check_params='', prompt=CONTROLLER_PROMPT):
    """
    Function to execute a command on a host machine
    """

    param_found = False

    controller_ssh = ControllerClient.get_active_controller()
    controller_ssh.set_prompt(prompt)
    exitcode, output = controller_ssh.exec_cmd('%s' % action, expect_timeout=60)
    print("Output: %s" % output)
    if any(val in output for val in check_params):
        param_found = True

    return param_found, output


def clear_alarms_list():
    """
    Method for clearing alarms
    """

    # Get the list of alarms
    cmd = 'source /etc/nova/openrc; system alarm-list --uuid'
    res, out = cmd_execute(cmd)
    alarm_table = table(out)

    # Clear the alarms
    if not alarm_table['values'] == []:
        for alarm in alarm_table['values']:
            if alarm[0].strip() != '':
                cmd = 'source /etc/nova/openrc; system alarm-delete %s' % alarm[0].strip()
                res, out = cmd_execute(cmd)
    time.sleep(2)

@mark.sanity
@mark.skipif(system_helper.is_small_footprint(), reason="Skip for small footprint lab")
def test_1443_system_alarm_list():
    """
    Verify system alarm-list command in the system

    Scenario:
    1. Execute "system alarm-list" command in the system.
    2. Reboot one active computes and wait 30 seconds.
    3. Verify commands return list of active alarms in table with expected
    rows.
    """

    test_result = True

    LOG.info("Get active computes")
    cmd = 'source /etc/nova/openrc; system host-list'
    res, out = cmd_execute(cmd)
    host_table = table(out)

    compute_list = []
    for host in host_table['values']:
        if re.match("compute", host[1].strip()) is not None:
            compute_list.append(host[1])

    # Clear the alarms currently present
    LOG.info("Clear the alarm table")
    clear_alarms_list()

    LOG.info("Execute system alarm-list. Verify header of " +
             "a table consist of correct items")

    # List existing alarms present in the system
    cmd = 'source /etc/nova/openrc; system alarm-list --nowrap --uuid'
    res, out = cmd_execute(cmd)
    alarm_list = table(out)

    # Verify that the alarm table contains the correct headers
    alarm_header = ['UUID', 'Alarm ID', 'Reason Text', 'Entity ID',
                    'Severity', 'Time Stamp']
    if alarm_list['headers'] != alarm_header:
        LOG.info("Fields in table not correct actual {0} expected {1}"
              .format(alarm_list['headers'], alarm_header))
        test_result = False

    LOG.info("Reboot compute and wait 30 seconds")
    compute_ssh = host_helper.reboot_hosts(compute_list[0])
    time.sleep(20)

    LOG.info("Verify alarm-list command returns list of active alarms")
    cmd = 'source /etc/nova/openrc; system alarm-list --nowrap --uuid'
    res, out = cmd_execute(cmd)
    alarm_list = table(out)

    if len(alarm_list['values']) != 0:
        for alarm in alarm_list['values'][0]:
            if re.match(".", alarm.strip()) is None:
                LOG.info("Alarm value in alarm list table is not correct. "
                                "Actual value: {0}".format(alarm))
                test_result = False
    else:
        LOG.info("Alarms are not present in alarm list")
        # Original below was set to False. Need to confirm with Aldo.
        test_result = True

    assert test_result

@mark.sanity
@mark.skipif(system_helper.is_small_footprint(), reason="Skip for small footprint lab")
def test_1446_system_alarm_show():
    """
    Verify system alarm-show command

    Scenario:
    1. Lock one compute.
    2. Execute system alarm list and get uuid.
    3. Execute system alarm-show -u <uuid>.
    4. Verify if in returned table are expected values.
    5. Unlock one compute.
    6. Verify system alarm-list and check if there is no entries is
    displayed.
    """

    LOG.info("Get active computes")
    cmd = 'source /etc/nova/openrc; system host-list'
    res, out = cmd_execute(cmd)
    host_table = table(out)

    compute_list = []
    for host in host_table['values']:
        if re.match("compute", host[1].strip()) is not None:
            compute_list.append(host[1])

    # Clear the alarms currently present
    LOG.info("Clear the alarm table")
    clear_alarms_list()

    # Raise a new alarm by locking a compute node
    # Get the compute
    LOG.info ("Lock compute and wait 30 seconds")
    compute_ssh = host_helper.lock_host(compute_list[0])
    time.sleep(20)

    LOG.info("Execute system alarm list and get uuid")
    # List existing alarms present in the system
    cmd = 'source /etc/nova/openrc; system alarm-list --uuid'
    res, out = cmd_execute(cmd)
    alarm_list = table(out)

    # Verify that the alarm table contains the correct alarm
    for alarm in alarm_list['values']:
        if re.match(compute_list[0], alarm[2].strip()) is not None:
            al_uuid = alarm[0]
            LOG.info("The current alarms in the system are: "
                  "{0}".format(alarm[0]))

            LOG.info("Execute system show uuid")
            cmd = 'source /etc/nova/openrc; system alarm-show {0}'.format(al_uuid)
            res, out = cmd_execute(cmd)
            alarm_show = table(out)

            LOG.info("Verify returned value in alarm-list is in sync with alarm-show")
            alarms_l = ['Alarm ID', 'Entity Instance ID', 'Severity',
                        'Reason Text']
            alarms_s = ['alarm_id', 'entity_instance_id', 'severity',
                        'reason_text']
            for _, (val1, val2) in enumerate(zip(alarms_l, alarms_s)):
                al_l = get_column_value_from_multiple_columns(alarm_list,
                                                              'UUID',
                                                               al_uuid,
                                                               val1)
                al_s = get_column_value(alarm_show, val2)
                if val1 == 'Entity Instance ID':
                    assert(al_l, re.findall('host={0}'
                                     .format(compute_list[0]), al_s)[0],
                                     "Alarm ID value in alarm-list is not in " +
                                     "sync with alarm-show value {0} != {1}"
                                     .format(al_l, al_s))
                else:
                    assert(al_l, al_s,
                                     "Alarm ID value in alarm-list is not in " +
                                     "sync with alarm-show value {0} != {1}"
                                    .format(al_l, al_s))

            LOG.info("Verify that alarm-show command properties consist of proper information")

            assert(len(alarm_show['values']), 0, "Alarm info is " +
                                "not present in alarm show")

            for alarm in alarm_show['values']:
                assert(re.match(".", alarm[1].strip()), None,
                                    "Alarm value in alarm list table is not " +
                                    "correct actual {0}".format(alarm))

    LOG.info("Unlock compute node and wait 30 seconds alarm disappeared from alarm-list table")
    # Clear the alarm by unlocking the compute node
    LOG.info("Unlock compute and wait 30 seconds")
    compute_ssh = host_helper.unlock_host(compute_list[0])
    time.sleep(30)

    LOG.info("Verify that entry is destroyed from alarm list table")
    # List existing alarms present in the system
    cmd = 'source /etc/nova/openrc; system alarm-list --uuid'
    res, out = cmd_execute(cmd)
    alarm_list = table(out)

    for alarm in alarm_list['values']:
        if re.match(compute_list[0], alarm[2].strip()) is not None:
            LOG.info( "The alarm was not removed from the alarm list table:")




def test_format_of_clear_alarm_list():
    """
    Verify format of the cleared alarm table

    The format of the clear alarm_state entry should include AlarmState,
    AlarmID, EntityInstanceId, Timestamp and Reason Text.  
    Other entries should be blank.

    Scenario:
    1. Execute "system clear-list" command in the system.
    2. Reboot one active computes and wait 30 seconds.
    3. Verify commands return list of active alarms in table with expected
    rows.
    """

    test_result = True
    LOG.info("Clear the alarm table")
    clear_alarms_list()

    LOG.info("Execute system alarm-list. Verify header of " +
             "a table consist of correct items")

    # List existing alarms present in the system
    cmd = 'source /etc/nova/openrc; system alarm-list --uuid'
    res, out = cmd_execute(cmd)
    alarm_list = table(out)

    LOG.info("Verify alarms were properly cleared")
    if len(alarm_list['values']) != 0:
        LOG.info("There are no alarms are not present in the alarm list")
        test_result = False

    # Verify the alarm header is present
    alarm_header = ['UUID', 'Time Stamp', 'Alarm ID', 'Reason Text', 'Entity ID', 'Severity']
    # if (alarm_list['headers'] != alarm_header):
    #     LOG.info("Fields in table not correct actual {0} expected {1}"
    #           .format(alarm_list['headers'], alarm_header))
    #     test_result = False
    assert len(alarm_list['headers']) == len(alarm_header), "alarm_list has {} fields, alarm_header has {} fields"\
                                                 .format(len(alarm_list['headers']), len(alarm_header))
    for alarm in alarm_header:
        if alarm not in alarm_list['headers']:
            LOG.info("Fields in table not correct actual {0} expected {1}"
            .format(alarm_list['headers'], alarm_header))
            test_result = False

    assert test_result
