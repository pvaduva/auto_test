###
# test_467_lock_unlock_compute_node sanity_juno_unified_R3.xls
###
import time
from pytest import mark, skip, param

from utils.tis_log import LOG
from utils.kpi import kpi_log_parser
from consts.stx import HostOperState, HostAvailState
from consts.kpi_vars import HostLock, HostUnlock, KPI_DATE_FORMAT
from testfixtures.recover_hosts import HostsToRecover
from keywords import host_helper, system_helper, common, container_helper


@mark.platform_sanity
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
    exit_code, cmd_output = host_helper.lock_host(active_controller, fail_ok=True, swact=False,
                                                  check_first=False)
    assert exit_code == 1, 'Expect locking active controller to be rejected. ' \
                           'Actual: {}'.format(cmd_output)
    status = system_helper.get_host_values(active_controller, 'administrative')[0]
    assert status == 'unlocked', "Fail: The active controller was locked."


@mark.parametrize('host_type', [
    param('controller', marks=mark.priorities('platform_sanity', 'kpi')),
    param('compute', marks=mark.priorities('platform_sanity', 'kpi')),
    param('storage', marks=mark.priorities('platform_sanity', 'kpi')),
])
def test_lock_unlock_host(host_type, collect_kpi):
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

    LOG.tc_step("Select a {} node from system if any".format(host_type))
    if host_type == 'controller':
        if system_helper.is_aio_simplex():
            host = 'controller-0'
        else:
            host = system_helper.get_standby_controller_name()
            assert host, "No standby controller available"

    else:
        if host_type == 'compute' and (system_helper.is_aio_duplex() or
                                       system_helper.is_aio_simplex()):
            skip("No compute host on AIO system")
        elif host_type == 'storage' and not system_helper.is_storage_system():
            skip("System does not have storage nodes")

        hosts = system_helper.get_hosts(personality=host_type,
                                        availability=HostAvailState.AVAILABLE,
                                        operational=HostOperState.ENABLED)

        assert hosts, "No good {} host on system".format(host_type)
        host = hosts[0]

    LOG.tc_step("Lock {} host - {} and ensure it is successfully locked".format(host_type, host))
    HostsToRecover.add(host)
    host_helper.lock_host(host, swact=False)

    # wait for services to stabilize before unlocking
    time.sleep(20)

    # unlock standby controller node and verify controller node is successfully unlocked
    LOG.tc_step("Unlock {} host - {} and ensure it is successfully unlocked".format(host_type,
                                                                                    host))
    host_helper.unlock_host(host)

    if collect_kpi:
        lock_kpi_name = HostLock.NAME.format(host_type)
        unlock_kpi_name = HostUnlock.NAME.format(host_type)
        unlock_host_type = host_type
        if container_helper.is_stx_openstack_deployed():
            if system_helper.is_aio_system():
                unlock_host_type = 'compute'
        else:
            lock_kpi_name += '_platform'
            unlock_kpi_name += '_platform'
            if unlock_host_type == 'compute':
                unlock_host_type = 'compute_platform'

        LOG.info("Collect kpi for lock/unlock {}".format(host_type))

        if not container_helper.is_stx_openstack_deployed():
            lock_kpi_name += '_platform'
            unlock_kpi_name += '_platform'

        code_lock, out_lock = kpi_log_parser.record_kpi(
            local_kpi_file=collect_kpi,
            kpi_name=lock_kpi_name,
            host=None, log_path=HostLock.LOG_PATH,
            end_pattern=HostLock.END.format(host),
            start_pattern=HostLock.START.format(host),
            start_path=HostLock.START_PATH,
            init_time=init_time)

        time.sleep(30)      # delay in sysinv log vs nova hypervisor list
        code_unlock, out_unlock = kpi_log_parser.record_kpi(
            local_kpi_file=collect_kpi,
            kpi_name=unlock_kpi_name, host=None,
            log_path=HostUnlock.LOG_PATH,
            end_pattern=HostUnlock.END[unlock_host_type].format(host),
            init_time=init_time,
            start_pattern=HostUnlock.START.format(host),
            start_path=HostUnlock.START_PATH)

        assert code_lock == 0, 'Failed to collect kpi for host-lock {}. ' \
                               'Error: \n'.format(host, out_lock)
        assert code_unlock == 0, 'Failed to collect kpi for host-unlock {}. ' \
                                 'Error: \n'.format(host, out_lock)
