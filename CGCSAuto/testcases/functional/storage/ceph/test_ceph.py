"""
This file contains CEPH-related storage test cases.
"""

from pytest import mark
import random
import time
import re
import ast

from utils import cli, exceptions, table_parser
from utils.ssh import ControllerClient
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, host_helper, system_helper, \
    storage_helper, glance_helper, cinder_helper
from consts.cgcs import HostAavailabilityState, EventLogID

PROC_RESTART_TIME = 30     # number of seconds between process restarts
RESTARTS_BEFORE_ASSERT = 3 # number of process restarts until error assertion

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
    osd_host, msg = storage_helper.get_osd_host(str(osd_id), con_ssh)
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
    for i in range(0, PROC_RESTART_TIME):
        osd_pid2, msg = storage_helper.get_osd_pid(osd_host, osd_id)
        if osd_pid2 != osd_pid:
            break
        time.sleep(1)
    msg = 'Process did not restart in time'
    assert osd_pid2 != osd_pid, msg
    LOG.info('Old pid is {} and new pid is {}'.format(osd_pid, osd_pid2))
    
    # Note, there is an impact to ceph health going from HEALTH_OK to
    # HEALTH_WARN but it is too brief to look for.

    LOG.tc_step('Repeatedly kill the OSD process until we alarm')
    for i in range(0, RESTARTS_BEFORE_ASSERT):
        osd_pid, msg = storage_helper.get_osd_pid(osd_host, osd_id)
        assert osd_pid, msg
        proc_killed, msg = storage_helper.kill_process(osd_host, osd_pid)
        assert proc_killed, msg
        for i in range(0, PROC_RESTART_TIME):
            osd_pid2, msg = storage_helper.get_osd_pid(osd_host, osd_id)
            if osd_pid2 != osd_pid:
                break
            time.sleep(1)
        msg = 'Process did not restart in time'
        assert osd_pid2 != osd_pid, msg
        LOG.info('Old pid is {} and new pid is {}'.format(osd_pid, osd_pid2))

    # Note, we cannot check alarms since the alarms clears too quickly.  Check
    # events instead.

    # storage-1 is degraded due to the failure of its 'ceph (osd.1)' process.
    # Auto recovery of this major process is in progress. 
    LOG.tc_step('Check events list for OSD failure')
    entity_instance = 'host={}.process=ceph (osd.{})'.format(osd_host, osd_id)
    system_helper.wait_for_events(30, strict=False, fail_ok=False, 
        **{'Entity Instance ID': entity_instance, 'Event Log ID':
        EventLogID.STORAGE_DEGRADE, 'State': 'set'})

    # Can't always catch this event - CGTS-4513
    # Loss of replication in replication group group-0: OSDs are down
    #LOG.tc_step('Check events list for replication group failure')
    #reason_text = 'Loss of replication in replication group {}: OSDs are down'.format(storage_group)
    #system_helper.wait_for_events(30, strict=False, fail_ok=False, 
    #    **{'Reason Text': reason_text, 'Event Log ID': EventLogID.STORAGE_LOR})

    # Note, the storage host degrade state is so brief that we cannot check
    # for it.

    LOG.tc_step('Check the OSD failure event clears')
    LOG.tc_step('Check events list for OSD failure')
    entity_instance = 'host={}.process=ceph (osd.{})'.format(osd_host, osd_id)
    system_helper.wait_for_events(45, strict=False, fail_ok=False, 
        **{'Entity Instance ID': entity_instance, 'Event Log ID':
        EventLogID.STORAGE_DEGRADE, 'State': 'clear'})

    # Can't always catch this event - CGTS-4513
    #LOG.tc_step('Check events list for replication group event clear')
    #reason_text = 'Loss of replication in replication group {}: OSDs are down'.format(storage_group)
    #system_helper.wait_for_events(30, strict=False, fail_ok=False, 
    #    **{'Reason Text': reason_text, 'Event Log ID': EventLogID.STORAGE_LOR,
    #    State: 'clear'})

    # Give Ceph a bit of time to return to health ok state
    # TODO: Do better than just sleeping
    time.sleep(10)

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

    # Alarm #1
    # controller-1 is degraded due to the failure of its 'ceph
    # (mon.controller-1)' process. Auto recovery of this major process is in
    # progress.
    # Alarm #2
    # Storage Alarm Condition: 1 mons down, quorum 0,2
    # controller-0,storage-0
    LOG.tc_step('Check events list for ceph monitor failure')
    entity_instance = 'host={}.process=ceph (mon.{})'.format(monitor,
        monitor)
    system_helper.wait_for_events(30, strict=False, fail_ok=False,
        **{'Entity Instance ID': entity_instance, 'Event Log ID':
        EventLogID.STORAGE_DEGRADE, 'State': 'set'})

    # This is not being seen.  CGTS-4520.  Instead we see:
    # Storage Alarm Condition: Pgs are degraded/stuck/blocked. Please check
    # 'ceph -s' for more details
    #LOG.tc_step('Check events list for storage alarm condition')
    #reason_text = 'Storage Alarm Condition: 1 mons down'
    #system_helper.wait_for_events(30, strict=False, fail_ok=False,
    #    **{'Reason Text': reason_text, 'Event Log ID':
    #    EventLogID.STORAGE_ALARM_COND, 'State': 'set'})

    # Note, the storage host degrade state is so brief that we cannot check
    # for it.

    # Sleep to give time for events to clear 
    time.sleep(20)

    LOG.tc_step('Check events list for ceph monitor clear')
    entity_instance = 'host={}.process=ceph (mon.{})'.format(monitor,
        monitor)
    system_helper.wait_for_events(45, strict=False, fail_ok=False, 
        **{'Entity Instance ID': entity_instance, 'Event Log ID':
        EventLogID.STORAGE_DEGRADE, 'State': 'clear'})

    # FAIL due to CGTS-4520
    #LOG.tc_step('Check events list for storage alarm condition')
    #reason_text = 'Storage Alarm Condition: 1 mons down'
    #system_helper.wait_for_events(45, strict=False, fail_ok=False,
    #**{'Reason Text': reason_text, 'Event Log ID':
    #EventLogID.STORAGE_ALARM_COND, 'State': 'clear'})

    # Give Ceph a bit of time to return to health ok state
    # TODO: Do better than just sleeping
    time.sleep(10)

    LOG.tc_step('Verify the health cluster is healthy')
    ceph_healthy, msg = storage_helper.is_ceph_healthy(con_ssh)

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
        LOG.tc_step("Results: {}".format(results))
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

        if not host_helper._wait_for_host_states(host, availability='available'):
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

        #LOG.tc_step('Get alarms list')
        #alarms_table = system_helper.get_alarms(con_ssh=None)
        #reasons = table_parser.get_values(alarms_table, 'Reason Text')
        #msg = '{0} \'ceph mon\' process has failed'.format(host)
        #assert not re.search(msg, reasons), \
        #    'Alarm {} system alarm-list'.format(msg)

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
    assert rtn_code == 0, out

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

    # We no longer see the Storage Alarm Condition: 1 mons down alarm
    #if host == 'storage-0':
    #    alarms_table = system_helper.get_alarms(query_key='alarm_id',
    #                                            query_value=EventLogID.STORAGE_ALARM_COND,
    #                                            query_type='string')
    #    LOG.info(alarms_table)
    #    msg = 'Alarm {} not found in alarm-list'.format(EventLogID.STORAGE_ALARM_COND)
    #    assert len(alarms_table) == 2, msg

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
    assert not EventLogID.HOST_LOCK in str(alarms_table), msg

    LOG.tc_step('Check that the replication group alarm is cleared')
    alarms_table = system_helper.get_alarms(con_ssh)
    LOG.info(alarms_table)
    ids = table_parser.get_values(alarms_table, 'Alarm ID')
    for id in ids:
        assert id != EventLogID.STORAGE_LOR, \
            'Alarm ID {} found in alarm-list'.format(EventLogID.STORAGE_LOR)

    LOG.tc_step('Check that the Storage Alarm Condition is cleared')
    alarms_table = system_helper.get_alarms(con_ssh)
    LOG.info(alarms_table)
    ids = table_parser.get_values(alarms_table, 'Alarm ID')
    for id in ids:
        assert id != EventLogID.STORAGE_ALARM_COND, \
            'Alarm ID {} found in alarm-list'.format(EventLogID.STORAGE_ALARM_COND)

    # Skipping until the alarm defect is resolved
    # If storage host is a storage monitor, ensure the monitor alarm clears
    #if host == 'storage-0':
    #    msg = 'Storage Alarm Condition: 1 mons down'
    #    assert re.search(msg, reasons), \
    #        'Alarm reason {} found in alarm-list'.format(msg)

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

    # Instead of mon down, we're seeing the following alarm:
    # Storage Alarm Condition: Pgs are degraded/stuck/blocked. Please check
    # 'ceph -s' for more details
    # We also see:
    # controller-1 was administratively locked to take it out-of-service.

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
    assert not EventLogID.HOST_LOCK in str(alarms_table), msg

    LOG.tc_step('Check that the Storage Alarm Condition is cleared')
    alarms_table = system_helper.get_alarms(con_ssh)
    LOG.info(alarms_table)
    ids = table_parser.get_values(alarms_table, 'Alarm ID')
    for id in ids:
        assert id != EventLogID.STORAGE_ALARM_COND, \
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
            assert rtn_code != 0, out

            LOG.tc_step('Attempt to force lock {}'.format(node))
            rtn_code, out = host_helper.lock_host(node, fail_ok=True, \
                force=True)

        LOG.tc_step('Unlock storage host {}'.format(host))
        rtn_code, out = host_helper.unlock_host(host)
        assert rtn_code == 0, out

        # Waita bit for alarms to clear
        # TODO: Why does it take so long to clear?
        time.sleep(20)

        # Check that alarms clear
        LOG.tc_step('Check that the host locked alarm is cleared')
        alarms_table = system_helper.get_alarms(con_ssh)
        LOG.info(alarms_table)
        ids = table_parser.get_values(alarms_table, 'Alarm ID')
        for id in ids:
            LOG.info("This is ID: {}".format(id))
            assert id != EventLogID.HOST_LOCK, \
                'Alarm ID {} was found in alarm-list'.format(EventLogID.HOST_LOCK)

        LOG.tc_step('Check that the replication group alarm is cleared')
        alarms_table = system_helper.get_alarms(con_ssh)
        LOG.info(alarms_table)
        ids = table_parser.get_values(alarms_table, 'Alarm ID')
        for id in ids:
            assert id != EventLogID.STORAGE_LOR, \
                'Alarm ID {} found in alarm-list'.format(EventLogID.STORAGE_LOR)

        LOG.tc_step('Check that the Storage Alarm Condition is cleared')
        alarms_table = system_helper.get_alarms(con_ssh)
        LOG.info(alarms_table)
        ids = table_parser.get_values(alarms_table, 'Alarm ID')
        for id in ids:
            assert id != EventLogID.STORAGE_ALARM_COND, \
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


