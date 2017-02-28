import re
import time
import random
from pytest import mark, skip, fixture

from utils.tis_log import LOG
from utils.multi_thread import MThread, Events

from consts.cgcs import FlavorSpec, ServerGroupMetadata, VMStatus
from consts.reasons import SkipReason
from consts.cli_errs import SrvGrpErr
from keywords import nova_helper, vm_helper, system_helper
from testfixtures.resource_mgmt import ResourceCleanup


MSG = 'HELLO SRV GRP MEMBERS!'


@fixture(scope='module', autouse=True)
def check_system(add_cgcsauto_zone, add_admin_role_module):
    storage_backing, hosts = nova_helper.get_storage_backing_with_max_hosts()

    is_simplex = system_helper.is_simplex()
    if is_simplex:
        hosts_to_add = hosts
    elif len(hosts) >= 2:
        hosts_to_add = hosts[:2]
    else:
        skip(SkipReason.LESS_THAN_TWO_HYPERVISORS)
        hosts_to_add = []

    LOG.fixture_step("Add hosts to cgcsauto aggregate: {}".format(hosts_to_add))
    nova_helper.add_hosts_to_aggregate('cgcsauto', hosts_to_add)

    def remove_():
        LOG.fixture_step("Remove hosts from cgcsauto aggregate: {}".format(hosts_to_add))
        nova_helper.remove_hosts_from_aggregate('cgcsauto', hosts_to_add)

    return is_simplex, hosts_to_add, storage_backing


def create_flavor_and_server_group(storage_backing, srv_grp_msging=None, policy=None, group_size=None,
                                   best_effort=None):
    LOG.tc_step("Create a flavor with server group messaging set to {}".format(srv_grp_msging))
    flavor_id = nova_helper.create_flavor('srv_grp', check_storage_backing=False, storage_backing=storage_backing)[1]
    ResourceCleanup.add('flavor', resource_id=flavor_id)

    srv_grp_msg_flv = False
    if srv_grp_msging is not None:
        srv_grp_msg_flv = True if 'true' in srv_grp_msging.lower() else False
        nova_helper.set_flavor_extra_specs(flavor_id, **{FlavorSpec.SRV_GRP_MSG: srv_grp_msg_flv})

    srv_grp_id = None
    if policy is not None:

        LOG.tc_step("Create a server group with policy set to {}".format(policy))
        srv_grp_id = nova_helper.create_server_group(policy=policy)[1]
        ResourceCleanup.add(resource_type='server_group', resource_id=srv_grp_id)

        metadata = {}
        if group_size is not None:
            metadata[ServerGroupMetadata.GROUP_SIZE] = group_size
        if best_effort is not None:
            metadata[ServerGroupMetadata.BEST_EFFORT] = best_effort

        LOG.tc_step("Add server group metadata: {}".format(metadata))
        nova_helper.set_server_group_metadata(srv_grp_id, **metadata)

    return flavor_id, srv_grp_msg_flv, srv_grp_id


