import re

from pytest import fixture, mark, skip

from utils import table_parser
from utils.tis_log import LOG
from consts.cgcs import FlavorSpec, InstanceTopology
from consts.cli_errs import NumaErr     # Do not remove
from keywords import nova_helper, vm_helper, system_helper, host_helper, network_helper
from testfixtures.fixture_resources import ResourceCleanup
from testfixtures.pre_checks_and_configs import check_numa_num      # Do not remove


########################################
# Test Set with NUMA node(s) Specified #
########################################

@mark.p3
@mark.parametrize(('vcpus', 'vswitch_affinity', 'numa_nodes', 'numa0', 'numa0_cpus', 'numa0_mem', 'numa1', 'numa1_cpus',
                   'numa1_mem', 'expt_err'), [
    (3, 'prefer', 2, 1, None, None, 0, None, None, 'NumaErr.FLV_UNDEVISIBLE'),
    (4, 'strict', 2, 0, 0, 512, 1, 1, None, 'NumaErr.FLV_CPU_OR_MEM_UNSPECIFIED'),
])
def test_flavor_setting_numa_negative(vcpus, vswitch_affinity, numa_nodes, numa0, numa0_cpus, numa0_mem,
                                      numa1, numa1_cpus, numa1_mem, expt_err):

    LOG.tc_step("Create a 1024ram flavor with {} vcpus".format(vcpus))
    name = 'vswitch_affinity_{}_1G_{}cpu'.format(vswitch_affinity, vcpus)
    flv_id = nova_helper.create_flavor(name=name, vcpus=vcpus, ram=1024, check_storage_backing=False)[1]
    ResourceCleanup.add('flavor', flv_id)

    specs = {FlavorSpec.CPU_POLICY: 'dedicated', FlavorSpec.NUMA_NODES: numa_nodes,
             FlavorSpec.VSWITCH_NUMA_AFFINITY: vswitch_affinity}
    tmp_dict = {FlavorSpec.NUMA_0: numa0,
                FlavorSpec.NUMA0_CPUS: numa0_cpus,
                FlavorSpec.NUMA0_MEM: numa0_mem,
                FlavorSpec.NUMA_1: numa1,
                FlavorSpec.NUMA1_CPUS: numa1_cpus,
                FlavorSpec.NUMA1_MEM: numa1_mem}

    for key, val in tmp_dict.items():
        if val is not None:
            specs[key] = val

    LOG.tc_step("Attempt to set following extra spec to flavor {} and ensure it's rejected: {}".format(flv_id, specs))
    code, output = nova_helper.set_flavor_extra_specs(flv_id, fail_ok=True, **specs)
    assert 1 == code, "Invalid extra spec is not rejected. Details: {}".format(output)
    assert eval(expt_err) in output, "Expected error message is not found"


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


@mark.p3
@mark.parametrize(('cpu_policy', 'numa_0', 'numa_1'), [
    ('dedicated', 1, 0),
    ('dedicated', 0, 1),
])
def test_2_nodes_set_guest_numa_node_value(flavor_2_nodes, cpu_policy, numa_0, numa_1):
    """
    Test set guest NUMA nodes values with 2 NUMA nodes.
    Args:
        flavor_2_nodes (str): id of a flavor with 2 numa nodes set in the extra spec
        cpu_policy (str): cpu policy to add to flavor
        numa_0 (int or str): cell id to assign to numa_node.0
        numa_1 (int or str): cell id to assign to numa_node.1

    Setup:
        - Create a flavor with number of numa nodes set to 2 in extra specs (module level)

    Test Steps:
        - Set cpu policy to given policy in flavor extra specs
        - Set guest numa nodes values in flavor extra specs and ensure it's set.

    Notes: Has to set both guest nodes in one cli. Otherwise cli will be rejected as expected.

    Teardown:
        - Delete created flavor (module level)

    """

    LOG.tc_step("Set flavor cpu_policy spec to {}.".format(cpu_policy))
    nova_helper.set_flavor_extra_specs(flavor=flavor_2_nodes, **{FlavorSpec.CPU_POLICY: cpu_policy})

    args = {FlavorSpec.NUMA_0: numa_0, FlavorSpec.NUMA_1: numa_1}
    LOG.tc_step("Set flavor numa_node spec(s) to {} and verify setting succeeded".format(args))
    nova_helper.set_flavor_extra_specs(flavor=flavor_2_nodes, **args)


