##########################################################################
# Memory page size tests with host configured to support 1g and 4k pages #
##########################################################################

import re

from pytest import fixture, mark, skip

from utils import table_parser, cli
from utils.tis_log import LOG
from consts.cgcs import FlavorSpec, ImageMetadata, NovaCLIOutput
from keywords import nova_helper, vm_helper, glance_helper, host_helper, system_helper, cinder_helper
from testfixtures.fixture_resources import ResourceCleanup


@fixture(scope='module')
def flavor_2g(add_1g_and_4k_pages):
    hosts, storage_backing = add_1g_and_4k_pages
    flavor = nova_helper.create_flavor(name='flavor-2g', ram=2048, check_storage_backing=False,
                                       storage_backing=storage_backing)[1]
    ResourceCleanup.add('flavor', resource_id=flavor, scope='module')

    return flavor, hosts, storage_backing


@fixture(scope='module', autouse=True)
def add_1g_and_4k_pages(config_host_module, add_hosts_to_zone):
    storage_backing, hosts = add_hosts_to_zone

    LOG.fixture_step("Configure system to have 1 host support 1G pages and 1 host support 4k pages")
    headers = ['vm_total_4K', 'vm_hp_total_2M', 'vm_hp_total_1G', 'mem_avail(MiB)']
    mem_host_0_proc_0 = system_helper.get_host_mem_values(hosts[0], headers, 0)
    mem_host_0_proc_1 = system_helper.get_host_mem_values(hosts[0], headers, 1)
    mem_host_1_proc_0 = system_helper.get_host_mem_values(hosts[1], headers, 0)
    mem_host_1_proc_1 = system_helper.get_host_mem_values(hosts[1], headers, 1)
    mem_host_0_proc_0 = [int(val) for val in mem_host_0_proc_0]
    mem_host_0_proc_1 = [int(val) for val in mem_host_0_proc_1]
    mem_host_1_proc_0 = [int(val) for val in mem_host_1_proc_0]
    mem_host_1_proc_1 = [int(val) for val in mem_host_1_proc_1]

    expt_4k = 2 * 1024 * 1024 / 4
    expt_1g = 2
    host0_proc0_mod = host0_proc1_mod = host1_proc0_mod = host1_proc1_mod = True
    if mem_host_0_proc_0[0] < expt_4k and mem_host_0_proc_0[2] < expt_1g:
        host0_proc0_mod = False
    if mem_host_0_proc_1[0] < expt_4k and mem_host_0_proc_1[2] >= expt_1g:
        host0_proc1_mod = False
    if mem_host_1_proc_0[0] < expt_4k and mem_host_1_proc_0[2] < expt_1g:
        host1_proc0_mod = False
    if mem_host_1_proc_1[0] >= expt_4k and mem_host_1_proc_1[2] < expt_1g:
        host1_proc1_mod = False

    def _modify(host):
        if host == hosts[0]:
            if host0_proc0_mod is True:
                host0_proc0_2m = int((mem_host_0_proc_0[3] - 1024) / 2 - 150)
                LOG.fixture_step("Modify host0 proc0 to have 0 of 1GB pages and 1GB of 4k pages")
                cli.system("host-memory-modify -2M {} -1G {} {} {}".format(host0_proc0_2m, 0, hosts[0], 0))
            if host0_proc1_mod is True:
                # host0_proc1_2m = int((mem_host_0_proc_1[3] - 3 * 1024) / 2)
                host0_proc1_2m = int((mem_host_0_proc_1[3] - 2 * 1024) / 2 - 150)
                LOG.fixture_step("Modify host0 proc1 to have 2GB of 1GB pages and 1GB of 4k pages")
                cli.system("host-memory-modify -2M {} -1G {} {} {}".format(int(host0_proc1_2m), 2, hosts[0], 1))
        elif host == hosts[1]:
            if host1_proc0_mod is True:
                host1_proc0_2m = int((mem_host_1_proc_0[3] - 1024) / 2 - 150)
                LOG.fixture_step("Modify host1 proc0 to have 0 of 1GB pages and 1GB of 4k pages")
                cli.system("host-memory-modify -2M {} -1G {} {} {}".format(int(host1_proc0_2m), 0, hosts[1], 0))
            if host1_proc1_mod is True:
                # host1_proc1_2m = int((mem_host_1_proc_1[3] - 3 * 1024) / 2)
                host1_proc1_2m = int((mem_host_1_proc_1[3] - 2 * 1024) / 2 - 150)
                LOG.fixture_step("Modify host1 proc1 to have 0 of 1GB pages and 2GB of 4k pages")
                cli.system("host-memory-modify -2M {} -1G {} {} {}".format(host1_proc1_2m, 0, hosts[1], 1))

    def _revert(host):
        header = ['mem_avail(MiB)']

        if host == hosts[0]:
            if host0_proc0_mod:
                host_0_proc_0_2g = ((int(system_helper.get_host_mem_values(hosts[0], header, 0)[0]) -
                                    (mem_host_0_proc_0[2] * 1024)) / 2) - 150
                if host_0_proc_0_2g < mem_host_0_proc_0[1]:
                    cli.system("host-memory-modify -2M {} -1G {} {} {}".format(int(host_0_proc_0_2g),
                                                                               mem_host_0_proc_0[2], hosts[0], 0))
                else:
                    cli.system("host-memory-modify -2M {} -1G {} {} {}".format(int(mem_host_0_proc_0[1]),
                                                                               mem_host_0_proc_0[2], hosts[0], 0))

            if host0_proc1_mod:
                host_0_proc_1_2g = ((int(system_helper.get_host_mem_values(hosts[0], header, 1)[0]) -
                                    (mem_host_0_proc_1[2] * 1024)) / 2) - 150
                if host_0_proc_1_2g < mem_host_0_proc_1[1]:
                    cli.system("host-memory-modify -2M {} -1G {} {} {}".format(int(host_0_proc_1_2g),
                                                                               mem_host_0_proc_1[2], hosts[0], 1))
                else:
                    cli.system("host-memory-modify -2M {} -1G {} {} {}".format(int(mem_host_0_proc_1[1]),
                                                                               mem_host_0_proc_1[2], hosts[0], 1))
        elif host == hosts[1]:
            if host1_proc0_mod:
                host_1_proc_0_2g = ((int(system_helper.get_host_mem_values(hosts[1], header, 0)[0]) -
                                    (mem_host_1_proc_0[2] * 1024)) / 2) - 150
                if host_1_proc_0_2g < mem_host_1_proc_0[1]:
                    cli.system("host-memory-modify -2M {} -1G {} {} {}".format(int(host_1_proc_0_2g),
                                                                               mem_host_1_proc_0[2], hosts[1], 0))
                else:
                    cli.system("host-memory-modify -2M {} -1G {} {} {}".format(int(mem_host_1_proc_0[1]),
                                                                               mem_host_1_proc_0[2], hosts[1], 0))
            if host1_proc1_mod:
                host_1_proc_1_2g = ((int(system_helper.get_host_mem_values(hosts[1], header, 1)[0]) -
                                    (mem_host_1_proc_1[2] * 1024)) / 2) - 150
                if host_1_proc_1_2g < mem_host_1_proc_1[1]:
                    cli.system("host-memory-modify -2M {} -1G {} {} {}".format(int(host_1_proc_1_2g),
                                                                               mem_host_1_proc_1[2], hosts[1], 1))
                else:
                    cli.system("host-memory-modify -2M {} -1G {} {} {}".format(int(mem_host_1_proc_1[1]),
                                                                               mem_host_1_proc_1[2], hosts[1], 1))

    if host0_proc0_mod or host0_proc1_mod:
        config_host_module(host=hosts[0], modify_func=_modify, revert_func=_revert)

    if host1_proc1_mod or host1_proc0_mod:
        config_host_module(host=hosts[1], modify_func=_modify, revert_func=_revert)

    return hosts, storage_backing


