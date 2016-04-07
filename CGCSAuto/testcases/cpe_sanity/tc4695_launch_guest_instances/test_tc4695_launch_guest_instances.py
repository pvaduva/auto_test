# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.


import sys
import copy
import datetime
import time
import paramiko
import re
from pytest import fixture, mark, skip, raises, fail
from utils.tis_log import LOG
from utils import cli, exceptions


class LaunchInstances():
    """Class to launch instances
    """

    def __init__(self, host_ip):
        self.host_ip = host_ip
        self.ssh = paramiko.SSHClient()
        self.ssh.load_system_host_keys()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect("%s" % self.host_ip, username="wrsroot", password="li69nux")


    def get_column_value_from_multiple_columns(self, table, match_header_key,
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

    def get_column_value(self, table, search_value):
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

    def table(self, output_lines):
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

    def sys_execute(self, action, param=''):
        """
        Function to execute a command on a host machine
        """
        data = ''

        ssh_stdin, ssh_stdout, ssh_stderr = self.ssh.exec_command("source /etc/nova/openrc; %s %s" % (action, param))
        return ssh_stdout.readlines()
        for row in ssh_stdout.readlines():
            print (row)
            data = data.join(row)
        self.print_out (ssh_stdout.readlines())
        return data

    def cmd_execute(self, action, param='', check_params=''):
        """
        Function to execute a command on a host machine
        """

        data = ''
        param_found = False

        ssh_stdin, ssh_stdout, ssh_stderr = self.ssh.exec_command("%s %s" % (action, param))
        while True:
            line = ssh_stdout.readline()
            if (line != ''):
                print (line)
                if any (val in line for val in check_params):
                    param_found = True
            else:
                break

        return param_found


    def _launch_instance_on_controller(self):
        """Method to list a host subfunctions
        """

        test_res = True

        cmd = ("source /etc/nova/openrc; sh /home/wrsroot/instances_group0/launch_instances.sh")  
        print ("Command executed: %s" % cmd)
        result = self.cmd_execute(cmd)

        # Verify that all the instances were successfully launched
        instance_table = self.table(self.sys_execute('/usr/bin/nova list --all'))
        instance_list = ['tenant1-avp1', 'tenant1-avp2', 'tenant1-avp3', 'tenant1-avp4',
                         'tenant1-virtio1', 'tenant1-virtio2', 'tenant1-virtio3', 'tenant1-virtio4',
                          'tenant1-vswitch1', 'tenant1-vswitch2', 'tenant2-avp1', 'tenant2-avp2',
                          'tenant2-avp3', 'tenant2-avp4', 'tenant2-virtio1', 'tenant2-virtio2', 
                          'tenant2-vswitch1', 'tenant2-vswitch2']

        for name in instance_list:
            instance_status = self.get_column_value_from_multiple_columns(instance_table,
                                                                         "Name",
                                                                          name,
                                                                         'Status')
            if instance_status != 'ACTIVE':
                test_res = False
                break

        if test_res == True:
            print ('Test case: Passed')
        else:
            print ('Test case: Failed')
            assert 1==2

@mark.parametrize('host_ip', [
                  '128.224.150.141',
                  '10.10.10.2',
                  '128.224.151.212'])
def test_tc4695_launch_guest_instances(host_ip):
    launch_instances = LaunchInstances(host_ip)
    launch_instances._launch_instance_on_controller()
