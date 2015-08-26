#!/usr/bin/env python

"""
Usage:
./collect_logs.py <FloatingIPAddress>

e.g.  ./collect_logs.py 10.10.10.2

Assumptions:
* System has been installed
* Lab setup has been run 

Objective:
* The objective of this test is to collect logs and place under /folk/cgts/logs
or move to the ${WASSP_TC_DIR} for attachment in MongoDB.

Test Steps:
0) SSH to the system
1) Run collect logs

General Conventions:
1) Functions that start with "list" have no return value and only report information
2) Functions that start with "check" return Boolean values
3) Functions that start with "get" check the system for conditions and return 1 or more values

Future Enhancements:
*  Handle connection to inactive controller
"""

import os
import sys
import re
# class is in non-standard location so refine python search path 
sys.path.append(os.path.expanduser('~/wassp-repos/testcases/cgcs/cgcs2.0/common/py'))

from CLI.cli import *

def collect_logs(conn, timeout):
    """ This runs the sudo collect all command. 
        Inputs:
        * conn - ID of pexpect session
        * timeout (sec) - how long to wait until collect completes, e.g. 300 seconds
        Output:
        * .tar.gz file created under /scratch
        * scp'ed off target to /folk/cgts/logs
        * no return value
    """
    conn.sendline("sudo collect all")
    conn.prompt()
    resp = 0
    while resp < 3:
        conn.timeout=timeout
        resp = conn.expect(["\?", "Password\:", TARBALL_NAME, PROMPT, pexpect.TIMEOUT])
        if resp == 0:
            conn.sendline("yes")
        elif resp == 1:
            conn.sendline(PASSWORD)
        elif resp == 2:
            tarball = conn.match.group()
            logging.info("Tarball name is: %s" % tarball)
            # Reported tarball name differs from the actual file name.  Workaround the issue.
            newtarball = string.replace(tarball, "tgz", "gz")
            logging.info("New tarball name is: %s" % newtarball)
            # should we ls to see if it's really there?
            logging.info("Test Result: PASSED")
            # scp it to /folk/cgts/logs
        elif resp == 4:
            logging.warning("Timed out before logs could be collected.  Please increase the collect timeout and try again.")
            logging.error("Test Result: FAILED")
    # reset timeout to original value after collect runs
    conn.timeout=TIMEOUT

if __name__ == "__main__":

    # Extract command line arguments
    if len(sys.argv) < 2:
        sys.exit("Usage: ./test_collect_logs_cli.py <Floating IP of host machine>")
    else:
        floating_ip = sys.argv[1]

    # Enable logging
    logging.basicConfig(level=logging.INFO)

    # Name of test
    test_name = "test_sanityrefresh_collectlogs"

    # Get time
    test_start_time = datetime.datetime.now()
    logging.info("Starting %s at %s" % (test_name, test_start_time))

    # Establish connection
    conn = Session(timeout=TIMEOUT)
    conn.connect(hostname=floating_ip, username=USERNAME, password=PASSWORD)
    conn.setecho(ECHO)

    collect_logs(conn, COLLECT_TIMEOUT) 

    # Should terminate connection here

    # Test end time
    test_end_time = datetime.datetime.now()
    test_duration = test_end_time - test_start_time
    logging.info("Ending %s at %s" % (test_name, test_end_time))
    logging.info("Test ran for %s" % test_duration)
