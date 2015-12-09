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

    def _grep_kill_process(self, host_ip, login, passwd, process_param=None,
                           timeout=20):
        """Function for find and kill process

        :param process_param: list of dictionaries with processes name,
                              threshold values, unexpected lines in grep output
            f.e. process_list = [{"proc_name": 'vswitch', 'threshold': 1,
                "except_line": "| grep -v neutron-avs-agent"},
                 {"proc_name": 'neutron-avs-agent'}]
        """
        if process_param is None:
            process_param = []

        # ssh to compute
        # ssh_conn = ssh_client(host_ip, login, password=passwd)
        # find necessary process
        for proc_count in range(process_param.get('threshold', 1)):
            # grep process
            add_val = process_param.get('except_line', '')
            proc = process_param["proc_name"]
            reboot = process_param.get('reboot', True)
            cmd = ("ps ax | grep %s %s | grep -v grep | grep -v restart" %
                   (proc, add_val))
            try:
                print (cmd)
                res = self.cmd_execute(cmd)
                date_cmd_exec = datetime.datetime.now()
                date_cmd_exec_str = date_cmd_exec.strftime("%a %b %d")
                print("Got answer on grep command: %s" % res)
            except Exception as e:
                 print(e)
                 print("pid for %s not found" % (proc, ))
            pids = []
            for line in res.split('\n'):
                if line != '':
                    if date_cmd_exec_str in line:
                        pass
                    else:
                        pid = line.strip().split(' ')[0]
                        pids.append(pid)
            count = len(pids)
            print('Pid found: %s' % pid)
            p = ' '.join(pids)
            if proc == 'hbsClient':
                kill_cmd = ' '.join(["pkill -stop", "hbsClient"])
            else:
                kill_cmd = ' '.join(["kill -9", p])

            print('killing process %s' % p)
            # kill process
            #self.cmd_execute(kill_cmd)
            time.sleep(5)
            # Wait until process restarted
            if not reboot and proc != 'hbsClient':
                rest_pid = self._wait_until_proc_restart(host_ip, login,
                                                         passwd,
                                                         add_val=add_val,
                                                         proc_name=proc,
                                                         timeout=timeout,
                                                         count=count)
                if(sorted(rest_pid) == sorted(pid)):
                    print("Processes are equal")

            # Wait until process restarted. If threshold is not reached
            # Only if host should be rebooted
            elif reboot and proc_count != process_param.get('threshold', 1) - 1:
                rest_pid = self._wait_until_proc_restart(host_ip, login,
                                                         passwd,
                                                         add_val=add_val,
                                                         proc_name=proc,
                                                         timeout=timeout,
                                                         count=count)
                self.assertNotEqual(sorted(rest_pid), sorted(pid),
                                    "Processes are equal")

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

    def _verify_that_vm_migrated(self, expected_location, vm_ids=None):
        """Function for verifying that VM migrated to another available compute

        :param expected_location: expected location
            f.e. 'compute-0'
        :param vm_ids: VM id
            f.e. vm_ids='6de7849b-6e17-44ca-aac9-67ba0c77d684'
        """
        # Verify that VMs are migrated to another available compute
        for v_id in vm_ids:
            cur_details_vm = self.parser.table(self.clients.nova('show', params=v_id))
            print("Verify that VM's are active")
            status = cli_helpers.get_column_value(cur_details_vm, 'status')
            self.assertEqual(status, "ACTIVE",
                             "Status is %s instead of 'ACTIVE'" % status)
            print("Get VM location")
            vm_location = cli_helpers.get_column_value(cur_details_vm,
                                                       'OS-EXT-SRV-ATTR:host')
            # Verify that VM migrated to other compute
            self.assertEqual(vm_location, expected_location,
                             'Vm located on %s insetead of %s' %
                             (vm_location, expected_location))

    def _find_kill_process_for_host(self, process_list, host='compute',
                                    proc_type='major', init_host=None):
        """Main function for kill process and verify host states

        """

        for params in process_list:
            self._grep_kill_process(self.host_ip, self.host_user_name,
                                    self.host_password, process_param=params)

            if proc_type == 'major' or proc_type == 'critical_non_reboot':
                print('Verify the unit availability changes to degraded')
                #cli_helpers.wait_until_host_state_equals(self, host_name,
                #                                         'availability',
                #                                         'degraded', timeout=30)

                if params["proc_name"] == 'hbsClient':
                    time.sleep(10)
                    resume_cmd = ' '.join(["pkill -cont", "hbsClient"])
                    self.cmd_execute(resume_cmd)
                print('Verify the unit availability changes to available')
                cli_helpers.wait_until_host_state_equals(self, host,
                                                         'availability',
                                                         'available')
            elif proc_type == 'critical_reboot':
                print('Verify that compute goes to reboot')
                print("Wait until 'availability' is changed to 'intest'")
                cli_helpers.wait_until_host_state_equals(self, host,
                                                         'availability',
                                                         'intest')
                print("Wait until 'operational' is changed to 'enabled'")
                cli_helpers.wait_until_host_state_equals(self, host,
                                                         'operational',
                                                         'enabled',
                                                         timeout=600,
                                                         check_interval=30)
                print("Wait until 'availability' is changed to 'available'")
                cli_helpers.wait_until_host_state_equals(self, host,
                                                         'availability',
                                                         'available')
            elif proc_type == 'minor':
                print("Verify that host 'availability' isn't changed")
                self._check_host_state_is_not_changed(host)

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

    def test_kill_critical_process_on_an_active_controller_node(self):
        """Kill Critical Process (sm) on the active Controller node
        """

        # table = self.parser.table(self.clients.sysinv('host-list'))
        sda_output = self.table(self.sys_execute('sda-list'))
        host_name = 'controller-0'
        #host_name = cli_helpers.master_slave_info(sda_output,
        #                                          node_type="master")
        host_info = self.table(self.sys_execute('host-show', host_name))
        #host_ip = self.get_column_value(host_info, 'mgmt_ip')
        host_ip = '10.10.10.2'
        proc = "sm"
        # ssh_conn = ssh_client(host_ip, "root", password="root")
        cmd = "echo 'li69nux' |sudo -S mv /usr/bin/sm /usr/bin/sm.save"
        print cmd
        cmd_1 = "echo 'li69nux' |sudo -S pkill -int %s" % proc
        print cmd_1
        try:
            # Rename sm process
            # res = ssh_conn.exec_command(cmd)
            self.cmd_execute(cmd)
            # Kill pmond - process
            # res_1 = ssh_conn.exec_command(cmd_1)
            self.cmd_execute(cmd_1)
        except:
            print("%s process was not killed" % (proc, ))
        print('Verify the unit availability changes to degraded')

        time.sleep(5)
        self.wait_until_host_state_equals(host_name,
                                                 'availability',
                                                 'degraded', timeout=30)
        # Restore pmond
        cmd_2 = "cp /usr/bin/sm.save /usr/bin/sm"
        # res = ssh_conn.exec_command(cmd_2)
        self.cmd_execute(cmd_2)

        # Verify that active controller is in available state
        print('Verify the unit availability changes to available')
        self.wait_until_host_state_equals(host_name,
                                                 'availability',
                                                 'available')

if __name__ == "__main__":
    process_kill = KillMajorCriticalProcess()
    process_kill.test_kill_critical_process_on_an_active_controller_node()
