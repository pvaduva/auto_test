#!/usr/bin/env python

"""
Usage:
./test_sanityrefresh_livemigratevms.py <FloatingIPAddress>

e.g.  ./test_sanityrefresh_livemigratevms.py 10.10.10.2

Assumptions:
* System has been installed
* Lab setup has been run 

Objective:
* The objective of this test is to live migrate VMs.  It will do two different
  live migrations:
  1.  live migration with the scheduler picking the destination host
  2.  live migration with a destination host specified, either controller or compute

Test Steps:
0) SSH to the system
1) Source /etc/nova/openrc
2) If no VMs exist, attempt to launch some (virtio, vswitch, avp) from volume 
3) For each VM: attempt a live migrate (scheduler picks destination host) 
                attempt a live migrate with destination host specified
4) Gather migration times for all VM migrations and report back 

General Conventions:
1) Functions that start with "list" have no return value and only report
   information
2) Functions that start with "check" return Boolean values
3) Functions that start with "get" check the system for conditions and return 1
   or more values
4) Functions that start with "exec", execute a command on the system

Future Enhancements:
* Handle connection to inactive controller in the case of VM launch
  Possible solution: rsync controller-0 /home/wrsroot to controller-1
* Include launch from image VMs
* Enhancement migration time measurement
  Possible solution: use customer logs or nova migration-list 
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

def test_sanityrefresh_livemigratevms(conn):
    """ This test performs a live migration of vms.  
        Inputs:
        * conn (string) - ID of pexpect session
        Outputs:
        * testFailed_flag - True if the test fails, False otherwise 
    """
    
    vmlist_virtio = vmlist_avp = vmlist_vswitch = []
    testFailed_flag = False

    test_name = "test_sanityrefresh_live_migrate_vms"
    
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
        vmlist_avp = vm.exec_launchvmscript(conn, "tenant2", "avp", 1)
        #vmlist_vswitch = vm.exec_launchvmscript(conn, "tenant1", "vswitch", 1)
        expectedvm_list = vmlist_virtio + vmlist_avp + vmlist_vswitch
        vm_list = nova.get_novavms(conn, "name")
        if set(vm_list) != set(expectedvm_list):
            logging.error("Expected the following VMs: %s, instead we have the following: %s" %  
                         (expectedvm_list, vm_list))
            logging.info("This means that not all expected VMs were launched.")
            testFailed_flag = True

    logging.info("Test Step 4: Live migrating without a destination host specified")
    vm_list = nova.get_novavms(conn, "id")
    for item in vm_list:
        test_result1 = vm.exec_vm_migrate(conn, item, "live")
        if not test_result1:
            testFailed_flag = True

    logging.info("Learn what hosts are on the system.")
    hostname_list, cont_hostname_list, comp_hostname_list, stor_hostname_list = sysinv.get_hosts(conn)

    logging.info("Test Step 5: Live migrating with a destination host specified")
    for item in vm_list:
        current_vm_host = nova.get_novashowvalue(conn, item, "host")
        logging.info("VM %s is on host %s" % (item, current_vm_host))
        host_personality = sysinv.get_hostpersonality(conn, current_vm_host)

        # Automatically determine which host to migrate to
        if host_personality == "controller":
            subset_hostname_list = copy.deepcopy(cont_hostname_list)
        else:
            subset_hostname_list = copy.deepcopy(comp_hostname_list)
        dest_vm_host = subset_hostname_list.remove(current_vm_host)
        dest_vm_host = random.choice(subset_hostname_list)

        logging.info("Live migrating VM %s from %s to %s" % (item, current_vm_host, dest_vm_host)) 
        test_result2 = vm.exec_vm_migrate(conn, item, "live", dest_vm_host)
        if not test_result2:
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
        sys.exit("Usage: ./test_sanityrefresh_livemigratevms.py <Floating IP of host machine>")
    else:
        floating_ip = sys.argv[1]

    # Enable logging
    logging.basicConfig(level=logging.INFO)

    # Establish connection
    conn = Session(timeout=TIMEOUT)
    conn.connect(hostname=floating_ip, username=USERNAME, password=PASSWORD)
    conn.setecho(ECHO)

    # Invoke test
    test_result = test_sanityrefresh_livemigratevms(conn)

    # Close connection at end of test
    conn.logout()
    conn.close()

    # For HTEE, non-zero exit code means test failed
    if test_result:
        exit(1)
    else:
        exit(0)
