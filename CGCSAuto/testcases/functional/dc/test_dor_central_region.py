import time
from pytest import mark
from utils.tis_log import LOG
from consts.timeout import HostTimeout
from consts.auth import Tenant
from keywords import system_helper, vlm_helper, dc_helper
from testfixtures.vlm_fixtures import reserve_unreserve_all_hosts_module_central, unreserve_hosts_module_central


@mark.usefixtures('check_alarms')
def test_dc_dead_office_recovery_central(reserve_unreserve_all_hosts_module_central):
    """
    Test dead office recovery main cloud
    Args:
    Setups:
        - Reserve all nodes for central cloud in vlm

    Test Steps:
        - Power off all nodes in vlm using multi-processing to simulate a power outage
        - Power on all nodes
        - Wait for nodes to become online/available
        - Check all the subclouds are syncs as start of the test.
    """
    central_auth = Tenant.get('admin_platform', dc_region='SystemController')
    hosts = system_helper.get_hosts(auth_info=central_auth)
    managed_subclouds = dc_helper.get_subclouds(mgmt='managed', avail='online')
    hosts_to_check = system_helper.get_hosts(availability=['available', 'online'], auth_info=central_auth)
    LOG.info("Online or Available hosts before power-off: {}".format(hosts_to_check))

    LOG.tc_step("Powering off hosts in multi-processes to simulate power outage: {}".format(hosts))
    try:
        vlm_helper.power_off_hosts_simultaneously(hosts, region='central_region')
    except Exception:
        raise
    finally:
        LOG.tc_step("Wait for 60 seconds and power on hosts: {}".format(hosts))
        time.sleep(60)
        LOG.info("Hosts to check after power-on: {}".format(hosts_to_check))
        vlm_helper.power_on_hosts(hosts, reserve=False, reconnect_timeout=HostTimeout.REBOOT+HostTimeout.REBOOT,
                                  hosts_to_check=hosts_to_check, region='central_region')

    LOG.tc_step("Check subclouds managed")
    current_managed_subclouds = dc_helper.get_subclouds(mgmt='managed', avail='online')
    assert managed_subclouds == current_managed_subclouds, 'current managed subclouds are diffrent from \
                                            origin {} current {}'.format(current_managed_subclouds, managed_subclouds)
