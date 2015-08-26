#!/usr/bin/python

""" This contains common functions related to nova. 
"""

import os
import sys
import re
import time
import random

# class is in non-standard location so refine python search path
sys.path.append(os.path.expanduser('~/wassp-repos/testcases/cgcs/cgcs2.0/common/py'))

from CLI.cli import *

def source_nova(conn, user=None):
    """ This function sources the desired openrc file.
        Inputs:
        * conn (string) - ID of pexpect session
        * user (string) (optional) - user name, e.g. tenant1, tenant2
        Outputs:
        * resp (integer) - 0 if successful
        Tag:
        * Add to common functions
    """

    # admin user is the default
    cmd = "source /etc/nova/openrc"
    if user:
        cmd = "source ./openrc." + user

    conn.sendline(cmd)

    # Check if the command succeeded or if we had errors
    resp = conn.expect([PROMPT, "-sh:.*\r\n", pexpect.TIMEOUT])
    if resp == 2:
        logging.warning("Unable to %s due to %s" % (cmd, conn.match.group()))
    elif resp == 3:
        logging.warning("Command %s timed out." % cmd)

    return resp

def get_novavms(conn, return_value="id", tenant_name=None):
    """ This functions does one of two things.  It does the equivalent of
        nova list --all-tenants if a tenant_name is not supplied as an
        argument.

        Or it does nova list --tenant <tenant_id> if the tenant_name, e.g.
        tenant2, is supplied.

        To keep it easy for the user, it takes the tenant_name and does a
        lookup via keystone or openstack to extract the ID or name associated
        with that tenant.

        Inputs:
        * conn (string) - ID of pexpect session
        * return_value (string) - accepts either id or name, depending on
          whether the user wants the function to return vms by name or id
        * tenant_name - optional parameter to specify a tenant, e.g. tenant1
        Outputs:
        * Returns a list of VM ids or names.  Note, this list can be empty.
    """

    vm_list = []

    # Determine which nova list command to use depending on the arguments supplied to
    # the function
    cmd = "nova list --all-tenants"
    if tenant_name:
        tenant_id = get_userid(conn, tenant_name)
        cmd = "nova list --tenant %s" % tenant_id

    conn.sendline(cmd)

    # determine if we should return a list of vm names or IDs
    if return_value == "name":
        extract = "(?<=\r\n\|\s[0-9a-f-]{36}\s\|\s)([0-9a-zA-Z-]+)"
    else:
        extract = "(?<=\r\n\|\s)([0-9a-f-]{36})"

    resp = 0
    while resp < 1:
        resp = conn.expect([extract, ERROR, PROMPT, pexpect.TIMEOUT])
        if resp == 0:
            vm_list.append(conn.match.group())
        elif resp == 1:
            msg = "Error listing nova VMs due to %s" % conn.match.group()
            logging.warning(msg)
        elif resp == 3:
            msg = "Command %s timed out" % cmd
            logging.warning(msg)

    #conn.prompt()
    logging.info("VM list by %s: %s" % (return_value, vm_list))

    return vm_list


def get_novashowvalue(conn, vm_id, field=None):
    """ This returns a value from the nova show table, e.g. host or state
        Inputs:
        * conn - ID of pexpect session
        * vm_id - ID of VM to query
        * field is the type of data to return from the nova show table, e.g. host, vm_state, etc.
          note1: this field needs to match with a field in the actual nova show table
          note2: this has not been tested with all field types, only host and vm_state
          note3: if field is not provided, we assume you want the host the vm is on
        Outputs:
        * hostname - hostname of machine hosting VM, e.g. compute-0, controller-1, etc. or
        * resp - non-zero value if we didn't match
    """

    # Assume the user wants the host the VM is on if field is None
    if not field:
        field == "host"

    # Pull the value field associated with the corresponding property field
    # Note, only tested with the "host" field so far
    extract = "(?<=%s)\s*\|\s(.*?)\s*\|\r\n" % field

    cmd = "nova show %s" % vm_id
    
    conn.prompt()
    conn.sendline(cmd)

    resp = conn.expect([extract, ERROR, PROMPT, pexpect.TIMEOUT])
    if resp == 0:
        value = conn.match.group(1)
        conn.prompt()
        logging.info("VM %s has %s field equal to %s" % (vm_id, field, value))
        return value
    elif resp == 1:
        logging.warning("Could not determine value of field %s associated with VM %s" % (field, vm_id))
        return resp
    elif resp == 3:
        logging.warning("Command %s timed out." % cmd)
        return resp

    #return value

def exec_novaresizeorrevert(conn, vm_id, nova_option=None):
    """ This issues a resize confirm after cold migration.
        Inputs:
        * conn - ID of pexpect session
        * vm_id - ID of VM to query
        * nova_option (optional) - takes two options, confirm or revert.
                                 - confirm is the default
        Outputs:
        * Return resp - 0 for success, non-zero for fail
    """

    # Resize is the default (if the option is not specified)
    if nova_option == "revert":
        cmd = "nova resize-revert %s" % vm_id
    else:
        cmd = "nova resize-confirm %s" % vm_id


    conn.prompt()
    conn.sendline(cmd)
    logging.info(cmd)
    resp = conn.expect([PROMPT, ERROR, pexpect.TIMEOUT])
    if resp == 1:
        logging.error("Failed to resize-confirm VM %s due to %s" % (vm_id, conn.match.group()))
        return resp
    elif resp == 2:
        logging.warning("Command %s timed out." % cmd)
        return resp

    return resp

