###
# Testcase 58 of the 2016-04-04 sysinv_test_plan.pdf
# 58) Launch VMs using 4k-memory-pages
###


from pytest import fixture, mark, skip
import ast, time
import random

from utils import cli
from utils.ssh import ControllerClient
from utils import table_parser
from consts.auth import Tenant
from consts.cgcs import FlavorSpec
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, host_helper, system_helper
from testfixtures.resource_mgmt import ResourceCleanup


def get_host_aggregate(host):
    #retrieve the host is either local_lvm or local_image
    args = host + ' nova-local'
    table_ = table_parser.table(cli.system('host-lvg-show', args, auth_info=Tenant.ADMIN, fail_ok=False))

    instance_backing = table_parser.get_value_two_col_table(table_,'parameters')
    inst_back = ast.literal_eval(instance_backing)['instance_backing']

    return inst_back

def is_enough_4k_page_memory():
    """
    Check if there is enough 4k pages on any compute node on any processors is a bit hassle

    Returns:

    """
    # check if any 4k pages greater than 600000 means more than 2G(~536871 4k pages) total.
    check = True
    for host in host_helper.get_hypervisors():

        proc0_num_4k_page = int(system_helper.get_host_mem_values(host, ['vm_total_4K'], proc_id=0)[0])
        proc1_num_4k_page = int(system_helper.get_host_mem_values(host, ['vm_total_4K'], proc_id=1)[0])
        print(proc0_num_4k_page,proc1_num_4k_page)
        if proc0_num_4k_page < 600000 and proc1_num_4k_page < 600000 :
            if system_helper.get_active_controller_name() == host:
                host_helper.swact_host()
                time.sleep(30)
                host_helper.lock_host(host)
                time.sleep(30)
            host_helper.lock_host(host)
            # chose to set 4k page of proc1 to 600000
            system_helper.set_host_4k_pages(host, proc_id=1, smallpage_num=600000)
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
def test_4k_page_vm(boot_source):
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

    flavor_id = nova_helper.create_flavor()[1]
    ResourceCleanup.add('flavor', flavor_id, scope='module')
    pagesize_spec = {'hw:mem_page_size': 'small'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **pagesize_spec)

    # verify there is enough 4k pages on compute nodes to create 4k page flavor
    is_enough_4k_page_memory()

    vm_id = vm_helper.boot_vm(flavor=flavor_id, source=boot_source)[1]
    ResourceCleanup.add('vm', vm_id, del_vm_vols=False)

    # check vm-topology

    LOG.tc_step("Verify cpu info for vm {} via vm-topology.".format(vm_id))
    con_ssh = ControllerClient.get_active_controller()
    # retrieve the correct table from the vm-topology
    nova_tab = table_parser.tables(con_ssh.exec_cmd('vm-topology --show servers',expect_timeout=30)[1],
                                   combine_multiline_entry=False)[0]
    print(nova_tab)
    vm_row = [row for row in nova_tab['values'] if row[1] == vm_id][0]
    attribute = vm_row[11].split(', ')

    assert attribute[2] == 'pgsize:4K', "expected result to be pgsize:4K. " \
                                        "However, output is {} ".format(attribute[2])


@mark.skipif(True, reason="Evacuation JIRA CGTS-4972")
@mark.parametrize(('storage_backing', 'ephemeral', 'swap', 'cpu_pol', 'vcpus', 'vm_type', 'block_mig'), [
    mark.p2(('local_image', 0, 0, None, 1, 'volume', True)),
    mark.p1(('local_image', 0, 0, None, 1, 'image',True)),
    mark.p1(('local_image', 0, 0, None, 3, 'image', True)),
    mark.p2(('local_lvm', 0, 0, None, 1, 'volume', True)),
    mark.p2(('local_lvm', 0, 0, None, 1, 'image',True)),
    mark.p2(('remote', 1, 1, None, 1, 'volume', True)),
    mark.p2(('remote', 0, 0, None, 2, 'image',True)),
])
def test_live_migrate_vm_positive(storage_backing, ephemeral, swap, cpu_pol, vcpus, vm_type, block_mig,
                                  hosts_per_stor_backing):
    if len(hosts_per_stor_backing[storage_backing]) < 2:
        skip("Less than two hosts have {} storage backing".format(storage_backing))

    vm_id = _boot_vm_under_test(storage_backing, ephemeral, swap, cpu_pol, vcpus, vm_type)
    ResourceCleanup.add('vm', vm_id, scope='function')

    # make sure the VM is up and pingable from natbox
    LOG.tc_step("Ping VM {} from NatBox(external network)".format(vm_id))
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id, fail_ok=False)

    # check vm-topology make sure the created vm's page size is 4k
    LOG.tc_step("Verify cpu info for vm {} via vm-topology.".format(vm_id))
    con_ssh = ControllerClient.get_active_controller()
    # retrieve the correct table from the vm-topology
    nova_tab = table_parser.tables(con_ssh.exec_cmd('vm-topology --show servers', expect_timeout=30)[1],
                                   combine_multiline_entry=False)[0]
    vm_row = [row for row in nova_tab['values'] if row[1] == vm_id][0]
    attribute = vm_row[11].split(', ')
    assert attribute[2] == 'pgsize:4K', "expected result to be pgsize:4K. " \
                                        "However, output is {} ".format(attribute[2])

    # start live migration
    prev_vm_host = nova_helper.get_vm_host(vm_id)
    LOG.tc_step("Live migrate VM and ensure it succeeded")
    # block_mig = True if boot_source == 'image' else False
    code, output = vm_helper.live_migrate_vm(vm_id, block_migrate=block_mig)
    assert 0 == code, "Live migrate is not successful. Details: {}".format(output)

    post_vm_host = nova_helper.get_vm_host(vm_id)
    assert prev_vm_host != post_vm_host

