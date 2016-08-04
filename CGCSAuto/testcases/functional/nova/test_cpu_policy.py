import time

from pytest import mark, fixture, skip

from utils.tis_log import LOG

from consts.cgcs import FlavorSpec, ImageMetadata
from consts.cli_errs import CPUPolicyErr        # used by eval

from keywords import nova_helper, vm_helper, glance_helper, cinder_helper, check_helper, host_helper
from testfixtures.resource_mgmt import ResourceCleanup


@mark.parametrize(('flv_vcpus', 'flv_pol', 'img_pol', 'boot_source', 'expt_err'), [
    mark.p2((5, None, 'dedicated', 'volume', None)),
    mark.p2((3, None, 'shared', 'image', None)),
    mark.p2((4, None, None, 'image', None)),
    mark.p3((4, 'dedicated', 'dedicated', 'volume', None)),
    mark.p3((1, 'dedicated', None, 'image', None)),
    mark.p3((1, 'shared', 'shared', 'volume', None)),
    mark.p3((2, 'shared', None, 'image', None)),
    mark.p1((3, 'dedicated', 'shared', 'volume', None)),
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
        image_id = glance_helper.get_image_id_from_name('cgcs-guest')

    if boot_source == 'volume':
        LOG.tc_step("Create a volume from image")
        source_id = cinder_helper.create_volume(name='cpu_pol_img', image_id=image_id)[1]
        ResourceCleanup.add('volume', source_id)
    else:
        source_id = image_id

    prev_cpus = host_helper.get_vcpus_for_computes(rtn_val='used_now')

    LOG.tc_step("Attempt to boot a vm from above {} with above flavor".format(boot_source))
    code, vm_id, msg, ignore = vm_helper.boot_vm(name='cpu_thread_image', flavor=flavor_id, source=boot_source,
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
    LOG.tc_step("Check vm is successfully booted on a HT enabled host.")
    assert 0 == code, "Expect vm boot successfully. Actual: {}".format(msg)

    # Calculate expected policy:
    expt_cpu_pol = flv_pol if flv_pol else img_pol

    vm_host = nova_helper.get_vm_host(vm_id)
    check_helper.check_topology_of_vm(vm_id, vcpus=flv_vcpus, cpu_pol=expt_cpu_pol, vm_host=vm_host,
                                      prev_total_cpus=prev_cpus[vm_host])


@mark.parametrize(('flv_vcpus', 'flv_pol', 'boot_source'), [
    mark.p1((4, None, 'image')),
    mark.p1((2, 'dedicated', 'volume')),
    mark.p2((3, 'shared', 'volume')),
    mark.p2((1, 'dedicated', 'image')),
])
def test_cpu_pol_vm_actions(flv_vcpus, flv_pol, boot_source):
    LOG.tc_step("Create flavor with {} vcpus".format(flv_vcpus))
    flavor_id = nova_helper.create_flavor(name='cpu_pol_image', vcpus=flv_vcpus)[1]
    # TODO ResourceCleanup.add('flavor', flavor_id)

    if flv_pol is not None:
        specs = {FlavorSpec.CPU_POLICY: flv_pol}

        LOG.tc_step("Set following extra specs: {}".format(specs))
        nova_helper.set_flavor_extra_specs(flavor_id, **specs)

    prev_cpus = host_helper.get_vcpus_for_computes(rtn_val='used_now')

    LOG.tc_step("Boot a vm from {} with above flavor and check vm topology is as expected".format(boot_source))
    vm_id = vm_helper.boot_vm(name='cpu_pol_{}_{}'.format(flv_pol, flv_vcpus), flavor=flavor_id, source=boot_source)[1]
    # TODO ResourceCleanup.add('vm', vm_id)

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    vm_host = nova_helper.get_vm_host(vm_id)
    check_helper.check_topology_of_vm(vm_id, vcpus=flv_vcpus, cpu_pol=flv_pol, vm_host=vm_host,
                                      prev_total_cpus=prev_cpus[vm_host])

    LOG.tc_step("Suspend/Resume vm and check vm topology stays the same")
    vm_helper.suspend_vm(vm_id)
    vm_helper.resume_vm(vm_id)

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=60)
    check_helper.check_topology_of_vm(vm_id, vcpus=flv_vcpus, cpu_pol=flv_pol, vm_host=vm_host,
                                      prev_total_cpus=prev_cpus[vm_host])

    LOG.tc_step("Stop/Start vm and check vm topology stays the same")
    vm_helper.stop_vms(vm_id)
    vm_helper.start_vms(vm_id)

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=60)
    check_helper.check_topology_of_vm(vm_id, vcpus=flv_vcpus, cpu_pol=flv_pol, vm_host=vm_host,
                                      prev_total_cpus=prev_cpus[vm_host])

    LOG.tc_step("Live migrate vm and check vm topology stays the same")
    vm_helper.live_migrate_vm(vm_id=vm_id)

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=60)
    vm_host = nova_helper.get_vm_host(vm_id)
    check_helper.check_topology_of_vm(vm_id, vcpus=flv_vcpus, cpu_pol=flv_pol, vm_host=vm_host,
                                      prev_total_cpus=prev_cpus[vm_host])

    LOG.tc_step("Cold migrate vm and check vm topology stays the same")
    vm_helper.cold_migrate_vm(vm_id=vm_id)

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=60)
    vm_host = nova_helper.get_vm_host(vm_id)
    check_helper.check_topology_of_vm(vm_id, vcpus=flv_vcpus, cpu_pol=flv_pol, vm_host=vm_host,
                                      prev_total_cpus=prev_cpus[vm_host])
