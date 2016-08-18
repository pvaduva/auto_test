###
# test_468_lock_unlock_compute_node sanity_juno_unified_R3.xls
###
import random
import time
from pytest import mark, skip

from utils.tis_log import LOG
from consts.reasons import SkipReason
from keywords import host_helper, system_helper


@mark.sanity
def test_lock_unlock_compute_node():
    """
    Verify lock unlock compute host on non-CPE system

    Test Steps:
        - Get a up hypervisor
        - Lock the selected hypervisor and ensure it is locked successfully
        - Unlock the selected hypervisor and ensure it is unlocked successfully with hypervisor state up

    """
    if system_helper.is_small_footprint():
        skip(SkipReason.CPE_DETECTED)

    LOG.tc_step('Randomly select a enabled and up hypervisor from system')
    nova_hosts = host_helper.get_nova_hosts()
    assert nova_hosts, "No up hypervisor found on system"

    lucky_compute_node = random.choice(nova_hosts)

    # lock compute node and verify compute node is successfully unlocked
    LOG.tc_step("Lock {} and ensure it is locked successfully".format(lucky_compute_node))
    host_helper.lock_host(lucky_compute_node)

    locked_compute_admin_state = host_helper.get_hostshow_value(lucky_compute_node,'administrative')
    assert locked_compute_admin_state == 'locked', 'Test Failed. Compute Node {} should be in locked state but ' \
                                        'is not.'.format(lucky_compute_node)

    # wait for services to stabilize before unlocking
    time.sleep(20)

    # unlock compute node and verify compute node is successfully unlocked
    LOG.tc_step("Unlock {} and ensure it is unlocked successfully with hypervisor state up".format(lucky_compute_node))
    host_helper.unlock_host(lucky_compute_node, check_hypervisor_up=True)

    unlocked_compute_admin_state = host_helper.get_hostshow_value(lucky_compute_node,'administrative')
    assert unlocked_compute_admin_state == 'unlocked', 'Test Failed. Compute Node {} should be in unlocked state ' \
                                                       'but is not.'.format(lucky_compute_node)

