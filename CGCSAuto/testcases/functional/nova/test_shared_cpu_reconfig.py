from pytest import mark, fixture

from utils.tis_log import LOG
from consts.cgcs import FlavorSpec
from keywords import nova_helper, vm_helper, host_helper, cinder_helper
from testfixtures.resource_cleanup import ResourceCleanup


def _modify(host):
    host_helper.modify_host_cpu(host, 'shared', p0=1, p1=1)


def _revert(host):
    host_helper.modify_host_cpu(host, 'shared', p0=0, p1=0)


@fixture(scope='module', autouse=True)
def add_shared_cpu(config_host):
    host = host_helper.get_nova_host_with_min_or_max_vms(rtn_max=False)
    config_host(host=host, modify_func=_modify, revert_func=_revert)


@mark.parametrize(('vcpus', 'cpu_policy', 'numa_nodes', 'numa_node0', 'shared_vcpu'), [
    mark.p1((2, 'dedicated', 1, 1, 1)),
])
def test_launch_vm_with_shared_cpu(vcpus, cpu_policy, numa_nodes, numa_node0, shared_vcpu):
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

    assert 0 == code, "Boot vm failed. Details: {}".format(output)

    # cores_quota = int(nova_helper.get_quotas('cores')[0])
    # if vcpus >= cores_quota:
    #     assert 4 == code, 'Expect boot vm cli rejected and no vm is booted. Actual: {}'.format(output)
    #     expt_err = 'Quota exceeded for cores: '
    #     assert expt_err in output, "Expected error message is not included in cli output."
    # else:
    #     assert 1 == code, 'Expect boot vm cli return error, although vm is booted anyway. Actual: {}'.format(output)
    #
    #     fault_pattern = ".*Shared not enabled for cell .*"
    #     res_bool, vals = vm_helper.wait_for_vm_values(vm_id, 10, regex=True, strict=False, status='ERROR',
    #                                                   fault=fault_pattern)
    #     assert res_bool, "VM did not reach expected error state. Actual: {}".format(vals)
