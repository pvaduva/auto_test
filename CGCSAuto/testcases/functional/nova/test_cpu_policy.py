from pytest import mark, fixture, skip

from utils import table_parser
from utils.tis_log import LOG

from consts.cgcs import FlavorSpec, ImageMetadata
from consts.cli_errs import CPUPolicyErr        # used by eval

from keywords import nova_helper, vm_helper, glance_helper, cinder_helper, check_helper, host_helper, system_helper
from testfixtures.resource_mgmt import ResourceCleanup


@mark.parametrize(('flv_vcpus', 'flv_pol', 'img_pol', 'boot_source', 'expt_err'), [
    # mark.domain_sanity((5, None, 'dedicated', 'volume', None)),   covered by test_cpu_pol_vm_actions
    mark.p1((3, None, 'shared', 'image', None)),
    # mark.p2((4, None, None, 'image', None)),  covered by test_cpu_pol_vm_actions
    mark.p3((4, 'dedicated', 'dedicated', 'volume', None)),
    mark.p3((1, 'dedicated', None, 'image', None)),
    mark.p3((1, 'shared', 'shared', 'volume', None)),
    mark.p3((2, 'shared', None, 'image', None)),
    mark.domain_sanity((3, 'dedicated', 'shared', 'volume', None)),
    mark.p2((1, 'shared', 'dedicated', 'image', 'CPUPolicyErr.CONFLICT_FLV_IMG')),
])
def test_boot_vm_cpu_policy_image(flv_vcpus, flv_pol, img_pol, boot_source, expt_err):
    LOG.tc_step("Create flavor with {} vcpus".format(flv_vcpus))
    flavor_id = nova_helper.create_flavor(name='cpu_pol_{}'.format(flv_pol), vcpus=flv_vcpus)[1]
    ResourceCleanup.add('flavor', flavor_id)

    if flv_pol is not None:
        specs = {FlavorSpec.CPU_POLICY: flv_pol}

        LOG.tc_step("Set following extra specs: {}".format(specs))
        nova_helper.set_flavor_extra_specs(flavor_id, **specs)

    if img_pol is not None:
        image_meta = {ImageMetadata.CPU_POLICY: img_pol}
        LOG.tc_step("Create image with following metadata: {}".format(image_meta))
        image_id = glance_helper.create_image(name='cpu_pol_{}'.format(img_pol), **image_meta)[1]
        ResourceCleanup.add('image', image_id)
    else:
        image_id = glance_helper.get_image_id_from_name('cgcs-guest', strict=True)

    if boot_source == 'volume':
        LOG.tc_step("Create a volume from image")
        source_id = cinder_helper.create_volume(name='cpu_pol_img', image_id=image_id)[1]
        ResourceCleanup.add('volume', source_id)
    else:
        source_id = image_id

    prev_cpus = host_helper.get_vcpus_for_computes(rtn_val='used_now')

    LOG.tc_step("Attempt to boot a vm from above {} with above flavor".format(boot_source))
    code, vm_id, msg, ignore = vm_helper.boot_vm(name='cpu_pol', flavor=flavor_id, source=boot_source,
                                                 source_id=source_id, fail_ok=True)
    if vm_id:
        ResourceCleanup.add('vm', vm_id)

    # check for negative tests
    if expt_err is not None:
        LOG.tc_step("Check VM failed to boot due to conflict in flavor and image.")
        assert 4 == code, "Expect boot vm cli reject and no vm booted. Actual: {}".format(msg)
        assert eval(expt_err) in msg, "Expected error message is not found in cli return."
        return  # end the test for negative cases

    # Check for positive tests
    LOG.tc_step("Check vm is successfully booted.")
    assert 0 == code, "Expect vm boot successfully. Actual: {}".format(msg)

    # Calculate expected policy:
    expt_cpu_pol = flv_pol if flv_pol else img_pol
    expt_cpu_pol = expt_cpu_pol if expt_cpu_pol else 'shared'

    vm_host = nova_helper.get_vm_host(vm_id)
    check_helper.check_topology_of_vm(vm_id, vcpus=flv_vcpus, cpu_pol=expt_cpu_pol, vm_host=vm_host,
                                      prev_total_cpus=prev_cpus[vm_host])


