from pytest import fixture, skip, mark

from utils.tis_log import LOG
from consts.cgcs import VMStatus
from consts.reasons import SkipReason

from keywords import vm_helper, host_helper, nova_helper, cinder_helper, keystone_helper
from testfixtures.resource_mgmt import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


@fixture(scope='module', autouse=True)
def skip_test_if_less_than_two_hosts():
    if len(host_helper.get_nova_hosts()) < 2:
        skip(SkipReason.LESS_THAN_TWO_HYPERVISORS)

    LOG.fixture_step("Update instance and volume quota to at least 10 and 20 respectively")
    if nova_helper.get_quotas(quotas='instances')[0] < 10:
        nova_helper.update_quotas(instances=10, cores=20)
    if cinder_helper.get_quotas(quotas='volumes')[0] < 20:
        cinder_helper.update_quotas(volumes=20)


class TestCgcsGuest:
    # TODO: replace this with the TestDefaultGuest

    @fixture(scope='class')
    def vms_(self):

        LOG.fixture_step("Create a flavor without ephemeral or swap disks")
        flavor_1 = nova_helper.create_flavor('flv_nolocaldisk')[1]
        ResourceCleanup.add('flavor', flavor_1, scope='module')

        LOG.fixture_step("Create a flavor with ephemeral and swap disks")
        flavor_2 = nova_helper.create_flavor('flv_localdisk', ephemeral=1, swap=1)[1]
        ResourceCleanup.add('flavor', flavor_2, scope='module')

        LOG.fixture_step("Boot vm1 from volume with flavor flv_nolocaldisk and wait for it pingable from NatBox")
        vm1_name = "vol_nolocal"
        vm1 = vm_helper.boot_vm(vm1_name, flavor=flavor_1, source='volume')[1]
        ResourceCleanup.add('vm', vm1, scope='module')
        vm_helper.wait_for_vm_pingable_from_natbox(vm1)

        LOG.fixture_step("Boot vm2 from volume with flavor flv_localdisk and wait for it pingable from NatBox")
        vm2_name = "vol_local"
        vm2 = vm_helper.boot_vm(vm2_name, flavor=flavor_2, source='volume')[1]
        ResourceCleanup.add('vm', vm2, scope='module')
        vm_helper.wait_for_vm_pingable_from_natbox(vm2)

        LOG.fixture_step("Boot vm3 from image with flavor flv_nolocaldisk and wait for it pingable from NatBox")
        vm3_name = "image_novol"
        vm3 = vm_helper.boot_vm(vm3_name, flavor=flavor_1, source='image')[1]
        ResourceCleanup.add('vm', vm3, scope='module', del_vm_vols=False)
        vm_helper.wait_for_vm_pingable_from_natbox(vm3)

        LOG.fixture_step("Boot vm4 from image with flavor flv_nolocaldisk and wait for it pingable from NatBox")
        vm4_name = 'image_vol'
        vm4 = vm_helper.boot_vm(vm4_name, flavor_1, source='image')[1]
        ResourceCleanup.add('vm', vm4, scope='module', del_vm_vols=True)
        vm_helper.wait_for_vm_pingable_from_natbox(vm4)

        return [vm1, vm2, vm3, vm4]

    @mark.trylast
    @mark.sanity
    def test_evacuate_vms(self, vms_):
        vm1, vm2, vm3, vm4 = vms_

        # vm2 cannot be live migrated so choose its host as target host
        target_host = nova_helper.get_vm_host(vm2)
        vms_to_mig = [vm1, vm3, vm4]

        LOG.tc_step("Live migrate vm1, vm3, vm4 to vm2 host {} if not already on it".format(target_host))

        for vm in vms_to_mig:
            if nova_helper.get_vm_host(vm) != target_host:
                vm_helper.live_migrate_vm(vm, destination_host=target_host)

        LOG.tc_step("Attach volume to vm4 which was booted from image: {}.".format(vm4))
        vm_helper.attach_vol_to_vm(vm4)

        LOG.tc_step("Reboot target host {}".format(target_host))
        host_helper.reboot_hosts(target_host, wait_for_reboot_finish=False)
        HostsToRecover.add(target_host)

        LOG.tc_step("Wait for vms to reach ERROR or REBUILD state with best effort")
        vm_helper._wait_for_vms_values(vms_, values=[VMStatus.ERROR, VMStatus.REBUILD], fail_ok=True, timeout=120)

        LOG.tc_step("Check vms are in Active state and moved to other host(s) after host reboot")
        res, active_vms, inactive_vms = vm_helper._wait_for_vms_values(vms=vms_, values=VMStatus.ACTIVE, timeout=600)

        vms_host_err = []
        for vm in vms_:
            if nova_helper.get_vm_host(vm) == target_host:
                vms_host_err.append(vm)

        assert not vms_host_err, "Following VMs stayed on the same host {}: {}\nVMs did not reach Active state: {}".\
                                 format(target_host, vms_host_err, inactive_vms)

        assert not inactive_vms, "VMs did not reach Active state after evacuated to other host: {}".format(inactive_vms)

        LOG.tc_step("Check VMs are pingable from NatBox after evacuation")
        vm_helper.ping_vms_from_natbox(vms_)


