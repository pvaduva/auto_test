from pytest import fixture, mark, skip

from keywords import vm_helper, host_helper
from utils import cli
from utils import table_parser
from utils.tis_log import LOG


# overall skip condition
def less_than_two_hypervisors():
    return len(host_helper.get_hypervisors()) < 2


# skip condition based on specific data set
def vm_tenant2_image_unavailable():
    table_ = table_parser.table(cli.openstack('server list', ssh_client=None)[
                                    1])  # auth_info unspecified, so it will run cli with primary tenant
    return 'tenant2-image' not in table_parser.get_column(table_, 'Name')


# Overall skipif condition for the whole test function (multiple test iterations)
# This should be a relatively static condition.i.e., independent with test params values
# @mark.skipif(less_than_two_hypervisors(), reason="Less than 2 hypervisor hosts on the system")
@mark.usefixtures('check_alarms')
@mark.parametrize(
    ('vm_boot_type', "vm_storage", "vm_interface", "block_migrate", "specify_host"), [
        ('volume', 'local_image', 'avp', False, True),
        ('volume', 'local_image', 'virtio', True, False),
        ('volume', 'local_image', 'virtio', False, False),
        ('image', 'local_image', '', True, True),  # local_image vm needs to be manually booted for now
        ('image', 'local_image', '', False, False),
        ('image', 'local_image', '', True, False),
        # ('volume', 'local_image', 'virtio', False, False),
        # ('volume', 'local_image', 'virtio', True, False),
        # ('volume', 'remote', 'vswitch', True, False),
    ])
# can add test fixture to configure hosts to be certain storage backing
def test_live_migrate_v1(vm_boot_type, vm_storage, vm_interface, block_migrate, specify_host):
    """
    Live migrate VM with:
        various vm storage type,
        various vm interface types,
        with/without block migration,
        with/without specify host when sending live-migration request

    Expected results can be successful or rejected depending on the VM storage details and hosts storage backing.

    Args:
        vm_boot_type (str): e.g, image, volume
        vm_storage (str): VM storage. e.g., local_image, local_volume, remote
        vm_interface (str): VM interface, e.g., virio, avp
        block_migrate (bool): Whether to live-migrate with block migration
        specify_host (bool): Whether to specify host in live-migration request

    =====
    Prerequisites (requirement for the system):
        - system is preconfigured to test scenario under test

    Skip conditions:
        - at least two hypervisor hosts on the system

    Test Steps:
        - Find/boot a VM that satisfy the given criteria
        - Find a suitable host to migrate to if specify_host is True
        - Attempt to live-migrate
        - Verify the results based on the return code

    """
    # Make skip decision based on the value(s) of test param(s) and the system condition
    if vm_boot_type == 'image' and vm_tenant2_image_unavailable():
        skip("VM named 'tenant2-image' doesn't exist on the system")

    # Mark test start
    # LOG.tc_start()

    # Mark test steps when applicable
    LOG.tc_step("Boot vm if not already booted.")

    if vm_boot_type == 'image':
        vm_name = 'tenant2-image'
        vm_id = vm_helper.get_vm_id_from_name(vm_name)
    else:
        # boot from volume using launch script from lab_setup
        vm_id = vm_helper.launch_vms_via_script(vm_type=vm_interface, num_vms=1)[0]

    dest_host = ''
    if specify_host:
        # This step only applicable when test param specify_host=True
        LOG.tc_step("Getting specific destination host")
        dest_host = vm_helper.get_dest_host_for_live_migrate(vm_id)

    # Another test step
    LOG.tc_step("Attempt to live migrate VM")
    return_code, message = vm_helper.live_migrate_vm(vm_id, fail_ok=True, block_migrate=block_migrate,
                                                     destination_host=dest_host)

    # Verify test results using assert
    LOG.tc_step("Verify test result")
    assert return_code in [0, 2], message
    # Can also add asserts to check the exact error message for negative test cases, i.e., return_code is 1

    # Mark test end
    # LOG.tc_end()


########################################################################################################################


@fixture(scope='function', params=['local_image', 'local_lvm', 'remote'])
def prepare_hosts(request):
    """
    Setup:
        Attempt to convert all computes to expected storage backing.
        Skip test if unsuccessful.

    Args:
        request: expected host storage backing to run the test

    Returns: hosts storage backing

    Teardown:
        Restore hosts to original state
    """
    expected_storage_backing = request.param
    avail_hosts = host_helper.get_hosts_in_storage_backing(storage_backing=expected_storage_backing)
    all_hosts = host_helper.get_hypervisors()
    modified_hosts = {}
    locked_hosts = []
    avail_num = len(avail_hosts)

    # Try to convert all available hypervisor hosts to the expected storage backing
    for host in all_hosts:
        if host not in avail_hosts:
            original_storage = host_helper.get_host_instance_backing(host)
            return_code, msg = host_helper.set_host_storage_backing(host=host, inst_backing=expected_storage_backing,
                                                                    fail_ok=True)
            if return_code == 0:
                avail_num += 1
                modified_hosts[host] = original_storage
            elif return_code == 1:  # Host locked, but cannot modify to the expected storage backing
                locked_hosts.append(host)
            else:
                skip("Host {} cannot be locked. Error: {}".format(host, msg))

    # Skip test if config failed
    if avail_num < 2:
        skip("Less than two hosts are successfully modified to {} backing".format(expected_storage_backing))

    # Teardown to restore hosts to original storage backing
    def restore_hosts():
        LOG.debug("Modifying hosts backing to original states..")
        host_helper.unlock_hosts(locked_hosts)
        for host in modified_hosts:
            host_helper.set_host_storage_backing(host, modified_hosts[host])

    request.addfinalizer(restore_hosts())

    return request.param
