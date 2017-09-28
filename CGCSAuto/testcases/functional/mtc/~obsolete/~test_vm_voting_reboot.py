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
from testfixtures.fixture_resources import ResourceCleanup

@fixture(scope='module')
def flavor_(request):
    flavor_id = nova_helper.create_flavor(name='heartbeat')[1]
    ResourceCleanup.add('flavor', flavor_id, scope='module')

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

    vm_id = vm_helper.boot_vm(name=vm_name, flavor=flavor_id, cleanup='module')[1]
    time.sleep(30)

    event = system_helper.wait_for_events(EventLogTimeout.HEARTBEAT_ESTABLISH, strict=False, fail_ok=True,
                                          **{'Entity Instance ID': vm_id, 'Event Log ID': [
                                              EventLogID.HEARTBEAT_DISABLED, EventLogID.HEARTBEAT_ENABLED]})

    assert event, "VM heartbeat is not enabled."
    assert EventLogID.HEARTBEAT_ENABLED == event[0], "VM heartbeat failed to establish."

    # Teardown to remove the vm and flavor
    def restore_hosts():
        LOG.fixture_step("Cleaning up vms..")
        vm_helper.delete_vms(vm_id, delete_volumes=True)

    request.addfinalizer(restore_hosts)

    return vm_id


def test_vm_voting_reboot(vm_):
    """
    Test vm that a vm cannot stop or start when the voting is set to no

    Test Steps:
        - Create a flavor with the heartbeat extension set to true
        - Instantiate a VM using that flavor
        - Check the VM to ensure the heartbeat process is running
                ps -ef | grep heartbeat
       - touch /tmp/vote_no_to_reboot on the VM
        - Attempt to soft reboot a VM
        - Verify it is rejected
        - Attempt to hard reboot a VM
        - Verify it is rejected
        - Remove the /tmp/vote_no_to_reboot file
        - Verify a VM can be soft rebooted
        - Verify a VM can be hard rebooted

    Teardown:
        - Delete created vm, volume, image, flavor

    """

    LOG.tc_step("Boot a vm using the flavor with guest heartbeat")
    vm_name = 'vm_with_hb'
    vm_id = vm_

    LOG.tc_step('Determine which compute the vm is on')
    compute_name = nova_helper.get_vm_host(vm_id)

    LOG.tc_step("Verify vm heartbeat is on by checking the heartbeat process")
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        exitcode, output = vm_ssh.exec_cmd("ps -ef | grep heartbeat | grep -v grep")
        assert (output is not None)

    LOG.tc_step("Set the voting criteria in the vm: touch /tmp/vote_no_to_reboot")
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        vm_ssh.exec_cmd("touch /tmp/vote_no_to_reboot")

    LOG.tc_step("Verify that attempts to soft reboot the VM is not allowed")
    time.sleep(10)
    with host_helper.ssh_to_host('controller-0') as cont_ssh:
        exitcode, output = cli.nova('reboot', vm_id, ssh_client=cont_ssh, auth_info=Tenant.ADMIN, rtn_list=True, fail_ok=True)
        assert ('action-rejected' in output)

    LOG.tc_step("Verify that attempts to hard reboot the VM is not allowed")
    time.sleep(10)
    with host_helper.ssh_to_host('controller-0') as cont_ssh:
        exitcode, output = cli.nova('reboot --hard', vm_id, ssh_client=cont_ssh, auth_info=Tenant.ADMIN, rtn_list=True, fail_ok=True)
        assert ('action-rejected' in output)

    LOG.tc_step("Remove the /tmp/vote_no_to_reboot file")
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        vm_ssh.exec_cmd("rm /tmp/vote_no_to_reboot")

    LOG.tc_step("Verify the VM can be rebooted")
    time.sleep(10)
    with host_helper.ssh_to_host('controller-0') as cont_ssh:
        exitcode, output = cli.nova('reboot', vm_id, ssh_client=cont_ssh, auth_info=Tenant.ADMIN, rtn_list=True, fail_ok=False)

    time.sleep(30)
    events_tab = system_helper.get_events_table()
    reasons = table_parser.get_values(events_tab, 'Reason Text', strict=False, **{'Entity Instance ID': vm_id})
    assert re.search('Reboot complete for instance .* now enabled on host', '\n'.join(reasons)), \
        "Was not able to reboot VM even though voting is removed"

    time.sleep(30)

    LOG.tc_step("Verify the VM can be hard rebooted")
    time.sleep(10)
    with host_helper.ssh_to_host('controller-0') as cont_ssh:
        exitcode, output = cli.nova('reboot --hard', vm_id, ssh_client=cont_ssh, auth_info=Tenant.ADMIN, rtn_list=True,
                                    fail_ok=False)

    time.sleep(30)
    events_tab = system_helper.get_events_table()
    reasons = table_parser.get_values(events_tab, 'Reason Text', strict=False, **{'Entity Instance ID': vm_id})
    assert re.search('Reboot complete for instance .* now enabled on host', '\n'.join(reasons)), \
        "Was not able to reboot VM even though voting is removed"







