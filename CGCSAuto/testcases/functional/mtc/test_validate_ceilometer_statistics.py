# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

import re
from pytest import fixture, mark, skip, raises, fail
from utils.tis_log import LOG
from utils import cli
from utils.ssh import ControllerClient
from utils import table_parser
from keywords import nova_helper, host_helper
from consts.auth import Tenant

CONTROLLER_PROMPT = 'wrsroot.*controller.* '


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

def get_number_of_elemnts_in_column(table=None, header_name=None,
                                    element_name=None, strict_match=True):
    """
    Get number of search element in table column

    :table param: parsed table
    :header_name param: name of header for search
    :element_name param: name of searched element
    :strict_match param: strict search or element existence in line
                                                                (True or False)

    get_number_of_elemnts_in_column(neutron_port_list_table,
                                                "fixed_ips", 'image.',
                                                strict_match=False)
    """
    counter = 0
    column_index = None
    for header in table["headers"]:
        if header == header_name:
            column_index = table["headers"].index(header)

    if column_index is not None:
        for value in table['values']:
            if strict_match:
                if element_name == value[column_index]:
                    counter = counter + 1
            else:
                if element_name in value[column_index]:
                    counter = counter + 1
    return counter

def cmd_execute(action, param='', check_params=''):
    """
    Function to execute a command on a host machine
    """

    param_found = False

    controller_ssh = ControllerClient.get_active_controller()
    controller_ssh.set_prompt(CONTROLLER_PROMPT)
    exitcode, output = controller_ssh.exec_cmd('%s %s' % (action, param), expect_timeout=30)
    print("Output: %s" % output)
    if any (val in output for val in check_params):
        param_found = True

    return param_found, output


@mark.cpe_sanity
@mark.sanity
def test_tc402_validate_statistics_for_one_meter():
    """
    Validate statistics for one meter

    """
    # List with column names
    column_names_list = ['Count', 'Min', 'Max', 'Avg']

    LOG.tc_step('Get ceilometer statistics table')
    # Verify that all the instances were successfully launched
    res, out = cmd_execute('source /etc/nova/openrc; ceilometer statistics -m image.size')

    stats_table = table(out)

    # Get first table value in first column
    first_value = stats_table["values"][0][0]

    LOG.debug('Check that count, min, max, avg values are non-zero')
    for column_name in column_names_list:
        column_value = get_column_value_from_multiple_columns(stats_table,
                                                               'Period',
                                                               first_value,
                                                               column_name)
        if (float(column_value) == 0.0):
            print("Parameter %s value is equal to 0" % column_name)
            assert(not(float(column_value) == 0.0))


@mark.sanity
def test_401_validate_ceilometer_meters_exist():
    """
    Validate ceilometer meters exist
    Verification Steps:
    1. Get ceilometer meter-list
    2. Check meters for router, subnet, image, and vswitch exists
    """

    LOG.tc_step('Get ceilometer meter-list')
    cmd = "ceilometer meter-list"
    LOG.info("Sending command: {}".format(cmd))
    exitcode, output = cmd_execute('source /etc/nova/openrc; ceilometer meter-list --limit 5000')

    meter_table = table_parser.table(output)

    tables_list = ['neutron router-list', 'neutron subnet-list']
    con_ssh = ControllerClient.get_active_controller()

    LOG.tc_step('Check meters for router and subnet')
    for value in tables_list:
        table_name = value.split()[0]
        table_action = value.split()[1]

        cmd = value
        exitcode, answer = con_ssh.exec_cmd(cmd)
        table = table_parser.table(answer)

        table_len = len(table['values'])
        LOG.info("Table %s length is: %s" % (value, table_len))

        search_name = value.split()[1].split("-")[0]
        meters_num = get_number_of_elemnts_in_column(meter_table,
                                                    "Name",
                                                    search_name,
                                                    strict_match=True)
        LOG.info("Number of elements in ceilometer table is: %s"
                  % meters_num)

        if meters_num >= table_len:
            match_flag = True
        else:
            LOG.info("Number of {} meters - {} is lower than table {} length - {}".format(
                search_name, meters_num, value, table_len))
            match_flag = False

        assert match_flag == True

    LOG.tc_step('Check meters for image')
    image_table = table_parser.table(cli.nova('image-list'))
    for header in image_table["headers"]:
        if header == "ID":
            index_value = image_table["headers"].index(header)
    image_id_list = []
    for id_value in image_table['values']:
        LOG.info("ID value is %s" % id_value[index_value])
        image_id_list.append(id_value[index_value])
    for id_value in image_id_list:
        meters_num = get_number_of_elemnts_in_column(meter_table,
                                                    "Resource ID",
                                                    id_value,
                                                    strict_match=True)

        if (meters_num == 0):
            LOG.info("No image resource IDs found.")
        assert meters_num != 0

    LOG.tc_step('Check meters for vswitch')
    meters_num = get_number_of_elemnts_in_column(meter_table,
                                                "Name",
                                                "vswitch.engine.util",
                                                strict_match=True)
    if meters_num == 0:
        LOG.info("No vswitch resource IDs found.")
    assert meters_num != 0


