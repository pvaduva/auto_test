from pytest import fixture

from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient
from consts.proj_vars import ProjVar
from consts.auth import Tenant
from consts.stx import EventLogID
from keywords import dc_helper, system_helper


@fixture(scope='function')
def ntp_precheck(request, check_alarms):

    LOG.info("Gather NTP config and subcloud management info")
    central_auth = Tenant.get('admin_platform', dc_region='RegionOne')
    central_ntp = system_helper.get_ntp_servers(auth_info=central_auth)

    primary_subcloud = ProjVar.get_var('PRIMARY_SUBCLOUD')
    subcloud_auth = Tenant.get('admin_platform', dc_region=primary_subcloud)
    subcloud_ntp = system_helper.get_ntp_servers(auth_info=subcloud_auth)

    if not central_ntp == subcloud_ntp:
        dc_helper.wait_for_subcloud_ntp_config(subcloud=primary_subcloud)

    managed_subclouds = dc_helper.get_subclouds(mgmt='managed', avail='online')
    ssh_map = ControllerClient.get_active_controllers_map()
    managed_subclouds = [subcloud for subcloud in managed_subclouds if subcloud in ssh_map]

    if primary_subcloud in managed_subclouds:
        managed_subclouds.remove(primary_subcloud)

    managed_subcloud = None
    if managed_subclouds:
        managed_subcloud = managed_subclouds.pop()
        LOG.fixture_step("Leave only one subcloud besides primary subcloud to be managed: {}".format(managed_subcloud))

    subclouds_to_revert = []
    if managed_subclouds:
        LOG.info("Unmange: {}".format(managed_subclouds))
        for subcloud in managed_subclouds:
            if not system_helper.get_alarms(alarm_id=EventLogID.CONFIG_OUT_OF_DATE,
                                            auth_info=Tenant.get('admin_platform', subcloud)):
                subclouds_to_revert.append(subcloud)
                dc_helper.unmanage_subcloud(subcloud)

    def revert():
        reverted = False
        try:
            LOG.fixture_step("Manage primary subcloud {} if unmanaged".format(primary_subcloud))
            dc_helper.manage_subcloud(primary_subcloud)

            LOG.fixture_step("Revert NTP config if changed")
            res = system_helper.modify_ntp(ntp_servers=central_ntp, auth_info=central_auth, check_first=True,
                                           clear_alarm=False)[0]
            if res != -1:
                LOG.fixture_step("Lock unlock config out-of-date hosts in central region")
                system_helper.wait_and_clear_config_out_of_date_alarms(auth_info=central_auth,
                                                                       wait_with_best_effort=True)

                LOG.fixture_step("Lock unlock config out-of-date hosts in {}".format(primary_subcloud))
                dc_helper.wait_for_subcloud_ntp_config(subcloud=primary_subcloud, expected_ntp=central_ntp,
                                                       clear_alarm=True)

                if managed_subcloud:
                    LOG.fixture_step("Lock unlock config out-of-date hosts in {}".format(managed_subcloud))
                    dc_helper.wait_for_subcloud_ntp_config(subcloud=managed_subcloud, expected_ntp=central_ntp,
                                                           clear_alarm=True)

            if subclouds_to_revert:
                LOG.fixture_step("Manage unmanaged subclouds and check they are unaffected")
                for subcloud in subclouds_to_revert:
                    dc_helper.manage_subcloud(subcloud)
                    assert not system_helper.get_alarms(alarm_id=EventLogID.CONFIG_OUT_OF_DATE,
                                                        auth_info=Tenant.get('admin_platform', dc_region=subcloud))
            reverted = True

        finally:
            if not reverted:
                for subcloud in subclouds_to_revert:
                    dc_helper.manage_subcloud(subcloud)

    request.addfinalizer(revert)

    return primary_subcloud, managed_subcloud, central_ntp


