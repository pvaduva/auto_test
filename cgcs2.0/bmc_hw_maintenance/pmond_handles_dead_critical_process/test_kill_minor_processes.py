# Copyright (c) 2013-2015 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.


import copy
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
                host_table = cls.parser.table(cls.clients.sysinv('host-list'))
                host_status = self.get_column_value_from_multiple_columns(host_table,
                                                                     "hostname",
                                                                     host_name,
                                                                     col_header)
                if host_status == status:
                    break
                time.sleep(check_interval)
            else:
                message = "Host status wasn't changed to expected %s" % status
                raise exceptions.TimeoutException(message)
        
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

    def wait_until_all_services_correct(self, state='active', timeout=120,
                                        check_inter=0.1, add_timeout=20,
                                        host='controller-0'):
        end_time = time.time() + timeout
        while True:
            if time.time() < end_time:
                check_res = cli_helpers.check_sm_dump_resources(self,
                                                                state=state,
                                                                host=host)
                if check_res:
                    break
                time.sleep(check_inter)
            else:
                message = "Not all services are in state %s" % state
                raise exceptions.TimeoutException(message)
            if check_res:
                while True:
                    if time.time() < end_time:
                        check_res_add = \
                            cli_helpers.check_sm_dump_resources(self,
                                                                state=state,
                                                                host=host)
                        if not check_res_add:
                            msg = "Some services changed their states"
                            raise exceptions.BuildErrorException(msg)
                        time.sleep(check_inter)
                    else:
                        break

    def test_697_kill_critical_process_on_a_compute_node(self):
        """Kill Critical Process on a Compute node
        """
        # 1 Kill a Critical process on a Compute node that hosts at least 1 VM.
        # 2 Verify that the compute node goes for a reset and recovers.
        # 3 Verify that the VM(s) are evacuated to another Compute node.
        image = 'wrl5-avp'
        if self.check_tenant_exist():
            net_type = '-'.join([self.tenant.name, 'mgmt-net'])
        else:
            net_type = 'public-net0'
        vm_params = ['wrl5-avp-0', 'wrl5-avp-1']
        # Get compute id
        table = self.parser.table(self.sys_execute('host-list'))
        computes_list = cli_helpers.get_active_computes(table)
        first_compute = computes_list[0]
        second_compute = computes_list[1]
        host_id_2 = \
            cli_helpers.get_column_value_from_multiple_columns(table,
                                                               "hostname",
                                                               second_compute,
                                                               "id")
        print('Lock all active computes except first one')
        instance_helpers.lock_redundant_computes(self, computes_list, 1)
        # Boot two VMs
        vm_ids = []
        for val in vm_params:
            print('Boot instance')
            vm_uuid = self.boot_vm(self, image, val, network_type=net_type)
            vm_id = vm_uuid['nova']['uuid']
            vm_ids.append(vm_id)
            instance_helpers.wait_until_instance_state_is_changed(self, vm_id,
                                                                  'ACTIVE')
            print("Get VM location")
            cur_details_vm = self.parser.table(self.clients.nova('show', params=vm_id))
            vm_location = cli_helpers.get_column_value(cur_details_vm,
                                                       'OS-EXT-SRV-ATTR:host')
            # Verify that VM launched on first compute from computes_list
            self.assertEqual(vm_location, first_compute,
                             ('VM located on %s instead of %s' %
                              (vm_location, first_compute)))
            print('Wait until VM answered on ping')
            vm_ip = instance_helpers.get_vm_ip_addr(self, vm_name=val,
                                                    network_type=net_type)
            network_helpers.wait_until_vm_answer_on_ping(self, ip_addr=vm_ip)

        print("Unlock second compute")
        self._unlock_host(host_id_2, second_compute)

        # Waiting untill mtce start woking
        time.sleep(70)
        # define list of process and threshold values
        process_list = [[[{"proc_name": 'vswitch', 'threshold': 1,
                           "except_line": "| grep -v neutron-avs-agent"}],
                        'critical_reboot'],
                        [[{"proc_name": 'libvirtd', 'threshold': 4}],
                        'critical_reboot'],
                        [[{"proc_name": 'nova-compute', 'threshold': 4}],
                        'critical_reboot'],
                        [[{"proc_name": 'neutron-avs-agent',
                           'threshold': 4}], 'critical_reboot']]

        print("Kill process")
        # define list of initial and expected VM location
        # for every iteration of cycle with killing processes(reboot)
        # VM botted on first compute from list of available computes
        # In this part
        # after first three processes were killed compute would be reboot
        host_pair_list = [{'init_location': first_compute,
                           'expected_location': second_compute},
                          {'init_location': second_compute,
                           'expected_location': first_compute},
                          {'init_location': first_compute,
                           'expected_location': second_compute},
                          {'init_location': second_compute,
                           'expected_location': first_compute}]
        iteration = 0
        for proc_param in process_list:
            # get initial and expected VM location
            init_host = host_pair_list[iteration]['init_location']
            expected_host = host_pair_list[iteration]['expected_location']
            # kill process
            self._find_kill_process_for_host(proc_param[0], host='compute',
                                             proc_type=proc_param[1],
                                             init_host=init_host)
            if proc_param[1] == 'critical_reboot':
                print('Verify that VMs are migrated to other compute')
                self._verify_that_vm_migrated(expected_host, vm_ids=vm_ids)
                iteration += 1
            elif proc_param[1] == 'critical_non_reboot':
                print('Verify the unit availability changes to degraded')
                cli_helpers.wait_until_host_state_equals(self, init_host,
                                                         'availability',
                                                         'degraded', timeout=30)
                print('Verify the unit availability changes to available')
                cli_helpers.wait_until_host_state_equals(self, init_host,
                                                         'availability',
                                                         'available')

    def test_kill_major_process_on_a_compute_node(self):
        """Kill Major Process on a Compute node
        """
        # 1) Continuously Kill Major Pocess on the node until
        #   the threshold is reached.
        #   Verify that the process id is changing for every kill.
        # 2) Continue killing the process.
        #   Once the threshold is reached the node goes degraded
        # 3) Stop killing the process.
        #   After you stop killing the process and
        #   the process stays up the node changes to available.
        process_list = [{'proc_name': 'neutron-metadata-agent',
                         'threshold': 4,
                         'reboot': False},
                        {'proc_name': 'neutron-avr-agent', 'threshold': 4,
                         'reboot': False},
                        {'proc_name': 'neutron-dhcp-agent', 'threshold': 4,
                         'reboot': False},
                        {'proc_name': 'mtcClient', 'threshold': 4,
                         'reboot': False},
                        {'proc_name': 'hbsClient', 'threshold': 4,
                         'reboot': False},
                        {'proc_name': 'sysinv-agent', 'threshold': 4,
                         'reboot': False},
                        {'proc_name': 'ceilometer-agent-compute',
                         'threshold': 4,
                         'reboot': False}]
        self._find_kill_process_for_host(process_list)

    def test_kill_major_process_on_the_active_controller_node(self):
        """Kill Major Process on the active Controller node
        """

        process_list = [{'proc_name': 'mtcClient', 'threshold': 4,
                         'reboot': False},
                        {'proc_name': 'hbsClient', 'threshold': 1,
                         'reboot': False},
                        {'proc_name': 'sysinv-agent', 'threshold': 4,
                         'reboot': False}]
        self._find_kill_process_for_host(process_list, host='master_controller')

    def test_kill_major_process_on_the_standby_controller_node(self):
        """Kill Major Process on the standby Controller node
        """
        #  the process stays up the node changes to available.
        process_list = [{'proc_name': 'mtcClient', 'threshold': 4,
                         'reboot': False},
                        {'proc_name': 'hbsClient', 'threshold': 4,
                         'reboot': False},
                        {'proc_name': 'sysinv-agent', 'threshold': 4,
                         'reboot': False}]
        self._find_kill_process_for_host(process_list, host='slave_controller')

    def test_698_kill_pmond_major_process_on_a_compute_node(self):
        """Kill Major Process (pmond) on a Compute node
        """
        # 1) Continuously Kill Major Pocess on the node until
        #   the threshold is reached.
        #   Verify that the process id is changing for every kill.
        # 2) Continue killing the process.
        #   Once the threshold is reached the node goes degraded
        # 3) Stop killing the process.
        #   After you stop killing the process and
        #   the process stays up the node changes to available.
        process_list = [{'proc_name': 'pmond', 'threshold': 31,
                         'reboot': False}]
        self._find_kill_process_for_host(process_list)

    def test_701_1_kill_pmond_major_process_on_the_standby_controller(self):
        """Kill Major Process (pmond) on the standby Controller node
        """
        # 1) Continuously Kill Major Pocess on the node until
        #   the threshold is reached.
        #   Verify that the process id is changing for every kill.
        # 2) Continue killing the process.
        #   Once the threshold is reached the node goes degraded
        # 3) Stop killing the process.
        #   After you stop killing the process and
        #   the process stays up the node changes to available.
        # table = self.parser.table(self.clients.sysinv('host-list'))
        sda_output = self.parser.table(self.sys_execute('sda-list'))
        host_name = cli_helpers.master_slave_info(sda_output, node_type="slave")
        host_info = self.parser.table(self.sys_execute('host-show',
                                      params=host_name))
        host_ip = cli_helpers.get_column_value(host_info, 'mgmt_ip')
        proc = "pmond"
        # ssh_conn = ssh_client(host_ip, "root", password="root")
        cmd = "mv /usr/local/bin/pmond /usr/local/bin/pmond.save"
        cmd_1 = "pkill -int %s" % proc
        try:
            # Rename pmond
            # res = ssh_conn.exec_command(cmd)
            self.cmd_execute(cmd)
            # Kill pmond - process
            # res_1 = ssh_conn.exec_command(cmd_1)
            self.cmd_execute(cmd_1)
        except:
            raise exceptions.NotFound("%s process was not killed" % (proc, ))
        print('Verify the unit availability changes to degraded')

        time.sleep(5)
        cli_helpers.wait_until_host_state_equals(self, host_name,
                                                 'availability',
                                                 'degraded', timeout=30)
        # Restore pmond
        cmd_2 = "mv /usr/local/bin/pmond.save /usr/local/bin/pmond"
        # res = ssh_conn.exec_command(cmd_2)
        self.cmd_execute(cmd_2)

        # Verify that active controller is in available state
        print('Verify the unit availability changes to available')
        cli_helpers.wait_until_host_state_equals(self, host_name,
                                                 'availability',
                                                 'available')

    def test_704_1_kill_pmond_major_process_on_the_active_controller_node(self):
        """Kill Major Process (pmond) on the active Controller node
        """
        # 1) Continuously Kill Major Pocess on the node until
        #   the threshold is reached.
        #   Verify that the process id is changing for every kill.
        # 2) Continue killing the process.
        #   Once the threshold is reached the node goes degraded
        # 3) Stop killing the process.
        #   After you stop killing the process and
        #   the process stays up the node changes to available.

        # table = self.parser.table(self.clients.sysinv('host-list'))
        sda_output = self.parser.table(self.sys_execute('sda-list'))
        host_name = cli_helpers.master_slave_info(sda_output,
                                                  node_type="master")
        host_info = self.parser.table(self.sys_execute('host-show',
                                      params=host_name))
        host_ip = cli_helpers.get_column_value(host_info, 'mgmt_ip')
        proc = "pmond"
        # ssh_conn = ssh_client(host_ip, "root", password="root")
        cmd = "mv /usr/local/bin/pmond /usr/local/bin/pmond.save"
        cmd_1 = "pkill -int %s" % proc
        try:
            # Rename pmond
            # res = ssh_conn.exec_command(cmd)
            self.cmd_execute(cmd)
            # Kill pmond - process
            # res_1 = ssh_conn.exec_command(cmd_1)
            self.cmd_execute(cmd_1)
        except:
            raise exceptions.NotFound("%s process was not killed" % (proc, ))
        print('Verify the unit availability changes to degraded')

        time.sleep(5)
        cli_helpers.wait_until_host_state_equals(self, host_name,
                                                 'availability',
                                                 'degraded', timeout=30)
        # Restore pmond
        cmd_2 = "mv /usr/local/bin/pmond.save /usr/local/bin/pmond"
        # res = ssh_conn.exec_command(cmd_2)
        self.cmd_execute(cmd_2)

        # Verify that active controller is in available state
        print('Verify the unit availability changes to available')
        cli_helpers.wait_until_host_state_equals(self, host_name,
                                                 'availability',
                                                 'available')

    def test_699_kill_minor_process_on_a_compute_node(self):
        """Kill Minor Process on a Compute node
        """
        # 1) Continuously Kill Minor Process on the standby Controller
        #   until the threshold is reached
        # 2) Verify that the process id is changing for every kill.
        # 3) For Manual Execution when threshold is reached
        #   a log will be seen in Designlog. No need to automate this part.
        process_list = [{'proc_name': 'acpid', 'threshold': 11,
                         'reboot': False}]
        self._find_kill_process_for_host(process_list, proc_type='minor')

    def test_705_kill_minor_process_on_a_standby_controller_node(self):
        """Kill Minor Process on the standby Controller node
        """
        # 1) Continuously Kill Minor Process on the standby Controller until
        #   the threshold is reached
        # 2) Verify that the process id is changing for every kill.
        # 3) For Manual Execution when threshold is reached
        #   a log will be seen in Designlog. No need to automate this part.
        process_list = [{'proc_name': 'acpid', 'threshold': 11,
                         'reboot': False}]
        self._find_kill_process_for_host(process_list, proc_type='minor',
                                         host='slave_controller')

    def test_702_kill_minor_process_on_a_active_controller_node(self):
        """Kill Minor Process on the active Controller node
        """
        # 1) Continuously Kill Minor Process on the active Controller
        #   until the threshold is reached.
        # 2) Verify that the process id is changing for every kill.
        # 3) For Manual Execution when threshold is reached
        #   a log will be seen in Designlog. No need to automate this part.
        process_list = [{'proc_name': 'acpid', 'threshold': 3,
                         'reboot': False}]
        self._find_kill_process_for_host(process_list, proc_type='minor',
                                         host='controller-0')

    def test_900_kill_all_services_managed_by_sm_on_active_controller(self):
        """Kill all services (one by one) managed by SM (on active controller)

        On the active controller, one service/process at a time
        do the following:
        kill <process id>
        Wait for up to 60 or more seconds.

        Expec
        Process should be restarted within 120 seconds or so.
        (Wait up to 2 minutes.)
        SM may or may not move the service to disabled
        for a short amount of time.
        SM will set the current state of the service back to enabled-active
        if it changed the state to disabled when the process was killed.
        """
        print("Confirm 'controller-0' is active.")
        sda = self.parser.table(self.sys_execute('sda-list'))
        master = cli_helpers.master_slave_info(sda, node_type="master")
        self.assertEqual(master, 'controller-0',
                         'Master is %s instead of controller-0' % master)
        print("Confirm 'controller-1' is standby.")
        slave = cli_helpers.master_slave_info(sda, node_type="slave")
        self.assertEqual(slave, 'controller-1',
                         'Slave is %s instead of controller-1' % slave)

        master_info = self.parser.table(self.sys_execute('host-show',
                                        params=master))
        master_ip = cli_helpers.get_column_value(master_info, 'mgmt_ip')
        # Define list of processes
        process_list = [{"proc_name": 'sysinv-api', 'threshold': 1,
                         'reboot': False},
                        {"proc_name": 'sysinv-conductor', 'threshold': 1,
                         'reboot': False},
                        {"proc_name": 'nova-novncproxy', 'threshold': 1,
                         'reboot': False},
                        {"proc_name": 'hbsAgent', 'threshold': 1,
                         'reboot': False},
                        {"proc_name": 'keystone-all', 'threshold': 1,
                         'reboot': False},
                        {"proc_name": 'power-mgmt-conductor', 'threshold': 1,
                         'reboot': False},
                        {"proc_name": 'power-mgmt-api', 'threshold': 1,
                         'reboot': False},
                        {"proc_name": 'neutron-server', 'threshold': 1,
                         'reboot': False},
                        {"proc_name": 'nova-scheduler', 'threshold': 1,
                         'reboot': False},
                        {"proc_name": 'nova-conductor', 'threshold': 1,
                         'reboot': False},
                        {"proc_name": 'nova-cert', 'threshold': 1,
                         'reboot': False},
                        {"proc_name": 'nova-consoleauth', 'threshold': 1,
                         'reboot': False},
                        {"proc_name": 'cinder-api', 'threshold': 1,
                         'reboot': False},
                        {"proc_name": 'cinder-scheduler', 'threshold': 1,
                         'reboot': False},
                        {"proc_name": 'ceilometer-agent-central',
                         'threshold': 1, 'reboot': False},
                        {"proc_name": 'ceilometer-collector',
                         'threshold': 1, 'reboot': False},
                        {"proc_name": 'ceilometer-api',
                         'threshold': 1, 'reboot': False},
                        {"proc_name": 'ceilometer-alarm-evaluator',
                         'threshold': 1, 'reboot': False},
                        {"proc_name": 'ceilometer-alarm-notifier',
                         'threshold': 1, 'reboot': False},
                        {"proc_name": 'ceilometer-agent-notification',
                         'threshold': 1, 'reboot': False},
                        {"proc_name": 'heat-engine',
                         'threshold': 1, 'reboot': False},
                        {"proc_name": 'heat-api-cfn',
                         'threshold': 1, 'reboot': False},
                        {"proc_name": 'heat-api-cloudwatch',
                         'threshold': 1, 'reboot': False},
                        {"proc_name": 'mtcAgent',
                         'threshold': 1, 'reboot': False},
                        {"proc_name": 'heat-api',
                         'threshold': 1, 'reboot': False,
                         "except_line": "| grep -v heat-api-"},
                        {"proc_name": 'glance-registry', 'threshold': 1,
                         'reboot': False, "except_line": "| grep S"},
                        {"proc_name": '/usr/bin/glance-api', 'threshold': 1,
                         'reboot': False, "except_line": "| grep S"},
                        {"proc_name": '/usr/bin/nova-api', 'threshold': 1,
                         'reboot': False},
                        {"proc_name": '/usr/bin/cinder-volume', 'threshold': 1,
                         'reboot': False},
                        {"proc_name": 'dnsmasq', 'threshold': 1,
                         'reboot': False}]
        # Kill proces and verify that it is restarted
        for proc_info in process_list:
            self._grep_kill_process(master_ip, 'root', 'root',
                                    process_param=proc_info, timeout=120)
            # verify that state of controller isn't changed"
            self._check_host_state_is_not_changed(master)
            # Verify that controller-1 is remain standby controller and
            # state of services is not changed
            self.wait_until_all_services_correct(state='standby',
                                                 host='controller-1')
            # Verify that controller-0 is remain master controller
            self.wait_until_all_services_correct()

    def _controller_swact_due_to_service_death(self, proc_info):
        """Controller HA: Swact due to service process death x times

        Swact due to service process death x times
        For every service, verify a swact happens if a service process
        dies x times in  a given time interval.
        """
        print("Confirm 'controller-0' is active.")
        sda = self.parser.table(self.sys_execute('sda-list'))
        master = cli_helpers.master_slave_info(sda, node_type="master")
        self.assertEqual(master, 'controller-0',
                         'Master is %s instead of controller-0' % master)
        print("Confirm 'controller-1' is standby.")
        slave = cli_helpers.master_slave_info(sda, node_type="slave")
        self.assertEqual(slave, 'controller-1',
                         'Slave is %s instead of controller-1')

        host_list = ['controller-1', 'controller-0']

        # Kill proces and verify that it is restarted
        host = host_list[1]
        self._grep_kill_process(host, self.host_user_name, self.host_password,
                                process_param=proc_info, timeout=55)

        print("Wait until %s become standby" % host_list[1])
        cli_helpers.wait_until_all_services_started(self, state='standby',
                                                    host=host_list[1])

        print("Wait until %s become active" % host_list[0])
        cli_helpers.wait_until_all_services_started(self, state='active',
                                                    host=host_list[0])





if __name__ == "__main__":
    process_kill = KillMajorCriticalProcess()
    process_kill.test_702_kill_minor_process_on_a_active_controller_node()
