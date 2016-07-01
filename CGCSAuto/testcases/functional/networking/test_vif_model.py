
from pytest import fixture, mark
from time import sleep

from utils import table_parser, cli, exceptions
from utils.tis_log import LOG

from consts.auth import Tenant
from consts.cgcs import VMStatus, FlavorSpec, NetworkingVmMapping
from keywords import vm_helper, nova_helper, host_helper, network_helper, cinder_helper, glance_helper

from testfixtures.resource_mgmt import ResourceCleanup


@fixture(scope='module')
def base_setup():

    flavor_id = nova_helper.create_flavor(name='dedicated')[1]
    ResourceCleanup.add('flavor', flavor_id, scope='module')

    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    internal_net_id = network_helper.get_internal_net_id()

    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': tenant_net_id, 'vif-model': 'virtio'},
            {'net-id': internal_net_id, 'vif-model': 'virtio'}
    ]
    base_vm = vm_helper.boot_vm(flavor=flavor_id, nics=nics)[1]
    ResourceCleanup.add('vm', base_vm, scope='module')

    return base_vm, mgmt_net_id, tenant_net_id, internal_net_id


@mark.sanity
@mark.parametrize('vif_model', [
    'avp',
    'e1000',
    'virtio'
])
def test_vif_models(vif_model, base_setup):
    """
    boot avp,e100 and virtio instance
    KNI is same as avp

    Test Steps:
        - boot up a vm with given vif model
        - Ping VM from Natbox(external network)
        - Ping from VM to itself over data network
        - Live-migrate the VM and verify ping over management and data networks
        - Cold-migrate the VM and verify ping over management and data networks
        - Pause and un-pause the VM and verify ping over management and data networks
        - Suspend and resume the VM and verify ping over management and data networks
        - Stop and start the VM and verify ping over management and data networks
        - Reboot the VM and verify ping over management and data networks

    Test Teardown:
        - Delete vm created
        - Delete flavor created

    """
    base_vm, mgmt_net_id, tenant_net_id, internal_net_id = base_setup

    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': tenant_net_id, 'vif-model': vif_model},
            {'net-id': internal_net_id, 'vif-model': 'avp'}]

    LOG.tc_step("Boot vm with vif_model {} for tenant-net".format(vif_model))
    vm_under_test = vm_helper.boot_vm(name=vif_model, nics=nics)[1]
    ResourceCleanup.add('vm', vm_under_test)

    LOG.tc_step("Ping VM {} from NatBox(external network)".format(vm_under_test))
    vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test, fail_ok=False)

    LOG.info("Ping vm's own data network ips")
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=vm_under_test, net_types='data')

    LOG.tc_step("Live-migrate the VM and verify ping over management and data networks")
    vm_helper.live_migrate_vm(vm_under_test)
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])

    LOG.tc_step("Cold-migrate the VM and verify ping over management and data networks")
    vm_helper.cold_migrate_vm(vm_under_test)
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])

    LOG.tc_step("Pause and un-pause the VM and verify ping over management and data networks")
    vm_helper.pause_vm(vm_under_test)
    vm_helper.unpause_vm(vm_under_test)
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])

    LOG.tc_step("Suspend and resume the VM and verify ping over management and data networks")
    vm_helper.suspend_vm(vm_under_test)
    vm_helper.resume_vm(vm_under_test)
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])

    LOG.tc_step("Stop and start the VM and verify ping over management and data networks")
    vm_helper.stop_vms(vm_under_test)
    vm_helper.start_vms(vm_under_test)
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])

    LOG.tc_step("Reboot the VM and verify ping over management and data networks")
    vm_helper.reboot_vm(vm_under_test)
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])
