import re
from pytest import fixture, mark, skip

from utils.tis_log import LOG
from consts.reasons import SkipReason
from consts.cgcs import VMStatus
from consts.cgcs import FlavorSpec, ImageMetadata, GuestImages
from consts.cli_errs import VCPUSchedulerErr

from keywords import nova_helper, vm_helper, host_helper, cinder_helper, glance_helper, check_helper
from testfixtures.fixture_resources import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


@mark.parametrize(('flv_model', 'img_model', 'boot_source', 'error'), [
    #('Conroe', 'Nehalem', 'volume', 'error'),
    #('Penryn', 'Westmere', 'image', 'error'),
    #('Broadwell-noTSX', 'Broadwell', 'image', 'error'),
    #('SandyBridge', 'Passthrough', 'volume', 'error'),
    #('Passthrough', 'Haswell', 'image', 'error'),
    ('Passthrough', 'Passthrough', 'image', None),
    ('SandyBridge', 'SandyBridge', 'volume', None)
])
def test_vcpu_model_flavor_and_image(flv_model, img_model, boot_source, error):
    """
    Test when vcpu model is set in both flavor and image
    Args:
        flv_model (str): vcpu model flavor extra spec setting
        img_model (str): vcpu model metadata in image
        boot_source (str): launch vm from image or volume
        error (str|None): whether an error is expected with given flavor/image vcpu settings

    Test steps:
        - Create a flavor and set vcpu model spec as specified
        - Create an image and set image metadata as specified
        - Launch a vm from image/volume using above flavor and image
        - If error is specified, check cpu model conflict error is displayed in nova show
        - Otherwise check vm is launched successfully and expected cpu model is used

    """
    code, vm, msg = _boot_vm_vcpu_model(flv_model=flv_model, img_model=img_model, boot_source=boot_source)

    if error:
        assert 1 == code
        vm_helper.wait_for_vm_values(vm, 10, regex=True, strict=False, status='ERROR', fail_ok=False)
        err = nova_helper.get_vm_fault_message(vm)

        expt_fault = VCPUSchedulerErr.CPU_MODEL_CONFLICT
        assert re.search(expt_fault, err), "Incorrect fault reported. Expected: {} Actual: {}" \
            .format(expt_fault, err)
    else:
        assert 0 == code, "Boot vm failed when cpu model in flavor and image both set to: {}".format(flv_model)
        check_vm_cpu_model(vm_id=vm, vcpu_model=flv_model)


def _boot_vm_vcpu_model(flv_model, img_model, boot_source, avail_zone=None, vm_host=None):
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
                                           fail_ok=True, cleanup='function', avail_zone=avail_zone, vm_host=vm_host)
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

    Test Steps:
        - Set flavor extra spec or image metadata with given vcpu model
        - Boot a vm from volume/image
        - If vcpu model is supported by host,
            - Check vcpu model specified in flavor/image is used by vm via virsh, ps aux (and /proc/cpuinfo)
            - Live migrate vm and check vcpu model again
            - Cold migrate vm and check vcpu model again
        - If vcpu model is not supported by host, check proper error message is included if host does not
            support specified vcpu model.
    Teardown:
        - Delete created vm, volume, image, flavor

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
    elif vcpu_model:
        virsh_tag = 'cpu/model'
        type_ = 'text'
        if vcpu_model == 'Haswell':
            pattern_ps = pattern_virsh = '(haswell|haswell\-notsx)'
        else:
            pattern_ps = pattern_virsh = vcpu_model.lower()
    else:
        # vcpu model is not set
        pattern_ps = None
        pattern_virsh = None
        virsh_tag = 'cpu'
        type_ = 'dict'

    LOG.info("Check vcpu model successfully applied to vm via ps aux and virsh dumpxml on vm host")
    host = nova_helper.get_vm_host(vm_id)
    inst_name = nova_helper.get_vm_instance_name(vm_id)
    with host_helper.ssh_to_host(host) as host_ssh:
        output_ps = host_ssh.exec_cmd("ps aux | grep --color='never' -i {}".format(vm_id), fail_ok=False)[1]
        output_virsh = host_helper.get_values_virsh_xmldump(inst_name, host_ssh, tag_paths=virsh_tag, target_type=type_)
        output_virsh = output_virsh[0]

    if vcpu_model:
        assert re.search('\s-cpu\s{}(\s|,)'.format(pattern_ps), output_ps.lower()), \
            'cpu_model {} not found for vm {}'.format(pattern_ps, vm_id)
    else:
        assert '-cpu' not in output_ps, "cpu model is specified in ps aux"

    if vcpu_model == 'Passthrough':
        assert output_virsh['mode'] == 'host-passthrough', \
            'cpu mode is not passthrough in virsh for vm {}'.format(vm_id)

        LOG.info("Check cpu passthrough model from within the vm")
        vm_vcpu_model = vm_helper.get_vcpu_model(vm_id)
        host_cpu_model = host_helper.get_host_cpu_model(host=host)
        assert host_cpu_model == vm_vcpu_model, "VM cpu model is different than host cpu model with cpu passthrough"

        if expt_arch:
            assert expt_arch == vm_vcpu_model, "VM cpu model changed. Original: {}. Current: {}".\
                format(expt_arch, vcpu_model)
    elif vcpu_model:
        assert re.search(pattern_virsh, output_virsh.lower()), \
            'cpu model {} is not found in virsh for vm {}'.format(pattern_virsh, vm_id)

    else:
        assert output_virsh == {}, "Virsh cpu output: {}".format(output_virsh)
        vm_vcpu_model = vm_helper.get_vcpu_model(vm_id)
        assert 'QEMU Virtual CPU' in vm_vcpu_model, "vCPU model is not QEMU Virtual CPU when unspecified"


