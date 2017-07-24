###
# Testcase of the 2016-04-04 sysinv_test_plan.pdf
# Launch VMs using 4k-memory-pages, cold and live migrate the vm
###

import time

from pytest import fixture, mark, skip

from utils.ssh import ControllerClient
from utils import table_parser
from consts.cgcs import FlavorSpec
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, host_helper, system_helper
from testfixtures.fixture_resources import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover
from testfixtures.verify_fixtures import check_alarms_module


def check_alarms():
    pass


@fixture(scope='module', params=['local_image', 'local_lvm', 'remote'])
def ensure_sufficient_4k_pages(request, check_alarms_module):
    """
    Check if there is enough 4k pages on any compute node on any processors is a bit hassle

    Returns:

    """
    # check if any 4k pages greater than 600000 means more than 2G(~536871 4k pages) total.

    storage_backing = request.param
    hypervisors = host_helper.get_hosts_by_storage_aggregate(storage_backing=storage_backing)
    if len(hypervisors) < 2:
        skip("Less than two hypersvisors with {} instance backing".format(storage_backing))

    is_cpe = system_helper.is_two_node_cpe()
    hypervisors = hypervisors[:2]
    LOG.fixture_step("Configure {} with sufficient 4k pages".format(hypervisors))

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
            host_helper.lock_host(pre_active_con, swact=True)
            system_helper.set_host_4k_pages(pre_active_con, proc_id=1, smallpage_num=revert_dict[pre_active_con])
            host_helper.unlock_host(pre_active_con, check_hypervisor_up=True, check_webservice_up=True)

    request.addfinalizer(revert_hosts)

    for host in hypervisors:
        LOG.fixture_step("Modify 4k page numbers to 600000 for {}".format(host))

        proc0_num_4k_page = int(system_helper.get_host_mem_values(host, ['vm_total_4K'], proc_id=0)[0])
        proc1_num_4k_page = int(system_helper.get_host_mem_values(host, ['vm_total_4K'], proc_id=1)[0])

        if proc0_num_4k_page < 600000 and proc1_num_4k_page < 600000:

            HostsToRecover.add(host, scope='module')
            host_helper.lock_host(host, swact=True)

            # chose to set 4k page of proc1 to 600000
            system_helper.set_host_4k_pages(host, proc_id=1, smallpage_num=600000)
            revert_dict[host] = proc1_num_4k_page
            host_helper.unlock_host(host, check_hypervisor_up=True, check_webservice_up=True)

    return storage_backing, hypervisors


@mark.parametrize(('ephemeral', 'swap', 'cpu_pol', 'vcpus', 'vm_type'), [
    mark.p1((0, 0, None, 1, 'volume')),
    mark.p2((1, 1, 'dedicated', 2, 'volume')),
    mark.p1((0, 0, 'dedicated', 3, 'image')),
    mark.p2((1, 1, None, 1, 'image')),
])
def test_migrate_4k_vm_positive(ephemeral, swap, cpu_pol, vcpus, vm_type, ensure_sufficient_4k_pages):
    """
    Test live and cold migrate 4k vm with various vm storage configurations
    Args:
        ephemeral (int):
        swap (int):
        cpu_pol (str):
        vcpus (int):
        vm_type (str): boot-from image or volume vm
        ensure_sufficient_4k_pages (tuple): module test fixture to configure 4k pages

    Setups:
        - Select at least 2 hosts with specified storage backing. e.g., local_image, local_lvm, or remote
        - Ensure 2 hosts are in nova zone (move rest to cgcsauto zone if more than 2)
        - Configure the 2 hosts with large amount of 4k pages

    Test Steps:
        - Create flavor with specified ephemeral, swap,

    """
    storage_backing, hosts = ensure_sufficient_4k_pages

    vm_id = _boot_vm_under_test(storage_backing, ephemeral, swap, cpu_pol, vcpus, vm_type)

    LOG.tc_step("Cold migrate VM and ensure it succeeded")
    vm_helper.cold_migrate_vm(vm_id)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    __check_pagesize(vm_id)

    LOG.tc_step("Attempt to live migrate VM")
    vm_helper.live_migrate_vm(vm_id)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    __check_pagesize(vm_id)


def _boot_vm_under_test(storage_backing, ephemeral, swap, cpu_pol, vcpus, vm_type):

    LOG.tc_step("Create a flavor with {} vcpus, {} ephemera disk, {} swap disk".format(vcpus, ephemeral, swap))

    flavor_id = nova_helper.create_flavor(name='flv_4k', ephemeral=ephemeral, swap=swap, vcpus=vcpus,
                                          storage_backing=storage_backing, check_storage_backing=False)[1]
    ResourceCleanup.add('flavor', flavor_id)

    specs = {FlavorSpec.MEM_PAGE_SIZE: 'small'}

    if cpu_pol is not None:
        specs[FlavorSpec.CPU_POLICY] = cpu_pol

    LOG.tc_step("Add following extra specs: {}".format(specs))
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **specs)

    boot_source = 'volume' if vm_type == 'volume' else 'image'
    LOG.tc_step("Boot a vm from {}".format(boot_source))
    vm_id = vm_helper.boot_vm('4k_vm', flavor=flavor_id, source=boot_source, cleanup='function')[1]
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
    nova_tab = table_parser.tables(con_ssh.exec_cmd('vm-topology --show servers', expect_timeout=30)[1],
                                   combine_multiline_entry=False)[0]

    vm_row = [row for row in nova_tab['values'] if row[1] == vm_id][0]
    attribute = vm_row[11].split(', ')

    assert attribute[2] == 'pgsize:4K', "Expected pgsize: 4K; Actual: {} ".format(attribute[2])
