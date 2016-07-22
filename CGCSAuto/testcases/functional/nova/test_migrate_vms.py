from pytest import fixture, mark, skip

from utils.tis_log import LOG

from consts.cgcs import FlavorSpec
from keywords import vm_helper, nova_helper, system_helper, host_helper
from testfixtures.resource_mgmt import ResourceCleanup



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
    if len(host_helper.get_hosts_by_storage_aggregate(storage_backing=storage)) < 1:
        skip("No host support {} storage backing".format(storage))

    flavor_id = nova_helper.create_flavor(ephemeral=param[0], swap=param[1], check_storage_backing=False)[1]
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

@mark.skipif(len(host_helper.get_hypervisors()) < 2, reason="Less than 2 hypervisor hosts on the system")
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
    live_mig_allowed = vm_helper._is_live_migration_allowed(vm_id=vm_id, block_migrate=block_migrate) and \
                       vm_helper.get_dest_host_for_live_migrate(vm_id)
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


@mark.skipif(len(host_helper.get_hypervisors()) < 2, reason="Less than 2 hypervisor hosts on the system")
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
    hosts_with_backing = host_helper.get_hosts_by_storage_aggregate(vm_storage_backing)
    if system_helper.is_small_footprint():
        up_hosts = host_helper.get_nova_hosts()
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


@fixture(scope='module')
def hosts_per_stor_backing():
    hosts_per_backing = host_helper.get_hosts_per_storage_backing()
    LOG.fixture_step("Hosts per storage backing: {}".format(hosts_per_backing))

    if max([len(hosts) for hosts in list(hosts_per_backing.values())]) < 2:
        skip("No two hosts have the same storage backing")

    return hosts_per_backing


@mark.parametrize(('storage_backing', 'ephemeral', 'swap', 'cpu_pol', 'vcpus', 'vm_type'), [
    mark.p1(('local_image', 0, 0, None, 1, 'volume')),
    mark.p1(('local_image', 0, 0, 'dedicated', 2, 'volume')),
    mark.p1(('local_image', 1, 0, 'shared', 2, 'image')),
    mark.p1(('local_image', 0, 1, 'dedicated', 1, 'image')),
    mark.p1(('local_lvm', 0, 0, None, 1, 'volume')),
    mark.p1(('local_lvm', 0, 0, 'dedicated', 2, 'volume')),
    mark.p1(('remote', 0, 0, None, 2, 'volume')),
    mark.p1(('remote', 1, 0, None, 1, 'volume')),
    mark.p1(('remote', 1, 1, None, 1, 'image')),
    mark.p1(('remote', 0, 1, None, 2, 'image_with_vol')),
])
def test_live_migrate_vm_positive(storage_backing, ephemeral, swap, cpu_pol, vcpus, vm_type, hosts_per_stor_backing):
    if len(hosts_per_stor_backing[storage_backing]) < 2:
        skip("Less than two hosts have {} storage backing".format(storage_backing))

    LOG.tc_step("Create a flavor with {} vcpus, {} ephemera disk, {} swap disk".format(vcpus, ephemeral, swap))
    flavor_id = nova_helper.create_flavor(name='live-mig', ephemeral=ephemeral, swap=swap, vcpus=vcpus,
                                          check_storage_backing=False)[1]
    ResourceCleanup.add('flavor', flavor_id)

    specs = {FlavorSpec.STORAGE_BACKING: storage_backing}
    if cpu_pol is not None:
        specs[FlavorSpec.CPU_POLICY] = cpu_pol

    LOG.tc_step("Add following extra specs: {}".format(specs))
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **specs)

    boot_source = 'volume' if vm_type == 'volume' else 'image'
    LOG.tc_step("Boot a vm from {}".format(boot_source))
    vm_id = vm_helper.boot_vm('live-mig', flavor=flavor_id, source=boot_source)[1]
    # ResourceCleanup.add('vm', vm_id)

    if vm_type == 'image_with_vol':
        LOG.tc_step("Attach volume to vm")
        vm_helper.attach_vol_to_vm(vm_id=vm_id)

    LOG.tc_step("Check sudo vcpupin before live mgirating vm")
    if cpu_pol == 'dedicated':
        pre_vm_host = nova_helper.get_vm_host(vm_id)
        # Check host side info such as nova-compute.log and virsh pcpupin
        instance_name = nova_helper.get_vm_instance_name(vm_id)
        with host_helper.ssh_to_host(pre_vm_host) as host_ssh:

            LOG.tc_step("Check vcpus for vm is the same via vm-topology and virsh vcpupin")
            vcpus_for_vm = host_helper.get_vcpus_for_instance_via_virsh(host_ssh, instance_name=instance_name)

            for vcpu in vcpus_for_vm:
                assert 1 == len(vcpus_for_vm[vcpu]), "More than 1 cpus listed in virsh vcpupin for dedicated vm"

    LOG.tc_step("Live migrate VM and ensure it succeeded")
    block_mig = True if boot_source == 'image' else False
    code, output = vm_helper.live_migrate_vm(vm_id, block_migrate=block_mig)
    assert 0 == code, "Live migrate is not successful. Details: {}".format(output)

    LOG.tc_step("Check vm topology stay unchanged")
    instance_topology = vm_helper.get_instance_topology(vm_id)

    expt_cpu_pol = 'ded' if cpu_pol == 'dedicated' else 'sha'
    pcpus_total = []
    for topology_on_numa_node in instance_topology:  # Cannot be on two numa nodes for dedicated vm unless specified
        assert expt_cpu_pol == topology_on_numa_node['pol'], "CPU policy is not {} in vm-topology".format(expt_cpu_pol)

        actual_siblings = topology_on_numa_node['siblings']
        actual_topology = topology_on_numa_node['topology']
        actual_pcpus = topology_on_numa_node['pcpus']
        pcpus_total += actual_pcpus

        if expt_cpu_pol == 'ded':
            assert topology_on_numa_node['thr'] == 'no', "cpu thread policy is in vm topology"
            if vcpus == 1:
                assert not actual_siblings, "siblings should not be included with only 1 vcpu"
            else:
                assert actual_siblings, "siblings should be included for dedicated vm"
            assert '1c,{}t'.format(vcpus) in actual_topology, 'vm topology is not as expected.'
            assert vcpus == len(actual_pcpus), "pcpus number for dedicated vm is not the same as setting in flavor"
        else:
            assert topology_on_numa_node['thr'] is None, "cpu thread policy is in vm topology"
            assert actual_siblings is None, 'siblings should not be included for floating vm'
            assert actual_topology is None, 'topology should not be included for floating vm'
            assert actual_pcpus is None, "pcpu should not be included in vm-topology for floating vm"

    if cpu_pol == 'dedicated':
        post_vm_host = nova_helper.get_vm_host(vm_id)
        assert pre_vm_host != post_vm_host, "VM host did not change after live migration"

        # Check host side info such as nova-compute.log and virsh pcpupin
        instance_name = nova_helper.get_vm_instance_name(vm_id)
        with host_helper.ssh_to_host(post_vm_host) as host_ssh:

            LOG.tc_step("Check vcpus for vm is the same via vm-topology and virsh vcpupin")
            vcpus_for_vm = host_helper.get_vcpus_for_instance_via_virsh(host_ssh, instance_name=instance_name)

            for vcpu in vcpus_for_vm:
                assert 1 == len(vcpus_for_vm[vcpu]), "More than 1 cpus listed in virsh vcpupin for dedicated vm"
