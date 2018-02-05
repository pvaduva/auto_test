"""
This file contains CEPH-related storage test cases.
"""

import random
import time
import ast
import re

from pytest import mark
from utils import cli, exceptions, table_parser
from utils.ssh import ControllerClient
from utils.tis_log import LOG
from utils.multi_thread import Events
from keywords import nova_helper, vm_helper, host_helper, system_helper, \
    storage_helper, glance_helper, cinder_helper
from consts.cgcs import EventLogID, GuestImages
from testfixtures.recover_hosts import HostsToRecover
from testfixtures.fixture_resources import ResourceCleanup

PROC_RESTART_TIME = 30          # number of seconds between process restarts


# Tested on PV1.  Runtime: 278.40  Date: Aug 2nd, 2017.  Status: Pass
@mark.nightly
@mark.usefixtures('ceph_precheck')
def _test_ceph_osd_process_kill():
    """
    us69932_tc1_ceph_osd_process_kill from us69932_ceph_monitoring.odt

    Verify that ceph osd processes recover when they are killed.

    Args:
        - Nothing

    Setup:
        - Requires system with storage nodes

    Test Steps:
        1.  Run CEPH pre-check fixture to check:
            - system has storage nodes
            - health of the ceph cluster is okay
            - that we have OSDs provisioned
        2.  Determine how many OSDs we have provisioned
        3.  Randomly pick one OSD and get the pid of the OSD process
        4.  Kill the ceph-osd PID for that OSD
        5.  Take the OSD out of service (ceph osd out, ceph osd down, ceph osd
        rm)
        6.  Verify expected alarms are raised
        7.  Re-add OSD via 'ceph osd create'
        8.  Wait for alarms to clear
        9.  Ensure ceph-osd process is running again

    Potential flaws:
        1.  We're not checking if unexpected alarms are raised (TODO).  If we
        do this, that means tests cannot run concurrently.

    Teardown:
        - None

    Notes:
        - Updated procedure for CGTS-6464

    """
    con_ssh = ControllerClient.get_active_controller()

    LOG.tc_step('Determine which OSDs to kill')
    osd_id = random.randint(0, storage_helper.get_num_osds(con_ssh) - 1)

    LOG.info('We will kill the process of OSD ID {}'.format(osd_id))

    LOG.tc_step('Determine host of OSD ID {}'.format(osd_id))
    osd_host, msg = storage_helper.get_osd_host(osd_id, con_ssh)
    assert osd_host, msg
    LOG.info(msg)

    LOG.tc_step('Determine the storage group for host {}'.format(osd_host))
    storage_group, msg = storage_helper.get_storage_group(osd_host)
    LOG.info(msg)

    LOG.tc_step('Determine the pid of OSD ID {}'.format(osd_id))
    osd_pid, msg = storage_helper.get_osd_pid(osd_host, str(osd_id))
    assert osd_pid, msg
    LOG.info(msg)

    LOG.tc_step('Kill the OSD process')
    proc_killed, msg = storage_helper.kill_process(osd_host, osd_pid)
    assert proc_killed, msg
    LOG.info(msg)

    with host_helper.ssh_to_host(osd_host) as host_ssh:
        LOG.tc_step('Take OSD {} out of service'.format(osd_id))
        cmd = 'ceph osd out {}'.format(osd_id)
        rc, out = host_ssh.exec_cmd(cmd)
        assert rc == 0, "Unable to take OSD out of service"

        LOG.tc_step('Bring OSD {} down'.format(osd_id))
        cmd = 'ceph osd down {}'.format(osd_id)
        rc, out = host_ssh.exec_cmd(cmd)
        msg = "Unable to bring down the OSD"
        assert rc == 0, msg

        LOG.tc_step('Remove OSD {}'.format(osd_id))
        cmd = 'ceph osd rm {}'.format(osd_id)
        rc, out = host_ssh.exec_cmd(cmd)
        msg = "Unable to remove the OSD"
        assert rc == 0, msg

    LOG.tc_step('Check for loss of replication alarm in group {}'.format(storage_group))
    assert system_helper.wait_for_alarm(alarm_id=EventLogID.STORAGE_LOR, timeout=180)[0], "Alarm {} not raised".format(EventLogID.STORAGE_LOR)
    
    LOG.tc_step('Check for ceph health warning alarm')
    assert system_helper.wait_for_alarm(alarm_id=EventLogID.STORAGE_ALARM_COND, timeout=180)[0], "Alarm {} not raised".format(EventLogID.STORAGE_ALARM_COND)

    LOG.tc_step('Check for OSD failure alarm')
    entity_instance = 'host={}.process=ceph (osd.{}'.format(osd_host, osd_id)
    events = system_helper.wait_for_alarm(alarm_id=EventLogID.STORAGE_DEGRADE, entity_id=entity_instance, timeout=180)

    LOG.tc_step('Put the OSD {} back in service'.format(osd_id))
    cmd = 'ceph osd create 5'.format(osd_id)
    rc, out = con_ssh.exec_cmd(cmd)
    msg = "Unable to start the OSD"
    assert rc == 0, msg

    LOG.tc_step('Check the OSD process is restarted with a different pid')
    endtime = time.time() + 300
    osd_pid2 = osd_pid
    while time.time() < endtime:
        osd_pid2, msg = storage_helper.get_osd_pid(osd_host, osd_id)
        if osd_pid2 != osd_pid:
            time.sleep(5)  # Process might still be initializing
            break
        time.sleep(1)
    msg = 'Process did not restart in time'
    assert osd_pid2 != osd_pid, msg

    LOG.info('Old pid is {} and new pid is {}'.format(osd_pid, osd_pid2))

    LOG.tc_step('Check that loss of replication alarm in group {} alarm clears'.format(storage_group))
    assert system_helper.wait_for_alarm_gone(alarm_id=EventLogID.STORAGE_LOR, timeout=300), "Alarm {} not cleared".format(EventLogID.STORAGE_LOR)
    
    LOG.tc_step('Check that ceph health warning clears')
    assert system_helper.wait_for_alarm_gone(alarm_id=EventLogID.STORAGE_ALARM_COND, timeout=300), "Alarm {} not cleared".format(EventLogID.STORAGE_ALARM_COND) 

    LOG.tc_step('Check the OSD failure alarm clears')
    entity_instance = 'host={}.process=ceph (osd.{}'.format(osd_host, osd_id)
    assert system_helper.wait_for_alarm_gone(alarm_id=EventLogID.STORAGE_DEGRADE, entity_id=entity_instance, timeout=300), "Alarm {} not cleared".format(EventLogID.STORAGE_DEGRADE)


