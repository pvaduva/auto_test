import random

from pytest import fixture, mark, skip

from utils.tis_log import LOG
from consts.auth import Tenant
from setup_consts import P1, P2, P3
from keywords import vm_helper, nova_helper, system_helper, host_helper, cinder_helper


@fixture(scope='module', autouse=True)
def update_instances_quota():
    if not nova_helper.get_quotas(quotas='instances')[0] > 8:
        nova_helper.update_quotas(instances=10, cores=20)

storage = [
    # storage backing, [ephemeral, swap]
    ('local_image', [0, 0]),
    ('local_image', random.choice([(1, 0), (0, 1), (1, 1)])),
    ('local_lvm', [0, 0]),
    ('local_lvm', random.choice([(1, 0), (0, 1), (1, 1)])),
    ('remote', [0, 0]),
    ('remote', random.choice([(1, 0), (0, 1), (1, 1)])),
]
@fixture(scope='module', params=storage)
def flavor_(request):
    """
    Text fixture to create flavor with specific 'ephemeral', 'swap', and 'storage_backing'
    Args:
        request: pytest arg

    Returns (tuple): (storage (str), flavor_id (str))
    """
    storage = request.param[0]
    ephemeral, swap = request.param[1]
    if len(host_helper.get_hosts_by_storage_aggregate(storage_backing=storage)) < 1:
        skip("No host support {} storage backing".format(storage))

    storage_spec = {'aggregate_instance_extra_specs:storage': storage}

    flavor_id = nova_helper.create_flavor(ephemeral=ephemeral, swap=swap)[1]
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **storage_spec)

    def delete_flavor():
        nova_helper.delete_flavors(flavor_ids=flavor_id, fail_ok=True)
    request.addfinalizer(delete_flavor)

    return storage, flavor_id


@fixture(scope='module', params=['volume', 'image', 'image_with_vol'])
def vm_(request, flavor_):
    """
    Test fixture to create vm from volume, image or image_with_vol with given flavor.

    Args:
        request: pytest arg
        flavor_: flavor_ fixture which passes the created flavor based on ephemeral', 'swap', and 'storage_backing'

    Returns: (storage_backing, vm_id)
    """
    vm_type = request.param
    storage_type, flavor_id = flavor_
    source = 'image' if 'image' in vm_type else 'volume'

    # instance_quota = nova_helper.get_quotas('instances')
    # existing_vms = nova_helper.get_vms()
    # new_vms_allowed = instance_quota - len(existing_vms)
    # if new_vms_allowed < 1:
    #    vm_helper.delete_vm(existing_vms[0])

    vm_id = vm_helper.boot_vm(flavor=flavor_id, source=source)[1]
    if vm_type == 'image_with_vol':
        vm_helper.attach_vol_to_vm(vm_id=vm_id)

    def delete_vms():
        vm_helper.delete_vm(vm_id=vm_id, delete_volumes=True)
    request.addfinalizer(delete_vms)

    return storage_type, vm_id


class TestEvacuateVM:
    @fixture()
    def unlock_if_locked(self, request):
        self.lock_rtn_code = None
        self.target_host = None

        def unlock():
            if self.lock_rtn_code in [0, 3]:
                host_helper.unlock_host(self.target_host)
        request.addfinalizer(unlock)

    @mark.skipif(len(nova_helper.get_hypervisor_hosts()) < 2, reason="Less than 2 hypervisor hosts on the system")
    @mark.usefixtures('unlock_if_locked')
    def temp_test_lock_with_vms_no_host_to_mig(self, vm_):
        """
        Lock host with one vm under test.
        Various configs for vm: vm boot source, has volume attached, has local disk, storage backing

        Args:
            vm_ (dict): vm created by vm_ fixture

        Prerequisite: computes are pre-configured for specific test scenario. e..g, configure storage backing
        Test Setups:
        - create flavor with specific 'ephemeral', 'swap', and 'storage_backing'
        - boot vm from specific boot source with specific flavor
        - (attach volume to vm in one specific scenario)

        Test Steps:
        - Lock host with vm created by vm_ fixture
        - Check lock result and ensure vm still in active state

        Skip conditions:
         - Less than two hypervisor hosts on system

        """
        storage, vm_id = vm_

        LOG.tc_step("Calculating expected result...")
        candidate_hosts = host_helper.get_up_hosts_with_storage_backing(storage)
        exp_codes = [0] if len(candidate_hosts) > 1 else [1, 4]

        target_host = nova_helper.get_vm_host(vm_id=vm_id)

        code, msg = host_helper.lock_host(host=target_host, fail_ok=True, check_bf_lock=False)
        self.lock_rtn_code = code
        self.target_host = target_host

        assert code in exp_codes, msg

########################################################################################################################


