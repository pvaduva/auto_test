import time

from pytest import fixture, skip, mark
from utils.tis_log import LOG
from keywords import host_helper, system_helper
from consts import timeout
from testfixtures.recover_hosts import HostsToRecover


def test_swact_standby_controller_negative():
    """
    TC610_2
    Verify that trying to swact a standby controller is rejected

    Test Steps:
        - Get the standby controller
        - Attempt to swact the controller
        - Verify that the swact doesn't happen

    """
    standby = system_helper.get_standby_controller_name()
    active = system_helper.get_active_controller_name()
    LOG.tc_step("Attempting to swact from standby controller {}".format(standby))
    code, out = host_helper.swact_host(standby, fail_ok=True)
    LOG.tc_step("Verifying that the swact didn't occur.")
    assert 0 != code, "FAIL: The swact wasn't rejected"
    curr_active = system_helper.get_active_controller_name()
    assert curr_active == active, "FAIL: The active controller was changed. " \
                                  "Previous: {} Current: {}".format(active, curr_active)


@fixture(scope='function')
def fail_controller(request):
    standby = system_helper.get_standby_controller_name()
    host_helper.reboot_hosts(standby, wait_for_reboot_finish=False)

    HostsToRecover.add(standby, scope='function')

    # def wait_for_controller():
    #     check_interval = 10
    #     LOG.fixture_step("Waiting for {} to reboot".format(standby))
    #     end_time = time.time() + timeout.HostTimeout.REBOOT
    #     while True:
    #         state = host_helper.get_hostshow_values(standby, None, 'availability', 'operational')
    #         if 'available' == state['availability'] and 'enabled' == state['operational']:
    #             LOG.info("{} has finished rebooting".format(standby))
    #             break
    #         if time.time() > end_time:
    #             assert 0 == 1, "FAIL: The controller hasn't rebooted"
    #         time.sleep(check_interval)
    #
    # request.addfinalizer(wait_for_controller)
    return True


def test_swact_failed_controller_negative(fail_controller):
    """
    TC610_3
    Verify that swacting to a failed controller is rejected

    Test Setup:
        - Reset the standby controller

    Test Steps:
        - Attempt to swact from the active controller
        - Verify that the swact was rejected and the active controller is the same

    Teardown:
        - Wait until the controller is online again

    Returns:

    """
    if not fail_controller:
        skip("Couldn't put controller into failed state.")

    active = system_helper.get_active_controller_name()
    LOG.tc_step("Attempting to swact to failed controller.")
    code, out = host_helper.swact_host(fail_ok=True)
    LOG.tc_step("Verifying that the swact didn't occur.")
    assert 1 == code, "FAIL: The swact wasn't rejected"
    curr_active = system_helper.get_active_controller_name()
    assert curr_active == active, "FAIL: The active controller was changed. " \
                                  "Previous: {} Current: {}".format(active, curr_active)


@fixture(scope='function')
def lock_controller(request):
    standby = system_helper.get_standby_controller_name()
    code, out = host_helper.lock_host(standby)

    def unlock_controller():
        host_helper.unlock_host(standby)

    request.addfinalizer(unlock_controller)

    if code == 0 or code == -1:
        return True

    return False


def test_swact_to_locked_controller_negative(lock_controller):
    """
    TC610_4
    Verify that trying to swact a locked controller is rejected

    Test Setup:
        - Lock the standby controller

    Test Steps:
        - Attempt to swact to the locked controller

    Teardown:
        - Unlock the controller

    """
    if not lock_controller:
        skip("Couldn't lock the controller.")

    active = system_helper.get_active_controller_name()
    LOG.tc_step("Attempting to swact to locked controller.")
    code, out = host_helper.swact_host(fail_ok=True)
    LOG.tc_step("Verifying that the swact didn't occur.")
    assert 1 == code, "FAIL: The swact wasn't rejected"
    curr_active = system_helper.get_active_controller_name()
    assert curr_active == active, "FAIL: The active controller was changed. " \
                                  "Previous: {} Current: {}".format(active, curr_active)



@mark.skipif(system_helper.is_small_footprint(), reason="Small footprint lab. No compute nodes.")
def test_swact_compute_negative():
    """
    TC610_5
    Verify that trying to swact a compute node is rejected

    Test Steps:
        - Attempt to swact from a compute

    """
    computes = system_helper.get_computes()
    for compute in computes:
        LOG.tc_step("Attempting to swact from {}".format(compute))
        code, out = host_helper.swact_host(compute, fail_ok=True)
        LOG.tc_step("Verifying that the swact didn't occur.")
        assert 1 == code, "FAIL: Swacting {} wasn't rejected".format(compute)
