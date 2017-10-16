# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

from pytest import fixture, mark

from utils.tis_log import LOG
from consts.timeout import EventLogTimeout
from consts.cgcs import FlavorSpec, EventLogID

from keywords import nova_helper, vm_helper, common, system_helper
from testfixtures.fixture_resources import ResourceCleanup


@fixture(scope='module')
def vm_():
    flavor_id = nova_helper.create_flavor(name='heartbeat')[1]
    ResourceCleanup.add('flavor', flavor_id, scope='module')

    extra_specs = {FlavorSpec.GUEST_HEARTBEAT: 'True'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    vm_name = 'vm_with_hb'

    vm_id = vm_helper.boot_vm(name=vm_name, flavor=flavor_id, cleanup='module')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    events = system_helper.wait_for_events(EventLogTimeout.HEARTBEAT_ESTABLISH, strict=False, fail_ok=False,
                                           entity_instance_id=vm_id, **{'Event Log ID': [EventLogID.HEARTBEAT_DISABLED,
                                                                                         EventLogID.HEARTBEAT_ENABLED]})
    assert EventLogID.HEARTBEAT_ENABLED == events[0], "VM heartbeat failed to establish."

    return vm_id


def test_guest_heartbeat_reboot_option(vm_):
    """
    Test reboot with guest heartbeat enabled

    Test Steps:
        - Create a flavor with heartbeat set to true, and auto recovery set to given value in extra spec
        - Boot a vm from volume with the flavor
        - Verify guest heartbeat is established via system event-list
        - Set vm to unhealthy state by 'kill -9 <guest-client_pid>' on vm
        - Verify vm auto recovery behavior is as expected based on auto recovery setting in flavor

    Teardown:
        - Delete created vm, volume, image, flavor

    """

    # Determine which compute the vm is on
    LOG.tc_step("Boot a vm using the flavor with guest heartbeat")
    vm_name = 'vm_with_hb'
    vm_id = vm_

    LOG.tc_step("Login to vm: %s and confirm the guest-client is running" % vm_name)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        exitcode, pid = vm_ssh.exec_cmd("ps -ef | grep guest-client | grep -v grep | awk '{print $2}'")
        assert (pid is not None)

        LOG.tc_step("Open /etc/guest-client/heartbeat/guest_heartbeat.conf \
         and confirm CORRECTIVE_ACTION is set to reboot")

        check_log = 'cat /etc/guest-client/heartbeat/guest_heartbeat.conf'
        exitcode, output = vm_ssh.exec_cmd(check_log, expect_timeout=900)
        assert('reboot' in output)

        start_time = common.get_date_in_format()
        LOG.tc_step("Force kill the guest-client on the VM.")
        vm_ssh.exec_cmd("kill -9 %s" % pid)

    LOG.tc_step("Verify VM automatically rebooted.")
    system_helper.wait_for_events(timeout=300, start=start_time, entity_instance_id=vm_id, strict=False, fail_ok=False,
                                  **{'Reason Text': 'Reboot complete for instance'})

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
