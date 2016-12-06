###
#from us57002_tc2: Pause/Suspend VM
###


from pytest import fixture, mark, skip
from time import sleep

from utils import table_parser
from utils.tis_log import LOG
from consts.cgcs import EventLogID, FlavorSpec, VMStatus
from consts.timeout import EventLogTimeout
from keywords import nova_helper, vm_helper, host_helper, system_helper
from testfixtures.resource_mgmt import ResourceCleanup


@fixture(scope='module')
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
    heartbeat = 'True'

    flavor_id = nova_helper.create_flavor()[1]
    ResourceCleanup.add(resource_type='flavor', resource_id=flavor_id, scope='module')
    heartbeat_spec = {FlavorSpec.GUEST_HEARTBEAT: heartbeat}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **heartbeat_spec)

    vm_id = vm_helper.boot_vm(flavor=flavor_id)[1]
    ResourceCleanup.add('vm', vm_id, scope='module')
    events = system_helper.wait_for_events(EventLogTimeout.HEARTBEAT_ESTABLISH, strict=False, fail_ok=True,
                                           **{'Entity Instance ID': vm_id, 'Event Log ID': [
                                              EventLogID.HEARTBEAT_DISABLED, EventLogID.HEARTBEAT_ENABLED]})

    vm = {'id': vm_id,
          'heartbeat': heartbeat
          }

    # touch the vm_voting_no_timeout file
    cmd = "touch /tmp/event_timeout"
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        vm_ssh.exec_cmd(cmd)


    return vm


#TODO execute this when natbox is back up
@mark.parametrize(('action', 'revert','vm_voting'), [
    ('pause_vm','unpause_vm','/tmp/vote_no_to_suspend'),
    ('suspend_vm','resume_vm', '/tmp/vote_no_to_suspend'),
    ('stop_vms','start_vms', '/tmp/vote_no_to_stop'),
    ('reboot_vm','','/tmp/vote_no_to_reboot'),
    ('live_migrate_vm','','/tmp/vote_no_to_migrate'),
])
def test_vm_voting_timeout(heartbeat_flavor_vm, action, revert, vm_voting):
    """

    Args:
        heartbeat_flavor_vm:
        action:
        revert:
        vm_voting:

    Returns:

    """

    vm_id = heartbeat_flavor_vm['id']

    # verifiy the actions are working
    LOG.tc_step("verify {} is still working".format(action))
    cmd_str = "vm_helper.{}(vm_id)".format(action)
    eval(cmd_str)

    # revert back once executed
    if revert:
        cmd_str = "vm_helper.{}(vm_id)".format(revert)
        eval(cmd_str)

    # touch the voting file verfied they all still work
    cmd = "touch {}".format(vm_voting)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        vm_ssh.exec_cmd(cmd)

    #wait for vm to sync
    sleep(20)

    # confirm the action still work
    cmd_str = "vm_helper.{}(vm_id)".format(action)
    eval(cmd_str)

    # revert back once excuted
    if revert:
        cmd_str = "vm_helper.{}(vm_id)".format(revert)
        eval(cmd_str)

    sleep(20)

    # delete vm automatically

