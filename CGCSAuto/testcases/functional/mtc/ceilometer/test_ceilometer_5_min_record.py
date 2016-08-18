# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

import copy
import datetime
import time
import re
from pytest import fixture, mark, skip, raises, fail
from utils.tis_log import LOG
from utils.ssh import ControllerClient

CONTROLLER_PROMPT = '.*controller\-[01].*\$ '
PROMPT = '.* '

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
            if match_col_value == col_value[match_index]:
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
            print('skipping invalid table line: %s' % line)
            continue
        row = []
        for col in columns:
            row.append(line[col[0]:col[1]].strip())
        if table_['headers']:
            table_['values'].append(row)
        else:
            table_['headers'] = row

    return table_


def cmd_execute(action, param='', check_params=''):
    """
    Function to execute a command on a host machine
    """

    param_found = False

    controller_ssh = ControllerClient.get_active_controller()
    controller_ssh.set_prompt(CONTROLLER_PROMPT)
    exitcode, output = controller_ssh.exec_cmd('%s %s' % (action, param), expect_timeout=20)
    print("Output: %s" % output)
    if any (val in output for val in check_params):
        param_found = True

    return param_found, output


@mark.cpe_sanity
@mark.sanity
def test_742_ceilometer_5_min_record():
    """Verify that ceilometer records 5 minute pm
        Scenario:
        1. Get last ceilometer statistic
        2. Get list id from two last statistic rows
        3. Get statistic table by given id
        4. Assert numbers of rows in given table with expected
    """
    action = 'source /etc/nova/openrc; ceilometer sample-list'
    params = '-m vswitch.port.transmit.util'
    params_id = '-m vswitch.port.transmit.util -q resource='
    last_row_idxs = -2
    last_row_id_index = 0
    expected_id_stat_rows = 10

    # Get last ceilometer statistic:
    LOG.info('Get last ceilometer statistic')
    res, out = cmd_execute(action, param=params)
    statistic = table(out)


    # Get list id from two last statistic rows:
    LOG.info('Get list id from two last statistic rows')

    def last_rows_id():
        return [row[last_row_id_index]
                for row in statistic['values'][last_row_idxs:]]

    for ids in last_rows_id():
        param_id = ''.join([params_id, ids])
        # Get statistic table by given id:
        LOG.info(' Get statistic table by given id')
        res, id_stat = cmd_execute(action, param=param_id)
        id_statistic = table(id_stat)

        # Assert numbers of rows in given table with expected:
        LOG.info('Assert numbers of rows in given table with expected')
        assert(len(id_statistic['values']) == expected_id_stat_rows)

