import re
import time
from pytest import fixture, mark, skip

from utils import table_parser
from utils.tis_log import LOG
from consts.timeout import EventLogTimeout
from consts.cgcs import FlavorSpec, VMStatus, EventLogID
from consts.reasons import SkipHypervisor
from keywords import nova_helper, vm_helper, host_helper, system_helper
from testfixtures.fixture_resources import ResourceCleanup, GuestLogs


@fixture(scope='module')
def hb_flavor():
    flavor_id = nova_helper.create_flavor(name='heartbeat')[1]
    ResourceCleanup.add('flavor', flavor_id, scope='module')

    extra_specs = {FlavorSpec.GUEST_HEARTBEAT: 'True'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    return flavor_id


def launch_vm(enable_hb=True, flavor=None, scope='function'):
    vm_name = 'vm_with_hb' if enable_hb else 'vm_no_hb'

    LOG.tc_step("Boot a {}".format(vm_name))
    vm_id = vm_helper.boot_vm(name=vm_name, flavor=flavor, cleanup=scope)[1]
    GuestLogs.add(vm_id, scope=scope)

    LOG.tc_step("Check guest heartbeat event is {}logged".format('' if enable_hb else 'NOT '))
    timeout = EventLogTimeout.HEARTBEAT_ESTABLISH if enable_hb else 120
    events = system_helper.wait_for_events(timeout=timeout, strict=False, fail_ok=True,
                                           **{'Entity Instance ID': vm_id, 'Event Log ID': [
                                               EventLogID.HEARTBEAT_DISABLED, EventLogID.HEARTBEAT_ENABLED]})
    if enable_hb:
        assert events, "VM heartbeat is not enabled."
        assert EventLogID.HEARTBEAT_ENABLED == events[0], "VM heartbeat failed to establish."
    else:
        assert EventLogID.HEARTBEAT_ENABLED not in events, \
            "Heartbeat enable event appeared while hb is disabled in flavor"

    return vm_id


def _perform_action(vm_id, action, expt_fail):
    """
    Perform an action on a vm
    Args:
        vm_id:
        action (str): migrate, suspend, reboot, stop
        expt_fail (bool): if the action is expected to fail because of the vm voting against it

    Returns:

    """
    if action == 'migrate':
        vm_host = nova_helper.get_vm_host(vm_id)
        dest_host = vm_helper.get_dest_host_for_live_migrate(vm_id)
        if expt_fail:
            LOG.tc_step("Verify that attempts to live migrate the VM is not allowed")
            return_code, message = vm_helper.live_migrate_vm(vm_id, fail_ok=True, block_migrate=False,
                                                             destination_host=dest_host)
            assert ('action-rejected' in message), "The vm voted against migrating but live migration was not rejected"
            assert nova_helper.get_vm_host(vm_id) == vm_host, "The vm voted against migrating but was live migrated"
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=30)

            LOG.tc_step("Verify that attempts to cold migrate the VM is not allowed")
            return_code, message = vm_helper.cold_migrate_vm(vm_id, fail_ok=True)
            assert ('action-rejected' in message), "The vm voted against migrating but cold migration was not rejected"
            assert nova_helper.get_vm_host(vm_id) == vm_host, "The vm voted against migrating but was cold migrated"
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=30)

        else:
            LOG.tc_step("Verify the VM can be live migrated")
            return_code, message = vm_helper.live_migrate_vm(vm_id, block_migrate=False,
                                                             destination_host=dest_host)
            vm_host_2 = nova_helper.get_vm_host(vm_id)
            assert return_code in [0, 1] and ('action-rejected' not in message), message
            assert vm_host != vm_host_2, "The vm didn't change hosts"
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

            LOG.tc_step("Verify the VM can be cold migrated")
            return_code, message = vm_helper.cold_migrate_vm(vm_id, revert=False)
            vm_host_3 = nova_helper.get_vm_host(vm_id)
            assert return_code in [0, 1] and ('action-rejected' not in message), message
            assert vm_host_2 != vm_host_3, "The vm didn't change hosts"
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    elif action == 'suspend':
        if expt_fail:
            LOG.tc_step("Verify that attempts to pause the VM is not allowed")
            code, out = vm_helper.pause_vm(vm_id, fail_ok=True)
            assert 1 == code, "pause is not rejected"
            vm_state = nova_helper.get_vm_status(vm_id)
            LOG.info(out)
            assert vm_state == VMStatus.ACTIVE
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=30)

            LOG.tc_step("Verify that attempts to suspend the VM is not allowed")
            code, out = vm_helper.suspend_vm(vm_id, fail_ok=True)
            assert 1 == code, "suspend is not rejected"
            vm_state = nova_helper.get_vm_status(vm_id)
            LOG.info(out)
            assert vm_state == VMStatus.ACTIVE
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=30)

        else:
            LOG.tc_step("Verify that the vm can be paused and unpaused")
            vm_helper.pause_vm(vm_id)
            assert not vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=60, fail_ok=True), \
                "The vm is still pingable after pause"

            vm_helper.unpause_vm(vm_id)
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

            LOG.tc_step("Verify that the vm can be suspended and resumed")
            vm_helper.suspend_vm(vm_id)
            assert not vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=60, fail_ok=True), \
                "The vm is still pingable after suspend"

            vm_helper.resume_vm(vm_id)
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    elif action == 'reboot':
        if expt_fail:
            LOG.tc_step("Verify that attempts to soft reboot the VM is not allowed")
            exitcode, output = vm_helper.reboot_vm(vm_id, hard=False, fail_ok=True)
            assert 1 == exitcode
            assert ('action-rejected' in output)
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=30)

            LOG.tc_step("Verify that attempts to hard reboot the VM is not allowed")
            exitcode, output = vm_helper.reboot_vm(vm_id, hard=True, fail_ok=True)
            assert 1 == exitcode
            assert ('action-rejected' in output)
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=30)
        else:
            LOG.tc_step("Verify the VM can be rebooted")
            vm_helper.reboot_vm(vm_id)
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

            LOG.tc_step("Verify the VM can be hard rebooted")
            vm_helper.reboot_vm(vm_id, hard=True)
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    elif action == 'stop':
        if expt_fail:
            LOG.tc_step("Attempt to stop a VM")
            exitcode, output = vm_helper.stop_vms(vm_id, fail_ok=True)
            assert ('Unable to stop the specified server' in output and 1 == exitcode)
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=30)

        else:
            LOG.tc_step("Verify a VM can be stopped")
            vm_helper.stop_vms(vm_id)
            assert not vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=60, fail_ok=True), \
                "The vm is still pingable after stop"

            events_tab = system_helper.get_events_table(limit=10)
            reasons = table_parser.get_values(events_tab, 'Reason Text', strict=False,
                                              **{'Entity Instance ID': vm_id, 'State': 'log'})
            assert re.search('Stop complete for instance .* now disabled on host', '\n'.join(reasons)), \
                "Was not able to stop VM even though voting is removed"

            LOG.tc_step("Verify a VM can be started again")
            vm_helper.start_vms(vm_id)
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

            events_tab = system_helper.get_events_table(limit=10)
            reasons = table_parser.get_values(events_tab, 'Reason Text', strict=False,
                                              **{'Entity Instance ID': vm_id, 'State': 'log'})
            assert re.search('Start complete for instance .* now enabled on host', '\n'.join(reasons)), \
                "Was not able to stop VM even though voting is removed"