@mark.parametrize(('source_model', 'dest_model'), [
    ('Nehalem', 'Passthrough'),
    ('Passthrough', 'Nehalem'),
    ('Passthrough', None),
    ('Passthrough', 'Passthrough')
])
def test_vcpu_model_resize(source_model, dest_model):
    """

    Args:
        source_model:
        dest_model:

    Test Steps:
        - Create a source flavor with 4G root disk and vcpu model extra spec as specified in source_model
        - Create a dest flavor with 5G root disk and vcpu model extra spec as specified in dest_model
        - Launch a vm from image with source flavor
        - Check vcpu_model is successfully applied
        - Resize the vm with dest flavor
        - Check new vcpu_model is successfully applied

    Teardown:
        - Delete created vm, image, flavors

    """
    LOG.tc_step("Create a source flavor with 4G root disk and vcpu model extra spec: {}".format(source_model))
    source_flv = _create_flavor_vcpu_model(vcpu_model=source_model, root_disk_size=4)

    LOG.tc_step("Create a destination flavor with 5G root disk and vcpu model extra spec: {}".format(source_model))
    dest_flv = _create_flavor_vcpu_model(vcpu_model=dest_model, root_disk_size=5)

    LOG.tc_step("Launch a vm from image with source flavor {}".format(source_flv))
    vm_id = vm_helper.boot_vm(flavor=source_flv, source='image', cleanup='function')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    check_vm_cpu_model(vm_id=vm_id, vcpu_model=source_model)

    expt_arch = None
    if source_model == dest_model == 'Passthrough':
        # Ensure vm resize to host with exact same cpu model when vcpu_model is passthrough
        host = nova_helper.get_vm_host(vm_id)
        expt_arch = host_helper.get_host_cpu_model(host)

    LOG.tc_step("Resize vm to destination flavor {}".format(dest_flv))
    vm_helper.resize_vm(vm_id, flavor_id=dest_flv)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    check_vm_cpu_model(vm_id, vcpu_model=dest_model, expt_arch=expt_arch)


def _create_flavor_vcpu_model(vcpu_model, root_disk_size=None):
    flv_id = nova_helper.create_flavor(name='vcpu_model_{}'.format(vcpu_model), root_disk=root_disk_size)[1]
    ResourceCleanup.add('flavor', flv_id)
    if vcpu_model:
        nova_helper.set_flavor_extra_specs(flavor=flv_id, **{FlavorSpec.VCPU_MODEL: vcpu_model})

    return flv_id


@mark.parametrize(('vcpu_model', 'thread_policy'), [
    ('Penryn', 'isolate'),
    ('Passthrough', 'require'),
])
def test_vcpu_model_and_thread_policy(vcpu_model, thread_policy):
    """
    Launch vm with vcpu model spec and cpu thread policy both set
    Args:
        vcpu_model (str):
        thread_policy (str):

    Test Steps:
        - create flavor with vcpu model and cpu thread extra specs set
        - boot vm from volume with above flavor
        - if no hyperthreaded host, check vm failed to schedule
        - otherwise check vcpu model and cpu thread policy both set as expected

    """
    name = '{}_{}'.format(vcpu_model, thread_policy)
    flv_id = nova_helper.create_flavor(name=name, vcpus=2)[1]
    ResourceCleanup.add('flavor', flv_id)
    nova_helper.set_flavor_extra_specs(flavor=flv_id, **{FlavorSpec.VCPU_MODEL: vcpu_model,
                                                         FlavorSpec.CPU_POLICY: 'dedicated',
                                                         FlavorSpec.CPU_THREAD_POLICY: thread_policy})

    code, vm, msg, vol = vm_helper.boot_vm(name=name, flavor=flv_id, fail_ok=True, cleanup='function')
    ht_hosts = host_helper.get_hypersvisors_with_config(hyperthreaded=True, up_only=True)
    if thread_policy == 'require' and not ht_hosts:
        assert 1 == code

    else:
        assert 0 == code, "VM is not launched successfully"
        check_vm_cpu_model(vm_id=vm, vcpu_model=vcpu_model)
        vm_host = nova_helper.get_vm_host(vm)
        check_helper._check_vm_topology_via_vm_topology(vm_id=vm, vcpus=2, cpu_pol='dedicated',
                                                        cpu_thr_pol=thread_policy, numa_num=1, vm_host=vm_host)


