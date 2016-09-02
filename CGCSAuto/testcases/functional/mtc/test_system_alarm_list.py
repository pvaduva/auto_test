# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

import time

from pytest import mark

from utils import table_parser, cli
from utils.tis_log import LOG

from keywords import system_helper, host_helper

from testfixtures.recover_hosts import HostsToRecover


@mark.sanity
def test_system_alarm_list_on_compute_reboot():
    """
    Verify system alarm-list command in the system

    Scenario:
    1. Execute "system alarm-list" command in the system.
    2. Reboot one active computes and wait 30 seconds.
    3. Verify commands return list of active alarms in table with expected
    rows.
    """

    # Clear the alarms currently present
    LOG.tc_step("Clear the alarms table")
    system_helper.delete_alarms()

    LOG.tc_step("Check alarm-list table consists of correct headers")
    alarms_tab = system_helper.get_alarms_table(uuid=True)
    # Verify that the alarm table contains the correct headers
    expt_headers = ['UUID', 'Alarm ID', 'Reason Text', 'Entity ID', 'Severity', 'Time Stamp']

    assert expt_headers == alarms_tab['headers'], "alarm-list headers not correct. Actual: {0}; Expected: {1}".format(
            alarms_tab['headers'], expt_headers)

    LOG.tc_step("Reboot a nova hypervisor host and wait for hypervisor state up")
    compute_host = host_helper.get_nova_hosts()[0]
    host_helper.reboot_hosts(compute_host, wait_for_reboot_finish=True)
    time.sleep(20)

    LOG.tc_step("Verify no active alarm generated after reboot completes")
    post_alarms_tab = system_helper.get_alarms_table(uuid=True)
    post_alarms_tab = table_parser.filter_table(post_alarms_tab, strict=False, **{'Entity ID': compute_host})
    post_alarms = table_parser.get_column(post_alarms_tab, 'UUID')

    assert not post_alarms, "Alarm(s) generated after {} reboot: \n{}".format(compute_host, post_alarms_tab)


@mark.sanity
def test_system_alarm_show_on_lock_unlock_compute():
    """
    Verify system alarm-show command

    Test Steps:
    1. Lock one nova compute host
    2. Execute system alarm list and get uuid.
    3. Execute system alarm-show <uuid>.
    4. Verify alarm-list and alarm-show values are in sync
    5. Unlock nova compute host
    6. Verify system alarm-list and check if there is no entries compute host related entries displayed.

    """

    # Clear the alarms currently present
    LOG.tc_step("Clear the alarms table")
    system_helper.delete_alarms()

    # Raise a new alarm by locking a compute node
    # Get the compute
    compute_host = host_helper.get_nova_hosts()[0]
    if compute_host == system_helper.get_active_controller_name():
        compute_host = system_helper.get_standby_controller_name()

    LOG.tc_step("Lock a nova hypervisor host {}".format(compute_host))
    HostsToRecover.add(compute_host)
    host_helper.lock_host(compute_host)
    time.sleep(20)

    LOG.tc_step("Check system alarm-list after locking")
    post_lock_alarms_tab = system_helper.get_alarms_table(uuid=True)
    post_lock_alarms_tab = table_parser.filter_table(post_lock_alarms_tab, strict=False,
                                                     **{'Reason Text': compute_host})

    post_lock_alarms = table_parser.get_column(post_lock_alarms_tab, 'UUID')

    LOG.info("{} related active alarms: \n{}".format(compute_host, post_lock_alarms_tab))

    # Verify that the alarm table contains the correct alarm

    alarms_l = ['Alarm ID', 'Entity ID', 'Severity', 'Reason Text']
    alarms_s = ['alarm_id', 'entity_instance_id', 'severity', 'reason_text']

    for post_alarm in post_lock_alarms:
        LOG.tc_step("Verify {} for alarm {} in alarm-list are in sync with alarm-show".format(alarms_l, post_alarm))

        alarm_show_tab = table_parser.table(cli.system('alarm-show', post_alarm))
        alarm_list_tab = table_parser.filter_table(post_lock_alarms_tab, UUID=post_alarm)

        for i in range(len(alarms_l)):
            alarm_l_val = table_parser.get_column(alarm_list_tab, alarms_l[i])[0]
            alarm_s_val = table_parser.get_value_two_col_table(alarm_show_tab, alarms_s[i])

            assert alarm_l_val == alarm_s_val, "{} value in alarm-list: {} is not in synce with alarm-show: {}".format(
                alarms_l[i], alarm_l_val, alarm_s_val)

    LOG.tc_step("Unlock compute and wait for hypervisor state up")
    host_helper.unlock_host(compute_host)
    time.sleep(30)

    LOG.tc_step("Verify that alarms generated due to lock compute is destroyed from alarm list table")
    post_unlock_alarms_tab = system_helper.get_alarms_table(uuid=True)
    post_unlock_alarms = table_parser.get_values(post_unlock_alarms_tab, 'UUID', **{'Reason Text': compute_host})

    assert not post_unlock_alarms, "Some alarm(s) still exist after unlock: {}. Alarms before unlock: {}".format(
            post_unlock_alarms, post_lock_alarms)
