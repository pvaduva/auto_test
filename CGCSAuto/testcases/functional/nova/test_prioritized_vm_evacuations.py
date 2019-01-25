import random
import string
from collections import defaultdict
from datetime import datetime

from pytest import mark, fixture, skip

from consts.cgcs import VMMetaData
from keywords import vm_helper, nova_helper, common
from testfixtures.fixture_resources import ResourceCleanup
from utils.tis_log import LOG

NUM_VM = 5
DEF_PRIORITY = 3
DEF_MEM_SIZE = 1024
DEF_DISK_SIZE = 1
DEF_NUM_VCPU = 1

MIN_PRI = 1
MAX_PRI = 10
VALID_OPERATIONS = ('reboot', 'force_reboot')
TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S.%f'


def get_vm_priority_metadata(vm_id, fail_ok=False):
    return vm_helper.get_vm_meta_data(vm_id, meta_data_names=[VMMetaData.EVACUATION_PRIORITY], fail_ok=fail_ok)


def set_evacuate_priority(vm_id, priority, fail_ok=False):
    data = {VMMetaData.EVACUATION_PRIORITY: priority}
    return vm_helper.set_vm_meta_data(vm_id, data, fail_ok=fail_ok, check_after_set=True)


def delete_evacuate_priority(vm_id, fail_ok=False):
    return vm_helper.delete_vm_meta_data(vm_id, [VMMetaData.EVACUATION_PRIORITY], fail_ok=fail_ok)


def verify_vim_evacuation_events(start_time, expected_orders):

    assert expected_orders, 'Expected orders undefined'

    event_id = 'instance-evacuate-begin'
    expt_orders = expected_orders[:]

    prev_timestamp = start_time
    i = 1
    for vm_info in expt_orders:
        vm_id, priority = vm_info
        LOG.info("Checking vm {} is evacuated in order{}...".format(vm_id, i))
        evac_events = vm_helper.get_vim_events(vm_id=vm_id, event_ids=event_id)
        actual_timestamp = evac_events[-1]['timestamp']
        actual_timestamp = datetime.strptime(actual_timestamp, TIMESTAMP_FORMAT)
        assert actual_timestamp > prev_timestamp, 'No evacuation record found for {} after {}'.\
            format(vm_id, prev_timestamp)

        # Set evacuation time for previous vm
        prev_timestamp = actual_timestamp
        i += 1

    LOG.info("VMs are evacuated in expected order.")


