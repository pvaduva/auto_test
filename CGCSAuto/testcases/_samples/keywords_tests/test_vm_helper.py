import time
from keywords import vm_helper, network_helper


def test_boot_vms(ubuntu_image):

    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    internal_net_id = network_helper.get_internal_net_id()

    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': tenant_net_id},
            {'net-id': internal_net_id}]

    for guest_os in ['ubuntu', 'cgcs-guest']:
        vm_id = vm_helper.boot_vm(guest_os=guest_os, nics=nics)[1]
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

        time.sleep(30)
        vm_helper.ping_vms_from_vm(vm_id, vm_id, net_types=['mgmt', 'data', 'internal'])
