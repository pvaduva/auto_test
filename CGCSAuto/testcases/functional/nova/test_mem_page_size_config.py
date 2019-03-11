##########################################################################
# Memory page size tests with host configured to support 1g and 4k pages #
##########################################################################

import re
import time

from pytest import fixture, mark, skip

from utils import table_parser, cli
from utils.tis_log import LOG
from consts.filepaths import CompConfPath
from consts.cgcs import FlavorSpec, ImageMetadata, NovaCLIOutput
from keywords import nova_helper, vm_helper, glance_helper, host_helper, system_helper
from testfixtures.fixture_resources import ResourceCleanup


@fixture()
def check_alarms():
    pass


@fixture(scope='module')
def flavor_2g(add_1g_and_4k_pages):
    hosts, storage_backing = add_1g_and_4k_pages
    flavor = nova_helper.create_flavor(name='flavor-2g', ram=2048, storage_backing=storage_backing)[1]
    ResourceCleanup.add('flavor', resource_id=flavor, scope='module')

    return flavor, hosts, storage_backing


def check_host_mem_configs(hosts):
    host0, host1 = hosts
    config_needed = {host0: {}, host1: {}}
    LOG.info("Ensure only {} proc1 has 2+ 1G pages, and only {} proc1 has 2GiB+ 4K pages".format(host0, host1))
    headers = ['vm_total_4K', 'vm_hp_total_2M', 'vm_hp_total_1G', 'mem_avail(MiB)']
    mem_host0 = system_helper.get_host_mem_values(host0, headers, (0, 1))
    mem_host1 = system_helper.get_host_mem_values(host1, headers, (0, 1))
    mem_host_0_proc_0 = [int(val) for val in mem_host0[0]]
    mem_host_0_proc_1 = [int(val) for val in mem_host0[1]]
    mem_host_1_proc_0 = [int(val) for val in mem_host1[0]]
    mem_host_1_proc_1 = [int(val) for val in mem_host1[1]]

    page_4k_2gib = 2 * 1024 * 1024 / 4
    page_1g_2gib = 2
    host0_proc0_mod = host0_proc1_mod = host1_proc0_mod = host1_proc1_mod = True
    if mem_host_0_proc_0[0] < page_4k_2gib and mem_host_0_proc_0[2] < page_1g_2gib:
        host0_proc0_mod = False
    if mem_host_0_proc_1[0] < page_4k_2gib and mem_host_0_proc_1[2] >= page_1g_2gib:
        host0_proc1_mod = False
    if mem_host_1_proc_0[0] < page_4k_2gib and mem_host_1_proc_0[2] < page_1g_2gib:
        host1_proc0_mod = False
    if mem_host_1_proc_1[0] >= page_4k_2gib and mem_host_1_proc_1[2] < page_1g_2gib:
        host1_proc1_mod = False

    if host0_proc0_mod:
        config_needed[host0][0] = mem_host_0_proc_0
    if host0_proc1_mod:
        config_needed[host0][1] = mem_host_0_proc_1
    if host1_proc0_mod:
        config_needed[host1][0] = mem_host_1_proc_0
    if host1_proc1_mod:
        config_needed[host1][1] = mem_host_1_proc_1

    return config_needed