def test_vcpu_model_evacuation(add_admin_role_func):
    """
    Launch vm with vcpu model spec set

    Skip if:
        - lab has < 2 hosts


    Test Steps:
        - boots vm on a host with specified cpu model
        - wait for it to be pingable from natbox
        - Run "cat /proc/cpuinfo" in guest and check it got the right model
        - sudo reboot -f on vm host
        - Ensure evacuation for vm is successful (vm host changed, active state, pingable from NatBox)

    Teardown:
            - Delete created vms
            - Remove admin role from primary tenant (module)
    """

    # hosts = host_helper.get_hosts_by_storage_aggregate()
    # if len(hosts) < 2:
    #    skip(SkipReason.LESS_THAN_TWO_HOSTS_WITH_BACKING.format(''))

    newest_cpu_found = False

    working_vcpu_model_list = ["Skylake-Client", "Broadwell", "Broadwell-noTSX", "Haswell", "IvyBridge", "SandyBridge",
                               "Westmere", "Nehalem", "Penryn", "Conroe"]
    boot_source_list = ["image", "volume", "image"]
    vm_list = []

    LOG.tc_step("Find the newest vm that will be supported by at least 2 hosts and create vm")
    while (not newest_cpu_found) and working_vcpu_model_list:
        vcpu_model = working_vcpu_model_list[0]
        code, vm, msg = _boot_vm_vcpu_model(vcpu_model, vcpu_model, "volume", avail_zone='nova')

        # if _boot_vm is unsuccessful
        if code != 0:
            LOG.tc_step("Check vm in error state due to vcpu model unsupported by hosts.")
            assert 1 == code, "boot vm cli exit code is not 1. Actual fail reason: {}".format(msg)

            expt_fault = VCPUSchedulerErr.CPU_MODEL_UNAVAIL
            res_bool, vals = vm_helper.wait_for_vm_values(vm, 10, regex=True, strict=False, status='ERROR')
            err = nova_helper.get_vm_nova_show_value(vm, field='fault')
            del working_vcpu_model_list[0]

            assert res_bool, "VM did not reach expected error state. Actual: {}".format(vals)
            assert re.search(expt_fault, err), "Incorrect fault reported. Expected: {} Actual: {}" \
                .format(expt_fault, err)
        else:
            assert 0 == code, "Boot vm failed when cpu model in flavor and image both set to: {}".format(vcpu_model)
            target_host = nova_helper.get_vm_host(vm)
            LOG.tc_step("Ping vm from NatBox after successful creation")
            vm_helper.wait_for_vm_pingable_from_natbox(vm)
            check_vm_cpu_model(vm_id=vm, vcpu_model=vcpu_model)

            LOG.tc_step("Perform a live migration to see if another host can support the CPU model")
            exit_code = vm_helper.live_migrate_vm(vm)[0]

            LOG.tc_step("Check if migration is blocked or if live migrate fails")
            assert exit_code not in [3, 4, 5, 6], "Live migrate failed for reasons not related to vCPU support"

            ResourceCleanup.add('vm', vm)

            if exit_code in [1, 2]:
                del working_vcpu_model_list[0]
            else:
                assert exit_code == 0, "Live migrate failed. Unknown reasons"
                LOG.tc_step("Ping vm from NatBox after successful live migration")
                vm_helper.wait_for_vm_pingable_from_natbox(vm, timeout=30)

                host_found = True
                target_host = nova_helper.get_vm_host(vm)
                vm_list.append(vm)

    if not vm_list:
        assert False, "None of the tested vCPU models are supposed by the hosts"

    LOG.tc_step("create remaining vms")
    if len(working_vcpu_model_list) < 2:
        remaining_vcpu_list = []
    else:
        remaining_vcpu_list = working_vcpu_model_list[1:]
        if len(remaining_vcpu_list) > 2:
            remaining_vcpu_list = remaining_vcpu_list[:3]

    for cpu, boot in zip(remaining_vcpu_list, boot_source_list):
        vm = _boot_vm_vcpu_model(cpu, cpu, boot, avail_zone='nova', vm_host=target_host)[1]
        check_vm_cpu_model(vm_id=vm, vcpu_model=cpu)
        vm_helper.wait_for_vm_pingable_from_natbox(vm)
        vm_list.append(vm)

    code, vm, msg = _boot_vm_vcpu_model("Passthrough", "Passthrough", "volume", avail_zone='nova', vm_host=target_host)
    vm_helper.wait_for_vm_pingable_from_natbox(vm)
    expt_arch = host_helper.get_host_cpu_model(target_host)
    check_vm_cpu_model(vm_id=vm, vcpu_model="Passthrough", expt_arch=expt_arch)
    vm_list.append(vm)

    LOG.tc_step("Check all VMs are booted on {}".format(target_host))
    vms_on_host = nova_helper.get_vms_on_hypervisor(hostname=target_host)
    assert set(vm_list) <= set(vms_on_host), "VMs booted on host: {}. Current vms on host: {}".format(vm_list, vms_on_host)

    LOG.tc_step("Reboot target host {}".format(target_host))
    host_helper.reboot_hosts(target_host, wait_for_reboot_finish=False)
    HostsToRecover.add(target_host)

    LOG.tc_step("Wait for vms to reach ERROR or REBUILD state with best effort")
    vm_helper.wait_for_vms_values(vm_list, values=[VMStatus.ERROR, VMStatus.REBUILD], fail_ok=True, timeout=120)

    LOG.tc_step("Check vms are in Active state and moved to other host(s) after host reboot")
    res, active_vms, inactive_vms = vm_helper.wait_for_vms_values(vms=vm_list, values=VMStatus.ACTIVE, timeout=600)

    vms_host_err = []
    for vm in vm_list:
        if nova_helper.get_vm_host(vm) == target_host:
            vms_host_err.append(vm)

    assert not vms_host_err, "Following VMs stayed on the same host {}: {}\nVMs did not reach Active state: {}". \
        format(target_host, vms_host_err, inactive_vms)

    assert not inactive_vms, "VMs did not reach Active state after evacuated to other host: {}".format(inactive_vms)

    LOG.tc_step("Check VMs are pingable from NatBox after evacuation")
    vm_helper.ping_vms_from_natbox(vm_list)

    LOG.tc_step("Check the vcpu models are still correct after transfer")
    non_passthru_vms = len(vm_list) - 3

    for vm, cpu in zip(vm_list[:non_passthru_vms], working_vcpu_model_list[:non_passthru_vms]):
        LOG.tc_step(vm)
        LOG.tc_step(cpu)
        check_vm_cpu_model(vm_id=vm, vcpu_model=cpu)

    host = nova_helper.get_vm_host(vm_list[non_passthru_vms])
    expt_arch = host_helper.get_host_cpu_model(host)
    check_vm_cpu_model(vm_id=vm_list[non_passthru_vms], vcpu_model="Passthrough", expt_arch=expt_arch)


