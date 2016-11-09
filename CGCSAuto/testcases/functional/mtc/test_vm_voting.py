import re
import time
from pytest import fixture, mark
from utils import table_parser
from utils.tis_log import LOG
from utils import cli
from consts.timeout import EventLogTimeout
from consts.cgcs import FlavorSpec, VMStatus, EventLogID
from keywords import nova_helper, vm_helper, host_helper, system_helper
from testfixtures.resource_mgmt import ResourceCleanup


@fixture(scope='module')
def flavor_():
    flavor_id = nova_helper.create_flavor(name='heartbeat')[1]
    ResourceCleanup.add('flavor', flavor_id, scope='module')

    extra_specs = {FlavorSpec.GUEST_HEARTBEAT: 'True'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    return flavor_id


@fixture(scope='function')
def vm_(flavor_):

    vm_name = 'vm_with_hb'
    flavor_id = flavor_
    LOG.fixture_step("Boot a vm with heartbeat enabled")

    vm_id = vm_helper.boot_vm(name=vm_name, flavor=flavor_id)[1]
    ResourceCleanup.add('vm', vm_id, del_vm_vols=True, scope='function')

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
            assert ('action-rejected' in output)
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=30)

            LOG.tc_step("Verify that attempts to hard reboot the VM is not allowed")
            exitcode, output = cli.nova('reboot --hard', vm_id, fail_ok=True)
            assert ('action-rejected' in output)
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=30)
        else:
            LOG.tc_step("Verify the VM can be rebooted")
            vm_helper.reboot_vm(vm_id)
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

            events_tab = system_helper.get_events_table(num=10)
            reasons = table_parser.get_values(events_tab, 'Reason Text', strict=False,
                                              **{'Entity Instance ID': vm_id, 'State': 'log'})
            assert re.search('Reboot complete for instance .* now enabled on host', '\n'.join(reasons)), \
                "Was not able to reboot VM"

            LOG.tc_step("Verify the VM can be hard rebooted")
            cli.nova('reboot --hard', vm_id)
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

            events_tab = system_helper.get_events_table(num=10)
            reasons = table_parser.get_values(events_tab, 'Reason Text', strict=False,
                                              **{'Entity Instance ID': vm_id, 'State': 'log'})
            assert re.search('Reboot complete for instance .* now enabled on host', '\n'.join(reasons)), \
                "Was not able to reboot VM even though voting is removed"

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
    'migrate',
    'suspend',
    'reboot',
    'stop',
])
def test_vm_voting(action, vm_):
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
    vm_id = vm_

    LOG.tc_step("Verify vm heartbeat is on by checking the heartbeat process")
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        exitcode, output = vm_ssh.exec_cmd("ps -ef | grep heartbeat | grep -v grep")
        assert (output is not None)

        LOG.tc_step("Set the voting criteria")
        cmd = 'touch /tmp/vote_no_to_{}'.format(action)
        vm_ssh.exec_cmd(cmd)

    _perform_action(vm_id, action, expt_fail=True)

    LOG.tc_step("Remove the voting file")
    cmd = "rm /tmp/vote_no_to_{}".format(action)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        vm_ssh.exec_cmd(cmd)

    _perform_action(vm_id, action, expt_fail=False)


def test_vm_voting_no_hb_migrate():
    """
    Test that a vm voting without heartbeat does not reject actions

    Test Steps:
        - Boot a vm without heartbeat
        - Vote no to migrating
        - Verify that migrating the vm is not rejected

    """
    vm_name = 'vm_no_hb_migrate'
    vm_id = vm_helper.boot_vm(name=vm_name)[1]
    ResourceCleanup.add('vm', vm_id, del_vm_vols=True, scope='function')
    time.sleep(30)

    cmd = 'touch /tmp/vote_no_to_migrate'
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        LOG.tc_step("Set the no migrate voting criteria")
        vm_ssh.exec_cmd(cmd)

    time.sleep(10)
    _perform_action(vm_id, 'migrate', expt_fail=False)
