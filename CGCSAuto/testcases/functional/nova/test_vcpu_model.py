import re
from pytest import fixture, mark

from utils.tis_log import LOG
from consts.cgcs import FlavorSpec, ImageMetadata, GuestImages
from consts.cli_errs import VCPUSchedulerErr
from keywords import nova_helper, vm_helper, host_helper, cinder_helper, glance_helper
from testfixtures.fixture_resources import ResourceCleanup


@mark.parametrize(('flv_model', 'img_model', 'boot_source', 'error'), [
    ('Conroe', 'Nehalem', 'volume', 'error'),
    ('Penryn', 'Westmere', 'image', 'error'),
    ('Broadwell-noTSX', 'Broadwell', 'image', 'error'),
    ('SandyBridge', 'Passthrough', 'volume', 'error'),
    ('Passthrough', 'Haswell', 'image', 'error'),
    ('Passthrough', 'Passthrough', 'image', None),
    ('SandyBridge', 'SandyBridge', 'volume', None)
])
def test_vcpu_model_image_and_flavor(flv_model, img_model, boot_source, error):
    code, vm, msg = _boot_vm_vcpu_model(flv_model=flv_model, img_model=img_model, boot_source=boot_source)

    if error:
        # if boot_source == 'volume':
        #     assert 4 == code, "boot vm cli exit code is not 1. Actual fail reason: {}".format(msg)
        #     assert re.search('Block Device Mapping is Invalid', msg)
        # else:
        assert 1 == code
        vm_helper.wait_for_vm_values(vm, 10, regex=True, strict=False, status='ERROR', fail_ok=False)
        err = nova_helper.get_vm_fault_message(vm)

        expt_fault = VCPUSchedulerErr.CPU_MODEL_CONFLICT
        assert re.search(expt_fault, err), "Incorrect fault reported. Expected: {} Actual: {}" \
            .format(expt_fault, err)
    else:
        assert 0 == code, "Boot vm failed when cpu model in flavor and image both set to: {}".format(flv_model)
        check_vm_cpu_model(vm_id=vm, vcpu_model=flv_model)


def _boot_vm_vcpu_model(flv_model, img_model, boot_source):
    LOG.tc_step("Attempt to launch vm from {} with image vcpu model metadata: {}; flavor vcpu model extra spec: {}".
                format(boot_source, img_model, flv_model))

    flv_id = nova_helper.create_flavor(name='vcpu_{}'.format(flv_model))[1]
    ResourceCleanup.add('flavor', flv_id)
    if flv_model:
        nova_helper.set_flavor_extra_specs(flavor=flv_id,  **{FlavorSpec.VCPU_MODEL: flv_model})

    if img_model:
        image_id = glance_helper.create_image(name='vcpu_{}'.format(img_model),
                                              **{ImageMetadata.CPU_MODEL: img_model})[1]
        ResourceCleanup.add('image', image_id)
    else:
        image_id = glance_helper.get_guest_image(guest_os=GuestImages.DEFAULT_GUEST)

    if boot_source == 'image':
        source_id = image_id
    else:
        source_id = cinder_helper.create_volume(name='vcpu_model', image_id=image_id)[1]
        ResourceCleanup.add('volume', source_id)

    code, vm, msg, vol = vm_helper.boot_vm(name='vcpu_model', flavor=flv_id, source=boot_source, source_id=source_id,
                                           fail_ok=True, cleanup='function')
    return code, vm, msg


