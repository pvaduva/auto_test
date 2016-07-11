"""
This file contains CEPH-related storage test cases.
"""

import random
import time
import ast

from pytest import mark
from utils import cli, exceptions, table_parser
from utils.ssh import ControllerClient
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, host_helper, system_helper, \
    storage_helper, glance_helper, cinder_helper
from consts.cgcs import EventLogID, IMAGE_DIR

PROC_RESTART_TIME = 30          # number of seconds between process restarts
RESTARTS_BEFORE_ASSERT = 3      # number of process restarts until error assertion

# Runtime: 208 seconds - pass on wildcat-7-12 and PV0
# CGTS-4513 Loss of replication group alarm not always seen
@mark.usefixtures('ceph_precheck')
def test_ceph_osd_process_kill():
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
        4.  Kill the OSD processes
        5.  Verify the process is restarted
        6.  Repeatedly kill processes until error assertion occurs
        7.  Verify the error assertion is cleared and health is restored
        recover.

    Potential flaws:
        1.  We're not checking if unexpected alarms are raised (TODO).  If we
        do this, that means tests cannot run concurrently.
        2.  Cannot test for: brief ceph -s health outages (timing issue)
        3.  Cannot test for: host change in state to degrade (timing issue)

    Teardown:
        - None

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

    # We're doing this twice, move to function
    LOG.tc_step('Check the OSD process is restarted with a different pid')
    endtime = time.time() + PROC_RESTART_TIME
    osd_pid2 = osd_pid
    while time.time() < endtime:
        osd_pid2, msg = storage_helper.get_osd_pid(osd_host, osd_id)
        if osd_pid2 != osd_pid:
            break
        time.sleep(1)
    # yang TODO updated. Better to move to keywords and remove assert altogether
    msg = 'Process did not restart in time'
    assert osd_pid2 != osd_pid, msg

    LOG.info('Old pid is {} and new pid is {}'.format(osd_pid, osd_pid2))

    # Note, there is an impact to ceph health going from HEALTH_OK to
    # HEALTH_WARN but it is too brief to look for.

    LOG.tc_step('Repeatedly kill the OSD process until we alarm')       # yang TODO: Better to add a keyword for this
    for i in range(0, RESTARTS_BEFORE_ASSERT):
        osd_pid, msg = storage_helper.get_osd_pid(osd_host, osd_id)
        assert osd_pid, msg
        proc_killed, msg = storage_helper.kill_process(osd_host, osd_pid)
        assert proc_killed, msg
        for i in range(0, PROC_RESTART_TIME):                   # yang TODO: update func to use while, or rename i
            osd_pid2, msg = storage_helper.get_osd_pid(osd_host, osd_id)
            if osd_pid2 != osd_pid:
                break
            time.sleep(1)
        msg = 'Process did not restart in time'
        assert osd_pid2 != osd_pid, msg
        LOG.info('Old pid is {} and new pid is {}'.format(osd_pid, osd_pid2))

    # Note, we cannot check alarms since the alarms clears too quickly.  Check
    # events instead.

    LOG.tc_step('Check events list for OSD failure')
    entity_instance = 'host={}.process=ceph (osd.{})'.format(osd_host, osd_id)
    system_helper.wait_for_events(30, strict=False, fail_ok=False,
                                  **{'Entity Instance ID': entity_instance,
                                     'Event Log ID': EventLogID.STORAGE_DEGRADE,
                                     'State': 'set'})

    # Loss of replication is too brief to catch
    # Note, the storage host degrade state is so brief that we cannot check
    # for it.

    LOG.tc_step('Check the OSD failure event clears')
    LOG.tc_step('Check events list for OSD failure')
    entity_instance = 'host={}.process=ceph (osd.{})'.format(osd_host, osd_id)
    system_helper.wait_for_events(45, strict=False, fail_ok=False,
                                  **{'Entity Instance ID': entity_instance,
                                     'Event Log ID': EventLogID.STORAGE_DEGRADE,
                                     'State': 'clear'})

    # Give Ceph a bit of time to return to health ok state
    # TODO: Do better than just sleeping
    time.sleep(20)

    LOG.tc_step('Verify the health cluster is healthy')
    ceph_healthy, msg = storage_helper.is_ceph_healthy(con_ssh)
    assert ceph_healthy, msg

