from pytest import fixture, mark, skip
from time import sleep

from utils.tis_log import LOG
from consts.cgcs import EventLogID, FlavorSpec
from consts.timeout import EventLogTimeout
from keywords import nova_helper, vm_helper, host_helper, system_helper

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


def test_heartbeat_after_swact(heartbeat_flavor_vm):
    """
    check the heartbeat of a given vm

    Args:
        heartbeat_flavor_vm: vm_ fixture which passes the created vm based on  <local_image, local_lvm, or remote>,

    """
    vm_id = heartbeat_flavor_vm['id']
    heartbeat_type = heartbeat_flavor_vm['heartbeat']

    LOG.tc_step("execute swact")
    host_helper.swact_host()

    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:

        LOG.tc_step("check heartbeat after swact")
        cmd = "ps -ef | grep [h]eartbeat | awk '{print $10}' "
        heartbeat_proc_shown = vm_ssh.wait_for_cmd_output(cmd, 'cgcs.heartbeat', timeout=10, strict=False, expt_timeout=3,
                                                          check_interval=2)

        if heartbeat_proc_shown:
            heartbeat_proc_disappear = vm_ssh.wait_for_cmd_output(cmd, 'cgcs.heartbeat', timeout=10, strict=False,
                                                                  expt_timeout=3, disappear=True, check_interval=2)
            if heartbeat_type == 'False':
                assert heartbeat_proc_disappear, "Heartbeat process is running after swact."
            else:
                assert not heartbeat_proc_disappear, "Heartbeat process is not running after swact."

        else:
            heartbeat_proc_appear = vm_ssh.wait_for_cmd_output(cmd, 'cgcs.heartbeat', timeout=10, strict=False,
                                                               expt_timeout=3, check_interval=2)
            if heartbeat_type == 'True':
                assert heartbeat_proc_appear, "Heartbeat process is not running after swact."
            else:
                assert not heartbeat_proc_appear, "Heartbeat process is running after swact."