@mark.p2
@mark.parametrize(('vcpu_model', 'vcpu_source', 'boot_source'), [
    ('Conroe', 'flavor', 'volume'),
    ('Penryn', 'flavor', 'volume'),
    ('Nehalem', 'flavor', 'volume'),
    ('Westmere', 'flavor', 'volume'),
    ('SandyBridge', 'flavor', 'volume'),
    ('Haswell', 'flavor', 'volume'),
    ('Broadwell', 'flavor', 'volume'),
    ('Broadwell-noTSX', 'flavor', 'volume'),
    ('Passthrough', 'flavor', 'volume'),
    ('Passthrough', 'image', 'image'),
    ('Passthrough', 'image', 'volume'),
    ('SandyBridge', 'image', 'volume'),
])
def test_vm_vcpu_model(vcpu_model, vcpu_source, boot_source):
    """
    Test vcpu model specified in flavor will be applied to vm. In case host does not support specified vcpu model,
    proper error message should be displayed in nova show.

    Args:
        vcpu_model
        vcpu_source
        boot_source

    Setup:
        - Create a basic flavor and volume (module level)
    Test Steps:
        - Set flavor extra spec to given vcpu model
        - Boot a vm from volume using the flavor
        - Verify vcpu model specified in flavor is used by vm. Or proper error message is included if host does not
            support specified vcpu model.
    Teardown:
        - Delete created vm
        - Delete created volume and flavor (module level)

    """
    flv_model = vcpu_model if vcpu_source == 'flavor' else None
    img_model = vcpu_model if vcpu_source == 'image' else None
    code, vm, msg = _boot_vm_vcpu_model(flv_model=flv_model, img_model=img_model, boot_source=boot_source)

    if code != 0:
        LOG.tc_step("Check vm in error state due to vcpu model unsupported by hosts.")
        assert 1 == code, "boot vm cli exit code is not 1. Actual fail reason: {}".format(msg)

        expt_fault = VCPUSchedulerErr.CPU_MODEL_UNAVAIL
        res_bool, vals = vm_helper.wait_for_vm_values(vm, 10, regex=True, strict=False, status='ERROR')
        err = nova_helper.get_vm_nova_show_value(vm, field='fault')

        assert res_bool, "VM did not reach expected error state. Actual: {}".format(vals)
        assert re.search(expt_fault, err), "Incorrect fault reported. Expected: {} Actual: {}" \
            .format(expt_fault, err)
        return

    # System supports specified vcpu, continue to verify
    expt_arch = None
    if vcpu_model == 'Passthrough':
        host = nova_helper.get_vm_host(vm)
        expt_arch = host_helper.get_host_cpu_model(host)

    LOG.tc_step("Check vm is launched with expected vcpu model")
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm)
    check_vm_cpu_model(vm_id=vm, vcpu_model=vcpu_model, expt_arch=expt_arch)

    LOG.tc_step("Live (block) migrate vm and check {} vcpu model".format(vcpu_model))
    vm_helper.live_migrate_vm(vm_id=vm)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm)
    check_vm_cpu_model(vm, vcpu_model, expt_arch=expt_arch)

    LOG.tc_step("Cold migrate vm and check {} vcpu model".format(vcpu_model))
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm)
    vm_helper.cold_migrate_vm(vm_id=vm)
    check_vm_cpu_model(vm, vcpu_model, expt_arch=expt_arch)


def check_vm_cpu_model(vm_id, vcpu_model, expt_arch=None):
    if vcpu_model == 'Passthrough':
        pattern_ps = 'host'
        pattern_virsh = 'host-passthrough'
        virsh_tag = 'cpu'
        type_ = 'dict'
    else:
        virsh_tag = 'cpu/model'
        type_ = 'text'
        if vcpu_model == 'Haswell':
            pattern_ps = pattern_virsh = '(haswell|haswell\-notsx)'
        else:
            pattern_ps = pattern_virsh = vcpu_model.lower()

    LOG.info("Check vcpu model successfully applied to vm via ps aux and virsh dumpxml on vm host")
    host = nova_helper.get_vm_host(vm_id)
    inst_name = nova_helper.get_vm_instance_name(vm_id)
    with host_helper.ssh_to_host(host) as host_ssh:
        output_ps = host_ssh.exec_cmd("ps aux | grep --color='never' -i {}".format(vm_id), fail_ok=False)[1]
        output_virsh = host_helper.get_values_virsh_xmldump(inst_name, host_ssh, tag_paths=virsh_tag, target_type=type_)
        print("VIRSH CPU: {}".format(output_virsh))
        output_virsh = output_virsh[0]

    assert re.search('\s-cpu\s{}(\s|,)'.format(pattern_ps), output_ps.lower()), \
        'cpu_model {} not found for vm {}'.format(pattern_ps, vm_id)

    if vcpu_model == 'Passthrough':
        assert output_virsh['mode'] == 'host-passthrough', \
            'cpu mode is not passthrough in virsh for vm {}'.format(vm_id)

        LOG.info("Check cpu passthrough model from within the vm")
        vcpu_model = vm_helper.get_vcpu_model(vm_id)
        host_cpu_model = host_helper.get_host_cpu_model(host=host)
        assert host_cpu_model == vcpu_model, "VM cpu model is different than host cpu model with cpu passthrough"

        if expt_arch:
            assert expt_arch == vcpu_model, "VM cpu model changed. Original: {}. Current: {}".format(expt_arch,
                                                                                                     vcpu_model)
    else:
        assert re.search(pattern_virsh, output_virsh.lower()), \
            'cpu model {} is not found in virsh for vm {}'.format(pattern_virsh, vm_id)
