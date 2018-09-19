import re
import random
from pytest import fixture, mark
from utils.tis_log import LOG

from consts.cgcs import VMStatus, EventLogID
from keywords import network_helper, nova_helper, vm_helper, system_helper, host_helper
from testfixtures.fixture_resources import ResourceCleanup


@fixture(scope='module')
def base_vm(setups):
    # port_security = None if system_helper.is_avs() else False
    port_security = False
    LOG.fixture_step("Create a network without subnet with port security disabled")
    tenant_net_id = network_helper.create_network(name='net_without_subnet', port_security=port_security)[1]
    ResourceCleanup.add('network', tenant_net_id)

    mgmt_net_id = network_helper.get_mgmt_net_id()
    mgmt_nic = {'net-id': mgmt_net_id, 'vif-model': 'virtio'}
    tenant_net_nic = {'net-id': tenant_net_id, 'vif-model': 'virtio'}
    nics = [mgmt_nic, tenant_net_nic]
    LOG.fixture_step("Create a VM with one nic using network without subnet")
    vm_id = vm_helper.boot_vm(name='base_vm', nics=nics, cleanup='module')[1]

    LOG.fixture_step("Assign an ip to the nic over network without subnet")
    _assign_ip_to_nic(vm_id)

    return vm_id, mgmt_nic, tenant_net_id, port_security


@fixture(scope='module')
def setups(request):
    LOG.fixture_step("Add port_security service parameter")
    code = system_helper.create_service_parameter(service='network', section='ml2', name='extension_drivers',
                                                  value='port_security', apply=False)[0]
    if 0 == code:
        system_helper.apply_service_parameters(service='network', wait_for_config=False)
        computes = host_helper.get_up_hypervisors()
        for host in computes:
            system_helper.wait_for_alarm(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, entity_id=host, timeout=30)
        host_helper.lock_unlock_hosts(computes)
        system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, timeout=60)

    network_quota = network_helper.get_quota('network')
    instance_quota = nova_helper.get_quotas('instances')[0]
    network_helper.update_quotas(network=network_quota + 20)
    nova_helper.update_quotas(instances=instance_quota + 5)

    def _revert_quota():
        network_helper.update_quotas(network=network_quota)
        nova_helper.update_quotas(instances=instance_quota)
    request.addfinalizer(_revert_quota)


@mark.parametrize(('if_attach_arg', 'vif_model'), [
    ('port_id', 'virtio'),
    ('net-id', 'avp')
])
def test_network_without_subnets(skip_for_ovs, base_vm, if_attach_arg, vif_model):
    """
    Sample test case for Boot an instance with network without subnet
    Args:
        skip_for_ovs: skip test if avp is specified
        base_vm (tuple): (base_vm_id, mgmt_nic, tenant_net_id)
        if_attach_arg (str): whether to attach via port_id or net_id
        vif_model (str): vif_model to pass to interface-attach cli, or None

    Setups:
        - Boot a base vm with mgmt net and net without subnet   (module)

    Test Steps:
        - Boot a vm with only mgmt interface & net without subnet based on given if_attach_arg and vif_model
        - Attach an vifs to vm with given vif_model
        - Assign ip to the interfaces
        - ping between base_vm and vm_under_test over mgmt & tenant network
        - Perform VM action - Cold migrate, live migrate, pause resume, suspend resume
        - Verify ping between base_vm and vm_under_test over mgmt & tenant network after vm operation
        - detach all the tenant interface
        - Repeat attach/detach after performing each vm action

    Teardown:
        - Delete created vm, volume, port (if any)  (func)
        - Delete base vm, volume    (module)

    """

    base_vm_id, mgmt_nic, tenant_net_id, port_security = base_vm

    if if_attach_arg == 'port_id':
        tenant_port_id = network_helper.create_port(tenant_net_id, 'port_without_subnet',
                                                    port_security=port_security)[1]
        ResourceCleanup.add('port', tenant_port_id)
        tenant_net_nic = {'port-id': tenant_port_id, 'vif-model': vif_model}
    else:
        tenant_net_nic = {'net-id': tenant_net_id, 'vif-model': vif_model}

    LOG.tc_step("Boot a vm with network without subnet")
    vm_under_test = vm_helper.boot_vm(name='vm-net-without-subnet', nics=[mgmt_nic, tenant_net_nic],
                                      cleanup='function')[1]

    for vm_actions in [['cold_migrate'], ['live_migrate'], ['suspend', 'resume'], ['stop', 'start']]:
        tenant_port_id = _pre_action_network_without_subnet(base_vm_id, vm_under_test, vm_actions, vif_model,
                                                            tenant_net_id)
        if vm_actions[0] == 'auto_recover':
            LOG.tc_step("Set vm to error state and wait for auto recovery complete, then verify ping from "
                        "base vm over management and data networks")
            vm_helper.set_vm_state(vm_id=vm_under_test, error_state=True, fail_ok=False)
            vm_helper.wait_for_vm_values(vm_id=vm_under_test, status=VMStatus.ACTIVE, fail_ok=True, timeout=600)
        else:
            LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm_under_test, vm_actions))
            for action in vm_actions:
                vm_helper.perform_action_on_vm(vm_under_test, action=action)

        vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test)
        _post_action_network_without_subnet(base_vm_id, vm_under_test, vm_actions, vif_model, tenant_port_id)