@fixture(scope='module')
def add_1g_and_4k_pages(add_hosts_to_zone, config_host_module):
    storage_backing, hosts = add_hosts_to_zone

    LOG.fixture_step("Configure system if needed so that only {} proc1 has 2+ 1G pages, "
                     "and only {} proc1 has 2GiB+ 4K pages".format(hosts[0], hosts[1]))
    config_needed = check_host_mem_configs(hosts=hosts)

    def _modify(host):
        host_config_needed = config_needed[host]
        actual_mems = host_helper._get_actual_mems(host=host)
        if host == hosts[0]:
            if host_config_needed.get(0):
                LOG.fixture_step("Modify host0 proc0 to have 0 of 1G pages and <2GiB of 4K pages")
                host_helper.modify_host_memory(host, proc=0, gib_1g=0, gib_4k_range=(None, 2), actual_mems=actual_mems)

            if host_config_needed.get(1):
                LOG.fixture_step("Modify host0 proc1 to have 2GiB of 1G pages and <2GiB of 4K pages")
                host_helper.modify_host_memory(host, proc=1, gib_1g=2, gib_4k_range=(None, 2), actual_mems=actual_mems)

        elif host == hosts[1]:
            if host_config_needed.get(0):
                LOG.fixture_step("Modify host1 proc0 to have 0 of 1G pages and <2GiB of 4K pages")
                host_helper.modify_host_memory(host, proc=0, gib_1g=0, gib_4k_range=(None, 2), actual_mems=actual_mems)

            if host_config_needed.get(1):
                LOG.fixture_step("Modify host1 proc1 to have 0 of 1G pages and >=2GiB of 4K pages")
                host_helper.modify_host_memory(host, proc=1, gib_1g=0, gib_4k_range=(2, None), actual_mems=actual_mems)

    configured = False
    host0_config = config_needed[hosts[0]]
    host0_proc0_mod = host0_config.get(0)
    host0_proc1_mod = host0_config.get(1)
    if host0_proc0_mod or host0_proc1_mod:
        configured = True
        config_host_module(host=hosts[0], modify_func=_modify)
        LOG.fixture_step("Check mem pages for {} are modified and updated successfully".format(hosts[0]))
        if host0_proc0_mod:
            host_helper.wait_for_mempage_update(host=hosts[0], proc_id=0, expt_1g=0)
        if host0_proc1_mod:
            host_helper.wait_for_mempage_update(host=hosts[0], proc_id=1, expt_1g=2)

    host1_config = config_needed[hosts[1]]
    host1_proc0_mod = host1_config.get(0)
    host1_proc1_mod = host1_config.get(1)
    if host1_proc1_mod or host1_proc0_mod:
        configured = True
        config_host_module(host=hosts[1], modify_func=_modify)
        LOG.fixture_step("Check mem pages for {} are modified successfully".format(hosts[1]))
        if host1_proc0_mod:
            host_helper.wait_for_mempage_update(host=hosts[1], proc_id=0, expt_1g=0)
        if host1_proc1_mod:
            host_helper.wait_for_mempage_update(host=hosts[1], proc_id=1, expt_1g=0)

    if configured:
        LOG.fixture_step("Check host memories for {} after mem config completed".format(hosts))
        post_modify_config_needed = check_host_mem_configs(hosts=hosts)
        assert not post_modify_config_needed[hosts[0]], \
            "Failed to configure {}. Expt: proc0:1g<2,4k<2ib;proc1:1g>=2,4k<2gib".format(hosts[0])
        assert not post_modify_config_needed[hosts[1]], \
            "Failed to configure {}. Expt: proc0:1g<2,4k<2ib;proc1:1g<2,4k>=2gib".format(hosts[1])

    return hosts, storage_backing


@fixture(scope='function')
def print_hosts_memories(add_1g_and_4k_pages):
    hosts, storage_backing = add_1g_and_4k_pages
    host_helper.get_hypervisor_info(hosts=hosts)
    for host in hosts:
        cli.system('host-memory-list', host)


@fixture(scope='module')
def add_hosts_to_zone(request, skip_for_one_proc, add_cgcsauto_zone, add_admin_role_module):
    storage_backing, target_hosts, up_hypervisors = nova_helper.get_storage_backing_with_max_hosts()

    if len(target_hosts) < 2:
        skip("Less than two up hosts have same storage backing")

    hosts_to_add = [target_hosts[0], target_hosts[1]]
    LOG.fixture_step('(module) Add hosts to cgcsauto aggregate: {}'.format(hosts_to_add))
    nova_helper.add_hosts_to_aggregate(aggregate='cgcsauto', hosts=hosts_to_add)

    def remove_host_from_zone():
        LOG.fixture_step('(module) Remove hosts from cgcsauto aggregate: {}'.format(hosts_to_add))
        nova_helper.remove_hosts_from_aggregate(aggregate='cgcsauto', check_first=False)
    request.addfinalizer(remove_host_from_zone)

    return storage_backing, hosts_to_add


testdata = [None, 'any', 'large', 'small', '2048', '1048576']