@mark.skipif(True, reason="Evacuation JIRA CGTS-4972")
@mark.parametrize(('storage_backing', 'ephemeral', 'swap', 'cpu_pol', 'vcpus', 'vm_type'), [
    mark.p2(('local_image', 0, 0, None, 1, 'volume')),
    mark.p2(('local_lvm', 0, 0, None, 1, 'volume')),
    mark.p2(('remote', 0, 0, None, 2, 'volume')),
    mark.p1(('local_image', 0, 0, None, 1, 'image')),
    mark.p2(('local_lvm', 0, 0, None, 1, 'image')),
    mark.p2(('remote', 0, 0, None, 2, 'image')),
])
def test_cold_migrate_4k_vm(storage_backing, ephemeral, swap, cpu_pol, vcpus, vm_type, hosts_per_stor_backing):
    if len(hosts_per_stor_backing[storage_backing]) < 2:
        skip("Less than two hosts have {} storage backing".format(storage_backing))

    vm_id = _boot_vm_under_test(storage_backing, ephemeral, swap, cpu_pol, vcpus, vm_type)
    ResourceCleanup.add('vm', vm_id)

    # make sure the VM is up and pingable from natbox
    LOG.tc_step("Ping VM {} from NatBox(external network)".format(vm_id))
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id, fail_ok=False)

    # check vm-topology make sure the created vm's page size is 4k
    LOG.tc_step("Verify cpu info for vm {} via vm-topology.".format(vm_id))
    con_ssh = ControllerClient.get_active_controller()
    # retrieve the correct table from the vm-topology
    nova_tab = table_parser.tables(con_ssh.exec_cmd('vm-topology --show servers',expect_timeout=30)[1],
                                   combine_multiline_entry=False)[0]
    print(nova_tab)
    vm_row = [row for row in nova_tab['values'] if row[1] == vm_id][0]
    attribute = vm_row[11].split(', ')
    assert attribute[2] == 'pgsize:4K', "expected result to be pgsize:4K. " \
                                        "However, output is {} ".format(attribute[2])

    prev_vm_host = nova_helper.get_vm_host(vm_id)
    LOG.tc_step("Cold migrate VM and ensure it succeeded")
    # block_mig = True if boot_source == 'image' else False
    code, output = vm_helper.cold_migrate_vm(vm_id)
    assert 0 == code, "Cold migrate is not successful. Details: {}".format(output)

    post_vm_host = nova_helper.get_vm_host(vm_id)
    assert prev_vm_host != post_vm_host


def _boot_vm_under_test(storage_backing, ephemeral, swap, cpu_pol, vcpus, vm_type):

    LOG.tc_step("Create a flavor with {} vcpus, {} ephemera disk, {} swap disk".format(vcpus, ephemeral, swap))

    flavor_id = nova_helper.create_flavor(name='live-mig', ephemeral=ephemeral, swap=swap, vcpus=vcpus,
                                          check_storage_backing=True)[1]
    ResourceCleanup.add('flavor', flavor_id)

    specs = {FlavorSpec.STORAGE_BACKING: storage_backing,
             'hw:mem_page_size': 'small'}
    if cpu_pol is not None:
        specs[FlavorSpec.CPU_POLICY] = cpu_pol

    LOG.tc_step("Add following extra specs: {}".format(specs))
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **specs)

    # verify there is enough 4k pages on compute nodes to create 4k page flavor
    is_enough_4k_page_memory()

    boot_source = 'volume' if vm_type == 'volume' else 'image'
    LOG.tc_step("Boot a vm from {}".format(boot_source))
    vm_id = vm_helper.boot_vm('mig', flavor=flavor_id, source=boot_source)[1]
    ResourceCleanup.add('vm', vm_id)

    if vm_type == 'image_with_vol':
        LOG.tc_step("Attach volume to vm")
        vm_helper.attach_vol_to_vm(vm_id=vm_id)

    return vm_id