class TestVariousGuests:

    @fixture(scope='class', params=['image', 'volume'])
    def boot_source(self, request):
        return request.param

    @mark.trylast
    @mark.features('guest_os')
    @mark.usefixtures('ubuntu14_image',
                      'centos6_image', 'centos7_image',
                      'opensuse11_image', 'opensuse12_image',
                      # 'opensuse13_image',
                      'rhel6_image', 'rhel7_image')
    @mark.parametrize('guest_os', [
        'ubuntu_14',
        'centos_6', 'centos_7',
        'opensuse_11', 'opensuse_12',
        # 'opensuse_13',
        'rhel_6', 'rhel_7',
    ])
    def test_evacuate_vm(self, guest_os, boot_source):
        if guest_os == 'opensuse_12':
            if not cinder_helper.is_volumes_pool_sufficient(min_size=30):
                skip(SkipReason.SMALL_CINDER_VOLUMES_POOL)

        LOG.tc_step("Boot a {} VM from {}".format(guest_os, boot_source))
        vm_id = vm_helper.boot_vm(name="{}_{}".format(guest_os, boot_source), source=boot_source, guest_os=guest_os)[1]
        ResourceCleanup.add('vm', vm_id)

        LOG.tc_step("Wait for VM pingable from NATBox")
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

        vm_host = nova_helper.get_vm_host(vm_id)
        LOG.tc_step("Reboot VM host {}".format(vm_host))
        HostsToRecover.add(vm_host, scope='function')
        host_helper.reboot_hosts(vm_host, wait_for_reboot_finish=False)

        LOG.tc_step("Wait for vms to reach ERROR or REBUILD state with best effort")
        vm_helper.wait_for_vm_values(vm_id, fail_ok=True, timeout=120, status=[VMStatus.ERROR, VMStatus.REBUILD])

        LOG.tc_step("Check vms are in Active state and moved to other host after host reboot")
        vm_helper.wait_for_vm_values(vm_id, timeout=300, fail_ok=False, status=[VMStatus.ACTIVE])

        post_vm_host = nova_helper.get_vm_host(vm_id)
        assert vm_host != post_vm_host, "VM host did not change upon host reboot even though VM is in Active state."

        LOG.tc_step("Check VM still pingable from Natbox after evacuated to other host")
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)


