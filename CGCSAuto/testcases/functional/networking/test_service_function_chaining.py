import time
from pytest import fixture, mark, skip
from utils.tis_log import LOG
from utils.multi_thread import MThread, Events
from keywords import vm_helper, host_helper, network_helper, nova_helper
from testfixtures.fixture_resources import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


@fixture(scope='module')
def check_system():
    LOG.info("Getting host list")
    hypervisors = host_helper.get_up_hypervisors()
    if len(hypervisors) < 3:
        skip("Less than 3 hypervisors on system. Skip the test.")

    LOG.info("check if the lab has vxlan enabled network")
    providernets = network_helper.get_providernets(rtn_val='name', strict=True, type='vxlan')
    if not providernets:
        skip("Vxlan provider-net not configured")

    for pnet in providernets:
        internal_nets = network_helper.get_networks_on_providernet(providernet_id=pnet, strict=False, name='internal')
        if internal_nets:
            break
    else:
        skip('Internal nets are not configured with vxlan.')
    return hypervisors


@mark.parametrize(('protocol', 'nsh_aware', 'same_host', 'add_protocol', 'symmetric'), [
    ('icmp', 'nsh_aware', 'same_host', 'tcp', 'asymmetric'),
    ('tcp', 'nsh_unaware', 'diff_host', 'icmp', 'symmetric')
])
def test_robustness_service_function_chaining(protocol, nsh_aware, same_host, add_protocol, symmetric, check_system,
                                              add_admin_role_module):
    """
        Test Service Function Chaining

        Test Steps:
            - Check if the system is compatible
            - Boot the source VM, dest VM & SFC VM in same host or diff host based on <same_host: True or False>
            - Install necessary software and package inside guest for packet forwarding test
            - Create port pair using nsh_ware <True:False>
            - Create port pair group
            - Create SFC flow classifier using protocol <tcp:icmp:udp>
            - Create port Chain
            - Check packet forwarding from source to dest vm via SFC vm
            - Migrate VM by force_lock compute host
            - Check packet forwarding from source to dest vm via SFC vm
            - Create new flow classifier with new protocol (add_protocol)
            - Update port chain with new flow classifier
            - Check packet forwarding from source to dest vm via SFC vm with new classifier
            - Evacuate VM by rebooting compute host
            - Verify VM evacuated
            - Check packet forwarding from source to dest vm via SFC vm with new classifier

        Test Teardown:
            - Delete port chain, port pair group, port pair, flow classifier, vms, volumes created

    """
    nsh_aware = True if nsh_aware == 'nsh_aware' else False
    same_host = True if same_host == 'same_host' else False
    symmetric = True if symmetric == 'symmetric' else False

    LOG.tc_step("Check if the system is compatible to run this test")
    computes = check_system

    LOG.tc_step("Boot the VM in same host: {}".format(same_host))
    hosts_to_boot = [computes[0]] * 3 if same_host else computes[0:3]
    LOG.info("Boot the VM in following compute host 1:{}, 2:{}, 3:{}".format(hosts_to_boot[0], hosts_to_boot[1],
                                                                             hosts_to_boot[2]))

    LOG.tc_step("Boot the source and dest VM")
    vm_ids = []
    vm_ids, source_vm_id, dest_vm_id, internal_net_id, mgmt_net_id, mgmt_nic = _setup_vm(vm_ids, hosts_to_boot)
    vm_helper.ping_vms_from_vm(to_vms=source_vm_id, from_vm=dest_vm_id, net_types=['mgmt'], retry=10)

    LOG.tc_step("Boot the SFC VM")
    sfc_vm_ids = []
    sfc_vm_ids, sfc_vm_under_test, ingress_port_id, egress_port_id = _setup_sfc_vm(sfc_vm_ids, hosts_to_boot, mgmt_nic,
                                                                                   internal_net_id)
    vm_helper.ping_vms_from_vm(to_vms=source_vm_id, from_vm=sfc_vm_under_test, net_types=['mgmt'], retry=10)

    # if protocol != 'icmp':
    LOG.tc_step("Install software package nc in vm {} {}".format(source_vm_id, dest_vm_id))
    _install_sw_packages_in_vm(source_vm_id)
    _install_sw_packages_in_vm(dest_vm_id)

    LOG.tc_step("copy vxlan tool in sfc vm {}".format(sfc_vm_under_test))
    vm_helper.scp_to_vm_from_natbox(vm_id=sfc_vm_under_test, source_file='/home/cgcs/sfc/vxlan_tool.py',
                                    dest_file='/root/vxlan_tool.py')

    LOG.tc_step("Create port pair")
    port_pair_ids = []
    port_pair_id = _setup_port_pair(nsh_aware, ingress_port_id, egress_port_id)
    port_pair_ids.append(port_pair_id)

    LOG.tc_step("Create port pair group")
    port_pair_group_ids = []
    port_pair_group_id = _setup_port_pair_groups(port_pair_id)
    port_pair_group_ids.append(port_pair_group_id)

    name = 'sfc_flow_classifier'
    LOG.tc_step("Create flow classifier:{}".format(name))
    flow_classifier, dest_vm_internal_net_ip = _setup_flow_classifier(name, source_vm_id, dest_vm_id, protocol)

    LOG.tc_step("Create port chain")
    port_chain_id = _setup_port_chain(port_pair_group_id, flow_classifier, symmetric)

    LOG.tc_step("Execute vxlan.py tool and verify {} packet received VM1 to VM2".format(protocol))
    _check_packets_forwarded_in_sfc_vm(source_vm_id, dest_vm_id, sfc_vm_ids, dest_vm_internal_net_ip, protocol,
                                       nsh_aware, symmetric, load_balancing=False)

    LOG.tc_step("Force lock {}".format(hosts_to_boot))
    if not same_host:
        for host_to_boot in hosts_to_boot:
            HostsToRecover.add(host_to_boot)
            lock_code, lock_output = host_helper.lock_host(host_to_boot, force=True, check_first=True)
            assert lock_code == 0, "Failed to force lock {}. Details: {}".format(host_to_boot, lock_output)
    else:
        HostsToRecover.add(hosts_to_boot[0])
        lock_code, lock_output = host_helper.lock_host(hosts_to_boot[0], force=True, check_first=True)
        assert lock_code == 0, "Failed to force lock {}. Details: {}".format(hosts_to_boot[0], lock_output)

    # Expect VMs to migrate off force-locked host (non-gracefully)
    LOG.tc_step("Wait for 'Active' status of VMs after host force lock completes")
    vm_helper.wait_for_vms_values(vm_ids, fail_ok=False)

    LOG.tc_step("Execute vxlan.py tool and verify {} packet received VM1 to VM2".format(protocol))
    _check_packets_forwarded_in_sfc_vm(source_vm_id, dest_vm_id, sfc_vm_ids, dest_vm_internal_net_ip, protocol,
                                       nsh_aware, symmetric, load_balancing=False)

    LOG.tc_step("Create new flow classifier with protocol {}".format(add_protocol))
    flow_classifier_name = 'new_sfc_flow_classifier'
    new_flow_classifier, dest_vm_internal_net_ip = _setup_flow_classifier(flow_classifier_name, source_vm_id,
                                                                          dest_vm_id, add_protocol)
    ResourceCleanup.add('flow_classifier', new_flow_classifier)

    LOG.tc_step("Update port chain with new flow classifier:".format(new_flow_classifier))
    network_helper.update_port_chain(port_chain_id, port_pair_groups=port_pair_group_id,
                                     flow_classifiers=new_flow_classifier)

    LOG.tc_step("Execute vxlan.py tool and verify {} packet received VM1 to VM2".format(add_protocol))
    _check_packets_forwarded_in_sfc_vm(source_vm_id, dest_vm_id, sfc_vm_ids, dest_vm_internal_net_ip, add_protocol,
                                       nsh_aware, symmetric, load_balancing=False)

    LOG.info("Get the host to reboot where the VMs launched")
    hosts_to_reboot = nova_helper.get_vms_host(vm_ids=vm_ids)

    LOG.tc_step("Reboot VMs host {} and ensure vms are evacuated to other host".format(hosts_to_reboot))
    vm_helper.evacuate_vms(host=hosts_to_reboot, vms_to_check=vm_ids, ping_vms=True)

    LOG.tc_step("Execute vxlan.py tool and verify {} packet received VM1 to VM2".format(add_protocol))
    _check_packets_forwarded_in_sfc_vm(source_vm_id, dest_vm_id, sfc_vm_ids, dest_vm_internal_net_ip, add_protocol,
                                       nsh_aware, symmetric, load_balancing=False)


