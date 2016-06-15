###
# test_468_lock_unlock_compute_node sanity_juno_unified_R3.xls
###

from pytest import fixture, mark, skip
import random

from utils.tis_log import LOG
from keywords import host_helper,system_helper
from setup_consts import P1, P2, P3

@mark.sanity
def test_lock_unlock_compute_node():
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
    LOG.tc_step('Randomly pick a compute node from list of compute node within the lab')
    lucky_compute_node = random.choice(list(system_helper.get_computes()))
    lucky_compute_node_state = host_helper.get_hostshow_value(lucky_compute_node,'administrative')

    if lucky_compute_node_state == 'locked':
        assert False, 'Selected compute node {} is in locked state. When the test lab should have no locked compute ' \
                      'node'.format(lucky_compute_node)
    # lock compute node and verify compute node is successfully unlocked
    host_helper.lock_host(lucky_compute_node)

    lucky_compute_node_locked_state = host_helper.get_hostshow_value(lucky_compute_node,'administrative')
    assert lucky_compute_node_locked_state == 'locked', 'Test Failed. Compute Node {} should be in locked state but ' \
                                                        'is not.'.format(lucky_compute_node)

    # unlock compute node and verify compute node is successfully unlocked
    host_helper.unlock_host(lucky_compute_node)
    lucky_compute_node_unlocked_state = host_helper.get_hostshow_value(lucky_compute_node,'administrative')
    assert lucky_compute_node_locked_state == 'unlocked', 'Test Failed. Compute Node {} should be in unlocked state ' \
                                                          'but is not.'.format(lucky_compute_node)
