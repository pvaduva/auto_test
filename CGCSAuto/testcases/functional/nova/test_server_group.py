import re
import time
import random
from pytest import mark, skip, fixture, param

from utils.tis_log import LOG
from utils.multi_thread import MThread, Events

from consts.cli_errs import SrvGrpErr
from keywords import nova_helper, vm_helper, host_helper
from testfixtures.fixture_resources import ResourceCleanup


MSG = 'HELLO SRV GRP MEMBERS!'


@fixture(scope='module', autouse=True)
def check_system():
    storage_backing, hosts = host_helper.get_storage_backing_with_max_hosts()
    up_hypervisors = host_helper.get_up_hypervisors()
    if not up_hypervisors:
        skip('No up hypervisor on system')

    vm_helper.ensure_vms_quotas(vms_num=10, cores_num=20, vols_num=10)

    return hosts, storage_backing, up_hypervisors


def create_flavor_and_server_group(storage_backing=None, policy=None):
    LOG.tc_step("Create a flavor{}".format(' with {} aggregate'.format(storage_backing) if storage_backing else ''))
    flavor_id = nova_helper.create_flavor('srv_grp', storage_backing=storage_backing, cleanup='function')[1]

    srv_grp_id = None
    if policy is not None:
        LOG.tc_step("Create a server group with policy set to {}".format(policy))
        srv_grp_id = nova_helper.create_server_group(policy=policy)[1]
        ResourceCleanup.add(resource_type='server_group', resource_id=srv_grp_id)

    return flavor_id, srv_grp_id


# TC2915 + TC2915 + TC_6566 + TC2917
# server group messaging is removed since STX
@mark.parametrize(('policy', 'vms_num'), [
    param('affinity', 2, marks=mark.priorities('nightly', 'domain_sanity', 'sx_nightly')),
    ('soft_anti_affinity', 3),
    param('anti_affinity', 2, marks=mark.priorities('nightly', 'domain_sanity')),   # For system with 2+ hypervisors
    ('soft_affinity', 3),
])
def test_server_group_boot_vms(policy, vms_num, check_system):
    """
    Test server group policy and messaging
    Test live migration with anti-affinity server group (TC6566)
    Test changing size of existing server group via CLI (TC2917)

    Args:
        policy (str): server group policy to set when creating the group
        vms_num (int): number of vms to boot

    Test Steps:
        - Create a server group with given policy
        - Add given metadata to above server group
        - Boot vm(s) with above server group
        - Verify vm(s) booted successfully and is a member of the server group
        - Verify that all vms have the server group listed in nova show
        - If more than 1 hypervisor available:
            - Attempt to live/cold migrate one of the vms, and check they succeed/fail based on server group setting

    Teardown:
        - Delete created vms, flavor, server group

    """
    hosts, storage_backing, up_hypervisors = check_system
    host_count = len(hosts)
    if host_count < 2 and policy == 'anti_affinity':
        skip("Skip anti_affinity strict for system with 1 up host in storage aggregate")

    flavor_id, srv_grp_id = create_flavor_and_server_group(storage_backing=storage_backing, policy=policy)
    vm_hosts = []
    members = []
    failed_num = 0
    if policy == 'anti_affinity' and vms_num > host_count:
        failed_num = vms_num - host_count
        vms_num = host_count

    LOG.tc_step("Boot {} vm(s) with flavor {} in server group {} and ensure they are successfully booted.".
                format(vms_num, flavor_id, srv_grp_id))

    for i in range(vms_num):
        vm_id = vm_helper.boot_vm(name='srv_grp', flavor=flavor_id, hint={'group': srv_grp_id},
                                  fail_ok=False, cleanup='function')[1]

        LOG.tc_step("Check vm {} is in server group {}".format(vm_id, srv_grp_id))
        members = nova_helper.get_server_group_info(srv_grp_id, headers='Members')[0]
        assert vm_id in members, "VM {} is not a member of server group {}".format(vm_id, srv_grp_id)

        # Deprecated:
        # server_group_output = nova_helper.get_vm_nova_show_values(vm_id, ['wrs-sg:server_group'])[0]
        # assert srv_grp_id in server_group_output, \
        #     'Server group info does not appear in nova show for vm {}'.format(vm_id)

        vm_hosts.append(vm_helper.get_vm_host(vm_id))

    for i in range(failed_num):
        LOG.tc_step("Boot vm{} in server group {} that's expected to fail".format(i, srv_grp_id))
        code, vm_id, err = vm_helper.boot_vm(name='srv_grp', flavor=flavor_id, hint={'group': srv_grp_id},
                                             fail_ok=True, cleanup='function')

        vm_helper.get_vm_fault_message(vm_id)
        assert 1 == code, "Boot vm is not rejected"

    unique_vm_hosts = list(set(vm_hosts))
    if policy == 'affinity' or host_count == 1:
        assert 1 == len(unique_vm_hosts)
    else:
        assert len(unique_vm_hosts) == min(vms_num, host_count), "Improper VM hosts for anti-affinity policy"

    assert len(members) == vms_num

    for vm in members:
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm)

    if host_count > 1:
        # TC6566 verified here
        expt_fail = policy == 'affinity' or (policy == 'anti_affinity' and host_count-vms_num < 1)

        for action in ('live_migrate', 'cold_migrate'):
            LOG.tc_step("Attempt to {} VMs and ensure it {}".format(action, 'fails' if expt_fail else 'pass'))
            vm_hosts_after_mig = []
            for vm in members:
                code, output = vm_helper.perform_action_on_vm(vm, action=action, fail_ok=True)
                if expt_fail:
                    assert 1 == code, "{} was not rejected. {}".format(action, output)
                else:
                    assert 0 == code, "{} failed. {}".format(action, output)
                vm_host = vm_helper.get_vm_host(vm)
                vm_hosts_after_mig.append(vm_host)
                vm_helper.wait_for_vm_pingable_from_natbox(vm)

            if policy == 'affinity':
                assert len(list(set(vm_hosts_after_mig))) == 1
            elif policy == 'anti_affinity':
                assert len(list(set(vm_hosts_after_mig))) == vms_num, "Some VMs are on same host with " \
                                                                      "strict anti-affinity polity"