@mark.parametrize(('protocol', 'nsh_aware', 'same_host', 'symmetric'), [
    ('tcp', 'nsh_aware', 'same_host', 'asymmetric'),
])
def test_multiple_chained_service_function(protocol, nsh_aware, same_host, symmetric, check_system,
                                           add_admin_role_module):
    """
        Test Multiple Chained Service Function

        Test Steps:
            - Check if the system is compatible
            - Boot the source VM, dest VM & SFC VM in same host or diff host based on <same_host: True or False>
            - Install necessary software and package inside guest for packet forwarding test
            - Create port pair using nsh_ware <True:False>
            - Create port pair group
            - Create SFC flow classifier using protocol <tcp:icmp:udp>
            - Create port Chain
            - Create SFC VM2. port pair, port pair group
            - Update port chain with new port pair group
            - Check packet forwarding from source to dest vm via SFC vm
            - Migrate VM by force_lock compute host
            - Check packet forwarding from source to dest vm via SFC vm

        Test Teardown:
            - Delete port chain, port pair group, port pair, flow classifier, vms, volumes created

    """
    nsh_aware = True if nsh_aware == 'nsh_aware' else False
    same_host = True if same_host == 'same_host' else False
    symmetric = True if symmetric == 'symmetric' else False

    LOG.tc_step("Check if the system is compatible to run this test")
    computes = check_system

    LOG.tc_step("Boot the VM in same host: {}".format(same_host))
    hosts_to_boot = [computes[0]] * 3 if same_host else computes[0:3]
    LOG.info("Boot the VM in following compute host 1:{}, 2:{}, 3:{}".format(hosts_to_boot[0], hosts_to_boot[1],
                                                                             hosts_to_boot[2]))

    LOG.tc_step("Boot the source and dest VM")
    vm_ids = []
    vm_ids, source_vm_id, dest_vm_id, internal_net_id, mgmt_net_id, mgmt_nic = _setup_vm(vm_ids, hosts_to_boot)
    vm_helper.ping_vms_from_vm(to_vms=source_vm_id, from_vm=dest_vm_id, net_types=['mgmt'], retry=10)

    LOG.tc_step("Boot the SFC VM")
    sfc_vm_ids = []
    sfc_vm_ids, sfc_vm_under_test, ingress_port_id, egress_port_id = _setup_sfc_vm(sfc_vm_ids, hosts_to_boot, mgmt_nic,
                                                                                   internal_net_id)
    vm_helper.ping_vms_from_vm(to_vms=source_vm_id, from_vm=sfc_vm_under_test, net_types=['mgmt'], retry=10)

    # if protocol != 'icmp':
    LOG.tc_step("Install software package nc in vm {} {}".format(source_vm_id, dest_vm_id))
    _install_sw_packages_in_vm(source_vm_id)
    _install_sw_packages_in_vm(dest_vm_id)

    LOG.tc_step("copy vxlan tool in sfc vm {}".format(sfc_vm_under_test))
    vm_helper.scp_to_vm_from_natbox(vm_id=sfc_vm_under_test, source_file='/home/cgcs/sfc/vxlan_tool.py',
                                    dest_file='/root/vxlan_tool.py')

    LOG.tc_step("Create Port Pair")
    port_pair_ids = []
    port_pair_id = _setup_port_pair(nsh_aware, ingress_port_id, egress_port_id)
    port_pair_ids.append(port_pair_id)

    LOG.tc_step("Create Port Pair group")
    port_pair_group_ids = []
    port_pair_group_id = _setup_port_pair_groups(port_pair_id)
    port_pair_group_ids.append(port_pair_group_id)

    LOG.tc_step("Create flow classifier")
    flow_classifier_name = 'sfc_flow_classifier'
    flow_classifier, dest_vm_internal_net_ip = _setup_flow_classifier(flow_classifier_name, source_vm_id, dest_vm_id,
                                                                      protocol)

    LOG.tc_step("Create Port Chain")
    port_chain_id = _setup_port_chain(port_pair_group_id, flow_classifier, symmetric)

    LOG.tc_step("Execute vxlan.py tool and verify {} packet received VM1 to VM2".format(protocol))
    _check_packets_forwarded_in_sfc_vm(source_vm_id, dest_vm_id, sfc_vm_ids, dest_vm_internal_net_ip, protocol,
                                       nsh_aware, symmetric, load_balancing=False)

    LOG.tc_step("Create second SFC VM")
    sfc_vm_ids, sfc_vm_under_test2, ingress_port_id2, egress_port_id2 = _setup_sfc_vm(sfc_vm_ids, hosts_to_boot,
                                                                                      mgmt_nic, internal_net_id)
    vm_helper.ping_vms_from_vm(to_vms=source_vm_id, from_vm=sfc_vm_under_test2, net_types=['mgmt'], retry=10)
    LOG.tc_step("copy vxlan tool in sfc vm {}".format(sfc_vm_under_test2))
    vm_helper.scp_to_vm_from_natbox(vm_id=sfc_vm_under_test2, source_file='/home/cgcs/sfc/vxlan_tool.py',
                                    dest_file='/root/vxlan_tool.py')

    LOG.tc_step("Create Port Pair for SFC VM2:{}".format(sfc_vm_under_test2))
    port_pair_id2 = _setup_port_pair(nsh_aware, ingress_port_id2, egress_port_id2)
    port_pair_ids.append(port_pair_id2)

    LOG.tc_step("Create Port Pair group for SFC VM2:{}".format(sfc_vm_under_test2))
    port_pair_group_id2 = _setup_port_pair_groups(port_pair_id2)
    port_pair_group_ids.append(port_pair_group_id2)

    LOG.tc_step("Update port chain")
    network_helper.update_port_chain(port_chain_id, port_pair_groups=port_pair_group_ids,
                                     flow_classifiers=flow_classifier)

    LOG.tc_step("Execute vxlan.py tool and verify {} packet received VM1 to VM2".format(protocol))
    _check_packets_forwarded_in_sfc_vm(source_vm_id, dest_vm_id, sfc_vm_ids, dest_vm_internal_net_ip, protocol,
                                       nsh_aware, symmetric, load_balancing=False)


