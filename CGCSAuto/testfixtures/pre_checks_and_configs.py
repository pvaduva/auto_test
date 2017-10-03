import time
from pytest import fixture, skip

from utils.tis_log import LOG
from consts.auth import Tenant
from consts.reasons import SkipReason
from consts.cgcs import EventLogID, HostAvailabilityState
from keywords import system_helper, host_helper, keystone_helper, security_helper


@fixture(scope='session')
def no_simplex():
    LOG.fixture_step("(Session) Skip if Simplex")
    if system_helper.is_simplex():
        skip(SkipReason.SIMPLEX_SYSTEM)


@fixture(scope='session')
def simplex_only():
    LOG.fixture_step("(Session) Skip if not Simplex")
    if not system_helper.is_simplex():
        skip(SkipReason.SIMPLEX_ONLY)


@fixture(scope='module')
def check_numa_num():
    proc_num = 2
    if system_helper.is_simplex():
        procs = host_helper.get_host_procs('controller-0')
        proc_num = len(procs)

    return proc_num


@fixture(scope='session')
def wait_for_con_drbd_sync_complete():
    if len(system_helper.get_controllers()) < 2:
        LOG.info("Less than two controllers on system. Do not wait for drbd sync")
        return False

    host = 'controller-1'
    LOG.fixture_step("Waiting for controller-1 drbd sync alarm gone if present")
    end_time = time.time() + 1200
    while time.time() < end_time:
        drbd_alarms = system_helper.get_alarms(alarm_id=EventLogID.CON_DRBD_SYNC, reason_text='drbd-',
                                               entity_id=host, strict=False)

        if not drbd_alarms:
            LOG.info("{} drbd sync alarm is cleared".format(host))
            break
        time.sleep(10)

    else:
        assert False, "drbd sync alarm {} is not cleared within timeout".format(EventLogID.CON_DRBD_SYNC)

    LOG.fixture_step("Wait for {} becomes available in system host-list".format(host))
    host_helper.wait_for_host_states(host, availability=HostAvailabilityState.AVAILABLE, timeout=30, fail_ok=False)

    LOG.fixture_step("Wait for {} drbd-cinder in sm-dump to reach desired state".format(host))
    host_helper.wait_for_sm_dump_desired_states(host, 'drbd-', strict=False, timeout=30, fail_ok=False)
    return True


@fixture(scope='session')
def change_admin_password_session(request, wait_for_con_drbd_sync_complete):
    more_than_one_controllers = wait_for_con_drbd_sync_complete
    prev_pswd = Tenant.ADMIN['password']
    post_pswd = '!{}9'.format(prev_pswd)

    LOG.fixture_step('(Session) Changing admin password to {}'.format(post_pswd))
    keystone_helper.update_user('admin', password=post_pswd)

    def _lock_unlock_controllers():
        LOG.fixture_step("Sleep for 120 seconds after admin password change")
        time.sleep(120)  # CGTS-6928
        if more_than_one_controllers:
            active, standby = system_helper.get_active_standby_controllers()
            if standby:
                LOG.fixture_step("(Session) Locking unlocking controllers to complete action")
                host_helper.lock_host(standby)
                host_helper.unlock_host(standby)

                host_helper.lock_host(active, swact=True)
                host_helper.unlock_host(active)
            else:
                LOG.warning("Standby controller unavailable. Skip lock unlock controllers post admin password change.")
        elif system_helper.is_simplex():
            LOG.fixture_step("(Session) Simplex lab - lock/unlock controller to complete action")
            host_helper.lock_host('controller-0', swact=False)
            host_helper.unlock_host('controller-0')

    def revert_pswd():
        LOG.fixture_step("(Session) Reverting admin password to {}".format(prev_pswd))
        keystone_helper.update_user('admin', password=prev_pswd)
        _lock_unlock_controllers()

        LOG.fixture_step("(Session) Check admin password is reverted to {} in keyring".format(prev_pswd))
        assert prev_pswd == security_helper.get_admin_password_in_keyring()
    request.addfinalizer(revert_pswd)

    _lock_unlock_controllers()

    LOG.fixture_step("(Session) Check admin password is changed to {} in keyring".format(post_pswd))
    assert post_pswd == security_helper.get_admin_password_in_keyring()

    return post_pswd