@mark.parametrize('monitor', [
    mark.nightly('controller-0'),
    'controller-1',
    'storage-0'])
# Tested on PV0.  Runtime: 222.34 seconds.  Date: Aug 4, 2017  Status: Pass
@mark.usefixtures('ceph_precheck')
def test_ceph_mon_process_kill(monitor):
    """
    us69932_tc2_ceph_mon_process_kill from us69932_ceph_monitoring.odt

    Verify that ceph mon processes recover when they are killed.

    Args:
        - Nothing

    Setup:
        - Requires system with storage nodes

    Test Steps:
        1.  Run CEPH pre-check fixture to check:
            - system has storage nodes
            - health of the ceph cluster is okay
            - that we have OSDs provisioned
        2.  Pick one ceph monitor and remove it from the quorum 
        3.  Kill the monitor process
        4.  Check that the appropriate alarms are raised
        5.  Restore the monitor to the quorum
        6.  Check that the alarms clear
        7.  Ensure the ceph monitor is restarted under a different pid

    Potential flaws:
        1.  We're not checking if unexpected alarms are raised (TODO)

    Teardown:
        - None

    What defects this addresses:
        1.  CGTS-2975

    """
    LOG.tc_step('Get process ID of ceph monitor')
    mon_pid, msg = storage_helper.get_mon_pid(monitor)

    with host_helper.ssh_to_host(monitor) as host_ssh:
        with host_ssh.login_as_root() as root_ssh:

            LOG.tc_step('Remove the monitor')
            cmd = 'ceph mon remove {}'.format(monitor)
            rc, out = root_ssh.exec_cmd(cmd)

            LOG.tc_step('Stop the ceph monitor')
            cmd = 'service ceph stop mon.{}'.format(monitor)
            rc, out = root_ssh.exec_cmd(cmd)

    LOG.tc_step('Check that ceph monitor failure alarm is raised')
    assert system_helper.wait_for_alarm(alarm_id=EventLogID.STORAGE_DEGRADE, timeout=300)[0], "Alarm {} not raised".format(EventLogID.STORAGE_DEGRADE)

    with host_helper.ssh_to_host(monitor) as host_ssh:
        with host_ssh.login_as_root() as root_ssh:
            LOG.tc_step('Get cluster fsid')
            cmd = 'ceph fsid'
            fsid = host_ssh.exec_cmd(cmd)[0]
            ceph_conf = '/etc/ceph/ceph.conf'

            LOG.tc_step('Remove old ceph monitor directory')
            cmd = 'rm -rf /var/lib/ceph/mon/ceph-{}'.format(monitor)
            rc, out = root_ssh.exec_cmd(cmd)

            LOG.tc_step('Re-add the monitor')
            cmd = 'ceph-mon -i {} -c {} --mkfs --fsid {}'.format(monitor, ceph_conf, fsid)
            rc, out = root_ssh.exec_cmd(cmd)

    LOG.tc_step('Check the ceph storage alarm condition clears')
    assert system_helper.wait_for_alarm_gone(alarm_id=EventLogID.STORAGE_DEGRADE, timeout=360), "Alarm {} not cleared".format(EventLogID.STORAGE_DEGRADE)

    LOG.tc_step('Check the ceph-mon process is restarted with a different pid')
    for i in range(0, PROC_RESTART_TIME):
        mon_pid2, msg = storage_helper.get_mon_pid(monitor)
        if mon_pid2 != mon_pid:
            break
        time.sleep(1)
    msg = 'Process did not restart in time'
    assert mon_pid2 != mon_pid, msg
    LOG.info('Old pid is {} and new pid is {}'.format(mon_pid, mon_pid2))


# Testd on PV0.  Ruentime: 1899.93 seconds.  Date: Aug 4, 2017.  Status: Pass
@mark.usefixtures('ceph_precheck')
@mark.domain_sanity
def test_ceph_reboot_storage_node():
    """
    us69932_tc2_ceph_mon_process_kill from us69932_ceph_monitoring.odt

    Verify that ceph mon processes recover when they are killed
    nodes.

    Args:
        - Nothing

    Setup:
        - Requires system with storage nodes

    Test Steps:
        0.  Run CEPH pre-check fixture to check:
            - system has storage nodes
            - health of the ceph cluster is okay
            - that we have OSDs provisioned
        1.  Delete existing VMs
        2.  Boot new VMs and run dd on them
        3.  Reboot storage node and ensure both:
            - mon state goes down (if storage-0)
            - OSD state goes down
        4.  Ensure mon and OSD state recover afterwards
        5.  Cleanup VMs

    Potential rework:
        1.  Add the alarms checks for raise and clear
        2.  Maybe we don't want to reboot all storage nodes

    What defects this addresses:
        1.  CGTS-2975

    Update:
        This test was updated for the Storage and Robustness feature.
    """
    con_ssh = ControllerClient.get_active_controller()

    LOG.tc_step("Delete existing VMs")
    vm_helper.delete_vms()

    LOG.tc_step("Boot various VMs")
    vms = vm_helper.boot_vms_various_types(cleanup="function")

    vm_threads = []
    LOG.tc_step("SSH to VMs and write to disk")
    end_event = Events("End dd in vms")

    try:
        for vm in vms:
            vm_thread = vm_helper.write_in_vm(vm, end_event=end_event, expect_timeout=40)
            vm_threads.append(vm_thread)

        storage_nodes = system_helper.get_storage_nodes(con_ssh)

        for host in storage_nodes:
            LOG.tc_step('Reboot {}'.format(host))
            HostsToRecover.add(host, scope='function')
            results = host_helper.reboot_hosts(host, wait_for_reboot_finish=False)
            host_helper.wait_for_host_states(host, availability='offline')
            LOG.tc_step("Results: {}".format(results))          # yang TODO log added to keyword, still needed?

            LOG.tc_step('Check health of CEPH cluster')
            end_time = time.time() + 10
            while time.time() < end_time:
                ceph_healthy, msg = storage_helper.is_ceph_healthy(con_ssh)
                if not ceph_healthy:
                    break
            assert not ceph_healthy, msg
            LOG.info(msg)

            LOG.tc_step('Check that OSDs are down')
            osd_list = storage_helper.get_osds(host, con_ssh)
            all_osds_up = True
            up_list = osd_list.copy()
            end_time = time.time() + 60
            while time.time() < end_time and all_osds_up:
                for osd_id in osd_list:
                    osd_up = storage_helper.is_osd_up(osd_id, con_ssh)
                    if not osd_up:
                        msg = 'OSD ID {} is down as expected'.format(osd_id)
                        LOG.info(msg)
                        up_list.remove(osd_id)
                if len(up_list) > 0:
                    osd_list = up_list.copy()
                else:
                    msg = ' All OSDs are down as expected'
                    LOG.info(msg)
                    all_osds_up = False

            assert not all_osds_up, " One or more OSD(s) {}  is(are) up but should be down".format(up_list)

            host_helper.wait_for_host_states(host, availability='available')

            LOG.tc_step('Check that OSDs are up')
            osd_list = storage_helper.get_osds(host, con_ssh)
            down_list = osd_list.copy()
            all_osds_up = False
            end_time = time.time() + 60
            while time.time() < end_time and not all_osds_up:
                for osd_id in osd_list:
                    osd_up = storage_helper.is_osd_up(osd_id, con_ssh)
                    if osd_up:
                        msg = 'OSD ID {} is up as expected'.format(osd_id)
                        LOG.info(msg)
                        down_list.remove(osd_id)
                if len(down_list) > 0:
                    osd_list = down_list.copy()
                else:
                    msg = ' All OSDs are up as expected'
                    LOG.info(msg)
                    all_osds_up = True

            assert all_osds_up, " One or more OSD(s) {}  is(are) down but should be up".format(down_list)

            LOG.tc_step('Check health of CEPH cluster')
            end_time = time.time() + 40
            while time.time() < end_time:
                ceph_healthy, msg = storage_helper.is_ceph_healthy(con_ssh)
                if ceph_healthy is True:
                    break

            assert ceph_healthy, msg

        for vm_thread in vm_threads:
            assert vm_thread.res is True, "Writing in vm stopped unexpectedly"

    except:
        raise
    finally:
        end_event.set()
        for vm_thread in vm_threads:
            vm_thread.wait_for_thread_end(timeout=20)

    LOG.tc_step("Delete existing VMs")
    vm_helper.delete_vms()


