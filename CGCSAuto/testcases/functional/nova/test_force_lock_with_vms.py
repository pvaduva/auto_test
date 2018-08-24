from pytest import skip, fixture

from utils.tis_log import LOG
from testfixtures.recover_hosts import HostsToRecover
from keywords import nova_helper, vm_helper, host_helper, system_helper


@fixture(scope='module')
def get_hosts_with_backing(add_admin_role_module):
    storage_backing, hosts = nova_helper.get_storage_backing_with_max_hosts()
    if len(hosts) < 2:
        skip("Minimum of two hypervisors must support the same storage_backing.")

    if not system_helper.is_small_footprint():
        host_under_test = hosts[0]
    else:
        host_under_test = system_helper.get_standby_controller_name()

    return storage_backing, host_under_test


def test_force_lock_with_mig_vms(get_hosts_with_backing):
    """
    Test force lock host with migrate-able vms on it

    Prerequisites:
        - Minimum of two hosts supporting the same storage backing.
    Test Setups:
        - Add admin role to primary tenant
        - Boot various VMs on host_under_test that can be live migrated
    Test Steps:
        - Get status info from VMs
        - Force lock target host
        - Verify force lock returns 0
        - Wait until VMs are active on a secondary host
        - Verify VMs can be pinged
    Test Teardown:
        - Remove admin role from primary tenant
        - Delete created vms
        - Unlock locked target host(s)
    """
    storage_backing, host_under_test = get_hosts_with_backing

    # Boot VMs on the host.
    LOG.tc_step("Boot VMs on {}".format(host_under_test))
    vm_ids = vm_helper.boot_vms_various_types(storage_backing=storage_backing, target_host=host_under_test,
                                              cleanup='function')

    # Force lock host that VMs are booted on
    LOG.tc_step("Force lock {}".format(host_under_test))
    HostsToRecover.add(host_under_test)
    lock_code, lock_output = host_helper.lock_host(host_under_test, force=True, check_first=False)
    assert lock_code == 0, "Failed to force lock {}. Details: {}".format(host_under_test, lock_output)

    # Expect VMs to migrate off force-locked host (non-gracefully)
    LOG.tc_step("Wait for 'Active' status of VMs after host force lock completes")
    vm_helper.wait_for_vms_values(vm_ids, fail_ok=False)

    for vm in vm_ids:
        vm_helper.wait_for_vm_pingable_from_natbox(vm)


@fixture()
def add_host_to_zone(request, get_hosts_with_backing, add_cgcsauto_zone):
    storage_backing, host_under_test = get_hosts_with_backing
    nova_helper.add_hosts_to_aggregate(aggregate='cgcsauto', hosts=host_under_test)

    def remove_host_from_zone():
        nova_helper.remove_hosts_from_aggregate(aggregate='cgcsauto', check_first=False)
    request.addfinalizer(remove_host_from_zone)

    return storage_backing, host_under_test


def test_force_lock_with_non_mig_vms(add_host_to_zone):
    """
    Test force lock host with non-migrate-able vms on it

    Prerequisites:
        - Minimum of two up hypervisors
    Test Setups:
        - Add admin role to primary tenant
        - Create cgcsauto aggregate
        - Add host_under_test to cgcsauto aggregate
        - Create flavor for vms_to_test with storage_backing support by host_under_test
        - Create vms_to_test on host_under_test that can be live migrated
    Test Steps:
        - Force lock target host
        - Verify force lock returns 0
        - Verify VMs cannot find a host to boot and are in error state
        - Unlock locked target host
        - Verify VMs are active on host once it is up and available
        - Verify VMs can be pinged
    Test Teardown:
        - Remove admin role from primary tenant
        - Delete created vms
        - Remove host_under_test from cgcsauto aggregate
    """
    storage_backing, host_under_test = add_host_to_zone

    # Create flavor with storage_backing the host_under_test supports
    flavor_id = nova_helper.create_flavor(storage_backing=storage_backing)[1]

    # Boot VMs on the host using the above flavor.
    LOG.tc_step("Boot VM on {}".format(host_under_test))
    vm_id = vm_helper.boot_vm(vm_host=host_under_test, flavor=flavor_id, avail_zone='cgcsauto', cleanup='function')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    # Force lock host that VMs are booted on.
    LOG.tc_step("Force lock {}".format(host_under_test))
    HostsToRecover.add(host_under_test)
    lock_code, lock_output = host_helper.lock_host(host_under_test, force=True)
    assert lock_code == 0, "Failed to lock {}. Details: {}".format(host_under_test, lock_output)

    vm_helper.wait_for_vm_values(vm_id, fail_ok=False, **{'status': 'ERROR'})

    host_helper.unlock_host(host_under_test)

    vm_helper.wait_for_vm_values(vm_id, timeout=300, fail_ok=False, **{'status': 'ACTIVE'})
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