@mark.parametrize(('cpu_policy', 'numa_0', 'numa_1'), [
    mark.p2(('dedicated', 1, 1)),
    mark.p2(('dedicated', 0, 0)),
])
def test_2_nodes_set_numa_node_values_reject(flavor_2_nodes, cpu_policy, numa_0, numa_1):
    LOG.tc_step("Set flavor cpu_policy spec to {}.".format(cpu_policy))
    nova_helper.set_flavor_extra_specs(flavor=flavor_2_nodes, **{FlavorSpec.CPU_POLICY: cpu_policy})

    args = {FlavorSpec.NUMA_0: numa_0, FlavorSpec.NUMA_1: numa_1}
    LOG.tc_step("Attempt set flavor numa_node spec(s) to {} and verify setting rejected".format(args))
    code, msg = nova_helper.set_flavor_extra_specs(flavor=flavor_2_nodes, fail_ok=True, **args)
    assert 1 == code


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


@mark.p3
@mark.parametrize('numa_node_spec', [
    {"hw:numa_node.2": 0},
    {"hw:numa_node.-1": 0},
    # {"hw:numa_node.0": 2},      # Cli accepted. Feature is under development to allow more than 0, 1 values
    {"hw:numa_node.0": '-1'},
])
def test_1_node_set_guest_numa_node_value_invalid(flavor_1_node, numa_node_spec):
    """
    Attempt to set guest NUMA node to invalid cell value, and ensure it's rejected.

    Args:
        flavor_1_node (str): id of flavor with NUMA nodes number set to 1 in extra specs
        numa_node_spec (dict): guest numa node spec to set

    Setup:
        - Create a flavor with number of numa nodes set to 1 in extra specs (module level)

    Test Steps:
        - Attempt to set guest NUMA node spec with invalid value and ensure it's rejected.

    Teardown:
        - Delete created flavor (module level)

    """

    LOG.tc_step("Attempt to set flavor numa_node spec(s) to {} and verify cli is rejected.".format(numa_node_spec))
    code, output = nova_helper.set_flavor_extra_specs(flavor=flavor_1_node, fail_ok=True, **numa_node_spec)
    assert code == 1, "Expect nova flavor-key set cli to be rejected. Actual: {}".format(output)


##########################################
# Test Unset with NUMA node(s) Specified #
##########################################

@fixture(scope='function')
def flavor_unset(request):
    """
    Create basic flavor with 2 vcpus and 1 numa node
    """
    flavor = nova_helper.create_flavor('test_unset_numa', vcpus=2)[1]

    def delete():
        nova_helper.delete_flavors(flavor)
    request.addfinalizer(delete)

    return flavor


@mark.p3
def test_1_node_unset_numa_nodes(flavor_unset):
    LOG.tc_step("Set number of numa nodes to 1 in extra specs")
    nova_helper.set_flavor_extra_specs(flavor_unset, **{FlavorSpec.NUMA_NODES: 1})

    LOG.tc_step("Set numa_node.0 spec.")
    nova_helper.set_flavor_extra_specs(flavor_unset, **{FlavorSpec.NUMA_0: 0})
    LOG.tc_step("Unset numa_node.0 spec and ensure it's successful.")
    nova_helper.unset_flavor_extra_specs(flavor_unset, FlavorSpec.NUMA_0)

    LOG.tc_step("Set numa_node.0 spec.")
    nova_helper.set_flavor_extra_specs(flavor_unset, **{FlavorSpec.NUMA_0: 0})
    LOG.tc_step("Unset numa_nodes spec and ensure it's successful.")
    nova_helper.unset_flavor_extra_specs(flavor_unset, FlavorSpec.NUMA_0)


@mark.p3
def test_2_nodes_unset_numa_nodes(flavor_unset):
    LOG.tc_step("Set number of numa nodes to 2 in extra specs")
    nova_helper.set_flavor_extra_specs(flavor_unset, **{FlavorSpec.NUMA_NODES: 2})

    LOG.tc_step("Set numa_node.0 and numa_node.1 specs.")
    nova_helper.set_flavor_extra_specs(flavor_unset, **{FlavorSpec.NUMA_0: 0, FlavorSpec.NUMA_1: 1})
    LOG.tc_step("Unset numa_node.0 and numa_node.1 specs and ensure it's successful.")
    nova_helper.unset_flavor_extra_specs(flavor_unset, [FlavorSpec.NUMA_0, FlavorSpec.NUMA_1])

    LOG.tc_step("Set numa_node.0 and numa_node.1 specs.")
    nova_helper.set_flavor_extra_specs(flavor_unset, **{FlavorSpec.NUMA_0: 1, FlavorSpec.NUMA_1: 0})
    LOG.tc_step("Unset numa_node.0, numa_node.1, and numa_nodes specs and ensure it's successful.")
    nova_helper.unset_flavor_extra_specs(flavor_unset, [FlavorSpec.NUMA_NODES, FlavorSpec.NUMA_0, FlavorSpec.NUMA_1])


