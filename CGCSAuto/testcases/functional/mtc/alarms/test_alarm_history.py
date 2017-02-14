# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

import time
import re

from pytest import fixture, mark, skip, raises, fail
from consts.auth import Tenant
from utils.tis_log import LOG
from utils import cli, exceptions, table_parser
from utils.ssh import ControllerClient, ssh_to_controller0
from testfixtures.recover_hosts import HostsToRecover
from keywords import vm_helper, nova_helper, system_helper, host_helper, cinder_helper, glance_helper


@mark.p1
def test_system_alarm_history_list():
    """
    Verify system alarm-history-list command in the system

    Scenario:
    1. Execute "system alarm-list" command in the system.
    2. Reboot one active computes and wait 30 seconds.
    3. Verify commands return list of active alarms in table with expected
    rows.
    """

    LOG.info("Execute system alarm-list. Verify header of " +
             "a table consist of correct items")

    # Get and save the list of existing alarms present in the system
    res, out = cli.system('alarm-list', rtn_list=True)
    alarm_list = table_parser.table(out)

    if len(alarm_list['values']) == 0:
        LOG.info("There are no alarms are not present in the alarm list")

    current_alarms = []
    for alarm in alarm_list['values']:
        if re.match(".", alarm[0].strip()) is not None:
            current_alarms.append(alarm[0])
            LOG.info("The current alarms in the system are: "
                     "{0}".format(alarm[0]))

    # Get the historical list of alarms
    hist_alarm_table = system_helper.get_events_table(num=15, uuid=True)

    # Check that a valid alarm header is present
    alarm_header = ['UUID', 'Time Stamp', 'State', 'Event Log ID', 'Reason Text', 'Entity Instance ID', 'Severity']
    if hist_alarm_table['headers'] != alarm_header:
        LOG.info("Fields in table not correct actual {0} expected {1}"
                 .format(hist_alarm_table['headers'], alarm_header))

    # Verify the existing alarms are present in the historical list in state 'set'
    for name in current_alarms:
        kwargs = {"Event Log ID": name}
        alarm_state = table_parser.get_values(hist_alarm_table, 'State', **kwargs)
        LOG.info('alarm: %s  state: %s' % (name, alarm_state))
        if alarm_state != ['set']:
            LOG.info('Alarm state is incorrect')
            test_res = False
            break

    # Raise a new alarm by locking a compute node
    # Get the compute
        LOG.info("Lock compute and wait 30 seconds")
    host = 'compute-1'
    if system_helper.is_two_node_cpe():
        host = system_helper.get_standby_controller_name()

    HostsToRecover.add(host, scope='function')
    host_helper.lock_host(host)
    time.sleep(20)

    # Verify the new alarm is present in the historical alarm and active alarm lists
    LOG.info("Verify alarm-list command returns list of active alarms")
    res, out = cli.system('alarm-list', rtn_list=True)
    new_active_alarm_table = table_parser.table(out)

    if len(alarm_list['values']) == 0:
        LOG.info("There are no alarms are not present in the alarm list")

    # Save the list of new alarms present in the list
    new_alarms = []
    for alarm in new_active_alarm_table['values']:
        if (re.match(".", alarm[0].strip()) is not None):
            new_alarms.append(alarm[0])
            LOG.info( "The alarm ID in the alarm list table is: "
                            "{0}".format(alarm[0]))

    # Identify the new alarms
    new_alarm_list = list(set(new_alarms) - set(current_alarms))
    LOG.info(new_alarm_list)

    # Verify the new alarms are present in the historical list in state 'set'
    # Get the historical list of alarms
    hist_alarm_table = system_helper.get_events_table(num=15, uuid=True)

    for name in new_alarm_list:
        kwargs = {"Event Log ID": name}
        alarm_state = table_parser.get_values(hist_alarm_table, 'State', **kwargs)
        LOG.info('new alarm: %s  state: %s' % (name, alarm_state))
        if alarm_state != ['set']:
            LOG.info('Alarm state is incorrect')
            test_res = False
            break

    # Clear the alarm by unlocking the compute node
        LOG.info("Unlock compute and wait 30 seconds")
    compute_ssh = host_helper.unlock_host(host)
    time.sleep(30)

    #Verify the alarm clear is shown in the historical table
    LOG.info("Verify event-list command returns list of active alarms")
    hist_alarm_table = system_helper.get_events_table(num=15, uuid=True)

    for name in new_alarm_list:
        kwargs = {"Event Log ID": name}
        alarm_state = table_parser.get_values(hist_alarm_table, 'State', **kwargs)
        LOG.info('new alarm: %s  state: %s' % (name, alarm_state))
        if alarm_state != ['clear']:
            LOG.info('Alarm state is incorrect')
            test_res = False
            break

    #Verify the alarm disappears from the active alarm table
    LOG.info("Verify alarm-list command returns list of active alarms")
    res, out = cli.system('alarm-list', rtn_list=True)
    new_active_alarm_table = table_parser.table(out)

    active_alarms = []
    for alarm in new_active_alarm_table['values']:
        if re.match(".", alarm[0].strip()) is not None:
            active_alarms.append(alarm[0])
            LOG.info("The alarm ID in the alarm list table is: "
                     "{0}".format(alarm[0]))

    # Identify the new alarms
    for name in new_alarm_list:
        if name in active_alarms:
            LOG.info("The alarm was not cleared from the active alarm table")
            test_res = False
            break


