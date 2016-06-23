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

#TODO execute this when natbox is back up
@mark.parametrize(('action', 'revert','vm_voting'), [
    ('pause','unpause','/tmp/vote_no_to_suspend'),
    #('suspend','resume', '/tmp/vote_no_to_suspend'),
    #('stop','start', '/tmp/vote_no_to_stop'),
    #('reboot','','/tmp/vote_no_to_reboot'),
    #('live_migrate','','/tmp/vote_no_to_migrate'),
])
def test_vm_voting_timeout(action, revert, vm_voting):

    heartbeat = 'True'

    flavor_id = nova_helper.create_flavor()[1]
    heartbeat_spec = {FlavorSpec.GUEST_HEARTBEAT: heartbeat}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **heartbeat_spec)
    ResourceCleanup.add('flavor', flavor_id)

    boot_source = 'image'
    vm_id = vm_helper.boot_vm(flavor=flavor_id, source=boot_source)[1]
    # assume heartbeat is working
    system_helper.wait_for_events(EventLogTimeout.HEARTBEAT_ESTABLISH, strict=False, fail_ok=False,
                                  **{'Entity Instance ID': vm_id,
                                     'Event Log ID': [EventLogID.HEARTBEAT_DISABLED, EventLogID.HEARTBEAT_ENABLED]})

    #ResourceCleanup.add('vm', vm_id)

    # touch the vm_voting_no_timeout file
    LOG.tc_step("touch /tmp/event_timeout file into created VM")
    cmd = "touch /tmp/event_timeout"
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        vm_ssh.exec_cmd(cmd)

    # verifiy the actions are working
    LOG.tc_step("verify {} is still working".format(action))
    cmd_str = "vm_helper.{}_vm(vm_id)".format(action)
    eval(cmd_str)

    # revert back once excuted
    if revert:
        cmd_str = "vm_helper.{}_vm(vm_id)".format(revert)
        eval(cmd_str)

    # touch the voting file verfied they all still work
    cmd = "touch {}".format(vm_voting)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        vm_ssh.exec_cmd(cmd)

    # confirm the action still work
    cmd_str = "vm_helper.{}_vm(vm_id)".format(action)
    eval(cmd_str)

    # revert back once excuted
    if revert:
        cmd_str = "vm_helper.{}_vm(vm_id)".format(revert)
        eval(cmd_str)

    # delete vm automatically