@mark.p3
def test_2_nodes_unset_numa_nodes_reject(flavor_unset):
    """
    Attempt to unset hw:numa_nodes spec when hw:numa_node.1 is set, and ensure it's rejected.

    Args:
        flavor_unset (str): id of a flavor with 2 numa nodes set in the extra spec

    Setup:
        - Create a flavor with 2 vcpus and number of numa nodes set to 2 in extra specs (module level)

    Test Steps:
        - Set guest numa nodes values in flavor extra specs
        - Attempt to unset number of NUMA nodes spec (hw:numa_nodes) and ensure it's rejected.

    Teardown:
        - Delete created flavor (module level)

    """
    LOG.tc_step("Set number of numa nodes to 2 and guest numa nodes values in extra specs")
    nova_helper.set_flavor_extra_specs(flavor_unset,
                                       **{FlavorSpec.NUMA_NODES: 2, FlavorSpec.NUMA_0: 0, FlavorSpec.NUMA_1: 1})

    LOG.tc_step("Attempt to unset numa_nodes extra spec with guest numa node extra spec, and verify cli is rejected.")
    code, output = nova_helper.unset_flavor_extra_specs(flavor_2_nodes, fail_ok=True, extra_specs=FlavorSpec.NUMA_NODES,
                                                        check_first=False)
    assert code == 1, "Expect nova flavor-key unset cli to be rejected. Actual: {}".format(output)


####################################################
# Test Set/Unset with NUMA nodes unspecified Start #
####################################################

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


@mark.p3
def test_0_node_set_guest_numa_node_value_reject(flavor_0_node):
    """
    Test set numa_node.1 is rejected when number of NUMA nodes is not set in extra specs.

    Args:
        flavor_0_node (str): id of flavor with 1 vcpu and without specifying hw:numa_nodes spec.

    Setup:
        - Create a flavor with 1 vcpu and number of numa nodes unset in extra specs (module level)

    Test Steps:
        - Attempt to set guest NUMA node 1 (hw:numa_node.1) and ensure it's rejected.

    Teardown:
        - Delete created flavor (module level)

    """
    numa_node_spec_0 = {FlavorSpec.NUMA_1: 0}

    LOG.tc_step("Attempt to set guest numa node extra spec without numa_nodes extra spec, and verify cli is rejected.")
    code, output = nova_helper.set_flavor_extra_specs(flavor=flavor_0_node, fail_ok=True, **numa_node_spec_0)
    assert 1 == code, "Expect nova flavor-key set cli to be rejected. Actual: {}".format(output)


@mark.p3
def test_0_node_unset_numa_nodes_reject(flavor_0_node):
    LOG.tc_step("Attempt to unset numa nodes spec when it's not in the spec, and verify cli is rejected.")
    code, output = nova_helper.unset_flavor_extra_specs(flavor_0_node, FlavorSpec.NUMA_NODES, fail_ok=True,
                                                        check_first=False)
    assert 1 == code, "Expect nova flavor-key unset cli to be rejected. Actual: {}".format(output)


################################
# Test vm NUMA node(s) configs #
################################