# Tested on PV0.  Runtime: 2770.23 seconds sec.  Date: Aug 4, 2017  Status: # Pass
@mark.parametrize('host', ['any', 'storage-0'])
@mark.usefixtures('ceph_precheck')
def test_lock_stor_check_osds_down(host):
    """
    This test is adapted from
    us69932_tc3_ceph_mon_maintenance_operations from us69932_ceph_monitoring.odt

    The goal of this test is to check that all OSDs go down on a locked storage
    node.  There are two variants:

    1.  Lock 'storage-0' which is a ceph monitor
    2.  Lock a storage node that is not 'storage-0', i.e. not a ceph monitor

    Args:
        - None

    Setup:
        - Requires system with storage nodes

    Test Steps:
        1.  Lock storage node
        2.  Check
            - CEPH cluster is in HEALTH_WARN
            - Ensure all OSDs on the locked storage node are down
            - Check that the appropriate alarms are raised:
        3.  Unlock storage node
            - ensure CEPH is HEALTH_OK
            - ensure all OSDs on unlocked node are up
            - Check that alarms are cleared

    Note: If the storage node to be locked is monitor, we also expect to see
    the mon down alarm.

    What defects this addresses:
        1.  CGTS-2609 - Ceph processes fail to start after storage node reboot

    Notes:
        - Updated test to write to disk to add I/O load on system

    """

    con_ssh = ControllerClient.get_active_controller()

    if host == 'any':
        storage_nodes = host_helper.get_hosts(personality='storage')
        LOG.info('System has {} storage nodes:'.format(storage_nodes))
        storage_nodes.remove('storage-0')
        node_id = random.randint(0, len(storage_nodes) - 1)
        host = storage_nodes[node_id]

    LOG.tc_step("Delete existing VMs")
    vm_helper.delete_vms()

    LOG.tc_step("Boot various VMs")
    vms = vm_helper.boot_vms_various_types(cleanup="function")

    vm_threads = []
    LOG.tc_step("SSH to VMs and write to disk")
    end_event = Events("End dd in vms")
    try:
        for vm in vms:
            vm_thread = vm_helper.write_in_vm(vm, end_event=end_event, expect_timeout=40)
            vm_threads.append(vm_thread)

        LOG.tc_step('Lock storage node {}'.format(host))
        HostsToRecover.add(host)
        host_helper.lock_host(host, check_first=False)

        LOG.tc_step('Determine the storage group for host {}'.format(host))
        storage_group, msg = storage_helper.get_storage_group(host)
        LOG.info(msg)

        LOG.tc_step('Check that host lock alarm is raised when {} is locked'.format(host))
        assert system_helper.wait_for_alarm(alarm_id=EventLogID.HOST_LOCK, entity_id=host, strict=False)[0], \
            "Alarm {} not raised".format(EventLogID.HOST_LOCK)

        LOG.tc_step('Check health of CEPH cluster')
        ceph_healthy, msg = storage_helper.is_ceph_healthy(con_ssh)
        assert not ceph_healthy, msg
        LOG.info(msg)

        LOG.tc_step('Check that OSDs are down')
        osd_list = storage_helper.get_osds(host, con_ssh)
        for osd_id in osd_list:
            osd_up = storage_helper.is_osd_up(osd_id, con_ssh)
            msg = 'OSD ID {} is up but should be down'.format(osd_id)
            assert not osd_up, msg
            msg = 'OSD ID {} is down as expected'.format(osd_id)
            LOG.info(msg)

        LOG.tc_step('Check that loss of replication alarm is raised')
        assert system_helper.wait_for_alarm(alarm_id=EventLogID.STORAGE_LOR)[0], \
            "Alarm {} not raised".format(EventLogID.STORAGE_LOR)

        LOG.tc_step('Check that ceph is in health warn')
        assert system_helper.wait_for_alarm(alarm_id=EventLogID.STORAGE_ALARM_COND)[0], \
            "Alarm {} not raised".format(EventLogID.STORAGE_ALARM_COND)

        # We're waiting 5 minutes for ceph rebalancing to be performed
        # DO NOT REMOVE.  This is part of the test.
        time.sleep(300)

        LOG.tc_step('Unlock storage node')
        rtn_code, out = host_helper.unlock_host(host)
        assert rtn_code == 0, out

        health = False
        end_time = time.time() + 40
        while time.time() < end_time:
            health = storage_helper.is_ceph_healthy(con_ssh)
            if health is True:
                break
        assert health, "Ceph did not become healthy"

        LOG.tc_step('Check that host lock alarm is cleared when {} is unlocked'.format(host))
        assert system_helper.wait_for_alarm_gone(EventLogID.HOST_LOCK, entity_id=host, strict=False), \
            "Alarm {} not cleared".format(EventLogID.HOST_LOCK)

        LOG.tc_step('Check that the replication group alarm is cleared')
        assert system_helper.wait_for_alarm_gone(EventLogID.STORAGE_LOR), \
            "Alarm {} not cleared".format(EventLogID.STORAGE_LOR)
        LOG.tc_step('Check that the Storage Alarm Condition is cleared')
        assert system_helper.wait_for_alarm_gone(EventLogID.STORAGE_ALARM_COND), \
            "Alarm {} not cleared".format(EventLogID.STORAGE_ALARM_COND)

        LOG.tc_step('Check OSDs are up after unlock')
        for osd_id in osd_list:
            osd_up = storage_helper.is_osd_up(osd_id, con_ssh)
            msg = 'OSD ID {} should be up but is not'.format(osd_id)
            assert osd_up, msg

        LOG.tc_step('Check health of CEPH cluster')
        end_time = time.time() + 40
        while time.time() < end_time:
            ceph_healthy, msg = storage_helper.is_ceph_healthy(con_ssh)
            if ceph_healthy is True:
                break

        for vm_thread in vm_threads:
            assert vm_thread.res is True, "Writing in vm stopped unexpectedly"
    except:
        raise
    finally:
        # wait_for_thread_end needs to be called even if test failed in the middle, otherwise thread will not end
        end_event.set()
        for vm_thread in vm_threads:
            vm_thread.wait_for_thread_end(timeout=20)

    LOG.tc_step("Delete existing VMs")
    vm_helper.delete_vms()


