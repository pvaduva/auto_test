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
    """Class to manage the launching of vms
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

    def sys_execute(self, cmd, param=''):
        """
        Function to execute a command on a host machine
        """
        data = ''

        ssh_stdin, ssh_stdout, ssh_stderr = self.ssh.exec_command("source /etc/nova/openrc; %s %s" % (cmd, param))
        return ssh_stdout.readlines()
        for row in ssh_stdout.readlines():
            print(row)
            data = data.join(row)
        self.print_out (ssh_stdout.readlines())
        return data

    def cmd_execute(self, cmd, param='', check_params='', wait=False):
        """
        Function to execute a command on a host machine
        """

        data = ''
        param_found = False

        ssh_stdin, ssh_stdout, ssh_stderr = self.ssh.exec_command("%s %s" % (cmd, param))
        while True:
            line = ssh_stdout.readline()
            if (line != ''):
                print(line)
                if any (val in line for val in check_params):
                    param_found = True
            else:
                break

        return param_found

    def wait_execute(self, cmd, ref_header, ref_value, header_to_search, status,
                                     timeout=600, check_interval=0.1):
        """
        Function for waiting until a state is found
        """

        param_found = False
        end_time = time.time() + timeout

        while True:
            if time.time() < end_time:
                time.sleep(15)
                table_to_check = self.table(self.sys_execute(cmd))
                cell_status = self.get_column_value_from_multiple_columns(table_to_check,
                                                                     ref_header,
                                                                     ref_value,
                                                                     header_to_search)
                if cell_status == status:
                    param_found = True
                    print('Correct state found')
                    break
                time.sleep(check_interval)
            else:
                message = "FAIL: Table status wasn't changed to expected %s" % status
                print(message)
                break

        return param_found

    def _cold_migrate_an_instance(self):
        """Method to list a host subfunctions
        """

        test_res = True
        instance_list = ['tenant2-avp1', 'tenant1-virtio2']
        instance_dict = {}
        instance_info = []

        # First launch the instances
        for name in instance_list:
            cmd = "source /etc/nova/openrc; sh /home/wrsroot/instances_group0/launch_%s.sh" % name  
            print ("Command executed: %s" % cmd)
            result = self.cmd_execute(cmd)

        # Verify that all the instances were successfully launched
        for name in instance_list:
            # Get the instance ID 
            instance_table = self.table(self.sys_execute('/usr/bin/nova list --all'))
            instance_id = self.get_column_value_from_multiple_columns(instance_table,
                                                                         "Name",
                                                                          name,
                                                                         'ID')

            # Verify the location of the instances
            cmd = ("source /etc/nova/openrc; nova show %s" % instance_id)  
            print ("Command executed: %s" % cmd)
            instance_table = self.table(self.sys_execute(cmd))
            hostname = self.get_column_value(instance_table, "OS-EXT-SRV-ATTR:host")

            # Save the instance location
            instance_dict[name] = hostname
             
            # Cold migrate the instances
            cmd = "source /etc/nova/openrc; nova migrate %s" % instance_id
            check_params = ["100% complete"]
            print ("Command executed: %s" % cmd)
            result = self.cmd_execute(cmd, param='', check_params = check_params)

            # Wait for the instance state to change
            cmd = '/usr/bin/nova list --all'
            result = self.wait_execute(cmd, "Name", name, 'Status', 'VERIFY_RESIZE')

            # Get the instance status after migration
            instance_table = self.table(self.sys_execute('/usr/bin/nova list --all'))
            instance_status = self.get_column_value_from_multiple_columns(instance_table,
                                                                         "Name",
                                                                          name,
                                                                         'Status')
            if instance_status == 'VERIFY_RESIZE':
                cmd = "source /etc/nova/openrc; nova resize-confirm %s" % instance_id
                print ("Command executed: %s" % cmd)
                result = self.cmd_execute(cmd)
            else:
                test_res = False
                break

            # Verify the new location of the instances
            cmd = ("source /etc/nova/openrc; nova show %s" % instance_id)  
            print ("Command executed: %s" % cmd)
            instance_table = self.table(self.sys_execute(cmd))
            hostname = self.get_column_value(instance_table, "OS-EXT-SRV-ATTR:host")

            # Save the instance location
            if (instance_dict[name] == hostname):
                test_res = False
                break

        # Verify that all the instances were successfully resumed
        instance_table = self.table(self.sys_execute('/usr/bin/nova list --all'))

        for name in instance_list:
            instance_status = self.get_column_value_from_multiple_columns(instance_table,
                                                                         "Name",
                                                                          name,
                                                                         'Status')
            if instance_status != 'ACTIVE':
                test_res = False
                break

        return test_res

    def cold_migrate_guest_instances(self):
        """Method to list a host subfunctions
        """

        test_res = self._cold_migrate_an_instance()
        if test_res == True:
            print ('Test case: Passed')
        else:
            print ('Test case: Failed')
            assert 1==2


@mark.parametrize('host_ip', [
                  '128.224.150.141',
                  '10.10.10.2',
                  '128.224.151.212'])
def test_tc4699_cold_migration_guest_instances(host_ip):
    launch_instances = LaunchInstances(host_ip)
    launch_instances.cold_migrate_guest_instances()
