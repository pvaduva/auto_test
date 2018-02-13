from pytest import mark, fixture

from utils.tis_log import LOG

from keywords import host_helper, vm_helper, nova_helper
from testfixtures.fixture_resources import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover

# To Avoid:

TEST_DATA = [('compute-0', 'local_image'),
             ('compute-0', 'local_lvm'),
             ('compute-0', 'remote'), ]

@fixture(scope='module', params=TEST_DATA)
def modify_system_backing(request):
    """
    Issues in this fixture:
    - Hardcoded compute name
        - compute could be in bad state
        - Does not work for CPE lab
    - Lock unlock 6 times    (could be only 3 times)
    - Did not check original storage backing    (lab could be configured with local_lvm by default)

    """
    hostname, storage_backing = request.param

    LOG.fixture_step("Modify {} storage backing to {}".format(hostname, storage_backing))
    host_helper.lock_host(hostname)
    host_helper.modify_host_lvg(hostname, inst_backing=storage_backing, lock=False)
    host_helper.unlock_hosts(hostname)

    def revert_host():
        LOG.fixture_step("Revert {} storage backing to local_image".format(hostname))
        host_helper.lock_host(hostname)
        host_helper.modify_host_lvg(hostname, inst_backing='local_image', lock=False)
        host_helper.unlock_hosts(hostname)
    request.addfinalizer(revert_host)

    return storage_backing


def test_something_avoid(modify_system_backing):
    """
    Test to AVOID! Do NOT parametrize module/class level fixture unless you are absolutely sure about the impact and
    intend to do so. Note that when a module level fixture is parametrized, both the setups AND teardowns will be run
    multiple times.

    Args:
        modify_system_backing:

    Setups:
        - Lock host, modify host storage backing to given backing, unlock host      (module)

    Test Steps:
        - Create a flavor with specified storage backing
        - Boot vm from above flavor

    Teardown:
        - Delete created vm, volume, flavor
        - Lock host, modify host storage backing to local_image, unlock host      (module)

    """
    LOG.tc_step("Create a flavor with specified storage backing")
    storage_backing = modify_system_backing
    flv_id = nova_helper.create_flavor(name='test_avoid_flv', storage_backing=storage_backing,
                                       check_storage_backing=False)[1]
    ResourceCleanup.add(resource_type='flavor', resource_id=flv_id)

    LOG.tc_step("Boot vm from above flavor")
    vm_id = vm_helper.boot_vm(name='test_avoid_vm', flavor=flv_id)[1]
    ResourceCleanup.add(resource_type='vm', resource_id=vm_id)


##############################################################################################################
# Good practice:


@fixture(scope='module')
def host_to_modify(request):
    """
    Select a hypervisor from existing hosts to test

    Args:
        request: pytset arg

    Returns (str): hostname

    """

    target_host = host_helper.get_nova_host_with_min_or_max_vms(rtn_max=False)
    original_backing = host_helper.get_host_instance_backing(host=target_host)

    # Ensure unlock attempt on target_host after running all test cases using this fixture
    HostsToRecover.add(target_host, scope='module')

    def revert_host():
        LOG.fixture_step("Revert {} storage backing to {} if needed".format(target_host, original_backing))
        host_helper.modify_host_lvg(target_host, inst_backing=original_backing, check_first=True, lock=True, unlock=True)

    request.addfinalizer(revert_host)

    return target_host


@mark.parametrize('storage_backing', [
    'local_image',
    'remote',
    'local_lvm'
])
def test_something(host_to_modify, storage_backing):
    """
    Test parametrize the test function instead of the test fixture.

    Args:
        host_to_modify (str): fixture that returns the hostname under test
        storage_backing (str): storage backing to configure

    Setups:
        - Select a host and record the storage backing before test starts    (module)

    Test Steps:
        - Modify host storage backing to given storage backing if not already on it
        - Create a flavor with specified storage backing
        - Boot vm from above flavor

    Teardown:
        - Delete created vm, volume, flavor
        - Modify host storage backing to its original config if not already on it     (module)

    """
    # Modify host storage backing withc check_first=True, so it will not modify if already in that backing
    # if lock_host() has to be done inside test case, set swact=True, so it will handle CPE case
    LOG.tc_step("Modify {} storage backing to {} if not already has the matching storage backing".format(
            host_to_modify, storage_backing))
    host_helper.modify_host_lvg(host_to_modify, inst_backing=storage_backing, check_first=True,
                                lock=True, unlock=True)

    LOG.tc_step("Create a flavor with specified storage backing")
    flv_id = nova_helper.create_flavor(name='test_avoid_flv', storage_backing=storage_backing,
                                       check_storage_backing=False)[1]
    ResourceCleanup.add(resource_type='flavor', resource_id=flv_id)

    LOG.tc_step("Boot vm from above flavor")
    vm_id = vm_helper.boot_vm(name='test_avoid_vm', flavor=flv_id)[1]
    ResourceCleanup.add(resource_type='vm', resource_id=vm_id)