class TestPrioritizedVMEvacuation:

    @fixture(scope='class', autouse=True)
    def setup_quota_and_hosts(self, request, add_admin_role_class, add_cgcsauto_zone):
        vm_helper.ensure_vms_quotas(vms_num=10, cores_num=50, vols_num=20)

        storage_backing, target_hosts = nova_helper.get_storage_backing_with_max_hosts()
        if len(target_hosts) < 2:
            skip("Less than two up hosts have same storage backing")

        hosts_to_add = target_hosts[:2]
        nova_helper.add_hosts_to_aggregate(aggregate='cgcsauto', hosts=hosts_to_add)

        def remove_hosts_from_zone():
            nova_helper.remove_hosts_from_aggregate(aggregate='cgcsauto', check_first=False)
        request.addfinalizer(remove_hosts_from_zone)

        return storage_backing, hosts_to_add

    @mark.parametrize(('operation', 'set_on_boot', 'prioritizing', 'vcpus', 'mem', 'root_disk', 'swap_disk'), [
        ('reboot', False, 'diff_priority', 'same_vcpus', 'same_mem', 'same_root_disk', 'same_swap_disk'),
        ('reboot', False, 'same_priority', 'diff_vcpus', 'diff_mem', 'same_root_disk', 'no_swap_disk'),
        ('reboot', True, 'same_priority', 'same_vcpus', 'diff_mem', 'diff_root_disk', 'same_swap_disk'),
        ('reboot', True, 'same_priority', 'same_vcpus', 'same_mem', 'diff_root_disk', 'diff_swap_disk'),
        ('reboot', True, 'same_priority', 'same_vcpus', 'same_mem', 'same_root_disk', 'diff_swap_disk'),
        # ('reboot', True, 'diff_priority', 'same_vcpus', 'same_mem', 'same_root_disk', 'same_swap_disk'),
        ('reboot', True, 'diff_priority', 'diff_vcpus', 'same_mem', 'same_root_disk', 'no_swap_disk'),
        ('reboot', True, 'diff_priority', 'diff_vcpus', 'diff_mem', 'diff_root_disk', 'diff_swap_disk'),
        ('force_reboot', False, 'same_priority', 'same_vcpus', 'diff_mem', 'diff_root_disk', 'diff_swap_disk'),
        ('force_reboot', True, 'diff_priority', 'diff_vcpus', 'diff_mem', 'same_root_disk', 'same_swap_disk'),
    ])
    def test_prioritized_vm_evacuations(self, operation, set_on_boot, prioritizing, vcpus, mem, root_disk, swap_disk,
                                        setup_quota_and_hosts):
        """

        Args:
            operation:      operations to perform on the hosting compute node
            set_on_boot:    whether to boot VMs with meta data: sw:wrs:recovery_priority
            prioritizing:   whether all VMs have same Evacuation-Priority
            vcpus:          whether all VMs have same number of VCPU
            mem:            whether all VMs have same amount of memory
            root_disk:      whether all VMs have the same size of root disk
            swap_disk:      whether all VMs have the same size of swap disk
            setup_quota_and_hosts

        Returns:

        Steps:
            1   make sure the requirements are meet for the intended VM operation
            2   create flavor
            3   create VM
            4   reboot the hosting node
            5   checking the evacuation/migration order
        """
        self.storage_backing, self.cgcsauto_hosts = setup_quota_and_hosts
        self.current_host = self.cgcsauto_hosts[0]
        self.vms_info = defaultdict()
        self.init_vm_settings(operation, set_on_boot, prioritizing, vcpus, mem, root_disk, swap_disk)
        self.create_flavors()
        self.create_vms()
        self.check_vm_settings()
        self.trigger_evacuation()
        self.check_evacuation_orders()
        self.check_vm_settings()

    def check_vm_settings(self):
        LOG.tc_step('Check if the evacuation-priority actually set')
        for vm_info in self.vms_info.values():
            recovery_priority = get_vm_priority_metadata(vm_info['vm_id'], fail_ok=False)
            if not recovery_priority:
                assert vm_info['priority'] is None, \
                    'Evacuation-Priority on VM is not set, expected priority:{}, actual:{}, vm_id:{}'.format(
                        vm_info['priority'], recovery_priority, vm_info['vm_id'])
            else:
                assert int(recovery_priority[VMMetaData.EVACUATION_PRIORITY]) == vm_info['priority'], \
                    'Evacuation-Priority on VM is not set, expected priority:{}, actual:{}, vm_id:{}'.format(
                        vm_info['priority'], recovery_priority, vm_info['vm_id'])

        LOG.info('OK, evacuation-priorities are correctly set')

    def check_evacuation_orders(self):
        LOG.tc_step('Checking the order of VM evacuation')
        for vm_info in self.vms_info.values():
            if 'priority' not in vm_info:
                vm_info['priority'] = MAX_PRI

        vm_infos = [(sn, vm_info) for sn, vm_info in self.vms_info.items()]
        sorted_vm_infos = sorted(vm_infos, key=lambda x: x[0])
        sorted_vm_infos = [v[1] for v in sorted_vm_infos]
        vm_attributes = zip(sorted_vm_infos, self.vcpus, self.mem, self.root_disk, self.swap_disk)
        sorted_attributes = sorted(vm_attributes,
                                   key=lambda x: (x[0]['priority'], -1 * x[1], -1 * x[2], -1 * x[3], -1 * x[4]))

        expected_orders = [(v[0]['vm_id'], v[0]['priority']) for v in sorted_attributes]
        verify_vim_evacuation_events(start_time=self.start_time, expected_orders=expected_orders)

    def trigger_evacuation(self):
        LOG.tc_step('Triggering evacuation on host: {} via action:{}'.format(self.current_host, self.operation))
        action = self.operation.lower()

        self.start_time = common.lab_time_now()[1]
        vms = [vm_dict['vm_id'] for vm_dict in self.vms_info.values()]

        if action in VALID_OPERATIONS:
            force_reboot = (action != 'reboot')
            vm_helper.evacuate_vms(host=self.current_host, force=force_reboot, vms_to_check=vms)
        else:
            skip('Not supported action:{}'.format(action))
        LOG.info('OK, triggered evacuation by {} host:{}'.format(self.operation, self.current_host))

    @mark.parametrize(('operation', 'priority', 'expt_error'), [
        ('set', -2, 'error'),
        ('set', 10, None),
        ('set', 11, 'error'),
        ('set', '', 'error'),
        ('set', 'random', 'error'),
        ('delete', '', 'error'),
    ])
    def test_setting_evacuate_priority(self, operation, priority, expt_error):
        LOG.tc_step('Launch VM for test')

        if not hasattr(TestPrioritizedVMEvacuation, 'vm_id'):
            TestPrioritizedVMEvacuation.vm_id = vm_helper.boot_vm(avail_zone='cgcsauto', cleanup='class')[1]

        vm_id = TestPrioritizedVMEvacuation.vm_id
        LOG.info('OK, VM launched (or already existing) for test, vm-id:{}'.format(vm_id))

        if priority == 'random':
            priority = 'ab' + ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(3))
        expecting_fail = True if expt_error else False

        if operation == 'set':
            code, output = set_evacuate_priority(vm_id, priority, fail_ok=expecting_fail)
        else:
            priorities_set = get_vm_priority_metadata(vm_id, fail_ok=True)
            expecting_fail = True if not priorities_set else False
            LOG.info('Attempt to delete evacuation-priority, expecting {}'.format('PASS' if expecting_fail else 'FAIL'))
            code, output = delete_evacuate_priority(vm_id, fail_ok=expecting_fail)

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

        priorities_set = get_vm_priority_metadata(vm_id, fail_ok=True)

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

    def create_vms(self):
        LOG.tc_step('Create VMs')

        vm_name_format = 'pve_vm_{}'

        num_priorities = len(self.prioritizing)

        for sn in range(NUM_VM):

            name = vm_name_format.format(sn)
            if self.set_on_boot and sn < num_priorities:
                vm_id = vm_helper.boot_vm(name,
                                          meta={VMMetaData.EVACUATION_PRIORITY: self.prioritizing[sn]},
                                          flavor=self.vms_info[sn]['flavor_id'],
                                          source='volume',
                                          avail_zone='cgcsauto',
                                          vm_host=self.current_host,
                                          cleanup='function')[1]
            else:
                vm_id = vm_helper.boot_vm(name,
                                          flavor=self.vms_info[sn]['flavor_id'],
                                          source='volume',
                                          avail_zone='cgcsauto',
                                          vm_host=self.current_host,
                                          cleanup='function')[1]
                if sn < num_priorities:
                    vm_helper.set_vm_meta_data(vm_id, {VMMetaData.EVACUATION_PRIORITY: self.prioritizing[sn]})

            LOG.info('OK, VM{} created: id={}\n'.format(sn, vm_id))
            self.vms_info[sn].update(vm_id=vm_id, vm_name=name, priority=self.prioritizing[sn])

        LOG.info('OK, VMs created:\n{}\n'.format([vm['vm_id'] for vm in self.vms_info.values()]))

    def create_flavors(self):
        LOG.tc_step('Create flavors')

        flavor_name_format = 'pve_flavor_{}'
        for sn in range(NUM_VM):
            name = flavor_name_format.format(sn)
            options = {
                'name': name,
                'vcpus': self.vcpus[sn],
                'ram': self.mem[sn],
                'root_disk': self.root_disk[sn],
                'is_public': True,
                'storage_backing': self.storage_backing,
            }
            if self.swap_disk:
                options['swap'] = self.swap_disk[sn]

            flavor_id = nova_helper.create_flavor(**options)[1]
            ResourceCleanup.add('flavor', flavor_id, scope='function')
            self.vms_info.update({sn: {'flavor_name': name, 'flavor_id': flavor_id}})

            # TODO create volume
        LOG.info('OK, flavors created:\n{}\n'.format([vm['flavor_id'] for vm in self.vms_info.values()]))

    def init_vm_settings(self, operation, set_on_boot, prioritizing, vcpus, mem, root_disk, swap_disk):
        self.operation = operation
        self.set_on_boot = set_on_boot

        if operation not in VALID_OPERATIONS:
            skip('Unspported operation:{}'.format(operation))
            return

        if 'diff' in prioritizing:
            self.prioritizing = random.sample(range(1, NUM_VM + 1), NUM_VM)
        else:
            self.prioritizing = [DEF_PRIORITY] * NUM_VM

        if 'diff' in vcpus:
            self.vcpus = random.sample(range(NUM_VM * DEF_NUM_VCPU + 1, DEF_NUM_VCPU, -1 * DEF_NUM_VCPU), NUM_VM)
        else:
            self.vcpus = [DEF_NUM_VCPU] * NUM_VM

        if 'diff' in mem:
            self.mem = list(range(DEF_MEM_SIZE + 512 * NUM_VM, DEF_MEM_SIZE, -512))
            random.shuffle(self.mem, random.random)
        else:
            self.mem = [DEF_MEM_SIZE] * NUM_VM

        if 'diff' in root_disk:
            self.root_disk = random.sample(
                range(DEF_DISK_SIZE * (NUM_VM + 1),
                      DEF_DISK_SIZE,
                      -1 * DEF_DISK_SIZE), NUM_VM)
        else:
            self.root_disk = [DEF_DISK_SIZE] * NUM_VM

        if 'diff' in swap_disk:
            self.swap_disk = [size * 1024 for size in list(
                range(DEF_DISK_SIZE * NUM_VM + 1,
                      DEF_DISK_SIZE,
                      -1 * DEF_DISK_SIZE))]
            random.shuffle(self.swap_disk, random.random)
        elif 'same' in swap_disk:
            self.swap_disk = [DEF_DISK_SIZE * 1024] * NUM_VM
        else:
            # no swap disk
            self.swap_disk = [0] * NUM_VM

        LOG.info('OK, will boot VMs with settings:\npriorities={}\nvcpus={}\nmem={}\nroot_disk={}\nswap_dis={}'.
                 format(self.prioritizing, self.vcpus, self.mem, self.root_disk, self.swap_disk))
