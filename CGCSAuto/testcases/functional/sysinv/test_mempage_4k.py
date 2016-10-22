###
# Testcase 58 of the 2016-04-04 sysinv_test_plan.pdf
# 58) Launch VMs using 4k-memory-pages
###

import time

from pytest import fixture, mark, skip

from utils.ssh import ControllerClient
from utils import table_parser
from consts.cgcs import FlavorSpec
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, host_helper, system_helper
from testfixtures.resource_mgmt import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


@fixture(scope='module', autouse=True)
def ensure_sufficient_4k_pages(request):
    """
    Check if there is enough 4k pages on any compute node on any processors is a bit hassle

    Returns:

    """
    # check if any 4k pages greater than 600000 means more than 2G(~536871 4k pages) total.

    hypervisors = host_helper.get_hypervisors(state='up', status='enabled')
    is_cpe = system_helper.is_small_footprint()

    if is_cpe and len(hypervisors) < 2:
        skip("Less than two hypersvisors are up for cpe lab.")

    if len(hypervisors) > 4:
        skip("System has too many compute hosts, reconfigure will take too long")

    revert_dict = {}

    def revert_hosts():
        pre_active_con = system_helper.get_active_controller_name()
        revert_active_con = False

        for host_, page_num in revert_dict.items():
            if host_ == pre_active_con:
                revert_active_con = True
                continue

            LOG.fixture_step("Revert host mem page setting for {}".format(host_))
            host_helper.lock_host(host_)
            system_helper.set_host_4k_pages(host_, proc_id=1, smallpage_num=page_num)

            if is_cpe:
                LOG.fixture_step("Unlock host one by one for CPE lab")
                host_helper.unlock_host(host_)

        if revert_active_con:
            LOG.fixture_step("Swact active controller and revert host mem page settings")
            host_helper.swact_host(pre_active_con)
            host_helper.lock_host(pre_active_con)
            system_helper.set_host_4k_pages(pre_active_con, proc_id=1, smallpage_num=revert_dict[pre_active_con])
            host_helper.unlock_host(pre_active_con, check_hypervisor_up=True, check_webservice_up=True)

    request.addfinalizer(revert_hosts)

    for host in hypervisors:
        LOG.fixture_step("Modify 4k page numbers to 600000 for {}".format(host))

        proc0_num_4k_page = int(system_helper.get_host_mem_values(host, ['vm_total_4K'], proc_id=0)[0])
        proc1_num_4k_page = int(system_helper.get_host_mem_values(host, ['vm_total_4K'], proc_id=1)[0])

        if proc0_num_4k_page < 600000 and proc1_num_4k_page < 600000:
            if system_helper.get_active_controller_name() == host:
                host_helper.swact_host()
                host_helper.wait_for_hypervisors_up(host)

            HostsToRecover.add(host, scope='module')
            host_helper.lock_host(host)

            # chose to set 4k page of proc1 to 600000
            system_helper.set_host_4k_pages(host, proc_id=1, smallpage_num=600000)
            revert_dict[host] = proc1_num_4k_page
            host_helper.unlock_host(host, check_hypervisor_up=True, check_webservice_up=True)


@fixture(scope='module')
def hosts_per_stor_backing():
    hosts_per_backing = host_helper.get_hosts_per_storage_backing()
    LOG.fixture_step("Hosts per storage backing: {}".format(hosts_per_backing))

    if max([len(hosts) for hosts in list(hosts_per_backing.values())]) < 2:
        skip("No two hosts have the same storage backing")

    return hosts_per_backing


@mark.parametrize(
    "boot_source", [
        'image',
        'volume'
    ])
def test_boot_4k_vm(boot_source):
    """
    58) Launch VMs using 4k-memory-pages from sysinv_test_plan.pdf

    Verify the version number (or str) exist for the system when execute the "system show" cli

    Args:
        - Nothing

    Setup:
        - Setup flavor with mem_page_size to small
        - Setup enough 4k page if there isnt enough in any of the compute nodes
        - Setup vm with 4k page

    Test Steps:
        -execute "vm-topology" cli
        -verify the vm from the table generated contain 'pgsize:4K'

    Teardown:
        - delete created 4k page vm
        - delete created 4k page flavor

    """
    LOG.tc_step("Create a flavor with mem_page_size set to small")
    flavor_id = nova_helper.create_flavor()[1]
    ResourceCleanup.add('flavor', flavor_id, scope='module')
    pagesize_spec = {'hw:mem_page_size': 'small'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **pagesize_spec)

    LOG.tc_step("Boot a 4kvm from {} with above flavor".format(boot_source))
    vm_id = vm_helper.boot_vm(flavor=flavor_id, source=boot_source)[1]
    ResourceCleanup.add('vm', vm_id, del_vm_vols=False)
    __check_pagesize(vm_id)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id, fail_ok=False)


