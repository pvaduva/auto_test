###
#from us57002_tc2: Pause/Suspend VM
###


from pytest import fixture, mark, skip
from time import sleep

from utils import table_parser
from utils.tis_log import LOG
from consts.cgcs import EventLogID, FlavorSpec
from consts.timeout import EventLogTimeout
from keywords import nova_helper, vm_helper, host_helper, system_helper


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

    #def delete_flavor_vm():
    #    # must delete VM before flavors
    #    vm_helper.delete_vms(vm_id, delete_volumes=True)
    #    nova_helper.delete_flavors(flavor_ids=flavor_id, fail_ok=True)
    #request.addfinalizer(delete_flavor_vm)

    return vm


def test_vm_voting_pause_and_suspend(heartbeat_flavor_vm):

    vm_id = heartbeat_flavor_vm['id']
    heartbeat_type = heartbeat_flavor_vm['heartbeat']

    cmd = "touch /tmp/vote_no_to_suspend"
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        vm_ssh.exec_cmd(cmd)

    #try to pause

    #verify it fail

    #try to suspend

    #verify that fail

    cmd = "rm /tmp/vote_no_to_suspend"
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        vm_ssh.exec_cmd(cmd)

    # try to pause

    # verify that pass

    # try to suspend

    #verify that pass

