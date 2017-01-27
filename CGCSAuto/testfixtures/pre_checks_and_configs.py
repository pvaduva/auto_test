import time
from pytest import fixture

from utils.tis_log import LOG
from consts.auth import Tenant
from consts.cgcs import EventLogID, HostAvailabilityState
from keywords import system_helper, host_helper, keystone_helper


@fixture(scope='session')
def wait_for_con_drbd_sync_complete():

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
    host_helper._wait_for_host_states(host, availability=HostAvailabilityState.AVAILABLE, timeout=30, fail_ok=False)

    LOG.fixture_step("Wait for {} drbd-cinder in sm-dump to reach desired state".format(host))
    host_helper.wait_for_sm_dump_desired_states(host, 'drbd-', strict=False, timeout=30, fail_ok=False)


@fixture(scope='session')
def change_admin_password_session(request, wait_for_con_drbd_sync_complete):
    prev_pswd = Tenant.ADMIN['password']
    post_pswd = "'!{}9'".format(prev_pswd)

    LOG.fixture_step('(Session) Changing admin password to {}'.format(post_pswd))
    keystone_helper.update_user('admin', password=post_pswd)

    def _lock_unlock_controllers():
        active, standby = system_helper.get_active_standby_controllers()
        if standby:
            LOG.fixture_step("(Session) Locking unlocking controllers to complete action")
            host_helper.lock_host(standby)
            host_helper.unlock_host(standby)

            host_helper.lock_host(active, swact=True)
            host_helper.unlock_host(active)

    def revert_pswd():
        LOG.fixture_step("(Session) Reverting admin password to {}".format(prev_pswd))
        keystone_helper.update_user('admin', password=prev_pswd)
        _lock_unlock_controllers()
    request.addfinalizer(revert_pswd)

    _lock_unlock_controllers()

    return post_pswd