@fixture(scope='module')
def add_hosts_to_zone(request, add_cgcsauto_zone, add_admin_role_module):
    storage_backing, target_hosts = nova_helper.get_storage_backing_with_max_hosts()

    if len(target_hosts) < 2:
        skip("Less than two up hosts have same storage backing")

    hosts_to_add = [target_hosts[0], target_hosts[1]]
    nova_helper.add_hosts_to_aggregate(aggregate='cgcsauto', hosts=hosts_to_add)

    def remove_host_from_zone():
        nova_helper.remove_hosts_from_aggregate(aggregate='cgcsauto', check_first=False)
    request.addfinalizer(remove_host_from_zone)

    return storage_backing, hosts_to_add


testdata = [None, 'any', 'large', 'small', '2048', '1048576']
@fixture(params=testdata)
def flavor_mem_page_size(request, flavor_2g):
    flavor_id = flavor_2g[0]
    mem_page_size = request.param

    if mem_page_size is None:
        nova_helper.unset_flavor_extra_specs(flavor_id, FlavorSpec.MEM_PAGE_SIZE)
    else:
        nova_helper.set_flavor_extra_specs(flavor_id, **{FlavorSpec.MEM_PAGE_SIZE: mem_page_size})

    return mem_page_size


@fixture(scope='module')
def image_mempage():
    image_id = glance_helper.create_image(name='mempage')[1]
    ResourceCleanup.add('image', image_id, scope='module')

    return image_id