class TestDefaultGuest:

    @mark.parametrize('storage_backing', [
        'local_image',
        'local_lvm',
        'remote',
    ])
    def test_evacuate_vms_with_inst_backing(self, storage_backing, add_admin_role):
        """
        Test evacuate vms with various vm storage configs and host instance backing configs

        Args:
            storage_backing: storage backing under test
            add_admin_role (None): test fixture to add admin role to primary tenant

        Skip conditions:
            - Less than two hosts configured with storage backing under test

        Setups:
            - Add admin role to primary tenant (module)

        Test Steps:
            - Create flv_rootdisk without ephemeral or swap disks, and set storage backing extra spec
            - Create flv_ephemswap with ephemeral AND swap disks, and set storage backing extra spec
            - Boot following vms on same host and wait for them to be pingable from NatBox:
                - Boot vm1 from volume with flavor flv_rootdisk
                - Boot vm2 from volume with flavor flv_localdisk
                - Boot vm3 from image with flavor flv_rootdisk
                - Boot vm4 from image with flavor flv_rootdisk, and attach a volume to it
                - Boot vm5 from image with flavor flv_localdisk
            - sudo reboot -f on vms host
            - Ensure evacuation for all 5 vms are successful (vm host changed, active state, pingable from NatBox)

        Teardown:
            - Delete created vms, volumes, flavors
            - Remove admin role from primary tenant (module)

        """
        hosts = host_helper.get_hosts_by_storage_aggregate(storage_backing=storage_backing)
        if len(hosts) < 2:
            skip(SkipReason.LESS_THAN_TWO_HOSTS_WITH_BACKING.format(storage_backing))

        target_host = hosts[0]

        LOG.tc_step("Create a flavor without ephemeral or swap disks")
        flavor_1 = nova_helper.create_flavor('flv_rootdisk', storage_backing=storage_backing,
                                             check_storage_backing=False)[1]
        ResourceCleanup.add('flavor', flavor_1, scope='module')

        LOG.tc_step("Create another flavor with ephemeral and swap disks")
        flavor_2 = nova_helper.create_flavor('flv_ephemswap', ephemeral=1, swap=1, storage_backing=storage_backing,
                                             check_storage_backing=False)[1]
        ResourceCleanup.add('flavor', flavor_2, scope='module')

        LOG.tc_step("Boot vm1 from volume with flavor flv_rootdisk and wait for it pingable from NatBox")
        vm1_name = "vol_root"
        vm1 = vm_helper.boot_vm(vm1_name, flavor=flavor_1, source='volume', vm_host=target_host)[1]
        ResourceCleanup.add('vm', vm1, scope='module')

        vm_helper.wait_for_vm_pingable_from_natbox(vm1)

        LOG.tc_step("Boot vm2 from volume with flavor flv_localdisk and wait for it pingable from NatBox")
        vm2_name = "vol_ephemswap"
        vm2 = vm_helper.boot_vm(vm2_name, flavor=flavor_2, source='volume', vm_host=target_host)[1]
        ResourceCleanup.add('vm', vm2, scope='module')

        vm_helper.wait_for_vm_pingable_from_natbox(vm2)

        LOG.tc_step("Boot vm3 from image with flavor flv_rootdisk and wait for it pingable from NatBox")
        vm3_name = "image_root"
        vm3 = vm_helper.boot_vm(vm3_name, flavor=flavor_1, source='image', vm_host=target_host)[1]
        ResourceCleanup.add('vm', vm3, scope='module', del_vm_vols=False)

        vm_helper.wait_for_vm_pingable_from_natbox(vm3)

        LOG.tc_step("Boot vm4 from image with flavor flv_rootdisk, attach a volume to it and wait for it "
                    "pingable from NatBox")
        vm4_name = 'image_root_attachvol'
        vm4 = vm_helper.boot_vm(vm4_name, flavor_1, source='image', vm_host=target_host)[1]
        ResourceCleanup.add('vm', vm4, scope='module', del_vm_vols=True)

        vol = cinder_helper.create_volume(bootable=False)[1]
        ResourceCleanup.add('volume', vol)
        vm_helper.attach_vol_to_vm(vm4, vol_id=vol)

        vm_helper.wait_for_vm_pingable_from_natbox(vm4)

        LOG.tc_step("Boot vm5 from image with flavor flv_localdisk and wait for it pingable from NatBox")
        vm5_name = 'image_ephemswap'
        vm5 = vm_helper.boot_vm(vm5_name, flavor_2, source='image', vm_host=target_host)[1]
        ResourceCleanup.add('vm', vm5, scope='module', del_vm_vols=True)
        vm_helper.wait_for_vm_pingable_from_natbox(vm5)

        LOG.tc_step("Check all VMs are booted on {}".format(target_host))
        vms_on_host = nova_helper.get_vms_on_hypervisor(hostname=target_host)
        vms = [vm1, vm2, vm3, vm4, vm5]
        assert set(vms) <= set(vms_on_host), "VMs booted on host: {}. Current vms on host: {}".format(vms, vms_on_host)

        LOG.tc_step("Reboot target host {}".format(target_host))
        host_helper.reboot_hosts(target_host, wait_for_reboot_finish=False)
        HostsToRecover.add(target_host)

        LOG.tc_step("Wait for vms to reach ERROR or REBUILD state with best effort")
        vm_helper._wait_for_vms_values(vms, values=[VMStatus.ERROR, VMStatus.REBUILD], fail_ok=True, timeout=120)

        LOG.tc_step("Check vms are in Active state and moved to other host(s) after host reboot")
        res, active_vms, inactive_vms = vm_helper._wait_for_vms_values(vms=vms, values=VMStatus.ACTIVE, timeout=600)

        vms_host_err = []
        for vm in vms:
            if nova_helper.get_vm_host(vm) == target_host:
                vms_host_err.append(vm)

        assert not vms_host_err, "Following VMs stayed on the same host {}: {}\nVMs did not reach Active state: {}". \
            format(target_host, vms_host_err, inactive_vms)

        assert not inactive_vms, "VMs did not reach Active state after evacuated to other host: {}".format(inactive_vms)

        LOG.tc_step("Check VMs are pingable from NatBox after evacuation")
        vm_helper.ping_vms_from_natbox(vms)
