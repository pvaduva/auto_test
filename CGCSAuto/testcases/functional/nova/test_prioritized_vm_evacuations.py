
import re
import os
import random
from datetime import datetime

from pytest import mark, fixture

from utils.ssh import ControllerClient
from utils.tis_log import LOG

from keywords import vm_helper, host_helper, nova_helper, patching_helper, system_helper, cinder_helper

from testfixtures.fixture_resources import ResourceCleanup

NUM_VM = 5
DEF_PRIORITY = 3
DEF_MEM_SIZE = 1
DEF_DISK_SIZE = 1
DEF_NUM_VCPU = 2

VM_META_DATA = 'sw:wrs:recovery_priority'
MIN_PRI = 1
MAX_PRI = 10

LOG_RECORDS = {
    'reboot': [
        {
            'host': 'active-controller',
            'log-file': 'nfv-vim-events.log',
            'patterns': [
                'event-id [ ]* = (instance-evacuat[^ ]*)',
            ],
            'checker': 'verify_vim_evacuation_events',
         },
        # {
        #     'host': 'compute',
        #     'log-file': 'nova/nova-compute.log',
        #     'patterns': [
        #          'nova.compute.resource_tracker.*Migrat.*change='
        #     ],
        #     'checker': 'verify_compute_evacuation_events'
        #  }
    ],
}

LOG_RECORD_LINES = 10
TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S.%f'


def run_cmd(cmd, **kwargs):
    con_ssh = ControllerClient.get_active_controller()
    return con_ssh.exec_cmd(cmd, **kwargs)


def verify_vim_evacuation_events():
    self, log_file, patterns = (yield)

    start = self.start_time

    search = '\grep -E -B2 -A{} \'{}\' {} | tail -n {}'.format(
        LOG_RECORD_LINES-2, patterns, log_file, LOG_RECORD_LINES * self.num_vms * 30)

    LOG.info('TODO: vim log: cmd={}\n'.format(search))
    log_entries = run_cmd(search)[1]

    search_pattern = r'^=+.*\n^log-id \s*=\s*\d+.*\n^event-id \s*= (instance-evacuat[^\s]+).*\n(.*\n){3}'
    search_pattern += r'^entity \s*= ([^\s]+).*\n'
    search_pattern += r'^reason_text \s*= Evacuat.* instance ([^\s]+) .*\n.*\n*'
    search_pattern += r'^timestamp \s*= (.*)\n^=+.*\n'

    evacuation_pattern = re.compile(search_pattern, re.MULTILINE)
    records = re.finditer(evacuation_pattern, log_entries)

    if not records:
        LOG.warn('No log records found for key:\n{}\n'.format(search_pattern))
        return

    expected_order = self.expected_order[:]
    vm_priorities = {order[0]: order[1] for order in expected_order}

    current_record = None
    for record in records:
        if not expected_order:
            msg = 'Fail, not expecting any more log entries, while still found more to come'
            assert False, msg

        if len(record.groups()) < 5:
            LOG.info('TODO: too less info found, record=\n{}\n'.format(record.groups()))
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

        LOG.info('TODO:\n{}, {}, {}, {}\n'.format(vm_id, timestamp, event_type, vm_name))

        if event_type == 'instance-evacuate-begin':
            assert not current_record, \
                'Found another instance begin evacuate while preivous not finished yet. Previous:\n' \
                'at {}, vm_name={}, event_type:{}, vm_id={}'.format(raw_timestamp, vm_name, event_type, vm_id)
            current_record = [timestamp, vm_name, event_type, vm_id]

        elif not current_record:
            assert False, \
                'Log records not starting with "instance-evacuate-begin", Previous:\n' \
                'at {}, vm_name={}, event_type:{}, vm_id={}'.format(raw_timestamp, vm_name, event_type, vm_id)

        if current_record:
            msg = 'Log records out of order\nprevious:' \
                ' {}\ncurrent: {}, vm_name={}, event_type:{}, vm_id={}'.format(
                    current_record, raw_timestamp, vm_name, event_type, vm_id)

            assert timestamp >= current_record[0], 'Timestamp wrong\n' + msg
            assert vm_id == current_record[3], 'Another VM started evacuating while previous not finished\n' + msg

        expected_vm_id, expected_priority = expected_order[0]
        if expected_vm_id != vm_id:
            if vm_priorities[vm_id] != expected_priority:
                msg = 'Wrong Evacuation Order: expecting Priority:{}, but found: {}' \
                      '\nexpecting VM:{}, hit VM:{}'.format(expected_priority,
                                                            vm_priorities[vm_id], expected_vm_id, vm_id)
                LOG.error(msg)
                assert False, msg
            else:
                LOG.warn('TODO: same priority orders, but different VMs \nexpecting:{}, found:{}'.format(
                    expected_vm_id, vm_id))

        if event_type == 'instance-evacuated':
            current_record = None
            expected_order.remove((vm_id, expected_priority))

        LOG.info('TODO: OK, record in order:\nvm_id={}, timestamp={}, event_type={}, vm_name\n'.format(
            vm_id, timestamp, event_type, vm_name))