@mark.parametrize(('flv_vcpus', 'cpu_pol', 'pol_source', 'boot_source'), [
    mark.p1((4, None, 'flavor', 'image')),
    mark.domain_sanity((2, 'dedicated', 'flavor', 'volume')),
    mark.p2((3, 'shared', 'flavor', 'volume')),
    mark.p1((1, 'dedicated', 'flavor', 'image')),
    mark.nightly((2, 'dedicated', 'image', 'volume')),
    mark.p2((3, 'shared', 'image', 'volume')),
    mark.domain_sanity((1, 'dedicated', 'image', 'image')),
])
def test_cpu_pol_vm_actions(flv_vcpus, cpu_pol, pol_source, boot_source):
    LOG.tc_step("Create flavor with {} vcpus".format(flv_vcpus))
    flavor_id = nova_helper.create_flavor(name='cpu_pol', vcpus=flv_vcpus)[1]
    ResourceCleanup.add('flavor', flavor_id)

    image_id = glance_helper.get_image_id_from_name('cgcs-guest', strict=True)
    if cpu_pol is not None:
        if pol_source == 'flavor':
            specs = {FlavorSpec.CPU_POLICY: cpu_pol}

            LOG.tc_step("Set following extra specs: {}".format(specs))
            nova_helper.set_flavor_extra_specs(flavor_id, **specs)
        else:
            image_meta = {ImageMetadata.CPU_POLICY: cpu_pol}
            LOG.tc_step("Create image with following metadata: {}".format(image_meta))
            image_id = glance_helper.create_image(name='cpu_pol_{}'.format(cpu_pol), **image_meta)[1]
            ResourceCleanup.add('image', image_id)

    if boot_source == 'volume':
        LOG.tc_step("Create a volume from image")
        source_id = cinder_helper.create_volume(name='cpu_pol'.format(cpu_pol), image_id=image_id)[1]
        ResourceCleanup.add('volume', source_id)
    else:
        source_id = image_id

    prev_cpus = host_helper.get_vcpus_for_computes(rtn_val='used_now')

    LOG.tc_step("Boot a vm from {} with above flavor and check vm topology is as expected".format(boot_source))
    vm_id = vm_helper.boot_vm(name='cpu_pol_{}_{}'.format(cpu_pol, flv_vcpus), flavor=flavor_id, source=boot_source,
                              source_id=source_id)[1]
    ResourceCleanup.add('vm', vm_id)

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    vm_host = nova_helper.get_vm_host(vm_id)
    check_helper.check_topology_of_vm(vm_id, vcpus=flv_vcpus, cpu_pol=cpu_pol, vm_host=vm_host,
                                      prev_total_cpus=prev_cpus[vm_host])

    LOG.tc_step("Suspend/Resume vm and check vm topology stays the same")
    vm_helper.suspend_vm(vm_id)
    vm_helper.resume_vm(vm_id)

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=60)
    check_helper.check_topology_of_vm(vm_id, vcpus=flv_vcpus, cpu_pol=cpu_pol, vm_host=vm_host,
                                      prev_total_cpus=prev_cpus[vm_host])

    LOG.tc_step("Stop/Start vm and check vm topology stays the same")
    vm_helper.stop_vms(vm_id)
    vm_helper.start_vms(vm_id)

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=60)
    prev_siblings = check_helper.check_topology_of_vm(vm_id, vcpus=flv_vcpus, cpu_pol=cpu_pol, vm_host=vm_host,
                                                      prev_total_cpus=prev_cpus[vm_host])[1]

    LOG.tc_step("Live migrate vm and check vm topology stays the same")
    vm_helper.live_migrate_vm(vm_id=vm_id)

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=60)
    vm_host = nova_helper.get_vm_host(vm_id)
    prev_siblings = prev_siblings if cpu_pol == 'dedicated' else None   # workaround for
    check_helper.check_topology_of_vm(vm_id, vcpus=flv_vcpus, cpu_pol=cpu_pol, vm_host=vm_host,
                                      prev_total_cpus=prev_cpus[vm_host], prev_siblings=prev_siblings)

    LOG.tc_step("Cold migrate vm and check vm topology stays the same")
    vm_helper.cold_migrate_vm(vm_id=vm_id)

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=60)
    vm_host = nova_helper.get_vm_host(vm_id)
    check_helper.check_topology_of_vm(vm_id, vcpus=flv_vcpus, cpu_pol=cpu_pol, vm_host=vm_host,
                                      prev_total_cpus=prev_cpus[vm_host])


