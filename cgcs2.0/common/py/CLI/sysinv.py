#!/usr/bin/python

""" This contains common functions related to system inventory. 
"""

import os
import sys
import re
import time
import random

# class is in non-standard location so refine python search path
sys.path.append(os.path.expanduser('~/wassp-repos/testcases/cgcs/cgcs2.0/common/py'))

from CLI.cli import *
from CLI import nova

def get_hostpersonality(conn, hostname):
    """ This function returns the personality of host.
        Inputs:
        * conn - ID of pexpect session
        * hostname - name of host to check personality of, e.g. storage
        Output:
        * Return string, either storage, compute, controller or,
        * Return resp (non-zero int value) if we fail
    """

    cmd = "system host-show %s" % hostname
    conn.sendline(cmd)
    resp = conn.expect([CONT_PERSONALITY, COMP_PERSONALITY, STOR_PERSONALITY,
                        pexpect.TIMEOUT])
    if resp == 0:
        host_type = "controller"
    elif resp == 1:
        host_type = "compute"
    elif resp == 2:
        host_type = "storage"
    elif resp == 3:
        logging.warning("Could not determine personality of host %s" % hostname)
        return resp

    logging.info("Host type of host %s is %s" % (hostname, host_type))
    conn.prompt()

    return host_type

def get_hosts(conn):
    """ This function checks the system for controllers, computes and storage nodes.
        Input:
        * conn - ID of pexpect session
        Output:
        Four lists - all hosts, controllers only, computes only, storage only
    """

    # Determine the hosts in the lab
    cont_hostname_list = []   # list of controllers by hostname
    comp_hostname_list = []   # list of computes by hostname
    stor_hostname_list = []   # list of storage nodes by hostname
    hostname_list = []        # list of all hostnames
    conn.sendline('system host-list')

    # Traverse the input buffer looking for controller, compute
    # and storage nodes.
    resp = 0
    while resp < 1:
        resp = conn.expect([HOSTNAME_MATCH_TBL, PROMPT, pexpect.TIMEOUT])

        if resp == 0:
            hostname_list.append(conn.match.group())

    conn.prompt()
    logging.info("Hostnames in the system: %s" % hostname_list)

    for host in hostname_list:
        value = get_hostshowvalue(conn, host,field="personality")
        if value.startswith("controller"):
            cont_hostname_list.append(host)
        elif value.startswith("compute"):
            comp_hostname_list.append(host)
        elif value.startswith("storage"):
            stor_hostname_list.append(host)

    logging.info("Controllers in system: %s" % cont_hostname_list)
    logging.info("Computes in system: %s" % comp_hostname_list)
    logging.info("Storage nodes in system: %s" % stor_hostname_list)

    return hostname_list, cont_hostname_list, comp_hostname_list, stor_hostname_list

def get_hostshowvalue(conn, hostname, field="availability"):
    """ This returns a value from the host show table, e.g. host or state
        Inputs:
        * conn - ID of pexpect session
        * hostname - name of host, e.g. controller-0 
        * field is the type of data to return from the host show table, e.g. administrative, availability 
          note1: this field needs to match with a field in the actual host show table
          note2: this has not been tested with all field types
          note3: if field is not provided, we assume you want the availability 
        Outputs:
        * hostname - hostname of machine hosting VM, e.g. compute-0, controller-1, etc. or
        * resp - non-zero value if we didn't match
    """

    # Pull the value field associated with the corresponding property field
    # Note, only tested with the "host" field so far
    extract = "(?<=%s)\s*\|\s(.*?)\s*\|\r\n" % field

    cmd = "system host-show %s" % hostname 

    conn.prompt()
    conn.sendline(cmd)

    resp = conn.expect([extract, ERROR, PROMPT, pexpect.TIMEOUT])
    if resp == 0:
        value = conn.match.group(1)
        conn.prompt()
        logging.info("%s has %s field equal to %s" % (hostname, field, value))
        return value
    elif resp == 1:
        logging.warning("Could not determine value of field %s associated with %s" % (field, hostname))
        return resp
    elif resp == 3:
        logging.warning("Command %s timed out." % cmd)
        return resp

def lock_host(conn, hostname=None):
    """ This function locks a specific host.
        Input:
        * conn - ID of pexpect
        Output:
        * True if the host could be locked, False if the lock failed
    """

    cmd = "system host-lock %s" %  hostname
    conn.sendline(cmd)
    resp = conn.expect([PROMPT, ERROR, pexpect.TIMEOUT, "(Avoiding.*)"])
    if resp == 1 or resp == 3:
        logging.error("Unable to lock %s due to %s" % (hostname, conn.match.group()))
        return False
    elif resp == 2:
        logging.warning("Command %s timed out" % cmd)
        return False

    return True   

def unlock_host(conn, hostname=None):
    """ This function unlocks a specific host.
        Input:
        * conn - ID of pexpect
        Output:
        * True if the host could be unlocked, False if the unlock failed
    """

    cmd = "system host-unlock %s" %  hostname
    conn.sendline(cmd)
    resp = conn.expect([PROMPT, ERROR, pexpect.TIMEOUT, "(Avoiding.*)"])
    if resp == 1 or resp == 3:
        logging.error("Unable to lock %s due to %s" % (hostname, conn.match.group()))
        return False
    elif resp == 2:
        logging.warning("Command %s timed out" % cmd)
        return False

    return True   

def check_smallfootprint(conn):
    """ This function checks to see if the system is configured for small footprint.
        Inputs:
        * conn - ID of pexpect session
        Output:
        * True if we are small footprint enabled or False if we are not
    """

    # Determine the hosts in the lab
    hostname_list, cont_hostname_list, comp_hostname_list, stor_hostname_list = get_hosts(conn)

    # Take one of the controllers, and check for the subfunctions field
    # Subfunctions is only displayed on small footprint nodes not regular systems
    result = get_hostshowvalue(conn, cont_hostname_list[0], "subfunctions")    
    if type(result) is str:
        if result == "controller, compute":
            return True
    else:
        return False 

