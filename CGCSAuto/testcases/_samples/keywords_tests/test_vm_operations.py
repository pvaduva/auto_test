from pytest import mark, skip

import keywords.cinder_helper
import keywords.glance_helper
from consts.auth import Tenant
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper

_skip = False


def test_cold_migrate():
    vm_id = vm_helper.launch_vms_via_script()[0]
    vm_helper.cold_migrate_vm(vm_id)
    vm_helper.cold_migrate_vm(vm_id, revert=True)


@mark.parametrize(('name', 'flavor', 'source', 'source_name'), [
    (None, 'test_yang', 'volume', None),
    ('img', 'test_yang', 'image', 'cirros'),
    ('snapshot', 'test_yang', 'snapshot', None),
])
def test_boot_vm(name, flavor, source, source_name):
    vm_id = vm_helper.boot_vm(name=name, flavor=flavor, source=source, source_id=source_name)[1]
    LOG.info("VM ID: {}".format(vm_id))
    # cli.nova('delete', vm_id)


@mark.parametrize(('name', 'swap', 'ephemeral', 'storage', 'cpu_policy'),[
    (None, None, None, 'local_image', 'shared'),
    (None, 0, 1, 'local_image', 'shared'),
    ('test', 1, 1, 'local_lvm', 'dedicated'),
    ('test', 1, None, 'local_lvm', 'shared')
])
def test_create_flavor(name, swap, ephemeral, storage, cpu_policy):
    flavor_id = nova_helper.create_flavor(name=name, swap=swap, ephemeral=ephemeral)[1]
    LOG.info("Flavor id: {}".format(flavor_id))
    specs = {'aggregate_instance_extra_specs:storage': storage,
             'hw:cpu_policy': cpu_policy}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **specs)


@mark.parametrize('vm_count', [
    1,
    2,
    'all',
])
def test_ping_vms_from_natbox(vm_count):
    if vm_count == 'all':
        vm_ids = None
    else:
        vm_ids = vm_helper.get_any_vms(count=vm_count)

    assert vm_ids != []

    vm_helper.ping_vms_from_natbox(vm_ids=vm_ids, fail_ok=False)


@mark.parametrize('vm_count', [
    1,
    2,
    'all'
])
def test_ping_vms_from_vm_1(vm_count):
    from_vm = vm_helper.get_any_vms(count=1)[0]
    if vm_count == 'all':
        vm_ids = None
    else:
        vm_ids = vm_helper.get_any_vms(count=vm_count)

    assert vm_ids != ()

    vm_helper.ping_vms_from_vm(to_vms=vm_ids, from_vm=from_vm, fail_ok=False)


@mark.parametrize('vm_image', [
    # 'cgcs-guest',
    # 'ubuntu',
    'wrl5',
    'centos',
])
def test_ping_vms_from_vm_various_images(vm_image):
    image_id = keywords.glance_helper.get_image_id_from_name(name=vm_image, strict=False)
    if not image_id:
        skip("No image name has substring: {}.".format(vm_image))

    vol_size = 1
    if vm_image in ['ubuntu', 'centos']:
        vol_size = 8
    vol_id = keywords.cinder_helper.create_volume(name='vol_' + vm_image, image_id=image_id, size=vol_size)[1]
    vm_id = vm_helper.boot_vm(source='volume', source_id=vol_id)[1]

    vm_helper.ping_vms_from_vm(from_vm=vm_id)


def test_ping_vms_from_vm_2():
    to_vms = vm_helper.get_any_vms(auth_info=Tenant.ADMIN, all_tenants=True)
    for vm in vm_helper.get_any_vms():
        vm_helper.ping_vms_from_vm(from_vm=vm, to_vms=to_vms)
