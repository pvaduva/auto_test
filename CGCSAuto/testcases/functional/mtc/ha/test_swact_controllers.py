###
# TC451 TiS_Mapping_AutomatedTests_v2.xlsx
###

from pytest import mark, skip

from utils.tis_log import LOG
from consts.reasons import SkipReason
from keywords import host_helper, system_helper, vm_helper

from testfixtures.resource_mgmt import ResourceCleanup


@mark.sanity
@mark.cpe_sanity
def test_swact_controllers(wait_for_con_drbd_sync_complete):
    """
    Verify swact active controller

    Test Steps:
        - Boot a vm on system and check ping works
        - Swact active controller
        - Verify standby controller and active controller are swapped
        - Verify vm is still pingable

    """
    if not wait_for_con_drbd_sync_complete:
        skip(SkipReason.LESS_THAN_TWO_CONTROLLERS)

    LOG.tc_step('retrieve active and available controllers')
    pre_active_controller = system_helper.get_active_controller_name()
    pre_standby_controller = system_helper.get_standby_controller_name()

    assert pre_standby_controller, "No standby controller available"

    LOG.tc_step("Boot a vm from image and ping it")
    vm_id_img = vm_helper.boot_vm(name='swact_img', source='image', cleanup='function')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id_img)

    LOG.tc_step("Boot a vm from volume and ping it")
    vm_id_vol = vm_helper.boot_vm(name='swact', cleanup='function')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id_vol)

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

    LOG.tc_step("Check boot-from-image vm still pingable after swact")
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id_img, timeout=30)

    LOG.tc_step("Check boot-from-volume vm still pingable after swact")
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id_vol, timeout=30)