# Runtime: 572.98 seconds - pass on PV0
# CGTS-4520 - All ceph monitors observed to be down in alarm-list when 1
# monitor killed
@mark.parametrize('monitor', ['controller-0', 'controller-1', 'storage-0'])
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
        2.  Pick one ceph monitor and get the pid of the monitor process
        3.  Kill the monitor process
        4.  Verify the process is restarted
        5.  Repeatedly kill processes until error assertion occurs
        6.  Check that the appropriate alarms are raised
        7.  Verify the error assertion is cleared and ceph health is restored
        8.  Check that the alarms clear

    Potential flaws:
        1.  We're not checking if unexpected alarms are raised (TODO)
        2.  Cannot test for: brief ceph -s health outages (timing issue)
        3.  Cannot test for: host change in state to degrade (timing issue)

    Teardown:
        - None

    What defects this addresses:
        1.  CGTS-2975

    """
    # TODO: remove
    con_ssh = ControllerClient.get_active_controller()

    LOG.tc_step('Determine the pid of the ceph-mon process on {}'.format(monitor))
    mon_pid, msg = storage_helper.get_mon_pid(monitor)
    assert mon_pid, msg
    LOG.info(msg)

    LOG.tc_step('Kill the OSD process')
    proc_killed, msg = storage_helper.kill_process(monitor, mon_pid)
    assert proc_killed, msg
    LOG.info(msg)

    # We're doing this twice, move to function
    LOG.tc_step('Check the ceph-mon process is restarted with a different pid')
    for i in range(0, PROC_RESTART_TIME):
        mon_pid2, msg = storage_helper.get_mon_pid(monitor)
        if mon_pid2 != mon_pid:
            break
        time.sleep(1)
    msg = 'Process did not restart in time'
    assert mon_pid2 != mon_pid, msg
    LOG.info('Old pid is {} and new pid is {}'.format(mon_pid, mon_pid2))

    # Note, there is an impact to ceph health going from HEALTH_OK to
    # HEALTH_WARN but it is too brief to look for.

    LOG.tc_step('Repeatedly kill the ceph-mon process until we alarm')
    for i in range(0, RESTARTS_BEFORE_ASSERT):
        mon_pid, msg = storage_helper.get_mon_pid(monitor)
        assert mon_pid, msg
        proc_killed, msg = storage_helper.kill_process(monitor, mon_pid)
        assert proc_killed, msg
        for i in range(0, PROC_RESTART_TIME):
            mon_pid2, msg = storage_helper.get_mon_pid(monitor)
            if mon_pid2 != mon_pid:
                break
            time.sleep(1)
        msg = 'Process did not restart in time'
        assert mon_pid2 != mon_pid, msg
        LOG.info('Old pid is {} and new pid is {}'.format(mon_pid, mon_pid2))

    # Note, we cannot check alarms since the alarms clears too quickly.  Check
    # events instead.

    LOG.tc_step('Check events list for ceph monitor failure')
    entity_instance = 'host={}.process=ceph (mon.{})'.format(monitor, monitor)
    system_helper.wait_for_events(30, strict=False, fail_ok=False,
                                  **{'Entity Instance ID': entity_instance,
                                     'Event Log ID':
                                     EventLogID.STORAGE_DEGRADE, 'State':
                                     'set'})

    LOG.tc_step('Check events list for storage alarm condition')
    reason_text = 'Storage Alarm Condition: HEALTH_WARN'
    system_helper.wait_for_events(30, strict=False, fail_ok=False,
                                  **{'Reason Text': reason_text,
                                     'Event Log ID':
                                     EventLogID.STORAGE_ALARM_COND,
                                     'State': 'set'})

    # Note, the storage host degrade state is so brief that we cannot check
    # for it.

    # Sleep to give time for events to clear
    time.sleep(20)

    LOG.tc_step('Check events list for ceph monitor clear')
    entity_instance = 'host={}.process=ceph (mon.{})'.format(monitor,
                                                             monitor)
    system_helper.wait_for_events(45, strict=False, fail_ok=False,
                                  **{'Entity Instance ID': entity_instance,
                                     'Event Log ID':
                                     EventLogID.STORAGE_DEGRADE, 'State':
                                     'clear'})

    LOG.tc_step('Check events list for storage alarm condition')
    reason_text = 'Storage Alarm Condition: HEALTH_WARN'
    system_helper.wait_for_events(45, strict=False, fail_ok=False,
                                  **{'Reason Text': reason_text, 'Event Log ID':
                                     EventLogID.STORAGE_ALARM_COND, 'State':
                                     'clear'})

    # Give Ceph a bit of time to return to health ok state
    # TODO: Do better than just sleeping
    time.sleep(10)

    LOG.tc_step('Verify the health cluster is healthy')
    ceph_healthy, msg = storage_helper.is_ceph_healthy()

# Pass on 700 seconds on PV0
@mark.usefixtures('ceph_precheck')
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
        1.  Run CEPH pre-check fixture to check:
            - system has storage nodes
            - health of the ceph cluster is okay
            - that we have OSDs provisioned
        2.  Reboot storage node and ensure both:
            - mon state goes down (if storage-0)
            - OSD state goes down
        3.  Ensure mon and OSD state recover afterwards

    Potential rework:
        1.  Add the alarms checks for raise and clear
        2.  Maybe we don't want to reboot all storage nodes

    What defects this addresses:
        1.  CGTS-2975
    """
    con_ssh = ControllerClient.get_active_controller()

    storage_nodes = system_helper.get_storage_nodes(con_ssh)

    for host in storage_nodes:
        LOG.tc_step('Reboot {}'.format(host))
        results = host_helper.reboot_hosts(host, wait_for_reboot_finish=False)
        LOG.tc_step("Results: {}".format(results))          # yang TODO log added to keyword, still needed?
        assert results[0] != 0

        LOG.tc_step('Check health of CEPH cluster')
        ceph_healthy, msg = storage_helper.is_ceph_healthy(con_ssh)
        assert not ceph_healthy, msg
        LOG.info(msg)

        # TODO: Alarms that are seen.  Only look for the ceph ones.
        # 1. storage-0 experienced a service-affecting failure. Auto-recovery in
        #    progress. 200.004
        # 2. Loss of replication in replication group group-0: OSDs are down
        #    800.011
        # 3. Storage Alarm Condition: Pgs are degraded/stuck/blocked. Please check
        #    'ceph -s' for more details 800.001
        # 4. storage-0 experienced a service-affecting failure. Auto-recovery in
        #    progress. 200.004
        # 5. storage-1 experienced a persistent critical 'Management Network'
        #    communication failure.
        # 6. storage-1 experienced a persistent critical 'Infrastructure
        #    Network' communication failure.

        LOG.tc_step('Check that OSDs are down')
        osd_list = storage_helper.get_osds(host, con_ssh)
        for osd_id in osd_list:
            osd_up = storage_helper.is_osd_up(osd_id, con_ssh)
            msg = 'OSD ID {} is up but should be down'.format(osd_id)
            assert not osd_up, msg
            msg = 'OSD ID {} is down as expected'.format(osd_id)
            LOG.info(msg)

        if not host_helper._wait_for_host_states(host, availability='available'):   # yang TODO use fail_ok flag?
            msg = 'Host {} did not come available in the expected time'.format(host)
            raise exceptions.HostPostCheckFailed(msg)

        LOG.tc_step('Check that OSDs are up')
        osd_list = storage_helper.get_osds(host, con_ssh)
        for osd_id in osd_list:
            osd_up = storage_helper.is_osd_up(osd_id, con_ssh)
            msg = 'OSD ID {} is down but should be up'.format(osd_id)
            assert osd_up, msg
            msg = 'OSD ID {} is up as expected'.format(osd_id)
            LOG.info(msg)

        # LOG.tc_step('Get alarms list')
        # alarms_table = system_helper.get_alarms(con_ssh=None)
        # reasons = table_parser.get_values(alarms_table, 'Reason Text')
        # msg = '{0} \'ceph mon\' process has failed'.format(host)
        # assert not re.search(msg, reasons), \
        #     'Alarm {} system alarm-list'.format(msg)

        LOG.tc_step('Check health of CEPH cluster')
        ceph_healthy, msg = storage_helper.is_ceph_healthy(con_ssh)
        assert ceph_healthy, msg