@mark.usefixtures('add_admin_role_module')
@mark.parametrize(('vcpus_dedicated', 'vcpus_shared', 'pol_source', 'boot_source'), [
    mark.p1((2, 1, 'flavor', 'image')),
    mark.p1((1, 3, 'image', 'image')),
    mark.p1((2, 4, 'image', 'volume')),
    mark.nightly((3, 2, 'flavor', 'volume')),
])
def test_cpu_pol_dedicated_shared_coexists(vcpus_dedicated, vcpus_shared, pol_source, boot_source):
    """
    Test two vms coexisting on the same host, one with the dedicated cpu property, and one with the shared cpu property.

    Args:
        vcpus_dedicated: Amount of vcpu(s) to allocate for the vm with the dedicated CPU_POLICY.
        vcpus_shared: Amount of vcpu(s) to allocate for the vm with the shared CPU_POLICY.
        pol_source: Where the CPU_POLICY is set from.
        boot_source: The boot media the vm will use to boot.

    Test Setups:
        - Create two flavors, one for each vm.
        - If using 'flavor' for pol_source, set extra specs for the CPU_POLICY.
        - If using 'image' for pol_source, set ImageMetaData for the CPU_POLICY.
        - If using 'volume' for boot_source, create volume from cgcs-guest image.
        - If using 'image' for boot_source, use cgcs-guest image.
        - Determine the amount of free vcpu(s) on the compute before testing.

    Test Steps:
        - Boot the first vm with CPU_POLICY: dedicated.
        - Wait until vm is pingable from natbox.
        - Check vm topology for vcpu(s).
        - Determine the amount of free vcpu(s) on the compute.
        - Boot the second vm with CPU_POLICY: shared.
        - Wait until vm is pingable from natbox.
        - Check vm topology for vcpu(s).
        - Delete vms
        - Determine the amount of free vcpu(s) on the compute after testing.
        - Compare free vcpu(s) on the compute before and after testing, ensuring they are the same.

    Test Teardown
        - Delete created volumes and flavors
    """
    LOG.tc_step("Getting host list")
    target_hosts = host_helper.get_hypervisors(state='up', status='enabled')
    target_host = target_hosts[0]
    storage_backing = host_helper.get_local_storage_backing(host=target_host)
    if 'image' in storage_backing:
        storage_backing = 'local_image'
    elif 'lvm' in storage_backing:
        storage_backing = 'local_lvm'
    elif 'remote' in storage_backing:
        storage_backing = 'remote'

    image_id = glance_helper.get_image_id_from_name('cgcs-guest', strict=True)
    pre_test_cpus = host_helper.get_vcpus_for_computes(rtn_val='used_now')
    vm_dedicated_id = ''
    vm_shared_id = ''

    collection = ['dedicated', 'shared']
    for x in collection:
        if x == 'dedicated':
            vcpus = vcpus_dedicated
        else:
            vcpus = vcpus_shared
        LOG.tc_step("Create {} flavor with {} vcpus".format(x, vcpus))
        flavor_id = nova_helper.create_flavor(name=x, vcpus=vcpus, storage_backing=storage_backing,
                                              check_storage_backing=False)[1]
        ResourceCleanup.add('flavor', flavor_id)

        if pol_source == 'flavor':
            LOG.tc_step("Set CPU_POLICY for {} flavor".format(x))
            specs = {FlavorSpec.CPU_POLICY: x}
            nova_helper.set_flavor_extra_specs(flavor_id, **specs)
        else:
            LOG.tc_step("Create image with CPU_POLICY: {}".format(x))
            image_meta = {ImageMetadata.CPU_POLICY: x}
            image_id = glance_helper.create_image(name='cpu_pol_{}'.format(x), **image_meta)[1]
            ResourceCleanup.add('image', image_id)

        if boot_source == 'volume':
            LOG.tc_step("Create volume from image")
            source_id = cinder_helper.create_volume(name='cpu_pol_{}'.format(x), image_id=image_id)[1]
            ResourceCleanup.add('volume', source_id)
        else:
            source_id = image_id

        pre_boot_cpus = host_helper.get_vcpus_for_computes(rtn_val='used_now')
        LOG.tc_step("Booting cpu_pol_{}".format(x))
        vm_id = vm_helper.boot_vm(name='cpu_pol_{}'.format(x), flavor=flavor_id, source=boot_source,
                                  source_id=source_id, vm_host=target_host)[1]
        ResourceCleanup.add('vm', vm_id)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        check_helper.check_topology_of_vm(vm_id, vcpus=vcpus, cpu_pol=x, vm_host=target_host,
                                          prev_total_cpus=pre_boot_cpus[target_host])
        if x == 'dedicated':
            vm_dedicated_id = vm_id
        else:
            vm_shared_id = vm_id

    LOG.tc_step("Removing cpu_pol_dedicated")
    vm_helper.delete_vms(vms=vm_dedicated_id)
    LOG.tc_step("Removing cpu_pol_shared")
    vm_helper.delete_vms(vms=vm_shared_id)
    post_delete_cpus = host_helper.get_vcpus_for_computes(rtn_val='used_now')
    assert post_delete_cpus == pre_test_cpus, "vcpu count after test does not equal vcpu count before test"
