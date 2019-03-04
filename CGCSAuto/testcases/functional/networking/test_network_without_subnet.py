import random

from pytest import fixture, mark

from utils.tis_log import LOG
from consts.cgcs import VMStatus
from keywords import network_helper, nova_helper, vm_helper, system_helper


@fixture(scope='module')
def base_vm(setups):
    LOG.fixture_step("Create a network without subnet with port security disabled")
    tenant_net_id = network_helper.create_network(name='net_without_subnet', port_security=False,
                                                  cleanup='module')[1]

    mgmt_net_id = network_helper.get_mgmt_net_id()
    mgmt_nic = {'net-id': mgmt_net_id}
    tenant_net_nic = {'net-id': tenant_net_id}
    nics = [mgmt_nic, tenant_net_nic]
    LOG.fixture_step("Create a VM with one nic using network without subnet")
    vm_id = vm_helper.boot_vm(name='base_vm', nics=nics, cleanup='module')[1]

    LOG.fixture_step("Assign an ip to the nic over network without subnet")
    ports = network_helper.get_ports(server=vm_id, network=tenant_net_id)
    _assign_ip_to_nic(vm_id, ports=ports)

    return vm_id, mgmt_nic, tenant_net_id


@fixture(scope='module')
def setups(request):
    LOG.fixture_step("Add port_security service parameter")
    system_helper.enable_port_security_param()

    network_quota = network_helper.get_quota('network')
    instance_quota = nova_helper.get_quotas('instances')[0]
    network_helper.update_quotas(network=network_quota + 5)
    nova_helper.update_quotas(instances=instance_quota + 5)

    def _revert_quota():
        network_helper.update_quotas(network=network_quota)
        nova_helper.update_quotas(instances=instance_quota)
    request.addfinalizer(_revert_quota)


