# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

from pytest import fixture, mark, skip, raises, fail

import copy
import datetime
import time
import sys
from utils.ssh import ControllerClient
from utils.tis_log import LOG
from utils import cli, exceptions

CONTROLLER_PROMPT = '.*controller\-[01].*\$ '



def cmd_execute(action, param=''):
    """
    Function to execute a command on a host machine
    """

    alarms_found = False

    controller_ssh = ControllerClient.get_active_controller()
    controller_ssh.set_prompt(CONTROLLER_PROMPT)
    exitcode, output = controller_ssh.exec_cmd('%s %s' % (action, param), expect_timeout=20)

    print("Output: %s" % output)
    if (('warning' in output) or 
        ('minor' in output) or 
        ('major' in output) or 
        ('critical' in output)):
        alarms_found = True

    return alarms_found

def test_tc4693_verify_no_alarms():
    """Method to list alarms
    """

    # list the alarms
    cmd = ("source /etc/nova/openrc; system alarm-list")
    print ("Command sent: %s" % cmd)
    result = cmd_execute(cmd)
    assert not result


