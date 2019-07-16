import re
import time
import random

from pytest import fixture, mark, skip, param

import keywords.host_helper
from utils.tis_log import LOG
from consts.filepaths import CompConfPath
from consts.stx import FlavorSpec, ImageMetadata, NovaCLIOutput
from keywords import nova_helper, vm_helper, system_helper, cinder_helper, host_helper, glance_helper


MEMPAGE_HEADERS = ('app_total_4K', 'app_hp_avail_2M', 'app_hp_avail_1G')


def skip_4k_for_ovs(mempage_size):
    if mempage_size in (None, 'any', 'small') and not system_helper.is_avs():
        skip("4K VM is only supported by AVS")


# Deprecated. Remove flavor spec setting test, since no spec validation is done upstream.
@mark.parametrize('mem_page_size', [
    'small',
    'large',
    'any',
    '2048',
    '1048576',
])
def _test_set_mem_page_size_extra_specs(flavor_id_module, mem_page_size):
    nova_helper.set_flavor(flavor_id_module, **{FlavorSpec.MEM_PAGE_SIZE: mem_page_size})


@fixture(scope='module')
def prepare_resource(add_admin_role_module):
    hypervisor = random.choice(host_helper.get_up_hypervisors())
    vm_helper.delete_vms()
    flavor = nova_helper.create_flavor(name='flavor-1g', ram=1024, cleanup='module')[1]
    vol_id = cinder_helper.create_volume('vol-mem_page_size', cleanup='module')[1]

    return hypervisor, flavor, vol_id


def _wait_for_all_app_hp_avail(host, timeout=360):
    headers = ['app_hp_total_2M', 'app_hp_avail_2M', 'app_hp_total_1G', 'app_hp_avail_1G']
    end_time = time.time() + timeout + 20
    while time.time() < end_time:
        mems = host_helper.get_host_memories(host, headers=headers)
        for proc, mems_for_proc in mems.items():
            total_2m, avail_2m, total_1g, avail_1g = mems_for_proc
            if total_2m != avail_2m or total_1g != avail_1g:
                break
        else:
            LOG.info('All app huge pages are available on {}'.format(host))
            return

        time.sleep(20)

    assert 0, 'app_hp_total is not the same as app_hp_avail within {}s'.format(timeout)


def _get_expt_indices(mempage_size):
    if mempage_size in ('small', None):
        expt_mempage_indices = (0,)
    elif str(mempage_size) == '2048':
        expt_mempage_indices = (1,)
    elif str(mempage_size) == '1048576':
        expt_mempage_indices = (2,)
    elif mempage_size == 'large':
        expt_mempage_indices = (1, 2)
    else:
        expt_mempage_indices = (0, 1, 2)
    return expt_mempage_indices


def is_host_mem_sufficient(host, mempage_size=None, mem_gib=1):
    host_mems_per_proc = host_helper.get_host_memories(host, headers=MEMPAGE_HEADERS)
    mempage_size = 'small' if not mempage_size else mempage_size
    expt_mempage_indices = _get_expt_indices(mempage_size)

    for proc, mems_for_proc in host_mems_per_proc.items():
        pages_4k, pages_2m, pages_1g = mems_for_proc
        mems_for_proc = (int(pages_4k*4/1048576), int(pages_2m*2/1024), int(pages_1g))
        for index in expt_mempage_indices:
            avail_g_for_memsize = mems_for_proc[index]
            if avail_g_for_memsize >= mem_gib:
                LOG.info("{} has sufficient {} mempages to launch {}G vm".format(host, mempage_size, mem_gib))
                return True, host_mems_per_proc

    LOG.info("{} does not have sufficient {} mempages to launch {}G vm".format(host, mempage_size, mem_gib))
    return False, host_mems_per_proc


def check_mempage_change(vm, host, prev_host_mems, mempage_size=None, mem_gib=1, numa_node=None,
                         timeout=360):
    expt_mempage_indics = _get_expt_indices(mempage_size)
    if numa_node is None:
        numa_node = vm_helper.get_vm_numa_nodes_via_ps(vm_id=vm, host=host)[0]

    prev_host_mems = prev_host_mems[numa_node]

    end_time = time.time() + timeout + 30
    while time.time() < end_time:
        current_host_mems = host_helper.get_host_memories(host, headers=MEMPAGE_HEADERS)[numa_node]

        if 0 in expt_mempage_indics:
            if current_host_mems[1:] == prev_host_mems[1:] and \
                    abs(prev_host_mems[0] - current_host_mems[0]) <= mem_gib*512*1024/4:
                return

        for i in expt_mempage_indics:
            if i == 0:
                continue

            expt_pagediff = 1 if i == 2 else mem_gib*1024/2
            if prev_host_mems[i] - expt_pagediff == current_host_mems[i]:
                LOG.info("{} {} memory page reduced by {}GiB as expected".format(
                    host, MEMPAGE_HEADERS[i], mem_gib))
                return

            LOG.info("{} {} memory pages - Previous: {}, current: {}".format(
                host, MEMPAGE_HEADERS[i], prev_host_mems[i], current_host_mems[i]))

        time.sleep(30)

    assert 0, "{} available vm {} memory page count did not change to expected within {}s".format(
        host, mempage_size, timeout)


