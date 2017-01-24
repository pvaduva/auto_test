##########################################################################
# Memory page size tests with host configured to support 1g and 4k pages #
##########################################################################

import re

from pytest import fixture, mark

from utils import table_parser, cli
from utils.tis_log import LOG
from consts.cgcs import FlavorSpec, ImageMetadata, NovaCLIOutput
from keywords import nova_helper, vm_helper, glance_helper, host_helper, system_helper, cinder_helper, check_helper
from testfixtures.resource_mgmt import ResourceCleanup


@fixture(scope='module')
def flavor_2g(add_1g_and_4k_pages):
    storage_backing = add_1g_and_4k_pages[1]
    flavor = nova_helper.create_flavor(name='flavor-2g', ram=2048, check_storage_backing=False,
                                       storage_backing=storage_backing)[1]
    ResourceCleanup.add('flavor', resource_id=flavor, scope='module')

    return flavor


def _modify(host):
    system_helper.set_host_1g_pages(host=host, proc_id=0, hugepage_num=2)
    system_helper.set_host_4k_pages(host=host, proc_id=1, smallpage_num=2048*2*1024/4)


def _revert(host):
    # Assume 1g page number is 0 by default
    system_helper.set_host_1g_pages(host, proc_id=0, hugepage_num=0)


@fixture(scope='module', autouse=True)
def add_1g_and_4k_pages(config_host_module):
    host = host_helper.get_nova_host_with_min_or_max_vms(rtn_max=False)

    config_host_module(host=host, modify_func=_modify, revert_func=_revert)
    host_helper.wait_for_hosts_in_nova_compute(host)

    storage_backing = host_helper.get_local_storage_backing(host)
    LOG.info("Host's storage backing: {}".format(storage_backing))
    if 'image' in storage_backing:
        storage_backing = 'local_image'
    elif 'lvm' in storage_backing:
        storage_backing = 'local_lvm'

    return host, storage_backing