@mark.parametrize(('vcpus', 'numa_nodes', 'numa_node0', 'numa_node1'), [
    mark.p2((2, 1, 0, None)),
    mark.nightly((2, 2, 1, 0)),
    mark.p2((1, 1, 1, None)),
])
def test_vm_numa_node_settings(vcpus, numa_nodes, numa_node0, numa_node1, check_numa_num, no_simplex):
    """
    Test NUMA nodes settings in flavor extra specs are successfully applied to a vm

    Args:
        vcpus (int): Number of vcpus to set when creating flavor
        numa_nodes (int): Number of NUMA nodes to set in flavor extra specs
        numa_node0 (int): node.0 value in flavor extra specs
        numa_node1 (int): node.1 value in flavor extra specs

    Test Steps:
        - Create a flavor with given number of vcpus specified
        - Add numa_nodes related extra specs
        - Boot a vm with flavor
        - Run vm-topology
        - Verify vcpus, numa nodes, cpulist for specific vm reflects the settings in flavor
        - Ensure that all virtual NICs are associated with guest virtual numa node 0 (tests TC5069)

    Teardown:
        - Delete created vm, volume, and flavor

    """
    if check_numa_num < numa_nodes:
        skip("Number of processors - {} is less than required numa nodes - {}".format(check_numa_num, numa_nodes))

    LOG.tc_step("Create flavor with {} vcpus".format(vcpus))
    flavor = nova_helper.create_flavor('numa_vm', vcpus=vcpus)[1]
    ResourceCleanup.add('flavor', flavor, scope='function')

    extra_specs = {FlavorSpec.CPU_POLICY: 'dedicated',
                   FlavorSpec.NUMA_NODES: numa_nodes,
                   FlavorSpec.NUMA_0: numa_node0
                   }
    if numa_node1 is not None:
        extra_specs[FlavorSpec.NUMA_1] = numa_node1

    LOG.tc_step("Set following extra specs for flavor {}: {}.".format(extra_specs, flavor))
    nova_helper.set_flavor_extra_specs(flavor, **extra_specs)

    LOG.tc_step("Boot vm with flavor {}.".format(flavor))
    vm_id = vm_helper.boot_vm(flavor=flavor, cleanup='function')[1]

    LOG.tc_step("Verify cpu info for vm {} via vm-topology.".format(vm_id))
    nova_tab, libvirt_tab = system_helper.get_vm_topology_tables('servers', 'libvirt')

    # Filter out the line for vm under test
    nova_tab = table_parser.filter_table(nova_tab, ID=vm_id)
    libvirt_tab = table_parser.filter_table(libvirt_tab, uuid=vm_id)

    instance_topology = table_parser.get_column(nova_tab, 'instance_topology')[0]
    cpulist = table_parser.get_column(libvirt_tab, 'cpulist')[0]
    if '-' in cpulist:
        cpulist = cpulist.split(sep='-')
        cpulist_len = int(cpulist[1]) - int(cpulist[0]) + 1
    else:
        cpulist_len = len(cpulist.split(sep=','))
    vcpus_libvirt = int(table_parser.get_column(libvirt_tab, 'vcpus')[0])
    nodelist = table_parser.get_column(libvirt_tab, 'nodelist')[0]

    if isinstance(instance_topology, str):
        instance_topology = [instance_topology]

    # Each numa node will have an entry for given instance, thus number of entries should be the same as number of
    # numa nodes for the vm
    assert numa_nodes == len(instance_topology), \
        "Number of numa node entries for vm {} is different than number of NUMA nodes set in flavor".format(vm_id)

    expected_node_vals = [int(val) for val in [numa_node0, numa_node1] if val is not None]
    actual_node_vals = []
    for actual_node_info in instance_topology:
        actual_node_val = int(re.findall(InstanceTopology.NODE, actual_node_info)[0])
        actual_node_vals.append(actual_node_val)

    assert expected_node_vals == actual_node_vals, \
        "Individual NUMA node value(s) for vm {} is different than numa_node setting in flavor".format(vm_id)

    assert vcpus == vcpus_libvirt, \
        "Number of vcpus for vm {} in libvirt view is different than what's set in flavor.".format(vm_id)

    assert vcpus == cpulist_len, \
        "Number of entries in cpulist for vm {} in libvirt view is different than number of vcpus set in flavor".format(
                vm_id)

    if '-' in nodelist:
        nodelist = nodelist.split(sep='-')
        nodelist_len = int(nodelist[1]) - int(nodelist[0]) + 1
    else:
        nodelist_len = 1 if nodelist else 0

    assert numa_nodes == nodelist_len, \
        "nodelist for vm {} in libvirt view does not match number of numa nodes set in flavor".format(vm_id)

    if system_helper.is_avs():
        # TC5069
        LOG.tc_step("Check via vshell that all vNICs are associated with the host NUMA node that guest numa0 maps to")
        host = nova_helper.get_vm_host(vm_id)
        actual_nics = network_helper.get_vm_nics(vm_id)
        with host_helper.ssh_to_host(host) as compute_ssh:
            for nic in actual_nics:
                port_id = list(nic.values())[0]['port_id']
                ports_tab = table_parser.table(compute_ssh.exec_cmd("vshell port-show {}".format(port_id),
                                                                    fail_ok=False)[1])
                socket_id = int(table_parser.get_value_two_col_table(ports_tab, field='socket-id'))
                assert socket_id == numa_node0, "NIC is not associated with numa-node0"
