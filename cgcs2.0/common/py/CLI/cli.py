#!/usr/bin/env python
# vim: ft=python ts=4 sw=4 et ai:

"""
Description:
This class extends pxssh, which is an extension on pxpect.  It has an initialization method which 
is tied to the parent constructor, and a connect method which establishes a connection.  No other 
methods are currently defined.  

Common regex matches are stored in a common constants file, which the developer can utilize or write
their own. 

Inputs:
* None

Assumptions:
* None

To be done:
- Take command line args for self-test
- Extract self-test code into methods that users can invoke

"""


# imports
from constants import *
import datetime
import logging
import os
import pexpect
import pxssh
import string
import sys

# set debug to false
DEBUG=True

class Session(pxssh.pxssh):
    """ Class for initiating a pexpect pxssh session. 
    """

    def __init__(self,  *args, **kwargs):
        """ Initialize connection class.
        """
        self.timeout = kwargs.get('timeout', TIMEOUT)
        # Chain to parent constructor
        pxssh.pxssh.__init__(self, *args, **kwargs)

    def connect(self, hostname, username, password):
        """ Method to establish a connection to a host.
        """

        try:
            logging.info("Connecting to %s using username %s and password %s" %
                        (hostname, username, password))

            self.SSH_OPTS = " -o 'StrictHostKeyChecking=no'" + \
                            " -o 'UserKnownHostsFile=/dev/null'"
            self.PROMPT = PROMPT
            self.force_password = True
            self.login(hostname, username, password, auto_prompt_reset=False, quiet=False)
            logging.info(self.before)
            #logfile_out = open(LOGFILE, 'w+')
            self.logfile_read = sys.stdout

        except pxssh.ExceptionPxssh as err:
            logging.error("pxssh failed on login due to %s" % err)
            self.close()

        except pexpect.EOF as err:
            logging.error("pxssh failed on login due to %s" % err)
            self.close()

