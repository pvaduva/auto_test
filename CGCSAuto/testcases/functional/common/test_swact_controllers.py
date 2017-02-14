###
# TC451 TiS_Mapping_AutomatedTests_v2.xlsx
###

from pytest import mark, skip

from utils.tis_log import LOG
from consts.reasons import SkipReason
from keywords import host_helper, system_helper


@mark.sanity
@mark.cpe_sanity
def test_swact_controllers(wait_for_con_drbd_sync_complete):
    """
    Verify swact active controller

    Test Steps:
        - Swact active controller and active controller is changed
        - Verify standby controller and active controller are swapped

    """
    if not wait_for_con_drbd_sync_complete:
        skip(SkipReason.LESS_THAN_TWO_CONTROLLERS)

    LOG.tc_step('retrieve active and available controllers')
    pre_active_controller = system_helper.get_active_controller_name()
    pre_standby_controller = system_helper.get_standby_controller_name()

    assert pre_standby_controller, "No standby controller available"

    LOG.tc_step("Swact active controller and ensure active controller is changed")
    exit_code, output = host_helper.swact_host(hostname=pre_active_controller)
    assert 0 == exit_code, "{} is not recognized as active controller".format(pre_active_controller)

    LOG.tc_step("Verify standby controller and active controller are swapped")
    post_active_controller = system_helper.get_active_controller_name()
    post_standby_controller = system_helper.get_standby_controller_name()

    assert pre_standby_controller == post_active_controller, "Prev standby: {}; Post active: {}".format(
            pre_standby_controller, post_active_controller)
    assert pre_active_controller == post_standby_controller, "Prev active: {}; Post standby: {}".format(
            pre_active_controller, post_standby_controller)
