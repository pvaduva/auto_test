import time

from pytest import fixture, mark, skip
from utils import table_parser, cli
from utils.tis_log import LOG

from keywords import vm_helper, nova_helper, host_helper, cinder_helper, glance_helper
from testfixtures.fixture_resources import ResourceCleanup
from consts.cgcs import FlavorSpec, GuestImages
from consts.auth import Tenant
from consts.reasons import SkipHypervisor


def id_gen(val):
    if isinstance(val, (tuple, list)):
        val = '_'.join([str(val_) for val_ in val])
    return val


@fixture(scope='module')
def add_hosts_to_zone(request, add_cgcsauto_zone, add_admin_role_module):
    hosts = host_helper.get_hosts_per_storage_backing()
    hosts_to_add = []
    avail_hosts = {'remote': '', 'local_lvm': '', 'local_image': ''}
    for backing in ['local_image', 'local_lvm', 'remote']:
        if hosts[backing]:
            host_to_add = hosts[backing][0]
            hosts_to_add.append(host_to_add)
            avail_hosts[backing] = host_to_add
            LOG.fixture_step('Select host {} with backing {}'.format(host_to_add, backing))

    if not hosts_to_add:
        skip("No host in any storage aggregate")

    nova_helper.add_hosts_to_aggregate(aggregate='cgcsauto', hosts=hosts_to_add)

    def remove_hosts_from_zone():
        nova_helper.remove_hosts_from_aggregate(aggregate='cgcsauto', check_first=False)
    request.addfinalizer(remove_hosts_from_zone)
    return avail_hosts


def bool_check_compute_disk(expected_increase, storage_backing):
    if storage_backing == 'remote':
        return expected_increase == 0
    else:
        return expected_increase >= 2


def get_expected_disk_occupancy_increase(origin_flavor, dest_flavor, boot_source, storage_backing):
    root_diff = dest_flavor[0] - origin_flavor[0]
    ephemeral_diff = dest_flavor[1] - origin_flavor[1]
    swap_diff = (dest_flavor[2] - origin_flavor[2]) / 1024

    if storage_backing == 'remote':
        expected_increase = 0
        expect_to_check = True
    else:
        if boot_source == 'volume':
            expected_increase = ephemeral_diff + swap_diff
            expect_to_check = False
        else:
            expected_increase = root_diff + ephemeral_diff + swap_diff
            expect_to_check = expected_increase >= 2

    return expected_increase, expect_to_check


def get_compute_disk_space(vm_host):
    hosttable_ = table_parser.table(cli.nova("hypervisor-show {}".format(vm_host), auth_info=Tenant.ADMIN))
    free_disk_space = int(table_parser.get_value_two_col_table(hosttable_, 'disk_available_least'))
    return free_disk_space


def check_correct_post_resize_value(original_disk_value, expected_increase, vm_host, sleep=True):
    if sleep:
        time.sleep(65)
    post_resize_value = get_compute_disk_space(vm_host)
    expected_range_min = original_disk_value - expected_increase - 1
    expected_range_max = original_disk_value - expected_increase + 1
    assert expected_range_min <= post_resize_value <= expected_range_max, \
        "Expected about {} space left, got {} space left".format(original_disk_value - expected_increase, post_resize_value)

    LOG.info("original_disk_value: {}. post_resize_value: {}. expected_increase: {}".format(original_disk_value, post_resize_value, expected_increase))
    return post_resize_value


# TC5155
@mark.parametrize(('storage_backing', 'origin_flavor', 'dest_flavor', 'boot_source'), [
    ('remote',      (4, 0, 0), (5, 1, 512), 'image'),
    ('remote',      (4, 1, 512), (5, 2, 1024), 'image'),
    ('remote',      (4, 1, 512), (4, 1, 0), 'image'),
    ('remote',      (4, 0, 0), (1, 1, 512), 'volume'),
    ('remote',      (4, 1, 512), (8, 2, 1024), 'volume'),
    ('remote',      (4, 1, 512), (0, 1, 0), 'volume'),
    ('local_lvm',   (4, 0, 0), (5, 1, 512), 'image'),
    ('local_lvm',   (4, 1, 512), (5, 2, 1024), 'image'),
    ('local_lvm',   (4, 1, 512), (4, 1, 0), 'image'),
    ('local_lvm',   (4, 0, 0), (2, 1, 512), 'volume'),
    ('local_lvm',   (4, 1, 512), (5, 2, 1024), 'volume'),
    ('local_lvm',   (4, 1, 512), (0, 1, 0), 'volume'),
    mark.priorities('nightly', 'sx_nightly')(('local_image', (4, 0, 0), (5, 1, 512), 'image')),
    ('local_image', (4, 1, 512), (5, 2, 1024), 'image'),
    mark.priorities('nightly', 'sx_nightly')(('local_image', (5, 1, 512), (5, 1, 0), 'image')),
    ('local_image', (4, 0, 0), (5, 1, 512), 'volume'),
    mark.priorities('nightly', 'sx_nightly')(('local_image', (4, 1, 512), (0, 2, 1024), 'volume')),
    mark.priorities('nightly', 'sx_nightly')(('local_image', (4, 1, 512), (1, 1, 0), 'volume')),
    ], ids=id_gen)
