from pytest import fixture, mark

from utils.tis_log import LOG
from keywords import vm_helper, network_helper, nova_helper
from testfixtures.fixture_resources import ResourceCleanup


@fixture(scope='module', autouse=True)
def update_net_quota(request):
    network_quota = network_helper.get_quota('network')
    network_helper.update_quotas(network=network_quota + 6)

    def _revert_quota():
        network_helper.update_quotas(network=network_quota)
    request.addfinalizer(_revert_quota)


def _bring_up_vlan_interface(vm_id, eth_name, vlan_ids):
    """
    ip link set <dev> up, and dhclient <dev> to bring up the interface of last nic for given VM
    Args:
        vm_id (str): VM to configure the vlan interface
        eth_name (str): eth interface name to add the vlan if
        vlan_ids (list): list of vlan ids to add
    """
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        for vlan in vlan_ids:
            tmp_list = [eth_name, str(vlan)]
            sub_if = '.'.join(tmp_list)
            vm_ssh.exec_sudo_cmd('ip link add link {} name {} type vlan id {}'.format(eth_name, sub_if, vlan))
            vm_ssh.exec_sudo_cmd('dhclient {}'.format(sub_if))

        vm_ssh.exec_sudo_cmd('ip addr')


@mark.parametrize('vif_model', [
    'avp'
])
def test_port_trunking(vif_model):
    """
    Port trunking feature test cases

    Test Steps:
        - Create networks
        - Create subnets
        - Create a parent port and subports
        - Create a truck with parent port and subports
        - Boot the first vm with the trunk
        - Create the second trunk without subport
        - Boot the second vm
        - Add suport to trunk
        - Configure vlan interfaces inside guests
        - Verify connectivity via vlan interfaces
        - Remove the subport from trunk and verify connectivity
        - Add the suport to trunk and verify connectivity
        - Do vm actions and verify connectivity


    Test Teardown:
        - Delete vms, ports, subnets, and networks created

    """
    network_names = ['network11', 'network12', 'network13']
    net_ids = []
    sub_nets = ["30.0.0.0/24", "30.0.1.0/24", "30.0.2.0/24"]
    subnet_ids = []
    # parent ports and sub ports for trunk 1 and trunk 2
    trunk1_parent_port = 'vrf10'
    trunk1_subport_1 = 'vrf11'
    trunk1_subport_2 = 'vrf12'

    trunk2_parent_port = 'host10'
    trunk2_subport_1 = 'host11'
    trunk2_subport_2 = 'host12'

    # vlan id for the subports
    segment_1 = 1
    segment_2 = 2

    LOG.tc_step("Create Networks to be used by trunk")
    for net in network_names:
        net_ids.append(network_helper.create_network(name=net)[1])
        ResourceCleanup.add('network', net_ids[-1])

    LOG.tc_step("Create Subnet on the Network Created")
    for sub, network in zip(sub_nets, net_ids):
        subnet_ids.append(network_helper.create_subnet(net_id=network, cidr=sub, no_gateway=True)[1])
        ResourceCleanup.add('subnet', subnet_ids[-1])

    # Create Trunks
    LOG.tc_step("Create Parent port for trunk 1")
    t1_parent_port_id = network_helper.create_port(net_ids[0], trunk1_parent_port, wrs_vif=vif_model)[1]
    ResourceCleanup.add('port', t1_parent_port_id)

    t1_parent_port_mac = network_helper.get_ports(rtn_val='mac_address', port_name=trunk1_parent_port)[0]

    LOG.tc_step("Create Subport with parent port mac to be used by trunk 1")
    t1_sub_port1_id = network_helper.create_port(net_ids[1], name=trunk1_subport_1, mac_addr=t1_parent_port_mac,
                                                 wrs_vif=vif_model)[1]
    ResourceCleanup.add('port', t1_sub_port1_id)

    LOG.tc_step("Create Subport with parent port mac to be used by trunk 1")
    t1_sub_port2_id = network_helper.create_port(net_ids[2], name=trunk1_subport_2, mac_addr=t1_parent_port_mac,
                                                 wrs_vif=vif_model)[1]
    ResourceCleanup.add('port', t1_sub_port2_id)

    t1_sub_ports = [{'port': t1_sub_port1_id, 'segmentation-type': 'vlan', 'segmentation-id': segment_1},
                    {'port': t1_sub_port2_id, 'segmentation-type': 'vlan', 'segmentation-id': segment_2}]

    LOG.tc_step("Create port trunk 1")
    trunk1_id = network_helper.create_trunk(t1_parent_port_id, name='trunk-1', sub_ports=t1_sub_ports)[1]
    ResourceCleanup.add('trunk', trunk1_id)

    LOG.tc_step("Boot a VM with mgmt net and trunk port")
    mgmt_net_id = network_helper.get_mgmt_net_id()
    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'}, {'port-id': t1_parent_port_id}]

    LOG.tc_step("Boot a vm with created ports")
    vm_id = vm_helper.boot_vm(name='vm-with-trunk1-port', nics=nics, cleanup='function')[1]
    LOG.tc_step("Setup Vlan interfaces inside guest")
    _bring_up_vlan_interface(vm_id, 'eth1', [segment_1])

    # Create second trunk port  with out the subports and vm
    LOG.tc_step("Create Parent port for trunk 2")
    t2_parent_port_id = network_helper.create_port(net_ids[0], trunk2_parent_port, wrs_vif=vif_model)[1]
    ResourceCleanup.add('port', t2_parent_port_id)
    t2_parent_port_mac = network_helper.get_ports(rtn_val='mac_address', port_name=trunk2_parent_port)[0]
    LOG.tc_step("Create Subport with parent port mac to be used by trunk 2")
    t2_sub_port1_id = network_helper.create_port(net_ids[1], name=trunk2_subport_1, mac_addr=t2_parent_port_mac,
                                                 wrs_vif=vif_model)[1]
    ResourceCleanup.add('port', t2_sub_port1_id)
    LOG.tc_step("Create Subport with parent port mac to be used by trunk 2")
    t2_sub_port2_id = network_helper.create_port(net_ids[2], name=trunk2_subport_2, mac_addr=t2_parent_port_mac,
                                                 wrs_vif=vif_model)[1]
    ResourceCleanup.add('port', t2_sub_port2_id)

    t2_sub_ports = [{'port': t2_sub_port1_id, 'segmentation-type': 'vlan', 'segmentation-id': segment_1},
                    {'port': t2_sub_port2_id, 'segmentation-type': 'vlan', 'segmentation-id': segment_2}]

    LOG.tc_step("Create port trunk 2")
    trunk2_id = network_helper.create_trunk(t2_parent_port_id, name='trunk-2')[1]
    ResourceCleanup.add('trunk', trunk2_id)

    LOG.tc_step("Boot a VM with mgmt net and trunk port")
    mgmt_net_id = network_helper.get_mgmt_net_id()
    nics_2 = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'}, {'port-id': t2_parent_port_id}]

    LOG.tc_step("Boot a vm with created ports")
    vm2_id = vm_helper.boot_vm(name='vm-with-trunk2-port', nics=nics_2, cleanup='function')[1]

    LOG.tc_step("Add the sub ports to the second truck")
    network_helper.add_trunk_subports(trunk2_id, sub_ports=t2_sub_ports)

    LOG.tc_step("Setup Vlan interfaces inside guest")
    _bring_up_vlan_interface(vm2_id, 'eth1', [segment_1])

    # ping b/w 2 vms using the vlan interfaces
    eth_name = 'eth1.1'

    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        ip_addr = network_helper.get_ip_for_eth(eth_name=eth_name, ssh_client=vm_ssh)

    if ip_addr:
        with vm_helper.ssh_to_vm_from_natbox(vm2_id) as vm2_ssh:
            LOG.tc_step("Ping on vlan interface from guest")
            network_helper.ping_server(ip_addr, ssh_client=vm2_ssh, num_pings=20, fail_ok=False)

    # unset the subport on trunk_1 and try the ping (it will fail)
    LOG.tc_step(" Removing a subport from trunk and ping on vlan interface inside guest")
    ret_code_10 = network_helper.remove_trunk_subports(trunk1_id, sub_ports=[t1_sub_port1_id])[0]
    assert ret_code_10 == 0, "Subports not removed as expected."

    with vm_helper.ssh_to_vm_from_natbox(vm2_id) as vm2_ssh:
        LOG.tc_step("Ping on vlan interface from guest")
        ping = network_helper.ping_server(ip_addr, ssh_client=vm2_ssh, num_pings=20, fail_ok=True)[0]
        assert ping == 100, "Ping did not fail as expected."

    # set the subport on trunk_1 and try the ping (it will work)
    LOG.tc_step(" Add back the subport to trunk and ping on vlan interface inside guest")
    t1_sub_port = [{'port': t1_sub_port1_id, 'segmentation-type': 'vlan', 'segmentation-id': segment_1}]
    network_helper.add_trunk_subports(trunk1_id, sub_ports=t1_sub_port)

    with vm_helper.ssh_to_vm_from_natbox(vm2_id) as vm2_ssh:
        LOG.tc_step("Ping on vlan interface from guest")
        network_helper.ping_server(ip_addr, ssh_client=vm2_ssh, num_pings=20, fail_ok=False)

    # VM operation and ping
    for vm_actions in [['pause', 'unpause'], ['suspend', 'resume'], ['live_migrate'], ['cold_migrate']]:

        LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm2_id, vm_actions))
        for action in vm_actions:
            vm_helper.perform_action_on_vm(vm2_id, action=action)

        LOG.tc_step("Ping vm from natbox")
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

        LOG.tc_step("Verify ping from base_vm to vm_under_test over management networks still works "
                    "after {}".format(vm_actions))
        vm_helper.ping_vms_from_vm(to_vms=vm_id, from_vm=vm2_id, net_types=['mgmt'])

        if vm_actions[0] == 'cold_migrate':
            LOG.tc_step("Setup Vlan interfaces inside guest")
            _bring_up_vlan_interface(vm2_id, 'eth1', [segment_1])

        with vm_helper.ssh_to_vm_from_natbox(vm2_id) as vm2_ssh:
            LOG.tc_step("Ping on vlan interface from guest after action {}".format(vm_actions))
            network_helper.ping_server(ip_addr, ssh_client=vm2_ssh, num_pings=20, fail_ok=False)

        vm_host = nova_helper.get_vm_host(vm2_id)

        vm_on_target_host = nova_helper.get_vms_on_hypervisor(vm_host)

    LOG.tc_step("Reboot VMs host {} and ensure vms are evacuated to other host".format(vm_host))
    vm_helper.evacuate_vms(host=vm_host, vms_to_check=vm2_id, ping_vms=True)

    for vm_id_on_target_host in vm_on_target_host:
        LOG.tc_step("Setup Vlan interfaces inside guest")
        _bring_up_vlan_interface(vm_id_on_target_host, 'eth1', [segment_1])

    with vm_helper.ssh_to_vm_from_natbox(vm2_id) as vm2_ssh:
        LOG.tc_step("Ping on vlan interface from guest after evacuation")
        network_helper.ping_server(ip_addr, ssh_client=vm2_ssh, num_pings=20, fail_ok=False)

    # Delete a trunk port used by the VM:
    code = network_helper.delete_trunk(trunk_id=trunk1_id)[0]
    assert code == 0, "Failed to delete port trunk"


