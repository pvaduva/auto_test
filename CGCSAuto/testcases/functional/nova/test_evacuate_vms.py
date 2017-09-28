from pytest import fixture, skip, mark

from utils.tis_log import LOG
from consts.cgcs import VMStatus
from consts.reasons import SkipReason

from keywords import vm_helper, host_helper, nova_helper, cinder_helper, check_helper
from testfixtures.fixture_resources import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


@fixture(scope='module', autouse=True)
def skip_test_if_less_than_two_hosts():
    if len(host_helper.get_up_hypervisors()) < 2:
        skip(SkipReason.LESS_THAN_TWO_HYPERVISORS)

    LOG.fixture_step("Update instance and volume quota to at least 10 and 20 respectively")
    if nova_helper.get_quotas(quotas='instances')[0] < 10:
        nova_helper.update_quotas(instances=10, cores=20)
    if cinder_helper.get_quotas(quotas='volumes')[0] < 20:
        cinder_helper.update_quotas(volumes=20)


def touch_files_under_vm_disks(vm_id, ephemeral, swap, vm_type, disks):

    expt_len = 1 + int(bool(ephemeral)) + int(bool(swap)) + (1 if 'with_vol' in vm_type else 0)

    LOG.tc_step("Auto mount non-root disks if any")
    mounts = vm_helper.auto_mount_vm_disks(vm_id=vm_id, disks=disks)
    assert expt_len == len(mounts)

    if bool(swap):
        mounts.remove('none')

    LOG.tc_step("Create files under vm disks: {}".format(mounts))
    file_paths, content = vm_helper.touch_files(vm_id=vm_id, file_dirs=mounts)
    return file_paths, content


