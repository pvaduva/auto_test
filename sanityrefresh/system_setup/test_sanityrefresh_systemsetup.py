#!/usr/bin/env python

"""
Usage:
./test_sanityrefresh_systemsetup.py <FloatingIPAddress>

e.g.  ./test_sanityrefresh_systemsetup.py 10.10.10.2

Assumptions:
* System has been installed
* Lab setup has been run 

Objective:
* The objective of this test is to setup the system with appropriate flavors and up the quotas so
tests can be run.

Test Steps:
0) SSH to the system
1) Source /etc/nova/openrc
2) Up the quotas
3) Create additional flavors
4) Launch VMs of each type (virtio, vswitch, avp)

General Conventions:
1) Functions that start with "list" have no return value and only report information
2) Functions that start with "check" return Boolean values
3) Functions that start with "get" check the system for conditions and return 1 or more values
4) Functions that start with "exec", execute a command on the system

Future Enhancements:
*  Handle connection to inactive controller
"""

import os
import sys
import re
# class is in non-standard location so refine python search path 
sys.path.append(os.path.expanduser('~/wassp-repos/testcases/cgcs/cgcs2.0/common/py'))

from CLI.cli import *
from CLI import nova
from CLI import keystone
from CLI import vm
from CLI import sysinv

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

def list_novaquota(conn, tenant_id):
    """ This function returns the current nova quota for a particular user.
        Inputs:
        * conn - ID of pexpect session
        * tenant_id - id of a tenant, e.g. 690d4635663a46aba6d4c1e6a3a9efc7 
        Output:
        * Return the return value from expect, e.g. non-zero if fails, 0 if successful
    """
    
    # Get nova quota list
    conn.prompt()
    cmd = "nova quota-show --tenant %s" % tenant_id 
    conn.sendline(cmd)
    # Possible enhancement is for regex to match non-empty table, to be more generic
    resp = conn.expect(["Quota", ERROR, pexpect.TIMEOUT])
    if resp == 1:
        logging.warning("Unable to list nova quota due to %s" % conn.match.group())
    elif resp == 2:
        logging.warning("Unable to retrieve Nova quota due to timeout.")

    return resp 

def list_cinderquota(conn, tenant_id):
    """ This function returns the current nova quota.
        Inputs:
        * conn - ID of pexpect session
        * tenant_id - id of a tenant, e.g. 690d4635663a46aba6d4c1e6a3a9efc7 
        Output:
        * Return the return value from expect, e.g. non-zero if fails, 0 if successful
    """
    
    # Get nova quota list
    conn.prompt()
    cmd = "cinder quota-show %s" % tenant_id 
    conn.sendline(cmd)
    #resp = conn.expect([NON_EMPTY_TABLE, PROMPT, pexpect.TIMEOUT])
    #resp = conn.expect(["Property", PROMPT, pexpect.TIMEOUT])
    resp = conn.expect(["Property", pexpect.TIMEOUT])
    if resp == 2:
        logging.warning("Cinder quota command %s timed out" % cmd)

    return resp 

def put_novaquota(conn, tenant_id, quota_name, quota_value):
    """ Update the nova quota.
        Inputs:
        * conn - ID of pexpect session
        * tenant_id - id of a tenant, e.g. 690d4635663a46aba6d4c1e6a3a9efc7 
        * quota_name - quota name to be updated, e.g. instances, cores, ram
        * quota_value - value to set the quota to, e.g. 100
        Outputs:
        * Returns True if the update was successful
        * Returns False if the update was not successful 
    """

    cmd = "nova quota-update --%s %s %s" % (quota_name, quota_value, tenant_id)
    conn.sendline(cmd)
    resp = conn.expect([PROMPT, ERROR, pexpect.TIMEOUT]) 
    conn.prompt()
    if resp == 1:
        logging.warning("Unable to update nova quota due to %s" % conn.match.group())
        return False
    elif resp == 2:
        logging.warning("The %s command timed out." % cmd) 
        return False

    return True

