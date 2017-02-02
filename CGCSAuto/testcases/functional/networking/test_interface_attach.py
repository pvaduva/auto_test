from pytest import fixture, mark
from utils.tis_log import LOG

from keywords import network_helper, nova_helper, vm_helper
from testfixtures.resource_mgmt import ResourceCleanup


@fixture(scope='module')
def base_vm():
    net_name = 'internal0-net1'
    net_id = network_helper.get_net_id_from_name(net_name)
    mgmt_net_id = network_helper.get_mgmt_net_id()
    mgmt_nic = {'net-id': mgmt_net_id, 'vif-model': 'virtio'}
    nics = [mgmt_nic,
            {'net-id': net_id, 'vif-model': 'virtio'}]

    vm_id = vm_helper.boot_vm(name='base_vm', nics=nics)[1]
    ResourceCleanup.add('vm', vm_id, scope='module')

    return vm_id, mgmt_nic, net_id


@mark.parametrize(('if_attach_arg', 'vif_model'), [
    ('net_id', 'e1000'),
    ('net_id', 'virtio'),
    # ('net_id', 'avp'),  # Unable to connect to vm
    ('port_id', None),
    # ('port_id', 'rtl8139'),   # Interface with vif mac is not listed in 'ip addr' in vm
    # ('port_id', 'ne2k_pci')   # ERROR (ClientException): Failed to attach network adapter device to
])
def test_interface_attach_detach(base_vm, if_attach_arg, vif_model):
    """
    Sample test case for interface attach/detach
    Args:
        base_vm (tuple): (base_vm_id, mgmt_nic, internal_net_id)
        if_attach_arg (str): whether to attach via port_id or net_id
        vif_model (str): vif_model to pass to interface-attach cli, or None

    Setups:
        - Boot a base vm with mgmt net and internal0-net1   (module)

    Test Steps:
        - Create a new port on internal0-net1 if attaching port via port_id
        - Boot a vm with mgmt nic only
        - Attach an interface to vm with given if_attach_arg and vif_model
        - Bring up the interface from vm
        - ping between base_vm and vm_under_test over internal0-net1
        - detach the interface
        - Verify vm_under_test can no longer ping base_vm over internal0-net1

    Teardown:
        - Delete created vm, volume, port (if any)  (func)
        - Delete base vm, volume    (module)

    """
    base_vm_id, mgmt_nic, net_id = base_vm

    port_id = None
    if if_attach_arg == 'port_id':
        LOG.tc_step("Create a new port")
        port_id = network_helper.create_port(net_id, 'if_attach_port')[1]
        ResourceCleanup.add('port', port_id)
        net_id = None

    LOG.tc_step("Boot a vm with mgmt nic only")
    vm_id = vm_helper.boot_vm(name='if_attach_tenant', nics=[mgmt_nic])[1]
    ResourceCleanup.add('vm', vm_id)

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    LOG.tc_step("Attach interface to vm via {} with vif_model: {}".format(if_attach_arg, vif_model))
    port = vm_helper.attach_interface(vm_id, net_id=net_id, vif_model=vif_model, port_id=port_id)[1]
    if port_id:
        assert port_id == port, "Specified port_id is different than attached port"

    LOG.tc_step("Bring up attached interface from vm")
    _bring_up_attached_interface(vm_id)

    LOG.tc_step("Verify VM internet0-net1 interface is up")
    vm_helper.ping_vms_from_vm(to_vms=vm_id, from_vm=base_vm_id, retry=5, net_types='internal')

    LOG.tc_step("Detach port {} from VM".format(port))
    vm_helper.detach_interface(vm_id=vm_id, port_id=port)

    res = vm_helper.ping_vms_from_vm(to_vms=base_vm_id, from_vm=vm_id, fail_ok=True, retry=0, net_types='internal')[0]
    assert not res, "Ping from base_vm to vm via detached interface still works"


def _bring_up_attached_interface(vm_id):
    """
    ip link set <dev> up, and dhclient <dev> to bring up the interface of last nic for given VM
    Args:
        vm_id (str):
    """
    vm_nics = nova_helper.get_vm_interfaces_info(vm_id=vm_id)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        mac_addr = vm_nics[-1]['mac_address']
        eth_name = network_helper.get_eth_for_mac(mac_addr=mac_addr, ssh_client=vm_ssh)
        assert eth_name, "Interface with mac {} is not listed in 'ip addr' in vm {}".format(mac_addr, vm_id)
        vm_ssh.exec_cmd('ip link set dev {} up'.format(eth_name))
        vm_ssh.exec_cmd('dhclient {}'.format(eth_name))
        vm_ssh.exec_cmd('ip addr')
