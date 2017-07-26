from pytest import mark, skip

from utils.tis_log import LOG

from consts.cgcs import VMStatus
from keywords import host_helper, system_helper, vm_helper, nova_helper, network_helper
from testfixtures.recover_hosts import HostsToRecover


@mark.usefixtures('check_alarms')
@mark.parametrize('host_type', [
    mark.sanity('controller'),
    'compute',
    # 'storage'
])
def test_system_persist_over_host_reboot(host_type):
    """
    Validate Inventory summary over reboot of one of the controller see if data persists over reboot

    Test Steps:
        - capture Inventory summary for list of hosts on system service-list and neutron agent-list
        - reboot the current Controller-Active
        - Wait for reboot to complete
        - Validate key items from inventory persist over reboot

    """
    if host_type == 'controller':
        host = system_helper.get_active_controller_name()
    elif host_type == 'compute':
        if system_helper.is_small_footprint():
            skip("No compute host for AIO system")

        host = None
    else:
        hosts = host_helper.get_hosts(personality='storage')
        if not hosts:
            skip(msg="Lab has no storage nodes. Skip rebooting storage node.")

        host = hosts[0]

    LOG.tc_step("Pre-check for system status")
    system_helper.wait_for_services_enable()
    up_hypervisors = host_helper.get_up_hypervisors()
    network_helper.wait_for_agents_alive(hosts=up_hypervisors)

    LOG.tc_step("Launch a vm")
    vm_id = vm_helper.boot_vm(cleanup='function')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    if host is None:
        host = nova_helper.get_vm_host(vm_id)

    LOG.tc_step("Reboot a {} node and wait for reboot completes: {}".format(host_type, host))
    HostsToRecover.add(host)
    host_helper.reboot_hosts(host, wait_for_reboot_finish=True)
    host_helper.wait_for_hosts_ready(host)

    LOG.tc_step("Check vm is still active and pingable after {} reboot".format(host))
    vm_helper._wait_for_vm_status(vm_id, status=VMStatus.ACTIVE, fail_ok=False)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)

    LOG.tc_step("Check neutron agents and system services are in good state after {} reboot".format(host))
    network_helper.wait_for_agents_alive(up_hypervisors)
    system_helper.wait_for_services_enable()

    if host in up_hypervisors:
        LOG.tc_step("Check {} can still host vm after reboot".format(host))
        if not nova_helper.get_vm_host(vm_id) == host:
            vm_helper.live_migrate_vm(vm_id, destination_host=host)
