from pytest import fixture, mark

from utils.tis_log import LOG
from consts.cgcs import FlavorSpec
from keywords import nova_helper, vm_helper, host_helper, cinder_helper


@fixture(scope='module')
def flavor_2_nodes(request):
    """
    Create basic flavor with 2 vcpus
    """
    flavor = nova_helper.create_flavor('two_numa_nodes', vcpus=2)[1]
    nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.NUMA_NODES: 2})

    def delete():
        nova_helper.delete_flavors(flavor)
    request.addfinalizer(delete)

    return flavor


@mark.parametrize(('cpu_policy', 'numa_0', 'numa_1'), [
    ('dedicated', 1, 0),
    ('dedicated', 0, 1),
])
def test_2_nodes_set_guest_numa_node_value(flavor_2_nodes, cpu_policy, numa_0, numa_1):

    LOG.tc_step("Set flavor cpu_policy spec to {}.".format(cpu_policy))
    nova_helper.set_flavor_extra_specs(flavor=flavor_2_nodes, **{FlavorSpec.CPU_POLICY: cpu_policy})

    args = {FlavorSpec.NUMA_0: numa_0, FlavorSpec.NUMA_1: numa_1}
    LOG.tc_step("Set flavor numa_node spec(s) to {} and verify setting succeeded".format(args))
    nova_helper.set_flavor_extra_specs(flavor=flavor_2_nodes, fail_ok=True, **args)


@fixture(scope='module')
def flavor_1_node(request):
    """
    Create basic flavor with 2 vcpus and 1 numa node
    """
    flavor = nova_helper.create_flavor('one_numa_node', vcpus=2)[1]
    nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.NUMA_NODES: 1})

    def delete():
        nova_helper.delete_flavors(flavor)
    request.addfinalizer(delete)

    return flavor

@mark.parametrize('numa_node_spec', [
    {"hw:numa_node.2": 0},
    {"hw:numa_node.-1": 0},
    # {"hw:numa_node.0": 2},      # Cli accepted. Feature is under development to allow more than 0, 1 values
    {"hw:numa_node.0": '-1'},
])
def test_1_node_set_guest_numa_node_value_invalid(flavor_1_node, numa_node_spec):

    LOG.tc_step("Attempt to set flavor numa_node spec(s) to {} and verify cli is rejected.".format(numa_node_spec))
    code, output = nova_helper.set_flavor_extra_specs(flavor=flavor_1_node, fail_ok=True, **numa_node_spec)
    assert code == 1, "Expect nova flavor-key set cli to be rejected. Actual: {}".format(output)


@fixture(scope='module')
def flavor_0_node(request):
    """
    Create basic flavor with 2 vcpus and 1 numa node
    """
    flavor = nova_helper.create_flavor('no_numa_node', vcpus=1)[1]

    def delete():
        nova_helper.delete_flavors(flavor)
    request.addfinalizer(delete)

    return flavor


def test_0_node_set_guest_numa_node_value_reject(flavor_0_node):
    numa_node_spec_0 = {FlavorSpec.NUMA_1: 0}

    LOG.tc_step("Attempt to set guest numa node extra spec without numa_nodes extra spec, and verify cli is rejected.")
    code, output = nova_helper.set_flavor_extra_specs(flavor=flavor_0_node, fail_ok=True, **numa_node_spec_0)
    assert code == 1, "Expect nova flavor-key set cli to be rejected. Actual: {}".format(output)


def test_2_nodes_unset_numa_nodes_reject(flavor_2_nodes):
    numa_node_spec_2 = {FlavorSpec.NUMA_0: 0, FlavorSpec.NUMA_1: 1}
    LOG.tc_step("Attempt to unset numa_nodes extra spec with guest numa node extra spec, and verify cli is rejected.")
    nova_helper.set_flavor_extra_specs(flavor=flavor_2_nodes, **numa_node_spec_2)
    code, output = nova_helper.unset_flavor_extra_specs(flavor_2_nodes, FlavorSpec.NUMA_NODES, fail_ok=True)
    assert code == 1, "Expect nova flavor-key unset cli to be rejected. Actual: {}".format(output)