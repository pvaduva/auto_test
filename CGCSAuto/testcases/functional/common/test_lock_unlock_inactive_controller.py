###
# test_467_lock_unlock_compute_node sanity_juno_unified_R3.xls
###

from pytest import fixture, mark, skip
import random

from utils.tis_log import LOG
from keywords import host_helper,system_helper
from setup_consts import P1, P2, P3


def test_lock_unlock_inactive_controller():
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
    LOG.tc_step('Retrieve the standby controller from the lab')
    standby_controller = system_helper.get_standby_controller_name()
    standby_controller_state = host_helper.get_hostshow_value(standby_controller,'administrative')

    if standby_controller_state == 'locked':
        assert False, 'Standby controller {} is in locked state. When the test lab should have no locked compute ' \
                      'node'.format(standby_controller)

    # lock standby controller node and verify compute node is successfully locked
    host_helper.lock_host(standby_controller)

    lucky_compute_node_locked_state = host_helper.get_hostshow_value(standby_controller,'administrative')
    assert lucky_compute_node_locked_state == 'locked', 'Test Failed. Standby Controller {} should be in locked ' \
                                                        'state but is not.'.format(standby_controller)

    # unlock standby controller node and verify controller node is successfully unlocked
    host_helper.unlock_host(standby_controller)
    lucky_compute_node_unlocked_state = host_helper.get_hostshow_value(standby_controller,'administrative')
    assert lucky_compute_node_locked_state == 'unlocked', 'Test Failed. Standby Controller {} should be in unlocked ' \
                                                          'state but is not.'.format(standby_controller)