def _test_port_trunking_basic():
    """
    Port trunking feature test cases

    Test Steps:
        - Create networks
        - Create subnets
        - Create a parent port and subports
        - Create a trunk with parent port and subports
        - Add a sub-port with existing vlan id
        - Add a sub-port with out of range vlan id
        - Delete a port that is used by the Trunk


    Test Teardown:
        - Delete vms, ports, subnets, and networks created
    """
    network_names = ['network21', 'network22', 'network23']
    net_ids = []
    sub_nets = ["40.0.0.0/24", "40.0.1.0/24", "40.0.2.0/24"]
    subnet_ids = []
    # parent ports and sub ports for trunk 1 and trunk 2
    trunk1_parent_port = 'vrf20'
    trunk1_subport_1 = 'vrf21'
    trunk1_subport_2 = 'vrf22'
    trunk1_subport_3 = 'vrf23'

    # vlan id for the subports
    segment_1 = 1
    segment_2 = 2

    LOG.tc_step("Create Networks to be used by trunk")
    for net in network_names:
        net_ids.append(network_helper.create_network(name=net)[1])
        ResourceCleanup.add('network', net_ids[-1])

    LOG.tc_step("Create Subnet on the Network Created")
    for sub, network in zip(sub_nets, net_ids):
        subnet_ids.append(network_helper.create_subnet(net_id=network, cidr=sub, no_gateway=True)[1])
        ResourceCleanup.add('subnet', subnet_ids[-1])

    # Create Trunks
    LOG.tc_step("Create Parent port for trunk 1")
    t1_parent_port_id = network_helper.create_port(net_ids[0], trunk1_parent_port)[1]
    ResourceCleanup.add('port', t1_parent_port_id)

    t1_parent_port_mac = network_helper.get_ports(rtn_val='mac_address', port_name=trunk1_parent_port)[0]

    LOG.tc_step("Create Subport with parent port mac to be used by trunk 1")
    t1_sub_port1_id = network_helper.create_port(net_ids[1], name=trunk1_subport_1, mac_addr=t1_parent_port_mac)[1]
    ResourceCleanup.add('port', t1_sub_port1_id)

    LOG.tc_step("Create Subport with parent port mac to be used by trunk 1")
    t1_sub_port2_id = network_helper.create_port(net_ids[2], name=trunk1_subport_2, mac_addr=t1_parent_port_mac)[1]
    ResourceCleanup.add('port', t1_sub_port2_id)

    LOG.tc_step("Create Subport with parent port mac to be used by trunk 1")
    t1_sub_port3_id = network_helper.create_port(net_ids[2], name=trunk1_subport_3)[1]
    ResourceCleanup.add('port', t1_sub_port3_id)

    t1_sub_ports = [{'port': t1_sub_port1_id, 'segmentation-type': 'vlan', 'segmentation-id': segment_1},
                    {'port': t1_sub_port2_id, 'segmentation-type': 'vlan', 'segmentation-id': segment_2}]

    LOG.tc_step("Create port trunk 1")
    trunk1_id = network_helper.create_trunk(t1_parent_port_id, name='trunk-1', sub_ports=t1_sub_ports)[1]
    ResourceCleanup.add('trunk', trunk1_id)

    LOG.tc_step("Attempt to add a port with same segment id and verify it's rejected")
    t1_sub_port2 = [{'port': t1_sub_port3_id, 'segmentation-type': 'vlan', 'segmentation-id': segment_1}]
    ret_code = network_helper.add_trunk_subports(trunk1_id, t1_sub_port2, fail_ok=True)[0]
    assert ret_code == 1, "Subport addition with the same vlan id is not rejected."

    LOG.tc_step("Attempt to add subport with out of range vlan id, and verify it's rejected")
    out_of_range_id = 5000
    t1_sub_port3 = [{'port': t1_sub_port3_id, 'segmentation-type': 'vlan', 'segmentation-id': out_of_range_id}]
    ret_code_2 = network_helper.add_trunk_subports(trunk1_id, t1_sub_port3, fail_ok=True)[0]
    assert ret_code_2 == 1, "Subport addition with out of range vlan id is not rejected."

    LOG.tc_step("Attempt to delete a port that is used by the trunk, and verify it's rejected")
    ret_code_3 = network_helper.delete_port(port_id=t1_sub_port1_id, fail_ok=True)[0]
    assert ret_code_3 == 1, "Port that is part of the trunk deletion is not rejected."
