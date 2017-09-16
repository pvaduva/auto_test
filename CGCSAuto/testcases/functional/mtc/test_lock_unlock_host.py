###
# test_467_lock_unlock_compute_node sanity_juno_unified_R3.xls
###
import time
from pytest import mark, skip

from utils.tis_log import LOG
from testfixtures.recover_hosts import HostsToRecover
from testfixtures.fixture_resources import ResourceCleanup
from testfixtures.pre_checks_and_configs import no_simplex_module

from keywords import host_helper,system_helper, nova_helper, vm_helper


@mark.sanity
@mark.cpe_sanity
def test_lock_active_controller_reject(no_simplex_module):
    """
    Verify lock unlock active controller. Expected it to fail

    Test Steps:
        - Get active controller
        - Attempt to lock active controller and ensure it's rejected

    """
    LOG.tc_step('Retrieve the active controller from the lab')
    active_controller = system_helper.get_active_controller_name()

    assert active_controller, "No active controller available"

    # lock standby controller node and verify it is successfully locked
    LOG.tc_step("Lock active controller and ensure it fail to lock")
    exit_code, cmd_output = host_helper.lock_host(active_controller, fail_ok=True, swact=False, check_first=False)
    assert exit_code == 1, 'Expect locking active controller to be rejected. Actual: {}'.format(cmd_output)

    status = host_helper.get_hostshow_value(active_controller, 'administrative')
    assert status == 'unlocked', "Fail: The active controller was locked."


@mark.sanity
@mark.cpe_sanity
def test_lock_unlock_standby_controller(no_simplex_module):
    """
    Verify lock unlock standby controller

    Test Steps:
        - Get standby controller
        - Lock standby controller and ensure it is successfully locked
        - Unlock standby controller and ensure it is successfully unlocked with web-services up

    """
    LOG.tc_step('Retrieve the standby controller from the lab')
    standby_controller = system_helper.get_standby_controller_name()

    assert standby_controller, "No standby controller available"

    # lock standby controller node and verify it is successfully locked
    LOG.tc_step("Lock standby controller and ensure it is successfully locked")
    host_helper.lock_host(standby_controller, swact=False)

    locked_controller_admin_state = host_helper.get_hostshow_value(standby_controller, 'administrative')
    assert locked_controller_admin_state == 'locked', 'Test Failed. Standby Controller {} should be in locked ' \
                                                      'state but is not.'.format(standby_controller)

    # wait for services to stabilize before unlocking
    time.sleep(20)

    # unlock standby controller node and verify controller node is successfully unlocked
    LOG.tc_step("Unlock standby controller and ensure it is successfully unlocked with web-services up")
    host_helper.unlock_host(standby_controller)

    unlocked_controller_admin_state = host_helper.get_hostshow_value(standby_controller,'administrative')
    assert unlocked_controller_admin_state == 'unlocked', 'Test Failed. Standby Controller {} should be in unlocked ' \
                                                          'state but is not.'.format(standby_controller)


# Remove since it's already covered by test_lock_with_vms
# @mark.sanity
def _test_lock_unlock_vm_host():
    """
    Verify lock unlock vm host

    Test Steps:
        - Boot a vm
        - Lock vm host and ensure it is locked successfully
        - Check vm is migrated to different host and in ACTIVE state
        - Unlock the selected hypervisor and ensure it is unlocked successfully with hypervisor state up

    """

    LOG.tc_step("Boot a vm that can be live-migrated")
    vm_id1 = vm_helper.boot_vm(name='lock_unlock_test', cleanup='function')[1]
    # ResourceCleanup.add('vm', vm_id1)

    LOG.tc_step("Boot a vm that cannot be live-migrated")
    flavor = nova_helper.create_flavor('swap1', swap=1)[1]
    ResourceCleanup.add('flavor', flavor)
    vm_id2 = vm_helper.boot_vm(name='volume_swap', flavor=flavor, cleanup='function')[1]
    # ResourceCleanup.add('vm', vm_id2)

    vm_host = nova_helper.get_vm_host(vm_id2)
    HostsToRecover.add(vm_host)

    if nova_helper.get_vm_host(vm_id1) != vm_host:
        vm_helper.live_migrate_vm(vm_id1, destination_host=vm_host)

    # lock compute node and verify compute node is successfully unlocked
    LOG.tc_step("Lock vm host {} and ensure it is locked successfully".format(vm_host))
    host_helper.lock_host(vm_host, check_first=False, swact=True)

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
