###
#from us63135_tc6: validate_clean_VM_deletion_after_live_migration
###

from pytest import fixture, mark, skip
from time import sleep

from utils.tis_log import LOG
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
    ResourceCleanup.add('flavor', flavor_id, scope='module')
    heartbeat_spec = {FlavorSpec.GUEST_HEARTBEAT: heartbeat}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **heartbeat_spec)

    # use volume to boot a vm by default
    vm_id = vm_helper.boot_vm(flavor=flavor_id)[1]
    ResourceCleanup.add('vm', vm_id, scope='module')
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



def test_clean_vm_deletion_after_live_migration(heartbeat_flavor_vm):
    """
    from us63135_tc6: validate_clean_VM_deletion_after_live_migration

    Args:
        - Nothing

    Setup:
        1) Log on to active controller, add flavor with extension with heartbeat enabled.
        2) Instantiate a VM.
        3) On controller console, live migrate the VM.
        4) Delete the VM after migration completes.

    Test Steps:
        5) Verify clean deletion by inspecting guestServer/guestAgent logs:
           * On the compute node hosting the VM, inspect /var/log/guestServer.log
           * On the active controller, inspect /var/log/guestAgent.log

    Teardown:
        -delete vm
        -unlock locked host

    """
    vm_id = heartbeat_flavor_vm['id']
    heartbeat_type = heartbeat_flavor_vm['heartbeat']

    LOG.tc_step("Live migrate the VM")
    # find the compute node where the vm is located
    vm_helper.live_migrate_vm(vm_id, block_migrate=True)
    # get new vm_host location after live migration
    vm_host = nova_helper.get_vm_host(vm_id)
    vm_helper.delete_vms(vm_id)

    # On the compute node hosting the VM, inspect /var/log/guestServer.log
    # look for line : Info : c84d5215-3d9b-4176-9a60-cc2907d803af delete
    with host_helper.ssh_to_host(vm_host) as vm_compute_node:
        compare_line = "Info : "+vm_id+" delete"
        compute_cmd = "cat /var/log/guestServer.log | grep '"+compare_line+"'"
        code, compute_output = vm_compute_node.exec_cmd(cmd=compute_cmd)

        LOG.tc_step("confirm line '{}' exist ".format(compare_line))
        assert code == 0, "delete output found in /var/log/guestServer.log"

    # On the active controller, inspect /var/log/guestAgent.log
    # look for line : Info : compute-0 removed instance c84d5215-3d9b-4176-9a60-cc2907d803af
    # the result should be different
    active_host = system_helper.get_active_controller_name()
    with host_helper.ssh_to_host(active_host) as vm_compute_node:

        compare_line = vm_host+" removed instance " + vm_id
        controller_cmd = "cat /var/log/guestAgent.log | grep '"+compare_line+"'"
        code, controller_output = vm_compute_node.exec_cmd(cmd=controller_cmd)

        LOG.tc_step("confirm line '{}' exist ".format(compare_line))
        assert code == 0, "delete output found in /var/log/guestAgent.log"