# Tested on PV1.  Runtime: 762.41 secs  Date: Aug 2nd, 2017.  Status: Pass
@mark.usefixtures('ceph_precheck')
def test_lock_cont_check_mon_down():
    """
    This test is adapted from
    us69932_tc3_ceph_mon_maintenance_operations from us69932_ceph_monitoring.odt

    The goal of this test is to check that we alarm when a CEPH monitor goes
    down.  This test is specifically for controller hosts.

    Args:
        - None

    Setup:
        - Requires system with storage nodes

    Test Steps:
        1.  Lock controller node
        2.  Check
            - CEPH cluster is in HEALTH_WARN
            - Ensure all OSDs stay up
            - Check that the appropriate alarms are raised:
              - controller-X is locked
              - ceph mon down
        3.  Unlock controller node
            - ensure CEPH is HEALTH_OK
            - Check that alarms are cleared

    Enhancements:
       1.  Should we do both controllers?  This will require a swact.
    """

    con_ssh = ControllerClient.get_active_controller()

    host = system_helper.get_standby_controller_name()
    LOG.tc_step('Lock standby controller node {}'.format(host))
    HostsToRecover.add(host, scope='function')
    rtn_code, out = host_helper.lock_host(host)
    assert rtn_code == 0, out

    LOG.tc_step('Check that storage degrade alarm is raised when {} is locked'.format(host))
    assert system_helper.wait_for_alarm(alarm_id=EventLogID.STORAGE_ALARM_COND)[0], \
        "Alarm {} not raised".format(EventLogID.STORAGE_ALARM_COND)

    LOG.tc_step('Check that host lock alarm is raised when {} is locked'.format(host))
    assert system_helper.wait_for_alarm(alarm_id=EventLogID.HOST_LOCK, entity_id=host)[0], \
        "Alarm {} not raised".format(EventLogID.HOST_LOCK)

    LOG.tc_step('Check OSDs are still up after lock')
    osd_list = storage_helper.get_osds(con_ssh=con_ssh)
    for osd_id in osd_list:
        osd_up = storage_helper.is_osd_up(osd_id, con_ssh)
        msg = 'OSD ID {} should be up but is not'.format(osd_id)
        assert osd_up, msg
        msg = 'OSD ID {} is up'.format(osd_id)
        LOG.info(msg)

    LOG.tc_step('Unlock standby controller node {}'.format(host))
    rtn_code, out = host_helper.unlock_host(host, available_only=True)
    assert rtn_code == 0, out

    LOG.tc_step('Check that the host locked alarm is cleared')
    assert system_helper.wait_for_alarm_gone(EventLogID.HOST_LOCK, entity_id=host), \
        "Alarm {} not cleared".format(EventLogID.HOST_LOCK)

    LOG.tc_step('Check that the Storage Alarm Condition is cleared')
    assert system_helper.wait_for_alarm_gone(EventLogID.STORAGE_ALARM_COND), \
        "Alarm {} not cleared".format(EventLogID.STORAGE_ALARM_COND)

    LOG.tc_step('Check health of CEPH cluster')
    health = False
    end_time = time.time() + 40
    while time.time() < end_time:
        ceph_healthy, msg = storage_helper.is_ceph_healthy(con_ssh)
        if ceph_healthy:
            break
    assert ceph_healthy, msg


