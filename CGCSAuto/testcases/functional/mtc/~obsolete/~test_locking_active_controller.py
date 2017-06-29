# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

import logging
import time
import re
import sys
from pytest import fixture, mark, skip, raises, fail
from utils.tis_log import LOG
from utils import cli, exceptions
from utils.ssh import ControllerClient
from keywords import vm_helper, nova_helper, system_helper, host_helper, cinder_helper, glance_helper


@mark.domain_sanity
def test_locking_active_controller():
    """
    Finds the active controller and attempts to lock it..

    Skip Conditions:
         - The active controller is already locked

    Test Steps:
        - Finds active controller
        - Checks that the controller is not locked already
        - Attempts to lock controller through CLI
        - Checks the output and status of the controller

    """
    if system_helper.is_simplex():
        skip("Not applicable to Simplex system")

    name = system_helper.get_active_controller_name()
    LOG.tc_step("Attempting to lock {}".format(name))
    res, out = host_helper.lock_host(host=name, fail_ok=True)
    LOG.tc_step("Result of the lock was: {}".format(res))

    status = host_helper.get_hostshow_value(name, 'administrative')

    assert res in [1, 4], "Fail: The lock request was not rejected: {}.".format(out)
    assert status == 'unlocked', "Fail: The active controller was locked."