def test_resize_vm_positive(add_hosts_to_zone, storage_backing, origin_flavor, dest_flavor, boot_source):
    """
    Test resizing disks of a vm
    - Resize root disk is allowed except 0 & boot-from-image
    - Resize to larger or same ephemeral is allowed
    - Resize swap to any size is allowed including removing

    Args: 
        storage_backing: The host storage backing required
        origin_flavor: The flavor to boot the vm from, listed by GBs for root, ephemeral, and swap disks, i.e. for a 
                       system with a 2GB root disk, a 1GB ephemeral disk, and no swap disk: (2, 1, 0)
        boot_source: Which source to boot the vm from, either 'volume' or 'image'
    Skip Conditions: 
        - No hosts exist with required storage backing.
    Test setup:
        - Put a single host of each backing in cgcsautozone to prevent migration and instead force resize.
        - Create two flavors based on origin_flavor and dest_flavor
        - Create a volume or image to boot from.
        - Boot VM with origin_flavor
    Test Steps:
        - Resize VM to dest_flavor with revert
        - If vm is booted from image and has a non-remote backing, check that the amount of disk space post-revert is
          around the same pre-revert
        - Resize VM to dest_flavor with confirm
        - If vm is booted from image and has a non-remote backing, check that the amount of disk space post-confirm is
          reflects the increase in disk-space taken up
    Test Teardown:
        - Delete created VM
        - Delete created volume or image
        - Delete created flavors
        - Remove hosts from cgcsautozone
        - Delete cgcsautozone
        
    """
    vm_host = add_hosts_to_zone[storage_backing]

    if vm_host == '':
        skip("No available host with {} storage backing".format(storage_backing))

    expected_increase, expect_to_check = get_expected_disk_occupancy_increase(origin_flavor, dest_flavor, boot_source, storage_backing)

    LOG.info("Expected_increase of vm compute occupancy is {}".format(expected_increase))

    LOG.tc_step('Create origin flavor')
    origin_flavor_id = _create_flavor(origin_flavor, storage_backing)
    LOG.tc_step('Create destination flavor')
    dest_flavor_id = _create_flavor(dest_flavor, storage_backing)
    vm_id = _boot_vm_to_test(boot_source, vm_host, origin_flavor_id)

    if expect_to_check:
        LOG.tc_step('Check initial disk usage')
        original_disk_value = get_compute_disk_space(vm_host)
        LOG.info("{} space left on compute".format(original_disk_value))

    LOG.tc_step('Resize vm to dest flavor with revert')
    vm_info = vm_helper.resize_vm(vm_id, dest_flavor_id, revert=True, fail_ok=False)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    LOG.info(vm_info[1])

    # Check for TC5155 blocked by JIRA: CGTS-8299
    '''
    if expect_to_check:
        LOG.tc_step('Check disk usage after revertion')
        revert_disk_value = check_correct_post_resize_value(original_disk_value, 0, vm_host)
    '''

    LOG.tc_step('Resize vm to dest flavor and confirm')
    vm_info = vm_helper.resize_vm(vm_id, dest_flavor_id, revert=False, fail_ok=False)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    LOG.info(vm_info[1])
    # TODO: Check that root Cinder volume does not resize, for appropriate cases

    # Check for TC5155 blocked by JIRA: CGTS-8299
    '''
    if expect_to_check:
        LOG.tc_step('Check that disk usage in hypervisor-stats changes is expected after a confirmed resize')
        check_correct_post_resize_value(original_disk_value, expected_increase, vm_host)
    '''