@mark.parametrize(('protocol', 'nsh_aware', 'same_host', 'symmetric'), [
    ('tcp', 'nsh_unaware', 'same_host', 'symmetric'),
])
def test_load_balancing_chained_service_function(protocol, nsh_aware, same_host, symmetric, check_system,
                                                 add_admin_role_module):
    """
        Test Load Balancing Chained Service Function

        Test Steps:
            - Check if the system is compatible
            - Boot the source VM, dest VM
            - Boot 3 SFC VM
            - Install necessary software and package inside guest for packet forwarding test
            - Create port pair using nsh_ware <True:False> for each SFC VM
            - Create port pair group with 3 port pair
            - Create SFC flow classifier using protocol <tcp:icmp:udp>
            - Create port Chain with port pair group created
            - Check packet forwarding from source to dest vm via SFC vm

        Test Teardown:
            - Delete port chain, port pair group, port pair, flow classifier, vms, volumes created

    """
    nsh_aware = True if nsh_aware == 'nsh_aware' else False
    same_host = True if same_host == 'same_host' else False
    symmetric = True if symmetric == 'symmetric' else False

    LOG.tc_step("Check if the system is compatible to run this test")
    computes = check_system

    LOG.tc_step("Boot the VM in same host: {}".format(same_host))
    hosts_to_boot = [computes[0]] * 3 if same_host else computes[0:3]
    LOG.info("Boot the VM in following compute host 1:{}, 2:{}, 3:{}".format(hosts_to_boot[0], hosts_to_boot[1],
                                                                             hosts_to_boot[2]))

    LOG.tc_step("Boot the source and dest VM")
    vm_ids = []
    vm_ids, source_vm_id, dest_vm_id, internal_net_id, mgmt_net_id, mgmt_nic = _setup_vm(vm_ids, hosts_to_boot)
    vm_helper.ping_vms_from_vm(to_vms=source_vm_id, from_vm=dest_vm_id, net_types=['mgmt'], retry=10)

    LOG.tc_step("Boot the 3 SFC VM")
    sfc_vm_ids = []
    sfc_vm_ids, sfc_vm_under_test, ingress_port_id1, egress_port_id1 = \
        _setup_sfc_vm(sfc_vm_ids, hosts_to_boot, mgmt_nic, internal_net_id)

    sfc_vm_ids, sfc_vm_under_test2, ingress_port_id2, egress_port_id2 = \
        _setup_sfc_vm(sfc_vm_ids, hosts_to_boot, mgmt_nic, internal_net_id)
    sfc_vm_ids, sfc_vm_under_test3, ingress_port_id3, egress_port_id3 = \
        _setup_sfc_vm(sfc_vm_ids, hosts_to_boot, mgmt_nic, internal_net_id)

    for sfc_vm_id in sfc_vm_ids:
        vm_helper.ping_vms_from_vm(to_vms=source_vm_id, from_vm=sfc_vm_id, net_types=['mgmt'], retry=10)

    # if protocol != 'icmp':
    LOG.tc_step("Install software package nc in vm {} {}".format(source_vm_id, dest_vm_id))

    vm_helper.scp_to_vm_from_natbox(vm_id=source_vm_id, source_file='/home/cgcs/sfc/tcp_client.py',
                                    dest_file='/root/tcp_client.py')
    vm_helper.scp_to_vm_from_natbox(vm_id=source_vm_id, source_file='/home/cgcs/sfc/loop_tcp_client.sh',
                                    dest_file='/root/loop_tcp_client.sh')
    vm_helper.scp_to_vm_from_natbox(vm_id=source_vm_id, source_file='/home/cgcs/sfc/tcp_server_multi.py',
                                    dest_file='/root/tcp_server_multi.py')
    vm_helper.scp_to_vm_from_natbox(vm_id=dest_vm_id, source_file='/home/cgcs/sfc/tcp_client.py',
                                    dest_file='/root/tcp_client.py')
    vm_helper.scp_to_vm_from_natbox(vm_id=dest_vm_id, source_file='/home/cgcs/sfc/loop_tcp_client.sh',
                                    dest_file='/root/loop_tcp_client.sh')
    vm_helper.scp_to_vm_from_natbox(vm_id=dest_vm_id, source_file='/home/cgcs/sfc/tcp_server_multi.py',
                                    dest_file='/root/tcp_server_multi.py')
    _install_sw_packages_in_vm(source_vm_id)
    _install_sw_packages_in_vm(dest_vm_id)

    for sfc_vm in sfc_vm_ids:
        LOG.tc_step("copy vxlan tool in sfc vm {}".format(sfc_vm))
        vm_helper.scp_to_vm_from_natbox(vm_id=sfc_vm, source_file='/home/cgcs/sfc/vxlan_tool.py',
                                        dest_file='/root/vxlan_tool.py')

    LOG.tc_step("Create Port Pair for 3 SFC VM")
    port_pair_ids = []
    port_pair_id1 = _setup_port_pair(nsh_aware, ingress_port_id1, egress_port_id1)
    port_pair_ids.append(port_pair_id1)
    port_pair_id2 = _setup_port_pair(nsh_aware, ingress_port_id2, egress_port_id2)
    port_pair_ids.append(port_pair_id2)
    port_pair_id3 = _setup_port_pair(nsh_aware, ingress_port_id3, egress_port_id3)
    port_pair_ids.append(port_pair_id3)

    LOG.tc_step("Create Port Pair group using 3 port pairs:{}".format(port_pair_ids))
    port_pair_group_ids = []
    port_pair_group_id = _setup_port_pair_groups(port_pair_ids)
    port_pair_group_ids.append(port_pair_group_id)

    LOG.tc_step("Create flow classifier")
    flow_classifier_name = 'sfc_flow_classifier'
    flow_classifier, dest_vm_internal_net_ip = _setup_flow_classifier(flow_classifier_name, source_vm_id, dest_vm_id,
                                                                      protocol)

    LOG.tc_step("Create Port Chain")
    _setup_port_chain(port_pair_group_ids, flow_classifier, symmetric)

    LOG.tc_step("Execute vxlan.py tool and verify {} packet received VM1 to VM2".format(protocol))
    _check_packets_forwarded_in_sfc_vm(source_vm_id, dest_vm_id, sfc_vm_ids, dest_vm_internal_net_ip, protocol,
                                       nsh_aware, symmetric, load_balancing=True)


