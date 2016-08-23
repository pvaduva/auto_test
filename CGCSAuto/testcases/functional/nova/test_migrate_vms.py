from pytest import fixture, mark, skip

from utils.tis_log import LOG

from consts.cgcs import FlavorSpec
from consts.cli_errs import LiveMigErr
from keywords import vm_helper, nova_helper, system_helper, host_helper, cinder_helper, glance_helper
from testfixtures.resource_mgmt import ResourceCleanup


@fixture(scope='module')
def hosts_per_stor_backing():
    hosts_per_backing = host_helper.get_hosts_per_storage_backing()
    LOG.fixture_step("Hosts per storage backing: {}".format(hosts_per_backing))

    # if max([len(hosts) for hosts in list(hosts_per_backing.values())]) < 2:
    #     skip("No two hosts have the same storage backing")

    return hosts_per_backing


@mark.parametrize(('storage_backing', 'ephemeral', 'swap', 'cpu_pol', 'vcpus', 'vm_type', 'block_mig'), [
    mark.p1(('local_image', 0, 0, None, 1, 'volume', False)),
    mark.p1(('local_image', 0, 0, 'dedicated', 2, 'volume', False)),
    mark.p1(('local_image', 0, 0, 'shared', 2, 'image', True)),
    mark.p1(('local_image', 1, 1, 'dedicated', 1, 'image', False)),
    mark.p1(('local_lvm', 0, 0, None, 1, 'volume', False)),
    mark.p1(('local_lvm', 0, 0, 'dedicated', 2, 'volume', False)),
    mark.p1(('remote', 0, 0, None, 2, 'volume', False)),
    mark.p1(('remote', 1, 0, 'dedicated', 1, 'volume', False)),
    mark.p1(('remote', 1, 1, None, 1, 'image', False)),
    mark.p1(('remote', 0, 1, 'dedicated', 2, 'image_with_vol', False)),
])
def test_live_migrate_vm_positive(storage_backing, ephemeral, swap, cpu_pol, vcpus, vm_type, block_mig,
                                  hosts_per_stor_backing):
    """
    Skip Condition:
        - Less than two hosts have specified storage backing

    Test Steps:
        - create flavor with specified vcpus, cpu_policy, ephemeral, swap, storage_backing
        - boot vm from specified boot source with above flavor
        - (attach volume to vm if 'image_with_vol', specified in vm_type)
        - Live migrate the vm with specified block_migration flag
        - Verify VM is successfully live migrated to different host

    Teardown:
        - Delete created vm, volume, flavor

    """
    if len(hosts_per_stor_backing[storage_backing]) < 2:
        skip("Less than two hosts have {} storage backing".format(storage_backing))

    vm_id = _boot_vm_under_test(storage_backing, ephemeral, swap, cpu_pol, vcpus, vm_type)

    prev_vm_host = nova_helper.get_vm_host(vm_id)

    LOG.tc_step("Live migrate VM and ensure it succeeded")
    # block_mig = True if boot_source == 'image' else False
    code, output = vm_helper.live_migrate_vm(vm_id, block_migrate=block_mig)
    assert 0 == code, "Live migrate is not successful. Details: {}".format(output)

    post_vm_host = nova_helper.get_vm_host(vm_id)
    assert prev_vm_host != post_vm_host