@mark.p1
@mark.parametrize('image_mem_page_size', testdata)
def test_boot_vm_mem_page_size(flavor_2g, flavor_mem_page_size, image_mempage, image_mem_page_size):
    """
    Test boot vm with various memory page size setting in flavor and image.

    Args:
        flavor_2g (tuple): flavor id of a flavor with ram set to 2G, hosts configured and storage_backing
        flavor_mem_page_size (str): memory page size extra spec value to set in flavor
        image_mempage (str): image id for tis image
        image_mem_page_size (str): memory page metadata value to set in image

    Setup:
        - Create a flavor with 2G RAM (module)
        - Get image id of tis image (module)

    Test Steps:
        - Set/Unset flavor memory page size extra spec with given value (unset if None is given)
        - Set/Unset image memory page size metadata with given value (unset if None if given)
        - Attempt to boot a vm with above flavor and image
        - Verify boot result based on the mem page size values in the flavor and image

    Teardown:
        - Delete vm if booted
        - Delete created flavor (module)

    """
    flavor_id, hosts, storage_backing = flavor_2g

    if image_mem_page_size is None:
        nova_helper.delete_image_metadata(image_mempage, ImageMetadata.MEM_PAGE_SIZE)
        expt_code = 0

    else:
        nova_helper.set_image_metadata(image_mempage, **{ImageMetadata.MEM_PAGE_SIZE: image_mem_page_size})
        if flavor_mem_page_size is None:
            expt_code = 4

        elif flavor_mem_page_size.lower() in ['any', 'large']:
            expt_code = 0

        else:
            expt_code = 0 if flavor_mem_page_size.lower() == image_mem_page_size.lower() else 4

    LOG.tc_step("Attempt to boot a vm with flavor_mem_page_size: {}, and image_mem_page_size: {}. And check return "
                "code is {}.".format(flavor_mem_page_size, image_mem_page_size, expt_code))

    actual_code, vm_id, msg, vol_id = vm_helper.boot_vm(name='mem_page_size', flavor=flavor_id, source='image',
                                                        source_id=image_mempage, fail_ok=True, avail_zone='cgcsauto',
                                                        cleanup='function')

    assert expt_code == actual_code, "Expect boot vm to return {}; Actual result: {} with msg: {}".format(
            expt_code, actual_code, msg)

    if expt_code != 0:
        assert re.search(NovaCLIOutput.VM_BOOT_REJECT_MEM_PAGE_SIZE_FORBIDDEN, msg)
    else:
        assert nova_helper.get_vm_host(vm_id) in hosts, "VM is not booted on hosts in cgcsauto zone"
        LOG.tc_step("Ensure VM is pingable from NatBox")
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)