def test_vmx_flag(add_admin_role_func):
    """
    Test that flavor creation fails and sends a human-readable error message if a flavor with >128 vCPUs is attempted
    to be created

    Test Steps:
       - Create a new flavor with 129 vCPUs
       - Check that create_flavor returns an error exit code and a proper readable output message is generated
    """

    # Create a flavor with specs: hw:wrs:nested_vmx=True and extraspec hw:cpu_model=<compute host cpu model>

    host_cpu_model = "Passthrough"
    LOG.tc_step("Create flavor for vcpu model {}".format(host_cpu_model))
    flavor_id = nova_helper.create_flavor(fail_ok=False)[1]
    ResourceCleanup.add('flavor', flavor_id)

    LOG.tc_step("Set extra specs for flavor of vcpu model {}".format(host_cpu_model))
    extra_specs = {FlavorSpec.NESTED_VMX: True, FlavorSpec.VCPU_MODEL: host_cpu_model}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    LOG.tc_step("Create VM for vcpu model {}".format(host_cpu_model))
    code, vm, msg, vol = vm_helper.boot_vm(flavor=flavor_id, cleanup='function', fail_ok=False)
    ResourceCleanup.add('vm', vm)

    LOG.tc_step("Checking to see if 'vmx' is in /proc/cpuinfo")
    with vm_helper.ssh_to_vm_from_natbox(vm) as vm_ssh:
        out = vm_ssh.exec_cmd("grep vmx /proc/cpuinfo", fail_ok=False)[1]
        print(out)
        assert out, "vmx flag not set"
