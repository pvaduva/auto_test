###
#from us63135_tc11: validate_heartbeat_works_after_compute_node_reboot
###


from pytest import fixture, mark, skip
from time import sleep

from utils import table_parser
from utils.tis_log import LOG
from consts.cgcs import EventLogID, FlavorSpec
from consts.timeout import EventLogTimeout
from keywords import nova_helper, vm_helper, host_helper, system_helper


# heartbeat Type
flavor_params = ['True', 'False']


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

    boot_source = 'image'
    vm_id = vm_helper.boot_vm(flavor=flavor_id, source=boot_source)[1]
    events = system_helper.wait_for_events(EventLogTimeout.HEARTBEAT_ESTABLISH, strict=False, fail_ok=True,
                                           **{'Entity Instance ID': vm_id, 'Event Log ID': [
                                              EventLogID.HEARTBEAT_DISABLED, EventLogID.HEARTBEAT_ENABLED]})
    if heartbeat == 'True':
        assert events, "VM heartbeat is not enabled."
        assert EventLogID.HEARTBEAT_ENABLED == events[0], "VM heartbeat failed to establish."
    else:
        assert not events, "Heartbeat event generated unexpectedly: {}".format(events)

    vm = {'id': vm_id,
          'boot_source': boot_source,
          'heartbeat': heartbeat
          }

    def delete_flavor_vm():
        # must delete VM before flavors
        vm_helper.delete_vms(vm_id, delete_volumes=True)
        nova_helper.delete_flavors(flavor_ids=flavor_id, fail_ok=True)
    request.addfinalizer(delete_flavor_vm)

    return vm


def test_heartbeat_after_compute_lock(heartbeat_flavor_vm):
    """
    from us63135_tc11: validate_heartbeat_works_after_compute_node_reboot

    Verfiy heartbeat is still function after compute node where vm is located is locked

    Args:
        - Nothing

    Setup:
        1) Log on to active controller, add flavor with extension with heartbeat enabled.
        2) Instantiate VM and log into their VM consoles. Verify it's running on a compute node.
        3) Confirm that heartbeating is running in both VMs (check logs, and/or "ps -ef | fgrep guest-client").
        4) Lock the compute node.

    Test Steps:
        5) Verify VMs successfully migrate to the other compute node.
        6) Log back into VM consoles, and verify that heartbeat is running

    Teardown:
        -delete vm

    """
    vm_id = heartbeat_flavor_vm['id']
    heartbeat_type = heartbeat_flavor_vm['heartbeat']

    LOG.tc_step("Reboot the compute node where the VM is located")
    # find the compute node where the vm is located

    vm_host_table = system_helper.get_vm_topology_tables('servers')[0]
    vm_host = table_parser.get_values(vm_host_table,'host', ID=vm_id)[0]

    host_helper.lock_host(vm_host)
    compute_list = system_helper.get_computes()
    print(compute_list)

    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:

        LOG.tc_step("check heartbeat after swact")
        cmd = "ps -ef | grep [h]eartbeat | awk '{print $10}' "
        heartbeat_proc_shown = vm_ssh.wait_for_cmd_output(cmd, 'cgcs.heartbeat', timeout=10, strict=False, expt_timeout=3,
                                                          check_interval=2)

        if heartbeat_proc_shown:
            heartbeat_proc_disappear = vm_ssh.wait_for_cmd_output(cmd, 'cgcs.heartbeat', timeout=10, strict=False,
                                                                  expt_timeout=3, disappear=True, check_interval=2)
            if heartbeat_type == 'False':
                assert heartbeat_proc_disappear, "Heartbeat set to False, However, heartbeat process is running " \
                                                 "after swact."
            else:
                assert not heartbeat_proc_disappear, "Heartbeat set to True. However, heartbeat process is not " \
                                                     "running after swact."

        else:
            heartbeat_proc_appear = vm_ssh.wait_for_cmd_output(cmd, 'cgcs.heartbeat', timeout=10, strict=False,
                                                               expt_timeout=3, check_interval=2)
            if heartbeat_type == 'True':
                assert heartbeat_proc_appear, "Heartbeat set to True. However, heartbeat process is not running " \
                                              "after swact."
            else:
                assert not heartbeat_proc_appear, "Heartbeat set to False, However, heartbeat process is running " \
                                                  "after swact. "

    # unlock the locked compute node after test
    host_helper.unlock_host(vm_host)
