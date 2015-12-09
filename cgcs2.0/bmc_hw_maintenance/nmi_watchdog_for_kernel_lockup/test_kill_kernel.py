# Copyright (c) 2013-2015 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.


import copy
import sys
import datetime
import time
import paramiko
import re


class KillMajorCriticalProcess():
    """Confirm kill major/critical process
    """
    proc_list = []

    def __init__(self):
        self.commands = []
        self.commandLns = []
        self.cmdAttrs = {}
        self.host_ip = '10.10.10.2'
        self.host_user_name = 'wrsroot'
        self.host_password = 'li69nux'

    def print_out(self, stdoutput):
        for row in stdoutput:
            print ("%s" % row)

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

    def wait_until_host_state_equals(self, host_name, col_header, status,
                                     timeout=600, check_interval=0.1):
        """
        Function for waiting until host status is changed
        """
        end_time = time.time() + timeout
        while True:
            if time.time() < end_time:
                time.sleep(5)
                host_table = self.table(self.sys_execute('host-list'))
                host_status = self.get_column_value_from_multiple_columns(host_table,
                                                                     "hostname",
                                                                     host_name,
                                                                     col_header)
                if host_status == status:
                    print('Correct host state found')
                    break
                time.sleep(check_interval)
            else:
                message = "FAIL: Host status wasn't changed to expected %s" % status
                sys.exit(message)
        
    def tearDown(self):
        time.sleep(15)
        print('tearDown: Processes need to be restarted: ' % self.proc_list)
        if self.proc_list is not []:
            proc_list_copy = copy.deepcopy(self.proc_list)
            for param in proc_list_copy:
                print('tearDown: Process %s will be restarted.' %
                         (param['proc_name']))
                if param['proc_name'] == 'pmond':
                    self._wait_until_proc_restart(param['host_ip'],
                                                  param['login'],
                                                  param['passwd'],
                                                  add_val=param['add_param'],
                                                  proc_name=param['proc_name'])
                    cmd = None
                    self.proc_list.remove(param)
                else:
                    cmd = '/etc/init.d/%s restart' % (param['proc_name'], )
                if cmd is not None:
                    self.cmd_execute(cmd)
                    self._wait_until_proc_restart(param['host_ip'],
                                                  param['login'],
                                                  param['passwd'],
                                                  add_val=param['add_param'],
                                                  proc_name=param['proc_name'],
                                                  timeout=60)
                    self.proc_list.remove(param)
        super(KillMajorCriticalProcess, self).tearDown()

    def _lock_host(self, host_id, host_name):
        print('Lock Host')
        host_action(self, host_id, "lock")
        cli_helpers.wait_until_host_state_equals(self, host_name,
                                                 'administrative', 'locked')
        print('Verify the unit state changes to locked-disabled-online')
        cli_helpers.wait_until_host_state_equals(self, host_name,
                                                 'availability', 'online')

    def _unlock_host(self, host_id, host_name):
        print('Unlock Host')
        host_action(self, host_id, "unlock")
        cli_helpers.wait_until_host_state_equals(self, host_name,
                                                 'administrative', 'unlocked')
        cli_helpers.wait_until_host_state_equals(self, host_name,
                                                 'availability', 'intest')
        cli_helpers.wait_until_host_state_equals(self, host_name,
                                                 'operational', 'enabled',
                                                 timeout=600, check_interval=30)
        print('Verify the unit availability changes to available')
        cli_helpers.wait_until_host_state_equals(self, host_name,
                                                 'availability', 'available')

    def host_action(self, hostname, action, add_params=""):
        """
        Function to change host behavior.
        Possible actions include:
        lock, lock --force, unlock, swact, reset, reboot,
        reinstall, power-off, power-on, apply-profile.

        Hostnames: consists of controller, compute and storage

        Additional parameters: used for host-update's personality,
        host-apply-profile's if/stor/cpu profile name, and
        host-lock --force (add_params = --force)
        """
        cmds = ["unlock", "swact", "reset", "reboot", "reinstall", "power-off",
                "power-on", "apply-profile", "lock"]
        if action == "apply-profile" or action == "update":
            self.sys_execute("host-%s" % action, params="%s %s" % (hostname,
                                                             add_params))
        elif action in cmds:
            self.sys_execute("host-%s" % action, params="%s %s" % (add_params,
                                                             hostname))

    def sys_execute(self, action, param=''):
        """
        Function to execute a command on a host machine
        """
        data = ''

        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect("%s" % self.host_ip, username="wrsroot", password="li69nux")
        ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("source /etc/nova/openrc; system %s %s" % (action, param))
        return ssh_stdout.readlines()
        for row in ssh_stdout.readlines():
            print row
            data = data.join(row)
        self.print_out (ssh_stdout.readlines())
        return data


    def cmd_execute(self, action, param=''):
        """
        Function to execute a command on a host machine
        """

        data = ''

        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect("%s" % self.host_ip, username="wrsroot", password="li69nux")
        ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("%s %s" % (action, param))
        for row in ssh_stdout.readlines():
            data = data.join(row)
        self.print_out (ssh_stdout.readlines())
        return data

    def _wait_until_proc_restart(self, host_ip, login, passwd,
                                 timeout=20, add_val="",
                                 proc_name=None, count=1):
        """Function for waiting until process restarted
        """
        # ssh to host
        # ssh_conn = ssh_client(host_ip, login, password=passwd)
        end_time = time.time() + timeout
        cmd = ("ps ax | grep %s %s | grep -v grep | grep -v restart" %
               (proc_name, add_val))
        # wait until process re-started during timeout
        quantity = 0
        res = ''
        while True:
            if time.time() < end_time:
                try:
                    # ssh_conn = ssh_client(host_ip, login, password=passwd)
                    # res = ssh_conn.exec_command(cmd)
                    res = self.cmd_execute(cmd)
                    date_cmd_exec = datetime.datetime.now()
                    date_cmd_exec_str = date_cmd_exec.strftime("%a %b %d")
                except:
                    print("grep process %s failed with err: %s" %
                             (proc_name, err))
                if res != "":
                    pid = res.split('\n')[0].strip().split(' ')[0]
                    print('New pid found: %s' % pid)
                    pids = []
                    for line in res.split('\n'):
                        if line != '':
                            if date_cmd_exec_str in line:
                                pass
                            else:
                                pid = line.strip().split(' ')[0]
                                pids.append(pid)
                    quantity = len(pids)
                if quantity == count:
                    return pids
                time.sleep(0.1)
            else:
                try:
                    self.proc_list.append({'host_ip': host_ip,
                                           'login': login,
                                           'passwd': passwd,
                                           'proc_name': proc_name,
                                           'add_param': add_val})
                    if quantity < count and quantity != 0:
                        message = \
                            ("Restarted %s processes instead of %s during %s sec" %
                             (quantity, count, timeout))
                    else:
                        message = \
                            "Process %s isn't restarted during %s sec" % (proc_name,
                                                                          timeout)
                    exit(message)
                except Exception as e:
                    print(e)


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


    def _check_host_state_is_not_changed(self, host_val, param='hostname',
                                         timeout=30, field='availability',
                                         value='available', check_int=0.2):
        """Function for verification that host state isn't
           changed during timeout

        """
        end_time = time.time() + timeout
        while True:
            if time.time() < end_time:
                table = self.table(self.sys_execute('host-list'))

                cur_state = \
                    self.get_column_value_from_multiple_columns(table,
                                                               param,
                                                               host_val,
                                                               field)
                if cur_state != value:
                    msg = ("Host %s state is changed to unexpected %s value" %
                           (field, cur_state, ))
                    raise Exception(msg)
                time.sleep(check_int)
            else:
                break



    def test_cause_kernel_lockup(self):
        """Create a kernel lockup condition on the  active Controller node
           When the magic SysRq key combination is pressed with the command "c", 
           it causes a kernel panic (no subsequent commands will be possible
           after that); or when the following equivalent command is executed 
           in a command prompt:

           echo c > /proc/sysrq-trigger
        """

        sda_output = self.table(self.sys_execute('sda-list'))
        host_name = 'controller-0'
        host_info = self.table(self.sys_execute('host-show', host_name))
        #self.host_ip = self.get_column_value(host_info, 'mgmt_ip')

        cmd = "echo 'li69nux' |sudo -S mv /proc/sysrq-trigger /proc/sysrq-trigger.save"
        print cmd

        cmd_1 = "echo 'li69nux' |sudo -S sh -c 'echo c > /proc/sysrq-trigger'"
        print cmd_1

        # Execute the command
        try:
            self.cmd_execute(cmd)
            self.cmd_execute(cmd_1)
        except:
            print("%s Sys Req command was not executed")

        print('Verify the unit rebooted')

        time.sleep(5)
        self.wait_until_host_state_equals(host_name,
                                                 'availability',
                                                 'degraded', timeout=30)
        # Restore pmond
        cmd_2 = "echo 'li69nux' |sudo -S mv /proc/sysrq-trigger.save /proc/sysrq-trigger"
        self.cmd_execute(cmd_2)

        # Verify that active controller is in available state
        print('Verify the unit availability changes to available')
        self.wait_until_host_state_equals(host_name,
                                                 'availability',
                                                 'available')



if __name__ == "__main__":
    process_kill = KillMajorCriticalProcess()
    process_kill.test_cause_kernel_lockup()
