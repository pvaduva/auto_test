#!/usr/bin/env python

"""
Usage:
./test_system_setup.py <FloatingIPAddress>

e.g.  ./test_system_setup.py 10.10.10.2

Assumptions:
* System has been installed
* Lab setup has been run 

Objective:
* The objective of this test is to setup the system with appropriate flavors and up the quotas so
tests can be run.

Test Steps:
0) SSH to the system
1) Source /etc/nova/openrc
2) Run lab_cleanup (if exists)
3) Run lab_setup (if exists)
4) Up the quotas
5) Unlock hosts if locked
6) Create additional flavors

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
    """ This function returns the current nova quota.
        Inputs:
        * conn - ID of pexpect session
        * tenant_id - id of a tenant, e.g. 690d4635663a46aba6d4c1e6a3a9efc7 
        Output:
        * Return the return value from expect, e.g. non-zero if fails, 0 if successful
    """
    
    # Get nova quota list
    cmd = "nova quota-show --tenant %s" % tenant_id 
    conn.sendline(cmd)
    #resp = conn.expect(["Quota", PROMPT, pexpect.TIMEOUT])
    resp = conn.expect([NON_EMPTY_TABLE, PROMPT, pexpect.TIMEOUT])
    if resp != 0:
        logging.warning("Unable to retrieve Nova quota")

    conn.prompt()
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
    resp = conn.expect(["Property", PROMPT, pexpect.TIMEOUT])
    if resp != 0:
        logging.warning("Unable to retrieve Cinder quota")
    #conn.prompt()
    return resp 

def get_projectuserid(conn, user):
    """ Return the UUID of a project.
        Inputs:
        * conn - ID of a pexpect session
        * user - name of a user, e.g. tenant1, tenant2, admin, etc.
        Outputs:
        * uuid - either a valid uuid or None
    """
    
    cmd1 = "openstack project list"
    cmd = "/usr/bin/keystone tenant-list"

    # We will use the deprecated commands unless the flag is true
    if USE_NEWCMDS:
        cmd = cmd1

    conn.sendline(cmd)
    uuid = None 
    resp = 0
    while resp < 2:
        # We could probably do better than this regex.  Revise.
        project_match = USER_ID + "(?=\s\| %s)" % user 
        resp = conn.expect([project_match, PROMPT, pexpect.TIMEOUT])
        if resp == 0:
            uuid = conn.match.group()
            logging.info("The UUID of %s is %s" % (user, uuid))
            break 
        elif resp == 2:
            logging.error("Unable to get UUID for %s" % user)
            break
    conn.prompt()
    return uuid

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

    # This is what will be returned by the system if we encounter an error
    # if this is generic enough, move to constants.py
    err = "(ERROR.*)\n"

    cmd = "nova quota-update --%s %s %s" % (quota_name, quota_value, tenant_id)
    conn.sendline(cmd)
    resp = conn.expect([PROMPT, err, pexpect.TIMEOUT]) 
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

    # This is what will be returned by the system if we encounter an error
    # if this is generic enough, move to constants.py
    err = "(ERROR.*)\n"

    cmd = "cinder quota-update --%s %s %s" % (quota_name, quota_value, tenant_id)
    conn.sendline(cmd)
    resp = conn.expect([PROMPT, err, pexpect.TIMEOUT]) 
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
        * Returns value of quota or non-zero value
    """

    err = "(ERROR.*)\n"

    quota_match = "(?<=%s).*?(\d+)" % quota_name
    cmd = "nova quota-show --tenant %s" % tenant_id 
    conn.sendline(cmd)
    resp = conn.expect([quota_match, PROMPT, pexpect.TIMEOUT])
    if resp == 2:
        logging.warning("The %s command timed out." % cmd) 
        return resp
    elif resp != 0:
        logging.warning("Unable to retrieve value of Nova quota %s" % quota_name)
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

    err = "(ERROR.*)\n"

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
    #conn.prompt()

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
    err = "(ERROR.*)\n"

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
        resp = conn.expect([err, PROMPT, pexpect.TIMEOUT])
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
    err = "(ERROR.*)\n"

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
        resp = conn.expect([err, PROMPT, pexpect.TIMEOUT])
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
    err = "(ERROR.*)\n"

    cmd = "nova flavor-delete"
    fullcmd = cmd + " " + name
    conn.prompt()
    conn.sendline(fullcmd)
    resp = conn.expect([err, PROMPT, pexpect.TIMEOUT])
    if resp == 0:
        logging.warning("Error deleting nova flavor due to %s" % conn.match.group())
    elif resp == 2:
        logging.warning("Command %s timed out" % fullcmd)

def list_nova(conn, tenant_name=None):
    """ This lists all the VMs.
        Inputs:
        * conn - ID of pexpect session
        * tenant_name - optional parameter to specify a tenant, e.g. tenant1
        Outputs:
        * Returns a list of VM IDs 
    """

    vm_list = []
    err = "(ERROR.*)\n"

    if tenant_name != None:
        tenant_id = get_projectuserid(conn, tenant_name)
        if not tenant_id:
            logging.error("Unable to retrieve corresponding ID for tenant %s" % cmd) 
            # this is poor form.  let's think about a better return value
            return -1 
        cmd = "nova list --tenant %s" % tenant_id
    else:
        cmd = "nova list --all-tenants"

    conn.prompt()
    conn.sendline(cmd)
    resp = 0
    while resp < 3:
        resp = conn.expect([UUID, err, PROMPT, pexpect.TIMEOUT])
        if resp == 0:
            vm_list.append(conn.match.group())
        elif resp == 1:
            logging.warning("Error listing nova VMs due to %s" % conn.match.group())
        elif resp == 3:
            logging.warning("Command %s timed out" % cmd)

    return vm_list

def launch_bulkvms(conn, options_list=None):
    """ This launches a bunch of VMs of different types.  If the user supplies a list of
        options, the launcher will attempt to launch VMs of that type.
        Inputs:
        * conn - ID of pexpect session
        * options_list - a list of options, e.g. heartbeat, sriov, dpdk, etc.
        Outputs:
        * None
    """ 
     

if __name__ == "__main__":

    # Enable logging
    logging.basicConfig(level=logging.INFO)

    # Test case name
    test_name = "test_sanityrefresh_systemsetup"

    # Get time
    test_start_time = datetime.datetime.now()
    logging.info("Starting %s at %s" % (test_name, test_start_time))

    # Establish connection
    conn = Session(timeout=TIMEOUT)
    #conn.connect(hostname=HOSTNAME, username=USERNAME, password=PASSWORD)
    conn.connect(hostname="128.224.150.219", username=USERNAME, password=PASSWORD)
    conn.setecho(ECHO)

    # source /etc/nova/openrc
    source_nova(conn)

    # Get the UUID for the user we're interested in
    tenant1_id = get_projectuserid(conn, "tenant2")

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
     
    # try deleting a flavor
    delete_novaflavor(conn, "fds")

    # nova list to list VMs
    vm_list = list_nova(conn)
    print(vm_list)

    # Test end time
    test_end_time = datetime.datetime.now()
    test_duration = test_end_time - test_start_time
    logging.info("Ending %s at %s" % (test_name, test_end_time))
    logging.info("Test ran for %s" % test_duration)