# Tested on PV1.  Runtime: 1212.55 secs Date: Aug 2nd, 2017.  Status: Pass
@mark.usefixtures('ceph_precheck')
def test_storgroup_semantic_checks():
    """
    This test validates CEPH semantic checks as it applies to storage nodes in
    a replication group.

    Args:
        - None

    Setup:
        - Requires a system with storage nodes (minimum of 2)
        - Requires TiS Release 3 and up

    Test Steps:
        1.  Lock one storage node in a storage node pair
        2.  Check the appropriate alarms are raised
        3.  Check OSDs are down on the storage node
        4.  Check that CEPH is no longer healthy
        5.  Attempt to lock the other node and ensure it is rejected
        6.  Attempt to force lock the other node and ensure it is rejected
        7.  If the storage node is a storage monitor, attempt to lock and force
            lock the controllers
        8.  Unlock the storage node in the storage node pair
        9.  Check that the alarms are cleared
        10.  Check that OSDs are up
        11.  Check that CEPH is healthy

    Defects this addresses:
        1.  CGTS-4286 Unexpected allowing lock action on storage node peergroup
            when redundancy lost
        2.  CGTS-3494 Some OSDs observed to be up on locked storage node
        3.  CGTS-3643 Able to lock standby controller despite only two CEPH
            monitors being available
        4.  CGTS-2690 Storage: Force locking a controller should be rejected when storage
            is locked.
    """

    con_ssh = ControllerClient.get_active_controller()
    storage_nodes = system_helper.get_storage_nodes(con_ssh)
    LOG.info("The following storage hosts are on the system: {}".format(storage_nodes))

    for host in storage_nodes:
        peers = host_helper.get_hostshow_values(host, 'peers')
        peers = ast.literal_eval(list(peers.values())[0])
        hosts = peers['hosts']
        hosts.remove(host)
        storage_group = peers['name']

        LOG.tc_step('Lock {} in the {} group:'.format(host, storage_group))
        HostsToRecover.add(host, scope='function')
        rtn_code, out = host_helper.lock_host(host)
        assert rtn_code == 0, out

        LOG.tc_step("Verify CEPH cluster health reflects the OSD being down")
        ceph_healthy, msg = storage_helper.is_ceph_healthy(con_ssh)
        assert not ceph_healthy, msg

        LOG.tc_step('Check that alarms are raised when {} is locked'.format(host))
        assert system_helper.wait_for_alarm(alarm_id=EventLogID.HOST_LOCK, entity_id=host)[0], \
            "Alarm {} not raised".format(EventLogID.HOST_LOCK)

        LOG.tc_step('Check that OSDs are down')
        osd_list = storage_helper.get_osds(host, con_ssh)
        for osd_id in osd_list:
            osd_up = storage_helper.is_osd_up(osd_id, con_ssh)
            msg = 'OSD ID {} is up but should be down'.format(osd_id)
            assert not osd_up, msg
            msg = 'OSD ID {} is down as expected'.format(osd_id)
            LOG.info(msg)

        LOG.tc_step('Check that loss of replication alarm is raise')
        assert system_helper.wait_for_alarm(alarm_id=EventLogID.STORAGE_LOR)[0], \
            "Alarm {} not raised".format(EventLogID.STORAGE_LOR)

        LOG.tc_step('Check that the ceph health warning alarm is raised')
        assert system_helper.wait_for_alarm(alarm_id=EventLogID.STORAGE_ALARM_COND)[0], \
            "Alarm {} not raised".format(EventLogID.STORAGE_ALARM_COND)

        if host == 'storage-0':
            hosts.append('controller-0')
            hosts.append('controller-1')

        for node in hosts:
            LOG.tc_step('Attempt to lock the {}'.format(node))
            HostsToRecover.add(node)
            rtn_code, out = host_helper.lock_host(node, fail_ok=True)
            assert 1 == rtn_code, out

            LOG.tc_step('Attempt to force lock {}'.format(node))
            rtn_code, out = host_helper.lock_host(node, force=True, fail_ok=True)
            assert 1 == rtn_code, out

        LOG.tc_step('Unlock storage host {}'.format(host))
        rtn_code, out = host_helper.unlock_host(host)
        assert rtn_code == 0, out

        LOG.info("Check if alarms have cleared")
        assert system_helper.wait_for_alarm_gone(EventLogID.HOST_LOCK, entity_id=host), \
            "Alarm {} not cleared".format(EventLogID.HOST_LOCK)
        assert system_helper.wait_for_alarm_gone(EventLogID.STORAGE_LOR), \
            "Alarm {} not cleared".format(EventLogID.STORAGE_LOR)
        assert system_helper.wait_for_alarm_gone(EventLogID.STORAGE_ALARM_COND), \
            "Alarm {} not cleared".format(EventLogID.STORAGE_ALARM_COND)

        LOG.tc_step('Check health of CEPH cluster')
        ceph_healthy, msg = storage_helper.is_ceph_healthy(con_ssh)
        assert ceph_healthy, msg

        LOG.tc_step('Check OSDs are up after unlock')
        for osd_id in osd_list:
            osd_up = storage_helper.is_osd_up(osd_id, con_ssh)
            msg = 'OSD ID {} should be up but is not'.format(osd_id)
            assert osd_up, msg


# Tested on PV0.  
@mark.usefixtures('ceph_precheck')
def test_import_with_cache_raw():
    """
    Verify that non-RAW format images, e.g. QCOW2, can be imported into glance
    using --cache-raw.

    This is US68056_tc1_import_with_cache_raw adapted from
    us68056_glance_backend_to_storage_node.odt

    Args:
    - None

    Setup:
        - Requires a system with storage nodes
        - Requires external connectivity to download images

    Test Steps:
        1.  Download a QCOW2 image
        2.  Import into glance using --cache-raw
        3.  Check the image file and the raw file are in rbd
        4.  Create a volume from the imported image
        5.  Launch a VM from volume
        6.  Launch a VM from image
        7.  Delete created:
            - VMs
            - volumes
            - glance images
        8.  Check rbd files are cleaned up

    Flaws:
        1.  Image names need more uniqueness

    Defects:
        1.  CGTS-3605 glance import --cache-raw should have an option to wait
        until RAW image is available
    """
    con_ssh = ControllerClient.get_active_controller()

    img_dest = '~/images'
    size = 10
    vm_list = []

    # Return a list of images of a given type
    LOG.tc_step('Determine what qcow2 images we have available')
    image_names = storage_helper.find_images(con_ssh)

    if not image_names:
        LOG.info('No qcow2 images were found on the system')
        LOG.tc_step('Downloading qcow2 image(s)... this will take some time')
        glance_helper._scp_guest_image()
        image_names = storage_helper.find_images(con_ssh)

    LOG.tc_step('Import qcow2 images into glance')
    for image in image_names:
        source_image_loc = img_dest + "/" + image
        img_name = 'testimage_{}'.format(image)
        ret = glance_helper.create_image(source_image_file=source_image_loc,
                                         disk_format='qcow2',
                                         container_format='bare',
                                         cache_raw=True, wait=True)
        ResourceCleanup.add('image', ret[1])
        LOG.info("ret {}".format(ret))
        assert ret[0] == 0, ret[2]
        end_time = time.time() + 30
        LOG.tc_step("Wait for image to finish RAW caching")
        while time.time() < end_time:
            cached = glance_helper.get_image_properties(ret[1], 'cache_raw_status')
            if cached['cache_raw_status'] == 'Cached':
                break
        else:
            assert 1 == 0, "The QCOW2 image did not finish caching"

        LOG.tc_step('Check image is shown in rbd')
        rbd_img_id = ret[1]
        rbd_raw_img_id = rbd_img_id + '_raw'
        cmd = 'rbd -p images ls'
        rtn_code, out = con_ssh.exec_cmd(cmd, expect_timeout=60)
        LOG.info("out {}:".format(out))
        msg = '{} was not found in rbd image pool'.format(rbd_img_id)
        assert rbd_img_id in out, msg
        msg = '{} was not found in rbd image pool'.format(rbd_raw_img_id)
        assert rbd_raw_img_id in out, msg

        # Check how large of a flavor the image requires
        flav_size = storage_helper.find_image_size(con_ssh, image)

        LOG.tc_step('Create volume from the imported image')
        volume_id = cinder_helper.create_volume(name=img_name,
                                                image_id=rbd_img_id,
                                                size=flav_size,
                                                con_ssh=con_ssh,
                                                rtn_exist=False)[1]
        msg = "Unable to create volume"
        assert volume_id, msg

        LOG.tc_step('Create flavor of sufficient size for VM')
        flv = nova_helper.create_flavor(name=img_name, root_disk=size)
        ResourceCleanup.add('flavor', flv[1])
        assert flv[0] == 0, flv[1]

        LOG.tc_step('Launch VM from created volume')
        vm_id = vm_helper.boot_vm(name=img_name, flavor=flv[1], source='volume', source_id=volume_id,
                                  cleanup='function')[1]
        vm_list.append(vm_id)

        # When spawning, make sure we don't download the image
        LOG.tc_step('Launch VM from image')
        img_name2 = img_name + '_fromimage'
        vm_id2 = vm_helper.boot_vm(name=img_name2, flavor=flv[1], source='image', source_id=rbd_img_id,
                                   cleanup='function')[1]
        vm_list.append(vm_id2)

        LOG.tc_step('Delete VMs {}'.format(vm_list))
        vm_helper.delete_vms(vms=vm_list, con_ssh=con_ssh)

        LOG.tc_step('Delete Flavor(s) {}'.format(flv[1]))
        nova_helper.delete_flavors(flv[1])

        LOG.tc_step('Delete Image(s) {}'.format(rbd_img_id))
        glance_helper.delete_images(rbd_img_id)

        # We're doing this twice, extract to function
        LOG.tc_step('Check images are cleaned up from rbd')
        cmd = 'rbd -p images ls'
        rtn_code, out = con_ssh.exec_cmd(cmd, expect_timeout=60)
        msg = '{} was found in rbd image pool'.format(rbd_img_id)
        assert rbd_img_id not in out, msg
        msg = '{} was found in rbd image pool'.format(rbd_raw_img_id)
        assert rbd_raw_img_id not in out, msg


