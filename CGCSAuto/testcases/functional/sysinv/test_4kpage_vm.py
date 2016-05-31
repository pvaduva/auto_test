###
# Testcase 58 of the 2016-04-04 sysinv_test_plan.pdf
# 58) Launch VMs using 4k-memory-pages
###


from pytest import fixture, mark, skip
import ast
from time import sleep

from utils import cli
from utils.ssh import ControllerClient
from utils import table_parser
from consts.auth import Tenant
from consts.timeout import CLI_TIMEOUT
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, host_helper, system_helper


@fixture(scope='module')
def smallpage_flavor_vm(request):
    """
    Text fixture to create flavor with specific 'ephemeral', 'swap', and 'mem_page_size'
    Args:
        request: pytest arg

    Returns: flavor dict as following:
        {'id': <flavor_id>,
         'boot_source : image
         'pagesize': pagesize
        }
    """
    pagesize = 'small'

    flavor_id = nova_helper.create_flavor()[1]
    pagesize_spec = {'hw:mem_page_size': pagesize}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **pagesize_spec)

    # verify there is enough 4k pages on compute nodes to create 4k page flavor
    is_enough_4k_page_memory()

    boot_source = 'image'
    vm_id = vm_helper.boot_vm(flavor=flavor_id, source=boot_source)[1]

    vm = {'id': vm_id,
          'pagesize': pagesize,
          'boot_source': boot_source,
          }

    def delete_flavor_vm():
        # must delete VM before flavors
        vm_helper.delete_vms(vm_id, delete_volumes=True)
        nova_helper.delete_flavors(flavor_ids=flavor_id, fail_ok=True)
    request.addfinalizer(delete_flavor_vm)

    return vm


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
    # check if any 4k pages greater than 60000 means more than 2G total.
    check = False
    for host in host_helper.get_hypervisors():
        for proc_id in [0, 1]:
            num_4k_page = system_helper.get_host_mem_values(host, ['vm_total_4K'], proc_id=proc_id)
            if int(num_4k_page[0]) > 600000 and get_host_aggregate(host) == 'image':
                check = True
                break

    if not check:
        # randomly pick a compute-0 node and give it enough 4k pages
        host_helper.lock_host('compute-0')
        system_helper.set_host_4k_pages('compute-0', proc_id=1, smallpage_num=600000)
        host_helper.unlock_host('compute-0')


def test_4k_page_vm(smallpage_flavor_vm):
    """
    58) Launch VMs using 4k-memory-pages from sysinv_test_plan.pdf

    Verify the version number (or str) exist for the system when execute the "system show" cli

    Args:
        - Nothing

    Setup:
        - Setup flavor with mem_page_size to small
        - Setup enough 4k page if there isnt enough inany of the compute nodes
        - Setup vm with 4k page

    Test Steps:
        -execute "vm-topology" cli
        -verify the vm from the table generated contain 'pgsize:4K'

    Teardown:
        - delete created 4k page vm
        - delete created 4k page flavor

    """
    vm_id = smallpage_flavor_vm['id']
    vm_pagesize= smallpage_flavor_vm['pagesize']
    # check vm-topology

    LOG.tc_step("Verify cpu info for vm {} via vm-topology.".format(vm_id))
    con_ssh = ControllerClient.get_active_controller()
    # retrieve the correct table from the vm-topology
    nova_tab = table_parser.tables(con_ssh.exec_cmd('vm-topology --show servers',expect_timeout=30)[1],
                                   combine_multiline_entry=False)[0]

    vm_row = [row for row in nova_tab['values'] if row[1] == vm_id][0]
    attribute = vm_row[11].split(', ')

    assert attribute[2] == 'pgsize:4K', "expected result to be pgsize:4K. " \
                                        "However, output is {} ".format(attribute[2])