@mark.parametrize(('if_attach_param', 'vif_model'), [
    ('port_id', 'virtio'),
    ('net_id', 'avp')
])
def test_network_without_subnets(skip_for_ovs, base_vm, if_attach_param, vif_model):
    """
    Sample test case for Boot an instance with network without subnet
    Args:
        skip_for_ovs: skip test if avp is specified
        base_vm (tuple): (base_vm_id, mgmt_nic, tenant_net_id)
        if_attach_param (str): whether to attach interface
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
    base_vm_id, mgmt_nic, tenant_net_id = base_vm
    tenant_net_nic = {'net-id': tenant_net_id}
    if vif_model == 'avp':
        tenant_net_nic['vif-model'] = vif_model

    LOG.tc_step("Boot a vm with network without subnet")
    vm_under_test = vm_helper.boot_vm(name='vm-net-without-subnet', nics=[mgmt_nic, tenant_net_nic],
                                      cleanup='function')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_under_test)
    init_ports = network_helper.get_ports(network=tenant_net_id, server=vm_under_test)
    init_ip = _assign_ip_to_nic(vm_under_test, init_ports, base_vm_id=base_vm_id)[0]

    for vm_actions in [['cold_migrate'], ['live_migrate'], ['suspend', 'resume'], ['stop', 'start']]:
        tenant_port_id, ip_addrs = _pre_action_network_without_subnet(base_vm_id, vm_under_test, vm_actions, vif_model,
                                                                      tenant_net_id, if_attach_param)
        if vm_actions[0] == 'auto_recover':
            LOG.tc_step("Set vm to error state and wait for auto recovery complete, then verify ping from "
                        "base vm over management and data networks")
            vm_helper.set_vm_state(vm_id=vm_under_test, error_state=True, fail_ok=False)
            vm_helper.wait_for_vm_values(vm_id=vm_under_test, status=VMStatus.ACTIVE, fail_ok=True, timeout=600)
        else:
            LOG.tc_step("Perform following action(s) on vm {}: {}, and verify ping vm over mgmt and data networks".
                        format(vm_under_test, vm_actions))
            for action in vm_actions:
                vm_helper.perform_action_on_vm(vm_under_test, action=action)

        vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test)
        _post_action_network_without_subnet(base_vm_id, vm_under_test, vm_actions, vif_model, tenant_port_id,
                                            port_ip=ip_addrs[0], init_port_ip=init_ip)


def _pre_action_network_without_subnet(base_vm_id, vm_under_test, vm_actions, vif_model, tenant_net_id, attach_param):

    """

    Args:
        base_vm_id (str): base vm id
        vm_under_test (str): vm id of instance to be tested
        vm_actions (list|tuple):
        vif_model (str):
        tenant_net_id (str):
        attach_param (str): port_id or net_id

    Returns tenant_port_id (str):

    """
    LOG.tc_step("Before {}: Attach {} interface to {}, assign a static ip, and ping data interfaces from the other vm".
                format(vm_actions, vif_model, vm_under_test))
    if attach_param == 'port_id':
        LOG.tc_step("Create a port for network without subnet")
        tenant_port_id = network_helper.create_port(tenant_net_id, 'port_without_subnet', cleanup='function',
                                                    port_security=False)[1]
        attach_arg = {'port_id': tenant_port_id}
    else:
        attach_arg = {'net_id': tenant_net_id}

    # TODO Update vif model config. Right now vif model avp still under implementation
    tenant_port_id = vm_helper.attach_interface(vm_under_test, vif_model=vif_model, **attach_arg)[1]

    ip_addrs = _assign_ip_to_nic(vm_under_test, ports=[tenant_port_id], base_vm_id=base_vm_id)

    return tenant_port_id, ip_addrs


def _post_action_network_without_subnet(base_vm_id, vm_under_test, vm_actions, vif_model, port_to_detach, port_ip,
                                        init_port_ip):

    """
    Args:
        base_vm_id (str): base vm id
        vm_under_test (str): vm id of instance to be tested
        vm_actions (list|tuple):
        vif_model (str):
        port_to_detach (str):

    """
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm_id, net_types=['mgmt'], retry=10)
    with vm_helper.ssh_to_vm_from_natbox(vm_id=base_vm_id) as vm_ssh:
        for ip_addr in (init_port_ip, port_ip):
            network_helper.ping_server(ip_addr, ssh_client=vm_ssh, retry=5)

    LOG.tc_step("After {}: Detach the {} port {} and ping vm's mgmt and data interface".
                format(vm_actions, vif_model, port_to_detach))
    vm_helper.detach_interface(vm_id=vm_under_test, port_id=port_to_detach, cleanup_route=False)
    vm_helper.cleanup_routes_for_vifs(vm_id=vm_under_test, vm_ips=port_ip)

    LOG.info("Ping tenant net ip for port that is not detached: {}".format(init_port_ip))
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm_id, net_types=['mgmt'], retry=10)
    with vm_helper.ssh_to_vm_from_natbox(vm_id=base_vm_id) as vm_ssh:
        network_helper.ping_server(init_port_ip, ssh_client=vm_ssh, retry=5)


ASSIGNED_IPS = []


def __get_unassigned_ip():
    global ASSIGNED_IPS
    static_ip = '172.16.0.{}'.format(random.choice(list(set(range(2, 255)) - set(ASSIGNED_IPS))))
    ASSIGNED_IPS.append(static_ip)
    return static_ip


def _assign_ip_to_nic(vm_id, ports, base_vm_id=None):
    """
    ip link set <dev> up, and dhclient <dev> to bring up the interface of last nic for given VM
    Args:
        vm_id (str):
    """
    vm_macs = network_helper.get_ports(rtn_val='MAC Address', server=vm_id, port_id=ports)
    static_ips = []
    for _ in vm_macs:
        static_ips.append(__get_unassigned_ip())
    vm_helper.add_ifcfg_scripts(vm_id=vm_id, mac_addrs=vm_macs, reboot=False, static_ips=static_ips)
    vm_helper.configure_vm_vifs_on_same_net(vm_id=vm_id, ports=ports, vm_ips=static_ips, reboot=True)

    if base_vm_id:
        with vm_helper.ssh_to_vm_from_natbox(vm_id=base_vm_id) as vm_ssh:
            LOG.info("ip address to ping {}".format(static_ips))
            for ip_addr in static_ips:
                network_helper.ping_server(ip_addr, ssh_client=vm_ssh, retry=5)

    return static_ips
