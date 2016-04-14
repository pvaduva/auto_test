from pytest import fixture, mark, skip
from time import sleep

from utils import cli
from utils import table_parser
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, host_helper, system_helper
from setup_consts import P1, P2, P3

###
#us63135_tc11: validate_heartbeat_works_after_controller_swact
###

# heartbeat Type
flavor_params = ['True', 'False']


@fixture(scope='module', params=flavor_params)
def heartbeat_flavor_vm(request):
    """
    Text fixture to create flavor with specific 'ephemeral', 'swap', and 'heartbeat'
    Args:
        request: pytest arg

    Returns: flavor dict as following:
        {'id': <flavor_id>,
         'heartbeat': <True/False>
        }
    """
    heartbeat = request.param

    flavor_id = nova_helper.create_flavor()[1]
    heartbeat_spec = {'sw:wrs:guest:heartbeat': heartbeat}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **heartbeat_spec)

    boot_source = 'image'
    vm_id = vm_helper.boot_vm(flavor=flavor_id, source=boot_source)[1]

    vm = {'id': vm_id,
          'boot_source': boot_source,
          'heartbeat': heartbeat
          }

    def delete_flavor_vm():
        # must delete VM before flavors
        vm_helper.delete_vm(vm_id=vm_id, delete_volumes=True)
        nova_helper.delete_flavors(flavor_ids=flavor_id, fail_ok=True)
    request.addfinalizer(delete_flavor_vm)

    return vm


def test_heartbeat(heartbeat_flavor_vm):
    """
    check the heartbeat of a given vm

    Args:
        heartbeat_flavor_vm: vm_ fixture which passes the created vm based on  <local_image, local_lvm, or remote>,

    """
    vm_id = heartbeat_flavor_vm['id']
    heartbeat_type = heartbeat_flavor_vm['heartbeat']
    # check before swact
    LOG.tc_step("Wait a few seconds before SSH into VM instance")
    sleep(10)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        # Even when heartbeat set to False in flavor. a 'heartbeat' process would show up in VM for a few seconds
        # depend on reply from DE may increase the sleep timer for VM process to settle
        sleep(30)
        LOG.tc_step("check heartbeat before swact")
        cmd = "ps -ef | grep [h]eartbeat | awk '{print $10}' "
        before_ssh_output = vm_ssh.exec_cmd(cmd)
        before_heartbeat = before_ssh_output[1].lstrip()

    LOG.tc_step("execute swact")
    exit_code, output = host_helper.swact_host(fail_ok=True)

    # check after swact
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        sleep(10)
        LOG.tc_step("check heartbeat after swact")
        cmd = "ps -ef | grep [h]eartbeat | awk '{print $10}' "
        after_ssh_output = vm_ssh.exec_cmd(cmd)
        after_heartbeat = after_ssh_output[1].lstrip()

    LOG.tc_step("check heartbeat after swact")
    if heartbeat_type == "True":
        LOG.tc_step("heartbeat process exist and after swact")
        assert before_heartbeat == after_heartbeat == '/dev/virtio-ports/cgcs.heartbeat'
    else:
        LOG.tc_step("heartbeat process does not exist and after swact")
        assert before_heartbeat == after_heartbeat == ''

    # tc end
