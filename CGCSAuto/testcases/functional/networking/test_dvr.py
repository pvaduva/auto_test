from pytest import mark, fixture

from utils.tis_log import LOG

from consts.auth import Tenant
from consts.cgcs import RouterStatus
from keywords import network_helper, vm_helper
from testfixtures.resource_mgmt import ResourceCleanup


##############################################
# us54724_test_strategy_JUNO_DVR_Integration #
##############################################


@fixture(scope='module')
def router_info(request):
    router_id = network_helper.get_tenant_router()
    is_dvr = eval(network_helper.get_router_info(router_id, field='distributed', auth_info=Tenant.ADMIN))

    def teardown():
        if eval(network_helper.get_router_info(router_id, field='distributed', auth_info=Tenant.ADMIN)) != is_dvr:
            network_helper.update_router_distributed(router_id, distributed=is_dvr)
    request.addfinalizer(teardown)

    return router_id, is_dvr


def test_update_router_distributed(router_info):
    """
    Test update router to distributed and non-distributed

    Args:
        router_info (tuple): router_id (str) and is_dvr (bool)

    Setups:
        - Get the router id and original distributed setting

    Test Steps:
        - Boot a vm before updating router and ping vm from NatBox
        - Change the distributed value of the router and verify it's updated successfully
        - Verify router is in ACTIVE state
        - Verify vm can still be ping'd from NatBox
        - Repeat the three steps above with the distributed value reverted to original value

    Teardown:
        - Delete vm
        - Revert router to it's original distributed setting if not already done so

    """
    router_id, is_dvr = router_info

    LOG.tc_step("Boot a vm before updating router and ping vm from NatBox")
    vm_id = vm_helper.boot_vm()[1]
    ResourceCleanup.add('vm', vm_id)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id, fail_ok=False)

    for update_to_val in [not is_dvr, is_dvr]:
        LOG.tc_step("Update router distributed to {}".format(update_to_val))
        network_helper.update_router_distributed(router_id, distributed=update_to_val)

        LOG.tc_step("Verify router is in active state and vm can be ping'd from NatBox")
        assert RouterStatus.ACTIVE == network_helper.get_router_info(router_id, field='status'), \
            "Router is not in active state after updating distributed to {}.".format(update_to_val)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id, fail_ok=False, timeout=60)