@mark.usefixtures('ceph_precheck')
def test_import_raw_with_cache_raw():
    """
    Verify that RAW format images can be imported with --cache-raw but there is
    no corresponding _raw image in rbd.

    This is US68056_tc2_neg_import_RAW_with_cache_raw_enabled adapted from
    us68056_glance_backend_to_storage_node.odt

    Args:
    - None

    Setup:
        - Requires a system with storage nodes
        - Requires external connectivity to download images

    Test Steps:
        1.  Import the cgcs-guest image into glance with --cache-raw specified
        2.  Confirm:
            - The image is imported successfully
            - There is no corresponding _raw image in rbd
            - In Horizon, RAW cache state should be set to disabled
        3.  Ensure you can launch a VM from image using the imported image
        4.  Ensure you can launch a VM from volume using the imported image
    """
    con_ssh = ControllerClient.get_active_controller()

    # Return a list of images of a given type
    LOG.tc_step('Determine what raw images we have available')
    image_names = storage_helper.find_images(con_ssh, image_type='raw')

    if not image_names:
        LOG.info('No raw images were found on the controller')
        LOG.tc_step('Rsyncing images from controller-0')
        rsync_images = 'rsync -avr -e "ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no " {} ' \
                       'controller-1:{}'.format(GuestImages.IMAGE_DIR, GuestImages.IMAGE_DIR)
        con_ssh.exec_cmd(rsync_images)
        image_names = storage_helper.find_images(con_ssh, image_type='raw')
        msg = 'No images found on controller'
        assert image_names, msg

    LOG.tc_step('Import raw images into glance with --cache-raw')
    for image in image_names:
        source_image_loc = GuestImages.IMAGE_DIR + '/' + image
        ret = glance_helper.create_image(source_image_file=source_image_loc,
                                         disk_format='raw',
                                         container_format='bare',
                                         cache_raw=True)
        ResourceCleanup.add('image', ret[1])
        LOG.info("ret {}".format(ret))
        assert ret[0] == 0, ret[2]

        LOG.tc_step('Check image is shown in rbd but no raw file is generated')
        rbd_img_id = ret[1]
        rbd_raw_img_id = rbd_img_id + '_raw'
        cmd = 'rbd -p images ls'
        rtn_code, out = con_ssh.exec_cmd(cmd, expect_timeout=60)
        LOG.info("out {}:".format(out))
        msg = '{} was not found in rbd image pool'.format(rbd_img_id)
        assert rbd_img_id in out, msg
        msg = '{} was found in rbd image pool'.format(rbd_raw_img_id)
        assert rbd_raw_img_id not in out, msg

    #TODO: Clean up resources used


# INPROGRESS
# Blocked due to product issue CGTS-7694 (uses cache-raw)
@mark.usefixtures('ceph_precheck', 'ubuntu14_image')
def _test_exceed_size_of_img_pool():
    """
    Verify that system behaviour when we exceed the size of the rbd image pool.

    This is US68056_tc3_neg_exceed_size_of_image_pool adapted from
    us68056_glance_backend_to_storage_node.odt

    Args:
    - None

    Setup:
        - Requires a system with storage nodes
        - Requires external connectivity to download images

    Test Steps:
        1. Fill up the ceph img pool
        2. Ensure the system alarms
    """

    con_ssh = ControllerClient.get_active_controller()

    # Return a list of images of a given type
    LOG.tc_step('Determine what qcow2 images we have available')
    image_names = storage_helper.find_images(con_ssh)
    
    if not image_names:
        LOG.info('No qcow2 images were found on the system')
        LOG.tc_step('Downloading qcow2 image(s)... this will take some time')
        glance_helper._scp_guest_image()
        image_names = storage_helper.find_images(con_ssh)

    LOG.tc_step('Import qcow2 images into glance until pool is full')
    source_img_path = "{}/{}".format(GuestImages.IMAGE_DIR, GuestImages.IMAGE_FILES['ubuntu_14'][2])

    timeout = 7200
    end_time = time.time() + timeout
    while time.time() < end_time:
        code, image_id = glance_helper.create_image(source_image_file=source_img_path,
                                                    disk_format='qcow2',
                                                    container_format='bare',
                                                    cache_raw=True, wait=True)
        ResourceCleanup.add('image', image_id)

        if code != 0:
            break
    else:
        raise exceptions.TimeoutException("Timed out (2 hours) filling out image pool.")

    # 800.001   Storage Alarm Condition: Pgs are degraded/stuck/blocked.
    # Please check 'ceph -s' for more details
    LOG.tc_step('Query alarms for ceph alarms')
    assert system_helper.wait_for_alarm(alarm_id=EventLogID.STORAGE_ALARM_COND), "Alarm {} not raised"\
        .format(EventLogID.STORAGE_ALARM_COND)

    LOG.tc_step('Verify the health cluster is not healthy')         # yang TODO verify healthy or unhealthy?
    ceph_healthy, msg = storage_helper.is_ceph_healthy(con_ssh)
    assert ceph_healthy, msg