def _setup_vm(vm_ids, hosts_to_boot):

    """
    Set up source and destination vm
    Args:
        vm_ids: List of already booted VMs
        hosts_to_boot: Boot on same compute if same_host is true or in difference host

    Returns:
        vm_ids: append vm_id created
        source_vm_id, dest_vm_id, internal_net_id, mgmt_net_id, mgmt_nic
    """

    internal_net_id = network_helper.get_internal_net_id()
    mgmt_net_id = network_helper.get_mgmt_net_id()
    mgmt_nic = {'net-id': mgmt_net_id}
    internal_nic = {'net-id': internal_net_id}
    nics = [mgmt_nic, internal_nic]

    source_vm_id = vm_helper.boot_vm(name='source_vm', nics=nics, cleanup='function', vm_host=hosts_to_boot[0])[1]
    vm_ids.append(source_vm_id)
    dest_vm_id = vm_helper.boot_vm(name='dest_vm', nics=nics, cleanup='function', vm_host=hosts_to_boot[1])[1]
    vm_ids.append(dest_vm_id)
    LOG.info("Source VM {} and Destination VM {} booted".format(source_vm_id, dest_vm_id))

    return vm_ids, source_vm_id, dest_vm_id, internal_net_id, mgmt_net_id, mgmt_nic


