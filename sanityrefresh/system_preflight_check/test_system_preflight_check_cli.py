#!/usr/bin/env python

"""
Usage:
./test_system_preflight_check_cli.py <FloatingIPAddress>

e.g.  ./test_system_preflight_check_cli.py 10.10.10.2

Assumptions:
* System has been installed
* Lab setup has been run 

Objective:
* The objective of this test is to summarize the condition of the system to 
make it easier to diagnose system failures.  

Test Steps:
0) SSH to the system
1) List the buildinfo of the system, e.g. cat /etc/build.info
2) Source /etc/nova/openrc
3) List the patch level of the system, e.g. sudo wrs-patch query
4) Query the system to get lists of all nodes, all controllers, all computes and all storage
6) Check if we are alarm-free
7) List all the host interfaces
8) List all the neutron networks
9) Get all the neutron provider-nets
10) Check there are flavors defined
11) Check all hosts are available
12) Check there are images on the system
13) Check there are VMs instantiated
14) Check that all expected nova services are up (also tests for active controller and small footprint) 


16) Check VMs have been created and for HB VMs, check heartbeat services are up (skip)


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

def get_hostname(conn):
    """ This function returns the hostname of the current system. 
        Inputs:
          * conn - ID of the pexpect session 
        Output:
          * a string containing the hostname, e.g. controller-0 

    """
    conn.sendline("cat /etc/hostname")
    resp = conn.expect(HOSTNAME_MATCH)
    current_host = conn.match.group()
    if current_host:
        logging.info("We're connected to host %s" % current_host)
        return current_host
    else:
        logging.warning("Unable to determine name of host")
        return -1

def list_buildinfo(conn):
    """ This function returns the build information of the current system. 
        Inputs:
        * conn - ID of pexpect session
        Outputs:
        * prints build info

    """
    conn.sendline("cat /etc/build.info")
    resp = conn.expect(["Formal", pexpect.TIMEOUT])
    build_type = conn.match.group()
    if build_type != "Formal":
        logging.warning("Tests are not being run on a formal build")

def source_nova(conn):
    """ This function sources the /etc/nova/openrc file.
        Inputs:
        * conn - ID of pexpect session
        Outputs:
    """
    conn.sendline('source /etc/nova/openrc')
    resp = conn.expect([PROMPT, pexpect.TIMEOUT])
    if resp == 1:
        logging.warning("Unable to source /etc/nova/openrc on %s" % current_host)
        active_controller, inactive_controller = get_activeinactive_controller(conn)
        current_host = get_hostname(conn)
        if inactive_controller == current_host:
            logging.warning("We are on the inactive controller") 
        # should we try the other IPs?

def list_patchlevel(conn):
    """ This function checks the patch level of the system.
        Inputs:
        * conn - ID of pexpect session
        Outputs:
        * prints patches (if any)
    """
    conn.sendline("sudo wrs-patch query")
    conn.expect_exact("Password:")
    conn.sendline(PASSWORD)
    conn.prompt()

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

def check_smallfootprint(conn):
    """ This function checks to see if the system is configured for small footprint.
        Inputs:
        * conn - ID of pexpect session
        Output:
        * True if we are small footprint enabled or False if we are not
    """

    # Damn lazy.  Do better than this.  We can check subfunctions instead
    if len(hostname_list) == 2:
        small_footprint = True
        logging.info("This system is configured for small footprint.")
        return True
    else:
        small_footprint = False
        logging.info("This system is not configured for small footprint.")
        return False

def get_activeinactive_controller(conn, cont_hostname_list):
    """ This function returns the hostname of the active controller 
        Inputs:
        * conn - ID of pexpect session
        * cont_hostname_list - list of controllers in the system
        Output:
        * hostname of active controller
    """
    for host in cont_hostname_list:
        cmd = "system host-show %s" % host
        conn.sendline(cmd)
        resp = 0
        while resp < 2:
            resp = conn.expect(["Controller-Active", "Controller-Standby", pexpect.TIMEOUT])
            conn.prompt()
            if resp == 0:
                logging.info("The active controller is: %s" % host)
                active_controller = host
            elif resp == 1:
                logging.info("The standby controller is: %s" % host)
                inactive_controller = host

    return active_controller, inactive_controller

def get_inactive_controller(conn, cont_hostname_list):
    """ This function returns the inactive controller.
        Inputs:
        * conn - ID of pexpect session
        * cont_hostname_list - list of controllers in the system
        Output:
        * hostname of inactive controller
    """
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

    return inactive_controller 

def check_alarm_free(conn):
    """ This checks the system for alarms.
        Input:
        * conn - ID of pexpect session
        Output:
        * return True if alarm free, False if there are alarms
    """
    conn.sendline('system alarm-list')
    resp = conn.expect([UUID, EMPTY_TABLE, pexpect.TIMEOUT])
    conn.prompt()
    if resp == 0:
        logging.warning("The system has alarms")
        return False 
    elif resp == 1:
        logging.info("This system is alarm free")
        return True

def list_interfaces(conn, hostname_list):
    """ This lists all the interfaces on the system.
        Inputs:
        * conn - ID of pexpect session
        * hostname_list - list of all hosts in the system
        Output:
        * prints all host interfaces
        * no return value
    """
    for host in hostname_list:
        cmd = "system host-if-list %s -a" % host
        conn.sendline(cmd)
        conn.prompt()

def list_neutronnetworks(conn):
    """ This lists all the neutron networks in the system.
        Inputs:
        * conn - ID of pexpect session
        Output:
        * prints all the neutron networks 
        * no return value
    """
    conn.sendline("neutron net-list")
    resp = conn.expect([UUID, EMPTY_TABLE, pexpect.TIMEOUT])
    if resp == 1:
        logging.warning("There are no networks defined.")
    conn.prompt()

def get_providernetworks(conn):
    """ This gets the neutron provider networks.
        Inputs:
        * conn - ID of pexpect session
        Output:
        * 3 lists: list of vxlan network names, vlan and flat
    """
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

    return vxlan_list, vlan_list, flat_list

def check_flavors(conn):
    """ This lists the defined flavors and return a boolean if flavors are defined or not.
        Inputs:
        * conn - ID of pexpect session
        Output:
        * True if there are flavors defined
        * False if there are no flavors defined.
    """
    conn.sendline("nova flavor-list")
    resp = conn.expect([FLAVOR_MATCH, EMPTY_TABLE, pexpect.TIMEOUT])
    conn.prompt()
    if resp == 0:
        return True
    elif resp == 1:
        logging.warning("There are no flavors defined")
        return False

def check_hostavail(conn):
    """ This checks if all hosts are available.
        Inputs:
        * conn - ID of pexpect session
        Output:
        * True if all hosts are available
        * False if hosts are not avaiable
    """ 
    conn.sendline("system host-list")
    resp = conn.expect([PROMPT, pexpect.TIMEOUT])
    raw_buffer = conn.match.group()
    available_nodes = raw_buffer.count("available", 0, len(raw_buffer))
    if available_nodes == len(hostname_list):
        logging.info("All nodes are available")
        return True
    else:
        logging.warning("Not all nodes are available")
        # additional behaviour? wait for nodes, report which is not available, etc? 
        return False

def check_images(conn):
    """ This checks if any images exist.
        Inputs:
        * conn - ID of pexpect session
        Output:
        * True if images exist
        * False if no images are defined.
    """
    conn.sendline("glance image-list")
    resp = conn.expect([UUID, EMPTY_TABLE, pexpect.TIMEOUT])
    conn.prompt()
    if resp == 0:
        return True
    elif resp == 1:
        logging.warning("There are no images currently installed.")
        return False
        # we may want to rsync images over
    # should we look for minimal set of images? e.g.
    # cgcs-guest_15_05, cgcs-guest_15_06, cgcs-guest_14_10, wrl5, wrl5-avp, wrl5-virtio, ubuntu, ubuntu-precise-amd64

def check_instances(conn):
    """ This checks if any instances are defined.
        Inputs:
        * conn - ID of pexpect session
        Output:
        * True if we have instances
        * False if there are no instances
    """
    conn.sendline("nova list --all-tenants")
    resp = conn.expect([UUID, EMPTY_TABLE, pexpect.TIMEOUT])
    conn.prompt()
    if resp == 0:
        return True
    if resp == 1:
        logging.warning("There are no VMs instantiated.")
        return False

def check_novaservices(conn, cont_hostname_list): 
    """ This checks that all expected nova services are up.  We expect that
        1.  All compute services will be up (if they exist)
        2.  All active controller services will be up (if they exist)
        3.  nova-compute will be up on the inactive-controller (if smallfootprint only)
        Inputs:
        * conn - ID of pexpect session
        * smallfootprint - result of check_smallfootprint function, e.g. True or False
        Output:
        * True if expected services are up
        * False if expected services are down 

    """
    # Flag to track if unexpected services are down
    unexpected_service_flag = False

    # Get the nova service list
    conn.sendline("nova service-list")
    resp = conn.expect([PROMPT, pexpect.TIMEOUT])
    raw_buffer = conn.match.group()
    conn.prompt()

    # Find all nova services that are down
    down_service = re.findall(DOWN_NOVASERVICE, raw_buffer)

    # Check if we are a small footprint system
    smallfootprint = check_smallfootprint(conn)

    # Grab the active and inactive controllers
    active_controller, inactive_controller = get_activeinactive_controller(conn, cont_hostname_list)

    for service in down_service:
        service_name = service[0]
        service_host = service[1]
        service_state = service[2]

        # Warn if any compute or active controller service is down 
        # On small footprint, also warn if nova-compute is down on the inactive controller
        if service_host.startswith("compute") or \
           service_host.startswith(active_controller) or \
           (service_host.startswith(inactive_controller) and (service_name == "nova-compute") and \
            smallfootprint):
            logging.warning("%s on %s is %s" % (service_name, service_host, service_state))
            unexpected_service_flag = True

    if not unexpected_service_flag:
        logging.info("All expected services are up")
        return True
    else:
        return False    
    
if __name__ == "__main__":

    # Enable logging
    logging.basicConfig(level=logging.INFO)

    # Test case name
    test_name = "test_sanityrefresh_preflightcheck"

    # Get time
    test_start_time = datetime.datetime.now()
    logging.info("Starting %s at %s" % (test_name, test_start_time))

    # Establish connection
    conn = Session(timeout=TIMEOUT)
    conn.connect(hostname=HOSTNAME, username=USERNAME, password=PASSWORD)
    conn.setecho(ECHO)

    # Determine which host we're connected to and return the hostname
    get_hostname(conn)

    # Cat the build info and extract the build type 
    list_buildinfo(conn)

    # source /etc/nova/openrc
    source_nova(conn)

    # Check if the system has patches installed and list them
    list_patchlevel(conn)

    # Determine the hosts in the lab
    hostname_list, cont_hostname_list, comp_hostname_list, stor_hostname_list = get_hosts(conn)

    # Check if we are using a storage lab 
    if len(stor_hostname_list) > 2:
        storage_system = True
        logging.info("This system is configured with storage nodes.")
    else:
        storage_system = False
        logging.info("This system is not configured with storage nodes.")

    # Check if we are alarm free
    alarms = check_alarm_free(conn)

    # List all interfaces provisioned
    list_interfaces(conn, hostname_list)

    # List all networks provisioned
    list_neutronnetworks(conn)

    # List all providernets on the system
    get_providernetworks(conn)

    # Check if there are flavors defined 
    flavors = check_flavors(conn)

    # Check if all nodes are available
    available = check_hostavail(conn)

    # Check if images have been installed
    images = check_images(conn)

    # Check if we have any instances on the system
    instances = check_instances(conn)

    # Check that expected nova services are up
    nova = check_novaservices(conn, cont_hostname_list)

    # Fail condition is no flavors, no images, no instances or nova being down.  
    # We can revise this later.  Hosts not being available, or alarms are
    # not considered a fail currently.
    logging.info("Test will fail if there are no flavors, no images, no instances or expected nova services are down.")
    if not all ((flavors, images, instances, nova)):
        logging.error("Test Result: FAILED")
    else:
        logging.info("Test Result: PASSED")

    # Test end time
    test_end_time = datetime.datetime.now()
    test_duration = test_end_time - test_start_time
    logging.info("Ending %s at %s" % (test_name, test_end_time))
    logging.info("Test ran for %s" % test_duration)
