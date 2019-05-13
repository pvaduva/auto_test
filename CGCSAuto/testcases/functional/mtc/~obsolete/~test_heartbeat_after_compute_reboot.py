###
#from us63135_tc10: validate_heartbeat_works_after_compute_node_reboot
###


from pytest import fixture, mark, skip
from time import sleep

from utils import table_parser
from utils.tis_log import LOG
from consts.cgcs import EventLogID, FlavorSpec
from consts.timeout import EventLogTimeout
from keywords import nova_helper, vm_helper, host_helper, system_helper
from testfixtures.fixture_resources import ResourceCleanup

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
    ResourceCleanup.add(resource_type='flavor', resource_id=flavor_id, scope='module')
    heartbeat_spec = {FlavorSpec.GUEST_HEARTBEAT: heartbeat}
    nova_helper.set_flavor(flavor=flavor_id, **heartbeat_spec)

    # use volume to boot a vm by default
    vm_id = vm_helper.boot_vm(flavor=flavor_id)[1]
    ResourceCleanup.add(resource_type='vm', resource_id=vm_id, scope='module')
    events = system_helper.wait_for_events(EventLogTimeout.HEARTBEAT_ESTABLISH, strict=False, fail_ok=True,
                                           **{'Entity Instance ID': vm_id, 'Event Log ID': [
                                              EventLogID.HEARTBEAT_DISABLED, EventLogID.HEARTBEAT_ENABLED]})
    if heartbeat == 'True':
        assert events, "VM heartbeat is not enabled."
        assert EventLogID.HEARTBEAT_ENABLED == events[0], "VM heartbeat failed to establish."
    else:
        assert not events, "Heartbeat event generated unexpectedly: {}".format(events)

    vm = {'id': vm_id,
          'heartbeat': heartbeat
          }


    return vm


def test_heartbeat_after_compute_reboot(heartbeat_flavor_vm):
    """
    from us63135_tc11: validate_heartbeat_works_after_compute_node_reboot

    Verfiy heartbeat is still function after compute node where vm is located is locked

    Args:
        - Nothing

    Setup:
        1) Log on to active controller, add flavor with extension with heartbeat enabled.
        2) Instantiate VM and log into their VM consoles. Verify it's running on a compute node.
        3) Confirm that heartbeating is running in VM (check logs, and/or "ps -ef | fgrep guest-client").
        4) Lock the compute node.

    Test Steps:
        5) Verify VMs successfully migrate to the other compute node.
        6) Log back into VM consoles, and verify that heartbeat is running

    Teardown:
        -delete vm
        -unlock locked host

    """
    vm_id = heartbeat_flavor_vm['id']
    heartbeat_type = heartbeat_flavor_vm['heartbeat']

    LOG.tc_step("Verify vm heartbeat is on by checking the heartbeat process")
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        exitcode, output = vm_ssh.exec_cmd("ps -ef | grep heartbeat | grep -v grep")
        assert (output is not None)

    LOG.tc_step("Reboot the compute node where the VM is located")
    # find the compute node where the vm is located
    vm_host = nova_helper.get_vm_host(vm_id)

    host_helper.reboot_hosts(vm_host)
    # wait for hostname to be back in host list in nova
    host_helper.wait_for_hypervisors_up(vm_host)

    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:

        LOG.tc_step("check heartbeat after compute reboot")
        cmd = "ps -ef | grep [h]eartbeat | awk '{print $10}' "
        heartbeat_proc_shown = vm_ssh.wait_for_cmd_output(cmd, 'cgcs.heartbeat', timeout=10, strict=False, expt_timeout=5,
                                                          check_interval=2)

        if heartbeat_proc_shown:
            heartbeat_proc_disappear = vm_ssh.wait_for_cmd_output(cmd, 'cgcs.heartbeat', timeout=10, strict=False,
                                                                  expt_timeout=5, disappear=True, check_interval=2)
            if heartbeat_type == 'False':
                assert heartbeat_proc_disappear, "Heartbeat set to False, However, heartbeat process is running " \
                                                 "after compute lock."
            else:
                assert not heartbeat_proc_disappear, "Heartbeat set to True. However, heartbeat process is not " \
                                                     "running after compute lock."

        else:
            heartbeat_proc_appear = vm_ssh.wait_for_cmd_output(cmd, 'cgcs.heartbeat', timeout=10, strict=False,
                                                               expt_timeout=5, check_interval=2)
            if heartbeat_type == 'True':
                assert heartbeat_proc_appear, "Heartbeat set to True. However, heartbeat process is not running " \
                                              "after compute lock."
            else:
                assert not heartbeat_proc_appear, "Heartbeat set to False, However, heartbeat process is running " \
                                                  "after compute lock. "

