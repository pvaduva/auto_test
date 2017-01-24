from pytest import fixture
from utils.tis_log import LOG

from keywords import network_helper, nova_helper, vm_helper
from testfixtures.resource_mgmt import ResourceCleanup


@fixture(scope='module')
def base_vm():
    net_name = 'internal0-net0'
    net_id = network_helper.get_net_id_from_name(net_name)
    mgmt_net_id = network_helper.get_mgmt_net_id()
    mgmt_nic = {'net-id': mgmt_net_id, 'vif-model': 'virtio'}
    nics = [mgmt_nic,
            {'net-id': net_id, 'vif-model': 'virtio'}]

    vm_id = vm_helper.boot_vm(name='base_vm', nics=nics)[1]
    ResourceCleanup.add('vm', vm_id)

    return vm_id, mgmt_nic, net_id


def test_if_attach_detach(base_vm):
    base_vm_id, mgmt_nic, net_id = base_vm
    LOG.tc_step("Boot a vm with mgmt nic only")

    vm_id = vm_helper.boot_vm(name='if_attach', nics=[mgmt_nic])[1]
    ResourceCleanup.add('vm', vm_id)

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    LOG.tc_step("Attach interface to vm via net_id")
    port = vm_helper.attach_interface(vm_id, net_id=net_id, vif_model='e1000')[1]

    LOG.tc_step("Verify VM internet0-net0 interface is up")
    vm_helper.ping_vms_from_vm(to_vms=vm_id, from_vm=base_vm_id, retry=5, net_types='internal')

    LOG.tc_step("Detach port {} from VM".format(port))
    vm_helper.detach_interface(vm_id=vm_id, port_id=port)

    res = vm_helper.ping_vms_from_vm(to_vms=vm_id, from_vm=base_vm_id, fail_ok=True, retry=0)[0]
    assert not res, "Ping from base_vm to vm via detached interface still works"

