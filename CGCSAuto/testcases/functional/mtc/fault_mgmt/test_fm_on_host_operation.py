# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

import time

from pytest import mark, skip

from utils import table_parser, cli
from utils.tis_log import LOG

from consts.cgcs import EventLogID
from keywords import system_helper, host_helper, common

from testfixtures.recover_hosts import HostsToRecover


# Remove following test - alarm checking is already covered by check_alarms fixture which
# is auto used by most testcases - table headers checking is of low priority
# @mark.sanity
# def _test_system_alarm_list_on_compute_reboot():
#     """
#     Verify fm alarm-list command in the system
#
#     Scenario:
#     1. Execute "fm alarm-list" command in the system.
#     2. Reboot one active computes and wait 30 seconds.
#     3. Verify commands return list of active alarms in table with expected
#     rows.
#     """
#
#     # # Clear the alarms currently present
#     # LOG.tc_step("Clear the alarms table")
#     # system_helper.delete_alarms()
#
#     LOG.tc_step("Check alarm-list table consists of correct headers")
#     alarms_tab = system_helper.get_alarms_table(uuid=True)
#     # Verify that the alarm table contains the correct headers
#     expt_headers = ['UUID', 'Alarm ID', 'Reason Text', 'Entity ID', 'Severity', 'Time Stamp']
#
#     assert expt_headers == alarms_tab['headers'], "alarm-list headers not correct. Actual: {0}; Expected: {1}".format(
#             alarms_tab['headers'], expt_headers)
#
#     LOG.tc_step("Reboot a nova hypervisor host and wait for hypervisor state up")
#     compute_host = host_helper.get_up_hypervisors()[0]
#     host_helper.reboot_hosts(compute_host)
#     time.sleep(20)
#
#     LOG.tc_step("Verify no active alarm generated after reboot completes")
#     post_alarms_tab = system_helper.get_alarms_table(uuid=True)
#     post_alarms_tab = table_parser.filter_table(post_alarms_tab, strict=False, **{'Entity ID': compute_host})
#     post_alarms = table_parser.get_column(post_alarms_tab, 'UUID')
#
#     assert not post_alarms, "Alarm(s) generated after {} reboot: \n{}".format(compute_host, post_alarms_tab)


@mark.sanity
def test_system_alarms_and_events_on_lock_unlock_compute(no_simplex):
    """
    Verify fm alarm-show command

    Test Steps:
    - Delete active alarms
    - Lock a host
    - Check active alarm generated for host lock
    - Check relative values are the same in fm alarm-list and fm alarm-show <uuid>
    - Check host lock 'set' event logged via fm event-list
    - Unlock host
    - Check active alarms cleared via fm alarm-list
    - Check host lock 'clear' event logged via fm event-list
    """

    # Remove following step because it's unnecessary and fails the test when alarm is re-generated
    # # Clear the alarms currently present
    # LOG.tc_step("Clear the alarms table")
    # system_helper.delete_alarms()

    # Raise a new alarm by locking a compute node
    # Get the compute
    compute_host = host_helper.get_up_hypervisors()[0]
    if compute_host == system_helper.get_active_controller_name():
        compute_host = system_helper.get_standby_controller_name()
        if not compute_host:
            skip('Standby controller unavailable')

    LOG.tc_step("Lock a nova hypervisor host {}".format(compute_host))
    pre_lock_time = common.get_date_in_format()
    HostsToRecover.add(compute_host)
    host_helper.lock_host(compute_host)

    LOG.tc_step("Check host lock alarm is generated")
    post_lock_alarms = system_helper.wait_for_alarm(field='UUID', entity_id=compute_host, reason=compute_host,
                                                    alarm_id=EventLogID.HOST_LOCK, strict=False, fail_ok=False)[1]

    LOG.tc_step("Check related fields in fm alarm-list and fm alarm-show are of the same values")
    post_lock_alarms_tab = system_helper.get_alarms_table(uuid=True)

    alarms_l = ['Alarm ID', 'Entity ID', 'Severity', 'Reason Text']
    alarms_s = ['alarm_id', 'entity_instance_id', 'severity', 'reason_text']

    # Only 1 alarm since we are now checking the specific alarm ID
    for post_alarm in post_lock_alarms:
        LOG.tc_step("Verify {} for alarm {} in alarm-list are in sync with alarm-show".format(alarms_l, post_alarm))

        alarm_show_tab = table_parser.table(cli.fm('alarm-show', post_alarm)[1])
        alarm_list_tab = table_parser.filter_table(post_lock_alarms_tab, UUID=post_alarm)

        for i in range(len(alarms_l)):
            alarm_l_val = table_parser.get_column(alarm_list_tab, alarms_l[i])[0]
            alarm_s_val = table_parser.get_value_two_col_table(alarm_show_tab, alarms_s[i])

            assert alarm_l_val == alarm_s_val, "{} value in alarm-list: {} is different than alarm-show: {}".format(
                alarms_l[i], alarm_l_val, alarm_s_val)

    LOG.tc_step("Check host lock is logged via fm event-list")
    system_helper.wait_for_events(entity_instance_id=compute_host, start=pre_lock_time, timeout=60,
                                  event_log_id=EventLogID.HOST_LOCK, fail_ok=False, **{'state': 'set'})

    pre_unlock_time = common.get_date_in_format()
    LOG.tc_step("Unlock {}".format(compute_host))
    host_helper.unlock_host(compute_host)

    LOG.tc_step("Check host lock active alarm cleared")
    alarm_sets = [(EventLogID.HOST_LOCK, compute_host)]
    system_helper.wait_for_alarms_gone(alarm_sets, fail_ok=False)

    LOG.tc_step("Check host lock clear event logged")
    system_helper.wait_for_events(event_log_id=EventLogID.HOST_LOCK, start=pre_unlock_time,
                                  entity_instance_id=compute_host, fail_ok=False, **{'state': 'clear'})