def _wait_for_srv_grp_msg(vm_id, msg, timeout, res_events, listener_event, sent_event):
    with vm_helper.ssh_to_vm_from_natbox(vm_id, retry_timeout=60) as vm_ssh:
        vm_ssh.send('server_group_app')
        # vm_ssh.expect('\r\n\r\n', timeout=1, searchwindowsize=100)
        listener_event.set()
        sent_event.wait_for_event()
        received_event = Events("Server group message received on VM {}".format(vm_id))
        res_events.append(received_event)
        end_time = time.time() + timeout
        while time.time() < end_time:
            code = vm_ssh.expect('\r\n\r\n', fail_ok=True, timeout=timeout)
            if code < 0:
                assert False, "No more server group notification received. Expected msg not found."

            current_output = vm_ssh.cmd_output
            if re.search(msg, current_output):
                received_event.set()
                vm_ssh.send_control('c')
                vm_ssh.expect(searchwindowsize=100, timeout=5)
                break
        else:
            assert False, "Expected msg did not appear within timeout"


def trigger_srv_grp_msg(vm_id, action, timeout=60, sent_event=None, rcv_event=None):
    if action == 'message':
        _send_srv_grp_msg(vm_id=vm_id, msg=MSG, timeout=timeout, sent_event=sent_event, rcv_event=rcv_event)
    elif action == 'pause':
        vm_helper.pause_vm(vm_id=vm_id)
        sent_event.set()


def _send_srv_grp_msg(vm_id, msg, timeout, sent_event, rcv_event):
    with vm_helper.ssh_to_vm_from_natbox(vm_id, close_ssh=False) as sender_ssh:
        sender_ssh.send("server_group_app '{}'".format(msg))
        sender_ssh.expect('\r\n\r\n')
        if sent_event:
            sent_event.set()

        if not isinstance(rcv_event, list):
            rcv_event = [rcv_event]

        for event in rcv_event:
            event.wait_for_event(timeout=timeout)


