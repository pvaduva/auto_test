
import re
import os
import random
import string
from datetime import datetime
from collections import defaultdict

from pytest import mark, fixture, skip

from utils.ssh import ControllerClient
from utils.tis_log import LOG
from utils import cli, table_parser
from consts.cgcs import VMStatus, VMMetaData
from consts.reasons import SkipReason
from consts.auth import Tenant

from keywords import vm_helper, host_helper, nova_helper, patching_helper, system_helper, keystone_helper

from testfixtures.fixture_resources import ResourceCleanup

NUM_VM = 5
DEF_PRIORITY = 3
DEF_MEM_SIZE = 1
DEF_DISK_SIZE = 1
DEF_NUM_VCPU = 2

MIN_PRI = 1
MAX_PRI = 10
LOG_RECORDS = {
    'reboot': [
        {
            'host': 'active-controller',
            'log-file': 'nfv-vim-events.log',
            'patterns': ['event-id [ ]* = (instance-evacuate-begin)'],
            # 'patterns': ['event-id [ ]* = (instance-evacuat[^ ]*)'],
            'checker': 'verify_vim_evacuation_events',
         },
    ],
    'force_reboot': [
        {
            'host': 'active-controller',
            'log-file': 'nfv-vim-events.log',
            'patterns': ['event-id [ ]* = (instance-evacuate-begin)'],
            # 'patterns': ['event-id [ ]* = (instance-evacuat[^ ]*)'],
            'checker': 'verify_vim_evacuation_events',
        },
    ],
}


LOG_RECORD_LINES = 10
TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S.%f'


def run_cmd(cmd, **kwargs):
    con_ssh = ControllerClient.get_active_controller()
    return con_ssh.exec_cmd(cmd, **kwargs)


def get_evcuation_priority(vm_id, fail_ok=False):
    return vm_helper.get_vm_meta_data(vm_id, meta_data_names=[VMMetaData.EVACUATION_PRIORITY], fail_ok=fail_ok)


def verify_vim_evacuation_events():
    self, log_file, patterns = (yield)

    if not self.expected_order:
        skip('Fail, not expecting any more log entries, while still found more to come')
        return

    start = self.start_time

    search = '\grep -E -B2 -A{} \'{}\' {} | tail -n {}'.format(
        LOG_RECORD_LINES-2, patterns, log_file, LOG_RECORD_LINES * self.num_vms * 5)

    log_entries = run_cmd(search, expect_timeout=120)[1]

    search_pattern = r'^=+.*\n^log-id \s*=\s*\d+.*\n^event-id \s*= (instance-evacuat[^\s]+).*\n(.*\n){3}'
    search_pattern += r'^entity \s*= ([^\s]+).*\n'
    search_pattern += r'^reason_text \s*= Evacuat.* instance ([^\s]+) .*\n.*\n*'
    search_pattern += r'^timestamp \s*= (.*)\n^=+.*'

    evacuation_pattern = re.compile(search_pattern, re.MULTILINE)

    records = re.finditer(evacuation_pattern, log_entries)

    if not records:
        LOG.warn('No log records found for key:\n{}\n'.format(search_pattern))
        return

    expected_order = self.expected_order[:]
    vm_priorities = {order[0]: order[1] for order in expected_order}
    LOG.info('vm_priorities=\n{}\n'.format(vm_priorities))

    count = 0
    current_record = None
    for record in records:
        if len(record.groups()) < 5:
            continue

        raw_timestamp = record.group(5).strip()
        timestamp = None
        if raw_timestamp:
            timestamp = datetime.strptime(raw_timestamp, TIMESTAMP_FORMAT)
            if timestamp < start:
                continue
        event_type = record.group(1).strip()
        vm_id = record.group(3).split('=')[2].strip()
        vm_name = record.group(4).strip()

        if event_type == 'instance-evacuate-begin':
            if current_record:
                assert timestamp >= current_record[0], 'Timestamp wrong\nprevious log found:{}\nnow:{}\n'.format(
                    current_record, [timestamp, vm_name, event_type, vm_id])

            current_record = [timestamp, vm_name, event_type, vm_id]

            expected_vm_id, expected_priority = expected_order[0]
            if expected_vm_id != vm_id:
                if vm_priorities[vm_id] != expected_priority:
                    msg = 'Wrong Evacuation Order: expecting Priority:{}, but found: {}' \
                      '\nexpecting VM:{}, hit VM:{}'.format(expected_priority,
                                                            vm_priorities[vm_id], expected_vm_id, vm_id)
                    msg += '\nexpected orders:{}\n'.format(vm_priorities)
                    msg += '\nactual saw now:{}\n'.format(current_record)
                    LOG.error(msg)
                    assert expected_priority in [None, MAX_PRI] and vm_priorities[vm_id] in [None, MAX_PRI], msg
                else:
                    LOG.warn('same priority orders, but different VMs \nexpecting:{}, found:{}'.format(
                        expected_vm_id, vm_id))

            expected_order.remove((vm_id, expected_priority))

            count += 1
            LOG.info('OK, record in order:\nvm_id={}, timestamp={}, event_type={}, vm_name={}\n'.format(
                vm_id, timestamp, event_type, vm_name))

    LOG.info('OK, total matched log records={}'.format(count))
    yield


