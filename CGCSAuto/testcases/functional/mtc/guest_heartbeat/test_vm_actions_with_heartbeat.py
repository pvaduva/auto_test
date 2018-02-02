from pytest import fixture, mark, skip
from time import sleep

from utils.tis_log import LOG
from utils.ssh import ControllerClient
from consts.reasons import SkipSysType
from consts.cgcs import EventLogID, FlavorSpec
from consts.timeout import EventLogTimeout
from keywords import nova_helper, vm_helper, host_helper, system_helper
from testfixtures.fixture_resources import ResourceCleanup, GuestLogs
from testfixtures.recover_hosts import HostsToRecover


@fixture(scope='module')
def heartbeat_flavors():
    """
    Create two flavors. One with heartbeat enabled, one with heartbeat disabled.
    Returns (dict): {'True': flav_id with hb, 'False': flav_id without hb}

    """

    flav_ids = {}

    flavor_id = nova_helper.create_flavor('hb_flavor')[1]
    ResourceCleanup.add(resource_type='flavor', resource_id=flavor_id, scope='module')
    heartbeat_spec = {FlavorSpec.GUEST_HEARTBEAT: 'True'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **heartbeat_spec)
    flav_ids['True'] = flavor_id

    flavor_id = nova_helper.create_flavor('no_hb_flavor')[1]
    ResourceCleanup.add(resource_type='flavor', resource_id=flavor_id, scope='module')
    flav_ids['False'] = flavor_id

    is_simplex = system_helper.is_simplex()
    return flav_ids, is_simplex


def _perform_action_on_hb_vm(vm_id, action):
    """
    Performs certain actions on vms with and without hb enabled
    Args:
        vm_id:
        action (str): swact, pause, kill_hb, guest_reboot, host-reboot, lock, vim_restart

    Returns:

    """
    if action == 'swact':
        LOG.tc_step("Swacting controllers")
        host_helper.swact_host()

    elif action == 'pause':
        LOG.tc_step("Pausing and unpausing vm 5 times")
        for i in range(0, 5):
            vm_helper.pause_vm(vm_id)
            sleep(15)
            vm_helper.unpause_vm(vm_id)
            sleep(15)

    elif action == 'migrate':
        LOG.tc_step("Live migrating 5 times")
        for i in range(0, 5):
            vm_helper.live_migrate_vm(vm_id)
            sleep(10)

    elif action == 'reboot':
        vm_host = nova_helper.get_vm_host(vm_id)
        # if vm_host == system_helper.get_active_controller_name():
        #     LOG.tc_step("Vm is on active controller. Swacting...")
        #     host_helper.swact_host()

        LOG.tc_step("Rebooting {}".format(vm_host))
        HostsToRecover.add(vm_host, scope='function')
        host_helper.reboot_hosts(vm_host)

    elif action == 'vm_reboot':
        LOG.tc_step("'sudo reboot -f' from vm, and check vm stays on same host")
        vm_helper.sudo_reboot_from_vm(vm_id)

    elif action == 'lock':
        vm_host = nova_helper.get_vm_host(vm_id)

        LOG.tc_step("Locking {}".format(vm_host))
        HostsToRecover.add(vm_host, scope='function')
        host_helper.lock_host(vm_host, swact=True)

    elif action == 'vim_restart':
        LOG.tc_step("Killing nfv-vim process")
        ssh_client = ControllerClient.get_active_controller()
        first_cmd = "cat /var/volatile/run/nfv-vim.pid"
        code, output = ssh_client.exec_sudo_cmd(first_cmd)
        second_cmd = "kill -9 " + output
        ssh_client.exec_sudo_cmd(second_cmd)


