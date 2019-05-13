from pytest import fixture

from utils.tis_log import LOG
from keywords import network_helper, vm_helper


######################################################################################
# us57685_Test Strategy for US57685_AVR_FIP (Accelerated Virtual router Floating IP) #
######################################################################################


@fixture(scope='module', autouse=True)
def fip_setups():
    # Create FIP and Associate VM to FIP
    floating_ip = network_helper.create_floating_ip(cleanup='module')[1]
    vm_id = vm_helper.boot_vm(cleanup='module')[1]

    network_helper.associate_floating_ip_to_vm(floating_ip=floating_ip, vm_id=vm_id)

    return vm_id, floating_ip


def obsolete_test_fip(fip_setups):
    """
    Test VM Floating IP  over VM launch, live-migration, cold-migration, pause/unpause, etc

    Args:
        fip_setups: test fixture

    Test Setups (module):
        - Create a floating ip
        - boot a vm
        - Attach floating ip to vm

    Test Steps:
        - Ping  VM FIP
        - Live-migrate the VM and verify ping from VM
        - Cold-migrate the VM and verify ping from VM
        - Pause and un-pause the VM and verify ping from VM
        - Suspend and resume the VM and verify ping from VM
        - Stop and start the VM and verify ping from VM
        - Reboot the VM and verify ping from VM
        - Ping  VM FIP

    Test Teardown:
        - Delete created FIP and vm (module)

    """
    vm_id, fip = fip_setups
    LOG.tc_step("Ping VM with Floating IP ")
    vm_helper.ping_ext_from_vm(vm_id, use_fip=True)

    LOG.tc_step("Live-migrate the VM and verify ping from VM")
    vm_helper.live_migrate_vm(vm_id)
    vm_helper.ping_ext_from_vm(vm_id, use_fip=True)

    LOG.tc_step("Cold-migrate the VM and verify ping from VM")
    vm_helper.cold_migrate_vm(vm_id)
    vm_helper.ping_ext_from_vm(vm_id, use_fip=True)

    LOG.tc_step("Pause and un-pause the VM and verify ping from VM")
    vm_helper.pause_vm(vm_id)
    vm_helper.unpause_vm(vm_id)
    vm_helper.ping_ext_from_vm(vm_id, use_fip=True)

    LOG.tc_step("Suspend and resume the VM and verify ping from VM")
    vm_helper.suspend_vm(vm_id)
    vm_helper.resume_vm(vm_id)
    vm_helper.ping_ext_from_vm(vm_id, use_fip=True)

    LOG.tc_step("Stop and start the VM and verify ping from VM")
    vm_helper.stop_vms(vm_id)
    vm_helper.start_vms(vm_id)
    vm_helper.ping_ext_from_vm(vm_id, use_fip=True)

    LOG.tc_step("Reboot the VM and verify ping from VM")
    vm_helper.reboot_vm(vm_id)
    vm_helper.ping_ext_from_vm(vm_id, use_fip=True)

    LOG.tc_step("Ping VM with Floating IP Ensure FIP reachable ")
    vm_helper.ping_ext_from_vm(vm_id, use_fip=True)