def verify_compute_evacuation_events():
    while True:
        self, log_file, patterns = (yield)

        search = '\grep -E \'{}\' {} | tail -n {}'.format(
            patterns, log_file, self.num_vms * 50)

        start = self.start_time

        search_results = run_cmd(search)[1]

        expected_order = self.expected_order[:]

        vm_priorities = {item[0]: item[1] for item in expected_order}

        previous_record = None
        for line in search_results.splitlines():
            search_pattern = r'(\d{4}-\d\d-\d\d \d\d(:\d\d){2}\.\d+).*'
            search_pattern += r'\[instance: (.+)\].*Migration\((.+)\);.*, name=([^,]+),'

            compiled_pattern = re.compile(search_pattern)

            record = re.search(compiled_pattern, line)
            if not record:
                continue

            if len(record.groups()) < 5:
                continue

            if not expected_order:
                msg = 'Fail, not expecting any more log entries, while still found more to come'
                assert False, msg

            raw_timestamp = record.group(1).strip()
            timestamp = datetime.strptime(raw_timestamp, TIMESTAMP_FORMAT)
            if timestamp and timestamp < start:
                continue
            if 'type=evacuation' not in re.split(', ', record.group(4)):
                continue
            event_type = re.split(', ', record.group(4))[2].strip()
            vm_id = record.group(3)
            vm_name = record.group(5)

            expected_vm_id, expected_priority = expected_order[0]
            if expected_vm_id == vm_id:
                LOG.info('OK, in order: vm_id={}'.format(vm_id))
                expected_order.pop(0)

            elif vm_priorities[vm_id] != expected_priority:
                msg = 'Wrong Evacuation order: expecting priority:{}, actual:{}, vm_id:{}, timestamp:{}\n' \
                      'prvious record:{}'.format(expected_priority, vm_priorities, vm_id, timestamp, previous_record)
                assert False, msg
            else:
                expected_order.remove((vm_id, expected_priority))

            current_record = (timestamp, vm_id, vm_name, event_type)
            if previous_record:
                if previous_record[0] > timestamp:
                    msg = 'Wrong Evacuation order, previous timestamp:{} is newer than current:{},\nprevious:{}' \
                          '\ncurrent:{}'.format(previous_record[0], timestamp, previous_record, current_record)
                    assert False, msg

            previous_record = current_record

            LOG.info('OK, compute-log verfied:{}'.format(current_record))


def set_quotas(quotas, project_id=None, auth_info=Tenant.ADMIN):
    if auth_info is None:
        auth_info = Tenant.get_primary()

    if not project_id:
        project_id = keystone_helper.get_tenant_ids(Tenant.get_primary()['tenant'])[0]

    current_quotas = table_parser.table(cli.openstack('quota show {}'.format(project_id),
                                                      auth_info=auth_info, fail_ok=False))['values']
    supported_quotas = [v[0] for v in current_quotas]

    if quotas:
        args = ' '.join(['--{}={}'.format(k, v) for k, v in quotas.items() if k in supported_quotas]).strip()
        if args:
            cli.openstack('quota set {} {}'.format(args, project_id), auth_info=auth_info, fail_ok=False)
    return True