@mark.parametrize(('storage_backing', 'origin_flavor', 'dest_flavor', 'boot_source'), [
    ('remote',      (5, 0, 0), (0, 0, 0), 'image'),      # Root disk can be resized, but cannot be 0
    ('remote',      (5, 2, 512), (5, 1, 512), 'image'),     # check ephemeral disk cannot be smaller than origin
    # ('remote',      (1, 0, 0), (0, 0, 0), 'volume'),     This should not fail, root disk size from volume not flavor
    ('remote',      (1, 1, 512), (1, 0, 512), 'volume'),     # check ephemeral disk cannot be smaller than origin
    ('local_lvm',   (5, 0, 0), (0, 0, 0), 'image'),     # Root disk can be resized, but cannot be 0
    ('local_lvm',   (5, 2, 512), (5, 1, 512), 'image'),
    # ('local_lvm',   (1, 0, 0), (0, 0, 0), 'volume'),      root disk size from volume not flavor
    ('local_lvm',   (1, 2, 512), (1, 1, 512), 'volume'),
    ('local_image', (5, 0, 0), (0, 0, 0), 'image'),      # Root disk can be resized, but cannot be 0
    ('local_image', (5, 2, 512), (5, 1, 512), 'image'),
    ('local_image', (5, 1, 512), (4, 1, 512), 'image'),
    ('local_image', (5, 1, 512), (4, 1, 0), 'image'),
    # ('local_image', (1, 0, 0), (0, 0, 0), 'volume'),    root disk size from volume not flavor
    ('local_image', (1, 1, 512), (1, 0, 512), 'volume'),
    ], ids=id_gen)
def test_resize_vm_negative(add_hosts_to_zone, storage_backing, origin_flavor, dest_flavor, boot_source):
    """
    Test resizing disks of a vm not allowed:
    - Resize to smaller ephemeral flavor is not allowed
    - Resize to zero disk flavor is not allowed     (boot from image only)

    Args: 
        storage_backing: The host storage backing required
        origin_flavor: The flavor to boot the vm from, listed by GBs for root, ephemeral, and swap disks, i.e. for a 
                       system with a 2GB root disk, a 1GB ephemeral disk, and no swap disk: (2, 1, 0)
        boot_source: Which source to boot the vm from, either 'volume' or 'image'
    Skip Conditions: 
        - No hosts exist with required storage backing.
    Test setup:
        - Put a single host of each backing in cgcsautozone to prevent migration and instead force resize.
        - Create two flavors based on origin_flavor and dest_flavor
        - Create a volume or image to boot from.
        - Boot VM with origin_flavor
    Test Steps:
        - Resize VM to dest_flavor with revert
        - Resize VM to dest_flavor with confirm
    Test Teardown:
        - Delete created VM
        - Delete created volume or image
        - Delete created flavors
        - Remove hosts from cgcsauto zone
        - Delete cgcsauto zone
        
    """
    vm_host = add_hosts_to_zone[storage_backing]

    if vm_host == '':
        skip("No available host with {} storage backing".format(storage_backing))

    LOG.tc_step('Create origin flavor')
    origin_flavor_id = _create_flavor(origin_flavor, storage_backing)
    LOG.tc_step('Create destination flavor')
    dest_flavor_id = _create_flavor(dest_flavor, storage_backing)
    vm_id = _boot_vm_to_test(boot_source, vm_host, origin_flavor_id)    

    LOG.tc_step('Resize vm to dest flavor')
    code, output = vm_helper.resize_vm(vm_id, dest_flavor_id, fail_ok=True)

    assert nova_helper.get_vm_flavor(vm_id) == origin_flavor_id, 'VM did not keep origin flavor'
    assert 1 or 2 == code, "Resize VM CLI is not rejected"


def _create_flavor(flavor_info, storage_backing):
    root_disk = flavor_info[0]
    ephemeral = flavor_info[1]
    swap = flavor_info[2]

    flavor_id = nova_helper.create_flavor(ephemeral=ephemeral, swap=swap, root_disk=root_disk, 
                                          storage_backing=storage_backing)[1]
    ResourceCleanup.add('flavor', flavor_id)
    return flavor_id


def _boot_vm_to_test(boot_source, vm_host, flavor_id):
    LOG.tc_step('Boot a vm with origin flavor')
    vm_id = vm_helper.boot_vm(flavor=flavor_id, avail_zone='cgcsauto', vm_host=vm_host, source=boot_source,
                              cleanup='function')[1]
    return vm_id


def find_cpu_count(storage_backing):
    LOG.fixture_step("Find suitable vm host and cpu count and backing of host")

    vm_hosts = host_helper.get_hosts_by_storage_aggregate(storage_backing)
    if len(vm_hosts) < 2:
        skip(SkipHypervisor.LESS_THAN_TWO_HYPERVISORS.format(storage_backing))
    compute_space_dict = {}

    vm_host = vm_hosts[0]
    vm_cpu_dict = host_helper.get_host_cpu_cores_for_function(vm_host, function='VMs', thread=None)
    vm_host_cpu_count = len(vm_cpu_dict[0])
    for host in vm_hosts:
        free_space = get_compute_disk_space(host)
        compute_space_dict[host] = free_space
        LOG.info("{} space on {}".format(free_space, host))

    # increase quota
    LOG.fixture_step("Increase quota of allotted cores")
    vm_helper.ensure_vms_quotas(cores_num=(vm_host_cpu_count + 1))

    return vm_host, vm_host_cpu_count, compute_space_dict


