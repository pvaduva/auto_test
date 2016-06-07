from  pytest import fixture
from keywords import network_helper
from utils.tis_log import LOG
from keywords import vm_helper
from testfixtures.resource_mgmt import ResourceCleanup
_skip = True
##############################################
# us57685_Test Strategy for US57685_AVR_FIP (Accelerated Virtual router Floating IP) #
##############################################
@fixture(scope='module', autouse=True)
def fip_setups(request):
    # Create FIP and Associate VM to FIP
    retcode, floating_ip = network_helper.create_floatingip(extnet_id=None)

    def disassoicate_fip():
        network_helper.disassociate_floatingip(floating_ip)
    # Boot VM with FIP
    request.addfinalizer(disassoicate_fip)
    vm_id = vm_helper.boot_vm()[1]
    network_helper.associate_floatingip(floating_ip=floating_ip, vm=vm_id)
    ResourceCleanup.add('vm', vm_id, scope='module')
    return vm_id, floating_ip


def test_fip(fip_setups):
    """
	Test VM Floating IP  over VM launch, live-migration, cold-migration, pause/unpause, etc

	Args:
		vm_ (str): vm created by module level test fixture

	Test Setups:
		- boot a vm from volume and ping vm from NatBox     (module)

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
	    - Disassoicate FIP
		- Delete the created vm

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