def _pre_action_network_without_subnet(base_vm_id, vm_under_test, vm_actions, vif_model, tenant_net_id):

    """

    Args:
        base_vm_id (str): base vm id
        vm_under_test (str): vm id of instance to be tested
        vm_actions (list|tuple):
        vif_model (str):
        tenant_net_id (str):

    Returns tenant_port_id (str):

    """
    _assign_ip_to_nic(vm_under_test)
    ip_addr = _find_ip_to_ping(vm_under_test)
    LOG.info("ip address to ping {}".format(ip_addr))

    LOG.tc_step("Verify ping from base_vm to vm_under_test over management & data networks still works "
                "before {}".format(vm_actions))
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm_id, net_types=['mgmt'], retry=10)
    with vm_helper.ssh_to_vm_from_natbox(vm_id=base_vm_id) as vm_ssh:
        LOG.info("ip address to ping {}".format(ip_addr))
        network_helper.ping_server(ip_addr, ssh_client=vm_ssh, retry=5)

    LOG.tc_step("Attach the interface to {} of {} vif_model".format(vm_under_test, vif_model))
    tenant_port_id = vm_helper.attach_interface(vm_under_test, vif_model=vif_model, net_id=tenant_net_id)[1]

    LOG.tc_step("Assign IP to attached interface to {} VM {}".format(tenant_port_id, vm_under_test))
    _assign_ip_to_nic(vm_under_test)
    LOG.tc_step("Find IP to ping {} VM".format(vm_under_test))
    ip_addr = _find_ip_to_ping(vm_under_test)
    LOG.info("ip address to ping {}".format(ip_addr))

    LOG.tc_step("Verify ping from base_vm to vm_under_test over attached data networks still works "
                "before {}".format(vm_actions))
    with vm_helper.ssh_to_vm_from_natbox(vm_id=base_vm_id) as vm_ssh:
        LOG.info("ip address to ping {}".format(ip_addr))
        network_helper.ping_server(ip_addr, ssh_client=vm_ssh, retry=5)

    return tenant_port_id


def _post_action_network_without_subnet(base_vm_id, vm_under_test, vm_actions, vif_model, tenant_port_id):

    """
    Args:
        base_vm_id (str): base vm id
        vm_under_test (str): vm id of instance to be tested
        vm_actions (list|tuple):
        vif_model (str):
        tenant_port_id (str):

    """

    _assign_ip_to_nic(vm_under_test)
    ip_addr = _find_ip_to_ping(vm_under_test)
    LOG.info("ip address to ping {}".format(ip_addr))

    LOG.tc_step("Verify ping from base_vm to vm_under_test over management & attached data networks still works "
                "after {}".format(vm_actions))
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm_id, net_types=['mgmt'], retry=10)
    with vm_helper.ssh_to_vm_from_natbox(vm_id=base_vm_id) as vm_ssh:
        network_helper.ping_server(ip_addr, ssh_client=vm_ssh, retry=5)

    LOG.tc_step("Detach the {} interface {}".format(vif_model, tenant_port_id))
    vm_helper.detach_interface(vm_id=vm_under_test, port_id=tenant_port_id)

    LOG.tc_step("Verify ping from base_vm to vm_under_test over management & data networks still works "
                "after {}".format(vm_actions))
    _assign_ip_to_nic(vm_under_test)
    ip_addr = _find_ip_to_ping(vm_under_test)
    LOG.info("ip address to ping {}".format(ip_addr))
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm_id, net_types=['mgmt'], retry=10)
    with vm_helper.ssh_to_vm_from_natbox(vm_id=base_vm_id) as vm_ssh:
        network_helper.ping_server(ip_addr, ssh_client=vm_ssh, retry=5)


def _remove_dhclient_cache(vm_id):
    dhclient_leases_cache = '/var/lib/dhclient/dhclient.leases'
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        if vm_ssh.file_exists(dhclient_leases_cache):
            vm_ssh.exec_sudo_cmd('rm {}'.format(dhclient_leases_cache))


def _assign_ip_to_nic(vm_id):
    """
    ip link set <dev> up, and dhclient <dev> to bring up the interface of last nic for given VM
    Args:
        vm_id (str):
    """
    vm_nics = nova_helper.get_vm_interfaces_info(vm_id=vm_id)
    dhclient_leases_cache = '/var/lib/dhclient/dhclient.leases'
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        if vm_ssh.file_exists(dhclient_leases_cache):
            vm_ssh.exec_sudo_cmd('rm {}'.format(dhclient_leases_cache))
        values = random.sample(range(2, 255), 5)
        vnic = vm_nics[-1]
        mac_addr = vnic['mac_address']
        eth_name = network_helper.get_eth_for_mac(mac_addr=mac_addr, ssh_client=vm_ssh)
        assert eth_name, "Interface with mac {} is not listed in 'ip addr' in vm {}".format(mac_addr, vm_id)
        vm_ssh.exec_sudo_cmd('ifconfig {} 172.16.0.{}/24 up'.format(eth_name, random.choice(values)))
        vm_ssh.exec_cmd('ip addr')


def _find_ip_to_ping(vm_id):
    """
    ip link set <dev> up, and dhclient <dev> to bring up the interface of last nic for given VM
    Args:
        vm_id (str):
    """
    vm_nics = nova_helper.get_vm_interfaces_info(vm_id=vm_id)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        vnic = vm_nics[-1]
        mac_addr = vnic['mac_address']
        eth_name = network_helper.get_eth_for_mac(mac_addr=mac_addr, ssh_client=vm_ssh)
        assert eth_name, "Interface with mac {} is not listed in 'ip addr' in vm {}".format(mac_addr, vm_id)
        output = vm_ssh.exec_cmd('ip addr show {}'.format(eth_name), fail_ok=False)[1]
        ip_addr = re.findall(r'inet (172.16.0.\d+)', output)[0]
        vm_ssh.exec_cmd('ip addr')
    return ip_addr
