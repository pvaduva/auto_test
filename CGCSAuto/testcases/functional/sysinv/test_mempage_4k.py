###
# Testcase of the 2016-04-04 sysinv_test_plan.pdf
# Launch VMs using 4k-memory-pages, cold and live migrate the vm
###

from pytest import fixture, mark, skip, param

from consts.stx import FlavorSpec
from utils import table_parser
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, host_helper, system_helper
from testfixtures.fixture_resources import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


@fixture(autouse=True)
def check_alarms():
    pass


@fixture(scope='module', autouse=True)
def check_avs_pattern():
    if not system_helper.is_avs():
        skip("4k vm unsupported by OVS-dpdk")


@fixture(scope='module', params=['local_image', 'remote'])
def ensure_sufficient_4k_pages(request):
    """
    Check if there is enough 4k pages on any compute node on any processors is a bit hassle

    Returns:

    """
    # check if any 4k pages greater than 600000 means more than 2G(~536871 4k pages) total.

    storage_backing = request.param
    hypervisors = host_helper.get_hosts_in_storage_backing(storage_backing=storage_backing)
    if len(hypervisors) < 2:
        skip("Less than two hypersvisors with {} instance backing".format(storage_backing))

    hypervisors = hypervisors[:2]
    LOG.fixture_step("Configure {} with sufficient 4k pages".format(hypervisors))

    for host in hypervisors:
        LOG.fixture_step("Modify 4k page numbers to 600000 for {}".format(host))
        num_4k_pages = host_helper.get_host_memories(host, 'app_total_4K')
        for proc, pages_4k in num_4k_pages.items():
            if pages_4k[0] > 1024*1024/4:
                break
        else:
            proc_to_set = 1 if len(num_4k_pages) > 1 else 0
            HostsToRecover.add(host, scope='module')
            host_helper.lock_host(host, swact=True)
            host_helper.modify_host_memory(host, proc=proc_to_set, gib_4k_range=(2, 4))
            host_helper.unlock_host(host, check_hypervisor_up=True, check_webservice_up=True)

    return storage_backing, hypervisors


@mark.parametrize(('ephemeral', 'swap', 'cpu_pol', 'vcpus', 'vm_type'), [
    param(0, 0, None, 1, 'volume', marks=mark.p2),
    param(1, 512, 'dedicated', 2, 'volume', marks=mark.p2),
    param(0, 0, 'dedicated', 3, 'image', marks=mark.p2),
    param(1, 512, None, 1, 'image', marks=mark.p2),
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
        - Select at least 2 hosts with specified storage backing. e.g., local_image, or remote
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

    LOG.tc_step("Create a flavor with {} vcpus, {}G ephemera disk, {}M swap disk".format(vcpus, ephemeral, swap))

    flavor_id = nova_helper.create_flavor(name='flv_4k', ephemeral=ephemeral, swap=swap, vcpus=vcpus,
                                          storage_backing=storage_backing)[1]
    ResourceCleanup.add('flavor', flavor_id)

    specs = {FlavorSpec.MEM_PAGE_SIZE: 'small'}

    if cpu_pol is not None:
        specs[FlavorSpec.CPU_POLICY] = cpu_pol

    LOG.tc_step("Add following extra specs: {}".format(specs))
    nova_helper.set_flavor(flavor=flavor_id, **specs)

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
    nova_tab = table_parser.tables(con_ssh.exec_sudo_cmd('vm-topology --show servers', expect_timeout=30)[1],
                                   combine_multiline_entry=False)[0]

    vm_row = [row for row in nova_tab['values'] if row[1] == vm_id][0]
    attribute = vm_row[11].split(', ')

    assert attribute[2] == 'pgsize:4K', "Expected pgsize: 4K; Actual: {} ".format(attribute[2])
