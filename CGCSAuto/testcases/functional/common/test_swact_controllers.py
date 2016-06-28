###
# TC451 TiS_Mapping_AutomatedTests_v2.xlsx
###

from pytest import fixture, mark, skip

from consts.cgcs import EventLogID, FlavorSpec, VMStatus
from utils.tis_log import LOG
from keywords import host_helper,system_helper,cinder_helper,glance_helper,vm_helper,nova_helper
from setup_consts import P1, P2, P3
from testfixtures.resource_mgmt import ResourceCleanup


def test_volume_based_vm():
    '''
    create a VM based of volumes
    Returns:

    '''
    img_id = glance_helper.get_image_id_from_name('cgcs-guest')
    vol_id = cinder_helper.create_volume("a_test_volume",image_id=img_id )[1]
    ResourceCleanup.add('volume', vol_id, scope='module')

    boot_source = 'volume'
    vm_id = vm_helper.boot_vm( source=boot_source, source_id=vol_id)[1]
    ResourceCleanup.add('vm', vm_id, scope='module')
    # get the status of the VM show that it is active at least
    vm_state = nova_helper.get_vm_status(vm_id)
    print(vm_state)
    assert vm_state == VMStatus.ACTIVE


@mark.sanity
@mark.skipif(system_helper.is_small_footprint(), reason="Skip for small footprint lab")
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

    LOG.tc_step('Active controller: {} Standby Controller:{}'.format(active_controller_before_swact,standby_controller_before_swact ))

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

    LOG.tc_step('Active controller: {} Standby Controller:{}'.format(active_controller_after_swact,standby_controller_after_swact ))
    # There is no revert back to previous controller to active becase both controller should work the same

