###
#from us63135_tc9: validate_heartbeat_works_after_compute_node_reboot
###


from pytest import fixture, mark, skip
from time import sleep

from utils import table_parser
from utils.tis_log import LOG
from utils.ssh import ControllerClient
from consts.cgcs import EventLogID, FlavorSpec
from consts.timeout import EventLogTimeout
from keywords import nova_helper, vm_helper, host_helper, system_helper
from testfixtures.resource_mgmt import ResourceCleanup

# heartbeat Type
flavor_params = ['True']


@fixture(scope='module', params=flavor_params)
def heartbeat_flavor_vm(request):
    """
    Text fixture to create flavor with specific 'heartbeat'
    Args:
        request: pytest arg

    Returns: flavor dict as following:
        {'id': <flavor_id>,
         'heartbeat': <True/False>
        }
    """
    heartbeat = request.param

    flavor_id = nova_helper.create_flavor()[1]
    heartbeat_spec = {FlavorSpec.GUEST_HEARTBEAT: heartbeat}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **heartbeat_spec)
    ResourceCleanup.add('flavor', flavor_id,scope='module')

    # use volume to boot a vm by default
    vm_id = vm_helper.boot_vm(flavor=flavor_id)[1]
    events = system_helper.wait_for_events(EventLogTimeout.HEARTBEAT_ESTABLISH, strict=False, fail_ok=True,
                                           **{'Entity Instance ID': vm_id, 'Event Log ID': [
                                              EventLogID.HEARTBEAT_DISABLED, EventLogID.HEARTBEAT_ENABLED]})

    vm = {'id': vm_id,
          'heartbeat': heartbeat
          }

    ResourceCleanup.add('vm', vm_id, scope='module')

    return vm


def test_heartbeat_after_vim_restart(heartbeat_flavor_vm):
    """
    from us63135_tc11: validate_heartbeat_works_after_vim_restart

    Verfiy heartbeat is still function after vim process is killed and restarted

    Args:
        - Nothing

    Setup:
        1) Log on to active controller, add flavor with extension with heartbeat enabled.
        2) Instantiate VM and log into their VM consoles. Verify it's running on a compute node.
        3) Confirm that heartbeating is running in VM (check logs, and/or "ps -ef | fgrep guest-client").
        4) Kill the vim process on active controller

    Test Steps:
        5) Verify VMs is still successfully running
        6) Log back into VM consoles, and verify that heartbeat is running

    Teardown:
        -delete vm
        -unlock locked host

    """
    vm_id = heartbeat_flavor_vm['id']
    heartbeat_type = heartbeat_flavor_vm['heartbeat']

    LOG.tc_step("Kill the nfv-vim.pid process on active controller")
    # find the compute node where the vm is located

    vm_host_table = system_helper.get_vm_topology_tables('servers')[0]
    vm_host = table_parser.get_values(vm_host_table, 'host', ID=vm_id)[0]

    #restart vim process
    #run this from active controller
    ssh_client = ControllerClient.get_active_controller()
    controller = system_helper.get_active_controller_name()
    first_cmd = "cat /var/volatile/run/nfv-vim.pid"
    code, output = ssh_client.exec_sudo_cmd(first_cmd)
    second_cmd = "kill -9 "+output
    ssh_client.exec_sudo_cmd(second_cmd)


    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:


        LOG.tc_step("check heartbeat after restart vim nfv-vim.pid ")
        cmd = "ps -ef | grep [h]eartbeat | awk '{print $10}' "
        heartbeat_proc_shown = vm_ssh.wait_for_cmd_output(cmd, 'cgcs.heartbeat', timeout=10, strict=False, expt_timeout=3,
                                                          check_interval=2)

        if heartbeat_proc_shown:
            heartbeat_proc_disappear = vm_ssh.wait_for_cmd_output(cmd, 'cgcs.heartbeat', timeout=10, strict=False,
                                                                  expt_timeout=3, disappear=True, check_interval=2)
            if heartbeat_type == 'False':
                assert heartbeat_proc_disappear, "Heartbeat set to False, However, heartbeat process is running " \
                                                 "after compute lock."
            else:
                assert not heartbeat_proc_disappear, "Heartbeat set to True. However, heartbeat process is not " \
                                                     "running after compute lock."

        else:
            heartbeat_proc_appear = vm_ssh.wait_for_cmd_output(cmd, 'cgcs.heartbeat', timeout=10, strict=False,
                                                               expt_timeout=3, check_interval=2)
            if heartbeat_type == 'True':
                assert heartbeat_proc_appear, "Heartbeat set to True. However, heartbeat process is not running " \
                                              "after compute lock."
            else:
                assert not heartbeat_proc_appear, "Heartbeat set to False, However, heartbeat process is running " \
                                                  "after compute lock. "

