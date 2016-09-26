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

    events = system_helper.wait_for_events(EventLogTimeout.HEARTBEAT_ESTABLISH, strict=False, fail_ok=True,
                                           **{'Entity Instance ID': vm_id, 'Event Log ID': [
                                               EventLogID.HEARTBEAT_DISABLED, EventLogID.HEARTBEAT_ENABLED]})
    assert events, "VM heartbeat is not enabled."
    assert EventLogID.HEARTBEAT_ENABLED == events[0], "VM heartbeat failed to establish."

    # Teardown to remove the vm and flavor
    def restore_hosts():
        LOG.fixture_step("Cleaning up vms..")
        vm_helper.delete_vms(vm_id, delete_volumes=True)

    request.addfinalizer(restore_hosts)

    return vm_id


def test_guest_heartbeat_reboot_option(vm_):
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
    LOG.tc_step("Boot a vm using the flavor with guest heartbeat")
    vm_name = 'vm_with_hb'
    vm_id = vm_
    time.sleep(30)

    LOG.tc_step('Determine which compute the vm is on')
    compute_name = nova_helper.get_vm_host(vm_id)

    LOG.tc_step("Login to vm: %s and confirm the guest-client is running" % vm_name)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        exitcode, pid = vm_ssh.exec_cmd("ps -ef | grep guest-client | grep -v grep | awk '{print $2}'")
        assert (pid is not None)

        LOG.tc_step("Open /etc/guest-client/heartbeat/guest_heartbeat.conf \
         and confirm CORRECTIVE_ACTION is set to reboot")

        check_log = 'cat /etc/guest-client/heartbeat/guest_heartbeat.conf'
        exitcode, output = vm_ssh.exec_cmd(check_log, expect_timeout=900)
        assert('reboot' in output)

        LOG.tc_step("Force kill the guest-client on the VM.")
        vm_ssh.exec_cmd("kill -9 %s" % pid)

    LOG.tc_step("Verify VM automatically reboots.")

    time.sleep(20)
    events_tab = system_helper.get_events()
    reasons = table_parser.get_values(events_tab, 'Reason Text', strict=False, **{'Entity Instance ID': vm_id})
    assert re.search('Reboot complete for instance .* now enabled on host', '\n'.join(reasons)), \
        "Was not able to reboot VM"