def _setup_sfc_vm(sfc_vm_ids, hosts_to_boot, mgmt_nic, internal_net_id):

    """
    Set up SFC vm
    Args:
        sfc_vm_ids: List of already booted SFC VMs
        hosts_to_boot: Boot on same compute if same_host is true or in difference host
        mgmt_nic: management nic of source and dest VM
        internal_net_id: internal net id of source and dest VM

    Returns:
        sfc_vm_id: append vm_id created
        sfc_vm_under_test, ingress_port_id, egress_port_id
    """

    LOG.info("Create two ports for SFC VM")
    ingress_port_id = network_helper.create_port(internal_net_id, 'sfc_port1', cleanup='function')[1]
    egress_port_id = network_helper.create_port(internal_net_id, 'sfc_port2', cleanup='function')[1]
    LOG.info("Created ingress {} and egress port {}".format(ingress_port_id, egress_port_id))

    internal_nic1 = {'port-id': ingress_port_id}
    internal_nic2 = {'port-id': egress_port_id}
    sfc_nics = [mgmt_nic, internal_nic1, internal_nic2]

    sfc_vm_under_test = vm_helper.boot_vm(name='sfc_vm_under_test', nics=sfc_nics, cleanup='function',
                                          vm_host=hosts_to_boot[2])[1]
    sfc_vm_ids.append(sfc_vm_under_test)
    LOG.info("SFC VM booted {}".format(sfc_vm_under_test))

    return sfc_vm_ids, sfc_vm_under_test, ingress_port_id, egress_port_id