@mark.parametrize('action', [
    mark.p2('migrate'),
    mark.p2('suspend'),
    mark.p2('reboot'),
    mark.priorities('domain_sanity', 'nightly', 'sx_nightly')('stop'),
])
def test_vm_voting(action, hb_flavor):
    """
    Tests that vms with heartbeat can vote to reject certain actions
    Args:
        action:
        vm_: fixture, create vm with heartbeat

    Setup:
        - Create a vm with heartbeat enabled

    Test Steps:
        - Set voting to reject some actions
        - Attempt to perform those actions
        - Remove the voting files
        - Verify that the actions are accepted

    Teardown:
        - Delete created vm

    """
    if action == 'migrate':
        if len(host_helper.get_hypervisors()) < 2:
            skip(SkipHypervisor.LESS_THAN_TWO_HYPERVISORS)

    vm_id = launch_vm(enable_hb=True, flavor=hb_flavor)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:

        LOG.tc_step("Wait for guest heartbeat process to run continuously for more than 10 seconds")
        vm_helper.wait_for_process('heartbeat', vm_ssh=vm_ssh, timeout=60, time_to_stay=10, check_interval=1,
                                   fail_ok=False)

        LOG.tc_step("Wait for 30 seconds for vm initialization before touching file in /tmp")
        time.sleep(30)

        LOG.tc_step("Set vote_no_to_{} from guest".format(action))
        cmd = 'touch /tmp/vote_no_to_{}'.format(action)
        vm_ssh.exec_cmd(cmd)
        time.sleep(15)

    _perform_action(vm_id, action, expt_fail=True)

    LOG.tc_step("Remove the voting file")
    cmd = "rm -f /tmp/vote_no_to_{}".format(action)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        vm_ssh.exec_cmd(cmd)
        time.sleep(15)

    _perform_action(vm_id, action, expt_fail=False)
    GuestLogs.remove(vm_id)