@mark.usefixtures('add_admin_role_module')
@mark.parametrize('mem_page_size', [
    mark.priorities('domain_sanity', 'nightly')('1048576'),
    mark.p2('large'),
    mark.nightly('small'),
])
def test_schedule_vm_mempage_config(flavor_2g, mem_page_size):
    """
    Test memory used by vm is taken from the expected memory pool and the vm was scheduled on the correct host/processor

    Args:
        flavor_2g (tuple): flavor id of a flavor with ram set to 2G, hosts, storage_backing
        mem_page_size (str): mem page size setting in flavor
        volume_ (str): id of the volume to boot vm from

    Setup:
        - Create host aggregate
        - Add two hypervisors to the host aggregate
        - Host-0 configuration:
            - Processor-0:
                - Not enough 1g pages to boot vm that requires 2g
                - Not enough 4k pages to boot vm that requires 2g
            - Processor-1:
                - Sufficient 1g pages to boot vm that requires 2g
                - Not enough 4k pages to boot vm that requires 2g
        - Host-1 configuration:
            - Processor-0:
                - Not enough 1g pages to boot vm that requires 2g
                - Not enough 4k pages to boot vm that requires 2g
            - Processor-1:
                - Not enough 1g pages to boot vm that requires 2g
                - Sufficient 4k pages to boot vm that requires 2g
        - Configure a compute to have 4 1G hugepages (module)
        - Create a flavor with 2G RAM (module)
        - Create a volume with default values (module)

    Test Steps:
        - Set memory page size flavor spec to given value
        - Boot a vm with above flavor and a basic volume
        - Calculate the available/used memory change on the vm host
        - Verify the memory is taken from 1G hugepage memory pool
        - Verify the vm was booted on a supporting host

    Teardown:
        - Delete created vm
        - Delete created volume and flavor (module)
        - Re-Configure the compute to have 0 hugepages (module)
        - Revert host mem pages back to original
    """
    flavor_id, hosts_configured, storage_backing = flavor_2g
    LOG.tc_step("Set memory page size extra spec in flavor")
    nova_helper.set_flavor_extra_specs(flavor_id, **{FlavorSpec.CPU_POLICY: 'dedicated',
                                                     FlavorSpec.MEM_PAGE_SIZE: mem_page_size})

    host_helper.wait_for_hypervisors_up(hosts_configured)
    pre_computes_tab = system_helper.get_vm_topology_tables('computes')[0]

    LOG.tc_step("Boot a vm with mem page size spec - {}".format(mem_page_size))

    host_1g, host_4k = hosts_configured
    code, vm_id, msg, vo = vm_helper.boot_vm('mempool_configured', flavor_id, fail_ok=True, avail_zone='cgcsauto',
                                             cleanup='function')
    assert 0 == code, "VM is not successfully booted."

    vm_host, vm_node = vm_helper.get_vm_host_and_numa_nodes(vm_id)
    if mem_page_size == '1048576':
        assert host_1g == vm_host, "VM is not created on the configured host {}".format(hosts_configured[0])
        assert vm_node == [1], "VM (huge) did not boot on the correct processor"
    elif mem_page_size == 'small':
        assert host_4k == vm_host, "VM is not created on the configured host {}".format(hosts_configured[1])
        assert vm_node == [1], "VM (small) did not boot on the correct processor"
    else:
        assert vm_host in hosts_configured

    LOG.tc_step("Calculate memory change on vm host - {}".format(vm_host))

    instance_topology = vm_helper.get_instance_topology(vm_id)
    for topology in instance_topology:
        vm_page_size = topology['pgsize']
    if mem_page_size == 'small':
        mem_table_header = 'A:mem_4K'
    elif mem_page_size == 'large' and vm_page_size == '2M':
        mem_table_header = 'A:mem_2M'
    else:
        mem_table_header = 'A:mem_1G'

    pre_computes_tab = table_parser.filter_table(pre_computes_tab, Host=vm_host)
    pre_used_mems = [int(mem) for mem in table_parser.get_column(pre_computes_tab, 'U:memory')[0]]
    pre_avail_mems = table_parser.get_column(pre_computes_tab, mem_table_header)[0]
    pre_avail_mems = [int(mem) for mem in pre_avail_mems]

    post_computes_tab = system_helper.get_vm_topology_tables('computes')[0]
    post_computes_tab = table_parser.filter_table(post_computes_tab, Host=vm_host)
    post_used_mems = [int(mem) for mem in table_parser.get_column(post_computes_tab, 'U:memory')[0]]
    post_avail_mems = table_parser.get_column(post_computes_tab, mem_table_header)[0]
    post_avail_mems = [int(mem) for mem in post_avail_mems]
    LOG.info("{}: Pre used mem: {}, post used mem:{}; Pre available: {}, post avail mem: {}".
             format(vm_host, pre_used_mems, post_used_mems, pre_avail_mems, post_avail_mems))

    LOG.tc_step("Verify memory is taken from {} pool".format(mem_table_header))
    assert sum(pre_used_mems) + 2048 == sum(post_used_mems), "Used memory is not increase by 2048MiB"
    assert sum(pre_avail_mems) - 2048 == sum(post_avail_mems), ("Available memory in {} page pool is not decreased "
                                                                "by 2048MiB").format(mem_page_size)

    LOG.tc_step("Ensure vm is pingable from NatBox")
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