# Pass on PV0 in 862.99
# CGTS-4556 and CGTS-4557 raised
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

    """

    con_ssh = ControllerClient.get_active_controller()

    if host == 'any':
        storage_nodes = system_helper.get_storage_nodes(con_ssh)
        LOG.info('System has {} storage nodes:'.format(storage_nodes))
        del storage_nodes['storage-0']
        node_id = random.randint(0, len(storage_nodes) - 1)
        host = 'storage-' + str(node_id)

    LOG.tc_step('Lock storage node {}'.format(host))
    rtn_code, out = host_helper.lock_host(host)
    assert rtn_code == 0, out       # yang TODO assert unnecessary here, can set check_first to false if needed.

    LOG.tc_step('Determine the storage group for host {}'.format(host))
    storage_group, msg = storage_helper.get_storage_group(host)
    LOG.info(msg)

    LOG.tc_step('Check that host lock alarm is raised when {} is locked'.format(host))
    query_value = 'host={}'.format(host)
    alarms_table = system_helper.get_alarms(query_key='entity_instance_id',
                                            query_value=query_value,
                                            query_type='string')
    LOG.info(alarms_table)
    msg = "Alarm {} was not found in alarm-list".format(EventLogID.HOST_LOCK)
    assert EventLogID.HOST_LOCK in str(alarms_table), msg

    LOG.tc_step('Check health of CEPH cluster')
    ceph_healthy, msg = storage_helper.is_ceph_healthy(con_ssh)
    assert not ceph_healthy, msg
    LOG.info(msg)

    # We need to wait a bit before OSDs go down
    time.sleep(5)

    LOG.tc_step('Check that OSDs are down')
    osd_list = storage_helper.get_osds(host, con_ssh)
    for osd_id in osd_list:
        osd_up = storage_helper.is_osd_up(osd_id, con_ssh)
        msg = 'OSD ID {} is up but should be down'.format(osd_id)
        assert not osd_up, msg
        msg = 'OSD ID {} is down as expected'.format(osd_id)
        LOG.info(msg)

    # Wait for alarms to be raised
    time.sleep(10)

    # 800.011   Loss of replication in replication group group-0: OSDs are down
    alarms_table = system_helper.get_alarms(query_key='alarm_id',
                                            query_value=EventLogID.STORAGE_LOR,
                                            query_type='string')
    LOG.info(alarms_table)
    msg = "Alarm {} not found in alarm-list".format(EventLogID.STORAGE_LOR)
    assert EventLogID.STORAGE_LOR in str(alarms_table), msg

    # 800.001   Storage Alarm Condition: Pgs are degraded/stuck/blocked. Please
    # check 'ceph -s' for more details
    alarms_table = system_helper.get_alarms(query_key='alarm_id',
                                            query_value=EventLogID.STORAGE_ALARM_COND,
                                            query_type='string')
    LOG.info(alarms_table)
    msg = "Alarm {} not found in alarm-list".format(EventLogID.STORAGE_ALARM_COND)
    assert EventLogID.STORAGE_ALARM_COND in str(alarms_table), msg

    LOG.tc_step('Unlock storage node')
    rtn_code, out = host_helper.unlock_host(host)
    assert rtn_code == 0, out

    # Give some time for alarms to clear
    time.sleep(30)

    # Check that alarms clear
    LOG.tc_step('Check that host lock alarm is cleared when {} is unlocked'.format(host))
    query_value = 'host={}'.format(host)
    alarms_table = system_helper.get_alarms(query_key='entity_instance_id',
                                            query_value=query_value,
                                            query_type='string')
    LOG.info(alarms_table)
    msg = "Alarm {} found in alarm-list".format(EventLogID.HOST_LOCK)
    assert EventLogID.HOST_LOCK not in str(alarms_table), msg

    LOG.tc_step('Check that the replication group alarm is cleared')
    alarms_table = system_helper.get_alarms(con_ssh)
    LOG.info(alarms_table)
    ids = table_parser.get_values(alarms_table, 'Alarm ID')
    for alarm_id in ids:
        assert alarm_id != EventLogID.STORAGE_LOR, \
            'Alarm ID {} found in alarm-list'.format(EventLogID.STORAGE_LOR)

    LOG.tc_step('Check that the Storage Alarm Condition is cleared')
    alarms_table = system_helper.get_alarms(con_ssh)
    LOG.info(alarms_table)
    ids = table_parser.get_values(alarms_table, 'Alarm ID')
    for alarm_id in ids:
        assert alarm_id != EventLogID.STORAGE_ALARM_COND, \
            'Alarm ID {} found in alarm-list'.format(EventLogID.STORAGE_ALARM_COND)

    LOG.tc_step('Check health of CEPH cluster')
    ceph_healthy, msg = storage_helper.is_ceph_healthy(con_ssh)
    assert ceph_healthy, msg

    LOG.tc_step('Check OSDs are up after unlock')
    for osd_id in osd_list:
        osd_up = storage_helper.is_osd_up(osd_id, con_ssh)
        msg = 'OSD ID {} should be up but is not'.format(osd_id)
        assert osd_up, msg

# Pass on PV0 603.47 seconds
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
    rtn_code, out = host_helper.lock_host(host)
    assert rtn_code == 0, out

    # Wait a bit for alarms to be raised
    time.sleep(5)

    LOG.tc_step('Check that storage degrade alarm is raised when {} is locked'.format(host))
    alarms_table = system_helper.get_alarms(query_key='alarm_id',
                                            query_value=EventLogID.STORAGE_ALARM_COND,
                                            query_type='string')
    LOG.info(alarms_table)
    msg = 'Alarm {} not found in alarm-list'.format(EventLogID.STORAGE_ALARM_COND)
    assert len(alarms_table) == 2, msg

    LOG.tc_step('Check that host lock alarm is raised when {} is locked'.format(host))
    query_value = 'host={}'.format(host)
    alarms_table = system_helper.get_alarms(query_key='entity_instance_id',
                                            query_value=query_value,
                                            query_type='string')
    LOG.info(alarms_table)
    msg = "Alarm {} not found in alarm-list".format(EventLogID.HOST_LOCK)
    assert EventLogID.HOST_LOCK in str(alarms_table), msg

    LOG.tc_step('Check OSDs are still up after lock')
    osd_list = storage_helper.get_osds(con_ssh=con_ssh)
    for osd_id in osd_list:
        osd_up = storage_helper.is_osd_up(osd_id, con_ssh)
        msg = 'OSD ID {} should be up but is not'.format(osd_id)
        assert osd_up, msg
        msg = 'OSD ID {} is up'.format(osd_id)
        LOG.info(msg)

    LOG.tc_step('Unlock standby controller node {}'.format(host))
    rtn_code, out = host_helper.unlock_host(host)
    assert rtn_code == 0, out

    # Wait for alarm to clear
    time.sleep(20)

    # Check that alarms clear
    LOG.tc_step('Check that the host locked alarm is cleared')
    query_value = 'host={}'.format(host)
    alarms_table = system_helper.get_alarms(query_key='entity_instance_id',
                                            query_value=query_value,
                                            query_type='string')
    LOG.info(alarms_table)
    msg = "Alarm {} not found in alarm-list".format(EventLogID.HOST_LOCK)
    assert EventLogID.HOST_LOCK not in str(alarms_table), msg

    LOG.tc_step('Check that the Storage Alarm Condition is cleared')
    alarms_table = system_helper.get_alarms(con_ssh)
    LOG.info(alarms_table)
    ids = table_parser.get_values(alarms_table, 'Alarm ID')
    for alarm_id in ids:
        assert alarm_id != EventLogID.STORAGE_ALARM_COND, \
            'Alarm ID {} found in alarm-list'.format(EventLogID.STORAGE_ALARM_COND)

    LOG.tc_step('Check health of CEPH cluster')
    ceph_healthy, msg = storage_helper.is_ceph_healthy(con_ssh)


# Pass on PV0 in 797.17 seconds
@mark.usefixtures('ceph_precheck')
def test_storgroup_semantic_checks():
    """
    This test validates CEPH semantic checks as it applies to storage nodes in
    a replication group.

    Args:
        - None

    Setup:
        - Requires a system with storage nodes (minimum of 2)
        - Requires TiS Release 3

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
        peers = host_helper.get_hostshow_values(host, con_ssh, 'peers')
        peers = ast.literal_eval(list(peers.values())[0])
        hosts = peers['hosts']
        hosts.remove(host)
        storage_group = peers['name']

        LOG.tc_step('Lock {} in the {} group:'.format(host, storage_group))
        rtn_code, out = host_helper.lock_host(host)
        assert rtn_code == 0, out

        LOG.tc_step("Verify CEPH cluster health reflects the OSD being down")
        ceph_healthy, msg = storage_helper.is_ceph_healthy(con_ssh)
        assert not ceph_healthy, msg

        LOG.tc_step('Check that alarms are raised when {} is locked'.format(host))
        alarms_table = system_helper.get_alarms(query_key='alarm_id',
                                                query_value=EventLogID.HOST_LOCK,
                                                query_type='string')
        LOG.info(alarms_table)
        msg = "Alarm {} not found in alarm-list".format(EventLogID.HOST_LOCK)
        assert len(alarms_table) == 2, msg

        LOG.tc_step('Check that OSDs are down')
        osd_list = storage_helper.get_osds(host, con_ssh)
        for osd_id in osd_list:
            osd_up = storage_helper.is_osd_up(osd_id, con_ssh)
            msg = 'OSD ID {} is up but should be down'.format(osd_id)
            assert not osd_up, msg
            msg = 'OSD ID {} is down as expected'.format(osd_id)
            LOG.info(msg)

        # TODO: If storage host is a storage monitor, ensure the monitor
        # alarm is raised.  We're not even seeing the monitor alarm

        # Check for loss of replication group alarm
        # 800.011   Loss of replication in replication group group-0: OSDs are down
        alarms_table = system_helper.get_alarms(query_key='alarm_id',
                                                query_value=EventLogID.STORAGE_LOR,
                                                query_type='string')
        LOG.info(alarms_table)
        msg = "Alarm {} not found in alarm-list".format(EventLogID.STORAGE_LOR)
        assert len(alarms_table) == 2, msg

        # Check for Storage Alarm Condition
        # 800.001   Storage Alarm Condition: Pgs are degraded/stuck/blocked. Please
        # check 'ceph -s' for more details
        alarms_table = system_helper.get_alarms(query_key='alarm_id',
                                                query_value=EventLogID.STORAGE_LOR,
                                                query_type='string')
        LOG.info(alarms_table)
        msg = "Alarm {} not found in alarm-list".format(EventLogID.STORAGE_LOR)
        assert len(alarms_table) == 2, msg

        if host == 'storage-0':
            hosts.append('controller-0')
            hosts.append('controller-1')

        for node in hosts:
            LOG.tc_step('Attempt to lock the {}'.format(node))
            rtn_code, out = host_helper.lock_host(node, fail_ok=True)
            assert rtn_code != 0, out       # yang TODO perhaps should assert 1 here for cli rejection.

            LOG.tc_step('Attempt to force lock {}'.format(node))
            rtn_code, out = host_helper.lock_host(node, fail_ok=True, force=True)
            # yang: TODO: Should the return code be checked?

        LOG.tc_step('Unlock storage host {}'.format(host))
        rtn_code, out = host_helper.unlock_host(host)
        assert rtn_code == 0, out           # yang TODO this may not be correct since host is never locked.

        # Waita bit for alarms to clear
        # TODO: Why does it take so long to clear?
        time.sleep(20)

        # Check that alarms clear
        LOG.tc_step('Check that the host locked alarm is cleared')
        alarms_table = system_helper.get_alarms(con_ssh)
        LOG.info(alarms_table)
        ids = table_parser.get_values(alarms_table, 'Alarm ID')
        for alarm_id in ids:
            LOG.info("This is ID: {}".format(id))
            assert alarm_id != EventLogID.HOST_LOCK, \
                'Alarm ID {} was found in alarm-list'.format(EventLogID.HOST_LOCK)

        LOG.tc_step('Check that the replication group alarm is cleared')
        alarms_table = system_helper.get_alarms(con_ssh)
        LOG.info(alarms_table)
        ids = table_parser.get_values(alarms_table, 'Alarm ID')
        for alarm_id in ids:
            assert alarm_id != EventLogID.STORAGE_LOR, \
                'Alarm ID {} found in alarm-list'.format(EventLogID.STORAGE_LOR)

        LOG.tc_step('Check that the Storage Alarm Condition is cleared')
        alarms_table = system_helper.get_alarms(con_ssh)
        LOG.info(alarms_table)
        ids = table_parser.get_values(alarms_table, 'Alarm ID')
        for alarm_id in ids:
            assert alarm_id != EventLogID.STORAGE_ALARM_COND, \
                'Alarm ID {} found in alarm-list'.format(EventLogID.STORAGE_ALARM_COND)

        # TODO: If storage host is a storage monitor, ensure the monitor alarm clears
        # We're not even seeing the monitor alarm

        LOG.tc_step('Check health of CEPH cluster')
        ceph_healthy, msg = storage_helper.is_ceph_healthy(con_ssh)
        assert ceph_healthy, msg

        LOG.tc_step('Check OSDs are up after unlock')
        for osd_id in osd_list:
            osd_up = storage_helper.is_osd_up(osd_id, con_ssh)
            msg = 'OSD ID {} should be up but is not'.format(osd_id)
            assert osd_up, msg


