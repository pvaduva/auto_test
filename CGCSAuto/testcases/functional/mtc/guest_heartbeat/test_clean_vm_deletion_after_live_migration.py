###
# from us63135_tc6: validate_clean_VM_deletion_after_live_migration
###

from pytest import mark

from utils.tis_log import LOG
from utils.ssh import ControllerClient
from consts.cgcs import EventLogID, FlavorSpec
from consts.timeout import EventLogTimeout
from keywords import nova_helper, vm_helper, host_helper, system_helper
from testfixtures.fixture_resources import ResourceCleanup


@mark.p3
def test_clean_vm_deletion_after_live_migration():
    """
    from us63135_tc6: validate_clean_VM_deletion_after_live_migration

    Test Steps:
        1) Log on to active controller, add flavor with extension with heartbeat enabled.
        2) Instantiate a VM.
        3) On controller console, live migrate the VM.
        4) Delete the VM after migration completes.
        5) Verify clean deletion by inspecting guestServer/guestAgent logs:
           * On the compute node hosting the VM, inspect /var/log/guestServer.log
           * On the active controller, inspect /var/log/guestAgent.log

    Teardown:
        -delete vm
        -unlock locked host

    """
    LOG.tc_step("Create a flavor with guest heartbeat enabled")
    flavor_id = nova_helper.create_flavor()[1]
    ResourceCleanup.add('flavor', flavor_id)
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **{FlavorSpec.GUEST_HEARTBEAT: True})

    # use volume to boot a vm by default
    vm_id = vm_helper.boot_vm(flavor=flavor_id, cleanup='function')[1]
    system_helper.wait_for_events(EventLogTimeout.HEARTBEAT_ESTABLISH, strict=False, fail_ok=False,
                                  **{'Entity Instance ID': vm_id, 'Event Log ID': EventLogID.HEARTBEAT_ENABLED})

    LOG.tc_step("Live migrate the VM")
    vm_helper.live_migrate_vm(vm_id)

    LOG.tc_step("Delete the vm")
    # get new vm_host location after live migration
    vm_host = nova_helper.get_vm_host(vm_id)
    vm_helper.delete_vms(vm_id, stop_first=False)

    # On the compute node hosting the VM, inspect /var/log/guestServer.log
    # look for line : Info : c84d5215-3d9b-4176-9a60-cc2907d803af delete
    guestserver_log = "Info : {} delete".format(vm_id)
    LOG.tc_step("Check line '{}' in /var/log/guestServer.log on vm host".format(guestserver_log))

    with host_helper.ssh_to_host(vm_host) as host_ssh:
        compute_cmd = "cat /var/log/guestServer.log | grep '"+guestserver_log+"'"
        code, compute_output = host_ssh.exec_cmd(cmd=compute_cmd)
        assert code == 0, "Expected string is not found in /var/log/guestServer.log: {}".format(guestserver_log)

    # On the active controller, inspect /var/log/guestAgent.log
    # look for line : Info : compute-0 removed instance c84d5215-3d9b-4176-9a60-cc2907d803af
    # the result should be different
    guestagent_log = "{} removed instance {}".format(vm_host, vm_id)
    LOG.tc_step("Check line '{}' in /var/log/guestAgent.log on active controller".format(guestagent_log))

    con_ssh = ControllerClient.get_active_controller()
    controller_cmd = "cat /var/log/guestAgent.log | grep '"+guestagent_log+"'"
    code, controller_output = con_ssh.exec_cmd(cmd=controller_cmd)
    assert code == 0, "Expected string is not found in /var/log/guestAgent.log: {}".format(guestagent_log)
