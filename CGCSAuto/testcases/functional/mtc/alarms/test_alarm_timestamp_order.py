# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

import re
import sys
from pytest import fixture, mark, skip, raises, fail
from utils.tis_log import LOG
from utils import cli, exceptions, table_parser
from utils.ssh import ControllerClient, ssh_to_controller0
from consts.auth import Tenant
from keywords import vm_helper, nova_helper, system_helper, host_helper, cinder_helper, glance_helper


def test_alarm_timestamp_order():
    """
    Verify the chronological order to the alarms

    Scenario:
    1. Query the alarm table
    2. Verify the list is shown most recent alarm to oldest (based on timestamp) [REQ-14]
    """
    alarms_list = system_helper.get_events_table(num=15, uuid=True)

    LOG.info('Verify the order of the timestamp of each entry')
    # Note the timestamp format will be, e.g 2014-06-25T16:58:57.324613
    previous_timestamp = ""
    for alarm in alarms_list['values']:
        LOG.info("The current alarm timestamp is: %s" % alarm[1])
        LOG.info("The previous time stamp is: %s" % previous_timestamp)
        if previous_timestamp == '':
            previous_timestamp = alarm[1]
        elif previous_timestamp >= alarm[1]:
            previous_timestamp = alarm[1]
        else:
            assertion_text = "Data is not in reverse chronological order"
            test_result = False
            assert test_result, assertion_text
