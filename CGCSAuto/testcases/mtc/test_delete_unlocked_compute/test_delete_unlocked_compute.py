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

CONTROLLER_PROMPT = ['.*controller\-[01].*\$ ', 'keystone_admin']


def cmd_execute(action, check_params='', prompt=CONTROLLER_PROMPT):
    """
    Function to execute a command on a host machine
    """

    param_found = False

    controller_ssh = ControllerClient.get_active_controller()
    controller_ssh.set_prompt(prompt)
    exitcode, output = controller_ssh.exec_cmd('%s' % action, expect_timeout=60)
    #print("Output: %s" % output)
    if any(val in output for val in check_params):
        param_found = True

    return param_found, output


@fixture(scope='module')
def find_unlocked_computes():
    computes = system_helper.get_computes()
    unlocked = []
    for node in computes:
        if host_helper.get_hostshow_value(node, 'administrative').lower() == 'unlocked':
            unlocked.append(node)

    return unlocked


def test_delete_unlocked_compute(find_unlocked_computes):
    """
    Attempts to delete each unlocked compute node.
    Fails if one unlocked compute node does get deleted.

    Skip Condition:
        - There are no unlocked compute nodes

    Test Steps:
        - Creates a list of every unlocked compute node
        - Iterate through each node and attempt to delete it
        - Verify that each compute node rejected the delete request

    """

    computes = find_unlocked_computes
    if not computes:
        skip("There are no unlocked compute nodes.")

    deleted_nodes = []

    for node in computes:
        LOG.tc_step("attempting to delete {}".format(node))
        cmd = 'source /etc/nova/openrc; system host-delete {}'.format(node)
        res, out = cmd_execute(cmd)

        LOG.tc_step("Delete request - result: {}\tout: {}".format(res, out))

        if 'Deleted host' in out:
            LOG.tc_step("{} was deleted.".format(node))
            deleted_nodes.append(node)
            continue

        LOG.tc_step("Confirming that the node was not deleted")
        cmd = 'source /etc/nova/openrc; system host-show {}'.format(node)
        res, out = cmd_execute(cmd)

        if 'host not found' in out:
            #the node was deleted even though it said it wasn't
            LOG.tc_step("{} was deleted.".format(node))
            deleted_nodes.append(node)

    assert not deleted_nodes, "Fail: Delete request for the following compute node(s) " \
                              "{} were accepted.".format(deleted_nodes)