@mark.parametrize('mem_page_size', [
    param('2048', marks=mark.domain_sanity),
    param('large', marks=mark.p1),
    param('small', marks=mark.domain_sanity),
    param('1048576', marks=mark.p3),
])
def test_vm_mem_pool_default_config(prepare_resource, mem_page_size):
    """
    Test memory used by vm is taken from the expected memory pool

    Args:
        prepare_resource (tuple): test fixture
        mem_page_size (str): mem page size setting in flavor

    Setup:
        - Create a flavor with 1G RAM (module)
        - Create a volume with default values (module)
        - Select a hypervisor to launch vm on

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
    hypervisor, flavor_1g, volume_ = prepare_resource
    _wait_for_all_app_hp_avail(host=hypervisor)

    LOG.tc_step("Set memory page size extra spec in flavor")
    nova_helper.set_flavor(flavor_1g, **{FlavorSpec.CPU_POLICY: 'dedicated',
                                         FlavorSpec.MEM_PAGE_SIZE: mem_page_size})

    LOG.tc_step("Check system host-memory-list before launch vm")
    is_sufficient, prev_host_mems = is_host_mem_sufficient(host=hypervisor, mempage_size=mem_page_size)

    LOG.tc_step("Boot a vm with mem page size spec - {}".format(mem_page_size))
    code, vm_id, msg = vm_helper.boot_vm('mempool_'+mem_page_size, flavor_1g, source='volume', fail_ok=True,
                                         vm_host=hypervisor, source_id=volume_, cleanup='function')

    if not is_sufficient:
        LOG.tc_step("Check boot vm rejected due to insufficient memory from {} pool".format(mem_page_size))
        assert 1 == code, "{} vm launched successfully when insufficient mempage configured on {}".\
            format(mem_page_size, hypervisor)
    else:
        LOG.tc_step("Check vm launches successfully and {} available mempages change accordingly".format(hypervisor))
        assert 0 == code, "VM failed to launch with '{}' mempages".format(mem_page_size)
        check_mempage_change(vm_id, host=hypervisor, prev_host_mems=prev_host_mems, mempage_size=mem_page_size)


def get_hosts_to_configure(candidates):
    hosts_selected = [None, None]
    hosts_to_configure = [None, None]
    max_4k, expt_p1_4k, max_1g, expt_p1_1g = 1.5*1048576/4, 2.5*1048576/4, 1, 2
    for host in candidates:
        host_mems = host_helper.get_host_memories(host, headers=MEMPAGE_HEADERS)
        if 1 not in host_mems:
            LOG.info("{} has only 1 processor".format(host))
            continue

        proc0_mems, proc1_mems = host_mems[0], host_mems[1]
        p0_4k, p1_4k, p0_1g, p1_1g = proc0_mems[0], proc1_mems[0], proc0_mems[2], proc1_mems[2]

        if p0_4k <= max_4k and p0_1g <= max_1g:
            if not hosts_selected[1] and p1_4k >= expt_p1_4k and p1_1g <= max_1g:
                hosts_selected[1] = host
            elif not hosts_selected[0] and p1_4k <= max_4k and p1_1g >= expt_p1_1g:
                hosts_selected[0] = host

        if None not in hosts_selected:
            LOG.info("1G and 4k hosts already configured and selected: {}".format(hosts_selected))
            break
    else:
        for i in range(len(hosts_selected)):
            if hosts_selected[i] is None:
                hosts_selected[i] = hosts_to_configure[i] = list(set(candidates) - set(hosts_selected))[0]
        LOG.info("Hosts selected: {}; To be configured: {}".format(hosts_selected, hosts_to_configure))

    return hosts_selected, hosts_to_configure


@fixture()
def reset_host_app_mems():
    vm_helper.delete_vms()
    for host in host_helper.get_up_hypervisors():
        _wait_for_all_app_hp_avail(host=host)


class TestConfigMempage:

    MEM_CONFIGS = [None, 'any', 'large', 'small', '2048', '1048576']

    @fixture(scope='class')
    def add_1g_and_4k_pages(self, request, config_host_class, skip_for_one_proc, add_cgcsauto_zone,
                            add_admin_role_module):

        storage_backing, candidate_hosts = host_helper.get_storage_backing_with_max_hosts()

        if len(candidate_hosts) < 2:
            skip("Less than two up hosts have same storage backing")

        vm_helper.delete_vms()

        LOG.fixture_step("Check mempage configs for hypervisors and select host to use or configure")
        hosts_selected, hosts_to_configure = get_hosts_to_configure(candidate_hosts)

        if set(hosts_to_configure) != {None}:
            def _modify(host):
                is_1g = True if hosts_selected.index(host) == 0 else False
                proc1_kwargs = {'gib_1g': 2, 'gib_4k_range': (None, 2)} if is_1g else \
                    {'gib_1g': 0, 'gib_4k_range': (2, None)}
                kwargs = {'gib_1g': 0, 'gib_4k_range': (None, 2)}, proc1_kwargs

                actual_mems = host_helper._get_actual_mems(host=host)
                LOG.fixture_step("Modify {} proc0 to have 0 of 1G pages and <2GiB of 4K pages".format(host))
                host_helper.modify_host_memory(host, proc=0, actual_mems=actual_mems, **kwargs[0])
                LOG.fixture_step("Modify {} proc1 to have >=2GiB of {} pages".format(host, '1G' if is_1g else '4k'))
                host_helper.modify_host_memory(host, proc=1, actual_mems=actual_mems, **kwargs[1])

            for host_to_config in hosts_to_configure:
                if host_to_config:
                    config_host_class(host=host_to_config, modify_func=_modify)
                    LOG.fixture_step("Check mem pages for {} are modified and updated successfully".
                                     format(host_to_config))
                    host_helper.wait_for_memory_update(host=host_to_config)

            LOG.fixture_step("Check host memories for {} after mem config completed".format(hosts_selected))
            _, hosts_unconfigured = get_hosts_to_configure(hosts_selected)
            assert not hosts_unconfigured[0], \
                "Failed to configure {}. Expt: proc0:1g<2,4k<2gib;proc1:1g>=2,4k<2gib".format(hosts_unconfigured[0])
            assert not hosts_unconfigured[1], \
                "Failed to configure {}. Expt: proc0:1g<2,4k<2gib;proc1:1g<2,4k>=2gib".format(hosts_unconfigured[1])

        LOG.fixture_step('(class) Add hosts to cgcsauto aggregate: {}'.format(hosts_selected))
        nova_helper.add_hosts_to_aggregate(aggregate='cgcsauto', hosts=hosts_selected)

        def remove_host_from_zone():
            LOG.fixture_step('(class) Remove hosts from cgcsauto aggregate: {}'.format(hosts_selected))
            nova_helper.remove_hosts_from_aggregate(aggregate='cgcsauto', check_first=False)

        request.addfinalizer(remove_host_from_zone)

        return hosts_selected, storage_backing

    @fixture(scope='class')
    def flavor_2g(self, add_1g_and_4k_pages):
        hosts, storage_backing = add_1g_and_4k_pages
        LOG.fixture_step("Create a 2G memory flavor to be used by mempage testcases")
        flavor = nova_helper.create_flavor(name='flavor-2g', ram=2048, storage_backing=storage_backing,
                                           cleanup='class')[1]
        return flavor, hosts, storage_backing

    @fixture(scope='class')
    def image_mempage(self):
        LOG.fixture_step("(class) Create a glance image for mempage testcases")
        image_id = glance_helper.create_image(name='mempage', cleanup='class')[1]
        return image_id

    @fixture()
    def check_alarms(self, add_1g_and_4k_pages):
        hosts, storage_backing = add_1g_and_4k_pages
        host_helper.get_hypervisor_info(hosts=hosts)
        for host in hosts:
            host_helper.get_host_memories(host, wait_for_update=False)

    @fixture(params=MEM_CONFIGS)
    def flavor_mem_page_size(self, request, flavor_2g):
        flavor_id = flavor_2g[0]
        mem_page_size = request.param
        skip_4k_for_ovs(mem_page_size)

        if mem_page_size is None:
            nova_helper.unset_flavor(flavor_id, FlavorSpec.MEM_PAGE_SIZE)
        else:
            nova_helper.set_flavor(flavor_id, **{FlavorSpec.MEM_PAGE_SIZE: mem_page_size})

        return mem_page_size

    @mark.parametrize('image_mem_page_size', MEM_CONFIGS)
    def test_boot_vm_mem_page_size(self, flavor_2g, flavor_mem_page_size, image_mempage,
                                   image_mem_page_size, reset_host_app_mems):
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
            glance_helper.set_image(image=image_mempage, properties={ImageMetadata.MEM_PAGE_SIZE: image_mem_page_size})
            if flavor_mem_page_size is None:
                expt_code = 4
            elif flavor_mem_page_size.lower() in ['any', 'large']:
                expt_code = 0
            else:
                expt_code = 0 if flavor_mem_page_size.lower() == image_mem_page_size.lower() else 4

        LOG.tc_step("Attempt to boot a vm with flavor_mem_page_size: {}, and image_mem_page_size: {}. And check return "
                    "code is {}.".format(flavor_mem_page_size, image_mem_page_size, expt_code))

        actual_code, vm_id, msg = vm_helper.boot_vm(name='mem_page_size', flavor=flavor_id, source='image',
                                                    source_id=image_mempage, fail_ok=True,
                                                    avail_zone='cgcsauto', cleanup='function')

        assert expt_code == actual_code, "Expect boot vm to return {}; Actual result: {} with msg: {}".format(
                expt_code, actual_code, msg)

        if expt_code != 0:
            assert re.search(NovaCLIOutput.VM_BOOT_REJECT_MEM_PAGE_SIZE_FORBIDDEN, msg)
        else:
            assert vm_helper.get_vm_host(vm_id) in hosts, "VM is not booted on hosts in cgcsauto zone"
            LOG.tc_step("Ensure VM is pingable from NatBox")
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    @mark.parametrize('mem_page_size', [
        param('1048576', marks=mark.priorities('domain_sanity', 'nightly')),
        param('large'),
        param('small', marks=mark.nightly),
    ])
    def test_schedule_vm_mempage_config(self, flavor_2g, mem_page_size, reset_host_app_mems):
        """
        Test memory used by vm is taken from the expected memory pool and the vm was scheduled on the correct
        host/processor

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
        nova_helper.set_flavor(flavor_id, **{FlavorSpec.CPU_POLICY: 'dedicated',
                                             FlavorSpec.MEM_PAGE_SIZE: mem_page_size})

        host_helper.wait_for_hypervisors_up(hosts_configured)
        prev_computes_mems = {}
        for host in hosts_configured:
            prev_computes_mems[host] = host_helper.get_host_memories(host=host, headers=MEMPAGE_HEADERS)

        LOG.tc_step("Boot a vm with mem page size spec - {}".format(mem_page_size))

        host_1g, host_4k = hosts_configured
        code, vm_id, msg = vm_helper.boot_vm('mempool_configured', flavor_id, fail_ok=True, avail_zone='cgcsauto',
                                             cleanup='function')
        assert 0 == code, "VM is not successfully booted."

        instance_name, vm_host = vm_helper.get_vm_values(vm_id, fields=[":instance_name", ":host"], strict=False)
        vm_node = vm_helper.get_vm_numa_nodes_via_ps(vm_id=vm_id, instance_name=instance_name, host=vm_host)
        if mem_page_size == '1048576':
            assert host_1g == vm_host, "VM is not created on the configured host {}".format(hosts_configured[0])
            assert vm_node == [1], "VM (huge) did not boot on the correct processor"
        elif mem_page_size == 'small':
            assert host_4k == vm_host, "VM is not created on the configured host {}".format(hosts_configured[1])
            assert vm_node == [1], "VM (small) did not boot on the correct processor"
        else:
            assert vm_host in hosts_configured

        LOG.tc_step("Calculate memory change on vm host - {}".format(vm_host))
        check_mempage_change(vm_id, vm_host, prev_host_mems=prev_computes_mems[vm_host],
                             mempage_size=mem_page_size, mem_gib=2, numa_node=vm_node[0])

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

    if not hosts:
        skip('No hosts available')

    LOG.info("---Wait for system host-memory-list updated for a random host")
    host_helper.wait_for_memory_update(hosts[0])

    for host in hosts:
        LOG.info("---Check {} memory info in system host-memory-list and on host".format(host))
        headers = ['vs_hp_size(MiB)', 'vs_hp_total', 'app_total_4K', 'app_hp_total_2M', 'app_hp_total_1G',
                   'app_hp_avail_2M', 'app_hp_avail_1G']
        cli_vars = check_meminfo_via_sysinv_nova_cli(host=host, headers=headers)
        check_memconfs_on_host(host=host, cli_vars=cli_vars)


def check_meminfo_via_sysinv_nova_cli(host, headers):
    end_time = time.time() + 306
    err = None
    while time.time() < end_time:
        sysinv_mems = host_helper.get_host_memories(host, headers, rtn_dict=False)
        proc_vars = []
        for proc in range(len(sysinv_mems)):
            proc_mems = sysinv_mems[proc]
            vs_size, vs_page, vm_4k, vm_2m, vm_1g, vm_avail_2m, vm_avail_1g = proc_mems
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
