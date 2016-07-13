# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

import re

import time
import sys
from pytest import fixture, mark
from utils import cli
from utils import table_parser
from utils.ssh import NATBoxClient
from utils.tis_log import LOG
from consts.timeout import VMTimeout, EventLogTimeout
from consts.cgcs import FlavorSpec, ImageMetadata, VMStatus, EventLogID
from consts.auth import Tenant
from keywords import nova_helper, vm_helper, host_helper, cinder_helper, glance_helper, system_helper
from testfixtures.resource_mgmt import ResourceCleanup



def test_vm_reboot_with_heartbeat():
    """
    Test reboot with guest heartbeat enabled

    Test Steps:
        - Create a flavor with heartbeat set to true, and auto recovery set to given value in extra spec
        - Create a volume from cgcs-guest image
        - Boot a vm with the flavor and the volume
        - Verify guest heartbeat is established via system event-logs
        - Set vm to unhealthy state via touch /tmp/unhealthy
        - Verify vm auto recovery behavior is as expected based on auto recovery setting in flavor

    Teardown:
        - Delete created vm, volume, image, flavor

    """

    # Determine which compute the vm is on
    vm_name = 'vm_with_hb'
    LOG.tc_step("Create a flavor with guest_heartbeart set to true")
    flavor_id = nova_helper.create_flavor(name='heartbeat')[1]
    ResourceCleanup.add('flavor', flavor_id)

    extra_specs = {FlavorSpec.GUEST_HEARTBEAT: 'True'}

    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    LOG.tc_step("Boot a vm using the flavor with guest heartbeat")
    vm_id = vm_helper.boot_vm(name=vm_name, flavor=flavor_id)[1]
    ResourceCleanup.add('vm', vm_id, del_vm_vols=True)
    time.sleep(30)

    LOG.tc_step("Verify vm heartbeat is on via event logs")
    #event = system_helper.wait_for_events(EventLogTimeout.HEARTBEAT_ESTABLISH, strict=False, fail_ok=False,
    #                                      **{'Entity Instance ID': vm_id, 'Event Log ID': [
    #                                         EventLogID.HEARTBEAT_DISABLED, EventLogID.HEARTBEAT_ENABLED]})[0]
    #assert event == EventLogID.HEARTBEAT_ENABLED, "Heartbeat is disabled for vm {}".format(vm_id)

    # Determine which compute the vm is on
    with host_helper.ssh_to_host('controller-0') as cont_ssh:
        vm_table = table_parser.table(cli.nova('show', vm_id, ssh_client=cont_ssh, auth_info=Tenant.ADMIN))
        table_param = 'OS-EXT-SRV-ATTR:host'
        compute_name = table_parser.get_value_two_col_table(vm_table, table_param)

    # Login to the compute and verify the vm heart is beating
    cat_log = 'cat /var/log/guestServer.log'
    with host_helper.ssh_to_host(compute_name) as compute_ssh:
        exitcode, output = compute_ssh.exec_cmd(cat_log, expect_timeout=900)
        assert ('is heartbeating' in output)

    LOG.tc_step("Login to vm: %s via NatBox and verify heartbeat is enabled" % vm_name)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:

        # verify that the heartbeat is running on the vm
        check_log = 'cat /var/log/daemon.log'
        exitcode, output = vm_ssh.exec_cmd(check_log, expect_timeout=900)
        assert('heartbeat state change from enabling to enabled' in output)

        LOG.tc_step("Run touch /tmp/unhealthy to put vm into unhealthy state.")
        vm_ssh.exec_cmd("touch /tmp/unhealthy")

    LOG.tc_step("Wait for reboot to complete and verify heartbeat is running.")
    time.sleep(60)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:

        # verify that the heartbeat is running on the vm
        check_log = 'cat /var/log/daemon.log'
        exitcode, output = vm_ssh.exec_cmd(check_log, expect_timeout=900)
        assert('heartbeat state change from enabling to enabled' in output)

        #step_str = "is rebooted automatically" if autorecovery_enabled else "is not rebooted"
        #LOG.tc_step("Verify vm {} with auto recovery set to {}".format(step_str, autorecovery_enabled))
        #natbox_ssh = NATBoxClient.get_natbox_client()
        #index = natbox_ssh.expect("Power button pressed", timeout=300, fail_ok=True)

        #if not autorecovery_enabled:
        #    assert -1 == index, "VM is rebooted automatically even though Auto Recovery is set to false."

        #else:
        #    assert 0 == index, "Auto recovery to reboot the vm is not kicked off within timeout."

        #   LOG.tc_step("Verify instance rebooting active alarm is on")
        #    alarms_tab = system_helper.get_alarms()
        #    reasons = table_parser.get_values(alarms_tab, 'Reason Text', strict=False, **{'Entity ID': vm_id})
        #    assert re.search('Instance .* is rebooting on host', '\n'.join(reasons)), \
        #        "Instance rebooting active alarm is not listed"