def verify_compute_evacuation_events():
    self, log_file, patterns = (yield)
    search = '\grep -E \'{}\' {} | tail -n {}'.format(
        patterns, log_file, self.num_vms * 50)

    start = self.start_time

    search_results = run_cmd(search)[1]

    expected_order = self.expected_order[:]
    LOG.info('TODO: compute log: expected_order:\n{}\n'.format(expected_order))

    vm_priorities = {item[0]: item[1] for item in expected_order}

    LOG.info('TODO: vm_priorities=\n{}\n'.format(vm_priorities))

    previous_record = None
    for line in search_results.splitlines():
        search_pattern = r'(\d{4}-\d\d-\d\d \d\d(:\d\d){2}\.\d+).*'
        search_pattern += r'\[instance: (.+)\].*Migration\((.+)\);.*, name=([^,]+),'

        compiled_pattern = re.compile(search_pattern)

        record = re.search(compiled_pattern, line)
        if not record:
            continue

        if len(record.groups()) < 5:
            LOG.info('TODO: unknown compute log format:{}\n'.format(record))
            continue

        if not expected_order:
            msg = 'Fail, not expecting any more log entries, while still found more to come'
            assert False, msg

        raw_timestamp = record.group(1).strip()
        timestamp = datetime.strptime(raw_timestamp, TIMESTAMP_FORMAT)
        if timestamp and timestamp < start:
            # LOG.info('TODO: discard older events:{}\n'.format(record))
            continue
        if 'type=evacuation' not in re.split(', ', record.group(4)):
            # LOG.info('TODO: not evacuation:\n{}\n'.format(record.group(4)))
            # LOG.info('TODO: not evacuation:groups=\n{}\n'.format(record.groups()))
            continue
        event_type = re.split(', ', record.group(4))[2].strip()
        vm_id = record.group(3)
        vm_name = record.group(5)

        LOG.info('TODO: compute log:\nvm_name={}, vm_id={}, timestamp={}, event_type\n'.format(
            vm_name, vm_id, timestamp, event_type))

        expected_vm_id, expected_priority = expected_order[0]
        if expected_vm_id == vm_id:
            LOG.info('OK, in order: vm_id={}'.format(vm_id))
            expected_order.pop(0)

        elif vm_priorities[vm_id] != expected_priority:
            LOG.info('TODO: \nexpected_vm_id={}, expected_priority={}, vm_id={}\n'.format(
                expected_vm_id, expected_priority, vm_id
            ))
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

        LOG.info('TODO: OK, compute-log verfied:{}'.format(current_record))


