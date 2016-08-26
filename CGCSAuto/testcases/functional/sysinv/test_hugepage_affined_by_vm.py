
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
from testfixtures.resource_mgmt import ResourceCleanup


@fixture(scope='module', params=['2048'])
def create_vm_(request):
    """
    Text fixture to create flavor with specific pagesize of 2M, (it's possible to add smallsize and hugesize as well
    but they require checking to see if there are enough memory available. This require additional checking)
    Args:
        request: pytest arg

    Returns: flavor dict as following:
        {'id': <flavor_id>,
         'boot_source : image
         'pagesize': pagesize
        }
    """
    page_size = request.param
    flavor_id = nova_helper.create_flavor()[1]
    ResourceCleanup.add(resource_type='flavor', resource_id=flavor_id, scope='module')
    pagesize_spec = {'hw:mem_page_size': page_size}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **pagesize_spec)

    boot_source = 'image'
    vm_id = vm_helper.boot_vm(flavor=flavor_id, source=boot_source)[1]
    ResourceCleanup.add(resource_type='vm', resource_id=vm_id, scope='module')

    vm = {'id': vm_id,
          'pagesize': page_size,
          'boot_source': boot_source,
          }

    # def delete_flavor_vm():
    #     # must delete VM before flavors
    #     vm_helper.delete_vms(vm_id, delete_volumes=True)
    #     nova_helper.delete_flavors(flavor_ids=flavor_id, fail_ok=True)
    # request.addfinalizer(delete_flavor_vm)

    return vm


# overall skip condition
def more_than_one_vm():
    return len(nova_helper.get_vms()) > 0


@mark.skipif(more_than_one_vm(), reason="More than one VM in the system. May skew the memory comparison")
def test_hugepage_affined_by_vm(create_vm_):
    """
    39) Verify Huge page memory is consumed on same NUMA node where VM is affined
    The test assume there us no other VMs running

    Args:
        an VM created to test memory are been cosumed by NUMA node

    Setup:
        - create a simple VM object with 2M hugepages

    Test Steps:
        - check the memory of the node where the VM is created
        - compare it with the memory of the VM to see if they are the same

    Teardown:
        - remove VM and it's flavours
    """

    vm_id = create_vm_['id']
    LOG.tc_step("Verify memory info for vm {} via vm-topology.".format(vm_id))
    con_ssh = ControllerClient.get_active_controller()
    # retrieve the correct table from the vm-topology
    nova_tab = table_parser.tables(con_ssh.exec_cmd('vm-topology --show servers', expect_timeout=30)[1],
                                   combine_multiline_entry=False)[0]

    vm_row = [row for row in nova_tab['values'] if row[1] == vm_id][0]
    host_name = vm_row[4]
    instance_topo = vm_row[11].split(', ')
    memory_size = int(instance_topo[1][0:-2])
    proc_id = instance_topo[0][-1]
    # memory_size return how much memory a vm used
    LOG.tc_step("Wait for 30 seconds for clis to sync up")
    sleep(30)
    total_used_mem = system_helper.get_host_used_mem_values(host_name, proc_id)

    assert memory_size == total_used_mem, "Expected {}MB to be used by VM {}. However, " \
                                          "{} MB were used instead".format(memory_size, vm_id, total_used_mem )
# i Want to get the host and instance