if __name__ == "__main__":

    # Enable logging
    logging.basicConfig(level=logging.INFO)

    # Get time
    test_start_time = datetime.datetime.now()
    logging.info("Starting self test at %s" % test_start_time) 

    # Establish connection
    conn = Session(timeout=TIMEOUT)
    conn.connect(hostname=HOSTNAME, username=USERNAME, password=PASSWORD)
    conn.setecho(ECHO)

    # Determine which host we're connected to and return the hostname
    conn.sendline("cat /etc/hostname")
    resp = conn.expect(HOSTNAME_MATCH)
    current_host = conn.match.group()
    if current_host:
        logging.info("We're connected to host %s" % current_host)
    else:
        logging.warning("Unable to determine name of host")
        # Should we terminate?

    # Cat the build info and extract the build type 
    conn.sendline("cat /etc/build.info")
    resp = conn.expect(["Formal", pexpect.TIMEOUT])
    build_type = conn.match.group()
    if build_type != "Formal":
        logging.warning("Tests are not being run on a formal build")

    # source /etc/nova/openrc
    conn.sendline('source /etc/nova/openrc')
    #resp = conn.expect([INACTIVE_CONT_RESP, pexpect.TIMEOUT])
    resp = conn.expect([PROMPT, pexpect.TIMEOUT])
    if resp == 1: 
        logging.warning("Unable to source /etc/nova/openrc on %s" % current_host)

    # Check if the system has patches installed and list them
    conn.sendline("sudo wrs-patch query") 
    conn.expect_exact("Password:")
    conn.sendline(PASSWORD)
    conn.prompt()

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

    # Check if we are small footprint enabled
    # Damn lazy.  Do better than this.  We can check subfunctions instead
    if len(hostname_list) == 2:
        small_footprint = True
        logging.info("This system is configured for small footprint.")
    else:
        small_footprint = False
        logging.info("This system is not configured for small footprint.")

    # Check if we are using a storage lab 
    if len(stor_hostname_list) > 2:
        storage_system = True 
        logging.info("This system is configured with storage nodes.")
    else:
        storage_system = False
        logging.info("This system is not configured with storage nodes.") 
 
    # Determine which controller is active and which is standby 
    for host in cont_hostname_list:
        cmd = "system host-show %s" % host
        conn.sendline(cmd)
        resp = conn.expect(["Controller-Active", "Controller-Standby"])
        conn.prompt()
        if resp == 0:
            logging.info("The active controller is: %s" % host)
            active_controller = host
        else:
            logging.info("The standby controller is: %s" % host)
            standby_controller = host
 
    # Check if we are alarm free
    conn.sendline('system alarm-list')
    resp = conn.expect([UUID, EMPTY_TABLE, pexpect.TIMEOUT]) 
    conn.prompt()
    if resp == 0:
        logging.info("The system has alarms") 
    elif resp == 1:
        logging.warning("This system is alarm free")

    # List all interfaces provisioned
    for host in hostname_list: 
        cmd = "system host-if-list %s -a" % host
        conn.sendline(cmd)
        conn.prompt()

    # List all networks provisioned
    conn.sendline("neutron net-list")
    resp = conn.expect([UUID, EMPTY_TABLE, pexpect.TIMEOUT])
    if resp == 1:
        loggin.warning("There are no networks defined.") 
    conn.prompt()
    # Useful to extract UUIDs or network names?

    # List all providernets on the system
    vxlan_list = []      # list of vxlan providernet names
    vlan_list = []       # list of vlan provider names 
    flat_list = []       # list of flat provider names
    conn.sendline("neutron providernet-list")

    resp = 0
    while resp < 3:
        resp = conn.expect([VXLAN_NAME, VLAN_NAME, FLAT_NAME, EMPTY_TABLE, 
                            pexpect.TIMEOUT])
        if resp == 0:
            vxlan_list.append(conn.match.group())
        elif resp == 1:
            vlan_list.append(conn.match.group())
        elif resp == 2:
            flat_list.append(conn.match.group())
        elif resp == 3:
            logging.warning("There are no provider networks defined.")

    conn.prompt()
    logging.info("Vxlan provider networks: %s" % vxlan_list)
    logging.info("Vlan provider networks: %s" % vlan_list) 
    logging.info("Flat provider networks: %s" % flat_list) 

    # List all flavors and warn if there are no flavors defined
    conn.sendline("nova flavor-list")
    resp = conn.expect([FLAVOR_MATCH, EMPTY_TABLE, pexpect.TIMEOUT])
    if resp == 1:
        logging.warning("There are no flavors defined")
    conn.prompt()

    # Check if all nodes are available.   
    conn.sendline("system host-list")
    resp = conn.expect([PROMPT, pexpect.TIMEOUT]) 
    raw_buffer = conn.match.group()
    available_nodes = raw_buffer.count("available", 0, len(raw_buffer))
    if available_nodes == len(hostname_list):
        logging.info("All nodes are available")
    else:
        logging.warning("Not all nodes are available")
        # additional behaviour? wait for nodes, report which is not available, etc? 

    # Check if images have been installed
    conn.sendline("glance image-list")
    resp = conn.expect([UUID, EMPTY_TABLE, pexpect.TIMEOUT])
    if resp == 1:
        logging.warning("There are no images currently installed.")
        # we may want to rsync images over
    conn.prompt()
    # should we look for minimal set of images? e.g.
    # cgcs-guest_15_05, cgcs-guest_15_06, cgcs-guest_14_10, wrl5, wrl5-avp, wrl5-virtio, ubuntu, ubuntu-precise-amd64

    # Check if we have any instances on the system
    conn.sendline("nova list --all-tenants")
    resp = conn.expect([UUID, EMPTY_TABLE, pexpect.TIMEOUT])
    if resp == 1:
        logging.warning("There are no VMs instantiated.")

    # Collect all logs
    # This takes too long so redefine the timeout
    if DEBUG == True:
        conn.timeout = 300
        conn.sendline("sudo collect all")
        conn.prompt()
        resp = 0
        while resp < 3:
            resp = conn.expect(["\?", "Password\:", TARBALL_NAME, PROMPT, pexpect.TIMEOUT])
            if resp == 0:
                conn.sendline("yes")
            elif resp == 1:
                conn.sendline(PASSWORD)
            elif resp == 2:
                tarball = conn.match.group()
                logging.info("Tarball name is: %s" % tarball)
                # Reported tarball name differs from the actual file name.  Workaround product issue.
                newtarball = string.replace(tarball, "tgz", "gz")
                logging.info("New tarball name is: %s" % newtarball)
                # scp it to /folk/cgts/logs
        # reset timeout to original value after collect runs
        conn.timeout = TIMEOUT
 
    # Test end time
    test_end_time = datetime.datetime.now()
    test_duration = test_end_time - test_start_time
    logging.info("Ending self test at %s" % test_end_time) 
    logging.info("Test ran for %s" % test_duration) 
