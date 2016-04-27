import re

from pytest import fixture, mark

from utils import table_parser
from utils.tis_log import LOG
from consts.cgcs import FlavorSpec, ImageMetadata
from keywords import nova_helper, vm_helper, glance_helper, host_helper, system_helper, cinder_helper
from testfixtures.resource_mgmt import ResourceCleanup


@fixture(scope='module')
def flavor_2g():
    flavor = nova_helper.create_flavor(name='flavor-2g', ram=2048)[1]
    ResourceCleanup.add('flavor', resource_id=flavor, scope='module')

    return flavor


def _modify(host):
    system_helper.set_host_1g_pages(host=host, proc_id=0, hugepage_num=4)


def _revert(host):
    system_helper.set_host_1g_pages(host, proc_id=0, hugepage_num=0)


@fixture(scope='module', autouse=True)
def add_huge_page_mem(config_host):
    host = host_helper.get_nova_host_with_min_or_max_vms(rtn_max=False)
    config_host(host=host, modify_func=_modify, revert_func=_revert)


@fixture(scope='module')
def image_cgcsguest(request):
    image_id = glance_helper.get_image_id_from_name(name='cgcs-guest')

    def delete_metadata():
        nova_helper.delete_image_metadata(image_id, ImageMetadata.MEM_PAGE_SIZE)
    request.addfinalizer(delete_metadata)

    return image_id


@mark.p1
@mark.parametrize(('flavor_mem_page_size', 'image_mem_page_size'), [
    ('1048576', None),
    ('1048576', 'any'),
    ('1048576', 'large'),
    ('1048576', 'small'),
    ('1048576', '2048'),
    ('1048576', '1048576'),
    (None, '1048576'),
    ('any', '1048576'),
    ('large', '1048576'),
    ('small', '1048576'),
    ('2048', '1048576'),
])
def test_boot_vm_hugepage(flavor_2g, flavor_mem_page_size, image_cgcsguest, image_mem_page_size):

    if flavor_mem_page_size is None:
        nova_helper.unset_flavor_extra_specs(flavor_2g, FlavorSpec.MEM_PAGE_SIZE)
    else:
        nova_helper.set_flavor_extra_specs(flavor_2g, **{FlavorSpec.MEM_PAGE_SIZE: flavor_mem_page_size})

    if image_mem_page_size is None:
        nova_helper.delete_image_metadata(image_cgcsguest, ImageMetadata.MEM_PAGE_SIZE)
        expt_code = 0

    else:
        nova_helper.set_image_metadata(image_cgcsguest, **{ImageMetadata.MEM_PAGE_SIZE: image_mem_page_size})
        if flavor_mem_page_size is None:
            expt_code = 4

        elif flavor_mem_page_size.lower() in ['any', 'large']:
            expt_code = 0

        else:
            expt_code = 0 if flavor_mem_page_size.lower() == image_mem_page_size.lower() else 4

    LOG.tc_step("Attempt to boot a vm with flavor_mem_page_size: {}, and image_mem_page_size: {}. And check return "
                "code is {}.".format(flavor_mem_page_size, image_mem_page_size, expt_code))

    actual_code, vm_id, msg, vol_id = vm_helper.boot_vm(name='huge_page', flavor=flavor_2g, source='image',
                                                        source_id=image_cgcsguest, fail_ok=True)

    if vm_id:
        ResourceCleanup.add('vm', vm_id, scope='function', del_vm_vols=False)

    assert expt_code == actual_code, "Expect boot vm to return {}; Actual result: {} with msg: {}".format(
            expt_code, actual_code, msg)

    if expt_code != 0:
        assert "Page size" in msg


@fixture(scope='module')
def volume_():
    vol_id = cinder_helper.create_volume('vol-hugepage')[1]
    ResourceCleanup.add('volume', vol_id, scope='module')
    return vol_id

@mark.parametrize('mem_page_size', [
    '1048576',
    'large',
])
def test_vm_mem_pool_1g(flavor_2g, mem_page_size, volume_):
    LOG.tc_step("Set memory page size extra spec in flavor")
    nova_helper.set_flavor_extra_specs(flavor_2g, **{FlavorSpec.CPU_POLICY: 'dedicated', 
                                                     FlavorSpec.MEM_PAGE_SIZE: mem_page_size})
    
    pre_computes_tab = system_helper.get_vm_topology_tables('computes')[0]

    LOG.tc_step("Boot a vm with mem page size spec - {}".format(mem_page_size))
    vm_id = vm_helper.boot_vm('mempool_1g', flavor_2g, source='volume', source_id=volume_)[1]
    ResourceCleanup.add('vm', vm_id, del_vm_vols=False)

    vm_host = nova_helper.get_vm_host(vm_id)
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