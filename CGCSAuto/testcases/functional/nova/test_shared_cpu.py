from pytest import fixture, mark

from utils.tis_log import LOG
from consts.cgcs import FlavorSpec
from keywords import nova_helper, vm_helper, host_helper, cinder_helper
from testfixtures.resource_cleanup import ResourceCleanup


@fixture(scope='module')
def flavor_64_vcpus(request):
    """
    Create basic flavor and volume to be used by test cases as test setup, at the beginning of the test module.
    Delete the created flavor and volume as test teardown, at the end of the test module.
    """
    flavor = nova_helper.create_flavor(name='shared_vcpus', vcpus=64)[1]
    nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.CPU_POLICY: 'dedicated'})

    ResourceCleanup.add('flavor', resource_id=flavor, scope='module')

    return flavor


@mark.p1
@mark.parametrize('vcpu_id', [
    0,
    2,
    63
])
def test_set_shared_vcpu_spec(flavor_64_vcpus, vcpu_id):
    nova_helper.set_flavor_extra_specs(flavor_64_vcpus, **{FlavorSpec.SHARED_VCPU: vcpu_id})


@mark.parametrize(('vcpus', 'cpu_policy', 'vcpu_id'),[
    mark.p2((4, 'shared', 3)),
    mark.p3((4, 'dedicated', 5)),
    mark.p3((4, 'dedicated', -1)),
    mark.p3((64, 'dedicated', 64)),
])
def test_set_shared_vcpu_spec_reject(cpu_policy, vcpus, vcpu_id):
    """
    Test set shared vcpu id to invalid value will be rejected.

    Args:
        cpu_policy (str): shared or dedicated
        vcpus (int): number of vcpus to set when creating flavor
        vcpu_id (int): vcpu id to attempt to set to

    Test Steps:
        - Create flavor with given number of vcpus
        - Set cpu_policy extra spec to given value
        - Attempt to set shared vcpu id to specific value (invalid value)
        - Ensure cli is rejected

    Teardown:
        - Delete created flavor

    """
    LOG.tc_step("Create flavor with {} vcpus, and set cpu_policy to {}".format(vcpus, cpu_policy))

    flavor = nova_helper.create_flavor(vcpus=vcpus)[1]
    ResourceCleanup.add('flavor', flavor, scope='function')
    nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.CPU_POLICY: cpu_policy})

    LOG.tc_step("Attempt to set vcpu_id spec to invalid value - {} and verify it's rejected.".format(vcpu_id))
    code, output = nova_helper.set_flavor_extra_specs(flavor, fail_ok=True, **{FlavorSpec.SHARED_VCPU: vcpu_id})

    error_msg = 'undefined'
    if cpu_policy == 'shared':
        error_msg = "ERROR (BadRequest): hw:wrs:shared_vcpu is only valid when hw:cpu_policy is 'dedicated'.  " \
                    "Either set an extra spec hw:cpu_policy to 'dedicated' or do not set hw:wrs:shared_vcpu."
    elif vcpu_id < 0:
        error_msg = 'ERROR (BadRequest): shared vcpu must be greater than or equal to 0'
    elif vcpu_id >= vcpus:
        error_msg = 'ERROR (BadRequest): shared vcpu must be less than flavor vcpus value'

    assert code == 1 and error_msg in output, "Set vcpu id cli should be rejected. Actual: {}".format(output)


