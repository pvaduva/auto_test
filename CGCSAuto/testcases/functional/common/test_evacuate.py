from pytest import fixture, skip, mark

from utils.tis_log import LOG
from consts.cgcs import VMStatus

from keywords import vm_helper, host_helper, nova_helper, cinder_helper
from testfixtures.resource_mgmt import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


@fixture(scope='module')
def vms_():
    if len(host_helper.get_nova_hosts()) < 2:
        skip("Less than two hypervisors available")

    LOG.fixture_step("Update instance and volume quota to at least 10 and 20 respectively")
    if nova_helper.get_quotas(quotas='instances')[0] < 10:
        nova_helper.update_quotas(instances=10, cores=20)
    if cinder_helper.get_quotas(quotas='volumes')[0] < 20:
        cinder_helper.update_quotas(volumes=20)

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

    return {vm1: vm1_name, vm2: vm2_name, vm3: vm3_name, vm4: vm4_name}


@mark.trylast
@mark.sanity
def test_evacuate_vms(vms_):
    vms_ids = vms_.keys()
    vm1, vm2, vm3, vm4 = vms_ids

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
    vm_helper._wait_for_vms_values(vms_ids, values=[VMStatus.ERROR, VMStatus.REBUILD], fail_ok=True, timeout=120)

    LOG.tc_step("Check vms are in Active state and moved to other host(s) after host reboot")
    res, active_vms, inactive_vms = vm_helper._wait_for_vms_values(vms=vms_ids, values=VMStatus.ACTIVE, timeout=600)

    vms_host_err = []
    for vm in vms_ids:
        if nova_helper.get_vm_host(vm) == target_host:
            vms_host_err.append(vm)

    assert not vms_host_err, "Following VMs stayed on the same host {}: {}\nVMs did not reach Active state: {}".\
                             format(target_host, vms_host_err, inactive_vms)

    assert not inactive_vms, "VMs did not reach Active state after evacuated to other host: {}".format(inactive_vms)

    LOG.tc_step("Check VMs are pingable from NatBox after evacuation")
    vm_helper.ping_vms_from_natbox(vms_ids)