def get_quotas(quota_names, project_id=None, auth_info=Tenant.ADMIN):
    quotas = dict()
    names = list()

    if quota_names:
        if auth_info is None:
            auth_info = Tenant.get_primary()

        if not project_id:
            project_id = keystone_helper.get_tenant_ids(Tenant.get_primary()['tenant'])[0]

        if isinstance(quota_names, str):
            names = [quota_names]
        else:
            names = list(quota_names)

        table = table_parser.table(cli.openstack('quota show {}'.format(project_id),
                                                 auth_info=auth_info, fail_ok=False))
        while names:
            name = names.pop()
            value = table_parser.get_value_two_col_table(table, name, strict=True)
            if value.strip():
                quotas[name] = value.strip()

        if names:
            LOG.warn('Quota not found for names:{}'.format(quota_names))

    return quotas, names


class TestPrioritizedVMEvacuation:

    quotas_expected = {'instances': 5, 'cores': 36, 'volumes': 10}
    quotas_saved = dict()

    @fixture(scope='class', autouse=True)
    def change_save_settings(self, request):
        def restore_settings():
            set_quotas(TestPrioritizedVMEvacuation.quotas_saved)

        expected = TestPrioritizedVMEvacuation.quotas_expected
        saved = TestPrioritizedVMEvacuation.quotas_saved

        current, unknown_quota_names = get_quotas(list(expected.keys()))

        if unknown_quota_names:
            skip('Unknown quotas:{}'.format(unknown_quota_names))
            return

        new_quotas = dict()
        for quota_name in expected:
            if int(current[quota_name]) < expected[quota_name]:
                saved[quota_name] = current[quota_name]
                new_quotas[quota_name] = expected[quota_name]

        if new_quotas:
            if not set_quotas(new_quotas):
                skip('Unable to adjust quota to:{}'.format(new_quotas))
            request.addfinalizer(restore_settings)

    @mark.parametrize(('operation', 'set_on_boot', 'prioritizing', 'vcpus', 'mem', 'root_disk', 'swap_disk'), [
        ('reboot', False, 'diff_priority', 'same_vcpus', 'same_mem', 'same_root_disk', 'same_swap_disk'),
        ('reboot', False, 'same_priority', 'diff_vcpus', 'same_mem', 'same_root_disk', 'same_swap_disk'),
        ('reboot', True, 'same_priority', 'same_vcpus', 'diff_mem', 'same_root_disk', 'same_swap_disk'),
        ('reboot', True, 'same_priority', 'same_vcpus', 'same_mem', 'diff_root_disk', 'same_swap_disk'),
        ('reboot', True, 'same_priority', 'same_vcpus', 'same_mem', 'same_root_disk', 'diff_swap_disk'),
        ('reboot', True, 'diff_priority', 'same_vcpus', 'same_mem', 'same_root_disk', 'same_swap_disk'),
        ('reboot', True, 'diff_priority', 'diff_vcpus', 'same_mem', 'same_root_disk', 'same_swap_disk'),
        ('reboot', True, 'diff_priority', 'diff_vcpus', 'diff_mem', 'diff_root_disk', 'same_swap_disk'),
        ('force_reboot', False, 'diff_priority', 'same_vcpus', 'same_mem', 'same_root_disk', 'same_swap_disk'),
        ('force_reboot', True, 'diff_priority', 'same_vcpus', 'same_mem', 'same_root_disk', 'same_swap_disk'),
    ])
    def test_prioritized_vm_evacuations(self, operation, set_on_boot, prioritizing, vcpus, mem, root_disk, swap_disk):
        """

        Args:
            operation:      operations to perform on the hosting compute node
            set_on_boot:    whether to boot VMs with meta data: sw:wrs:recovery_priority
            prioritizing:   whether all VMs have same Evacuation-Priority
            vcpus:          whether all VMs have same number of VCPU
            mem:            whether all VMs have same amount of memory
            root_disk:      whether all VMs have the same size of root disk
            swap_disk:      whether all VMs have the same size of swap disk

        Returns:

        Steps:
            1   make sure the requirements are meet for the intended VM operation
            2   create flavor
            3   create VM
            4   reboot the hosting node
            5   checking the evacuation/migration order
        """
        self.vms_info = defaultdict()
        self.init_vm_settings(operation, set_on_boot, prioritizing, vcpus, mem, root_disk, swap_disk)
        self.check_resource()
        self.create_flavors()
        self.create_vms()
        self.check_vm_settings()
        self.trigger_evacuation()
        self.check_vm_status()
        self.check_evaucation_orders()
        self.check_vm_settings()

    def check_vm_settings(self):
        self.check_vm_status()

        LOG.tc_step('Check if the evacuation-priority actually set')
        for vm_info in self.vms_info.values():
            recovery_priority = get_evcuation_priority(vm_info['vm_id'], fail_ok=False)
            if not recovery_priority:
                assert vm_info['priority'] is None, \
                    'Evacuation-Priority on VM is not set, expected priority:{}, actual:{}, vm_id:{}'.format(
                        vm_info['priority'], recovery_priority, vm_info['vm_id'])
            else:
                assert int(recovery_priority[VMMetaData.EVACUATION_PRIORITY]) == vm_info['priority'], \
                    'Evacuation-Priority on VM is not set, expected priority:{}, actual:{}, vm_id:{}'.format(
                        vm_info['priority'], recovery_priority, vm_info['vm_id'])

        LOG.info('OK, evacuation-priorities are correctly set')

    def check_vm_status(self):
        LOG.tc_step('Checking states of VMs')
        if not self.vms_info:
            skip('No VMs to check')
            return

        for vm_info in self.vms_info.values():
            vm_helper.wait_for_vm_values(vm_info['vm_id'], timeout=1200, status=[VMStatus.ACTIVE])

        LOG.info('OK, all VMs are in ACTIVE status\n')

    def check_evaucation_orders(self):
        LOG.tc_step('Checking the order of VM evacuation')

        vm_priorities = [(vm_info['vm_id'], vm_info['priority'])
                         for vm_info in self.vms_info.values() if 'priority' in vm_info]
        self.expected_order = sorted(vm_priorities, key=lambda item: int(item[1]))
        self.expected_order += [(vm_info['vm_id'], None)
                         for vm_info in self.vms_info.values() if 'priority' not in vm_info]

        base_log_dir = '/var/log'

        for log_info in LOG_RECORDS[self.operation]:
            checker = eval(log_info['checker'] + '()')
            checker.send(None)
            log_file = os.path.join(base_log_dir, log_info['log-file'])
            patterns = '|'.join(log_info['patterns'])
            checker.send((self, log_file, patterns))
        LOG.info('OK, the VMs were evacuated in expected order:\n{}\n'.format(vm_priorities))

    def trigger_evacuation(self):
        LOG.tc_step('Triggering evacuation on host: {} via action:{}'.format(self.current_host, self.operation))
        action = self.operation.lower()

        self.start_time = patching_helper.lab_time_now()[1]

        if action in ['reboot', 'force_reboot']:
            force_reboot = (action != 'reboot')
            host_helper.reboot_hosts(self.current_host, force_reboot=force_reboot, fail_ok=False)
        else:
            skip('Not supported action:{}'.format(action))

        LOG.info('OK, triggered evacuation by {} host:{}'.format(self.operation, self.current_host))

    def set_evacuate_priority(self, vm_id, priority, fail_ok=False):
        data = {VMMetaData.EVACUATION_PRIORITY: priority}
        self.meta_data = data
        return vm_helper.set_vm_meta_data(vm_id, data, fail_ok=fail_ok, check_after_set=True)


    def delete_evacuate_priority(sel, vm_id, fail_ok=False):
        return vm_helper.delete_vm_meta_data(vm_id, [VMMetaData.EVACUATION_PRIORITY], fail_ok=fail_ok)


    @mark.parametrize( ('operation, priority'), [
        ('set', random.randint(-1 * MAX_PRI, MIN_PRI)),
        ('set', random.randint(MIN_PRI, MAX_PRI+1)),
        ('set', random.randint(MAX_PRI + 1, 100)),
        ('set', ''),
        ('set', 'random'),
        ('delete', ''),
    ])
    def test_setting_evacuate_priority(self, operation, priority):
        LOG.tc_step('Luanch VM for test')

        if not hasattr(TestPrioritizedVMEvacuation, 'vm_id'):
            TestPrioritizedVMEvacuation.vm_id = vm_helper.boot_vm()[1]
            ResourceCleanup.add('vm', TestPrioritizedVMEvacuation.vm_id, scope='class')

        supported_operations = ['set', 'delete']
        if operation not in supported_operations:
            skip('Unsupported operation on meta data:{}, \nsupported:{}\n'.format(
                VMMetaData.EVACUATION_PRIORITY, supported_operations))
            return

        vm_id = TestPrioritizedVMEvacuation.vm_id

        LOG.info('OK, VM launched (or already existing) for test, vm-id:{}'.format(vm_id))

        expecting_fail = False
        if not priority or isinstance(priority, str):
            if operation != 'delete':
                expecting_fail = True

            if priority == 'random':
                priority = 'ab' + ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(3))
                expecting_fail = True
        else:
            try:
                to_set = int(priority)

            except ValueError:
                expecting_fail = True if operation == 'set' else False

            else:
                if to_set not in range(MIN_PRI, MAX_PRI+1):
                    LOG.info('Expecting the INVALID priority will be rejected, priority:{} on VM:{}'.format(
                        priority, vm_id))
                    expecting_fail = True

        if operation == 'set':
            code, output = self.set_evacuate_priority(vm_id, priority, fail_ok=expecting_fail)

        else:
            code, output = self.delete_evacuate_priority(vm_id, fail_ok=expecting_fail)

        if 0 == code:
            assert not expecting_fail, \
                'Fail to set Evacuation-priority:{} to VM:{}\ncode={}\noutput={}'.format(priority, vm_id, code, output)

            LOG.info('OK, {} Evacuation-Priority was accepted, set to "{}" on VM:{}'.format(operation, priority, vm_id))
        else:
            assert expecting_fail, \
                'Fail to set Evacuation-priority:{} to VM:{}\ncode={}\noutput={}, expecting failing, but not'.format(
                    priority, vm_id, code, output)

            LOG.info('OK, attempt to change Evacuation-Priority to:"{}" on VM:{} failed as expected'.format(
                priority, vm_id))

        priorities_set = get_evcuation_priority(vm_id, fail_ok=True)

        actual_priority = None
        if priorities_set and VMMetaData.EVACUATION_PRIORITY in priorities_set:
            try:
                actual_priority = int(priorities_set[VMMetaData.EVACUATION_PRIORITY])
            except ValueError:
                pass

        if operation == 'set':
            if not expecting_fail:
                assert actual_priority == priority, \
                    'Failed to set Evacuation-Priority, expecting:{}, actual:{}'.format(priority, actual_priority)
            else:
                assert actual_priority is None or actual_priority != priority, \
                    'Failed, expecting Evacuation-Priority not set, but not. expecting:{}, actual:{}'.format(
                        priority, actual_priority)
        else:
            assert actual_priority is None, \
                'Failed, expecting Evacuation-Priority been deleted, but not. actual:{}'.format(actual_priority)

    @staticmethod
    def get_dest_host():
        computes = host_helper.get_up_hypervisors()
        active_controller = system_helper.get_active_controller_name()

        return random.choice([compute for compute in computes if compute != active_controller])

    def create_vms(self):
        LOG.tc_step('Create VMs')

        vm_name_format = 'pve_vm_{}'

        num_priorities = len(self.prioritizing)

        for sn in range(self.num_vms):

            name = vm_name_format.format(sn)
            if self.set_on_boot and sn < num_priorities:
                vm_id = vm_helper.boot_vm(name,
                                          meta={VMMetaData.EVACUATION_PRIORITY: self.prioritizing[sn]},
                                          flavor=self.vms_info[sn]['flavor_id'],
                                          source='volume',
                                          avail_zone='nova')[1]
            else:
                vm_id = vm_helper.boot_vm(name,
                                          flavor=self.vms_info[sn]['flavor_id'],
                                          source='volume',
                                          avail_zone='nova')[1]
                if sn < num_priorities:
                    vm_helper.set_vm_meta_data(vm_id,
                                           {VMMetaData.EVACUATION_PRIORITY: self.prioritizing[sn]})

            LOG.info('OK, VM{} created: id={}\n'.format(sn, vm_id))
            self.vms_info[sn].update(vm_id=vm_id, vm_name=name, priority=self.prioritizing[sn])

            ResourceCleanup.add('vm', vm_id, scope='function')

        LOG.info('OK, VMs created:\n{}\n'.format([vm['vm_id'] for vm in self.vms_info.values()]))

        for sn, vm_info in self.vms_info.items():
            host = nova_helper.get_vm_nova_show_value(vm_info['vm_id'], 'OS-EXT-SRV-ATTR:hypervisor_hostname')

            if host != self.current_host:
                vm_helper.cold_migrate_vm(vm_info['vm_id'], fail_ok=False)

                actual_host = vm_helper.get_vm_host_and_numa_nodes(vm_info['vm_id'])[0]

                assert actual_host == self.current_host, \
                    'Failed to live-migrate VM:{} to host:{}, actual host:{}'.format(
                        vm_info['vm_id'], host, actual_host)

        LOG.info('OK, Evacuation-Priorities are set on VMs\n')

    def create_flavors(self):
        LOG.tc_step('Create flavors')

        flavor_name_format = 'pve_flavor_{}'
        for sn in range(self.num_vms):
            name = flavor_name_format.format(sn)
            flavor_id = nova_helper.create_flavor(name=name, vcpus=self.vcpus[sn], ram=int(self.mem[sn]) * 1024,
                                                  root_disk=self.root_disk[sn], swap=int(self.swap_disk[sn]) * 1024,
                                                  is_public=True)[1]
            self.vms_info.update({sn: {'flavor_name': name, 'flavor_id': flavor_id}})
            ResourceCleanup.add('flavor', flavor_id, scope='function')

        LOG.info('OK, flavors created:\n{}\n'.format([vm['flavor_id'] for vm in self.vms_info.values()]))

    def init_vm_settings(self, operation, set_on_boot, prioritizing, vcpus, mem, root_disk, swap_disk):
        self.operation = operation
        self.set_on_boot = set_on_boot

        if operation not in LOG_RECORDS:
            skip('Unspported operation:{}'.format(operation))
            return

        if 'diff' in prioritizing:
            self.prioritizing = list(range(1, NUM_VM + 1))
        else:
            self.prioritizing = [DEF_PRIORITY] * NUM_VM

        if 'diff' in vcpus:
            self.vcpus = list(range(NUM_VM * DEF_NUM_VCPU + 1,
                                    DEF_NUM_VCPU,
                                    -1 * DEF_NUM_VCPU))
        else:
            self.vcpus = [DEF_NUM_VCPU] * NUM_VM

        if 'diff' in mem:
            self.mem = list(range(DEF_MEM_SIZE + NUM_VM + 1,
                                  DEF_MEM_SIZE,
                                  -1))
        else:
            self.mem = [DEF_MEM_SIZE] * NUM_VM

        if 'diff' in root_disk:
            self.root_disk = list(
                range(DEF_DISK_SIZE * NUM_VM + 1,
                      DEF_DISK_SIZE,
                      -1 * DEF_DISK_SIZE))
        else:
            self.root_disk = [DEF_DISK_SIZE] * NUM_VM

        if 'diff' in swap_disk:
            self.swap_disk = list(
                range(DEF_DISK_SIZE * NUM_VM + 1,
                      DEF_DISK_SIZE,
                      -1 * DEF_DISK_SIZE))
        else:
            self.swap_disk = [DEF_DISK_SIZE] * NUM_VM

        LOG.info('OK, will boot VMs with settings:\npriorities={}\nvcpus={}\nmem={}\nroot_disk={}\nswap_dis={}'.format(
            self.prioritizing, self.vcpus, self.mem, self.root_disk, self.swap_disk
        ))

    def check_resource(self):
        LOG.tc_step('Check if the system supports the test')

        vm_helper.delete_vms()

        self.num_vms = NUM_VM
        self.current_host = self.get_dest_host()
        self.active_controller = system_helper.get_active_controller_name()

        if self.operation in ['reboot', 'force-reboot']:
            hypervisors = host_helper.get_up_hypervisors()

            if len(hypervisors) < 2:
                skip(SkipReason.LESS_THAN_TWO_HYPERVISORS)

            elif len(hypervisors) > 2:
                LOG.info('More than 2 hypervisors, will only leave 2 and lock the rest')
                to_lock = len(hypervisors) - 2
                for host in hypervisors:
                    if to_lock < 1:
                        break

                    if host in [self.active_controller, self.current_host]:
                        continue
                    LOG.info('Locking host:{}'.format(host))
                    host_helper.lock_host(host, fail_ok=False)
                    ResourceCleanup.add('host', host, scope='class')
                    to_lock -= 1

                LOG.info('OK, total locked host:{}'.format(len(hypervisors) - 2))
                self.hypervisors = host_helper.get_up_hypervisors()
                LOG.inof('OK, now active hypervisors:{}'.format(self.hypervisors))

        LOG.info('OK, system is ready to test')