# Blocked due to product issue CGTS-7694
@mark.usefixtures('ceph_precheck')
def _test_import_large_images_with_cache_raw():
    """
    Verify that system behaviour when we attempt to import large images, i.e.
    20-40GB, with cache-raw enabled.

    This is US68056_tc4_import_large_images_with_cache_raw
    us68056_glance_backend_to_storage_node.odt

    Args:
    - None

    Setup:
        - Requires a system with storage nodes

    Test Steps:
        1.  Determine if we have a cgcs-guest.img and if not, rsync from the
        other controller
        2.  Use qemu-img resize to enlarge an existing cgcs-guest image
        3.  Use qemu-img convert to convert the raw image into qcow2
        4.  Import image into glance with --cache-raw specified
        5.  Ensure the image is imported successfully
        6.  Create a flavor of sufficient size for the image
        6.  Using the image, create a volume
        7.  Launch a VM from volume
        8.  Launch a VM from image
        9.  Cleanup flavors and VMs
    """

    con_ssh = ControllerClient.get_active_controller()
    img = 'cgcs-guest'
    glance_helper.get_guest_image(guest_os=img)

    base_img = img + '.img'
    qcow2_img = img + '.qcow2'
    new_img = '40GB' + base_img
    new_img_loc = GuestImages.IMAGE_DIR + '/' + new_img
    vm_list = []

    # Check that we have the cgcs-guest.img available
    # If we are on controller-1, we may need to rsync image files from
    # controller-0
    LOG.tc_step('Determine if the cgcs-guest image is available')
    image_names = storage_helper.find_images(con_ssh, image_type='all')
    if base_img not in image_names:
        LOG.tc_step('Rsyncing images from controller-0')
        rsync_images = 'rsync -avr -e "ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no " {} ' \
                       'controller-1:{}'.format(GuestImages.IMAGE_DIR, GuestImages.IMAGE_DIR)
        con_ssh.exec_cmd(rsync_images)
        image_names = storage_helper.find_images(con_ssh)
        msg = '{} was not found in {}'.format(base_img, GuestImages.IMAGE_DIR)
        assert base_img in image_names, msg

    # Resize the image to 40GB
    LOG.tc_step('Resize the cgcs-guest image to 40GB')
    cmd = 'cp {}/{} {}/{}'.format(GuestImages.IMAGE_DIR, base_img, GuestImages.IMAGE_DIR, new_img)
    rtn_code, out = con_ssh.exec_cmd(cmd)
    assert not rtn_code, out
    cmd = 'qemu-img resize {} -f raw 40G'.format(new_img_loc)
    rtn_code, out = con_ssh.exec_cmd(cmd, expect_timeout=600)
    assert not rtn_code, out

    # Confirm the virtual size is 40GB
    size = storage_helper.find_image_size(con_ssh, image_name=new_img)
    msg = 'Image was not resized to 40GB'
    assert str(size) == '40', msg

    # Convert the image to qcow2
    LOG.tc_step('Convert the raw image to qcow2')
    args = '{}/{} {}/{}'.format(GuestImages.IMAGE_DIR, new_img, GuestImages.IMAGE_DIR, qcow2_img)
    cmd = 'qemu-img convert -f raw -O qcow2' + ' ' + args
    con_ssh.exec_cmd(cmd, expect_timeout=600)

    # Check the image type is updated
    image_names = storage_helper.find_images(con_ssh, image_type='qcow2')
    msg = 'qcow2 image was not found in {}'.format(GuestImages.IMAGE_DIR)
    assert qcow2_img in image_names, msg

    LOG.tc_step('Import image into glance')
    source_img = GuestImages.IMAGE_DIR + '/' + qcow2_img
    out = glance_helper.create_image(source_image_file=source_img,
                                     disk_format='qcow2',
                                     container_format='bare',
                                     cache_raw=True, wait=True)
    ResourceCleanup.add('image', out[1])
    msg = 'Failed to import {} into glance'.format(qcow2_img)
    assert out[0] == 0, msg

    LOG.tc_step('Create volume from the imported image')
    volume_id = cinder_helper.create_volume(name=qcow2_img,
                                            image_id=out[1],
                                            size=40,
                                            con_ssh=con_ssh,
                                            rtn_exist=False)[1]
    msg = "Unable to create volume"
    assert volume_id, msg

    LOG.tc_step('Create flavor of sufficient size for VM')
    flv = nova_helper.create_flavor(name=qcow2_img, root_disk=size)
    ResourceCleanup.add('flavor', flv[1])
    assert flv[0] == 0, flv[1]

    LOG.tc_step('Launch VM from created volume')
    vm_id = vm_helper.boot_vm(name=qcow2_img, flavor=flv[1], source='volume', source_id=volume_id,
                              cleanup='function')[1]
    vm_list.append(vm_id)

    # When spawning, make sure we don't download the image
    LOG.tc_step('Launch VM from image')
    img_name2 = qcow2_img + '_fromimage'
    vm_id2 = vm_helper.boot_vm(name=img_name2, flavor=flv[1], source='image', source_id=out[1], cleanup='function')[1]
    vm_list.append(vm_id2)

    # yang TODO use ResourceCleanup in case of test fail.
    LOG.tc_step('Delete VMs {}'.format(vm_list))
    vm_helper.delete_vms(vms=vm_list, con_ssh=con_ssh)

    LOG.tc_step('Delete Flavor(s) {}'.format(flv[1]))
    nova_helper.delete_flavors(flv[1])

    LOG.tc_step('Delete Image(s) {}'.format(out[1]))
    glance_helper.delete_images(out[1])


