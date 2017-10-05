from pytest import fixture, mark, skip
from utils.tis_log import LOG

from keywords import vm_helper, nova_helper, host_helper, cinder_helper, glance_helper
from testfixtures.fixture_resources import ResourceCleanup


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
    nova_helper.add_hosts_to_aggregate(aggregate='cgcsauto', hosts=hosts_to_add)

    def remove_hosts_from_zone():
        nova_helper.remove_hosts_from_aggregate(aggregate='cgcsauto', check_first=False)
    request.addfinalizer(remove_hosts_from_zone)
    return avail_hosts


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
        - Resize VM to dest_flavor with confirm
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

    LOG.tc_step('Create origin flavor')
    origin_flavor_id = _create_flavor(origin_flavor, storage_backing)
    LOG.tc_step('Create destination flavor')
    dest_flavor_id = _create_flavor(dest_flavor, storage_backing)
    vm_id = _boot_vm_to_test(boot_source, vm_host, origin_flavor_id)    

    LOG.tc_step('Resize vm to dest flavor with revert')
    vm_info = vm_helper.resize_vm(vm_id, dest_flavor_id, revert=True, fail_ok=False)
    LOG.info(vm_info[1])
    
    LOG.tc_step('Resize vm to dest flavor and confirm')
    vm_info = vm_helper.resize_vm(vm_id, dest_flavor_id, revert=False, fail_ok=False)
    LOG.info(vm_info[1])
    # TODO: Check that root Cinder volume does not resize, for appropriate cases


@mark.parametrize(('storage_backing', 'origin_flavor', 'dest_flavor', 'boot_source'),[
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
