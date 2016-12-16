import time
from pytest import fixture

from utils.tis_log import LOG
from consts.cgcs import EventLogID
from keywords import system_helper


@fixture(scope='session')
def wait_for_con_drdb_sync_complete():

    LOG.fixture_step("Waiting for controller-1 drbd sync alarm gone if present")
    end_time = time.time() + 1200
    while time.time() < end_time:
        drbd_alarms = system_helper.get_alarms(alarm_id=EventLogID.CON_DRBD_SYNC, reason_text='drbd-',
                                               entity_id='controller-1', strict=False)

        if not drbd_alarms:
            return True

        time.sleep(10)

    LOG.warning("controller-1 drbd sync alarm 400.001 still exists on system")
    return False
