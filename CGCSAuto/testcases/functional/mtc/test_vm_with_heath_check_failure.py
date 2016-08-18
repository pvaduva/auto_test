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

@fixture(scope='module')
def flavor_(request):
    flavor_id = nova_helper.create_flavor(name='heartbeat')[1]
    ResourceCleanup.add('flavor', flavor_id)

    extra_specs = {FlavorSpec.GUEST_HEARTBEAT: 'True'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    def delete_flavor():
        nova_helper.delete_flavors(flavor_ids=flavor_id, fail_ok=True)

    request.addfinalizer(delete_flavor)
    return flavor_id


@fixture(scope='module')
def vm_(request, flavor_):

    vm_name = 'vm_with_hb'
    flavor_id = flavor_

    vm_id = vm_helper.boot_vm(name=vm_name, flavor=flavor_id)[1]
    time.sleep(30)
    ResourceCleanup.add('vm', vm_id, del_vm_vols=True)

    # Teardown to remove the vm and flavor
    def restore_hosts():
        LOG.fixture_step("Cleaning up vms..")
        vm_helper.delete_vms(vm_id, delete_volumes=True)

    request.addfinalizer(restore_hosts)

    return vm_id


def test_vm_with_health_check_failure(vm_):
    """
    Test vm when a health check failure occurs

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

    LOG.tc_step("Boot a vm using the flavor with guest heartbeat")
    vm_name = 'vm_with_hb'
    vm_id = vm_

    LOG.tc_step('Determine which compute the vm is on')
    compute_name = nova_helper.get_vm_host(vm_id)

    #with host_helper.ssh_to_host('controller-0') as cont_ssh:
    #    vm_table = table_parser.table(cli.nova('show', vm_id, ssh_client=cont_ssh, auth_info=Tenant.ADMIN))
    #    table_param = 'OS-EXT-SRV-ATTR:host'
    #    compute_name = table_parser.get_value_two_col_table(vm_table, table_param)

    #LOG.tc_step("Verify vm heartbeat is on via event logs")
    #cat_log = 'cat /var/log/guestServer.log'
    #host = nova_helper.get_vm_host(vm_id)
    #with host_helper.ssh_to_host(host) as compute_ssh:
    #    exitcode, output = compute_ssh.exec_cmd(cat_log, expect_timeout=10)
    #    assert ('is heartbeating' in output)

    LOG.tc_step("Write fail to Health Check file and verify that heartbeat daemon reboots the VM")
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        LOG.tc_step("Run touch /tmp/unhealthy to put vm into unhealthy state.")
        vm_ssh.exec_cmd("touch /tmp/unhealthy")

    LOG.tc_step("Verify an active alarm for the reboot is present")
    reasons = system_helper.wait_for_events(EventLogTimeout.VM_REBOOT_EVENT, strict=False, fail_ok=True,
                                           **{'Entity Instance ID': vm_id, 'Event Log ID': [
                                               EventLogID.VM_REBOOTING]})
    assert reasons, "Instance rebooting active alarm is not listed"
    # time.sleep(20)
    # alarms_tab = system_helper.get_alarms()
    # reasons = table_parser.get_values(alarms_tab, 'Reason Text', strict=False, **{'Entity ID': vm_id})
    # assert re.search('Instance .* is rebooting on host', '\n'.join(reasons)), \
    #     "Instance rebooting active alarm is not listed"

    LOG.tc_step("Kill the vim process to force the VM to another compute")
    with host_helper.ssh_to_host(compute_name) as compute_ssh:
        cmd = "ps -ef | grep 'kvm -c' | grep -v grep | awk '{print $2}'"
        exitcode, output = compute_ssh.exec_cmd(cmd, expect_timeout=90)
        time.sleep(10)
        cmd = "echo 'Li69nux*' | sudo -S kill -9 %s" % output
        exitcode, output = compute_ssh.exec_cmd(cmd, expect_timeout=90)

    time.sleep(10)
    LOG.tc_step('Determine which compute the vm is on after the reboot')
    new_compute_name = nova_helper.get_vm_host(vm_id)

    #with host_helper.ssh_to_host('controller-0') as cont_ssh:
    #    vm_table = table_parser.table(cli.nova('show', vm_id, ssh_client=cont_ssh, auth_info=Tenant.ADMIN))
    #    table_param = 'OS-EXT-SRV-ATTR:host'
    #    new_compute_name = table_parser.get_value_two_col_table(vm_table, table_param)

    assert (new_compute_name == compute_name)




