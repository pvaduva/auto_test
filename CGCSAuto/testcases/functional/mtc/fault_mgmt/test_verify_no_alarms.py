# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

from utils.tis_log import LOG
from utils import cli

allowable_alarms=['100.104', '100.114', '400.001']

# remove following test case since alarms are checked before and after each test.


def _test_tc4693_verify_no_alarms():
    """Method to list alarms
    """

    # list the alarms

    alarms_found = False

    output = cli.fm('alarm-list')

    LOG.tc_step("Check no unexpected alarms in output for fm alarm-list: \n%s" % output)

    if (('warning' in output) or
            ('minor' in output) or
            ('major' in output) or
            ('critical' in output)):
        if not (any(val in output for val in allowable_alarms)):
            alarms_found = True

    assert not alarms_found