def put_cinderquota(conn, tenant_id, quota_name, quota_value):
    """ Update the cinder quota.
        Inputs:
        * conn - ID of pexpect session
        * tenant_id - id of a tenant, e.g. 690d4635663a46aba6d4c1e6a3a9efc7 
        * quota_name - quota name to be updated, e.g. volumes 
        * quota_value - value to set the quota to, e.g. 100
        Outputs:
        * Returns True if the update was successful
        * Returns False if the update was not successful 
    """

    cmd = "cinder quota-update --%s %s %s" % (quota_name, quota_value, tenant_id)
    conn.sendline(cmd)
    resp = conn.expect([PROMPT, ERROR, pexpect.TIMEOUT]) 
    conn.prompt()
    if resp == 1:
        logging.warning("Unable to update cinder quota due to %s" % conn.match.group())
        return False
    elif resp == 2:
        logging.warning("The %s command timed out." % cmd) 
        return False

    return True

def get_novaquotavalue(conn, tenant_id, quota_name):
    """ This gets a particular value from the nova quota table, based on quota name.
        Inputs:
        * conn - ID of pexpect session
        * tenant_id - id of a tenant, e.g. 690d4635663a46aba6d4c1e6a3a9efc7
        * quota_name - name of quota to query, e.g. cores
        Outputs:
        There might be a better way to handle this but for now:
        * Returns value of quota which will be a string, or return resp (numeric) 
    """

    # Extract match to common file when perfected
    quota_match = "(?<=%s).*?(\d+)" % quota_name
    cmd = "nova quota-show --tenant %s" % tenant_id 
    conn.sendline(cmd)
    resp = conn.expect([quota_match, ERROR, pexpect.TIMEOUT])
    if resp == 1:
        logging.warning("Unable to list nova quota due to %s" % conn.match.group())
        return resp 
    elif resp == 2:
        logging.warning("Unable to retrieve Nova quota due to timeout.")
        return resp

    return conn.match.group(1) 

def get_cinderquotavalue(conn, tenant_id, quota_name):
    """ This gets a particular value from the nova quota table, based on quota name.
        Inputs:
        * conn - ID of pexpect session
        * tenant_id - id of a tenant, e.g. 690d4635663a46aba6d4c1e6a3a9efc7
        * quota_name - name of quota to query, e.g. volumes 
        Outputs:
        * Returns value of quota or non-zero value
    """

    quota_match = "(?<=%s).*?(\d+)" % quota_name
    cmd = "cinder quota-show %s" % tenant_id 
    conn.sendline(cmd)
    resp = conn.expect([quota_match, PROMPT, pexpect.TIMEOUT])
    if resp == 2:
        logging.warning("The %s command timed out." % cmd) 
        return resp
    elif resp != 0:
        logging.warning("Unable to retrieve value of cinder quota %s" % quota_name)
        return resp

    return conn.match.group(1) 

def list_novaflavors(conn):
    """ This lists the exists flavors
        Inputs:
        * conn - ID of pexpect session
        Ouputs:
        *  Returns empty list if there are no flavors
        *  Returns list with flavor IDs if there are flavors
    """

    # Get nova flavor list
    flavorid_list = [] 
    resp = 0

    conn.prompt()
    cmd = "nova flavor-list"
    conn.sendline(cmd)
    while resp < 2:
        resp = conn.expect(["ID", FLAVOR_ID, PROMPT, pexpect.TIMEOUT])
        if resp == 1:
            flavorid_list.append(conn.match.group())
        elif resp == 3:
            logging.warning("The %s command timed out." % cmd)

    if not flavorid_list:
        logging.info("There are no flavors currently defined.")

    return flavorid_list 

