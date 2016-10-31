from pytest import fixture, mark, skip
from time import sleep

from utils.tis_log import LOG
from utils.ssh import ControllerClient
from consts.cgcs import EventLogID, FlavorSpec
from consts.timeout import EventLogTimeout
from keywords import nova_helper, vm_helper, host_helper, system_helper
from testfixtures.resource_mgmt import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


@fixture(scope='module', autouse=True)
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

    return flav_ids


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
        if vm_host == system_helper.get_active_controller_name():
            LOG.tc_step("Vm is on active controller. Swacting...")
            host_helper.swact_host()

        LOG.tc_step("Rebooting {}".format(vm_host))
        HostsToRecover.add(vm_host, scope='function')
        host_helper.reboot_hosts(vm_host)

    elif action == 'lock':
        vm_host = nova_helper.get_vm_host(vm_id)
        if vm_host == system_helper.get_active_controller_name():
            LOG.tc_step("Vm is on active controller. Swacting...")
            host_helper.swact_host()

        LOG.tc_step("Locking {}".format(vm_host))
        HostsToRecover.add(vm_host, scope='function')
        host_helper.lock_host(vm_host)

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
    ('True', 'migrate'),
    # ('True', 'reboot'),   fails because of CGTS-4911 (cgcs-guest issue)
    ('True', 'lock'),
    ('False', 'lock'),
    ('True', 'vim_restart')
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
    LOG.tc_step("Booting vm. heartbeat enabled: {}".format(hb_enabled))
    vm_id = vm_helper.boot_vm('hb_guest', flavor=heartbeat_flavors[hb_enabled])[1]
    ResourceCleanup.add(resource_type='vm', resource_id=vm_id, scope='function')
    events = system_helper.wait_for_events(EventLogTimeout.HEARTBEAT_ESTABLISH, strict=False, fail_ok=True,
                                           **{'Entity Instance ID': vm_id, 'Event Log ID': [
                                               EventLogID.HEARTBEAT_DISABLED, EventLogID.HEARTBEAT_ENABLED]})

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
