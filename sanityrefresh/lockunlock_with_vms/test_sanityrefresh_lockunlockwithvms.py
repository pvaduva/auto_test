#!/usr/bin/env python

"""
Usage:
./test_sanityrefresh_lockunlockwithvms.py <FloatingIPAddress>

e.g.  ./test_sanityrefresh_lockunlockwithvms.py 10.10.10.2

Assumptions:
* System has been installed
* Lab setup has been run 

Objective:
* The objective of this test is to lock and unlock a controller or compute that is 
  hosting VMs and ensure the VMs migrate off the locked host 

Test Steps:
0) SSH to the system
1) Source /etc/nova/openrc
2) If no VMs exist, attempt to launch some (virtio, vswitch, avp) 
3) Pick a host with VMs, lock it and ensure that the VMs migrate to 
   the other host 
4) Gather migration times for all VM migrations and report back 

General Conventions:
1) Functions that start with "list" have no return value and only report
   information
2) Functions that start with "check" return Boolean values
3) Functions that start with "get" check the system for conditions and return 1
   or more values
4) Functions that start with "exec", execute a command on the system

Future Enhancements:
*  Handle connection to inactive controller in the case of VM launch
"""

import os
import sys
import re
import time
import random
import copy
import time
# class is in non-standard location so refine python search path 
sys.path.append(os.path.expanduser('~/wassp-repos/testcases/cgcs/cgcs2.0/common/py'))

from CLI.cli import *
from CLI import nova
from CLI import keystone
from CLI import vm
from CLI import sysinv

def test_sanityrefresh_lockunlockwithvms(conn):
    """ This test performs a lock/unlock of a host with VMs. 
        Inputs:
        * conn (string) - ID of pexpect session
        Outputs:
        * None.  We will simply reports if the test failed 
    """
    
    vmlist_virtio = vmlist_avp = vmlist_vswitch = []
    testFailed_flag = False

    test_name = "test_sanityrefresh_lockunlockwithvms"
    
    # Get time
    test_start_time = datetime.datetime.now()
    logging.info("Starting %s at %s" % (test_name, test_start_time))
    
    # source /etc/nova/openrc
    logging.info("Test Step 1: source nova openrc")
    nova.source_nova(conn)
   
    # Get the UUID for the user we're interested in
    logging.info("Test Step 2: get the IDs associated with tenant users")
    tenant1_id = keystone.get_userid(conn, "tenant1")
    tenant2_id = keystone.get_userid(conn, "tenant2")
    
    # Get the list of VMs on the system 
    logging.info("Test Step 3: Check if there are already VMs on the system")
    vm_list = nova.get_novavms(conn, "name")

    # Check that there are VMs on the system
    if not vm_list: 
	logging.warning("There are no VMs present on the system so the test " \
                        "will launch some to proceed.")
        vmlist_virtio = vm.exec_launchvmscript(conn, "tenant1", "virtio", 1)
        vmlist_avp = vm.exec_launchvmscript(conn, "tenant2", "avp", 2)
        vmlist_vswitch = vm.exec_launchvmscript(conn, "tenant1", "vswitch", 1)
        expectedvm_list = vmlist_virtio + vmlist_avp + vmlist_vswitch
        vm_list = nova.get_novavms(conn, "name")
        if set(vm_list) != set(expectedvm_list):
            logging.error("Expected the following VMs: %s, instead we have the following: %s" %  
                         (expectedvm_list, vm_list))
            logging.info("This means that not all expected VMs were launched.")
            testFailed_flag = True

    # Totals vms
    total_vms = len(vm_list)

    # Check if we're small footprint
    smallfootprint = sysinv.check_smallfootprint(conn)
    if smallfootprint == True:
        logging.info("This system is small footprint enabled.")
   
    # Determine which hypervisors we have in the system        
    hypervisor_list = nova.get_novahypervisors(conn)
    logging.info("The system has the following hypervisors: %s" % hypervisor_list)             

    # For each hypervisor, determine the VMs associated with it
    hypvm_dict = {}
    for hypervisor in hypervisor_list:
        hypervisorserver_list = nova.get_hypervisorservers(conn, hypervisor)
        logging.info("VMs on server %s: %s" % (hypervisor, hypervisorserver_list))
        # dict has key hypervisor, e.g. compute-0, value: number of vms
        hypvm_dict[hypervisor] = len(hypervisorserver_list)

    # Get the hostname of the hypervisor with the max VMs
    hypervisor_max = max(hypvm_dict, key = lambda x: hypvm_dict.get(x))
    
    # Lock the host with the most VMs
    logging.info("Test Step 4: Lock the hypervisor with most VMs")
    result = sysinv.lock_host(conn, hypervisor_max)

    # We should poll and set a hard-limit for timeout (preferrably get from dev)
    hypervisor_state = ""
    i = 0
    # Move the timeout to constants (FIXME)  
    while i < 60: 
        hypervisor_state = sysinv.get_hostshowvalue(conn, hypervisor_max, field="administrative")
        if hypervisor_state == "locked":
             logging.info("Hypervisor %s locked as expected" % hypervisor_max)
             break
        i = i + 1
        time.sleep(1)

    # Test fails if we couldn't lock the host with the VMs
    if hypervisor_state != "locked":
        logging.error("Failed to lock %s" % hypervisor_max) 
        testFailed_flag = True

    # After the host is locked, ensure that no VMs remain on it
    logging.info("Test Step 5: Ensure the VMs migrated off the locked hypervisor")
    if hypervisor_state == "locked":
        vms_after = nova.get_hypervisorservers(conn, hypervisor_max)
        if len(vms_after) != 0:
           logging.error("Not all VMs migrated off %s" % hypervisor_max)
           logging.error("The following VMs are still on %s: %s" % (vms_after, hypervisor_max))
           testFailed_flag = True

        # FIXME: Check if the VMs that are on another host are available/paused/etc. (not error)
        
        # Unlock the host at the end of the test
        logging.info("Unlock the host at the end of the test")
        result = sysinv.unlock_host(conn, hypervisor_max)
      
        # Wait until the host becomes available 
        i = 0 
        # Move to constants (FIXME)
        while i < 180:
            hypervisor_state = sysinv.get_hostshowvalue(conn, hypervisor_max, field="availability")
            if hypervisor_state == "available":
                logging.info("Hypervisor %s is now unlocked" % hypervisor_max)
                break
            i = i + 1
            time.sleep(1)

    # just for information
    if testFailed_flag == True:
        logging.info("Test result: FAILED")
    else:
        logging.info("Test result: PASSED")

    # Test end time
    test_end_time = datetime.datetime.now()
    test_duration = test_end_time - test_start_time
    logging.info("Ending %s at %s" % (test_name, test_end_time))
    logging.info("Test ran for %s" % test_duration)

if __name__ == "__main__":

    # Extract command line arguments
    if len(sys.argv) < 2:
        sys.exit("Usage: ./test_sanityrefresh_lockunlockwithvms.py <Floating IP of host machine>")
    else:
        floating_ip = sys.argv[1]

    # Enable logging
    logging.basicConfig(level=logging.INFO)

    # Establish connection
    conn = Session(timeout=TIMEOUT)
    conn.connect(hostname=floating_ip, username=USERNAME, password=PASSWORD)
    conn.setecho(ECHO)

    # Invoke test
    test_result = test_sanityrefresh_lockunlockwithvms(conn)

    # Logout at the end
    conn.logout()