def put_bulknovaflavors(conn):
    """ This creates some basic flavors depending on what options the user wants.
        Inputs:
        * conn - ID of pexpect session
        Outputs:
        * No return value 
        Enhancement:
        * Optional arg so that the user can create custom flavors
    """
    cmd = "nova flavor-create"
    options = ["m1.small 2 2048 20 1", 
               "wrl5.dpdk.small.heartbeat 200 512 0 2",
               "wrl5.dpdk.big.heartbeat 201 4096 0 3",
               "wrl5.dpdk.big.heartbeat.pinToMgmtCore 233 4096 0 3",
               "m1.tiny 1 512 1 1"]

    for option in options:
        fullcmd = cmd + " " + option
        conn.prompt()
        conn.sendline(fullcmd)
        resp = conn.expect([ERROR, PROMPT, pexpect.TIMEOUT])
        if resp == 0:
            logging.warning("Error creating nova flavor due to %s" % conn.match.group())
        elif resp == 2:
            logging.warning("Command %s timed out" % fullcmd)

def put_bulknovaflavorkeys(conn):
    """ This creates some flavor keys to go along with the created flavors.
         Input:
         * conn - ID of pexpect session
         Outputs:
         * No return value
         Enhancements:
         * Optional arg so that the user can create custom flavor keys
    """

    cmd = "nova flavor-key"
    options = ["m1.small set hw:cpu_policy=dedicated hw:mem_page_size=2048",
               "wrl5.dpdk.small.heartbeat set hw:cpu_policy=dedicated hw:mem_page_size=2048",
               "wrl5.dpdk.big.heartbeat set hw:cpu_policy=dedicated hw:mem_page_size=2048",
               "wrl5.dpdk.big.heartbeat.pinToMgmtCore set hw:cpu_policy=dedicated hw:mem_page_size=2048",
               "m1.tiny set hw:cpu_policy=dedicated hw:mem_page_size=2048",
               "wrl5.dpdk.small set hw:cpu_policy=dedicated hw:mem_page_size=2048",
               "wrl5.dpdk.big set hw:cpu_policy=dedicated hw:mem_page_size=2048"]

    for option in options:
        fullcmd = cmd + " " + option
        conn.prompt()
        conn.sendline(fullcmd)
        resp = conn.expect([ERROR, PROMPT, pexpect.TIMEOUT])
        if resp == 0:
            logging.warning("Error creating nova flavor-key due to %s" % conn.match.group())
        elif resp == 2:
            logging.warning("Command %s timed out" % fullcmd)

def delete_novaflavor(conn, name):
    """ This deletes a nova flavor.
        Inputs:
        * conn - ID of pexpect session
        * name - name of flavor to be deleted
        Outputs:
        * None
    """

    cmd = "nova flavor-delete"
    fullcmd = cmd + " " + name
    conn.prompt()
    conn.sendline(fullcmd)
    resp = conn.expect([ERROR, PROMPT, pexpect.TIMEOUT])
    if resp == 0:
        logging.warning("Error deleting nova flavor due to %s" % conn.match.group())
    elif resp == 2:
        logging.warning("Command %s timed out" % fullcmd)

def get_neutronnetid(conn, network_name):
    """ This returns the ID of a network by querying neutron net-show.
        Inputs:
        * conn - ID of pexpect session
        * network_name - name of network to query, e.g. tenant1-mgmt-net
        Outputs:
        * ID of network which is a string, or non-zero integer if failure
    """

    conn.prompt()
    cmd = "neutron net-show %s -F id" % network_name
    conn.sendline(cmd)
 
    resp = conn.expect([UUID, "(Unable.*)", pexpect.TIMEOUT])
    if resp == 0:
        return conn.match.group()
    elif resp == 1:
        logging.warning("Encountered error on command %s: %s" % (cmd, conn.match.group()))
    elif resp == 2:
        logging.warning("Command %s timed out" % cmd)

    return resp