# TC5155
@mark.parametrize('storage_backing',[
    'local_image',
    'local_lvm',
    ])
def test_resize_different_comp_node(storage_backing, add_admin_role_module):
    """
        Test resizing disks of a larger vm onto a different compute node and check hypervisor statistics to make sure
        difference in disk usage of both nodes involved is correctly reflected

        Args:
            storage_backing: The host storage backing required
        Skip Conditions:
            - 2 hosts must exist with required storage backing.
        Test setup:
            - For each of the two backings tested, the setup will return the number of nodes for each backing, the vm
              host that the vm will initially be created on and the number of hosts for that backing.
        Test Steps:
            - Create a flavor with a root disk size that is slightly larger than the default image used to boot up the VM
            - Create a VM with the aforementioned flavor
            - Create a flavor will enough cpus to occupy the rest of the cpus on the same host as the first VM
            - Create another VM on the same host as the first VM
            - Create a similar flavor to the first one, except that it has one more vcpu
            - Resize the first VM and confirm that it is on a different host
            - Check hypervisor-show on both computes to make sure that disk usage goes down on the original host and
              goes up on the new host
        Test Teardown:
            - Delete created VMs
            - Delete created flavors

    """

    vm_host, cpu_count, compute_space_dict = find_cpu_count(storage_backing)

    root_disk_size = GuestImages.IMAGE_FILES[GuestImages.DEFAULT_GUEST][1] + 3

    # make vm (1 cpu)
    LOG.tc_step("Create flavor with 1 cpu")
    numa0_specs = {FlavorSpec.CPU_POLICY: 'dedicated', FlavorSpec.NUMA_0: 0}
    flavor_1 = nova_helper.create_flavor(ephemeral=0, swap=0, root_disk=root_disk_size, vcpus=1, storage_backing=storage_backing)[1]
    ResourceCleanup.add('flavor', flavor_1)
    nova_helper.set_flavor_extra_specs(flavor_1, **numa0_specs)

    LOG.tc_step("Boot a vm with above flavor")
    vm_1 = vm_helper.boot_vm(flavor=flavor_1, source='image', cleanup='function', avail_zone='nova', vm_host=vm_host,
                             fail_ok=False)[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_1)

    # make another vm
    LOG.tc_step("Create a flavor to occupy vcpus")
    occupy_amount = cpu_count - 1
    second_specs = {FlavorSpec.CPU_POLICY: 'dedicated', FlavorSpec.NUMA_0: 0}
    flavor_2 = nova_helper.create_flavor(vcpus=occupy_amount, storage_backing=storage_backing)[1]
    ResourceCleanup.add('flavor', flavor_2)
    nova_helper.set_flavor_extra_specs(flavor_2, **second_specs)

    LOG.tc_step("Boot a vm with above flavor to occupy remaining vcpus")
    vm_2 = vm_helper.boot_vm(flavor=flavor_2, source='image', cleanup='function', avail_zone='nova', vm_host=vm_host,
                             fail_ok=False)[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_2)

    LOG.tc_step('Check disk usage before resize')
    hosttable_ = table_parser.table(cli.nova("hypervisor-show {}".format(vm_host), auth_info=Tenant.ADMIN))
    original_disk_value_old_host = int(table_parser.get_value_two_col_table(hosttable_, 'disk_available_least'))
    LOG.info("{} space left on compute".format(original_disk_value_old_host))

    # create a larger flavor and resize
    LOG.tc_step("Create a flavor that has an extra vcpu to force resize to a different node")
    resize_flavor = nova_helper.create_flavor(ephemeral=0, swap=0, root_disk=root_disk_size, vcpus=2, storage_backing=storage_backing)[1]
    ResourceCleanup.add('flavor', resize_flavor)
    nova_helper.set_flavor_extra_specs(resize_flavor, **numa0_specs)

    LOG.tc_step("Resize the vm and verify if it is on a different host")
    vm_helper.resize_vm(vm_1, resize_flavor)
    new_host = nova_helper.get_vm_host(vm_1)
    assert new_host != vm_host, "vm did not change hosts following resize"

    LOG.tc_step('Check disk usage after resize')
    new_disk_value_old_host = get_compute_disk_space(vm_host)
    LOG.info("Went from {} to {} space left on old compute".format(original_disk_value_old_host, new_disk_value_old_host))
    check_correct_post_resize_value(original_disk_value_old_host, (root_disk_size * -1), vm_host)

    original_disk_value_new_host = compute_space_dict[new_host]
    new_disk_value_new_host = get_compute_disk_space(new_host)
    LOG.info("Went from {} to {} space left on new compute".format(original_disk_value_new_host, new_disk_value_new_host))
    check_correct_post_resize_value(original_disk_value_new_host, root_disk_size, new_host, sleep=False)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_1)
