###
# test_467_lock_unlock_compute_node sanity_juno_unified_R3.xls
###
import time
from pytest import mark, skip

from utils.tis_log import LOG
from utils.kpi import kpi_log_parser
from consts.kpi_vars import HostLock, HostUnlock, KPI_DATE_FORMAT
from testfixtures.recover_hosts import HostsToRecover
from testfixtures.fixture_resources import ResourceCleanup
from testfixtures.pre_checks_and_configs import no_simplex

from keywords import host_helper,system_helper, nova_helper, vm_helper, common


@mark.sanity
@mark.cpe_sanity
def test_lock_active_controller_reject(no_simplex):
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


@mark.parametrize('host_type', [
    mark.priorities('sanity', 'cpe_sanity', 'kpi')('controller'),
    mark.priorities('kpi')('compute'),
    mark.priorities('kpi')('storage'),
])
def test_lock_unlock_host(host_type, no_simplex, collect_kpi):
    """
    Verify lock unlock host

    Test Steps:
        - Select a host per given type. If type is controller, select standby controller.
        - Lock selected host and ensure it is successfully locked
        - Unlock selected host and ensure it is successfully unlocked

    """
    init_time = None
    if collect_kpi:
        init_time = common.get_date_in_format(date_format=KPI_DATE_FORMAT)

    if host_type == 'controller':
        LOG.tc_step('Retrieve the standby controller from system')
        host = system_helper.get_standby_controller_name()

        assert host, "No standby controller available"
    elif host_type == 'compute':
        if system_helper.is_small_footprint():
            skip("No compute host on AIO system")

        LOG.tc_step("Get a compute host from system")
        hosts = host_helper.get_up_hypervisors()
        assert hosts, "No hypervisor is up on system"
        host = hosts[0]
    elif host_type == 'storage':
        storage_nodes = system_helper.get_storage_nodes()
        if not storage_nodes:
            skip("No storage node on system")
        host = storage_nodes[0]
    else:
        raise ValueError("Unrecognized host_type: {}".format(host_type))

    # lock standby controller node and verify it is successfully locked
    LOG.tc_step("Lock {} host - {} and ensure it is successfully locked".format(host_type, host))
    host_helper.lock_host(host, swact=False)

    locked_controller_admin_state = host_helper.get_hostshow_value(host, 'administrative')
    assert locked_controller_admin_state == 'locked', 'Test Failed. Standby Controller {} should be in locked ' \
                                                      'state but is not.'.format(host)

    # wait for services to stabilize before unlocking
    time.sleep(20)

    # unlock standby controller node and verify controller node is successfully unlocked
    LOG.tc_step("Unlock {} host - {} and ensure it is successfully unlocked".format(host_type, host))
    host_helper.unlock_host(host)

    unlocked_controller_admin_state = host_helper.get_hostshow_value(host,'administrative')
    assert unlocked_controller_admin_state == 'unlocked', 'Test Failed. Standby Controller {} should be in unlocked ' \
                                                          'state but is not.'.format(host)

    if collect_kpi:
        LOG.info("Collect kpi for lock/unlock {}".format(host_type))
        kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=HostLock.NAME.format(host_type), host=None,
                                  log_path=HostLock.LOG_PATH, end_pattern=HostLock.END.format(host),
                                  start_pattern=HostLock.START.format(host), start_path=HostLock.START_PATH,
                                  init_time=init_time)

        kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=HostUnlock.NAME.format(host_type), host=None,
                                  log_path=HostUnlock.LOG_PATH, end_pattern=HostUnlock.END[host_type].format(host),
                                  init_time=init_time, start_pattern=HostUnlock.START.format(host),
                                  start_path=HostUnlock.START_PATH)


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

    LOG.tc_step("Boot a vm that cannot be live-migrated")
    flavor = nova_helper.create_flavor('swap512', swap=512)[1]
    ResourceCleanup.add('flavor', flavor)
    vm_id2 = vm_helper.boot_vm(name='volume_swap', flavor=flavor, cleanup='function')[1]

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
