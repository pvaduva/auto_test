from pytest import mark, fixture, skip

from utils.tis_log import LOG

from consts.cgcs import FlavorSpec, ImageMetadata
from consts.cli_errs import CPUPolicyErr        # used by eval

from keywords import nova_helper, vm_helper, glance_helper, cinder_helper, check_helper, host_helper
from testfixtures.resource_mgmt import ResourceCleanup


@mark.parametrize(('flv_vcpus', 'flv_pol', 'img_pol', 'create_vol', 'expt_err'), [
    mark.p2((5, None, 'dedicated', True, None)),
    mark.p2((3, None, 'shared', False, None)),
    mark.p2((4, None, None, False, None)),
    mark.p3((4, 'dedicated', 'dedicated', True, None)),
    mark.p3((1, 'dedicated', None, False, None)),
    mark.p3((1, 'shared', 'shared', True, None)),
    mark.p3((2, 'shared', None, False, None)),
    mark.p1((3, 'dedicated', 'shared', True, None)),
    mark.p2((1, 'shared', 'dedicated', False, 'CPUPolicyErr.CONFLICT_FLV_IMG')),
])
def test_boot_vm_cpu_policy_image(flv_vcpus, flv_pol, img_pol, create_vol, expt_err):
    LOG.tc_step("Create flavor with {} vcpus".format(flv_vcpus))
    flavor_id = nova_helper.create_flavor(name='cpu_thread_image', vcpus=flv_vcpus)[1]
    ResourceCleanup.add('flavor', flavor_id)

    if flv_pol is not None:
        specs = {FlavorSpec.CPU_POLICY: flv_pol}

        LOG.tc_step("Set following extra specs: {}".format(specs))
        nova_helper.set_flavor_extra_specs(flavor_id, **specs)

    if img_pol is not None:
        image_meta = {ImageMetadata.CPU_POLICY: img_pol}
        LOG.tc_step("Create image with following metadata: {}".format(image_meta))
        image_id = glance_helper.create_image(name='cpu_thread_{}'.format(img_pol), **image_meta)[1]
        ResourceCleanup.add('image', image_id)
    else:
        image_id = glance_helper.get_image_id_from_name('cgcs-guest')

    if create_vol:
        LOG.tc_step("Create a volume from image")
        source_id = cinder_helper.create_volume(name='cpu_thr_img', image_id=image_id)[1]
        ResourceCleanup.add('volume', source_id)
        source = 'volume'
    else:
        source_id = image_id
        source = 'image'

    prev_cpus = host_helper.get_vcpus_for_computes(rtn_val='used_now')

    LOG.tc_step("Attempt to boot a vm with above flavor and {}".format(source))
    code, vm_id, msg, ignore = vm_helper.boot_vm(name='cpu_thread_image', flavor=flavor_id, source=source,
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

    check_helper.check_topology_of_vm(vm_id, vcpus=flv_vcpus, cpu_pol=expt_cpu_pol, prev_total_cpus=prev_cpus)

