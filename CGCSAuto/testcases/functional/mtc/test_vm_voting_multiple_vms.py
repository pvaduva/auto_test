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
    ResourceCleanup.add('flavor', flavor_id, scope='module')

    extra_specs = {FlavorSpec.GUEST_HEARTBEAT: 'True'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    def delete_flavor():
        nova_helper.delete_flavors(flavor_ids=flavor_id, fail_ok=True)

    request.addfinalizer(delete_flavor)
    return flavor_id


@fixture(scope='module')
def vms_(request, flavor_):

    vm_name1 = 'test-hb-vote-migrate'
    vm_name2 = 'test-hb-vote-reboot'
    vm_name3 = 'test-hb-vote-stop-start'
    vm_name4 = 'test-no-hb-vote-migrate'
    inst_names = [vm_name1, vm_name2, vm_name3, vm_name4]

    flavor_id = flavor_
    vm_ids = []
    # for idx in range(len(inst_names) - 1):
    #     vm_id = vm_helper.boot_vm(name=inst_names[idx], flavor=flavor_id)[1]
    #     time.sleep(30)
    #     vm_ids.append(vm_id)
    #     ResourceCleanup.add('vm', vm_id, del_vm_vols=True, scope='module')
    #
    # vm_id = vm_helper.boot_vm(name=inst_names[3])[1]
    # time.sleep(30)
    # vm_ids.append(vm_id)
    # ResourceCleanup.add('vm', vm_id, del_vm_vols=True, scope='module')
    vm_id = vm_helper.boot_vm(name=vm_name3, flavor=flavor_id)[1]
    time.sleep(30)
    vm_ids.append(vm_id)
    ResourceCleanup.add('vm', vm_id, del_vm_vols=True, scope='module')

    # Teardown to remove the vm and flavor
    def remove_vms():
        LOG.fixture_step("Cleaning up vms..")
        for idx in range(len(vm_ids)):
            vm_helper.delete_vms(vm_ids[idx], delete_volumes=True)

    request.addfinalizer(remove_vms)

    return vm_ids


def test_vm_voting_multiple_vms(vms_):
    """
    Test vm voting behavior scales with multiple vms

    Test Steps:
        - Create multiple VMs
        - In each VM, provision different voting behaviour
        - Ensure in each case, the VM behaviour corresponds with its voting settings
        - Create one VM without the heartbeat extension
        - Provision voting behaviour on that VM by touching the desired vote files
        - Ensure the VM behaviour is not impacted by the vote settings

    Teardown:
        - Delete created vm, volume, image, flavor

    """

    vote_no_migrate = "touch /tmp/vote_no_to_migrate"
    vote_no_reboot = "touch /tmp/vote_no_to_reboot"
    vote_no_stop_start = "touch /tmp/vote_no_to_stop"
    voting_list = [vote_no_migrate, vote_no_reboot, vote_no_stop_start]

    vm_ids = vms_
    # vm_id = vm_ids[0]
    #
    # LOG.tc_step("Provision and verify the no migration voting behavior\
    #  for vm: {0:s}".format(vm_id))
    # with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
    #     LOG.tc_step("Verify vm heartbeat is running in vm: %s" % vm_id)
    #     exitcode, output = vm_ssh.exec_cmd("ps -ef | grep heartbeat| grep -v grep")
    #     assert (output is not None)
    #
    #     LOG.tc_step("Set the voting criteria in vm: %s" % vm_id)
    #     vm_ssh.exec_cmd(voting_list[0])
    #
    # LOG.tc_step("Verify that attempts to live migrate the VM is not allowed")
    # time.sleep(10)
    # dest_host = vm_helper.get_dest_host_for_live_migrate(vm_id)
    # return_code, message = vm_helper.live_migrate_vm(vm_id, fail_ok=True, block_migrate=False,
    #                                                  destination_host=dest_host)
    # assert ('action-rejected' in message)
    #
    # LOG.tc_step("Verify that attempts to cold migrate the VM is not allowed")
    # time.sleep(10)
    # return_code, message = vm_helper.cold_migrate_vm(vm_id,fail_ok=True)
    # assert ('action-rejected' in message)
    #
    # vm_id = vm_ids[1]
    # LOG.tc_step("Provision and verify the no reboot voting behavior\
    #  for vm: {0:s}".format(vm_id))
    # with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
    #     LOG.tc_step("Verify vm heartbeat is running in vm: %s" % vm_id)
    #     exitcode, output = vm_ssh.exec_cmd("ps -ef | grep heartbeat | grep -v grep")
    #     assert (output is not None)
    #
    #     LOG.tc_step("Set the no rebooting voting criteria in vm: %s" % vm_id)
    #     vm_ssh.exec_cmd(voting_list[1])
    #
    # LOG.tc_step("Verify that attempts to soft reboot the VM is not allowed")
    # time.sleep(10)
    # with host_helper.ssh_to_host('controller-0') as cont_ssh:
    #     exitcode, output = cli.nova('reboot', vm_id, ssh_client=cont_ssh, auth_info=Tenant.ADMIN, rtn_list=True, fail_ok=True)
    #     assert ('action-rejected' in output)
    #
    # LOG.tc_step("Verify that attempts to hard reboot the VM is not allowed")
    # time.sleep(10)
    # with host_helper.ssh_to_host('controller-0') as cont_ssh:
    #     exitcode, output = cli.nova('reboot --hard', vm_id, ssh_client=cont_ssh, auth_info=Tenant.ADMIN, rtn_list=True, fail_ok=True)
    #     assert ('action-rejected' in output)

    vm_id = vm_ids[0]
    LOG.tc_step("Provision and verify the no stop/start voting behavior\
     for vm: {0:s}".format(vm_id))
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        LOG.tc_step("Verify vm heartbeat is running in vm: %s" % vm_id)
        exitcode, output = vm_ssh.exec_cmd("ps -ef | grep heartbeat | grep -v grep")
        assert (output is not None)

    LOG.tc_step("Set the no stop voting criteria in vm: %s" % vm_id)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        vm_ssh.exec_cmd('touch /tmp/vote_no_to_stop')
        code, out = vm_ssh.exec_cmd('ls /tmp')
        assert out is not None

    LOG.tc_step("Verify that attempts to stop the VM is not allowed")
    time.sleep(10)
    with host_helper.ssh_to_host('controller-0') as cont_ssh:
        exitcode, output = cli.nova('stop', vm_id, ssh_client=cont_ssh, auth_info=Tenant.ADMIN, rtn_list=True, fail_ok=True)
        assert ('Unable to stop the specified server' in output)

    # vm_id = vm_ids[3]
    # LOG.tc_step("Provision the no migration voting behavior\
    #  for vm: {0:s} that has no heartbeat extension".format(vm_id))
    # with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
    #     LOG.tc_step("Verify that no heartbeat is running in the vm: %s" % vm_id)
    #     exitcode, output = vm_ssh.exec_cmd("ps -ef | grep heartbeat | grep -v grep")
    #     assert (output is None)
    #
    #     LOG.tc_step("Set the no migration voting criteria in vm: %s" % vm_id)
    #     vm_ssh.exec_cmd(voting_list[0])
    #
    # LOG.tc_step("Verify that attempts to migrate the VM is allowed")
    # time.sleep(10)
    # dest_host = vm_helper.get_dest_host_for_live_migrate(vm_id)
    # return_code, message = vm_helper.live_migrate_vm(vm_id, fail_ok=True, block_migrate=False,
    #                                                  destination_host=dest_host)
    # assert ('action-rejected' not in message)
    #
    # LOG.tc_step("Verify that attempts to cold migrate the VM is allowed")
    # time.sleep(10)
    # return_code, message = vm_helper.cold_migrate_vm(vm_id, fail_ok=True, revert=False)
    # assert ('action-rejected' not in message)










