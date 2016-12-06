# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

import re
from datetime import timedelta

from pytest import fixture, mark, skip, raises, fail
from utils.tis_log import LOG
from utils import cli, exceptions, table_parser
from utils.ssh import ControllerClient, ssh_to_controller0
from consts.auth import Tenant
from keywords import vm_helper, nova_helper, system_helper, host_helper, cinder_helper, glance_helper,  common


@mark.p3
def test_alarm_overwritten():
    """
    Verify the chronological order to the alarms

    Scenario:
    1. Query the alarm table
    2. Verify the list is shown most recent alarm to oldest (based on timestamp) [REQ-14]
    """
    output = cli.system('event-list', '--limit 10 --nowrap --nopaging --uuid',
                                  auth_info=Tenant.ADMIN)
    alarm_table = table_parser.table(output, combine_multiline_entry=True)
    size = len(alarm_table['values'])

    LOG.info('Get the last entry in the alarm table')
    last_alarm = alarm_table['values'][size - 1][0]
    secondlast_alarm = alarm_table['values'][size-2][0]
    LOG.info("last_alarm = %s" % last_alarm)
    LOG.info("secondlast_alarm = %s" % secondlast_alarm)

    time_1 = alarm_table['values'][size - 1][1]
    time_2 = alarm_table['values'][size - 2][1]

    # The last alarm should be older than the second last
    assert (common.get_timedelta_for_isotimes(time_1, time_2).total_seconds() > 0 or
            time_1.split('.')[1] < time_2.split('.')[1])
