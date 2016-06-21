from collections import Counter
from pytest import mark, fixture, skip

from utils.tis_log import LOG

from consts.auth import Tenant
from consts.cgcs import RouterStatus
from keywords import network_helper, vm_helper, nova_helper, host_helper, cinder_helper
from testfixtures.resource_mgmt import ResourceCleanup


##############################################
# us54724_test_strategy_JUNO_DVR_Integration #
##############################################

# This is to test dvr, non-dvr routers with SNAT disabled. Tests with SNAT enabled are in test_avr_snat.py


@fixture(scope='module')
def router_info(request):
    router_id = network_helper.get_tenant_router()
    is_dvr = eval(network_helper.get_router_info(router_id, field='distributed', auth_info=Tenant.ADMIN))
    LOG.info("Update router to DVR if not already done.")
    if not is_dvr:
        network_helper.update_router_distributed(router_id, distributed=True)

    def teardown():
        if eval(network_helper.get_router_info(router_id, field='distributed', auth_info=Tenant.ADMIN)) != is_dvr:
            network_helper.update_router_distributed(router_id, distributed=is_dvr)
        network_helper.update_router_ext_gateway_snat(enable_snat=True)
    request.addfinalizer(teardown)

    return router_id


def test_update_router_distributed(router_info):
    """
    Test update router to distributed and non-distributed

    Args:
        router_info (str): router_id (str)

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
    router_id = router_info

    LOG.tc_step("Boot a vm before updating router and ping vm from NatBox")
    vm_id = vm_helper.boot_vm()[1]
    ResourceCleanup.add('vm', vm_id)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id, fail_ok=False)

    for update_to_val in [False, True]:
        LOG.tc_step("Update router distributed to {}".format(update_to_val))
        network_helper.update_router_distributed(router_id, distributed=update_to_val)

        LOG.tc_step("Verify router is in active state and vm can be ping'd from NatBox")
        assert RouterStatus.ACTIVE == network_helper.get_router_info(router_id, field='status'), \
            "Router is not in active state after updating distributed to {}.".format(update_to_val)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id, fail_ok=False, timeout=60)


@mark.parametrize(('vms_num', 'srv_grp_policy'), [
    (2, 'affinity'),
    (2, 'anti-affinity'),
    (3, 'affinity'),
    (3, 'anti-affinity'),
])
def test_vms_network_connection(vms_num, srv_grp_policy, server_groups):
    """
    Test vms East West connection by pinging vms' data network from vm

    Args:
        vms_num (int): number of vms to boot
        srv_grp_policy (str): affinity to boot vms on same host, anti-affinity to boot vms on different hosts

    Setups:
        - Enable DVR
        - Boot vms with specific server group policy to schedule vms on same or different host(s)
        - Ping vms' data network from vm

    Teardown:
        - Delete vms
        - Delete server group

    """
    if srv_grp_policy == 'anti-affinity' and len(host_helper.get_nova_hosts()) == 1:
        skip("Only one nova host on the system.")

    LOG.tc_step("Boot vms with server group policy {}".format(srv_grp_policy))
    affinity_grp, anti_affinity_grp = server_groups()
    srv_grp_id = affinity_grp if srv_grp_policy == 'affinity' else anti_affinity_grp

    vms = []
    tenant_net_id = network_helper.get_tenant_net_id()
    mgmt_net_id = network_helper.get_mgmt_net_id()
    internal_net_id = network_helper.get_internal_net_id()

    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': tenant_net_id, 'vif-model': 'virtio'},
            {'net-id': internal_net_id, 'vif-model': 'avp'}]
    for i in range(vms_num):
        vol = cinder_helper.create_volume(rtn_exist=False)[1]
        vm_id = vm_helper.boot_vm('dvr_ew_traffic', source='volume', source_id=vol, nics=nics,
                                  hint={'group': srv_grp_id})[1]
        ResourceCleanup.add(resource_type='vm', resource_id=vm_id, del_vm_vols=True)
        vms.append(vm_id)

    for vm in vms:
        LOG.tc_step("Ping vms' data network ip (172.x.x.x) from vm {}, and verify ping successful.".format(vm))
        vm_helper.ping_vms_from_vm(from_vm=vm, to_vms=vms, net_type='data', fail_ok=False)
