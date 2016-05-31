# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

import logging
import time
import re
import sys
from pytest import fixture, mark, skip, raises, fail
from utils.tis_log import LOG
from utils import cli, exceptions, table_parser
from utils.ssh import ControllerClient, ssh_to_controller0
from consts.auth import Tenant
from keywords import vm_helper, nova_helper, system_helper, host_helper, cinder_helper, glance_helper


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

def test_alarm_timestamp_order(con_ssh=None):
    """
    Verify the chronological order to the alarms

    Scenario:
    1. Query the alarm table
    2. Verify the list is shown most recent alarm to oldest (based on timestamp) [REQ-14]
    """
    if not con_ssh:
        con_ssh = ControllerClient.get_active_controller()
    if not con_ssh.get_hostname() == 'controller-0':
        host_helper.swact_host()

    test_result = True
    LOG.info("Execute system alarm-history-list")
    with host_helper.ssh_to_host('controller-0') as cont_ssh:
        cmd = 'alarm-history-list --uuid --nowrap --limit 20'
        exitcode,output = cli.system(cmd, ssh_client=con_ssh,
                                     auth_info=Tenant.ADMIN,
                                     rtn_list=True, fail_ok=False,
                                     timeout=90)
    alarms_list = table(output)

    LOG.info('Verify the order of the timestamp of each entry')
    # Note the timestamp format will be, e.g 2014-06-25T16:58:57.324613
    previous_timestamp = ""
    for alarm in alarms_list['values']:
        LOG.info("The current alarm timestamp is: %s" % alarm[1])
        LOG.info("The previous time stamp is: %s" % previous_timestamp)
        if (previous_timestamp == ''):
            previous_timestamp = alarm[1]
        elif (previous_timestamp >= alarm[1]):
            previous_timestamp = alarm[1]
        else:
            assertion_text = "Data is not in reverse chronological order"
            test_result = False

    assert test_result