@mark.parametrize(('storage_backing', 'ephemeral', 'swap', 'vm_type', 'block_mig', 'expt_err'), [
    mark.p1(('local_image', 0, 0, 'volume', True, 'LiveMigErr.BLOCK_MIG_UNSUPPORTED')),
    mark.p1(('local_image', 1, 0, 'volume', False, 'TBD')),
    mark.p1(('local_image', 0, 1, 'volume', False, 'TBD')),
    mark.p1(('local_image', 0, 0, 'image_with_vol', False, 'TBD')),
    mark.p1(('local_image', 0, 0, 'image_with_vol', True, 'TBD')),
    # mark.p1(('local_image', 0, 0, 'shared', 2, 'image', False, ??)),      obsolete in Mitaka
    # mark.p1(('local_image', 1, 1, 'dedicated', 1, 'image', False, ??)),   obsolete in Mitaka
    mark.p1(('local_lvm', 0, 0, 'volume', True, 'LiveMigErr.BLOCK_MIG_UNSUPPORTED')),
    mark.p1(('local_lvm', 1, 0, 'volume', True, 'TBD')),
    mark.p1(('local_lvm', 0, 1, 'volume', True, 'TBD')),
    mark.p1(('local_lvm', 0, 1, 'volume', False, 'TBD')),
    mark.p1(('local_lvm', 1, 0, 'volume', False, 'TBD')),
    mark.p1(('local_lvm', 0, 0, 'image', True, 'TBD')),
    mark.p1(('local_lvm', 1, 0, 'image', True, 'TBD')),
    mark.p1(('local_lvm', 0, 0, 'image', False, 'TBD')),
    mark.p1(('local_lvm', 0, 1, 'image', False, 'TBD')),
    mark.p1(('local_lvm', 0, 0, 'image_with_vol', False, 'TBD')),
    mark.p1(('local_lvm', 0, 0, 'image_with_vol', True, 'TBD')),
    mark.p1(('remote', 0, 0, 'volume', True, 'LiveMigErr.BLOCK_MIG_UNSUPPORTED')),
    mark.p1(('remote', 1, 0, 'volume', True, 'LiveMigErr.BLOCK_MIG_UNSUPPORTED')),
    mark.p1(('remote', 0, 1, 'volume', True, 'LiveMigErr.BLOCK_MIG_UNSUPPORTED')),
    mark.p1(('remote', 0, 1, 'image', True, 'LiveMigErr.BLOCK_MIG_UNSUPPORTED')),
    mark.p1(('remote', 0, 0, 'image_with_vol', True, 'LiveMigErr.BLOCK_MIG_UNSUPPORTED')),
])
def test_live_migrate_vm_negative(storage_backing, ephemeral, swap, vm_type, block_mig, expt_err, hosts_per_stor_backing):
    """
    Skip Condition:
        - Less than two hosts have specified storage backing

    Test Steps:
        - create flavor with specified vcpus, cpu_policy, ephemeral, swap, storage_backing
        - boot vm from specified boot source with above flavor
        - (attach volume to vm if 'image_with_vol', specified in vm_type)
        - Live migrate the vm with specified block_migration flag
        - Verify VM is successfully live migrated to different host

    Teardown:
        - Delete created vm, volume, flavor

    """
    if len(hosts_per_stor_backing[storage_backing]) < 2:
        skip("Less than two hosts have {} storage backing".format(storage_backing))

    vm_id = _boot_vm_under_test(storage_backing, ephemeral, swap, None, 1, vm_type)

    prev_vm_host = nova_helper.get_vm_host(vm_id)

    LOG.tc_step("Live migrate VM and ensure it succeeded")
    # block_mig = True if boot_source == 'image' else False
    code, output = vm_helper.live_migrate_vm(vm_id, block_migrate=block_mig)
    assert 1 == code, "Expect live migration to have expected fail. Actual: {}".format(output)
    assert expt_err in output, "Expected error message {} is not in actual error message: {}".format(expt_err, output)

    post_vm_host = nova_helper.get_vm_host(vm_id)
    assert prev_vm_host == post_vm_host, "VM host changed even though live migration request rejected."


