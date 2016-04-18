import random

from pytest import fixture, mark, skip

import keywords.host_helper
from utils.tis_log import LOG
from consts.auth import Tenant
from setup_consts import P1, P2, P3
from keywords import vm_helper, nova_helper, system_helper, host_helper, cinder_helper


flavor_params = [
    # 'ephemeral', 'swap', 'storage_backing'
    (0, 0, 'local_image'),
    (0, 0, 'local_lvm'),
    (0, 0, 'remote'),
    (0, 1, 'local_lvm'),
    (1, 0, 'local_image'),
    (1, 1, 'remote'),
]
@fixture(scope='module', params=flavor_params)
def flavor_(request):
    """
    Text fixture to create flavor with specific 'ephemeral', 'swap', and 'storage_backing'
    Args:
        request: pytest arg

    Returns: flavor dict as following:
        {'id': <flavor_id>,
         'local_disk': <0 or 1>,
         'storage': <'local_image', 'local_lvm', or 'remote'>
        }
    """
    param = request.param
    storage = param[2]
    if len(keywords.host_helper.get_hosts_by_storage_aggregate(storage_backing=storage)) < 1:
        skip("No host support {} storage backing".format(storage))

    flavor_id = nova_helper.create_flavor(ephemeral=param[0], swap=param[1])[1]
    storage_spec = {'aggregate_instance_extra_specs:storage': storage}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **storage_spec)
    flavor = {'id': flavor_id,
              'local_disk': param[0] or param[1],
              'storage': storage
              }

    def delete_flavor():
        nova_helper.delete_flavors(flavor_ids=flavor_id, fail_ok=True)
    request.addfinalizer(delete_flavor)

    return flavor


@fixture(scope='module', params=['volume', 'image', 'image_with_vol'])
def vm_(request, flavor_):
    """
    Test fixture to create vm from volume, image or image_with_vol with given flavor.

    Args:
        request: pytest arg
        flavor_: flavor_ fixture which passes the created flavor based on ephemeral', 'swap', and 'storage_backing'

    Returns: vm dict as following:
        {'id': <vm_id>,
          'boot_source': <image or volume>,
          'image_with_vol': <True or False>,
          'storage': <local_image, local_lvm, or remote>,
          'local_disk': <True or False>,
          }
    """
    storage = flavor_['storage']
    boot_source = 'image' if 'image' in request.param else 'volume'

    vm_id = vm_helper.boot_vm(flavor=flavor_['id'], source=boot_source)[1]

    image_with_vol = request.param == 'image_with_vol'
    if image_with_vol:
        vm_helper.attach_vol_to_vm(vm_id=vm_id)

    vm = {'id': vm_id,
          'boot_source': boot_source,
          'image_with_vol': image_with_vol,
          'storage': storage,
          'local_disk': request.param == 'image' or bool(flavor_['local_disk']),
          }

    def delete():
        vm_helper.delete_vms(vm_id, delete_volumes=True)
    request.addfinalizer(delete)

    return vm


@mark.skipif(len(keywords.host_helper.get_hypervisors()) < 2, reason="Less than 2 hypervisor hosts on the system")
@mark.parametrize(
        "block_migrate", [
            False,
            True,
        ])
def test_live_migrate_vm(vm_, block_migrate):
    """
    Test live migrate vm with various configs for:
        vm boot source, has volume attached, has local disk, storage backing, block migrate

    Args:
        vm_ (dict): vm created by vm_ fixture
        block_migrate (bool): Whether to migrate with block

    Test Setups:
    - create flavor with specific 'ephemeral', 'swap', and 'storage_backing'
    - boot vm from specific boot source with specific flavor
    - (attach volume to vm in one specific scenario)

    Test Steps:
    - Calculate expected result based on: vm boot source, attached volume, local disk, storage backing, block migrate.
    - Attempt to live migrate
    - Assert result based on the pre-calculated expectation.

    Skip conditions:
     - Less than two hypervisor hosts on system
     - Hosts local storage backing is not already configured to required storage backing.

    """
    LOG.tc_step("Calculate expected result...")
    vm_id = vm_['id']
    live_mig_allowed = vm_helper._is_live_migration_allowed(vm_id=vm_id, block_migrate=block_migrate) \
                       and vm_helper.get_dest_host_for_live_migrate(vm_id)
    exp_code = 0 if live_mig_allowed else 1

    extra_msg = ''
    if vm_['boot_source'] == 'image':
        extra_msg = "Volume attached: {}; ".format(vm_['image_with_vol'])
    LOG.tc_step("Attempt to live migrate vm {}..."
                "\nVM details - Boot Source: {}; {}Local Disk: {}; Storage Backing: {}; Block Migrate: {}.".
                format(vm_['id'], vm_['boot_source'], extra_msg, vm_['local_disk'], vm_['storage'], block_migrate))
    code, msg = vm_helper.live_migrate_vm(vm_id=vm_id, block_migrate=block_migrate, fail_ok=True)

    if exp_code == 1:
        check_msg = "Verify live migration request rejected..."
    else:
        check_msg = "Verify live migration succeeded..."
    LOG.tc_step(check_msg)
    assert exp_code == code, "Expected return code {}. Actual return code: {}; details: {}".format(exp_code, code, msg)


@mark.skipif(len(keywords.host_helper.get_hypervisors()) < 2, reason="Less than 2 hypervisor hosts on the system")
@mark.parametrize(
        "revert", [
            False,
            True,
        ])
def test_cold_migrate_vm(vm_, revert):
    """
    Test live migrate vm with various configs for: vm boot source, has volume attached, has local disk, storage backing

    Args:
        vm_ (dict): vm created by vm_ fixture
        revert (bool): whether to revert

    Test Setups:
    - create flavor with specific 'ephemeral', 'swap', and 'storage_backing'
    - boot vm from specific boot source with specific flavor
    - (attach volume to vm in one specific scenario)

    Test Steps:
    - Cold migrate vm created by vm_ fixture
    - Assert cold migration and confirm/revert succeeded

    Skip conditions:
     - Less than two hypervisor hosts on system

    """

    LOG.tc_step("Check whether host with same storage backing available for cold migrate vm...")
    vm_id = vm_['id']
    vm_storage_backing = nova_helper.get_vm_storage_type(vm_id=vm_id)
    hosts_with_backing = keywords.host_helper.get_hosts_by_storage_aggregate(vm_storage_backing)
    if system_helper.is_small_footprint():
        up_hosts = host_helper.get_nova_computes()
    else:
        up_hosts = host_helper.get_hypervisors(state='up', status='enabled')
    candidate_hosts = list(set(hosts_with_backing) & set(up_hosts))
    if len(candidate_hosts) < 2:
        expt = 1
        check_msg = "Verify cold migration request rejected..."
    else:
        expt = 0
        check_msg = "Verify cold migration succeeded..."

    extra_msg = ''
    if vm_['boot_source'] == 'image':
        extra_msg = "Volume attached: {}; ".format(vm_['image_with_vol'])
    LOG.tc_step("Attempt to cold migrate vm {}..."
                "\nVM details - Boot Source: {}; {}Local Disk: {}; Storage Backing: {}.".
                format(vm_['id'], vm_['boot_source'], extra_msg, vm_['local_disk'], vm_['storage']))
    code, msg = vm_helper.cold_migrate_vm(vm_id=vm_id, revert=revert, fail_ok=True)

    LOG.tc_step(check_msg)
    assert code == expt, "Expected return code {}. Actual return code: {}; details: {}".format(expt, code, msg)