@fixture(params=testdata)
def flavor_mem_page_size(request, flavor_2g):
    flavor_id = flavor_2g[0]
    mem_page_size = request.param
    skip_4k_for_ovs(mem_page_size)

    if mem_page_size is None:
        nova_helper.unset_flavor_extra_specs(flavor_id, FlavorSpec.MEM_PAGE_SIZE)
    else:
        nova_helper.set_flavor_extra_specs(flavor_id, **{FlavorSpec.MEM_PAGE_SIZE: mem_page_size})

    return mem_page_size


def skip_4k_for_ovs(mempage_size):
    if mempage_size == 'small' and not system_helper.is_avs():
        skip("4K VM is only supported by AVS")


@fixture(scope='module')
def image_mempage():
    image_id = glance_helper.create_image(name='mempage', cleanup='module')[1]
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
    skip_4k_for_ovs(image_mem_page_size)

    flavor_id, hosts, storage_backing = flavor_2g

    if image_mem_page_size is None:
        glance_helper.unset_image(image_mempage, properties=ImageMetadata.MEM_PAGE_SIZE)
        expt_code = 0

    else:
        # nova_helper.set_image_metadata(image_mempage, **{ImageMetadata.MEM_PAGE_SIZE: image_mem_page_size})
        glance_helper.set_image(image=image_mempage, properties={ImageMetadata.MEM_PAGE_SIZE: image_mem_page_size})
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

    Setup:
        - Create host aggregate
        - Add two hypervisors to the host aggregate
        - Host-0 configuration:
            - Processor-0:
                - Insufficient 1g pages to boot vm that requires 2g
                - Insufficient 4k pages to boot vm that requires 2g
            - Processor-1:
                - Sufficient 1g pages to boot vm that requires 2g
                - Insufficient 4k pages to boot vm that requires 2g
        - Host-1 configuration:
            - Processor-0:
                - Insufficient 1g pages to boot vm that requires 2g
                - Insufficient 4k pages to boot vm that requires 2g
            - Processor-1:
                - Insufficient 1g pages to boot vm that requires 2g
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
    skip_4k_for_ovs(mem_page_size)

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

    instance_topology = vm_helper.get_instance_topology(vm_id)[0]
    vm_page_size = instance_topology['pgsize']

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
    assert sum(post_avail_mems) - 500 < sum(pre_avail_mems) - 2048 < sum(post_avail_mems) + 500, \
        "Available memory in {} page pool is not decreased by 2048MiB".format(mem_page_size)

    LOG.tc_step("Ensure vm is pingable from NatBox")
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)


def test_compute_mempage_vars(hosts=None):
    """
    Steps:
        - Collect host mempage stats from system host-memory-list
        - Ensure the stats collected are reflected in following places:
            - nova hypervisor-show
            - compute_extend.conf and compute_reserved.conf on compute host
            - /sys/devices/system/node/node*/hugepages/ on compute host

    Args:
        hosts (str|None|list|tuple): this param is reserved if any test wants to call this as verification step

    """
    if isinstance(hosts, str):
        hosts = [hosts]
    elif not hosts:
        hosts = host_helper.get_up_hypervisors()

    LOG.info("---Collect host memory info via system host-memory-list cmd")
    for host in hosts:

        LOG.info("---Check {} memory info in system host-memory-list is the same as vm-topology tool".format(host))
        headers = ['vs_hp_size(MiB)', 'vs_hp_total', 'vm_total_4K', 'vm_hp_total_2M', 'vm_hp_total_1G',
                   'vm_hp_avail_2M', 'vm_hp_avail_1G']
        host_helper.wait_for_mempage_update(host)
        cli_vars = check_meminfo_via_sysinv_nova_cli(host=host, headers=headers)
        check_memconfs_on_host(host=host, cli_vars=cli_vars)


