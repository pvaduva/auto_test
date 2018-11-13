from pytest import fixture

from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient
from consts.proj_vars import ProjVar
from consts.auth import Tenant, SvcCgcsAuto
from keywords import dc_helper, system_helper


SNMP_COMM = 'cgcsauto_dc_snmp_comm'
SNMP_TRAPDEST = ('cgcsauto_dc_snmp_trapdest', SvcCgcsAuto.SERVER)


@fixture(scope='module')
def snmp_precheck(request):

    LOG.info("Gather SNMP config and subcloud management info")
    central_auth = Tenant.get('admin', dc_region='RegionOne')
    central_comms = system_helper.get_snmp_comms(auth_info=central_auth)
    central_trapdests = system_helper.get_snmp_trapdests(auth_info=central_auth)

    primary_subcloud = ProjVar.get_var('PRIMARY_SUBCLOUD')
    managed_subclouds = dc_helper.get_subclouds(mgmt='managed', avail='online')
    if primary_subcloud in managed_subclouds:
        managed_subclouds.remove(primary_subcloud)
    else:
        dc_helper.manage_subcloud(primary_subcloud)

    ssh_map = ControllerClient.get_active_controllers_map()
    managed_subclouds = [subcloud for subcloud in managed_subclouds if subcloud in ssh_map]

    LOG.fixture_step("Ensure SNMP community strings are synced on {}".format(primary_subcloud))
    subcloud_auth = Tenant.get('admin', dc_region=primary_subcloud)
    subcloud_comms = system_helper.get_snmp_comms(auth_info=subcloud_auth)

    if sorted(subcloud_comms) != sorted(central_comms):
        dc_helper.wait_for_subcloud_snmp_comms(primary_subcloud, expected_comms=central_comms)

    LOG.fixture_step("Ensure SNMP trapdests are synced on {}".format(primary_subcloud))
    subcloud_trapdests = system_helper.get_snmp_trapdests(auth_info=subcloud_auth)
    if sorted(subcloud_trapdests) != sorted(central_trapdests):
        dc_helper.wait_for_subcloud_snmp_trapdests(primary_subcloud, expected_trapdests=central_trapdests)

    def revert():
        LOG.fixture_step("Manage {} if unmanaged".format(primary_subcloud))
        dc_helper.manage_subcloud(primary_subcloud)

        LOG.fixture_step("Delete new SNMP community string and trapdest on central region")
        system_helper.delete_snmp_comm(comms=SNMP_COMM, auth_info=central_auth)
        system_helper.delete_snmp_trapdest(ip_addrs=SNMP_TRAPDEST[1], auth_info=central_auth)

        LOG.fixture_step("Wait for sync audit on {} and SNMP community strings and trapdests to sync over".
                         format(primary_subcloud))
        dc_helper.wait_for_sync_audit(subclouds=primary_subcloud)
        dc_helper.wait_for_subcloud_snmp_comms(primary_subcloud, expected_comms=central_comms, timeout=60,
                                               check_interval=10)
        dc_helper.wait_for_subcloud_snmp_trapdests(primary_subcloud, expected_trapdests=central_trapdests, timeout=60,
                                                   check_interval=10)

    request.addfinalizer(revert)

    return primary_subcloud, managed_subclouds, central_comms, central_trapdests


def test_dc_snmp(snmp_precheck):
    """

    Update DNS servers on central region and check it is propagated to subclouds
    Args:
        snmp_precheck: test fixture for setup/teardown

    Setups:
        - Ensure primary subcloud is managed and SNMP config is synced

    Test Steps:
        - Un-manage primary subcloud
        - Configure DNS servers on central region to new value based on given scenario
        - Wait for new DNS config to sync over to managed online subclouds
        - Ensure DNS config is not updated on unmanaged primary subcloud
        - Re-manage primary subcloud and ensure DNS config syncs over
        - Verify nslookup works in Central Region and primary subcloud

    Teardown:
        - Delete DNS servers to original value (module)

    """
    primary_subcloud, managed_subclouds, central_comms, central_trapdests = snmp_precheck
    central_auth = Tenant.get('admin', dc_region='RegionOne')
    sub_auth = Tenant.get('admin', dc_region=primary_subcloud)

    LOG.tc_step("Unmanage {}".format(primary_subcloud))
    dc_helper.unmanage_subcloud(subcloud=primary_subcloud, check_first=False)

    LOG.tc_step('Add SNMP community string and trapdest to unmanaged subcloud - {}'.format(primary_subcloud, SNMP_COMM))
    system_helper.create_snmp_comm('cgcsauto comm local', auth_info=sub_auth)
    system_helper.create_snmp_trapdest(comm_string="cgcsauto trapdest local", ip_addr='8.8.8.8', auth_info=sub_auth)

    LOG.tc_step('Add SNMP community string and trapdest to central region')
    system_helper.create_snmp_comm(SNMP_COMM, auth_info=central_auth)
    system_helper.create_snmp_trapdest(comm_string=SNMP_TRAPDEST[0], ip_addr=SNMP_TRAPDEST[1], auth_info=central_auth)

    LOG.tc_step("Wait for new SNMP config to sync over to managed subclouds: {}".format(managed_subclouds))
    expt_comms = central_comms + [SNMP_COMM]
    expt_trapdests = central_trapdests + [SNMP_TRAPDEST[1]]
    dc_helper.wait_for_sync_audit(subclouds=managed_subclouds)
    for managed_sub in managed_subclouds:
        dc_helper.wait_for_subcloud_snmp_comms(subcloud=managed_sub, expected_comms=expt_comms,
                                               timeout=30, check_interval=10)
        dc_helper.wait_for_subcloud_snmp_trapdests(subcloud=managed_sub, expected_trapdests=expt_trapdests,
                                                   timeout=30, check_interval=10)

    LOG.tc_step("Ensure central SNMP config is not synced to unmanaged subcloud: {}".format(primary_subcloud))
    code_comm = dc_helper.wait_for_subcloud_snmp_comms(subcloud=primary_subcloud,
                                                       expected_comms=expt_comms,
                                                       timeout=15, check_interval=5, fail_ok=True)[0]
    code_trapdest = dc_helper.wait_for_subcloud_snmp_trapdests(subcloud=primary_subcloud,
                                                               expected_trapdests=expt_trapdests,
                                                               timeout=15, check_interval=5, fail_ok=True)[0]
    assert code_comm == 1, "SNMP comm is updated unexpectedly on unmanaged subcloud {}".format(primary_subcloud)
    assert code_trapdest == 1, "SNMP trapdest is updated unexpectedly on unmanaged subcloud {}".format(primary_subcloud)

    LOG.tc_step('Re-manage {} and ensure DNS config syncs over'.format(primary_subcloud))
    dc_helper.manage_subcloud(subcloud=primary_subcloud, check_first=False)
    dc_helper.wait_for_subcloud_snmp_comms(subcloud=primary_subcloud, expected_comms=expt_comms)
    dc_helper.wait_for_subcloud_snmp_trapdests(subcloud=primary_subcloud, expected_trapdests=expt_trapdests,
                                               timeout=30, check_interval=10)
