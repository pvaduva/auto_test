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

def get_userid(conn, user):
    """ Returns the user ID from the keystone tenant-list or
        openstack project-list.
        Inputs:
        * conn (string) - ID of a pexpect session
        * user (string) - name of a user, e.g. tenant1, tenant2, admin, etc.
        Outputs:
        * user_id (string) - a valid user ID or empty string if user ID was not
          found
        Tags:
        * Add to common functions
    """

    user_id = ""

    cmd1 = "openstack project list"
    cmd = "keystone tenant-list"

    # We will use the deprecated commands unless the flag is true
    if USE_NEWCMDS:
        cmd = cmd1

    conn.sendline(cmd)

    resp = 0
    while resp < 1:
        # Extract the 32 character user ID
        extract = "([0-9a-f]{32})(?=\s\| %s)" % user
        resp = conn.expect([extract, PROMPT, pexpect.TIMEOUT])
        if resp == 0:
            user_id = conn.match.group()
            logging.info("The ID of %s is %s" % (user, user_id))
        elif resp == 2:
            logging.error("Unable to get ID for %s" % user)

    return user_id

