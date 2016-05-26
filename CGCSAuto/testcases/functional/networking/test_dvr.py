from pytest import mark

from utils.tis_log import LOG

from consts.cgcs import RouterStatus
from keywords import host_helper, network_helper
from testfixtures.resource_mgmt import ResourceCleanup


##############################################
# us54724_test_strategy_JUNO_DVR_Integration #
##############################################


@mark.parametrize(('dvr_create', 'dvr_update', 'expt_dvr'), [
    (True, None, True),
    (True, False, False),
    (False, True, True),
])
def test_router_distributed(dvr_create, dvr_update, expt_dvr):
    """
    Args:
        dvr_create (bool|None): distributed value when creating the router. Don't explicitly set dvr value if None.
        dvr_update (bool|None): distributed value to update to. Don't update if None.
        expt_dvr (bool): expected distributed setting for router

    Test Steps:
        - Create a router with given dvr setting
        - Update the router to given dvr setting
        - Verify distributed setting via neutron router-show
        - Verify router is in DOWN state
        - Add a gateway to router
        - Attach a management subnet interface to router
        - Verify router is in ACTIVE state
        - If distributed, verify the router name space is created on one compute node only

    Teardown:
        - Delete router interface
        - Delete router
        - Delete created subnet

    """
    LOG.tc_step("Create a router with dvr={}, and verify it via neutron router-show".format(dvr_create))
    router_id = network_helper.create_router('dvr', distributed=dvr_create)[1]
    ResourceCleanup.add('router', router_id, scope='function')

    if dvr_create:
        LOG.tc_step("Verify router namespace is not created on any host yet.")
        assert not network_helper.get_router_info(router_id, field='wrs-net:host'), \
            "Router namespace should not be created yet."

    if dvr_update is not None:
        LOG.tc_step("Update router dvr to {}, and verify it via neutron router-show.".format(dvr_update))
        network_helper.update_router_distributed(router_id, distributed=dvr_update)

    LOG.tc_step("Verify Router is not in active state before adding interfaces.")
    assert RouterStatus.DOWN == network_helper.get_router_info(router_id, field='status'), \
        "Router is not in DOWN state before adding interfaces."

    LOG.tc_step("Add external network gateway to router.")
    network_helper.set_router_gateway(router_id)

    if expt_dvr:
        LOG.tc_step("Add management subnet interface to router")
        subnet_id = network_helper.add_router_interface(router_id)[2]
        ResourceCleanup.add('subnet', subnet_id)

    LOG.tc_step("Verify router is in ACTIVE state after adding gateway/interfaces.")
    assert RouterStatus.ACTIVE == network_helper.get_router_info(router_id, field='status'), \
        "Router is not in ACTIVE state after adding interfaces."

    if expt_dvr:
        router_host = network_helper.get_router_info(router_id, field='wrs-net:host')
        assert router_host, "Router namespace is not created on any compute."

        LOG.tc_step("Verify DVR router name space is created on {} only.".format(router_host))

        nova_hosts = host_helper.get_nova_hosts()
        for nova_host in nova_hosts:
            with host_helper.ssh_to_host(nova_host) as host_ssh:
                output = host_ssh.exec_sudo_cmd('sudo ip netns list', fail_ok=False)[1]

                if nova_host == router_host:
                    assert router_id in output, "Router name space is not created on host: {}".format(router_host)
                else:
                    assert router_id not in output, "Router name space is created on more than one host."