@mark.parametrize(('hb_enabled', 'action'), [
    ('True', 'swact'),
    ('False', 'swact'),
    ('True', 'pause'),
    mark.domain_sanity(('True', 'migrate')),
    ('True', 'reboot'),   # failed because of CGTS-4911 (cgcs-guest issue)
    ('True', 'vm_reboot'),
    ('True', 'lock'),
    ('False', 'lock'),
    mark.domain_sanity(('True', 'vim_restart'))
])
def test_hb_vm_with_action(hb_enabled, action, heartbeat_flavors):
    """
    Creates a vm with heartbeat enabled or disabled and performs an action and
    checks if heartbeat is still in the same state
    Args:
        hb_enabled:
        action:
        heartbeat_flavors: fixture, creates two flavors with hb enabled and disabled

    Setup:
        - Creates two flavors, one with hb, one without

    Test Steps:
        - Boot vm with hb enabled or disabled
        - Wait for heartbeat enabled event
        - Perform failure scenario action
        - Check if heartbeat is running or not on the vm

    Teardown:
        - Delete vm and volume

    """
    heartbeat_flavors, is_simplex = heartbeat_flavors

    if is_simplex and action in ['swact', 'lock', 'migrate']:
        skip(SkipSysType.SIMPLEX_SYSTEM)

    LOG.tc_step("Booting vm. heartbeat enabled: {}".format(hb_enabled))
    vm_id = vm_helper.boot_vm('hb_guest', flavor=heartbeat_flavors[hb_enabled], cleanup='function')[1]
    GuestLogs.add(vm_id)
    events = system_helper.wait_for_events(EventLogTimeout.HEARTBEAT_ESTABLISH, strict=False, fail_ok=True,
                                           entity_instance_id=vm_id,
                                           **{'Event Log ID': [EventLogID.HEARTBEAT_DISABLED,
                                                               EventLogID.HEARTBEAT_ENABLED]})

    if hb_enabled == 'True':
        assert events, "VM heartbeat is not enabled."
        assert EventLogID.HEARTBEAT_ENABLED == events[0], "VM heartbeat failed to establish."
    else:
        assert not events, "Heartbeat event generated unexpectedly: {}".format(events)

    _perform_action_on_hb_vm(vm_id, action)

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:

        LOG.tc_step("check heartbeat after {}".format(action))
        cmd = "ps -ef | grep [h]eartbeat | awk '{print $10}' "
        heartbeat_proc_shown = vm_ssh.wait_for_cmd_output(cmd, 'cgcs.heartbeat', timeout=10, strict=False,
                                                          expt_timeout=5, check_interval=2)

        if heartbeat_proc_shown:
            heartbeat_proc_disappear = vm_ssh.wait_for_cmd_output(cmd, 'cgcs.heartbeat', timeout=10, strict=False,
                                                                  expt_timeout=5, disappear=True, check_interval=2)
            if hb_enabled == 'False':
                assert heartbeat_proc_disappear, "Heartbeat set to False, However, heartbeat process is running " \
                                                 "after {}.".format(action)
            else:
                assert not heartbeat_proc_disappear, "Heartbeat set to True. However, heartbeat process is not " \
                                                     "running after {}.".format(action)

        else:
            heartbeat_proc_appear = vm_ssh.wait_for_cmd_output(cmd, 'cgcs.heartbeat', timeout=10, strict=False,
                                                               expt_timeout=5, check_interval=2)
            if hb_enabled == 'True':
                assert heartbeat_proc_appear, "Heartbeat set to True. However, heartbeat process is not running " \
                                              "after {}.".format(action)
            else:
                assert not heartbeat_proc_appear, "Heartbeat set to False, However, heartbeat process is running " \
                                                  "after {}.".format(action)

    GuestLogs.remove(vm_id)


@mark.p3
def test_clean_vm_deletion_after_live_migration(heartbeat_flavors):
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
    heartbeat_flavors, is_simplex = heartbeat_flavors

    if is_simplex:
        skip("Not applicable to simplex system")

    # use volume to boot a vm by default
    vm_id = vm_helper.boot_vm(flavor=heartbeat_flavors['True'], cleanup='function')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)
    GuestLogs.add(vm_id)
    system_helper.wait_for_events(EventLogTimeout.HEARTBEAT_ESTABLISH, strict=False, fail_ok=False,
                                  **{'Entity Instance ID': vm_id, 'Event Log ID': EventLogID.HEARTBEAT_ENABLED})

    LOG.tc_step("Live migrate the VM")
    vm_helper.live_migrate_vm(vm_id)

    LOG.tc_step("Delete the vm")
    # get new vm_host location after live migration
    vm_host = nova_helper.get_vm_host(vm_id)
    vm_helper.delete_vms(vm_id, stop_first=False)
    GuestLogs.remove(vm_id)

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
