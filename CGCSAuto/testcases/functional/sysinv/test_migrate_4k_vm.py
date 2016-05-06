

from pytest import fixture, mark, skip


from utils.tis_log import LOG
from keywords import vm_helper, nova_helper, system_helper, host_helper, cinder_helper


flavor_params = [
    # 'ephemeral', 'swap', 'storage_backing'
    (0, 0, 'local_image'),
]
@fixture(scope='module', params=flavor_params)
def flavor_(request):
    """
    Text fixture to create flavor with specific 'ephemeral', 'swap', and 'mem_page_size'
    Args:
        request: pytest arg

    Returns: flavor dict as following:
        {'id': <flavor_id>,
         'boot_source : image
         'pagesize': pagesize
        }
    """
    pagesize = 'small'
    param = request.param
    storage = param[2]
    if len(host_helper.get_hosts_by_storage_aggregate(storage_backing=storage)) < 1:
        skip("No host support {} storage backing".format(storage))

    flavor_id = nova_helper.create_flavor(ephemeral=param[0], swap=param[1])[1]
    storage_spec = {'aggregate_instance_extra_specs:storage': storage}
    pagesize_spec = {'hw:mem_page_size': pagesize}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **pagesize_spec)
    flavor = {'id': flavor_id,
              'local_disk': param[0] or param[1],
              'storage': storage,
              'page_size': pagesize_spec
              }

    # verify there is enough 4k pages on compute nodes to create 4k page flavor
    is_enough_4k_page_memory()

    def delete_flavor():
        nova_helper.delete_flavors(flavor_ids=flavor_id, fail_ok=True)
    request.addfinalizer(delete_flavor)

    return flavor


@fixture(scope='module', params=['volume'])
def vm_(request, flavor_):

    storage = flavor_['storage']
    boot_source = 'image' if 'image' in request.param else 'volume'

    vm_id = vm_helper.boot_vm(flavor=flavor_['id'], source=boot_source)[1]

    image_with_vol = request.param == 'image_with_vol'
    pagesize=flavor_['page_size']
    if image_with_vol:
        vm_helper.attach_vol_to_vm(vm_id=vm_id)

    vm = {'id': vm_id,
          'boot_source': boot_source,
          'image_with_vol': image_with_vol,
          'storage': storage,
          'local_disk': request.param == 'image' or bool(flavor_['local_disk']),
          'page_size': flavor_['page_size'],
          }

    def delete_vm():
        vm_helper.delete_vms(vm_id, delete_volumes=True)
    request.addfinalizer(delete_vm)

    return vm


def is_enough_4k_page_memory():
    """
    Check if there is enough 4k pages on any compute node on any processors is a bit hassle

    Returns:

    """
    # check if any 4k pages greater than 60000 means more than 2G total.
    check = False
    for host in host_helper.get_hypervisors():
        for proc_id in [0,1]:
            num_4k_page = system_helper.get_host_mem_values(host, ['vm_total_4K'], proc_id=proc_id)
            if int(num_4k_page[0]) > 600000:
                check = True
                break
    if not check:
        # randomly pick a compute node and give it enough 4k pages
        host_helper.lock_host('compute-1')
        system_helper.set_host_4k_pages('compute-1', proc_id=1, smallpage_num=600000)
        host_helper.unlock_host('compute-1')


@mark.skipif(len(host_helper.get_hypervisors()) < 2, reason="Less than 2 hypervisor hosts on the system")
@mark.parametrize(
        "block_migrate", [
            False,
            True,
        ])
def test_live_migrate_vm(vm_, block_migrate):
    """
    Test live migrate vm with 4k page config.
    This is almost a direct copy of /functional/nova/test_migrate_vms.py with minor differences

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