# Pass with workaround for defect
# PV0 pass in 186.00
# CGTS-4587 raised
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
        image_names = storage_helper.download_images(dload_type='ubuntu',
            img_dest=img_dest, con_ssh=con_ssh)

    LOG.tc_step('Import qcow2 images into glance')
    for image in image_names:
        source_image_loc = img_dest + "/" + image
        img_name = 'testimage_{}'.format(image)
        ret = glance_helper.create_image(source_image_file=source_image_loc,
                                         disk_format='qcow2',
                                         container_format='bare',
                                         cache_raw=True, wait=True)
        LOG.info("ret {}".format(ret))
        assert ret[0] == 0, ret[2]

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
        assert flv[0] == 0, flv[1]

        LOG.tc_step('Launch VM from created volume')
        vm_id = vm_helper.boot_vm(name=img_name, flavor=flv[1],
            source='volume', source_id=volume_id)[1]
        vm_list.append(vm_id)

        # When spawning, make sure we don't download the image
        LOG.tc_step('Launch VM from image')
        img_name2 = img_name + '_fromimage'
        vm_id2 = vm_helper.boot_vm(name=img_name2, flavor=flv[1], source='image', source_id=rbd_img_id)[1]
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


# Pass PV0 52.55 seconds
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
                       'controller-1:{}'.format(IMAGE_DIR, IMAGE_DIR)
        con_ssh.exec_cmd(rsync_images)
        image_names = storage_helper.find_images(con_ssh, image_type='raw')
        msg = 'No images found on controller'
        assert not image_names, msg     # yang: TODO: Assert no images, but error msg is the opposite

    LOG.tc_step('Import raw images into glance with --cache-raw')
    for image in image_names:
        source_image_loc = IMAGE_DIR + image
        ret = glance_helper.create_image(source_image_file=source_image_loc,
                                         disk_format='raw',
                                         container_format='bare',
                                         cache_raw=True)
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
@mark.usefixtures('ceph_precheck')
def test_exceed_size_of_img_pool():
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
    glance_ids = []

    # Return a list of images of a given type
    LOG.tc_step('Determine what qcow2 images we have available')
    image_names = storage_helper.find_images(con_ssh)

    if not image_names:
        LOG.info('No qcow2 images were found on the system')
        LOG.tc_step('Downloading qcow2 image(s)... this will take some time')
        image_names = storage_helper.download_images(dload_type='ubuntu', \
            img_dest=IMAGE_DIR, con_ssh=con_ssh)

    LOG.tc_step('Import qcow2 images into glance until pool is full')
    source_img = IMAGE_DIR + "/" + image_names[0]
    while True:     # yang TODO would ret[0] = 1 happen for sure? otherwise it might become a indefinite loop
        ret = glance_helper.create_image(source_image_file=source_img,
                                         disk_format='qcow2', \
                                         container_format='bare', \
                                         cache_raw=True, wait=True,
                                         fail_ok=True)
        glance_ids.append(ret[1])

        if ret[0] == 1:
            break

    #Wait for alarm to appear
    time.sleep(10)

    # 800.001   Storage Alarm Condition: Pgs are degraded/stuck/blocked.
    # Please check 'ceph -s' for more details
    LOG.tc_step('Query alarms for ceph alarms')
    alarms_table = system_helper.get_alarms(query_key='alarm_id',
                                            query_value=EventLogID.STORAGE_ALARM_COND,
                                            query_type='string')
    LOG.info(alarms_table)
    msg = "Alarm {} not found in alarm-list".format(EventLogID.STORAGE_ALARM_COND)
    assert EventLogID.STORAGE_ALARM_COND in str(alarms_table), msg

    LOG.tc_step('Verify the health cluster is not healthy')         # yang TODO verify healthy or unhealthy?
    ceph_healthy, msg = storage_helper.is_ceph_healthy(con_ssh)
    assert ceph_healthy, msg

    LOG.info("glance ids {}".format(glance_ids))

    #LOG.tc_step('Delete Image(s) {}'.format(glance_ids))
    #glance_helper.delete_images(glance_ids)