def _install_sw_packages_in_vm(vm_id):
    """
    install nc inside guest
    Args:
        vm_id (str):
    """
    with vm_helper.ssh_to_vm_from_natbox(vm_id,) as vm_ssh:
        vm_ssh.exec_sudo_cmd('yum install nc -y', searchwindowsize=100)


def _setup_port_pair(nsh_aware, ingress_port_id, egress_port_id):
    """
    create port pair and add resource cleanup
    Args:
        nsh_aware (bool): True or False
        ingress_port_id, egress_port_id from SFC VM

    Returns:
        port_pair_id
    """
    service_func_param = 'correlation=nsh' if nsh_aware else ''
    LOG.info("Create port pair with nsh aware: {}".format(nsh_aware))
    port_pair_id = network_helper.create_port_pair(name='sfc_port_pair',
                                                   ingress_port=ingress_port_id,
                                                   egress_port=egress_port_id,
                                                   service_func_param=service_func_param)[1]
    ResourceCleanup.add('port_pair', port_pair_id)
    LOG.info("Created port pair: {}".format(port_pair_id))
    return port_pair_id


def _setup_port_pair_groups(port_pair_id):

    """
    create port pair group and add resource cleanup
    Args:
        port_pair_id

    Returns:
        port_pair_group_id
    """

    LOG.info("Create port pair group")
    port_pair_group_id = network_helper.create_port_pair_group(port_pairs=port_pair_id, name='port_pair_group')[1]
    ResourceCleanup.add('port_pair_group', port_pair_group_id)
    LOG.info("Created port pair group {} with port pair:{}".format(port_pair_group_id, port_pair_id))
    return port_pair_group_id


def _setup_flow_classifier(name, source_vm_id, dest_vm_id, protocol):
    """
    create flow classifier and add resource cleanup
    Args:
        name: Str
        source vm id, dest vm id & protocol

    Returns:
        flow_classifier_id
    """
    internal_net_ip = network_helper.get_internal_ips_for_vms(source_vm_id, rtn_dict=False)
    internal_net_ip = ''.join(internal_net_ip)
    source_ip_prefix = "{}/32".format(internal_net_ip)

    dest_vm_internal_net_ip = network_helper.get_internal_ips_for_vms(dest_vm_id, rtn_dict=False)
    dest_vm_internal_net_ip = ''.join(dest_vm_internal_net_ip)

    logical_source_port = network_helper.get_vm_port(vm=internal_net_ip, vm_val='ip')
    LOG.info("internal port id is {}".format(logical_source_port))
    LOG.info("internal net ip is {}".format(source_ip_prefix))

    flow_classifier = network_helper.create_flow_classifier(name=name,
                                                            logical_source_port=logical_source_port,
                                                            source_ip_prefix=source_ip_prefix, protocol=protocol)[1]
    ResourceCleanup.add('flow_classifier', flow_classifier)
    LOG.info("Created flow classifier: {}".format(flow_classifier))
    return flow_classifier, dest_vm_internal_net_ip


def _setup_port_chain(port_pair_group_id, flow_classifier, symmetric):
    """
    create port chain and add resource cleanup
    Args:
        port_pair_group_id, slow_Classifier
        symmetric(bool)

    Returns:
        port_chain_id
    """
    chain_param = 'symmetric=true' if symmetric else ''
    LOG.info("Create port chain with symmetric: {}".format(symmetric))
    port_chain_id = network_helper.create_port_chain(name='sfc_port_chain', port_pair_groups=port_pair_group_id,
                                                     flow_classifiers=flow_classifier, chain_param=chain_param)[1]
    ResourceCleanup.add('port_chain', port_chain_id)
    LOG.info("Created port chain: {}".format(port_chain_id))
    return port_chain_id


