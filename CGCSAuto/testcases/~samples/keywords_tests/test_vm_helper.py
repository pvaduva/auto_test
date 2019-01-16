import time
from pytest import mark

from utils.tis_log import LOG
from consts.auth import Tenant
from keywords import vm_helper, network_helper, glance_helper


def test_boot_vms():

    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    internal_net_id = network_helper.get_internal_net_id()

    nics = [{'net-id': mgmt_net_id},
            {'net-id': tenant_net_id},
            {'net-id': internal_net_id}]

    for guest_os in ['ubuntu_14', 'cgcs-guest']:
        glance_helper.get_guest_image(guest_os)
        vm_id = vm_helper.boot_vm(guest_os=guest_os, nics=nics)[1]
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

        time.sleep(30)
        vm_helper.ping_vms_from_vm(vm_id, vm_id, net_types=['mgmt', 'data', 'internal'])


def test_vm_topo_check():
    vm_id = vm_helper.boot_vm()[1]
    affined_cpus = vm_helper.get_affined_cpus_for_vm(vm_id)
    LOG.info(affined_cpus)


@mark.parametrize('guest_os', [
    'opensuse_11',
    'opensuse_12',
    # 'rhel_6',
    'rhel_7'
    # 'opensuse_13',
])
def test_boot_and_ping_vm(guest_os, opensuse11_image, opensuse12_image, opensuse13_image, rhel6_image, rhel7_image):

    vm_id = vm_helper.boot_vm(guest_os=guest_os, source='image', cleanup='function')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)


def test_non_primary_tenant():
    vm_1 = vm_helper.boot_vm(cleanup='function', auth_info=Tenant.TENANT1)[1]
    vm_2 = vm_helper.launch_vms(vm_type='dpdk', auth_info=Tenant.TENANT1)[0][0]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_1)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_2)
    vm_helper.ping_vms_from_natbox(vm_ids=vm_2)
    vm_helper.ping_vms_from_vm(vm_2, vm_1, net_types='mgmt')
