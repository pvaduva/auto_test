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
    ResourceCleanup.add(resource_type='flavor', resource_id=flavor_id, scope='module')
    heartbeat_spec = {FlavorSpec.GUEST_HEARTBEAT: heartbeat}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **heartbeat_spec)

    boot_source = 'image'
    vm_id = vm_helper.boot_vm(flavor=flavor_id, source=boot_source)[1]
    ResourceCleanup.add(resource_type='vm', resource_id=vm_id, scope='module')
    events = system_helper.wait_for_events(EventLogTimeout.HEARTBEAT_ESTABLISH, strict=False, fail_ok=True,
                                           **{'Entity Instance ID': vm_id, 'Event Log ID': [
                                              EventLogID.HEARTBEAT_DISABLED, EventLogID.HEARTBEAT_ENABLED]})
    if heartbeat == 'True':
        assert events, "VM heartbeat is not enabled."
        assert EventLogID.HEARTBEAT_ENABLED == events[0], "VM heartbeat failed to establish."
    else:
        assert not events, "Heartbeat event generated unexpectedly: {}".format(events)


    # use volume to boot a vm by default
    vm_id = vm_helper.boot_vm(flavor=flavor_id)[1]
    ResourceCleanup.add(resource_type='vm', resource_id=vm_id, scope='module')
    events = system_helper.wait_for_events(EventLogTimeout.HEARTBEAT_ESTABLISH, strict=False, fail_ok=True,
                                           **{'Entity Instance ID': vm_id, 'Event Log ID': [
                                              EventLogID.HEARTBEAT_DISABLED, EventLogID.HEARTBEAT_ENABLED]})

    vm = {'id': vm_id,
          'heartbeat': heartbeat
          }

    return vm


def test_vm_pause_resume_five_time(heartbeat_flavor_vm):
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

    LOG.tc_step("Pause and Resume VM five times")

    # find the compute node where the vm is located
    for i in range(0,5):
        LOG.info("Pause and unpause vm. #{}".format(i))
        vm_helper.pause_vm(vm_id)
        sleep(10)
        vm_helper.unpause_vm(vm_id)
        sleep(10)

    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:

        LOG.tc_step("check heartbeat after restart vim nfv-vim.pid ")
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




def test_vm_live_migration_five_time(heartbeat_flavor_vm):
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

    LOG.tc_step("Pause and Resume VM five times")
    # find the compute node where the vm is located

    # On the compute node hosting the VM, inspect /var/log/guestServer.log
    # On the active controller, inspect /var/log/guestAgent.log

    LOG.tc_step("Live migrate the VMs five time")
    # find the compute node where the vm is located
    for i in range(0, 5):
        LOG.info("Live migrate vm. #{}".format(i))
        vm_helper.live_migrate_vm(vm_id, block_migrate=True)
        sleep(5)

    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:

        LOG.tc_step("check heartbeat after restart vim nfv-vim.pid ")
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