def _check_packets_forwarded_in_sfc_vm(source_vm_id, dest_vm_id, sfc_vm_ids, dest_vm_internal_net_ip, protocol,
                                       nsh_aware, symmetric, load_balancing=False):
    end_event = Events("Hello or ping sent to vm")
    start_event = Events("VM {} started listening".format(dest_vm_id))
    received_event = Events("Greeting received on vm {}".format(dest_vm_id))
    vms_events = {}
    for sfc_vm in sfc_vm_ids:
        start_event_sfc = Events("SFC vm {} started listening".format(sfc_vm))
        received_event_sfc = Events("Packets received on SFC vm {}".format(sfc_vm))
        vms_events[sfc_vm] = (start_event_sfc, received_event_sfc)

    greeting = "hello"
    port = 20010
    if protocol != 'icmp':
        vm_thread = MThread(_ssh_to_dest_vm_and_wait_for_greetings, start_event, end_event,
                            received_event, dest_vm_id, dest_vm_internal_net_ip, greeting, port, protocol,
                            load_balancing)

    sfc_vm_threads = []
    for sfc_vm in sfc_vm_ids:
        start_event_sfc, received_event_sfc = vms_events[sfc_vm]
        sfc_vm_thread = MThread(_ssh_to_sfc_vm_and_wait_for_packets, start_event_sfc, end_event, received_event_sfc,
                                sfc_vm, protocol, nsh_aware, symmetric)
        sfc_vm_threads.append(sfc_vm_thread)

    LOG.tc_step("Starting VM ssh session threads to ping (icmp) or send hello (tcp, udp)")
    if protocol != 'icmp':
        vm_thread.start_thread()

    for sfc_vm_thread in sfc_vm_threads:
        LOG.tc_step("Starting each SFC VM threads")
        sfc_vm_thread.start_thread()

    try:
        if protocol != 'icmp':
            start_event.wait_for_event(timeout=180, fail_ok=False)
        for sfc_vm in sfc_vm_ids:
            start_event_sfc, received_event_sfc = vms_events[sfc_vm]
            start_event_sfc.wait_for_event(timeout=120, fail_ok=False)
        if protocol == 'icmp':
            LOG.tc_step("Ping from from vm {} to vm {}, and check it's received".format(source_vm_id, dest_vm_id))
            _ping_from_source_to_dest_vm(source_vm_id, end_event, dest_vm_internal_net_ip)
        else:
            if load_balancing:
                LOG.tc_step("Send Hello msg from vm using tcp_client.py {} to vm {}, and check it's received"
                            .format(source_vm_id, dest_vm_id))
                _send_hello_message_from_vm_using_tcp_client(source_vm_id, end_event, dest_vm_internal_net_ip)
            else:
                LOG.tc_step("Send Hello msg from vm {} to vm {}, and check it's received"
                            .format(source_vm_id, dest_vm_id))
                _send_hello_message_from_vm(source_vm_id, greeting, end_event, dest_vm_internal_net_ip, port, protocol)
        if protocol != 'icmp':
            assert received_event.wait_for_event(timeout=30), "Received Event {} is not set".format(received_event)
        for sfc_vm in sfc_vm_ids:
            start_event_sfc, received_event_sfc = vms_events[sfc_vm]
            assert received_event_sfc.wait_for_event(timeout=10), "Received Event is not set in SFC function"

    except:
        raise
    finally:
        end_event.set()
        if protocol != 'icmp':
            vm_thread.wait_for_thread_end(timeout=40, fail_ok=False)
        for sfc_vm_thread in sfc_vm_threads:
            sfc_vm_thread.wait_for_thread_end(timeout=40, fail_ok=False)


