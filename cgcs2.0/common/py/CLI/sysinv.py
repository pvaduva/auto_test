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

    # For each hostname grab its personality from system host-show
    for host in hostname_list:
        cmd = "system host-show %s" % host
        conn.sendline(cmd)
        resp = conn.expect([CONT_PERSONALITY, COMP_PERSONALITY, STOR_PERSONALITY,
                            pexpect.TIMEOUT])
        if resp == 0:
            cont_hostname_list.append(host)
        elif resp == 1:
            comp_hostname_list.append(host)
        elif resp == 2:
            stor_hostname_list.append(host)
        conn.prompt()

    logging.info("Controllers in system: %s" % cont_hostname_list)
    logging.info("Computes in system: %s" % comp_hostname_list)
    logging.info("Storage nodes in system: %s" % stor_hostname_list)

    return hostname_list, cont_hostname_list, comp_hostname_list, stor_hostname_list

