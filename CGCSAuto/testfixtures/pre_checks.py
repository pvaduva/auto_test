import time
from pytest import fixture

from utils.tis_log import LOG
from consts.cgcs import EventLogID, HostAvailabilityState
from keywords import system_helper, host_helper, common


@fixture(scope='session')
def wait_for_con_drdb_sync_complete():

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
    host_helper.wait_for_sm_dump_desired_state(host, 'drbd-cinder', timeout=30, fail_ok=False)
