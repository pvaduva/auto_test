import re

from pytest import fixture, mark

from utils.tis_log import LOG
from utils import table_parser
from consts.cgcs import FlavorSpec, ImageMetadata
from keywords import nova_helper, vm_helper, glance_helper, system_helper, cinder_helper
from testfixtures.resource_mgmt import ResourceCleanup


#########################################
# Test set memory page size flavor spec #
#########################################

@mark.sanity
@mark.parametrize('mem_page_size', [
    'small',
    'large',
    'any',
    '2048',
    '1048576',
])
def test_set_mem_page_size_extra_specs(flavor_id_module, mem_page_size):
    nova_helper.set_flavor_extra_specs(flavor_id_module, **{FlavorSpec.MEM_PAGE_SIZE: mem_page_size})


#####################################################
# Test memory is taken from proper memory page pool #
#####################################################

@fixture(scope='module')
def flavor_1g():
    flavor = nova_helper.create_flavor(name='flavor-1g', ram=1024)[1]
    ResourceCleanup.add('flavor', resource_id=flavor, scope='module')

    return flavor


@fixture(scope='module')
def volume_():
    vol_id = cinder_helper.create_volume('vol-mem_page_size')[1]
    ResourceCleanup.add('volume', vol_id, scope='module')
    return vol_id


@mark.p1
@mark.parametrize('mem_page_size', [
    '2048',
    'large',
    'small',
    '1048576',
])
def test_vm_mem_pool(flavor_1g, mem_page_size, volume_):
    """
    Test memory used by vm is taken from the expected memory pool

    Args:
        flavor_1g (str): flavor id of a flavor with ram set to 1G
        mem_page_size (str): mem page size setting in flavor
        volume_ (str): id of the volume to boot vm from

    Setup:
        - Create a flavor with 1G RAM (module)
        - Create a volume with default values (module)

    Test Steps:
        - Set memory page size flavor spec to given value
        - Attempt to boot a vm with above flavor and a basic volume
        - Verify the system is taking memory from the expected memory pool:
            - If boot vm succeeded:
                - Calculate the available/used memory change on the vm host
                - Verify the memory is taken from memory pool specified via mem_page_size
            - If boot vm failed:
                - Verify system attempted to take memory from expected pool, but insufficient memory is available

    Teardown:
        - Delete created vm
        - Delete created volume and flavor (module)

    """
    LOG.tc_step("Set memory page size extra spec in flavor")
    nova_helper.set_flavor_extra_specs(flavor_1g, **{FlavorSpec.CPU_POLICY: 'dedicated', 
                                                     FlavorSpec.MEM_PAGE_SIZE: mem_page_size})

    # Save the vm-topology table before booting vm
    pre_computes_tab = system_helper.get_vm_topology_tables('computes')[0]

    LOG.tc_step("Boot a vm with mem page size spec - {}".format(mem_page_size))
    code, vm_id, msg, vol_id = vm_helper.boot_vm('mempool_'+mem_page_size, flavor_1g, source='volume',
                                                 source_id=volume_, fail_ok=True)
    ResourceCleanup.add('vm', vm_id, del_vm_vols=False)

    assert code in [0, 1], "Actual result for booting vm: {}".format(msg)

    if code == 1:
        LOG.tc_step("Check boot vm rejected due to insufficient memory from {} pool".format(mem_page_size))
        fault_msg = nova_helper.get_vm_nova_show_value(vm_id, 'fault')
        if mem_page_size == '1048576':
            req_num = '1G'
        else:
            req_num = mem_page_size
        pattern = "Not enough memory.*req: {}".format(req_num)
        assert bool(re.search(pattern, fault_msg))
        return

    # If vm booted successfully:
    vm_host = nova_helper.get_vm_host(vm_id)
    LOG.tc_step("Calculate memory change on vm host - {}".format(vm_host))

    avail_headers = []
    if mem_page_size == '2048':
        avail_headers = ['A:mem_2M']
    elif mem_page_size == 'large':
        avail_headers = ['A:mem_2M', 'A:mem_1G']
    elif mem_page_size == 'small':
        avail_headers = ['A:mem_4K']
    elif mem_page_size == '1048576':
        avail_headers = ['A:mem_1G']

    # Calculate used and available memories before booting vm
    pre_computes_tab = table_parser.filter_table(pre_computes_tab, Host=vm_host)
    pre_used_mem = sum([int(mem) for mem in table_parser.get_column(pre_computes_tab, 'U:memory')[0]])
    pre_avail_mems = []
    for header in avail_headers:
        pre_avail_mems += table_parser.get_column(pre_computes_tab, header)[0]
    pre_avail_mems = [int(mem) for mem in pre_avail_mems]

    # Calculate used and available memories after booting vm
    post_computes_tab = system_helper.get_vm_topology_tables('computes')[0]
    post_computes_tab = table_parser.filter_table(post_computes_tab, Host=vm_host)
    post_used_mem = sum([int(mem) for mem in table_parser.get_column(post_computes_tab, 'U:memory')[0]])
    post_avail_mems = []
    for header in avail_headers:
        post_avail_mems += table_parser.get_column(post_computes_tab, header)[0]
    post_avail_mems = [int(mem) for mem in post_avail_mems]

    LOG.tc_step("Check memory is taken from mem page pool that matches mem_page_size - {} via vm-topology.".
                format(mem_page_size))
    assert pre_used_mem + 1024 == post_used_mem, "Used memory is not increased by 1024MiB"
    assert sum(pre_avail_mems) - 1024 == sum(post_avail_mems), ("Available memory in {} page pool is not decreased "
                                                                "by 1024MiB").format(mem_page_size)