@mark.parametrize(('vcpus', 'cpu_policy', 'numa_nodes', 'numa_node0', 'shared_vcpu'), [
    mark.p1((2, 'dedicated', 1, 1, 1)),
    mark.p1((3, 'dedicated', 1, 1, 0)),
    mark.p3((64, 'dedicated', 1, 1, 2)),
    mark.p3((64, 'dedicated', 1, 1, 63)),    # Assuming quota for cores for tenant under test is less than 63
])
def test_launch_vm_shared_cpu_setting_negative(vcpus, cpu_policy, numa_nodes, numa_node0, shared_vcpu):
    """
    Test boot vm cli returns error when system does not meet the shared cpu requirement(s) in given flavor

    Args:
        vcpus (int): number of vcpus to set when creating flavor
        cpu_policy (str): 'dedicated' or 'shared' to set in flavor extra specs
        numa_nodes (int): number of numa nodes to set in flavor extra specs
        numa_node0 (int): value for numa_node.0
        shared_vcpu (int):

    Test Steps:
        - Create flavor with given number of vcpus
        - Add specific cpu_policy, number of numa nodes, nume_node.0 , shared_vcpu values to flavor extra specs
        - Attempt to boot a vm with the flavor
        - Ensure proper error is returned

    Teardown:
        - Delete created vm if any (function)
        - Delete created volume if any (module)

    """
    flavor = nova_helper.create_flavor(vcpus=vcpus)[1]
    ResourceCleanup.add('flavor', flavor, scope='function')
    nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.CPU_POLICY: cpu_policy})
    nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.NUMA_NODES: numa_nodes, FlavorSpec.NUMA_0: numa_node0})
    nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.SHARED_VCPU: shared_vcpu})

    code, vm_id, output, vol_id = vm_helper.boot_vm(name='shared_cpu', flavor=flavor, fail_ok=True)
    if vm_id:
        ResourceCleanup.add('vm', vm_id, scope='function')
    if vol_id:
        ResourceCleanup.add('volume', vol_id, scope='module')

    cores_quota = int(nova_helper.get_quotas('cores')[0])
    if vcpus >= cores_quota:
        assert 4 == code, 'Expect boot vm cli rejected and no vm is booted. Actual: {}'.format(output)
        expt_err = 'Quota exceeded for cores: '
        assert expt_err in output, "Expected error message is not included in cli output."
    else:
        assert 1 == code, 'Expect boot vm cli return error, although vm is booted anyway. Actual: {}'.format(output)

        fault_pattern = ".*Shared not enabled for cell .*"
        res_bool, vals = vm_helper.wait_for_vm_values(vm_id, 10, regex=True, strict=False, status='ERROR',
                                                      fault=fault_pattern)
        assert res_bool, "VM did not reach expected error state. Actual: {}".format(vals)


@fixture(scope='module')
def basic_vm():
    vm_id = vm_helper.boot_vm()[1]
    ResourceCleanup.add('vm', vm_id, scope='module')
    return vm_id


@mark.parametrize(('vcpus', 'cpu_policy', 'shared_vcpu'), [
    mark.p1((2, 'dedicated', 1)),
])
def test_resize_vm_shared_cpu_negative(vcpus, cpu_policy, shared_vcpu, basic_vm):
    """
    Test resize request is rejected if system does not meet the shared_cpu requirement(s) in the flavor

    Args:
        vcpus (int): number of vcpus in flavor
        cpu_policy (str): cpu_policy in flavor extra specs
        shared_vcpu (int):
        basic_vm (str): id of a basic vm to attempt resize on

    Setup:
        - Boot a basic vm (module)

    Test Steps:
        - Create a flavor with given number of vcpus
        - Set extra specs for cpu_policy, shared_vcpu
        - Attempt to resize the basic vm with the flavor
        - Ensure cli is rejected and proper error returned

    Teardowns:
        - Delete created vm and volume (module)

    """
    LOG.tc_step("Create a flavor with {} vcpus. Set extra specs with: {} cpu_policy, {} shared_vcpu".format(
            vcpus, cpu_policy, shared_vcpu))
    flavor = nova_helper.create_flavor(vcpus=vcpus)[1]
    ResourceCleanup.add('flavor', flavor, scope='function')
    nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.CPU_POLICY: cpu_policy})
    nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.SHARED_VCPU: shared_vcpu})

    LOG.tc_step("Attempt to resize vm with invlid flavor, and verify resize request is rejected.")
    code, msg = vm_helper.resize_vm(basic_vm, flavor, fail_ok=True)
    assert code == 1 and 'No valid host found for resize' in msg