@mark.usefixtures('check_alarms')
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
    """
    con_ssh = ControllerClient.get_active_controller()

    img_dest = '~/images/'
    size = 10
    vm_list = []

    LOG.tc_step('Downloading image(s)... this will take some time')
    image_names = storage_helper.download_images(dload_type='ubuntu', \
        img_dest=img_dest, con_ssh=con_ssh)

    LOG.tc_step('Import image into glance')
    for i in range(0, len(image_names)):
        source_image_loc = img_dest + image_names[i]
        img_name = 'image_{}'.format(i)
        ret = glance_helper.create_image(name=img_name, \
            source_image_file=source_image_loc,
            disk_format='qcow2', \
            container_format='raw', \
            cache_raw=True)
        assert not ret[0] == 0, ret[2]

        LOG.tc_step('Check image is shown in rbd')
        rbd_img_id = ret[1]
        rbd_raw_img_id = rbd_img_id + '_raw'
        cmd = 'rbd -p images ls'
        rtn_code, out = con_ssh.exec_cmd(cmd, expect_timeout=60)
        assert not re.search(rbd_img_id, out)
        assert not re.search(rbd_raw_img_id, out)

        LOG.tc_step('Check glance for image with Cache RAW set to true')
        image_id = glance_helper.get_images("Disk Format='raw'", \
            images=rbd_img_id, con_ssh=con_ssh, strict=True)
        msg = "Image {} not found in glance".format(rbd_img_id)
        assert not image_id, msg

        LOG.tc_step('Create volume from the imported image')
        volume_id = cinder_helper.create_volume(name=img_name, \
            image_id=rbd_img_id, \
            size=size,
            con_ssh=con_ssh, \
            rtn_exist=False)

        LOG.tc_step('Create flavor of sufficient size for VM')
        flv = nova_helper.create_flavor(name=img_name, root_disk=size)
        assert flv[0] != 0, flv[1]

        LOG.tc_step('Launch VM from created volume')
        vm_id = vm_helper.boot_vm(name=img_name, flavor=img_name, \
            source='volume', source_id=volume_id)
        vm_list.append(vm_id)

        LOG.tc_step('Launch VM from image')
        img_name2 = img_name + '_fromimage'
        vm_id2 = vm_helper.boot_vm(name=img_name2, flavor=img_name, \
            source='image', source_id=image_id)
        vm_list.append(vm_id2)

        LOG.tc_step('Delete VMs {}'.format(vm_list))
        vm_helper.delete_vms(vms=vm_list, con_ssh=con_ssh)

        LOG.tc_step('Delete Flavor(s) {}'.format(flv[1]))
        nova_helper.delete_flavors(flv[1])

        LOG.tc_step('Delete Image(s) {}'.format(image_id))
        glance_helper.delete_images(image_id)

        LOG.tc_step('Check images are cleaned up from rbd')
        rtn_code, out = con_ssh.exec_cmd(cmd, expect_timeout=60)
        assert re.search(rbd_img_id, out)
        assert re.search(rbd_raw_img_id, out)

@mark.usefixtures('check_alarms')
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
    size = 10
    con_ssh = ControllerClient.get_active_controller()

    image_path = '/home/wrsroot/'
    image_file = 'cgcs-guest.img'
    source_image_loc = image_path + image_file
    image_name = 'autotest_' + image_file.split('.')[0]

    LOG.tc_step('Import {} into glance'.format(image_name))
    ret = glance_helper.create_image(name=image_name, \
        source_image_file=source_image_loc, disk_format='raw', \
        container_format='bare', cache_raw=True)
    assert ret[0] != 0, ret[2]

    LOG.tc_step('Check non-raw image is shown in rbd')
    rbd_img_id = ret[1]
    rbd_raw_img_id = rbd_img_id + '_raw'
    cmd = 'rbd -p images ls'
    rtn_code, out = con_ssh.exec_cmd(cmd, expect_timeout=60)
    assert re.search(rbd_img_id, out)
    assert not re.search(rbd_raw_img_id, out)

    LOG.tc_step('Query RAW cache state')
    image_id = glance_helper.get_images("Raw Cache=''", \
            images=rbd_img_id, con_ssh=con_ssh, strict=True)

    # Query image for disk size
    cmd = 'qemu-img info {}'.format(source_image_loc)
    rtn_code, out = con_ssh.exec_cmd(cmd, expect_timeout=60)
    disk_size = re.search('virtual size: (\d+\.?\d*)[MG]', out)
    if not disk_size.group(1):
        LOG.info('Unable to determine size of image, using 10G default value')
    elif disk_size.group(1):
        if disk_size.group(2) == "M":
            disk_size = 1
        if disk_size(2) == "G":
            disk_size = disk_size

    LOG.tc_step('Create flavor of sufficient size for VM')
    flv = nova_helper.create_flavor(name=image_name, root_disk=size)
    assert flv[0] == 0, flv[1]

    LOG.tc_step('Ensure you can launch a VM from image')
    image_name2 = image_name + '_fromimage'
    vm_id2 = vm_helper.boot_vm(name=image_name2, flavor=image_name, \
        source='image', source_id=image_id)
    vm_list.append(vm_id2)

    LOG.tc_step('Ensure you can launch a VM from volume')
    vm_id = vm_helper.boot_vm(name=image_name, flavor=image_name, \
        source='volume', source_id=volume_id)
    vm_list.append(vm_id)

    # TODO: Resource cleanup