@mark.parametrize(('srv_grp_msging', 'policy', 'group_size', 'best_effort', 'vms_num'), [
    mark.priorities('nightly', 'domain_sanity')((None, 'affinity', 4, None, 2)),
    mark.domain_sanity((None, 'anti_affinity', 3, True, 3)),
    mark.nightly(('srv_grp_msg_true', 'anti_affinity', 4, None, 3)),    # negative res for last vm
    ('srv_grp_msg_true', 'affinity', 2, True, 2)
])
def test_server_group_boot_vms(srv_grp_msging, policy, group_size, best_effort, vms_num, check_system):
    """
    Test server group policy and messaging

    Args:
        srv_grp_msging (str): server group messaging flavor spec
        policy (str): server group policy to set when creating the group
        group_size (int): group size metadata to set for server group
        best_effort (bool): best effort metadata to set for server group
        vms_num (int): number of vms to boot

    Setups:
        - Add admin role to tenant under test (module)
        - Add two hosts to cgcsauto zone to limit the vms on two hosts only; add one if simplex system detected (module)

    Test Steps:
        - Create a server group with given policy
        - Add given metadata to above server group
        - Boot vm(s) with above server group
        - Verify vm(s) booted successfully and is a member of the server group
        - If server_group_messaging is on, then verify
            - vms receive srv grp msg sent from other vm
            - vms receive notification when other vm is paused
        - If server group messaging is off, verify server_group_app is not included in vm

    Teardown:
        - Delete created vms, flavor, server group
        - Remove cgcsauto hosts from aggregate  (module)
        - Remove admin role from tenant under test  (module)

    """
    is_simplex, cgcsauto_hosts, storage_backing = check_system
    if is_simplex and policy == 'anti_affinity' and not best_effort:
        skip("Skip anti_affinity strict for simplex system")

    flavor_id, srv_grp_msg_flv, srv_grp_id = create_flavor_and_server_group(storage_backing, srv_grp_msging, policy,
                                                                            group_size, best_effort)

    vm_hosts = []
    members = []
    failed_num = 0
    if policy == 'anti_affinity' and not best_effort and vms_num > 2:
        failed_num = vms_num - 2
        vms_num = 2

    LOG.tc_step("Boot {} vm(s) with flavor {} in server group {} and ensure they are successfully booted.".
                format(flavor_id, srv_grp_id, vms_num))

    for i in range(vms_num):
        code, vm_id, err, vol = vm_helper.boot_vm(name='srv_grp', flavor=flavor_id, hint={'group': srv_grp_id},
                                                  avail_zone='cgcsauto', fail_ok=True)
        ResourceCleanup.add(resource_type='vm', resource_id=vm_id, del_vm_vols=False)
        ResourceCleanup.add('volume', vol)
        assert 0 == code, "VM is not booted successfully. Details: {}".format(err)

        LOG.tc_step("Check vm {} is in server group {}".format(vm_id, srv_grp_id))
        members = eval(nova_helper.get_server_groups_info(srv_grp_id, header='Members')[0])
        assert vm_id in members, "VM {} is not a member of server group {}".format(vm_id, srv_grp_id)

        vm_hosts.append(nova_helper.get_vm_host(vm_id))

    for i in range(failed_num):
        LOG.tc_step("Boot vm{} in server group {} that's expected to fail".format(i, srv_grp_id))
        code, vm_id, err, vol = vm_helper.boot_vm(name='srv_grp', flavor=flavor_id, hint={'group': srv_grp_id},
                                                  avail_zone='cgcsauto', fail_ok=True)
        ResourceCleanup.add(resource_type='vm', resource_id=vm_id, del_vm_vols=False)
        ResourceCleanup.add('volume', vol)

        nova_helper.get_vm_nova_show_value(vm_id, 'fault')
        assert 1 == code, "Boot vm is not rejected"

    unique_vm_hosts = list(set(vm_hosts))
    if policy == 'affinity' or is_simplex:
        assert 1 == len(unique_vm_hosts)

    else:
        assert len(unique_vm_hosts) >= 2

    assert len(members) == vms_num

    vm_to_ssh = members[0]
    another_vm = members[1]

    vm_helper.wait_for_vm_pingable_from_natbox(vm_to_ssh)
    vm_helper.wait_for_vm_pingable_from_natbox(another_vm)

    if srv_grp_msg_flv:
        LOG.tc_step("Check server group message can be sent/received among group members")
        check_server_group_messaging_enabled(vms=members, action='message')

        LOG.tc_step("Check server group message received when a member is paused")
        check_server_group_messaging_enabled(vms=members, action='pause')
    else:
        LOG.tc_step("Check server group message is not enabled")
        check_server_group_messaging_disabled(vms=members)


def _wait_for_srv_grp_msg(vm_id, msg, timeout, event):
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        vm_ssh.send('server_group_app')
        # vm_ssh.expect('\r\n\r\n', timeout=1, searchwindowsize=100)

        end_time = time.time() + timeout
        while time.time() < end_time:
            code = vm_ssh.expect('\r\n\r\n', fail_ok=True, timeout=timeout)
            if code < 0:
                assert False, "No more server group notification received. Expected msg not found."

            current_output = vm_ssh.cmd_output
            if re.search(msg, current_output):
                event.set()
                vm_ssh.send_control('c')
                vm_ssh.expect(searchwindowsize=100, timeout=5)
                break
        else:
            assert False, "Expected msg did not appear within timeout"


def trigger_srv_grp_msg(vm_id, action, timeout=60, event=None):
    if action == 'message':
        _send_srv_grp_msg(vm_id=vm_id, msg=MSG, timeout=timeout, event=event)
    elif action == 'pause':
        vm_helper.pause_vm(vm_id=vm_id)


def _send_srv_grp_msg(vm_id, msg, timeout, event):
    with vm_helper.ssh_to_vm_from_natbox(vm_id, close_ssh=False) as sender_ssh:
        sender_ssh.send("server_group_app '{}'".format(msg))
        sender_ssh.expect('\r\n\r\n')
        if event is None:
            time.sleep(timeout)
        else:
            event.wait_for_event(timeout=timeout, fail_ok=True)


def check_server_group_messaging_enabled(vms, action):
    vms = list(set(vms))
    vm_sender = random.choice(vms)
    vms.remove(vm_sender)

    if action == 'message':
        msg = MSG
        timeout = 90
    elif action == 'pause':
        msg = '{}.*paused'.format(vm_sender)
        timeout = 180
    else:
        raise ValueError("Unknown action - '{}' provided".format(action))

    res_event = Events("srv group messaging result")
    vm_threads = []

    for vm in vms:
        new_thread = MThread(_wait_for_srv_grp_msg, vm, msg, timeout, res_event)
        new_thread.start_thread(timeout=timeout+30)
        vm_threads.append(new_thread)

    time.sleep(5)
    # this 60 seconds timeout is hardcoded for action == 'message' scenario to send the message out
    sender_thread = MThread(trigger_srv_grp_msg, vm_sender, action, 60, res_event)
    sender_thread.start_thread(timeout=timeout)

    for vm_thr in vm_threads:
        vm_thr.wait_for_thread_end()

    sender_thread.wait_for_thread_end()