# Tested on PV0.  Runtime: 58.82 seconds.  Status: Pass  Date: Aug 8, 2017
@mark.usefixtures('ceph_precheck')
def test_modify_ceph_pool_size():
    """
    Verify that the user can modify the size of the ceph images pool.

    This is US68056_tc5_modify_ceph_pool_size adapted from
    us68056_glance_backend_to_storage_node.odt

    Args:
    - None

    Assumptions:
    - Cinder-volumes is the largest pool

    Setup:
        - Requires a system with storage nodes

    Test Steps:
        1.  Determine the current size of the ceph image pool
        2.  Modify the sizes of all ceph pools (object pool only if swift is
        enabled) 
        3.  Confirm the pool size has been increased both in sysinv and
        underlying ceph
    """

    con_ssh = ControllerClient.get_active_controller()

    LOG.tc_step('Query the size of the CEPH storage pools')
    glance_pool, cinder_pool, ephemeral_pool, object_pool, ceph_total_space, object_gateway = \
        storage_helper.get_storage_backend_show_vals(backend='ceph', fields=(
            'glance_pool_gib', 'cinder_pool_gib', 'ephemeral_pool_gib', 'object_pool_gib',
            'ceph_total_space_gib', 'object_gateway'))

    LOG.info("Current pool values: Glance {}, Cinder {}, Ephemeral {}, Object {}".format(glance_pool, cinder_pool,
                                                                                         ephemeral_pool, object_pool))

    new_glance_pool = glance_pool + 10
    new_ephemeral_pool = ephemeral_pool + 10

    if not object_gateway:
        LOG.info("Swift is disabled so we won't modify the object pool")
        new_object_pool = 0
        new_cinder_pool = cinder_pool - 20
        LOG.tc_step("Modifying pools: Glance {}, Cinder {}, Ephemeral {}".
                    format(new_glance_pool, new_cinder_pool, new_ephemeral_pool))
        rc, out = storage_helper.modify_storage_backend('ceph', ephemeral=str(new_ephemeral_pool),
                                                        cinder=str(new_cinder_pool), glance=str(new_glance_pool),
                                                        lock_unlock=False)
    else:
        new_object_pool = object_pool + 10
        new_cinder_pool = cinder_pool - 30
        LOG.tc_step("Modifying pools: Glance {}, Cinder {}, Ephemeral {}, Object {}".
                    format(new_glance_pool, new_cinder_pool, new_ephemeral_pool, new_object_pool))
        rc, out = storage_helper.modify_storage_backend('ceph', ephemeral=str(new_ephemeral_pool),
                                                        cinder=str(new_cinder_pool), glance=str(new_glance_pool),
                                                        object_gib=str(new_object_pool), lock_unlock=False)
    assert rc == 0, out

    LOG.info('Check the ceph images pool is set to the right value')
    glance_pool2, cinder_pool2, ephemeral_pool2, object_pool2, ceph_total_space2, object_gateway2 = \
        storage_helper.get_storage_backend_show_vals(backend='ceph', fields=(
            'glance_pool_gib', 'cinder_pool_gib', 'ephemeral_pool_gib', 'object_pool_gib',
            'ceph_total_space_gib', 'object_gateway'))

    assert glance_pool2 == new_glance_pool, "Glance pool should be {} but is {}".\
        format(new_glance_pool, glance_pool2)
    assert cinder_pool2 == new_cinder_pool, "Cinder pool should be {} but is {}".\
        format(new_cinder_pool, cinder_pool2)
    assert ephemeral_pool2 == new_ephemeral_pool, "Ephemeral pool should be {} but is {}".\
        format(new_ephemeral_pool, ephemeral_pool2)
    assert object_pool2 == new_object_pool, "Object pool should be {} but is {}".format(new_object_pool, object_pool2)

    LOG.tc_step("Pool values after modification: Glance {}, Cinder {}, Ephemeral {}, Object {}".
                format(glance_pool2, cinder_pool2, ephemeral_pool2, object_pool2))

    LOG.tc_step("Check ceph pool information")
    cmd = "ceph osd pool get-quota {}"
    max_bytes_regex = "max bytes.*([0-9]*)(.B)$"

    newcmd = cmd.format('images')
    rc, out = con_ssh.exec_cmd(newcmd)
    max_bytes = re.search(max_bytes_regex, out)
    assert max_bytes
    ceph_glance_pool = int(max_bytes.group(1))
    if max_bytes.group(2) == 'MB':
        ceph_glance_pool /= 1000

    newcmd = cmd.format('cinder-volumes')
    rc, out = con_ssh.exec_cmd(newcmd)
    max_bytes = re.search(max_bytes_regex, out)
    assert max_bytes
    ceph_cinder_pool = int(max_bytes.group(1))
    if max_bytes.group(2) == 'MB':
        ceph_cinder_pool /= 1000

    newcmd = cmd.format('ephemeral')
    rc, out = con_ssh.exec_cmd(newcmd)
    max_bytes = re.search(max_bytes_regex, out)
    assert max_bytes
    ceph_ephemeral_pool = int(max_bytes.group(1))
    if max_bytes.group(2) == 'MB':
        ceph_ephemeral_pool /= 1000

    if object_gateway:
        newcmd = cmd.format('default.rgw.buckets.data')
        rc, out = con_ssh.exec_cmd(newcmd)
        max_bytes = re.search(max_bytes_regex, out)
        assert max_bytes
        ceph_object_pool = int(max_bytes.group(1))
        if max_bytes.group(2) == 'MB':
            ceph_object_pool /= 1000
        LOG.info("Ceph pool values after modification: Glance {}, Cinder {}, Ephemeral {}, Object {}".format(
                ceph_glance_pool, ceph_cinder_pool, ceph_ephemeral_pool, ceph_object_pool))
    else:
        ceph_object_pool = 0
        LOG.info("Ceph pool values after modification: Glance {}, Cinder {}, Ephemeral {}".format(
                ceph_glance_pool, ceph_cinder_pool, ceph_ephemeral_pool))

    # Set margin of error to some reasonable value to account for unit
    # conversion and rounding errors
    moe = 3

    LOG.info("Margin of error is set to {}".format(moe))

    assert new_glance_pool - moe <= ceph_glance_pool <= new_glance_pool + moe, \
        "Glance pool should be {} but is {}".format(new_glance_pool, ceph_glance_pool)
    assert new_cinder_pool - moe <= ceph_cinder_pool <= new_cinder_pool + moe, \
        "Cinder pool should be {} but is {}".format(new_cinder_pool, ceph_cinder_pool)
    assert new_ephemeral_pool - moe <= ceph_ephemeral_pool <= new_ephemeral_pool + moe, \
        "Ephemeral pool should be {} but is {}".format(new_ephemeral_pool, ceph_ephemeral_pool)
    assert new_object_pool - moe <= ceph_object_pool <= new_object_pool + moe, \
        "Object pool should be {} but is {}".format(new_object_pool, ceph_object_pool)
