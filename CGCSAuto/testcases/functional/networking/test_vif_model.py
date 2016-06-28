
from pytest import fixture, mark
from time import sleep

from utils import table_parser, cli, exceptions
from utils.tis_log import LOG

from consts.auth import Tenant
from consts.cgcs import VMStatus, FlavorSpec, NetworkingVmMapping
from keywords import vm_helper, nova_helper, host_helper, network_helper, cinder_helper, glance_helper

from testfixtures.resource_mgmt import ResourceCleanup

@mark.parametrize('vif_model', ['avp','e1000','virtio'])
def test_avp_vms_with_vm_actions(vif_model):
    """
    boot avp,e100 and virtio instance
    KNI is same as avp


    Test Steps:
        - boot up a vm
        - Ping VM from Natbox(external network)
        - Ping from VM to 8.8.8.8
        - Live-migrate the VM and verify ping from VM
        - Cold-migrate the VM and verify ping from VM
        - Pause and un-pause the VM and verify ping from VM
        - Suspend and resume the VM and verify ping from VM
        - Stop and start the VM and verify ping from VM
        - Reboot the VM and verify ping from VM

    Test Teardown:
        - Delete vm created
        - Delete flavor created

    """

    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': tenant_net_id, 'vif-model': vif_model}]

    LOG.tc_step("Boot vm with vif_model {} for tenant-net".format(vif_model))
    sourceid = glance_helper.get_image_id_from_name('cgcs-guest')
    vm = vm_helper.boot_vm(source='image', source_id=sourceid, nics=nics)[1]
    ResourceCleanup.add('vm', vm)
    sleep(10)
    LOG.tc_step("Ping VM {} from NatBox(external network)".format(vm))
    vm_helper.ping_vms_from_natbox(vm)

    #LOG.tc_step("Ping from VM to external ip 8.8.8.8")
    #vm_helper.ping_ext_from_vm(vm)

    LOG.tc_step("Live-migrate the VM and verify ping from VM")
    vm_helper.live_migrate_vm(vm)
    vm_helper.ping_ext_from_vm(vm)

    LOG.tc_step("Cold-migrate the VM and verify ping from VM")
    vm_helper.cold_migrate_vm(vm)
    vm_helper.ping_ext_from_vm(vm)

    LOG.tc_step("Pause and un-pause the VM and verify ping from VM")
    vm_helper.pause_vm(vm)
    vm_helper.unpause_vm(vm)
    vm_helper.ping_ext_from_vm(vm)

    LOG.tc_step("Suspend and resume the VM and verify ping from VM")
    vm_helper.suspend_vm(vm)
    vm_helper.resume_vm(vm)
    vm_helper.ping_ext_from_vm(vm)

    #LOG.tc_step("Stop and start the VM and verify ping from VM")
    #vm_helper.stop_vms(vm)
    #vm_helper.start_vms(vm)
    #vm_helper.ping_ext_from_vm(vm)

    LOG.tc_step("Reboot the VM and verify ping from VM")
    vm_helper.reboot_vm(vm)
    vm_helper.ping_ext_from_vm(vm)