@mark.parametrize(('storage_backing', 'ephemeral', 'swap', 'cpu_pol', 'vcpus', 'vm_type', 'resize'), [
    mark.p1(('local_image', 0, 0, None, 1, 'volume', 'confirm')),
    mark.p1(('local_image', 0, 0, 'dedicated', 2, 'volume', 'confirm')),
    mark.p1(('local_image', 1, 0, 'shared', 2, 'image', 'confirm')),
    mark.p1(('local_image', 0, 1, 'dedicated', 1, 'image', 'confirm')),
    mark.p1(('local_image', 0, 0, None, 1, 'image_with_vol', 'confirm')),
    mark.p1(('local_lvm', 0, 0, None, 1, 'volume', 'confirm')),
    mark.p1(('local_lvm', 0, 0, 'dedicated', 2, 'image', 'confirm')),
    mark.p1(('local_lvm', 0, 0, 'dedicated', 1, 'image_with_vol', 'confirm')),
    mark.p1(('local_lvm', 0, 1, None, 2, 'volume', 'confirm')),
    mark.p1(('local_lvm', 1, 1, 'dedicated', 2, 'volume', 'confirm')),
    mark.p1(('remote', 0, 0, None, 2, 'volume', 'confirm')),
    mark.p1(('remote', 1, 0, None, 1, 'volume', 'confirm')),
    mark.p1(('remote', 1, 1, None, 1, 'image', 'confirm')),
    mark.p1(('remote', 0, 0, None, 2, 'image_with_vol', 'confirm')),
    mark.p1(('local_image', 0, 0, None, 2, 'volume', 'revert')),
    mark.p1(('local_image', 0, 0, 'dedicated', 1, 'volume', 'revert')),
    mark.p1(('local_image', 1, 0, 'shared', 2, 'image', 'revert')),
    mark.p1(('local_image', 0, 1, 'dedicated', 1, 'image', 'revert')),
    mark.p1(('local_image', 0, 0, 'dedicated', 2, 'image_with_vol', 'revert')),
    mark.p1(('local_lvm', 0, 0, None, 2, 'volume', 'revert')),
    mark.p1(('local_lvm', 0, 0, 'dedicated', 1, 'volume', 'revert')),
    mark.p1(('local_lvm', 0, 1, None, 1, 'volume', 'revert')),
    mark.p1(('local_lvm', 1, 0, 'dedicated', 2, 'image', 'revert')),
    mark.p1(('local_lvm', 0, 0, 'dedicated', 1, 'image_with_vol', 'revert')),
    mark.p1(('remote', 0, 0, None, 2, 'volume', 'revert')),
    mark.p1(('remote', 1, 1, None, 1, 'volume', 'revert')),
    mark.p1(('remote', 0, 0, None, 1, 'image', 'revert')),
    mark.p1(('remote', 1, 0, None, 2, 'image_with_vol', 'revert')),
])
def test_cold_migrate_vm_2(storage_backing, ephemeral, swap, cpu_pol, vcpus, vm_type, resize, hosts_per_stor_backing):
    """
    Skip Condition:
        - Less than two hosts have specified storage backing

    Test Steps:
        - create flavor with specified vcpus, cpu_policy, ephemeral, swap, storage_backing
        - boot vm from specified boot source with above flavor
        - (attach volume to vm if 'image_with_vol', specified in vm_type)
        - Cold migrate vm
        - Confirm/Revert resize as specified
        - Verify VM is successfully cold migrated and confirmed/reverted resize

    Teardown:
        - Delete created vm, volume, flavor

    """
    if len(hosts_per_stor_backing[storage_backing]) < 2:
        skip("Less than two hosts have {} storage backing".format(storage_backing))

    vm_id = _boot_vm_under_test(storage_backing, ephemeral, swap, cpu_pol, vcpus, vm_type)
    prev_vm_host = nova_helper.get_vm_host(vm_id)

    LOG.tc_step("Cold migrate VM and {} resize".format(resize))

    revert = True if resize == 'revert' else False
    code, output = vm_helper.cold_migrate_vm(vm_id, revert=revert)
    assert 0 == code, "Cold migrate {} is not successful. Details: {}".format(resize, output)

    # Below steps are unnecessary as host is already checked in cold_migrate_vm keyword. Add steps below just in case.
    LOG.tc_step("Check VM host is as expected after cold migrate {}".format(resize))
    post_vm_host = nova_helper.get_vm_host(vm_id)
    if revert:
        assert prev_vm_host == post_vm_host, "vm host changed after cold migrate revert"
    else:
        assert prev_vm_host != post_vm_host, "vm host did not change after cold migrate"


@mark.parametrize(('storage_backing', 'ephemeral', 'swap', 'boot_source'), [
    ('local_image', 0, 0, 'image'),
    ('local_image', 1, 0, 'volume'),
    ('local_image', 1, 1, 'volume'),
    ('local_image', 0, 1, 'image'),
    ('local_lvm', 0, 0, 'image'),
    ('local_lvm', 1, 0, 'volume'),
    ('local_lvm', 0, 1, 'volume'),
    ('local_lvm', 1, 1, 'image'),
    ('remote', 0, 0, 'image'),
    ('remote', 1, 0, 'volume'),
    ('remote', 0, 1, 'image'),
    ('remote', 1, 1, 'volume'),
])
def test_migrate_vm_negative_no_other_host(storage_backing, ephemeral, swap, boot_source, hosts_per_stor_backing):
    """
    Skip Condition:
        - Number of hosts with specified storage backing is not 1

    Test Steps:
        - create flavor with specified storage_backing, ephemera disk, swap disk
        - Boot vm from specified boot source with above flavor
        - Attempt to live migrate the vm
        - verify live migration request rejected due to no matching storage backing
        - Attempt to cold migrate the vm
        - verify cold migration request rejected due to no matching storage backing

    Teardown:
        - Delete created vm, volume, flavor

    """
    if len(hosts_per_stor_backing[storage_backing]) != 1:
        skip("Number of {} hosts is not 1".format(storage_backing))

    vm_id = _boot_vm_under_test(storage_backing, ephemeral, swap, None, 2, boot_source)

    LOG.tc_step("Attempt to live migrate VM and verify request rejected due to no matching storage backing")
    code, output = vm_helper.live_migrate_vm(vm_id=vm_id, fail_ok=True)
    assert 1 == code, "Expect live mig to fail due to no matching storage backing. Actual: {}".format(output)

    LOG.tc_step("Attempt to cold migrate VM and verify request rejected due to no matching storage backing")
    code, output = vm_helper.cold_migrate_vm(vm_id, fail_ok=True)
    assert 1 == code, "Expect cold mig to fail due to no matching storage backing. Actual: {}".format(output)


