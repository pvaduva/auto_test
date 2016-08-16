###
# test_467_lock_unlock_compute_node sanity_juno_unified_R3.xls
###

from pytest import mark

from time import sleep
from utils.tis_log import LOG
from keywords import host_helper,system_helper


@mark.sanity
def test_lock_unlock_inactive_controller():
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
    host_helper.lock_host(standby_controller)

    # wait for services to stabilize before unlocking
    sleep(20)

    # unlock standby controller node and verify controller node is successfully unlocked
    LOG.tc_step("Unlock standby controller and ensure it is successfully unlocked with web-services up")
    host_helper.unlock_host(standby_controller)