@mark.usefixtures('ceph_precheck')
def test_import_large_images_with_cache_raw():
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
    base_img = img + '.img'
    qcow2_img = img + '.qcow2'
    new_img = '40GB' + base_img
    vm_list = []

    # Check that we have the cgcs-guest.img available
    # If we are on controller-1, we may need to rsync image files from
    # controller-0
    LOG.tc_step('Determine if the cgcs-guest image is available')
    image_names = storage_helper.find_images(con_ssh)
    if base_img not in image_names:
        LOG.tc_step('Rsyncing images from controller-0')
        rsync_images = 'rsync -avr -e "ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no " {} ' \
                       'controller-1:{}'.format(IMAGE_DIR, IMAGE_DIR)
        con_ssh.exec_cmd(rsync_images)
        image_names = storage_helper.find_images(con_ssh)
        msg = '{} was not found in {}'.format(base_img, IMAGE_DIR)
        assert base_img in image_names, msg

    # Resize the image to 40GB
    LOG.tc_step('Resize the cgcs-guest image to 40GB')
    cmd = 'cp {}/{} {}/{}'.format(IMAGE_DIR, base_img, IMAGE_DIR, new_img)
    rtn_code, out = con_ssh.exec_cmd(cmd)
    assert not rtn_code, out
    cmd = 'qemu-img resize {} -f raw 40G'.format(new_img)
    rtn_code, out = con_ssh.exec_cmd(cmd, expect_timeout=600)
    assert not rtn_code, out

    # Confirm the virtual size is 40GB
    size = storage_helper.find_image_size(con_ssh, image_name=new_img)
    msg = 'Image was not resized to 40GB'
    assert size == '40', msg

    # Convert the image to qcow2
    LOG.tc_step('Convert the raw image to qcow2')
    args = '{}/{} {}/{}'.format(IMAGE_DIR, new_img, IMAGE_DIR, qcow2_img)
    cmd = 'qemu-img convert -f raw -O qcow2' + ' ' + args
    rtn_code, out = con_ssh.exec_cmd(cmd, expect_timeout=600)
    assert not rtn_code, out    # yang TODO can use fail_ok=False if needed

    # Check the image type is updated
    image_names = storage_helper.find_images(con_ssh, image_type='qcow2')
    msg = 'qcow2 image was not found in {}'.format(IMAGE_DIR)
    assert qcow2_img in image_names, msg

    LOG.tc_step('Import image into glance')
    source_img = IMAGE_DIR + qcow2_img
    out = glance_helper.create_image(source_image_file=source_img,
                                     disk_format='qcow2', \
                                     container_format='bare', \
                                     cache_raw=True, wait=True)
    msg = 'Failed to import {} into glance'.format(qcow2_img)
    assert out[0] == 0, msg

    LOG.tc_step('Create volume from the imported image')
    volume_id = cinder_helper.create_volume(name=image_names[0],
                                            image_id=out[1],
                                            size=40,
                                            con_ssh=con_ssh,
                                            rtn_exist=False)[1]
    msg = "Unable to create volume"
    assert volume_id, msg

    LOG.tc_step('Create flavor of sufficient size for VM')
    flv = nova_helper.create_flavor(name=image_names[0], root_disk=size)
    assert flv[0] == 0, flv[1]

    LOG.tc_step('Launch VM from created volume')
    vm_id = vm_helper.boot_vm(name=image_names[0], flavor=flv[1], \
        source='volume', source_id=volume_id)[1]
    vm_list.append(vm_id)

    # When spawning, make sure we don't download the image
    LOG.tc_step('Launch VM from image')
    img_name2 = image_names[0] + '_fromimage'
    vm_id2 = vm_helper.boot_vm(name=img_name2, flavor=flv[1], \
        source='image', source_id=out[1])[1]        # yang TODO 120 chars limit instead of 80
    vm_list.append(vm_id2)

    # yang TODO use ResourceCleanup in case of test fail.
    LOG.tc_step('Delete VMs {}'.format(vm_list))
    vm_helper.delete_vms(vms=vm_list, con_ssh=con_ssh)

    LOG.tc_step('Delete Flavor(s) {}'.format(flv[1]))
    nova_helper.delete_flavors(flv[1])

    LOG.tc_step('Delete Image(s) {}'.format(out[1]))
    glance_helper.delete_images(out[1])


