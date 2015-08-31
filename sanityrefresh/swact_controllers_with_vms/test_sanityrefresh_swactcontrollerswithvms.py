#!/usr/bin/env python

"""
Usage:
./test_sanityrefresh_swactcontrollerswithvms.py <FloatingIPAddress>

e.g.  ./test_sanityrefresh_swactcontrollerswithvms.py 10.10.10.2

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
3) Pick a host with VMs, swact controllers
   - Ensure VMs remain on the same host
   - Ensure VMs are pingable from NAT box
   - Ensure VMs can ping each other 
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

def test_sanityrefresh_swactcontrollerswithvms(conn):
    """ This test performs a swact of a controller with VMs. 
        Inputs:
        * conn (string) - ID of pexpect session
        Outputs:
        * None.  We will simply reports if the test failed 
    """
    
    vmlist_virtio = vmlist_avp = vmlist_vswitch = []
    testFailed_flag = False

    test_name = "test_sanityrefresh_swactcontrollerswithvms"
    
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

    # The active controller is the current host 
    current_host = sysinv.get_hostname(conn) 
  
    # Get list of VMs per hypervisor
    logging.info("Test 4: Get hypervisor to VM association")
    hypvm_dict =  nova.get_hypervisorvms(conn)
 
    # Only applies to small footprint
    # In theory, the active controller could have no VMs, so maybe lock/unlock
    # inactive controller

    # Swact the active controller 
    logging.info("Test Step 5: Swact the active controller") 
    result = sysinv.swact_host(conn, current_host)

    # We'll now get kicked out of ssh. Wait and then reconnect and source openrc 
    logging.info("Test Step 6: Wait %s seconds before reconnecting" % SWACT_MAXTIME)
    time.sleep(SWACT_MAXTIME)
    conn = Session(timeout=TIMEOUT)
    conn.connect(hostname=floating_ip, username=USERNAME, password=PASSWORD)
    conn.setecho(ECHO)
    nova.source_nova(conn)

    # Check that we are now on a different host, otherwise test failed
    new_currenthost = sysinv.get_hostname(conn)
    if current_host == new_currenthost:
        logging.error("Swact of host %s failed" % current_host) 
        testFailed_flag = True

    # Could check that all nova services are up

    # Check the VMs again to ensure they have not migrated
    new_hypvmdict =  nova.get_hypervisorvms(conn)
    if hypvm_dict != new_hypvmdict: 
        logging.error("VM list before swact is not equal to VM list after.")
        logging.info("VMs before swact: %s" % hypvm_dict) 
        logging.info("VMs after swact: %s" % new_hypvmdict)
        testFailed_flag = True

    # Ping VMs from NAT box
    logging.info("Test Step 5: Ensure we can ping the VMs from the NAT box") 
    result = vm.ping_vms_from_natbox(conn, ping_duration=3)
    if result:
        testFailed_flag = True

    # Ping VMs internally
    logging.info("Test Step 6: Ensure we can ping between the VMs")
    result = vm.ping_between_vms(conn, no_packets=3)
    if result:
        testFailed_flag = True

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

    return testFailed_flag

if __name__ == "__main__":

    # Extract command line arguments
    if len(sys.argv) < 2:
        sys.exit("Usage: ./test_sanityrefresh_swactcontrollerswithvms.py <Floating IP of host machine>")
    else:
        floating_ip = sys.argv[1]

    # Enable logging
    logging.basicConfig(level=logging.INFO)

    # Establish connection
    conn = Session(timeout=TIMEOUT)
    conn.connect(hostname=floating_ip, username=USERNAME, password=PASSWORD)
    conn.setecho(ECHO)

    # Invoke test
    test_result = test_sanityrefresh_swactcontrollerswithvms(conn) 

    # Logout at the end
    conn.logout()
    conn.close()