def check_meminfo_via_sysinv_nova_cli(host, headers):
    end_time = time.time() + 306
    err = None
    while time.time() < end_time:
        compute_table = system_helper.get_vm_topology_tables('computes')[0]
        host_values = {}
        for field in ('node', 'A:mem_2M', 'A:mem_1G'):
            values = table_parser.get_values(table_=compute_table, target_header=field, host=host)[0]
            if isinstance(values, str):
                # in case of only 1 processor.
                values = [values]
            host_values[field] = values

        procs = host_values.pop('node')
        sysinv_mems = system_helper.get_host_mem_values(host, headers, rtn_dict=False)
        proc_vars = []
        for proc in range(len(sysinv_mems)):
            vm_topology_hp_mibs = []
            vm_topology_index = procs.index(str(proc))
            for header in ('A:mem_2M', 'A:mem_1G'):
                value = int(host_values[header][vm_topology_index])
                vm_topology_hp_mibs.append(value)

            LOG.info("{} proc{} memories in MiB via vm-topogy: {}".format(host, proc, vm_topology_hp_mibs))
            proc_mems = sysinv_mems[proc]
            vs_size, vs_page, vm_4k, vm_2m, vm_1g, vm_avail_2m, vm_avail_1g = proc_mems
            syinv_hp_avails = [vm_avail_2m*2, vm_avail_1g*1024]
            if vm_topology_hp_mibs != syinv_hp_avails:
                err = "{} proc{} mem info in system host-memory-list is different than vm-topology".\
                    format(host, proc)
                LOG.info(err)
                time.sleep(5)
                break

            proc_vars.append((vs_size, vs_page, vm_4k, vm_2m, vm_1g, vm_avail_2m, vm_avail_1g))

        else:
            LOG.info("{} mempage info in system host-memory-list is in-sync with nova hypervisor-show".format(host))
            return proc_vars

    assert 0, err


def check_memconfs_on_host(host, cli_vars):
    # compose expected vars for compute_extend.conf
    expt_compute_extend = {
        'vswitch_2M_pages': [],
        'vswitch_1G_pages': [],
        'vm_4K_pages': [],
        'vm_2M_pages': [],
        'vm_1G_pages': []
    }

    expt_sys_hp = {
        '2048kB': {'nr': [], 'free': []},
        '1048576kB': {'nr': [], 'free': []}
    }
    for proc_var in cli_vars:
        vs_size, vs_page, vm_4k, vm_2m, vm_1g, vm_avail_2m, vm_avail_1g = proc_var
        if vs_size == 1024:
            vs_1g = vs_page
            vs_2m = 0
        else:
            vs_1g = 0
            vs_2m = vs_page

        expt_compute_extend['vswitch_2M_pages'].append(str(vs_2m))
        expt_compute_extend['vswitch_1G_pages'].append(str(vs_1g))
        expt_compute_extend['vm_4K_pages'].append(str(vm_4k))
        expt_compute_extend['vm_2M_pages'].append(str(vm_2m))
        expt_compute_extend['vm_1G_pages'].append(str(vm_1g))

        expt_sys_hp['2048kB']['nr'].append(vm_2m + vs_2m)
        expt_sys_hp['1048576kB']['nr'].append(vm_1g + vs_1g)
        expt_sys_hp['2048kB']['free'].append(vm_avail_2m)
        expt_sys_hp['1048576kB']['free'].append(vm_avail_1g)

    with host_helper.ssh_to_host(hostname=host) as host_ssh:
        comp_extend = CompConfPath.COMP_EXTEND
        LOG.info("---Check mempage values in {} on {}".format(comp_extend, host))
        output = host_ssh.exec_cmd('cat {}'.format(comp_extend), fail_ok=False)[1]
        for key, expt_val in expt_compute_extend.items():
            expt_val = ','.join(expt_val)
            actual_val = re.findall('{}=(.*)'.format(key), output)[0].strip()
            assert expt_val == actual_val, "{} in host-memory-list {}: {}; in {}: {}". \
                format(key, host, expt_val, comp_extend, actual_val)

        LOG.info("---Check {} hugepages via /sys/devices/system/node/node*/hugepages/".format(host))
        for pagesize in expt_sys_hp:
            for mem_status in expt_sys_hp[pagesize]:
                file_path = '/sys/devices/system/node/node*/hugepages/hugepages-{}/{}_hugepages'. \
                    format(pagesize, mem_status)
                output = host_ssh.exec_cmd('cat {}'.format(file_path), fail_ok=False)[1]
                actual_res = [int(val) for val in output.splitlines()]
                assert expt_sys_hp[pagesize][mem_status] == actual_res, \
                    "{}: system host-memory-list and {} mismatch".format(host, file_path)