def _boot_migrable_vms(storage_backing):
    """
    Create vms with specific storage backing that can be live migrated

    Args:
        storage_backing: 'local_image', 'local_lvm' or 'remote'

    Returns: (vms_info (list), flavors_created (list))
        vms_info : [(vm_id1, block_mig1), (vm_id2, block_mig2), ...]

    """
    storage_spec = {'aggregate_instance_extra_specs:storage': storage_backing}
    vms_to_test = []
    flavors_created = []
    flavor_no_localdisk = nova_helper.create_flavor(ephemeral=0, swap=0)[1]
    flavors_created.append(flavor_no_localdisk)
    nova_helper.set_flavor_extra_specs(flavor=flavor_no_localdisk, **storage_spec)
    vm_1 = vm_helper.boot_vm(flavor=flavor_no_localdisk, source='volume')[1]
    block_mig_1 = False
    vms_to_test.append((vm_1, block_mig_1))
    if storage_backing != 'local_lvm':
        LOG.info("Boot a VM from image if host storage backing is local_image or remote...")
        vm_2 = vm_helper.boot_vm(flavor=flavor_no_localdisk, source='image')[1]
        block_mig_2 = True
        vms_to_test.append((vm_2, block_mig_2))
        if storage_backing == 'remote':
            LOG.info("Boot a VM from volume with local disks if storage backing is remote...")
            ephemeral_swap = random.choice([[0, 1], [1, 1], [1, 0]])
            flavor_with_localdisk = nova_helper.create_flavor(ephemeral=ephemeral_swap[0],
                                                              swap=ephemeral_swap[1])[1]
            flavors_created.append(flavor_with_localdisk)
            nova_helper.set_flavor_extra_specs(flavor=flavor_with_localdisk, **storage_spec)
            vm_3 = vm_helper.boot_vm(flavor=flavor_with_localdisk, source='volume')[1]
            block_mig_3 = False
            vms_to_test.append((vm_3, block_mig_3))
            LOG.info("Boot a VM from image with volume attached if storage backing is remote...")
            vm_4 = vm_helper.boot_vm(flavor=flavor_no_localdisk, source='image')[1]
            vm_helper.attach_vol_to_vm(vm_id=vm_4)
            block_mig_4 = False
            vms_to_test.append((vm_4, block_mig_4))

    return vms_to_test, flavors_created


class TestLockWithVMs:
    @fixture()
    def target_hosts(self, request):
        """
        Calculate target host(s) to perform lock based on storage backing of vms_to_test, and live migrate suitable vms
        to target host before test start.

        Args:
            request: pytest arg

        Returns: (target_hosts, storages_to_test)

        Teardown:
            - Delete created vms and volumes
            - Delete create flavors
            - Unlock host(s) if locked during test.

        """
        self.hosts_locked = []

        storages_to_test = []
        for storage in ['local_image', 'local_lvm', 'remote']:
            hosts_per_storage = host_helper.get_hosts_by_storage_aggregate(storage)
            if len(hosts_per_storage) > 1:
                storages_to_test.append(storage)

        if not storages_to_test:
            skip("No two hypervisors support same storage backing.")

        all_vms = []
        target_hosts = []
        all_new_flavors = []
        for storage_backing in storages_to_test:
            vms_to_test, flavors_created = _boot_migrable_vms(storage_backing)
            all_new_flavors += flavors_created
            all_vms += [vm[0] for vm in vms_to_test]

            LOG.info("Find targeted {} host with most vms and live migrate rest of the vms to target host".
                     format(storage_backing))
            vm_hosts = []
            for vm in vms_to_test:
                vm_host = nova_helper.get_vm_host(vm_id=vm[0])
                if vm_host in vm_hosts:
                    target_host = vm_host
                    break
                vm_hosts.append(vm_host)
            else:
                target_host = random.choice(vm_hosts)

            vms_on_target = nova_helper.get_vms_on_hypervisor(target_host)
            for vm in vms_to_test:
                if vm[0] not in vms_on_target:
                    vm_helper.live_migrate_vm(vm_id=vm[0], destination_host=target_host, block_migrate=vm[1])

            target_hosts.append(target_host)

        def teardown():
            LOG.info("Delete all created vms and unlock target host(s)...")
            for vm_to_del in all_vms:
                vm_helper.delete_vm(vm_id=vm_to_del)
            nova_helper.delete_flavors(all_new_flavors)
            for host_to_unlock in self.hosts_locked:
                host_helper.unlock_host(host_to_unlock)
        request.addfinalizer(teardown)

        return target_hosts, storages_to_test

    @mark.skipif(len(nova_helper.get_hypervisor_hosts()) < 2, reason="Less than 2 hypervisor hosts on the system")
    # @mark.usefixtures('delete_all_vms')
    def test_lock_with_vms(self, target_hosts):
        """
        Test lock host with vms on it.

        Args:
            target_hosts:

        Prerequisites: hosts storage backing are pre-configured to storage backing under test
        Test Setups:
            - Set instances quota to 10 if it was less than 8
            - Determine storage backing(s) under test. i.e.,storage backings supported by at least 2 hosts on the system
            - Create flavors with storage extra specs set based on storage backings under test
            - Create vms_to_test that can be live migrated using created flavors
            - Determine target host(s) to perform lock based on which host(s) have the most vms_to_test
            - Live migrate vms to target host(s)
        Test Steps:
            - Lock target host
            - Verify lock succeeded and vms status unchanged
            - Repeat above steps if more than one target host
        Test Teardown:
            - Delete created vms and volumes
            - Delete created flavors
            - Unlock locked target host(s)

        """
        target_hosts_, storages_to_test = target_hosts
        LOG.info("Negative test: host-lock attempt on host(s) with {} storage backing(s). \n"
                 "Host(s) to attempt lock: {}".format(storages_to_test, target_hosts_))
        for host in target_hosts_:
            vms_on_host = nova_helper.get_vms_on_hypervisor(hostname=host)
            pre_vms_status = nova_helper.get_vms_info(vm_ids=vms_on_host, header='Status')

            LOG.tc_step("Lock target host {}...".format(host))
            lock_code, lock_output = host_helper.lock_host(host=host, check_bf_lock=False, fail_ok=True)

            # Add locked host to cleanup list
            if lock_code in [0, 3]:
                self.hosts_locked.append(host)

            post_vms_status = nova_helper.get_vms_info(vm_ids=vms_on_host, header='Status')

            LOG.tc_step("Verify lock succeeded and vms status unchanged.")
            assert lock_code == 0, "Failed to lock {}. Details: {}".format(host, lock_output)
            assert pre_vms_status == post_vms_status, "VM(s) status has changed after host-lock {}".format(host)


