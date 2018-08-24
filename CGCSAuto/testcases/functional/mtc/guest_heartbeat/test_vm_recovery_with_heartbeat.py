# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

import time

from utils.tis_log import LOG
from consts.timeout import EventLogTimeout
from consts.cgcs import FlavorSpec, EventLogID

from keywords import nova_helper, vm_helper, host_helper, system_helper, common
from testfixtures.fixture_resources import ResourceCleanup, GuestLogs


def test_vm_with_health_check_failure():
    """
    Test vm when a health check failure occurs

    Test Steps:
        - Boot a vm with with guest heartbeat enabled
        - Verify guest heartbeat is established via fm event-logs
        - Set vm to unhealthy state via touch /tmp/unhealthy
        - Verify vm failed and then auto recovered on the same host
        - Kill kvm process on vm host
        - Verify vm failed and then auto recovered on the same host

    Teardown:
        - Delete created vm, volume, image, flavor

    """

    LOG.tc_step("Boot a vm using the flavor with guest heartbeat enabled")
    flavor_id = nova_helper.create_flavor(name='heartbeat')[1]
    ResourceCleanup.add('flavor', flavor_id)

    extra_specs = {FlavorSpec.GUEST_HEARTBEAT: 'True'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    vm_id = vm_helper.boot_vm(name='vm_with_hb', flavor=flavor_id, cleanup='function')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    GuestLogs.add(vm_id)
    LOG.tc_step("Check guest heartbeat enable event is logged")
    events = system_helper.wait_for_events(timeout=EventLogTimeout.HEARTBEAT_ESTABLISH, strict=False, fail_ok=False,
                                           entity_instance_id=vm_id,
                                           **{'Event Log ID': [EventLogID.HEARTBEAT_DISABLED,
                                                               EventLogID.HEARTBEAT_ENABLED]})

    assert EventLogID.HEARTBEAT_ENABLED == events[0], "VM heartbeat failed to establish."

    LOG.tc_step("Wait for 30 seconds for vm initialization then touch /tmp/unhealthy in vm")
    time.sleep(30)
    compute_name = nova_helper.get_vm_host(vm_id)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:

        LOG.tc_step("Check vm CORRECTIVE_ACTION is 'reboot' in /etc/guest-client/heartbeat/guest_heartbeat.conf")
        check_log = 'cat /etc/guest-client/heartbeat/guest_heartbeat.conf'
        output = vm_ssh.exec_cmd(check_log, fail_ok=False)[1]
        assert 'reboot' in output, "CORRECTIVE_ACTION is not reboot by default"

        LOG.tc_step("check guest-client daemon is running on vm")
        pid = vm_ssh.exec_cmd("ps -ef | grep guest-client | grep -v grep | awk '{print $2}'", fail_ok=False)[1]
        assert pid, "guest-client daemon is not running"

        start_time = common.get_date_in_format()
        LOG.tc_step("Force kill the guest-client on the VM.")
        vm_ssh.exec_cmd("kill -9 %s" % pid)

    check_vm_recovered(vm_id, expt_host=compute_name, start_time=start_time)

    LOG.tc_step("Kill the kvm process to force the VM to error state")
    time.sleep(10)
    start_time = common.get_date_in_format()
    with host_helper.ssh_to_host(compute_name) as compute_ssh:
        cmd = "ps -ef | grep 'kvm -c' | grep -v grep | awk '{print $2}'"
        exitcode, output = compute_ssh.exec_cmd(cmd, expect_timeout=90)
        cmd = "kill -9 %s" % output
        compute_ssh.exec_sudo_cmd(cmd, expect_timeout=90)

    check_vm_recovered(vm_id, expt_host=compute_name, start_time=start_time)

    time.sleep(10)
    LOG.tc_step("Kill the heartbeat daemon")
    start_time = common.get_date_in_format()
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        cmd = "ps -ef | grep 'heartbeat' | grep -v grep | awk '{print $2}'"
        exitcode, output = vm_ssh.exec_cmd(cmd)
        cmd = "kill -9 %s" % output
        vm_ssh.exec_sudo_cmd(cmd, expect_timeout=90)

    check_vm_recovered(vm_id, expt_host=compute_name, start_time=start_time)

    time.sleep(10)
    LOG.tc_step("Kill the heartbeat daemon again")
    start_time = common.get_date_in_format()
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        cmd = "ps -ef | grep [h]eartbeat | awk '{print $10}' "
        vm_ssh.wait_for_cmd_output(cmd, 'cgcs.heartbeat', timeout=30, strict=False, expt_timeout=5, check_interval=2)

        cmd = "ps -ef | grep 'heartbeat' | grep -v grep | awk '{print $2}'"
        exitcode, out = vm_ssh.exec_cmd(cmd)
        cmd = "kill -9 %s" % out
        vm_ssh.exec_sudo_cmd(cmd, expect_timeout=90)

    check_vm_recovered(vm_id, expt_host=compute_name, start_time=start_time)

    time.sleep(10)
    LOG.tc_step("Run touch /tmp/unhealthy to put vm into unhealthy state.")
    start_time = common.get_date_in_format()
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        vm_ssh.exec_cmd("touch /tmp/unhealthy")

    check_vm_recovered(vm_id, expt_host=compute_name, start_time=start_time)
    GuestLogs.remove(vm_id)


def check_vm_recovered(vm_id, expt_host, start_time):
    LOG.tc_step("Verify vm is auto recovered on same host")
    system_helper.wait_for_events(EventLogTimeout.VM_REBOOT, num=10, entity_instance_id=vm_id, start=start_time,
                                  fail_ok=False, **{'Event Log ID': EventLogID.REBOOT_VM_COMPLETE})
    assert expt_host == nova_helper.get_vm_host(vm_id), "VM is recovered onto a different host"
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
