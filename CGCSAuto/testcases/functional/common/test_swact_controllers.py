###
# TC451 TiS_Mapping_AutomatedTests_v2.xlsx
###

from pytest import fixture, mark, skip

from utils.tis_log import LOG
from keywords import host_helper,system_helper
from setup_consts import P1, P2, P3


def test_swact_controllers():
    """
    Verify Swact is working on two controllers system

    Args:
        - Nothing

    Setup:
        - Nothing

    Test Steps:
        -execute swact command on active controller
        -verify the command is successful

    Teardown:
        - Nothing

    """
    LOG.tc_step('retrieve active and available controllers')
    active_controller_before_swact = system_helper.get_active_controller_name()
    standby_controller_before_swact = system_helper.get_standby_controller_name()

    LOG.tc_step('Execute swact cli')
    exit_code, output = host_helper.swact_host(fail_ok=True)
    # Verify that swact cli excuted successfully
    if exit_code == 1:
        assert False, "Execute swact cli Failed: {}".format(output)

    # Verify that the status of the controllers are correct after swact
    active_controller_after_swact = system_helper.get_active_controller_name()
    standby_controller_after_swact = system_helper.get_standby_controller_name()

    LOG.tc_step('Check status of controllers after Swact')
    assert active_controller_before_swact == standby_controller_after_swact and \
           standby_controller_before_swact == active_controller_after_swact, "Test Failed. New active controller is " \
                                                                             "not the original standby controller"

    # Swact controllers back to it's original state
    host_helper.swact_host(fail_ok=True)