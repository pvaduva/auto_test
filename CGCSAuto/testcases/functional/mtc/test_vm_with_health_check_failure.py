# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

import time
from pytest import fixture, mark

from utils.tis_log import LOG
from consts.timeout import EventLogTimeout
from consts.cgcs import FlavorSpec, EventLogID

from keywords import nova_helper, vm_helper, host_helper, system_helper, common
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

    events = system_helper.wait_for_events(EventLogTimeout.HEARTBEAT_ESTABLISH, strict=False, fail_ok=False, timeout=60,
                                           **{'Entity Instance ID': vm_id,
                                              'Event Log ID': [EventLogID.HEARTBEAT_DISABLED,
                                                               EventLogID.HEARTBEAT_ENABLED]})

    assert EventLogID.HEARTBEAT_ENABLED == events[0], "VM heartbeat failed to establish."

    return vm_id


def test_vm_with_health_check_failure(vm_):
    """
    Test vm when a health check failure occurs

    Test Steps:
        - Create a flavor with heartbeat set to true, and auto recovery set to given value in extra spec
        - Create a volume from tis image
        - Boot a vm with the flavor and the volume
        - Verify guest heartbeat is established via system event-logs
        - Set vm to unhealthy state via touch /tmp/unhealthy
        - Verify vm auto recovery behavior is as expected based on auto recovery setting in flavor

    Teardown:
        - Delete created vm, volume, image, flavor

    """

    LOG.tc_step("Boot a vm using the flavor with guest heartbeat")
    vm_id = vm_

    LOG.tc_step('Determine which compute the vm is on')
    compute_name = nova_helper.get_vm_host(vm_id)

    LOG.tc_step("Write fail to Health Check file and verify that heartbeat daemon reboots the VM")
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        start_time = common.get_date_in_format()
        LOG.tc_step("Run touch /tmp/unhealthy to put vm into unhealthy state.")
        vm_ssh.exec_cmd("touch /tmp/unhealthy")

    LOG.tc_step("Verify vm reboot event is logged")
    system_helper.wait_for_events(EventLogTimeout.VM_REBOOT_EVENT, strict=False, fail_ok=False, start=start_time,
                                  entity_instance_id=vm_id, **{'Event Log ID': EventLogID.VM_REBOOTING})

    LOG.tc_step("Kill the vim process to force the VM to another compute")
    with host_helper.ssh_to_host(compute_name) as compute_ssh:
        cmd = "ps -ef | grep 'kvm -c' | grep -v grep | awk '{print $2}'"
        exitcode, output = compute_ssh.exec_cmd(cmd, expect_timeout=90)
        time.sleep(10)
        cmd = "kill -9 %s" % output
        compute_ssh.exec_sudo_cmd(cmd, expect_timeout=90)

    # FIXME: comments from yang: below code do not match the step log, which says vm host should change
    time.sleep(10)
    LOG.tc_step('Determine which compute the vm is on after the reboot')
    new_compute_name = nova_helper.get_vm_host(vm_id)

    assert (new_compute_name == compute_name)