class TestLockWithVMsNegative:
    @fixture()
    def target_hosts_negative(self, request):
        self.hosts_locked = []

        storages_to_test = []
        for storage_backing in ['local_image', 'local_lvm', 'remote']:
            hosts = host_helper.get_up_hosts_with_storage_backing(storage_backing=storage_backing)
            if len(hosts) == 1:
                storages_to_test.append(storage_backing)

        if not storages_to_test:
            skip("Test requires specific storage backing supported by only one host for negative test.")

        all_vms = []
        target_hosts = []
        all_new_flavors = []
        for storage_backing in storages_to_test:
            vms_to_test, flavors_created = _boot_migrable_vms(storage_backing)
            all_new_flavors += flavors_created
            for vm in vms_to_test:
                target_hosts.append(nova_helper.get_vm_host(vm[0]))
                all_vms.append(vm[0])

        def teardown():
            LOG.info("Delete all created vms and unlock target host(s)...")
            for vm_to_del in all_vms:
                vm_helper.delete_vm(vm_id=vm_to_del)
            nova_helper.delete_flavors(all_new_flavors)
            for host_to_unlock in self.hosts_locked:
                host_helper.unlock_host(host_to_unlock)
        request.addfinalizer(teardown)

        return target_hosts, storages_to_test

    def test_lock_with_vms_mig_fail(self, target_hosts_negative):
        """
        Test lock host with vms on it - Negative test. i.e., lock should be rejected

        Args:
            target_hosts_negative: target host(s) to perform lock

        Prerequisites: hosts storage backing are pre-configured to storage backing under test.
            ie., only 1 host should support the storage backing under test.
        Test Setups:
            - Set instances quota to 10 if it was less than 8
            - Determine storage backing(s) under test, i.e., storage backings supported by only 1 host on the system
            - Create flavors with storage extra specs set based on storage backings under test
            - Create vms_to_test that can be live migrated using created flavors
            - Determine target host(s) to perform lock based on which host(s) have the most vms_to_test
        Test Steps:
            - Lock target host
            - Verify lock rejected and vms status unchanged
            - Repeat above steps if more than one target host
        Test Teardown:
            - Delete created vms and volumes
            - Delete created flavors
            - Unlock locked target host(s)

        """
        target_hosts, storages_to_test = target_hosts_negative
        LOG.info("Negative test: host-lock attempt on host(s) with {} storage backing(s). \n"
                 "Host(s) to attempt lock: {}".format(storages_to_test, target_hosts_negative))
        for host in target_hosts:
            vms_on_host = nova_helper.get_vms_on_hypervisor(hostname=host)
            pre_vms_status = nova_helper.get_vms_info(vm_ids=vms_on_host, header='Status')

            LOG.tc_step("Lock target host {}...".format(host))
            lock_code, lock_output = host_helper.lock_host(host=host, check_bf_lock=False, fail_ok=True)

            # Add locked host to cleanup list
            if lock_code in [0, 3]:
                self.hosts_locked.append(host)

            post_vms_status = nova_helper.get_vms_info(vm_ids=vms_on_host, header='Status')

            LOG.tc_step("Verify lock rejected and vms status unchanged.")
            assert lock_code in [1, 4, 5], "Unexpected result: {}".format(lock_output)
            assert pre_vms_status == post_vms_status, "VM(s) status has changed after host-lock {}".format(host)
