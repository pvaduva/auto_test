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
from keywords import nova_helper, vm_helper, system_helper, common
from testfixtures.fixture_resources import ResourceCleanup


@fixture(scope='module')
def flavor_(request):
    flavor_id = nova_helper.create_flavor(name='heartbeat')[1]
    ResourceCleanup.add('flavor', flavor_id, scope='module')

    extra_specs = {FlavorSpec.GUEST_HEARTBEAT: 'True'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    return flavor_id


@fixture(scope='module')
def vm_(flavor_):

    vm_name = 'vm_with_hb'
    flavor_id = flavor_

    vm_id = vm_helper.boot_vm(name=vm_name, flavor=flavor_id, cleanup='module')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    system_helper.wait_for_events(EventLogTimeout.HEARTBEAT_ESTABLISH, entity_instance_id=vm_id, fail_ok=False,
                                  **{'Event Log ID': EventLogID.HEARTBEAT_ENABLED})

    return vm_id


def test_vm_with_heartbeat_failure(vm_):
    """
    Test vm when a heartbeat failure occurs

    Test Steps:
        - Create a flavor with heartbeat set to true, and auto recovery set to given value in extra spec
        - Create a volume from tis image
        - Boot a vm with the flavor and the volume
        - Verify guest heartbeat is established via system event-logs
        - Set vm to unhealthy state by force kill guest-client pid in vm
        - Verify vm auto recovery behavior is as expected based on auto recovery setting in flavor

    Teardown:
        - Delete created vm, volume, image, flavor

    """

    LOG.tc_step("Boot a vm using the flavor with guest heartbeat")
    vm_id = vm_

    LOG.tc_step('Determine which compute the vm is on')
    pre_compute_name = nova_helper.get_vm_host(vm_id)

    LOG.tc_step("Kill the heartbeat daemon")
    start_time = common.get_date_in_format()
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        cmd = "ps -ef | grep 'heartbeat' | grep -v grep | awk '{print $2}'"
        exitcode, output = vm_ssh.exec_cmd(cmd)
        cmd = "kill -9 %s" % output
        vm_ssh.exec_sudo_cmd(cmd, expect_timeout=90)

    LOG.tc_step("Verify an active alarm for the reboot is present")
    system_helper.wait_for_events(timeout=120, num=10, entity_instance_id=vm_id, start=start_time,
                                  fail_ok=False, **{'Event Log ID': EventLogID.REBOOT_VM_COMPLETE})

    compute_name = nova_helper.get_vm_host(vm_id)
    assert compute_name == pre_compute_name

    LOG.tc_step("Kill the heartbeat daemon again")
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        cmd = "ps -ef | grep [h]eartbeat | awk '{print $10}' "
        vm_ssh.wait_for_cmd_output(cmd, 'cgcs.heartbeat', timeout=30, strict=False, expt_timeout=5, check_interval=2)

        cmd = "ps -ef | grep 'heartbeat' | grep -v grep | awk '{print $2}'"
        exitcode, out = vm_ssh.exec_cmd(cmd)
        cmd = "kill -9 %s" % out
        vm_ssh.exec_sudo_cmd(cmd, expect_timeout=90)

    system_helper.wait_for_events(timeout=120, num=10, entity_instance_id=vm_id, start=start_time,
                                  fail_ok=False, **{'Event Log ID': EventLogID.REBOOT_VM_COMPLETE})

    LOG.tc_step('Determine which compute the vm is on after the reboot')
    new_compute_name = nova_helper.get_vm_host(vm_id)

    assert (new_compute_name == compute_name)




