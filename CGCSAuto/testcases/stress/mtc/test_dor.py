import time
from pytest import mark

from utils.tis_log import LOG
from utils import local_host
from consts.timeout import HostTimeout
from consts.vlm import VlmAction
from keywords import system_helper, vlm_helper, host_helper, vm_helper
from testfixtures.vlm_fixtures import reserve_unreserve_all_hosts_module, unreserve_hosts_module


def power_off_and_on(barcode, power_off_event, timeout):

    if power_off_event.wait(timeout=timeout):
        rc, output = local_host.vlm_exec_cmd(VlmAction.VLM_TURNOFF, barcode, reserve=False)
        assert 0 == rc, "Failed to turn off target"
        LOG.info("{} powered off successfully".format(barcode))
        return
    else:
        raise TimeoutError("Timed out waiting for power_off_event to be set")


@mark.usefixtures('check_alarms')
def test_dead_office_recovery(reserve_unreserve_all_hosts_module):
    """
    Test dead office recovery with vms
    Args:
        reserve_unreserve_all_hosts_module: test fixture to reserve unreserve all vlm nodes for lab under test

    Setups:
        - Reserve all nodes in vlm

    Test Steps:
        - Boot 5 vms with various boot_source, disks, etc and ensure they can be reached from NatBox
        - Power off all nodes in vlm using multi-processing to simulate a power outage
        - Power on all nodes
        - Wait for nodes to become online/available
        - Check vms are recovered after hosts come back up and vms can be reached from NatBox

    """
    LOG.tc_step("Boot 5 vms with various boot_source, disks, etc")
    vms = vm_helper.boot_vms_various_types()

    hosts = system_helper.get_hostnames()
    hosts_to_check = system_helper.get_hostnames(availability=['available', 'online'])

    LOG.info("Online or Available hosts before power-off: {}".format(hosts_to_check))
    LOG.tc_step("Powering off hosts in multi-processes to simulate power outage: {}".format(hosts))
    try:
        vlm_helper.power_off_hosts_simultaneously(hosts)
    except:
        raise
    finally:
        LOG.tc_step("Wait for 60 seconds and power on hosts: {}".format(hosts))
        time.sleep(60)
        LOG.info("Hosts to check after power-on: {}".format(hosts_to_check))
        vlm_helper.power_on_hosts(hosts, reserve=False, reconnect_timeout=HostTimeout.REBOOT+HostTimeout.REBOOT,
                                  hosts_to_check=hosts_to_check)

    LOG.tc_step("Check vms are recovered after dead office recovery")
    vm_helper.wait_for_vms_values(vms, fail_ok=False, timeout=600)
    for vm in vms:
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm)