def test_dc_ntp_modify(ntp_precheck):
    """
    Update NTP servers on central region and check it is propagated to subclouds
    Args:
        ntp_precheck (fixture for test setup and teardown)

    Setups:
        - Ensure primary subcloud is manged and NTP config is in sync with central region
        - Un-manage rest of the subclouds except one

    Test Steps:
        - Un-manage primary subcloud
        - Configure NTP servers on above unmanaged subcloud to remove the first NTP server
        - Configure NTP servers on central region to add an invalid server 8.8.8.8
        - Lock/unlock controllers on central region to apply the config
        - Wait for new NTP config to sync over to the only managed osubcloud and config out-of-date alarms appear
        - Lock/unlock controllers on managed subcloud to apply config
        - Ensure central NTP config does not sync to unmanaged primary subcloud
        - Re-manage primary subcloud and ensure NTP config syncs over
        - Lock/unlock controllers in primary subcloud to apply new NTP configuration
        - Verify fm alarm 100.114 appears for invalid/unreachable NTP server on central region and managed

    Teardown:
        - Reset NTP servers to original value
        - Lock/unlock controllers on all managed subclouds to clear the config out of date alarm
        - Re-manage subclouds that were umanaged in setup
        - Verify no config out-of-date alarms on the re-managed subclouds

    """
    primary_subcloud, managed_subcloud, prev_central_ntp = ntp_precheck
    new_central_ntp = ['8.8.8.8'] + prev_central_ntp[:-1]
    local_subcloud_ntp = prev_central_ntp[1:]

    central_auth = Tenant.get('admin_platform', dc_region='RegionOne')
    primary_sub_auth = Tenant.get('admin_platform', dc_region=primary_subcloud)
    auth_list = [central_auth, primary_sub_auth]
    if managed_subcloud:
        managed_sub_auth = Tenant.get('admin_platform', dc_region=managed_subcloud)
        auth_list.append(managed_sub_auth)

    LOG.tc_step("Unmanage {}".format(primary_subcloud))
    dc_helper.unmanage_subcloud(subcloud=primary_subcloud, check_first=True)

    LOG.tc_step("While {} is unmanaged, modify its NTP servers locally from {} to {}".
                format(primary_subcloud, prev_central_ntp, local_subcloud_ntp))
    system_helper.modify_ntp(ntp_servers=local_subcloud_ntp, auth_info=primary_sub_auth)

    LOG.tc_step("Reconfigure NTP servers on central region from {} to {}".format(prev_central_ntp, new_central_ntp))
    system_helper.modify_ntp(ntp_servers=new_central_ntp, auth_info=central_auth)

    if managed_subcloud:
        LOG.tc_step("Wait for new NTP config to sync over to managed subcloud: {}".format(managed_subcloud))
        dc_helper.wait_for_subcloud_ntp_config(subcloud=managed_subcloud, expected_ntp=new_central_ntp)

    LOG.tc_step("Ensure NTP config is not updated on unmanaged subcloud: {}".format(primary_subcloud))
    code = dc_helper.wait_for_subcloud_ntp_config(subcloud=primary_subcloud, expected_ntp=new_central_ntp,
                                                  timeout=60, fail_ok=True, clear_alarm=False)[0]
    assert 1 == code, "Actual return code: {}".format(code)
    assert local_subcloud_ntp == system_helper.get_ntp_servers(auth_info=primary_sub_auth)

    LOG.tc_step('Re-manage {} and ensure NTP config syncs over'.format(primary_subcloud))
    dc_helper.manage_subcloud(subcloud=primary_subcloud, check_first=False)
    dc_helper.wait_for_subcloud_ntp_config(subcloud=primary_subcloud, expected_ntp=new_central_ntp)

    LOG.tc_step('Verify NTP alarm appeared for invalid server 8.8.8.8 on central and managed subclouds')
    for auth_info in auth_list:
        system_helper.wait_for_alarm(alarm_id=EventLogID.NTP_ALARM, auth_info=auth_info, timeout=660)