def _boot_vm_under_test(storage_backing, ephemeral, swap, cpu_pol, vcpus, vm_type):

    LOG.tc_step("Create a flavor with {} vcpus, {} ephemera disk, {} swap disk".format(vcpus, ephemeral, swap))
    flavor_id = nova_helper.create_flavor(name='migration_test', ephemeral=ephemeral, swap=swap, vcpus=vcpus,
                                          check_storage_backing=False)[1]
    ResourceCleanup.add('flavor', flavor_id)

    specs = {FlavorSpec.STORAGE_BACKING: storage_backing}
    if cpu_pol is not None:
        specs[FlavorSpec.CPU_POLICY] = cpu_pol

    LOG.tc_step("Add following extra specs: {}".format(specs))
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **specs)

    boot_source = 'volume' if vm_type == 'volume' else 'image'
    LOG.tc_step("Boot a vm from {}".format(boot_source))
    vm_id = vm_helper.boot_vm('live-mig', flavor=flavor_id, source=boot_source, reuse_vol=False)[1]
    ResourceCleanup.add('vm', vm_id)

    if vm_type == 'image_with_vol':
        LOG.tc_step("Attach volume to vm")
        vm_helper.attach_vol_to_vm(vm_id=vm_id)

    return vm_id


@mark.sanity
@mark.parametrize(('guest_os', 'mig_type', 'cpu_pol'), [
    ('ubuntu', 'live', 'dedicated'),
    ('ubuntu', 'cold', 'dedicated'),
    ('cgcs-guest', 'live', None),
    mark.cpe_sanity(('cgcs-guest', 'cold', None)),
])
def test_migrate_vm(guest_os, mig_type, cpu_pol, ubuntu_image):
    LOG.tc_step("Create a flavor with 1 vcpu")
    flavor_id = nova_helper.create_flavor(name='{}-mig'.format(mig_type), vcpus=1, root_disk=9)[1]
    ResourceCleanup.add('flavor', flavor_id)

    if cpu_pol is not None:
        specs = {FlavorSpec.CPU_POLICY: cpu_pol}
        LOG.tc_step("Add following extra specs: {}".format(specs))
        nova_helper.set_flavor_extra_specs(flavor=flavor_id, **specs)

    LOG.tc_step("Create a volume from {} image".format(guest_os))
    if guest_os == 'ubuntu':
        image_id = ubuntu_image
    else:
        image_id = glance_helper.get_image_id_from_name('cgcs-guest')
    vol_id = cinder_helper.create_volume(name='ubuntu', image_id=image_id, size=9)[1]
    ResourceCleanup.add('volume', vol_id)

    LOG.tc_step("Boot a vm from above flavor and volume")
    vm_id = vm_helper.boot_vm('live-mig', flavor=flavor_id, source='volume', source_id=vol_id)[1]
    ResourceCleanup.add('vm', vm_id, del_vm_vols=False)

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    LOG.tc_step("{} migrate vm and check vm is moved to different host".format(mig_type))
    prev_vm_host = nova_helper.get_vm_host(vm_id)
    if mig_type == 'live':
        vm_helper.live_migrate_vm(vm_id)
    else:
        vm_helper.cold_migrate_vm(vm_id)

    vm_host = nova_helper.get_vm_host(vm_id)
    assert prev_vm_host != vm_host, "vm host did not change after {} migration".format(mig_type)

    LOG.tc_step("Ping vm from NatBox after {} migration".format(mig_type))
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=30)
