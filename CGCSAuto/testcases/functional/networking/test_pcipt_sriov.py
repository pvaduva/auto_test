from pytest import fixture, mark, skip

from utils import table_parser, cli, exceptions
from utils.tis_log import LOG

from consts.auth import Tenant
from consts.cgcs import VMStatus, FlavorSpec, NetworkingVmMapping
from keywords import vm_helper, nova_helper, host_helper, network_helper, cinder_helper, common

from testfixtures.resource_mgmt import ResourceCleanup


@mark.skipif(True, reason="Update required")
@mark.parametrize(('vm_type', 'resource_usage'), [
    ('pcipt', 'pci_vfs_used'),
    ('sriov', 'pci_pfs_used')
])
def incomplete_test_sriov_pcipt_with_vm_actions(vm_type, resource_usage):
    """
    <summary>

    Test Steps:
        - boot a vm via lab_setup script for sriov & pcipt
        - resize the vm with the flavor created
        - Ping VM from Natbox(external network)
        - Ping from VM to 8.8.8.8
        - Live-migrate the VM and verify ping from VM
        - Cold-migrate the VM and verify ping from VM
        - Pause and un-pause the VM and verify ping from VM
        - Suspend and resume the VM and verify ping from VM
        - Stop and start the VM and verify ping from VM
        - Reboot the VM and verify ping from VM
        - Check the resource usage is not changed after VM operation

    Test Teardown:
        - Delete vm created
    """

    LOG.tc_step("Get the actual resource used {} ".format('resource_usage'))
    pnet_id = network_helper.get_provider_net_xxx(vm_type='vm_type') ## need input from yang
    pnet_id = network_helper.get_provider_net_for_interface(interface='vm_type')
    LOG.tc_step("Get the actual resource used {} ".format('resource_usage'))


    LOG.tc_step("Boot vm vif_model {} ".format(vm_type))
    vms = vm_helper.launch_vms_via_script(vm_type='vm_type')
    for vm in vms:
        ResourceCleanup.add('vm', vm)
    increment_value = len(vms)


    if not pnet_id:
        skip("The lab does not support {}".format(vm_type))

    actual_resource_value = nova_helper.get_provider_net_info(pnet_id, field='resource_usage')

    if actual_resource_value == increment_value:
        LOG.tc_step("Tne resource usage {} is equal to expected value {}".format(actual_resource_value, increment_value))
    else:
        assert actual_resource_value == increment_value, "The resource usage is not equal to expected value"
        LOG.tc_step("The resource usage {} is not equal to expected value {}".format(actual_resource_value, increment_value))

    LOG.tc_step("Ping VM {} from NatBox".format(vms))
    vm_helper.wait_for_vm_pingable_from_natbox(vms)

    LOG.tc_step("Ping from VM to external ip 8.8.8.8")
    vm_helper.ping_ext_from_vm(vms)

    LOG.tc_step("Live-migrate the VM and verify ping from VM")
    vm_helper.live_migrate_vm(vms)
    vm_helper.ping_ext_from_vm(vms)

    LOG.tc_step("Cold-migrate the VM and verify ping from VM")
    vm_helper.cold_migrate_vm(vms)
    vm_helper.ping_ext_from_vm(vms)

    LOG.tc_step("Pause and un-pause the VM and verify ping from VM")
    vm_helper.pause_vm(vms)
    vm_helper.unpause_vm(vms)
    vm_helper.ping_ext_from_vm(vms)

    LOG.tc_step("Suspend and resume the VM and verify ping from VM")
    vm_helper.suspend_vm(vms)
    vm_helper.resume_vm(vms)
    vm_helper.ping_ext_from_vm(vms)

    LOG.tc_step("Stop and start the VM and verify ping from VM")
    vm_helper.stop_vms(vms)
    vm_helper.start_vms(vms)
    vm_helper.ping_ext_from_vm(vms)

    LOG.tc_step("Reboot the VM and verify ping from VM")
    vm_helper.reboot_vm(vms)
    vm_helper.ping_ext_from_vm(vms)

    if actual_resource_value == increment_value:
        LOG.tc_step("Tne resource usage {} is equal to expected value {} after VM actions".format(actual_resource_value, increment_value))
    else:
        assert actual_resource_value == increment_value, "The resource usage is not equal to expected value after VM actions"
        LOG.tc_step("The resource usage {} is not equal to expected value {}".format(actual_resource_value, increment_value))