def check_server_group_messaging_disabled(vms):
    for vm in vms:
        with vm_helper.ssh_to_vm_from_natbox(vm) as vm_ssh:
            code, output = vm_ssh.exec_cmd("server_group_app", fail_ok=True)
            assert code > 0


@mark.parametrize(('policy', 'group_size', 'best_effort', 'min_count', 'max_count'), [
    mark.p2(('affinity', 3, False, 3, 4)),
    mark.p2(('affinity', 2, True, 3, 4)),
    mark.p2(('anti_affinity', 3, True, 3, None)),
    mark.p2(('anti_affinity', 4, None, 3, None)),    # negative res for last vm
    mark.p2(('anti_affinity', 3, False, 1, 3))
    # ('affinity', 2, True, 2)
])
def test_server_group_launch_vms_in_parallel(policy, group_size, best_effort, min_count, max_count, check_system):
    """
    Test launch vms with server group in parallel using min_count, max_count param in nova boot

    Args:
        policy (str): affinity or anti_affinity
        group_size (int): max vms in server group
        best_effort (bool|None): best_effort flag to set
        min_count (int):
        max_count (int|None):
        check_system (tuple): test fixture

    Setups:
        - Add admin role to tenant under test (module)
        - Add two hosts to cgcsauto zone to limit the vms on two hosts only; add one if simplex system detected (module)

    Test Steps
        - Create a server group with given server group policy, group size and best effort flag
        - Create a flavor with storage backing supported by cgcsauto hosts
        - Boot a vm from image using above flavor and in above server group
        - Verify:
            - VMs status are as expected
            - Number of vms booted are as expected
            - All vms are in specified server group even if boot failed

    Teardown:
        - Delete created vms, flavor, server group
        - Remove cgcsauto hosts from aggregate  (module)
        - Remove admin role from tenant under test  (module)

    """
    is_simplex, cgcsauto_hosts, storage_backing = check_system
    if is_simplex and policy == 'anti_affinity' and not best_effort:
        skip("Skip anti_affinity strict for simplex system")

    flavor_id, srv_grp_msg_flv, srv_grp_id = create_flavor_and_server_group(storage_backing, None, policy, group_size,
                                                                            best_effort)

    LOG.tc_step("Boot vms with {} server group policy and min/max count".format(policy))
    code, vms, msg = vm_helper.boot_vm(name='srv_grp_parallel', flavor=flavor_id, hint={'group': srv_grp_id},
                                       avail_zone='cgcsauto', fail_ok=True, min_count=min_count, max_count=max_count)
    ResourceCleanup.add('vm', vms)

    if max_count is None:
        max_count = min_count

    if min_count > group_size:
        LOG.tc_step("Check vms failed to boot when min_count > group_size")
        assert 1 == code, msg
        assert max_count == len(vms)

        expt_err = SrvGrpErr.EXCEEDS_GRP_SIZE.format(srv_grp_id, group_size)
        for vm in vms:
            fault = nova_helper.get_vm_fault_message(vm)
            assert expt_err in fault

    elif policy == 'anti_affinity' and not best_effort and min_count > 2:
        LOG.tc_step("Check anti-affinity strict vms failed to boot when min_count > hosts_count")
        assert 1 == code, msg
        expt_err = SrvGrpErr.HOST_UNAVAIL_ANTI_AFFINITY
        for vm in vms:
            fault = nova_helper.get_vm_fault_message(vm)
            assert expt_err in fault

    elif policy == 'anti_affinity' and not best_effort and max_count > 2:
        LOG.tc_step("Check anti-affinity strict vms_count=host_count when min_count <= hosts_count <= max_count")
        assert 0 == code, msg
        assert 2 == len(vms), "VMs number is not the same as qualified hosts number"

    elif max_count > group_size:
        LOG.tc_step("Check vms_count=group_size when min_count <= group_size <= max_count")
        assert 0 == code, msg
        assert group_size == len(vms), "Expecting vms booted is the same as server group size due to max count " \
                                       "larger than group size."
    else:
        LOG.tc_step("Check vms_count=max_count when max_count <= group_size and no other constrains")
        assert 0 == code, msg
        assert max_count == len(vms), "Expecting vms booted is the same as max count when max count <= group size"

    # if code == 0:
    LOG.tc_step("Check vms are in server group {}: {}".format(srv_grp_id, vms))
    members = eval(nova_helper.get_server_groups_info(srv_grp_id, header='Members')[0])
    assert set(vms) <= set(members), "Some vms are not in srv group"


