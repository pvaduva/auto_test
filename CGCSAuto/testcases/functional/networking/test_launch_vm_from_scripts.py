
from pytest import fixture, mark
from utils.tis_log import LOG
from consts.cgcs import VMStatus
from keywords import vm_helper, nova_helper, network_helper

from testfixtures.resource_mgmt import ResourceCleanup


# @mark.parametrize('vm_type', ['avp', 'virtio', 'vswitch'])
@mark.parametrize('vm_type', ['vswitch'])
def test_vif_models(vm_type):
    """
    boot avp,e100 and virtio instance
    KNI is same as avp

    Test Steps:
        - boot up a vm with given vm type from script
        - boot up a base vm with given vm type from script
        - Ping VM from Natbox(external network)
        - Live-migrate the VM and verify ping over management and data networks
        - Cold-migrate the VM and verify ping over management and data networks
        - Pause and un-pause the VM and verify ping over management and data networks
        - Suspend and resume the VM and verify ping over management and data networks
        - Stop and start the VM and verify ping over management and data networks
        - Reboot the VM and verify ping over management and data networks

    Test Teardown:
        - Delete vm created

    """

    LOG.tc_step("Boot vm to test with vm_type {} from script".format(vm_type))
    vm_under_test = vm_helper.launch_vms_via_script(vm_type=vm_type)[0]
    ResourceCleanup.add('vm', vm_under_test)

    LOG.tc_step("Boot a base vm to test with vm_type {} from script".format(vm_type))
    base_vm = vm_helper.launch_vms_via_script(vm_type=vm_type, tenant_name='tenant1')
    ResourceCleanup.add('vm', base_vm)

    LOG.tc_step("Ping VM {} from NatBox(external network)".format(vm_under_test))
    vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test, fail_ok=False)

    for vm_actions in [['cold_migrate'], ['live_migrate'],  ['pause', 'unpause'], ['suspend', 'resume'], ['stop', 'start']]:
        if vm_actions[0] == 'auto_recover':
            LOG.tc_step("Set vm to error state and wait for auto recovery complete, then verify ping from "
                        "base vm over management and data networks")
            vm_helper.set_vm_state(vm_id=vm_under_test, error_state=True, fail_ok=False)
            vm_helper.wait_for_vm_values(vm_id=vm_under_test, status=VMStatus.ACTIVE, fail_ok=True, timeout=600)
        else:
            LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm_under_test, vm_actions))
            for action in vm_actions:
                vm_helper.perform_action_on_vm(vm_under_test, action=action)

        # vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test)

        LOG.tc_step("Verify ping from base_vm to vm_under_test over management networks still works "
                    "after {}".format(vm_actions))
        vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt'])

        # if vm_type != 'vswitch':
        #     LOG.tc_step("Verify ping from base_vm to vm_under_test over data networks still works after {}"
        #                 .format(vm_actions))
        #     vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['data'])