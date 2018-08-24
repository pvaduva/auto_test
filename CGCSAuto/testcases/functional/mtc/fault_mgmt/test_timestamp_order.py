# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

import time

from pytest import fixture, mark

from keywords import system_helper
from utils import table_parser
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG


def check_timestamps_order(table_):
    timestamps = table_parser.get_column(table_, 'Time Stamp')
    for i in range(len(timestamps) - 1):
        current_stamp = timestamps[i]
        prev_stamp = timestamps[i+1]
        assert current_stamp >= prev_stamp, "Time Stamp {} is smaller than previous stamp in table: \n{}".\
            format(current_stamp, table_)


@fixture()
def generate_alarms(request):
    alarm_id = '300.005'

    def del_alarms():
        LOG.fixture_step("Delete 300.005 alarms and ensure they are removed from alarm-list")
        alarms_tab = system_helper.get_alarms_table(uuid=True)
        alarm_uuids = table_parser.get_values(table_=alarms_tab, target_header='UUID', **{'Alarm ID': alarm_id})
        if alarm_uuids:
            system_helper.delete_alarms(alarms=alarm_uuids)

        post_del_alarms = system_helper.get_alarms(alarm_id=alarm_id)
        assert not post_del_alarms, "300.005 alarm still exits after deletion"
    request.addfinalizer(del_alarms)

    LOG.fixture_step("Generate 10 active alarms with alarm_id 900.00x")
    alarm_gen_base = "fmClientCli -c '### ###300.005###set###system.vm###host=autohost-{}### ###critical###" \
                     "Automation test###processing-error###cpu-cycles-limit-exceeded### ###True###True###'"

    con_ssh = ControllerClient.get_active_controller()
    for i in range(10):
        LOG.info("Create an critical alarm with id {}".format(alarm_id))
        alarm_gen_cmd = alarm_gen_base.format(i)
        con_ssh.exec_cmd(alarm_gen_cmd, fail_ok=False)
        time.sleep(1)

    return alarm_id


@mark.p3
def test_alarms_and_events_timestamp_order(generate_alarms):
    """
    Verify the chronological order to the alarms

    Scenario:
    1. Query the events and alarms table
    2. Verify the list is shown most recent alarm to oldest (based on timestamp) [REQ-14]
    """
    alarm_id = generate_alarms

    LOG.tc_step("Check system events are displayed in chronological order")
    events_table = system_helper.get_events_table(num=15, uuid=True)
    check_timestamps_order(events_table)

    LOG.tc_step("Check active alarms are displayed in chronological order")
    alarms_table = system_helper.get_alarms_table()
    assert 10 == len(table_parser.get_values(alarms_table, 'UUID', **{'Alarm ID': alarm_id})), "Unexpected alarm count"

    check_timestamps_order(table_=alarms_table)
