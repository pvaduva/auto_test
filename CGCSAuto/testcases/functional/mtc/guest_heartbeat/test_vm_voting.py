import re
import time
from pytest import fixture, mark, skip
from utils import table_parser
from utils.tis_log import LOG
from utils import cli
from consts.timeout import EventLogTimeout
from consts.cgcs import FlavorSpec, VMStatus, EventLogID
from consts.reasons import SkipReason
from keywords import nova_helper, vm_helper, host_helper, system_helper
from testfixtures.fixture_resources import ResourceCleanup


@fixture(scope='module')
def hb_flavor():
    flavor_id = nova_helper.create_flavor(name='heartbeat')[1]
    ResourceCleanup.add('flavor', flavor_id, scope='module')

    extra_specs = {FlavorSpec.GUEST_HEARTBEAT: 'True'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    return flavor_id


def boot_vm_(flavor):

    vm_name = 'vm_with_hb'
    LOG.tc_step("Boot a vm with heartbeat enabled")
    vm_id = vm_helper.boot_vm(name=vm_name, flavor=flavor, cleanup='function')[1]
    # ResourceCleanup.add('vm', vm_id, del_vm_vols=True, scope='function')

    event = system_helper.wait_for_events(EventLogTimeout.HEARTBEAT_ESTABLISH, strict=False, fail_ok=True,
                                          **{'Entity Instance ID': vm_id, 'Event Log ID': [
                                              EventLogID.HEARTBEAT_DISABLED, EventLogID.HEARTBEAT_ENABLED]})

    assert event, "VM heartbeat is not enabled."
    assert EventLogID.HEARTBEAT_ENABLED == event[0], "VM heartbeat failed to establish."

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
            # TODO check the rejection output or exitcode == 1
            LOG.tc_step("Verify that attempts to pause the VM is not allowed")
            code, out = vm_helper.pause_vm(vm_id, fail_ok=True)
            vm_state = nova_helper.get_vm_status(vm_id)
            LOG.info(out)
            assert vm_state == VMStatus.ACTIVE
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=30)

            LOG.tc_step("Verify that attempts to suspend the VM is not allowed")
            code, out = vm_helper.suspend_vm(vm_id, fail_ok=True)
            vm_state = nova_helper.get_vm_status(vm_id)
            LOG.info(out)
            assert vm_state == VMStatus.ACTIVE
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=30)

        else:
            LOG.tc_step("Verify that the vm can be paused and unpaused")
            vm_helper.pause_vm(vm_id)
            vm_state = nova_helper.get_vm_status(vm_id)
            assert vm_state == VMStatus.PAUSED
            assert not vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=60, fail_ok=True), \
                "The vm is still pingable after pause"

            vm_helper.unpause_vm(vm_id)
            vm_state = nova_helper.get_vm_status(vm_id)
            assert vm_state == VMStatus.ACTIVE
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

            LOG.tc_step("Verify that the vm can be suspended and resumed")
            vm_helper.suspend_vm(vm_id)
            vm_state = nova_helper.get_vm_status(vm_id)
            assert vm_state == VMStatus.SUSPENDED
            assert not vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=60, fail_ok=True), \
                "The vm is still pingable after suspend"

            vm_helper.resume_vm(vm_id)
            vm_state = nova_helper.get_vm_status(vm_id)
            assert vm_state == VMStatus.ACTIVE
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

            events_tab = system_helper.get_events_table(num=10)
            reasons = table_parser.get_values(events_tab, 'Reason Text', strict=False,
                                              **{'Entity Instance ID': vm_id, 'State': 'log'})
            assert re.search('Stop complete for instance .* now disabled on host', '\n'.join(reasons)), \
                "Was not able to stop VM even though voting is removed"

            LOG.tc_step("Verify a VM can be started again")
            vm_helper.start_vms(vm_id)
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

            events_tab = system_helper.get_events_table(num=10)
            reasons = table_parser.get_values(events_tab, 'Reason Text', strict=False,
                                              **{'Entity Instance ID': vm_id, 'State': 'log'})
            assert re.search('Start complete for instance .* now enabled on host', '\n'.join(reasons)), \
                "Was not able to stop VM even though voting is removed"


@mark.parametrize('action', [
    mark.p2('migrate'),
    mark.p2('suspend'),
    mark.p2('reboot'),
    mark.priorities('domain_sanity', 'nightly')('stop'),
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
            skip(SkipReason.LESS_THAN_TWO_HYPERVISORS)

    vm_id = boot_vm_(hb_flavor)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:

        LOG.tc_step("Wait for guest heartbeat process to run continuously for more than 10 seconds")
        vm_helper.wait_for_process('heartbeat', vm_ssh=vm_ssh, timeout=60, time_to_stay=10, check_interval=1,
                                   fail_ok=False)

        LOG.tc_step("Set vote_no_to_{} from guest".format(action))
        cmd = 'touch /tmp/vote_no_to_{}'.format(action)
        vm_ssh.exec_cmd(cmd)
        time.sleep(5)

    _perform_action(vm_id, action, expt_fail=True)

    LOG.tc_step("Remove the voting file")
    cmd = "rm -f /tmp/vote_no_to_{}".format(action)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        vm_ssh.exec_cmd(cmd)
        time.sleep(5)

    _perform_action(vm_id, action, expt_fail=False)


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
        skip(SkipReason.LESS_THAN_TWO_HYPERVISORS)

    LOG.tc_step("Boot a vm without guest heartbeat")
    vm_name = 'vm_no_hb_migrate'
    vm_id = vm_helper.boot_vm(name=vm_name, cleanup='function')[1]
    # ResourceCleanup.add('vm', vm_id, del_vm_vols=True, scope='function')
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    LOG.tc_step("Check heartbeat event is NOT logged")
    events = system_helper.wait_for_events(timeout=120, strict=False, fail_ok=True,
                                           **{'Entity Instance ID': vm_id, 'Event Log ID': [
                                              EventLogID.HEARTBEAT_DISABLED, EventLogID.HEARTBEAT_ENABLED]})
    assert EventLogID.HEARTBEAT_ENABLED not in events, "Heartbeat enable event appeared while hb is disabled in flavor"

    cmd = 'touch /tmp/vote_no_to_migrate'
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        LOG.tc_step("Check guest heartbeat process is not running")
        vm_helper.wait_for_process('heartbeat', vm_ssh=vm_ssh, timeout=60, time_to_stay=10, check_interval=1,
                                   fail_ok=False, disappear=True)

        LOG.tc_step("Set vote_not_to_migrate from guest")
        vm_ssh.exec_cmd(cmd)

    time.sleep(10)
    _perform_action(vm_id, 'migrate', expt_fail=False)