from pytest import fixture

from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient
from consts.proj_vars import ProjVar
from consts.auth import Tenant
from keywords import dc_helper, nova_helper


NEW_KEYPAIR = 'dc_new_keypair'


@fixture(scope='module')
def keypair_precheck(request):

    LOG.fixture_step("Make sure all online subclouds are managed")
    unmanaged_subclouds = dc_helper.get_subclouds(mgmt='unmanaged', avail='online')
    for subcloud in unmanaged_subclouds:
        dc_helper.manage_subcloud(subcloud)

    primary_subcloud = ProjVar.get_var('PRIMARY_SUBCLOUD')
    managed_subclouds = dc_helper.get_subclouds(mgmt='managed', avail='online')
    managed_subclouds.remove(primary_subcloud)

    assert managed_subclouds, "This test needs at least two online subclouds for testing."

    central_auth = Tenant.get('admin', dc_region='SystemController')
    central_keypair = nova_helper.get_keypairs(auth_info=central_auth)

    ssh_map = ControllerClient.get_active_controllers_map()
    managed_subclouds = [subcloud for subcloud in managed_subclouds if subcloud in ssh_map]

    LOG.fixture_step("Ensure keypair are synced on {}".format(primary_subcloud))
    subcloud_auth = Tenant.get('admin', dc_region=primary_subcloud)
    subcloud_keypair = nova_helper.get_keypairs(auth_info=subcloud_auth)

    if sorted(subcloud_keypair) != sorted(central_keypair):
        dc_helper.wait_for_subcloud_keypair(primary_subcloud, expected_keypair=central_keypair)

    def revert():
        LOG.fixture_step("Manage {} if unmanaged".format(primary_subcloud))
        dc_helper.manage_subcloud(primary_subcloud)

        LOG.fixture_step("Delete new keypair on central region")
        nova_helper.delete_keypairs(keypairs=NEW_KEYPAIR, auth_info=central_auth)

        LOG.fixture_step("Wait for sync audit on {} and keypair to sync over".
                         format(primary_subcloud))
        dc_helper.wait_for_sync_audit(subclouds=primary_subcloud, filters_regex='keypair')
        dc_helper.wait_for_subcloud_keypair(primary_subcloud, expected_keypair=central_keypair, timeout=60,
                                            check_interval=10)

    request.addfinalizer(revert)

    return primary_subcloud, managed_subclouds, central_keypair


def test_dc_keypair(keypair_precheck):
    """

    Create keypair on central region and check it is propagated to subclouds
    Args:
        keypair_precheck: test fixture for setup/teardown

    Setups:
        - Ensure primary subcloud is managed and keypair info is synced

    Test Steps:
        - Un-manage primary subcloud
        - Add a new keypair on central region
        - Wait for new keypair to sync over to managed online subclouds
        - Ensure central keypair is not updated on unmanaged primary subcloud
        - Re-manage primary subcloud and ensure new keypair syncs over

    Teardown:
        - Delete new created keypair

    """
    primary_subcloud, managed_subclouds, central_keypair = keypair_precheck
    central_auth = Tenant.get('admin', dc_region='RegionOne')

    LOG.tc_step("Unmanage {}".format(primary_subcloud))
    dc_helper.unmanage_subcloud(subcloud=primary_subcloud, check_first=False)

    LOG.tc_step('Add new keypair to central region')
    nova_helper.create_keypair(NEW_KEYPAIR, auth_info=central_auth)

    LOG.tc_step("Wait for new keypair to sync over to managed subclouds: {}".format(managed_subclouds))
    expt_keypair = central_keypair + [NEW_KEYPAIR]
    dc_helper.wait_for_sync_audit(subclouds=managed_subclouds, filters_regex='keypair')
    for managed_sub in managed_subclouds:
        dc_helper.wait_for_subcloud_keypair(subcloud=managed_sub, expected_keypair=expt_keypair,
                                            timeout=30, check_interval=10)

    LOG.tc_step("Ensure new keypair is not synced to unmanaged subcloud: {}".format(primary_subcloud))
    code_keypair = dc_helper.wait_for_subcloud_keypair(subcloud=primary_subcloud,
                                                       expected_keypair=expt_keypair,
                                                       timeout=15, check_interval=5, fail_ok=True)[0]

    assert code_keypair == 1, "keypair is updated unexpectedly on unmanaged subcloud {}".format(primary_subcloud)

    LOG.tc_step('Re-manage {} and ensure keypair syncs over'.format(primary_subcloud))
    dc_helper.manage_subcloud(subcloud=primary_subcloud, check_first=False)
    dc_helper.wait_for_subcloud_keypair(subcloud=primary_subcloud, expected_keypair=expt_keypair)