def _ssh_to_dest_vm_and_wait_for_greetings(start_event, end_event, received_event, vm_id, dest_vm_internal_net_ip,
                                           greeting, port, protocol, load_balancing, timeout=300):

    with vm_helper.ssh_to_vm_from_natbox(vm_id) as root_ssh:
        if load_balancing:
            LOG.info("Load balancing Enabled, using tcp_server app")
            LOG.info("Start listening on port 20010-20020 on vm {} internal IP {}"
                     .format(vm_id, dest_vm_internal_net_ip))
            cmd = "python ./tcp_server_multi.py {} 20010-20020".format(dest_vm_internal_net_ip)
            root_ssh.send(cmd)
            start_event.set()
        else:
            LOG.info("Start listening on port 80 on vm {}".format(vm_id))
            udp_param = 'u' if protocol == 'udp' else ''
            cmd = "nc -{}lp {}".format(udp_param, port)
            root_ssh.send(cmd)
            start_event.set()

        def _check_receive_event():
            # set receive event if msg received
            if load_balancing:
                index = root_ssh.expect([greeting, root_ssh.prompt], timeout=10, fail_ok=True, searchwindowsize=50)
            else:
                index = root_ssh.expect(timeout=10, fail_ok=True)

            if index == 0:
                output = root_ssh.cmd_output
                assert greeting in output, \
                    "Output: {} received, but not as expected: {}".format(output, greeting)
                LOG.info("greeting {} and received output {}".format(greeting, output))
                received_event.set()
                LOG.info("Received output: {}".format(output))

        end_time = time.time() + timeout
        while time.time() < end_time:
            # Exit the vm ssh, end thread
            if end_event.is_set():
                if not received_event.is_set():
                    _check_receive_event()

                root_ssh.send_control()
                root_ssh.expect(timeout=10, fail_ok=True)
                return

            _check_receive_event()
            time.sleep(5)

    assert 0, "end_event is not set within timeout"


def _ssh_to_sfc_vm_and_wait_for_packets(start_event, end_event, received_event, vm_id, protocol, nsh_aware, symmetric,
                                        timeout=300):

    with vm_helper.ssh_to_vm_from_natbox(vm_id) as root_ssh:
        LOG.info("Verify the tool received {} packets from VM1 to VM2 and you can see the pkts coming in"
                 .format(protocol))
        cmd = 'ifconfig'
        root_ssh.send(cmd)
        nsh_type = 'eth'
        if nsh_aware:
            nsh_type = 'eth_nsh'
        # nsh_type = 'eth_nsh' if nsh_aware == 'yes' else 'eth'
        LOG.info("nsh aware {} nsh type".format(nsh_aware, nsh_type))
        cmd = 'python ./vxlan_tool.py -i eth1 -o eth2 -d forward -t {}'.format(nsh_type)
        root_ssh.send(cmd)
        start_event.set()

        packet_num = 8 if symmetric else 4
        blob_list = 'Forwarding packet'
        if nsh_aware:
            if protocol != 'icmp':
                blob_list = 'Packet #{}'.format(packet_num)
            else:
                blob_list = 'Packet #'
        # if nsh_aware:
        #     blob_list = 'Packet #{}'.format(packet_num)

        def _check_receive_event():
            # set receive event if msg received
            index = root_ssh.expect(blob_list=blob_list, timeout=10, fail_ok=True)
            if index == 0:
                LOG.info("Received packet in SFC VM: {}".format(vm_id))
                received_event.set()

        end_time = time.time() + timeout
        while time.time() < end_time:
            # Exit the vm ssh, end thread
            if end_event.is_set():
                if not received_event.is_set():
                    _check_receive_event()

                root_ssh.send_control()
                root_ssh.expect(timeout=10, fail_ok=True)
                return

            _check_receive_event()
            time.sleep(5)


def _send_hello_message_from_vm(vm_id, greeting, end_event, dest_vm_internal_net_ip, port, protocol):
    """

    nc <internal ip of dest vm> <port>
    nc -lp 20010
    Args:
        vm_id (str):
        greeting (str): hello

    """
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        udp_param = '-u' if protocol == 'udp' else ''
        cmd = 'nc {} {} {}'.format(udp_param, dest_vm_internal_net_ip, port)
        vm_ssh.send(cmd)
        vm_ssh.send(greeting)
        time.sleep(1)
        vm_ssh.send_control()
        vm_ssh.expect(timeout=10, fail_ok=True)
        end_event.set()


def _ping_from_source_to_dest_vm(vm_id, end_event, dest_vm_internal_net_ip):
    """
    ping -c 4 <dest vm internal ip>
    Args:
        vm_id (str):
    """
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        cmd = 'ping -c 4 {}'.format(dest_vm_internal_net_ip)
        vm_ssh.send(cmd)
        time.sleep(1)
        vm_ssh.send_control()
        vm_ssh.expect(timeout=10, fail_ok=True)
        end_event.set()


def _send_hello_message_from_vm_using_tcp_client(vm_id, end_event, dest_vm_internal_net_ip):
    """

    nc <internal ip of dest vm> <port>
    nc -lp 20010
    Args:
        vm_id (str):

    """
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        cmd = "./loop_tcp_client.sh '{}'".format(dest_vm_internal_net_ip)
        vm_ssh.send(cmd)
        time.sleep(1)
        vm_ssh.send_control()
        vm_ssh.expect(timeout=10, fail_ok=True)
        end_event.set()