def test_sanityrefresh_systemsetup(conn):
    """ This test sets up the system for use by sanity.
        Inputs:
        * conn - ID of pexpect session
        Outputs:
        * testFailed_flag - True if test fails, false otherwise
    """

    testFailed_flag = False

    # source /etc/nova/openrc
    nova.source_nova(conn)

    # Get the UUID for the user we're interested in
    tenant1_id = keystone.get_userid(conn, "tenant1")
    tenant2_id = keystone.get_userid(conn, "tenant2")
 
    # Get the nova quota for tenant1
    list_novaquota(conn, tenant1_id)

    # Update quotas so we don't run out
    max_cores = "100"
    max_instances = "100"
    max_ram = "51200"
    put_novaquota(conn, tenant1_id, "cores", max_cores)      

    # Update quotas so we don't run out
    put_novaquota(conn, tenant1_id, "instances", max_instances)      

    # Update quotas so we don't run out (this may be default)
    put_novaquota(conn, tenant1_id, "ram", max_ram)      

    # Get the nova quota for tenant1
    list_novaquota(conn, tenant1_id)

    # Add a check to see if nova quotas were updated
    result = get_novaquotavalue(conn, tenant1_id, "cores")
    if result == max_cores:
        logging.info ("Nova cores have been set correctly to %s" % max_cores)
    else:
        logging.warning("Nova cores not set correctly.  Expected %s, received %s" % (max_cores, result))


    # Get the cinder quotas for tenant1
    list_cinderquota(conn, tenant1_id)

    # volumes
    max_volumes = "100"

    # Update the quota for tenant1
    put_cinderquota(conn, tenant1_id, "volumes", max_volumes)

    # result = get_cinderquotavalue(conn, tenant1_id, "volumes")
    if result == max_volumes:
        logging.info("Cinder volumes have been set correctly to %s" % max_volumes)
    else:
        logging.warning("Cinder volumes not set correctly.  Expected %s, received %s" % (max_volumes, result))

    # list existing flavors
    flavorid_list = list_novaflavors(conn)
    logging.info("Extracted flavor IDs: %s" % flavorid_list)

    # create new flavors
    put_bulknovaflavors(conn)

    # create flavor-keys to go with the newly created flavors
    put_bulknovaflavorkeys(conn)

    # try deleting a flavor just for fun
    delete_novaflavor(conn, "fds")

    # Launch VMs via script
    vmlist_virtio = vm.exec_launchvmscript(conn, "tenant1", "virtio", 1)
    vmlist_avp = vm.exec_launchvmscript(conn, "tenant2", "avp", 1)
    vmlist_vswitch = vm.exec_launchvmscript(conn, "tenant1", "vswitch", 1)
    expectedvm_list = vmlist_virtio + vmlist_avp + vmlist_vswitch

    # Get an updated list of VMs that have been launched by the system 
    vm_list = nova.get_novavms(conn, "name")

    # Check if expected VMs are present 
    logging.info("Test will fail if the expected VMs are not present on the system.")
    if vm_list == expectedvm_list:
        logging.info("Test result: PASSED")
    else:
        logging.error("Current VMs %s not equivalent to expected VMs %s" % (vm_list, expectedvm_list))
        logging.info("Test result: FAILED")
        testFailed_flag = True

    # Test end time
    test_end_time = datetime.datetime.now()
    test_duration = test_end_time - test_start_time
    logging.info("Ending %s at %s" % (test_name, test_end_time))
    logging.info("Test ran for %s" % test_duration)

    return testFailed_flag

if __name__ == "__main__":

    # Extract command line arguments
    if len(sys.argv) < 2:
        sys.exit("Usage: ./test_sanityrefresh_systemsetup.py <Floating IP of host machine>")
    else:
        floating_ip = sys.argv[1]

    # Enable logging
    logging.basicConfig(level=logging.INFO)

    # Test case name
    test_name = "test_sanityrefresh_systemsetup"

    # Get time
    test_start_time = datetime.datetime.now()
    logging.info("Starting %s at %s" % (test_name, test_start_time))

    # Establish connection
    conn = Session(timeout=TIMEOUT)
    conn.connect(hostname=floating_ip, username=USERNAME, password=PASSWORD)
    conn.setecho(ECHO)

    # Invoke test
    test_result = test_sanityrefresh_systemsetup(conn) 

    # Terminate connection
    conn.logout()
    conn.close()

    # For HTEE, non-zero value fails the test
    if test_result:
        exit(1)
    else:
        exit(0)