def check_server_group_messaging_enabled(vms, action):
    vms = list(set(vms))
    vm_sender = random.choice(vms)
    vms.remove(vm_sender)

    if action == 'message':
        msg = MSG
        timeout = 180
    elif action == 'pause':
        msg = '{}.*paused'.format(vm_sender)
        timeout = 240
    else:
        raise ValueError("Unknown action - '{}' provided".format(action))

    res_events = []
    sent_event = Events("srv msg/event triggered")
    listener_event = Events("VM started listening to server group messages")
    vm_threads = []
    sender_thread = None

    try:
        for vm in vms:
            listener_event.clear()
            new_thread = MThread(_wait_for_srv_grp_msg, vm, msg, timeout=timeout, res_events=res_events,
                                 listener_event=listener_event, sent_event=sent_event)
            new_thread.start_thread(timeout=timeout+30)
            vm_threads.append(new_thread)
            listener_event.wait_for_event()

        time.sleep(5)
        # this 60 seconds timeout is hardcoded for action == 'message' scenario to send the message out
        sender_thread = MThread(trigger_srv_grp_msg, vm_sender, action, timeout=60, sent_event=sent_event,
                                rcv_event=res_events)
        sender_thread.start_thread(timeout=timeout)

        sent_event.wait_for_event()
        for res_event in res_events:
            res_event.wait_for_event()

    finally:
        # wait for server group msg to be received
        for vm_thr in vm_threads:
            vm_thr.wait_for_thread_end(timeout=30)

        if sender_thread:
            sender_thread.wait_for_thread_end(timeout=30)
            if action == 'pause':
                vm_helper.unpause_vm(vm_sender)


def check_server_group_messaging_disabled(vms):
    for vm in vms:
        with vm_helper.ssh_to_vm_from_natbox(vm) as vm_ssh:
            code, output = vm_ssh.exec_cmd("server_group_app", fail_ok=True)
            assert code > 0


# Deprecated - align with upstream. Remove test to reduce upstream test. anti_affinity with max count will fail.
# TC2913, TC2915
@mark.parametrize(('policy', 'min_count', 'max_count'), [
    # ('soft_affinity', 3, 4),  # TODO: add after cutover to stein
    ('affinity', 3, 4),
    # ('soft_anti_affinity', 3, None),  # TODO: add after cutover to stein
    ('anti_affinity', 1, 3),
])
def _test_server_group_launch_vms_in_parallel(policy, min_count, max_count, check_system):
    """
    Test launch vms with server group in parallel using min_count, max_count param in nova boot

    Args:
        policy (str): affinity or anti_affinity
        check_system (tuple): test fixture

    Test Steps
        - Create a server group with given server group policy, group size and best effort flag
        - Create a flavor with storage backing supported
        - Boot a vm from image using above flavor and in above server group
        - Verify:
            - VMs status are as expected
            - Number of vms booted are as expected
            - All vms are in specified server group even if boot failed

    Teardown:
        - Delete created vms, flavor, server group

    """
    hosts, storage_backing, up_hypervisors = check_system
    host_count = len(up_hypervisors)
    if host_count == 1 and policy == 'anti_affinity':
        skip("Skip anti_affinity strict for system with 1 hypervisor")

    flavor_id, srv_grp_id = create_flavor_and_server_group(policy=policy)

    LOG.tc_step("Boot vms with {} server group policy and min/max count".format(policy))
    code, vms, msg = vm_helper.boot_vm(name='srv_grp_parallel', flavor=flavor_id, hint={'group': srv_grp_id},
                                       fail_ok=True, min_count=min_count, max_count=max_count,
                                       cleanup='function')

    if max_count is None:
        max_count = min_count

    if policy == 'anti_affinity' and min_count > host_count:
        LOG.tc_step("Check anti-affinity strict vms failed to boot when min_count > hosts_count")
        assert 1 == code, msg
        expt_err = SrvGrpErr.HOST_UNAVAIL_ANTI_AFFINITY
        for vm in vms:
            fault = vm_helper.get_vm_fault_message(vm)
            assert expt_err in fault

    elif policy == 'anti_affinity' and max_count > host_count:
        LOG.tc_step("Check anti-affinity strict vms_count=host_count when min_count <= hosts_count <= max_count")
        assert 0 == code, msg
        assert host_count == len(vms), "VMs number is not the same as qualified hosts number"

    else:
        LOG.tc_step("Check vms_count=max_count when policy={} and host_count={}".format(policy, host_count))
        assert 0 == code, msg
        assert max_count == len(vms), "Expecting vms booted is the same as max count when max count <= group size"

    # if code == 0:
    LOG.tc_step("Check vms are in server group {}: {}".format(srv_grp_id, vms))
    members = nova_helper.get_server_group_info(srv_grp_id, headers='Members')[0]
    assert set(vms) <= set(members), "Some vms are not in srv group"
