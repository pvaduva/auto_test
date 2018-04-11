import random

from pytest import fixture, mark, skip
import time
from utils.tis_log import LOG
from utils.kpi import kpi_log_parser
from consts.kpi_vars import HostLock, KPI_DATE_FORMAT
from consts.reasons import SkipStorageBacking
from consts.cgcs import VMStatus, SysType
from testfixtures.recover_hosts import HostsToRecover
from keywords import vm_helper, nova_helper, host_helper, system_helper, common


@fixture(scope='module', autouse=True)
def update_instances_quota():
    if not nova_helper.get_quotas(quotas='instances')[0] > 8:
        nova_helper.update_quotas(instances=10, cores=20)


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
    flavor_no_localdisk = nova_helper.create_flavor(ephemeral=0, swap=0, check_storage_backing=False)[1]
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
            ephemeral_swap = random.choice([[0, 512], [1, 512], [1, 0]])
            flavor_with_localdisk = nova_helper.create_flavor(ephemeral=ephemeral_swap[0], swap=ephemeral_swap[1],
                                                              check_storage_backing=False)[1]
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
    def target_hosts(self):
        """
        Test fixture for test_lock_with_vms().
        Calculate target host(s) to perform lock based on storage backing of vms_to_test, and live migrate suitable vms
        to target host before test start.
        """

        storage_backing, target_hosts = nova_helper.get_storage_backing_with_max_hosts()
        if len(target_hosts) < 2:
            skip(SkipStorageBacking.LESS_THAN_TWO_HOSTS_WITH_BACKING.format(storage_backing))

        target_host = target_hosts[0]
        if SysType.AIO_DX == system_helper.get_sys_type():
            target_host = system_helper.get_standby_controller_name()

        return storage_backing, target_host

    @mark.nightly
    @mark.kpi
    def test_lock_with_vms(self, target_hosts, no_simplex, add_admin_role_func, collect_kpi):
        """
        Test lock host with vms on it.

        Args:
            target_hosts (list): targeted host(s) to lock that was prepared by the target_hosts test fixture.

        Skip Conditions:
            - Less than 2 hypervisor hosts on the system

        Prerequisites:
            - Hosts storage backing are pre-configured to storage backing under test
                ie., 2 or more hosts should support the storage backing under test.
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
        storage_backing, host = target_hosts
        vms_num = 5
        vm_helper.ensure_vms_quotas(vms_num=vms_num)

        LOG.tc_step("Boot {} vms with various storage settings".format(vms_num))
        vms = vm_helper.boot_vms_various_types(cleanup='function', vms_num=vms_num, storage_backing=storage_backing,
                                               target_host=host)

        LOG.tc_step("Attempt to lock target host {}...".format(host))
        HostsToRecover.add(host)

        init_time = None
        if collect_kpi:
            init_time = common.get_date_in_format(date_format=KPI_DATE_FORMAT)

        host_helper.lock_host(host=host, check_first=False, fail_ok=False, swact=True)

        LOG.tc_step("Verify lock succeeded and vms still in good state")
        vm_helper.wait_for_vms_values(vms=vms, fail_ok=False)
        for vm in vms:
            vm_host = nova_helper.get_vm_host(vm_id=vm)
            assert vm_host != host, "VM is still on {} after lock".format(host)

            vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm)

        if collect_kpi:
            LOG.info("Collect kpi for lock host with vms")
            kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=HostLock.WITH_VM.format(storage_backing),
                                      host=None, log_path=HostLock.LOG_PATH, end_pattern=HostLock.END.format(host),
                                      start_pattern=HostLock.START.format(host), start_path=HostLock.START_PATH,
                                      init_time=init_time, uptime=5)

    @mark.sx_nightly
    def test_lock_with_max_vms_simplex(self, simplex_only):
        vms_num = host_helper.get_max_vms_supported(host='controller-0')
        vm_helper.ensure_vms_quotas(vms_num=vms_num)

        LOG.tc_step("Boot {} vms with various storage settings".format(vms_num))
        vms = vm_helper.boot_vms_various_types(cleanup='function', vms_num=vms_num)

        LOG.tc_step("Lock vm host on simplex system")
        HostsToRecover.add('controller-0')
        host_helper.lock_host('controller-0')

        LOG.tc_step("Ensure vms are in {} state after locked host come online".format(VMStatus.STOPPED))
        vm_helper.wait_for_vms_values(vms, values=VMStatus.STOPPED, fail_ok=False)
        # TODO: TEMP delay for Chris F  must be reverted after
        time.sleep(120)

        LOG.tc_step("Unlock host on simplex system")
        host_helper.unlock_host(host='controller-0')

        LOG.tc_step("Ensure vms are Active and Pingable from NatBox")
        vm_helper.wait_for_vms_values(vms, values=VMStatus.ACTIVE, fail_ok=False, timeout=600)
        for vm in vms:
            vm_helper.wait_for_vm_pingable_from_natbox(vm)


@mark.p2
class TestLockWithVMsNegative:
    @fixture()
    def target_hosts_negative(self, request):
        self.hosts_locked = []

        storages_to_test = []
        for storage_backing in ['local_image', 'local_lvm', 'remote']:
            hosts = host_helper.get_hosts_in_storage_aggregate(storage_backing=storage_backing)
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
                vm_helper.delete_vms(vm_to_del)
            nova_helper.delete_flavors(all_new_flavors)
            for host_to_unlock in self.hosts_locked:
                host_helper.unlock_host(host_to_unlock, check_hypervisor_up=True)
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
            if system_helper.get_active_controller_name() == host:
                host_helper.swact_host(hostname=host)
                host_helper.wait_for_hypervisors_up(host)
                host_helper.wait_for_webservice_up(host)

            vms_on_host = nova_helper.get_vms_on_hypervisor(hostname=host)
            pre_vms_status = nova_helper.get_vms_info(vm_ids=vms_on_host, field='Status')

            LOG.tc_step("Lock target host {}...".format(host))
            lock_code, lock_output = host_helper.lock_host(host=host, check_first=False, fail_ok=True, swact=True)

            # Add locked host to cleanup list
            if lock_code in [0, 3]:
                self.hosts_locked.append(host)

            post_vms_status = nova_helper.get_vms_info(vm_ids=vms_on_host, field='Status')

            LOG.tc_step("Verify lock rejected and vms status unchanged.")
            assert lock_code in [1, 2, 4, 5], "Unexpected result: {}".format(lock_output)
            assert pre_vms_status == post_vms_status, "VM(s) status has changed after host-lock {}".format(host)
