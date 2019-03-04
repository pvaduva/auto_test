import time
from pytest import mark
from utils.tis_log import LOG
from consts.timeout import HostTimeout, VMTimeout
from consts.auth import Tenant
from keywords import system_helper, vlm_helper, dc_helper, vm_helper
from testfixtures.vlm_fixtures import reserve_unreserve_all_hosts_module_central, unreserve_hosts_module_central


@mark.usefixtures('check_alarms')
def test_dc_dead_office_recovery_central(reserve_unreserve_all_hosts_module_central):
    """
    Test dead office recovery main cloud
    Args:
    Setups:
        - Reserve all nodes for central cloud in vlm

    Test Steps:
        - Launch various types of VMs in primary clouds.
        - Power off all nodes in vlm using multi-processing to simulate a power outage
        - Power on all nodes
        - Wait for nodes to become online/available
        - Check all the subclouds are syncs as start of the test.
        - check all the VMs are up in subclouds which are launched.
    """
    LOG.tc_step("Boot 5 vms with various boot_source, disks, etc")
    vms = vm_helper.boot_vms_various_types()
    central_auth = Tenant.get('admin', dc_region='SystemController')
    hosts = system_helper.get_hostnames(auth_info=central_auth)
    managed_subclouds = dc_helper.get_subclouds(mgmt='managed', avail='online')
    hosts_to_check = system_helper.get_hostnames(auth_info=central_auth, availability=['available', 'online'])
    LOG.info("Online or Available hosts before power-off: {}".format(hosts_to_check))

    LOG.tc_step("Powering off hosts in multi-processes to simulate power outage: {}".format(hosts))
    try:
        vlm_helper.power_off_hosts_simultaneously(hosts, region='central_region')
    except:
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

    LOG.tc_step("Check vms are recovered after dead office recovery")
    vm_helper.wait_for_vms_values(vms, fail_ok=False, timeout=600)

    LOG.tc_step("Check vms are reachable after centtral clouds DOR test")
    for vm in vms:
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm, timeout=VMTimeout.DHCP_RETRY)