class TestPrioritizedVMEvacuation:

    quota_expected = {'instances': 5, 'cores': 20, 'volumes':10}
    quota_origin = dict()

    @fixture(scope='class', autouse=True)
    def change_save_settings(self, request):
        expected = TestPrioritizedVMEvacuation.quota_expected
        origin = TestPrioritizedVMEvacuation.quota_origin

        instances, cores = nova_helper.get_quotas(quotas=['instances', 'cores'])
        volumes = cinder_helper.get_quotas(quotas='volumes')[0]

        new_nova_quota = dict()
        new_cinder_quota = dict()
        if instances < expected['instances']:
            new_nova_quota.update(instances=expected['instances'])
        if cores < expected['cores']:
            new_nova_quota.update(instances=expected['instances'])

        if volumes < expected['volumes']:
            new_cinder_quota.update(volumes=volumes)

        if new_nova_quota:
            nova_helper.update_quotas(**new_nova_quota)
            origin.update(instances=instances, cores=cores)

        if new_cinder_quota:
            cinder_helper.update_quotas(**new_cinder_quota)
            origin.update(volumes=volumes)

        def restore_settings():
            quota_origin = TestPrioritizedVMEvacuation.quota_origin
            nova_settings = ['instances', 'cores']
            if 'instances' in quota_origin or 'cores' in quota_origin:
                quotas = {k: v for k, v in quota_origin.items() if k in nova_settings}
                nova_helper.update_quotas(**quotas)

            if 'volumes' in quota_origin:
                nova_helper.update_quotas(volumes=quota_origin['volumes'])

        request.addfinalizer(restore_settings)

    @mark.parametrize(('operation', 'prioritizing', 'vcpus', 'mem', 'root_disk', 'swap_disk'), [
        ('reboot', 'diff_priority', 'same_vcpus', 'same_mem', 'same_root_disk', 'same_swap_disk'),
        # ('reboot', 'same_priority', 'diff_vcpus', 'same_mem', 'same_root_disk', 'same_swap_disk'),
        # ('reboot', 'same_priority', 'same_vcpus', 'diff_mem', 'same_root_disk', 'same_swap_disk'),
        # ('reboot', 'same_priority', 'same_vcpus', 'diff_mem', 'same_root_disk', 'same_swap_disk'),
        # ('reboot', 'same_priority', 'same_vcpus', 'same_mem', 'diff_root_disk', 'same_swap_disk'),
        # ('reboot', 'same_priority', 'same_vcpus', 'same_mem', 'same_root_disk', 'diff_swap_disk'),
        # ('force_reboot', 'diff_priority', 'same_vcpus', 'same_mem', 'same_root_disk', 'same_swap_disk'),
    ])
    def test_prioritized_vm_evacuations(self, operation, prioritizing, vcpus, mem, root_disk, swap_disk):
        """

        Args:
            operation:      operations to perform on the hosting compute node
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
        self.vms_info = {}
        self.init_vm_settings(operation, prioritizing, vcpus, mem, root_disk, swap_disk)
        self.check_resource()
        self.create_flavors()
        self.create_vms()
        self.trigger_evacuation()
        self.check_evaucation_orders()

    def test_log(self):
        # vm_priorities = [(vm_info['vm_id'], vm_info['priority']) for vm_info in self.vms_info.values()]
        vm_priorities = [
            ('7a1f03c3-ed95-4e93-be71-a0126c9b5f10', 1),
            ('073620e5-45c6-49a6-81c0-7093815e06c3', 2),
            ('90769575-a379-4b6c-8fc0-c4eeb749443b', 3),
            ('a628b005-c441-40e2-91e9-1f99108ee790', 4),
            ('419643b1-b2bc-4f3b-a625-0798e6be7fa6', 5),
        ]
        LOG.info('TODO: vm_priorities:{}'.format(vm_priorities))

        self.expected_order = sorted(vm_priorities, key=lambda item: int(item[1]))

        LOG.info('\nTODO: expected_orders:{}\n'.format(self.expected_order))

        base_log_dir = '/var/log'

        time_string = '2017-08-11 18:49:37.313317'
        self.start_time = datetime.strptime(time_string, TIMESTAMP_FORMAT)
        self.operation = 'reboot'
        self.num_vms = 5

        for log_info in LOG_RECORDS[self.operation]:
            checker = eval(log_info['checker'] + '()')
            next(checker)
            log_file = os.path.join(base_log_dir, log_info['log-file'])
            patterns = '|'.join(log_info['patterns'])
            checker.send((self, log_file, patterns))

    def check_evaucation_orders(self):
        vm_priorities = [(vm_info['vm_id'], vm_info['priority']) for vm_info in self.vms_info.values()]
        LOG.info('TODO: vm_priorities:{}'.format(vm_priorities))

        self.expected_order = sorted(vm_priorities, key=lambda item: int(item[1]))

        LOG.info('\nTODO: expected_orders:{}\n'.format(self.expected_order))

        base_log_dir = '/var/log'

        for log_info in LOG_RECORDS[self.operation]:
            checker = eval(log_info['checker'] + '()')
            next(checker)
            log_file = os.path.join(base_log_dir, log_info['log-file'])
            patterns = '|'.join(log_info['patterns'])
            checker.send((self, log_file, patterns))

    def trigger_evacuation(self, fail_ok=False):
        LOG.tc_step('Triggering evacuation on host: {} via action:{}'.format(self.current_host, self.operation))
        action = self.operation.lower()

        self.start_time = patching_helper.lab_time_now()[1]

        LOG.info('TODO: Connecting to host:{}'.format(self.current_host))
        if action in ['reboot', 'force_reboot']:
            if action == 'reboot':
                LOG.info('TODO: reboot the host')
                force_reboot = False
            else:  # action == 'force_reboot':
                LOG.info('TODO: force-reboot the host')
                force_reboot = True
            code, output = host_helper.reboot_hosts(self.current_host, force_reboot=force_reboot, fail_ok=fail_ok)
        else:
            code, output = 0, 'Not supported action:{}'.format(action)

        LOG.info('TODO: host:{} is rebooted, code={}, output={}'.format(self.current_host, code, output))

    def set_evacuate_priority(self, vm_id, priority, fail_ok=False):
        data = {VM_META_DATA: priority}
        self.meta_data = data
        return vm_helper.set_vm_meta_data(vm_id, fail_ok=fail_ok, check_after_set=True, **data)

    @mark.parametrize('priority', [
        random.randint(-1 * MAX_PRI, MIN_PRI),
        random.randint(MIN_PRI, MAX_PRI+1),
        random.randint(MAX_PRI + 1, 100),
    ])
    def test_setting_evacuate_priority(self, priority):
        if not hasattr(TestPrioritizedVMEvacuation, 'vm_id'):
            TestPrioritizedVMEvacuation.vm_id = vm_helper.boot_vm()[1]
            ResourceCleanup.add('vm', TestPrioritizedVMEvacuation.vm_id, scope='class')

        vm_id = TestPrioritizedVMEvacuation.vm_id

        expecting_fail = False
        if priority not in range(MIN_PRI, MAX_PRI+1):
            LOG.info('Expecting the INVALID priority will be rejected, priority:{} on VM:{}'.format(priority, vm_id))
            expecting_fail = True

        code, output = self.set_evacuate_priority(vm_id, priority, fail_ok=expecting_fail)

        if 0 == code:
            assert not expecting_fail, \
                'Fail to set Evacuation-priority:{} to VM:{}\ncode={}\noutput={}'.format(priority, vm_id, code, output)

            LOG.info('OK, modifiying Evacuation-Priority was accepted: {} on VM:{}'.format(priority, vm_id))
        else:
            assert expecting_fail, \
                'Fail to set Evacuation-priority:{} to VM:{}\ncode={}\noutput={}, expecting failing, but not'.format(
                    priority, vm_id, code, output)

            LOG.info('OK, attempt to change Evacuation-Priority to:{} on VM:{} failed as expected'.format(
                priority, vm_id))

    @staticmethod
    def get_dest_host():
        computes = host_helper.get_up_hypervisors()
        active_controller = system_helper.get_active_controller_name()

        return random.choice([compute for compute in computes if compute != active_controller])

    def create_vms(self):
        self.current_host = self.get_dest_host()
        vm_name_format = 'pve_vm_{}'

        for sn in range(self.num_vms):
            name = vm_name_format.format(sn)

            vm_id = vm_helper.boot_vm(name,
                                      flavor=self.vms_info[sn]['flavor_id'],
                                      source='volume',
                                      avail_zone='nova')[1]
            LOG.info('OK, VM{} created: id={}\n'.format(sn, vm_id))
            self.vms_info[sn].update(vm_id=vm_id, vm_name=name)
            # ResourceCleanup.add('vm', vm_id, scope='class')

        LOG.info('OK, VMs created:\n{}\n'.format([vm['vm_id'] for vm in self.vms_info.values()]))

        for sn, vm_info in self.vms_info.items():
            host = nova_helper.get_vm_nova_show_value(vm_info['vm_id'], 'OS-EXT-SRV-ATTR:hypervisor_hostname')
            if host != self.current_host:
                vm_helper.live_migrate_vm(vm_info['vm_id'], destination_host=self.current_host)

            vm_helper.set_vm_meta_data(vm_info['vm_id'],
                                       **{VM_META_DATA: self.prioritizing[sn]})
            self.vms_info[sn].update(priority=self.prioritizing[sn])

    def create_flavors(self):
        flavor_name_format = 'pve_flavor_{}'
        for sn in range(self.num_vms):
            name = flavor_name_format.format(sn)
            flavor_id = nova_helper.create_flavor(name=name, vcpus=self.vcpus[sn], ram=int(self.mem[sn]) * 1024,
                                                  root_disk=self.root_disk[sn], swap=int(self.swap_disk[sn]) * 1024,
                                                  is_public=True)[1]
            self.vms_info[sn] = {'flavor_name': name, 'flavor_id': flavor_id}

        LOG.info('TODO: flavors created:\{}'.format([vm['flavor_id'] for vm in self.vms_info.values()]))

    def init_vm_settings(self, operation, prioritizing, vcpus, mem, root_disk, swap_disk):
        self.operation = operation

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
        self.num_vms = NUM_VM

        if self.operation == 'reboot':
            if len(host_helper.get_up_hypervisors()) < 2:
                pass
                # todo
                # skip(SkipReason.LESS_THAN_TWO_HYPERVISORS)
