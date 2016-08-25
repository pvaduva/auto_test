###
# test_468_lock_unlock_compute_node sanity_juno_unified_R3.xls
###
import time

from utils.tis_log import LOG
from testfixtures.recover_hosts import HostsToRecover
from testfixtures.resource_mgmt import ResourceCleanup

from keywords import host_helper, vm_helper, nova_helper


# Remove from sanity as it is already covered by system alarm-list/show sanity test cases
# Updated the test to lock with vm on host

# @mark.sanity
def test_lock_unlock_vm_host():
    """
    Verify lock unlock vm host

    Test Steps:
        - Boot a vm
        - Lock vm host and ensure it is locked successfully
        - Check vm is migrated to different host and in ACTIVE state
        - Unlock the selected hypervisor and ensure it is unlocked successfully with hypervisor state up

    """

    LOG.tc_step("Boot a vm that can be live-migrated")
    vm_id1 = vm_helper.boot_vm(name='lock_unlock_test')[1]
    ResourceCleanup.add('vm', vm_id1)

    LOG.tc_step("Boot a vm that cannot be live-migrated")
    flavor = nova_helper.create_flavor('swap1', swap=1)[1]
    ResourceCleanup.add('flavor', flavor)
    vm_id2 = vm_helper.boot_vm(name='volume_swap', flavor=flavor)[1]
    ResourceCleanup.add('vm', vm_id2)

    vm_host = nova_helper.get_vm_host(vm_id2)
    HostsToRecover.add(vm_host)

    if nova_helper.get_vm_host(vm_id1) != vm_host:
        vm_helper.live_migrate_vm(vm_id1, destination_host=vm_host)

    # lock compute node and verify compute node is successfully unlocked
    LOG.tc_step("Lock vm host {} and ensure it is locked successfully".format(vm_host))
    host_helper.lock_host(vm_host, check_first=False)

    LOG.tc_step("Check vms are migrated to different host and in ACTIVE state")
    for vm in [vm_id1, vm_id2]:
        post_vm_host = nova_helper.get_vm_host(vm)
        assert post_vm_host != vm_host, "VM {} host did not change even though vm host is locked".format(vm)

        post_vm_status = nova_helper.get_vm_status(vm).upper()
        assert 'ACTIVE' == post_vm_status, "VM {} status is {} instead of ACTIVE".format(vm, post_vm_status)

    # wait for services to stabilize before unlocking
    time.sleep(10)

    # unlock compute node and verify compute node is successfully unlocked
    LOG.tc_step("Unlock {} and ensure it is unlocked successfully with hypervisor state up".format(vm_host))
    host_helper.unlock_host(vm_host, check_hypervisor_up=True)
