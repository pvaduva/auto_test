#!/usr/bin/env python

"""
Usage:
./test_sanityrefresh_collectlogs.py <FloatingIPAddress>

e.g.  ./test_sanityrefresh_collectlogs.py 10.10.10.2

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
        * return code of 0 on pass, or non-zero on fail
    """

    # Default return code (0 is pass, non-zero fail)
    rc = 0

    conn.sendline("sudo collect all")
    conn.prompt()
    resp = 0

    while resp < 3:
        conn.timeout=timeout
        resp = conn.expect(["\?", "assword\:", TARBALL_NAME, PROMPT, pexpect.TIMEOUT])
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
            break
            # scp it to /folk/cgts/logs
        elif resp == 4:
            logging.warning("Timed out before logs could be collected.  Please increase the collect timeout and try again.")
            logging.error("Test Result: FAILED")
            rc = 83

    return rc

if __name__ == "__main__":

    # Name of test
    test_name = "test_sanityrefresh_collectlogs"

    # Extract command line arguments
    if len(sys.argv) < 2:
        sys.exit("Usage: ./%s.py <Floating IP of host machine>" % test_name)
    else:
        floating_ip = sys.argv[1]
    
    # Enable logging
    test_start_time = datetime.datetime.now()
    logfile_name = test_name + "_" + test_start_time.strftime("%Y%m%d-%H%M%S")
    logfile_path = LOGFILE_BASE + logfile_name
    logging.basicConfig(level=logging.INFO, filename=logfile_path)
    logging.info("Starting %s at %s" % (test_name, test_start_time))

    # Establish connection
    conn = Session(timeout=TIMEOUT)
    conn.connect(hostname=floating_ip, username=USERNAME, password=PASSWORD)
    conn.setecho(ECHO)

    # Run test case and get return code
    rc = collect_logs(conn, COLLECT_TIMEOUT) 

    # Terminate connection
    conn.logout()
    conn.close() 

    # Test end time
    test_end_time = datetime.datetime.now()
    test_duration = test_end_time - test_start_time
    logging.info("Ending %s at %s" % (test_name, test_end_time))
    logging.info("Test ran for %s" % test_duration)

    # For HTEE, non-zero exit code is a failed test
    exit(rc)