testdata = [None, 'any', 'large', 'small', '2048', '1048576']
@fixture(params=testdata)
def flavor_mem_page_size(request, flavor_2g):
    mem_page_size = request.param

    if mem_page_size is None:
        nova_helper.unset_flavor_extra_specs(flavor_2g, FlavorSpec.MEM_PAGE_SIZE)
    else:
        nova_helper.set_flavor_extra_specs(flavor_2g, **{FlavorSpec.MEM_PAGE_SIZE: mem_page_size})

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
        flavor_2g (str): flavor id of a flavor with ram set to 2G
        flavor_mem_page_size (str): memory page size extra spec value to set in flavor
        image_mempage (str): image id for cgcs-guest image
        image_mem_page_size (str): memory page metadata value to set in image

    Setup:
        - Create a flavor with 2G RAM (module)
        - Get image id of cgcs-guest image (module)

    Test Steps:
        - Set/Unset flavor memory page size extra spec with given value (unset if None is given)
        - Set/Unset image memory page size metadata with given value (unset if None if given)
        - Attempt to boot a vm with above flavor and image
        - Verify boot result based on the mem page size values in the flavor and image

    Teardown:
        - Delete vm if booted
        - Delete created flavor (module)

    """

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

    actual_code, vm_id, msg, vol_id = vm_helper.boot_vm(name='mem_page_size', flavor=flavor_2g, source='image',
                                                        source_id=image_mempage, fail_ok=True)

    if vm_id:
        ResourceCleanup.add('vm', vm_id, scope='function', del_vm_vols=False)

    assert expt_code == actual_code, "Expect boot vm to return {}; Actual result: {} with msg: {}".format(
            expt_code, actual_code, msg)

    if expt_code != 0:
        assert re.search(NovaCLIOutput.VM_BOOT_REJECT_MEM_PAGE_SIZE_FORBIDDEN, msg)
    else:
        LOG.tc_step("Ensure VM is pingable from NatBox")
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)


@fixture(scope='module')
def volume_():
    vol_id = cinder_helper.create_volume('vol-hugepage')[1]
    ResourceCleanup.add('volume', vol_id, scope='module')
    return vol_id


@mark.usefixtures('add_admin_role_module')
@mark.parametrize('mem_page_size', [
    mark.domain_sanity('1048576'),
    mark.p1('large'),
])
def test_vm_mem_pool_1g(flavor_2g, mem_page_size, volume_, add_1g_and_4k_pages):
    """
    Test memory used by vm is taken from the expected memory pool

    Args:
        flavor_2g (str): flavor id of a flavor with ram set to 2G
        mem_page_size (str): mem page size setting in flavor
        volume_ (str): id of the volume to boot vm from

    Setup:
        - Configure a compute to have 4 1G hugepages (module)
        - Create a flavor with 2G RAM (module)
        - Create a volume with default values (module)

    Test Steps:
        - Set memory page size flavor spec to given value
        - Boot a vm with above flavor and a basic volume
        - Calculate the available/used memory change on the vm host
        - Verify the memory is taken from 1G hugepage memory pool

    Teardown:
        - Delete created vm
        - Delete created volume and flavor (module)
        - Re-Configure the compute to have 0 hugepages (module)

    """
    host_configured, storage_backing = add_1g_and_4k_pages
    LOG.tc_step("Set memory page size extra spec in flavor")
    nova_helper.set_flavor_extra_specs(flavor_2g, **{FlavorSpec.CPU_POLICY: 'dedicated',
                                                     FlavorSpec.MEM_PAGE_SIZE: mem_page_size})

    host_helper.wait_for_hosts_in_nova_compute(host_configured)
    pre_computes_tab = system_helper.get_vm_topology_tables('computes')[0]

    LOG.tc_step("Boot a vm with mem page size spec - {}".format(mem_page_size))
    boot_host = host_configured if mem_page_size == 'large' else None

    code, vm_id, msg, vo = vm_helper.boot_vm('mempool_1g', flavor_2g, source='volume', source_id=volume_, fail_ok=True,
                                             avail_zone='nova', vm_host=boot_host)
    ResourceCleanup.add('vm', vm_id, del_vm_vols=False)
    assert 0 == code, "VM is not successfully booted."

    vm_host = nova_helper.get_vm_host(vm_id)
    assert host_configured == vm_host, "VM is not created on the configured host {}".format(vm_host)

    LOG.tc_step("Calculate memory change on vm host - {}".format(vm_host))

    pre_computes_tab = table_parser.filter_table(pre_computes_tab, Host=vm_host)
    pre_used_mems = [int(mem) for mem in table_parser.get_column(pre_computes_tab, 'U:memory')[0]]
    pre_avail_mems = table_parser.get_column(pre_computes_tab, 'A:mem_1G')[0]
    pre_avail_mems = [int(mem) for mem in pre_avail_mems]

    post_computes_tab = system_helper.get_vm_topology_tables('computes')[0]
    post_computes_tab = table_parser.filter_table(post_computes_tab, Host=vm_host)
    post_used_mems = [int(mem) for mem in table_parser.get_column(post_computes_tab, 'U:memory')[0]]
    post_avail_mems = table_parser.get_column(post_computes_tab, 'A:mem_1G')[0]
    post_avail_mems = [int(mem) for mem in post_avail_mems]
    LOG.info("{}: Pre used mem: {}, post used mem:{}; Pre avail 1g mem: {}, post avail 1g mem: {}".
             format(vm_host, pre_used_mems, post_used_mems, pre_avail_mems, post_avail_mems))

    LOG.tc_step("Verify memory is taken from 1G hugepage pool")
    assert sum(pre_used_mems) + 2048 == sum(post_used_mems), "Used memory is not increase by 2048MiB"
    assert sum(pre_avail_mems) - 2048 == sum(post_avail_mems), ("Available memory in {} page pool is not decreased "
                                                                "by 2048MiB").format(mem_page_size)

    LOG.tc_step("Ensure vm is pingable from NatBox")
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)


@mark.usefixtures('add_admin_role_module')
@mark.parametrize(('vcpus', 'memory'), [
    mark.p2((8, 2048)),
])
def test_scheduling_vm_mem_page_size(vcpus, memory):
    """
    Test vm with huge_mem_page gets booted on supporting host

    Args:
        vcpus: Amount of vcpu(s) to use.
        memory: Amount of RAM to use.

    Test Setups:
        - Create host aggregate
        - Add two hypervisors to the host aggregate
        - Host-0 configuration:
            - Processor-0:
                - Not enough 1g pages to boot vm that requires 1g pages
                - Not enough 4k pages to boot vm that requires 1g pages
            - Processor-1:
                - Sufficient 1g pages to boot vm that requires 1g pages
                - Not enough 4k pages to boot vm that requires 1g pages
        - Host-1 configuration:
            - Processor-0:
                - Not enough 1g pages to boot vm that requires 1g pages
                - Not enough 4k pages to boot vm that requires 1g pages
            - Processor-1:
                - sufficient 4k pages to boot vm that requires 1g pages
                - Not enough 1g pages to boot vm that requires 1g pages
        - Create flavor, flavor_huge, with extra-specs; MEM_PAGE_SIZE: 1048576
        - Create flavor, flavor_small, with extra-specs; MEM_PAGE_SIZE: small

    Test Steps:
        - Boot two vm's, one with flavor_huge, the other with flavor_small
        - Wait until both vm's are pingable from natbox
        - Check vm with flavor_huge is booted on Host-0, Processor-1
        - Check vm with flavor_small is booted on Host-1, Processor-1

    Test Teardown
        - Delete host aggregate\
        - Delete created volumes and flavors
    """
    LOG.tc_step("Create aggregate test_scheduling")
    nova_helper.create_aggregate(name='test_scheduling')
    LOG.tc_step("Get list of 'up' and 'enabled' hypervisors")
    target_hosts = host_helper.get_hypervisors(state='up', status='enabled')
    assert len(target_hosts) >= 2, "Not 2 or more hypervisors. Cannot properly test."
    LOG.tc_step("Add the first two found hypervisors to test_scheduling aggregate")
    nova_helper.add_hosts_to_aggregate(aggregate='test_scheduling', hosts=target_hosts[0:2])
    image_id = glance_helper.get_image_id_from_name('cgcs-guest', strict=True)

    LOG.tc_step("Set all 1g pages")
    # Put into a loop later, logic is complicated
    system_helper.set_host_1g_pages(host=target_hosts[0], proc_id=0, hugepage_num=0)
    system_helper.set_host_1g_pages(host=target_hosts[0], proc_id=1, hugepage_num=2)
    system_helper.set_host_1g_pages(host=target_hosts[1], proc_id=0, hugepage_num=0)
    system_helper.set_host_1g_pages(host=target_hosts[1], proc_id=1, hugepage_num=0)

    LOG.tc_step("Set all 4k pages")
    system_helper.set_host_4k_pages(host=target_hosts[0], proc_id=0, smallpage_num=0)
    system_helper.set_host_4k_pages(host=target_hosts[0], proc_id=1, smallpage_num=0)
    system_helper.set_host_4k_pages(host=target_hosts[1], proc_id=0, smallpage_num=0)
    system_helper.set_host_4k_pages(host=target_hosts[1], proc_id=1, smallpage_num=1024)

    collection = ['huge', 'small']
    for x in collection:

        if x == 'huge':
            mem_page_size = 1048576
        else:
            mem_page_size = 'small'

        LOG.tc_step("Create flavor_{}".format(x))
        flavor_id = nova_helper.create_flavor(name='flavor_{}'.format(x), vcpus=vcpus, ram=memory)[1]
        ResourceCleanup.add('flavor', flavor_id)
        LOG.tc_step("Set extra specs for MEM_PAGE_SIZE: {}".format(x))
        nova_helper.set_flavor_extra_specs(flavor_id, {FlavorSpec.MEM_PAGE_SIZE: mem_page_size})

        LOG.tc_step("Boot vm mem_page_{}".format(x))
        vm_id = vm_helper.boot_vm(name='mem_page_{}'.format(x), flavor=flavor_id, source='image',
                                  source_id=image_id, avail_zone='test_scheduling')[1]
        ResourceCleanup.add('vm', vm_id)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

