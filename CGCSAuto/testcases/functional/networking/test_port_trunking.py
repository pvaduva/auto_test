from pytest import fixture, mark, skip

from utils.tis_log import LOG

from consts.cgcs import FlavorSpec, VMStatus, GuestImages
from consts.reasons import SkipReason
from consts.auth import Tenant
from keywords import vm_helper, nova_helper, network_helper, host_helper, check_helper, glance_helper, common
from testfixtures.fixture_resources import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


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
            tmp_list = []
            tmp_list.append(eth_name)
            tmp_list.append("{}".format(vlan))
            sub_if = '.'.join(tmp_list)
            vm_ssh.exec_sudo_cmd('ip link add link {} name {} type vlan id {}'.format(eth_name, sub_if,
                                                                                              vlan))
            vm_ssh.exec_sudo_cmd('dhclient {}'.format(sub_if))

        vm_ssh.exec_sudo_cmd('ip addr')


@mark.parametrize(('guest_os','vif_model'), [
    ('tis-centos-guest','avp'),
    ('tis-centos-guest', 'virtio'),
    ('tis-centos-guest', 'e1000')
])
def test_port_trunking(guest_os, vif_model):
    """
    Ping between two vms with virtio and avp vif models

    Test Steps:
        - Create networks
        - Create subnets
        - Create a parent port and subports
        - Create a truck with parent port and subports
        - boot VMS and verify connectivity


    Test Teardown:
        - Delete vms, ports, subnets, and networks created

    """
    network_names = ['network11', 'network12', 'network13']
    net_ids = []
    sub_nets = ["30.0.0.0/24", "30.0.1.0/24","30.0.2.0/24"]
    subnet_ids = []
    # parent ports and sub ports for trunk 1 and trunk 2
    trunk1_parent_port ='vrf10'
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
    for sub, network in zip(sub_nets,net_ids):
        subnet_ids.append(network_helper.create_subnet(net_id=network,cidr=sub,no_gateway=True)[1])
        ResourceCleanup.add('subnet', subnet_ids[-1])

    # for sub_id, network_id in zip(subnet_ids,net_ids):
    #    ResourceCleanup.add('network', network_id)
     #   ResourceCleanup.add('subnet', sub_id)

    # Create Trunks
    LOG.tc_step("Create Parent port for trunk 1")
    t1_parent_port_id = network_helper.create_port(net_ids[0], trunk1_parent_port)[1]
    ResourceCleanup.add('port', t1_parent_port_id)

    t1_parent_port_mac = network_helper.get_ports(rtn_val='mac_address',port_name=trunk1_parent_port)[0]

    LOG.tc_step("Create Subport with parent port mac to be used by trunk 1")
    t1_sub_port1_id = network_helper.create_port(net_ids[1], name=trunk1_subport_1,mac_addr=t1_parent_port_mac)[1]
    ResourceCleanup.add('port', t1_sub_port1_id)

    LOG.tc_step("Create Subport with parent port mac to be used by trunk 1")
    t1_sub_port2_id = network_helper.create_port(net_ids[2], name=trunk1_subport_2,mac_addr=t1_parent_port_mac)[1]
    ResourceCleanup.add('port', t1_sub_port2_id)

    t1_sub_ports = [{'port':t1_sub_port1_id,'segmentation-type': 'vlan','segmentation-id':segment_1},
                  {'port':t1_sub_port2_id,'segmentation-type': 'vlan','segmentation-id':segment_2}]

    LOG.tc_step("Create port trunk 1")
    trunk1_id = network_helper.create_trunk(t1_parent_port_id,name='trunk-1',sub_ports=t1_sub_ports)[1]
    ResourceCleanup.add('trunk', trunk1_id)

    LOG.tc_step("Boot a VM with mgmt net and trunk port")
    mgmt_net_id = network_helper.get_mgmt_net_id()
    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'}]
    nics.append({'port-id': t1_parent_port_id, 'vif-model': vif_model})
    LOG.tc_step("Boot a vm with created ports")
    vm_id = vm_helper.boot_vm(name='vm-with-trunk1-port', nics=nics, cleanup='function')[1]
    LOG.tc_step("Setup Vlan interfaces inside guest")
    _bring_up_vlan_interface(vm_id,'eth1',[segment_1])

    # Create second trunk port and vm
    LOG.tc_step("Create Parent port for trunk 2")
    t2_parent_port_id = network_helper.create_port(net_ids[0], trunk2_parent_port)[1]
    ResourceCleanup.add('port', t2_parent_port_id)
    t2_parent_port_mac = network_helper.get_ports(rtn_val='mac_address',port_name=trunk2_parent_port)[0]
    LOG.tc_step("Create Subport with parent port mac to be used by trunk 2")
    t2_sub_port1_id = network_helper.create_port(net_ids[1], name=trunk2_subport_1,mac_addr=t2_parent_port_mac)[1]
    ResourceCleanup.add('port', t2_sub_port1_id)
    LOG.tc_step("Create Subport with parent port mac to be used by trunk 2")
    t2_sub_port2_id = network_helper.create_port(net_ids[2], name=trunk2_subport_2,mac_addr=t2_parent_port_mac)[1]
    ResourceCleanup.add('port', t2_sub_port2_id)

    t2_sub_ports = [{'port':t2_sub_port1_id,'segmentation-type': 'vlan','segmentation-id':segment_1},
                  {'port':t2_sub_port2_id,'segmentation-type': 'vlan','segmentation-id':segment_2}]

    LOG.tc_step("Create port trunk 2")
    trunk2_id = network_helper.create_trunk(t2_parent_port_id,name='trunk-2',sub_ports=t2_sub_ports)[1]
    ResourceCleanup.add('trunk', trunk2_id)

    LOG.tc_step("Boot a VM with mgmt net and trunk port")
    mgmt_net_id = network_helper.get_mgmt_net_id()
    nics_2 = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'}]
    nics_2.append({'port-id': t2_parent_port_id, 'vif-model': vif_model})

    LOG.tc_step("Boot a vm with created ports")
    vm2_id = vm_helper.boot_vm(name='vm-with-trunk2-port', nics=nics_2, cleanup='function')[1]

    LOG.tc_step("Setup Vlan interfaces inside guest")
    _bring_up_vlan_interface(vm2_id,'eth1',[segment_1])

    # ping b/w 2 vms using the vlan interfaces
    eth_name='eth1.1'

    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        ip_addr = network_helper.get_ip_for_eth(eth_name=eth_name, ssh_client=vm_ssh)

    if ip_addr is not None:
        with vm_helper.ssh_to_vm_from_natbox(vm2_id) as vm2_ssh:
            LOG.tc_step("Ping on vlan interface from guest")
            ping = network_helper._ping_server(ip_addr, ssh_client=vm2_ssh, num_pings=20,
                                           fail_ok=True)[0]

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
            ping = network_helper._ping_server(ip_addr, ssh_client=vm2_ssh, num_pings=20,
                                       fail_ok=True)[0]