class TestDefaultGuest:

    @mark.parametrize('storage_backing', [
        'local_image',
        'local_lvm',
        'remote',
    ])
    def test_evacuate_vms_with_inst_backing(self, storage_backing, add_admin_role_class):
        """
        Test evacuate vms with various vm storage configs and host instance backing configs

        Args:
            storage_backing: storage backing under test
            add_admin_role_class (None): test fixture to add admin role to primary tenant

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
        ResourceCleanup.add('flavor', flavor_1, scope='class')

        LOG.tc_step("Create another flavor with ephemeral and swap disks")
        flavor_2 = nova_helper.create_flavor('flv_ephemswap', ephemeral=1, swap=512, storage_backing=storage_backing,
                                             check_storage_backing=False)[1]
        ResourceCleanup.add('flavor', flavor_2, scope='class')

        LOG.tc_step("Boot vm1 from volume with flavor flv_rootdisk and wait for it pingable from NatBox")
        vm1_name = "vol_root"
        vm1 = vm_helper.boot_vm(vm1_name, flavor=flavor_1, source='volume', avail_zone='nova', vm_host=target_host,
                                cleanup='class')[1]

        vms_info = {vm1: {'ephemeral': 0,
                          'swap': 0,
                          'vm_type': 'volume',
                          'disks': vm_helper.get_vm_devices_via_virsh(vm1)}}
        vm_helper.wait_for_vm_pingable_from_natbox(vm1)

        LOG.tc_step("Boot vm2 from volume with flavor flv_localdisk and wait for it pingable from NatBox")
        vm2_name = "vol_ephemswap"
        vm2 = vm_helper.boot_vm(vm2_name, flavor=flavor_2, source='volume', avail_zone='nova', vm_host=target_host,
                                cleanup='class')[1]

        vm_helper.wait_for_vm_pingable_from_natbox(vm2)
        vms_info[vm2] = {'ephemeral': 1,
                         'swap': 512,
                         'vm_type': 'volume',
                         'disks': vm_helper.get_vm_devices_via_virsh(vm2)}

        LOG.tc_step("Boot vm3 from image with flavor flv_rootdisk and wait for it pingable from NatBox")
        vm3_name = "image_root"
        vm3 = vm_helper.boot_vm(vm3_name, flavor=flavor_1, source='image', avail_zone='nova', vm_host=target_host,
                                cleanup='class')[1]

        vm_helper.wait_for_vm_pingable_from_natbox(vm3)
        vms_info[vm3] = {'ephemeral': 0,
                         'swap': 0,
                         'vm_type': 'image',
                         'disks': vm_helper.get_vm_devices_via_virsh(vm3)}

        LOG.tc_step("Boot vm4 from image with flavor flv_rootdisk, attach a volume to it and wait for it "
                    "pingable from NatBox")
        vm4_name = 'image_root_attachvol'
        vm4 = vm_helper.boot_vm(vm4_name, flavor_1, source='image', avail_zone='nova', vm_host=target_host,
                                cleanup='class')[1]

        vol = cinder_helper.create_volume(bootable=False)[1]
        ResourceCleanup.add('volume', vol, scope='class')
        vm_helper.attach_vol_to_vm(vm4, vol_id=vol, mount=False)

        vm_helper.wait_for_vm_pingable_from_natbox(vm4)
        vms_info[vm4] = {'ephemeral': 0,
                         'swap': 0,
                         'vm_type': 'image_with_vol',
                         'disks': vm_helper.get_vm_devices_via_virsh(vm4)}

        LOG.tc_step("Boot vm5 from image with flavor flv_localdisk and wait for it pingable from NatBox")
        vm5_name = 'image_ephemswap'
        vm5 = vm_helper.boot_vm(vm5_name, flavor_2, source='image', avail_zone='nova', vm_host=target_host,
                                cleanup='class')[1]
        vm_helper.wait_for_vm_pingable_from_natbox(vm5)
        vms_info[vm5] = {'ephemeral': 1,
                         'swap': 512,
                         'vm_type': 'image',
                         'disks': vm_helper.get_vm_devices_via_virsh(vm5)}

        LOG.tc_step("Check all VMs are booted on {}".format(target_host))
        vms_on_host = nova_helper.get_vms_on_hypervisor(hostname=target_host)
        vms = [vm1, vm2, vm3, vm4, vm5]
        assert set(vms) <= set(vms_on_host), "VMs booted on host: {}. Current vms on host: {}".format(vms, vms_on_host)

        for vm_ in vms:
            file_paths, content = touch_files_under_vm_disks(vm_, **vms_info[vm_])
            vms_info[vm_]['file_paths'] = file_paths
            vms_info[vm_]['content'] = content

        LOG.tc_step("Reboot target host {}".format(target_host))
        host_helper.reboot_hosts(target_host, wait_for_reboot_finish=False)
        HostsToRecover.add(target_host)

        LOG.tc_step("Wait for vms to reach ERROR or REBUILD state with best effort")
        vm_helper.wait_for_vms_values(vms, values=[VMStatus.ERROR, VMStatus.REBUILD], fail_ok=True, timeout=120)

        LOG.tc_step("Check vms are in Active state and moved to other host(s) after host reboot")
        res, active_vms, inactive_vms = vm_helper.wait_for_vms_values(vms=vms, values=VMStatus.ACTIVE, timeout=600)

        vms_host_err = []
        for vm in vms:
            post_host = nova_helper.get_vm_host(vm)
            if post_host == target_host:
                vms_host_err.append(vm)
            vms_info[vm]['post_host'] = post_host
        # by now, all vm_info dict should include: ephemeral, swap, vm_type, disks, file_paths, content, post_host

        assert not vms_host_err, "Following VMs stayed on the same host {}: {}\nVMs did not reach Active state: {}". \
            format(target_host, vms_host_err, inactive_vms)

        assert not inactive_vms, "VMs did not reach Active state after evacuated to other host: {}".format(inactive_vms)

        LOG.tc_step("Check VMs are pingable from NatBox after evacuation")
        vm_helper.ping_vms_from_natbox(vms, fail_ok=False)

        LOG.tc_step("Check files after evacuation")
        for vm_ in vms:
            LOG.info("--------------------Check files for vm {}".format(vm_))
            check_helper.check_vm_files(vm_id=vm_, vm_action='evacuate', storage_backing=storage_backing,
                                        prev_host=target_host, **vms_info[vm_])