@mark.nightly
def test_vm_voting_no_hb_migrate():
    """
    Test that a vm voting without heartbeat does not reject actions

    Test Steps:
        - Boot a vm without heartbeat
        - Vote no to migrating
        - Verify that migrating the vm is not rejected

    """
    if len(host_helper.get_hypervisors()) < 2:
        skip(SkipHypervisor.LESS_THAN_TWO_HYPERVISORS)

    LOG.tc_step("Boot a vm without guest heartbeat")
    vm_id = launch_vm(enable_hb=False)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    cmd = 'touch /tmp/vote_no_to_migrate'
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        LOG.tc_step("Check guest heartbeat process is not running")
        vm_helper.wait_for_process('heartbeat', vm_ssh=vm_ssh, timeout=60, time_to_stay=10, check_interval=1,
                                   fail_ok=False, disappear=True)

        LOG.tc_step("Wait for 30 seconds for vm initialization before touching file in /tmp")
        time.sleep(30)

        LOG.tc_step("Set vote_not_to_migrate from guest")
        vm_ssh.exec_cmd(cmd)

    time.sleep(10)
    _perform_action(vm_id, 'migrate', expt_fail=False)
    GuestLogs.remove(vm_id)


@fixture(scope='module')
def event_timeout_vm():
    """
    Text fixture to create flavor with specific 'heartbeat'

    Returns: flavor dict as following:
        {'id': <flavor_id>,
         'heartbeat': <True/False>
        }
    """
    LOG.fixture_step("Launch a vm with guest heartbeat enabled")
    heartbeat = 'True'

    flavor_id = nova_helper.create_flavor()[1]
    ResourceCleanup.add(resource_type='flavor', resource_id=flavor_id, scope='module')
    heartbeat_spec = {FlavorSpec.GUEST_HEARTBEAT: heartbeat}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **heartbeat_spec)

    vm_id = vm_helper.boot_vm(flavor=flavor_id, cleanup='module')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    GuestLogs.add(vm_id)
    system_helper.wait_for_events(EventLogTimeout.HEARTBEAT_ESTABLISH, strict=False, fail_ok=True,
                                  entity_instance_id=vm_id,
                                  **{'Event Log ID': [EventLogID.HEARTBEAT_DISABLED, EventLogID.HEARTBEAT_ENABLED]})

    LOG.fixture_step("Wait for 30 seconds and touch /tmp/event_timeout from vm {}".format(vm_id))
    time.sleep(30)

    # touch the vm_voting_no_timeout file
    cmd = "touch /tmp/event_timeout"
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        vm_ssh.exec_cmd(cmd)

    GuestLogs.remove(vm_id)

    return vm_id


@mark.parametrize(('action', 'revert', 'vm_voting'), [
    ('pause_vm', 'unpause_vm', '/tmp/vote_no_to_suspend'),
    ('suspend_vm', 'resume_vm', '/tmp/vote_no_to_suspend'),
    ('stop_vms', 'start_vms', '/tmp/vote_no_to_stop'),
    ('reboot_vm', '', '/tmp/vote_no_to_reboot'),
    ('live_migrate_vm', '', '/tmp/vote_no_to_migrate'),
])
def test_vm_voting_timeout(event_timeout_vm, action, revert, vm_voting):
    """

    Args:
        event_timeout_vm: vm with voting event_timeout touched
        action:
        revert:
        vm_voting:

    Returns:

    """
    vm_id = event_timeout_vm

    # since vm is shared, give it sometime in between tests
    time.sleep(10)
    LOG.tc_step("touch {} from vm".format(vm_voting))
    cmd = "touch {}".format(vm_voting)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        GuestLogs.add(vm_id)
        vm_ssh.exec_cmd(cmd)

    LOG.tc_step("Ensure vote_no actions are still allowed due to event_timeout touched")
    # wait for vm to sync
    time.sleep(10)

    # confirm the action still work
    cmd_str = "vm_helper.{}(vm_id)".format(action)
    eval(cmd_str)

    # revert back once excuted
    if revert:
        cmd_str = "vm_helper.{}(vm_id)".format(revert)
        eval(cmd_str)

    GuestLogs.remove(vm_id)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