@mark.parametrize(('storage_backing', 'ephemeral', 'swap', 'cpu_pol', 'vcpus', 'vm_type'), [
    mark.p2(('local_image', 0, 0, None, 1, 'volume')),
    mark.p1(('local_image', 0, 0, None, 1, 'image')),
    mark.p1(('local_image', 0, 0, None, 3, 'image')),
    mark.p2(('local_lvm', 0, 0, None, 1, 'volume')),
    mark.p2(('local_lvm', 0, 0, None, 1, 'image')),
    mark.p2(('remote', 1, 1, None, 1, 'volume')),
    mark.p2(('remote', 0, 0, None, 2, 'image')),
])
def test_live_migrate_4k_vm_positive(storage_backing, ephemeral, swap, cpu_pol, vcpus, vm_type, hosts_per_stor_backing):
    if len(hosts_per_stor_backing[storage_backing]) < 2:
        skip("Less than two hosts have {} storage backing".format(storage_backing))

    vm_id = _boot_vm_under_test(storage_backing, ephemeral, swap, cpu_pol, vcpus, vm_type)

    LOG.tc_step("Attempt to live migrate VM")
    vm_helper.live_migrate_vm(vm_id)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    __check_pagesize(vm_id)


@mark.parametrize(('storage_backing', 'ephemeral', 'swap', 'cpu_pol', 'vcpus', 'vm_type'), [
    mark.p2(('local_image', 0, 0, None, 1, 'volume')),
    mark.p2(('local_lvm', 0, 1, None, 1, 'volume')),
    mark.p2(('remote', 1, 0, None, 2, 'volume')),
    mark.p1(('local_image', 1, 0, None, 1, 'image')),
    mark.p2(('local_lvm', 0, 0, None, 1, 'image')),
    mark.p2(('remote', 0, 1, None, 2, 'image')),
])
def test_cold_migrate_4k_vm(storage_backing, ephemeral, swap, cpu_pol, vcpus, vm_type, hosts_per_stor_backing):
    if len(hosts_per_stor_backing[storage_backing]) < 2:
        skip("Less than two hosts have {} storage backing".format(storage_backing))

    vm_id = _boot_vm_under_test(storage_backing, ephemeral, swap, cpu_pol, vcpus, vm_type)
    ResourceCleanup.add('vm', vm_id)

    LOG.tc_step("Cold migrate VM and ensure it succeeded")
    vm_helper.cold_migrate_vm(vm_id)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    __check_pagesize(vm_id)


def _boot_vm_under_test(storage_backing, ephemeral, swap, cpu_pol, vcpus, vm_type):

    LOG.tc_step("Create a flavor with {} vcpus, {} ephemera disk, {} swap disk".format(vcpus, ephemeral, swap))

    flavor_id = nova_helper.create_flavor(name='flv_4k', ephemeral=ephemeral, swap=swap, vcpus=vcpus,
                                          check_storage_backing=True)[1]
    ResourceCleanup.add('flavor', flavor_id)

    specs = {FlavorSpec.STORAGE_BACKING: storage_backing,
             FlavorSpec.MEM_PAGE_SIZE: 'small'}

    if cpu_pol is not None:
        specs[FlavorSpec.CPU_POLICY] = cpu_pol

    LOG.tc_step("Add following extra specs: {}".format(specs))
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **specs)

    boot_source = 'volume' if vm_type == 'volume' else 'image'
    LOG.tc_step("Boot a vm from {}".format(boot_source))
    vm_id = vm_helper.boot_vm('4k_vm', flavor=flavor_id, source=boot_source)[1]
    ResourceCleanup.add('vm', vm_id)

    __check_pagesize(vm_id)

    if vm_type == 'image_with_vol':
        LOG.tc_step("Attach volume to vm")
        vm_helper.attach_vol_to_vm(vm_id=vm_id)

    # make sure the VM is up and pingable from natbox
    LOG.tc_step("Ping VM {} from NatBox(external network)".format(vm_id))
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id, fail_ok=False)

    return vm_id


def __check_pagesize(vm_id):
    LOG.tc_step("Check pagesize is 4k for vm {} via vm-topology.".format(vm_id))
    con_ssh = ControllerClient.get_active_controller()
    nova_tab = table_parser.tables(con_ssh.exec_cmd('vm-topology --show servers',expect_timeout=30)[1],
                                   combine_multiline_entry=False)[0]

    vm_row = [row for row in nova_tab['values'] if row[1] == vm_id][0]
    attribute = vm_row[11].split(', ')

    assert attribute[2] == 'pgsize:4K', "Expected pgsize: 4K; Actual: {} ".format(attribute[2])
