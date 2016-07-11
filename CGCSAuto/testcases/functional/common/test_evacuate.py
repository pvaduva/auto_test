from pytest import mark, fixture

from utils.tis_log import LOG
from consts.cgcs import VMStatus
from consts.timeout import VMTimeout
from keywords import vm_helper, host_helper, nova_helper, cinder_helper
from testfixtures.resource_mgmt import ResourceCleanup


@fixture(scope='module')
def vms_():
    if nova_helper.get_quotas(quotas='instances')[0] < 10:
        nova_helper.update_quotas(instances=10, cores=20)
    if cinder_helper.get_quotas(quotas='volumes')[0] < 20:
        cinder_helper.update_quotas(volumes=20)

    flavor_1 = nova_helper.create_flavor('vol_nolocal')[1]
    ResourceCleanup.add('flavor', flavor_1, scope='module')
    flavor_2 = nova_helper.create_flavor('vol_local', ephemeral=1)[1]
    ResourceCleanup.add('flavor', flavor_2, scope='module')
    flavor_3 = nova_helper.create_flavor('image_novol')[1]
    ResourceCleanup.add('flavor', flavor_3, scope='module')
    flavor_4 = nova_helper.create_flavor('image_vol')[1]
    ResourceCleanup.add('flavor', flavor_4, scope='module')

    vm1 = vm_helper.boot_vm('vol_nolocal', flavor=flavor_1, source='volume')[1]
    ResourceCleanup.add('vm', vm1, scope='module')
    vm2 = vm_helper.boot_vm('vol_local', flavor=flavor_2, source='volume')[1]
    ResourceCleanup.add('vm', vm2, scope='module')
    vm3 = vm_helper.boot_vm('image_novol', flavor=flavor_3, source='image')[1]
    ResourceCleanup.add('vm', vm3, scope='module', del_vm_vols=False)
    vm4 = vm_helper.boot_vm('image_vol', flavor_4, source='image')[1]
    ResourceCleanup.add('vm', vm4, scope='module', del_vm_vols=False)

    return [vm1, vm2, vm3, vm4]


def test_reboot_with_vms(vms_):
    vm1, vm2, vm3, vm4 = vms_

    target_host = nova_helper.get_vm_host(vm2)
    LOG.tc_step("Live migrate following vms to target host {}: {}".format(target_host, vms_))

    if nova_helper.get_vm_host(vm1) != target_host:
        vm_helper.live_migrate_vm(vm1, destination_host=target_host, block_migrate=False)

    # Live migrate vms booted from image to target host with best effort only in case of storage backing mismatch
    for vm in [vm3, vm4]:
        if nova_helper.get_vm_host(vm) != target_host:
            vm_helper.live_migrate_vm(vm, destination_host=target_host, block_migrate=True)

    LOG.tc_step("Attach volume to vm that was booted from image: {}.".format(vm4))
    vm_helper.attach_vol_to_vm(vm4)

    vms_on_target = nova_helper.get_vms_on_hypervisor(target_host)
    pre_vms_status = nova_helper.get_vms_info(vms_on_target, field='Status')
    vms_to_check = [vm for vm in pre_vms_status if pre_vms_status[vm].lower() != 'error']

    LOG.tc_step("Reboot target host.")
    host_helper.reboot_hosts(target_host)
    host_helper.wait_for_hypervisors_up(target_host)
    host_helper.wait_for_hosts_in_nova_compute(target_host)

    post_vms_status = nova_helper.get_vms_info(vms_to_check, field='Status')

    LOG.tc_step("Check vms are evacuated to different host and vms are in Active state or original state.")
    for vm, status in post_vms_status.items():
        assert nova_helper.get_vm_host(vm) != target_host, "VM {} is not evacuated to other host.".format(vm)
        vm_helper.wait_for_vm_values(vm, timeout=VMTimeout.AUTO_RECOVERY, fail_ok=False,
                                     status=[VMStatus.ACTIVE, pre_vms_status])