@mark.usefixtures('ceph_precheck')
def test_modify_ceph_pool_size():
    """
    Verify that the user can modify the size of the ceph images pool.

    This is US68056_tc5_modify_ceph_pool_size adapted from
    us68056_glance_backend_to_storage_node.odt

    Args:
    - None

    Setup:
        - Requires a system with storage nodes

    Test Steps:
        1.  Determine the current size of the ceph image pool
        2.  Increase the ceph image pool size
        3.  Confirm the pool size has been increased (without having to reboot
        controllers)
    """

    LOG.tc_step('Query the size of the CEPH storage pools')
    table_ = table_parser.table(cli.system('storagepool-show'))
    glance_pool_gib = int(table_parser.get_values(table_, 'glance_pool_gib'))
    cinder_pool_gib = int(table_parser.get_values(table_, 'cinder_pool_gib'))
    ephemeral_pool_gib = int(table_parser.get_values(table_, 'ephemeral_pool_gib'))
    ceph_total_space_gib = table_parser.get_values(table_, 'ceph_total_space_gib')

    LOG.tc_step('Increase the size of the ceph image pool')
    total_used = glance_pool_gib + cinder_pool_gib + ephemeral_pool_gib
    if total_used != ceph_total_space_gib:
        # Check for 800.003 Ceph cluster has free space unused by storage pool quotas
        alarms_table = system_helper.get_alarms(query_key='alarm_id',
                                                query_value=EventLogID.STORAGE_POOLQUOTA,
                                                query_type='string')
        LOG.info(alarms_table)
        msg = "Alarm {} not found in alarm-list".format(EventLogID.STORAGE_POOLQUOTA)
        assert EventLogID.STORAGE_POOLQUOTA in str(alarms_table)

        # Add the free space to the glance_pool_gib
        total_available = ceph_total_space_gib - total_used
        new_value = glance_pool_gib + total_available
        args = 'glance_pool_gib=' + str(new_value)
        rtn_code, out = cli.system('storagepool-modify', args)
        msg = 'Unable to change pool quota from {} to {}'.format(glance_pool_gib,
                                                                 new_value)
        assert rtn_code == 0, msg

        # Now, let's wait a bit for the free space alarm to clear
        time.sleep(10)

        # Check for 800.003 Ceph cluster has free space unused by storage pool quotas
        alarms_table = system_helper.get_alarms(query_key='alarm_id',
                                                query_value=EventLogID.STORAGE_POOLQUOTA,
                                                query_type='string')
        LOG.info(alarms_table)
        msg = "Alarm {} found in alarm-list".format(EventLogID.STORAGE_POOLQUOTA)
        assert EventLogID.STORAGE_POOLQUOTA not in str(alarms_table), msg

    else:
        # Else we have used up all the space we have available, so let's take some
        # space from the other pools.
        # We check because in some cases ephemeral pool can be set to 0
        if ephemeral_pool_gib > 10:
            other_args = 'ephemeral_pool_gib=' + str(ephemeral_pool_gib - 10)
        else:
            other_args = 'cinder_pool_gib=' + str(cinder_pool_gib - 10)

        glance_args = 'glance_pool_gib=' + str(glance_pool_gib + 10)
        args = glance_args + " " + other_args
        new_value = glance_pool_gib + 10
        rtn_code, out = cli.system('storagepool-modify', args)
        msg = 'Failed to change glance storage pool quota from {} to {}'.format(glance_pool_gib,
                                                                                new_value)
        assert rtn_code == 0, msg

    LOG.info('Check the ceph images pool is set to the right value')
    table_ = table_parser.table(cli.system('storagepool-show'))
    glance_pool_gib = table_parser.get_values(table_, 'glance_pool_gib')

    msg = 'Glance pool size was supposed to be {} but is {} instead'.format(new_value,
                                                                            glance_pool_gib)
    assert int(glance_pool_gib) == new_value, msg


@mark.usefixtures('ceph_precheck')
def test_modify_ceph_pool_size_neg():
    """
    Verify that the user can modify the size of the ceph images pool.

    This is US68056_tc6_neg_modify_ceph_pool_size adapted from
    us68056_glance_backend_to_storage_node.odt

    Args:
    - None

    Setup:
        - Requires a system with storage nodes

    Test Steps:
        1.  Determine the current size of the ceph image pool
        2.  Fill up the images pool until you can't add anymore images
        3.  Attempt to set the ceph pool size to less than the data in the
        pool.  It should be rejected.
        4.  Increase the pool size.
        5.  Ensure you can import another image.
    """

    con_ssh = ControllerClient.get_active_controller()

    LOG.tc_step('Query the size of the CEPH storage pools')
    table_ = table_parser.table(cli.system('storagepool-show'))
    glance_pool_gib = int(table_parser.get_values(table_, 'glance_pool_gib'))
    ephemeral_pool_gib = int(table_parser.get_values(table_, 'ephemeral_pool_gib'))

    LOG.tc_step('Determine what qcow2 images we have available')
    image_names = storage_helper.find_images(con_ssh)

    if not image_names:
        LOG.info('No qcow2 images were found on the system')
        LOG.tc_step('Downloading qcow2 image(s)... this will take some time')
        image_names = storage_helper.download_images(dload_type='ubuntu', \
            img_dest=IMAGE_DIR, con_ssh=con_ssh)    # TODO for Yang: perhaps a session level fixture should be added

    LOG.tc_step('Import qcow2 images into glance until pool is full')
    source_img = IMAGE_DIR + "/" + image_names[0]
    while True:
        ret = glance_helper.create_image(source_image_file=source_img,
                                         disk_format='qcow2', \
                                         container_format='bare', \
                                         cache_raw=True, wait=True,
                                         fail_ok=True)

        if ret[0] == 1:
            break

    LOG.tc_step('Attempt to reduce the quota to less than the data in pool')
    glance_args = 'glance_pool_gib=' + str(glance_pool_gib - 10)
    eph_args = 'ephemeral_pool_gib=' + str(ephemeral_pool_gib + 10)
    args = glance_args + " " + eph_args
    new_value = glance_pool_gib - 10
    rtn_code, out = cli.system('storagepool-modify', args)      # TODO for Yang: keyword needed
    msg = 'Unexpectedly changed glance storage pool quota from {} to {}'.format(glance_pool_gib,
                                                                                new_value)
    assert rtn_code != 0, msg

    LOG.tc_step('Increase the pool quota and ensure you can import images again')
    glance_args = 'glance_pool_gib=' + str(glance_pool_gib + 20)
    eph_args = 'ephemeral_pool_gib=' + str(ephemeral_pool_gib - 20)
    args = glance_args + " " + eph_args
    new_value = glance_pool_gib + 20
    rtn_code, out = cli.system('storagepool-modify', args)
    msg = 'Unable to change pool quota from {} to {}'.format(glance_pool_gib,
                                                             new_value)
    assert rtn_code == 0, msg

    LOG.tc_step('Import one more image')
    ret = glance_helper.create_image(source_image_file=source_img,
                                     disk_format='qcow2', \
                                     container_format='bare', \
                                     cache_raw=True, wait=True,
                                     fail_ok=True)
    msg = 'Was not able to import another image after increasing the quota'
    assert ret[0] == 0, msg


