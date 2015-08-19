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
import time
import random
# class is in non-standard location so refine python search path 
sys.path.append(os.path.expanduser('~/wassp-repos/testcases/cgcs/cgcs2.0/common/py'))

from CLI.cli import *

def source_nova(conn, user=None):
    """ This function sources the desired openrc file.
        Inputs:
        * conn - ID of pexpect session
        * user (optional) - user name, e.g. tenant1, tenant2 
        Outputs:
        * Exit if command fails with non-zero return code
        * Return zero if command passes
        Tag:
        * Add to common functions
    """

    logging.info("Sourcing the openrc file")

    # Admin user is the default.  Optionally, we can use tenant1 or tenant2
    if not user:
        cmd = "source /etc/nova/openrc"
        extract = "keystone_admin"
    else:
        cmd = "source ./openrc." + user 
        extract = "keystone_" + user

    conn.sendline(cmd)

    # Check if the source nova openrc command succeeded or if we had errors
    resp = conn.expect([extract, "-sh:.*\r\n", pexpect.TIMEOUT])
    if resp == 1:
        logging.warning("Unable to %s due to %s" % (cmd, conn.match.group())) 
        exit(-1)
    elif resp == 2:
        logging.warning("Command %s timed out." % cmd)
        exit(-1)

    return resp

def get_hostpersonality(conn, hostname):
    """ This function returns the personality of host.
        Inputs:
        * conn - ID of pexpect session
        * hostname - name of host to check personality of, e.g. storage
        Output:
        * Return string, either storage, compute, controller or,
        * Return resp (non-zero int value) if we fail
    """

    cmd = "system host-show %s" % hostname
    conn.sendline(cmd)
    resp = conn.expect([CONT_PERSONALITY, COMP_PERSONALITY, STOR_PERSONALITY,
                        pexpect.TIMEOUT])
    if resp == 0:
        host_type = "controller" 
    elif resp == 1:
        host_type = "compute" 
    elif resp == 2:
        host_type = "storage" 
    elif resp == 3:
        logging.warning("Could not determine personality of host %s" % hostname)
        return resp
   
    logging.info("Host type of host %s is %s" % (hostname, host_type)) 
    conn.prompt()

    return host_type 


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

def get_userid(conn, user):
    """ Returns the user ID from the keystone tenant-list or 
        openstack project-list.
        Inputs:
        * conn - ID of a pexpect session
        * user - name of a user, e.g. tenant1, tenant2, admin, etc.
        Outputs:
        * id - a valid user ID or,
        * resp - non-zero value if we couldn't get the user id 
        Tags:
        * Add to common functions 
    """
   
    logging.info("Getting the tenant user id")
 
    cmd1 = "openstack project list"
    cmd = "keystone tenant-list"

    # We will use the deprecated commands unless the flag is true
    if USE_NEWCMDS:
        cmd = cmd1

    conn.sendline(cmd)
    conn.prompt()

    resp = 0
    while resp < 1:
        # Extract the 32 character user ID 
        extract = "([0-9a-f]{32})(?=\s\| %s)" % user 
        resp = conn.expect([extract, pexpect.TIMEOUT])
        if resp == 0:
            user_id = conn.match.group()
            logging.info("The ID of %s is %s" % (user, user_id))
            return resp
        elif resp == 1:
            logging.error("Unable to get ID for %s" % user)
            return resp

    return user_id 

def get_novavms(conn, return_value="id", tenant_name=None):
    """ This functions does one of two things.  It does the equivalent of 
	nova list --all-tenants if a tenant_name is not supplied as an
        argument. 

	Or it does nova list --tenant <tenant_id> if the tenant_name, e.g.
        tenant2, is supplied.
        
        To keep it easy for the user, it takes the tenant_name and does a lookup
        via keystone or openstack to extract the ID associated with that tenant.
 
        Inputs:
        * conn - ID of pexpect session
        * return_value - accepts either id or name, depending on whether the user
          wants the function to return vms by name or id 
        * tenant_name - optional parameter to specify a tenant, e.g. tenant1
        Outputs:
        * Returns a list of VM ids or names
    """

    logging.info("Getting list of VMs by %s" % return_value)

    vm_list = []

    # Determine which nova list command to use depending on the arguments supplied to
    # the function
    if tenant_name != None:
        tenant_id = get_userid(conn, tenant_name)
        if not tenant_id:
            logging.error("Unable to retrieve corresponding ID for tenant %s" % cmd) 
            return -1 
        cmd = "nova list --tenant %s" % tenant_id
    else:
        cmd = "nova list --all-tenants"

    conn.prompt()
    conn.sendline(cmd)

    # determine if we should return a list of vm names or IDs
    if return_value == "name":
        #extract = VM_NAME
        extract = "(?<=\r\n\|\s[0-9a-f-]{36}\s\|\s)([0-9a-zA-Z-]+)" 
    else:
        #extract = UUID
        extract = "(?<=\r\n\|\s)([0-9a-f-]{36})" 

    resp = 0
    while resp < 1:
        resp = conn.expect([extract, ERROR, PROMPT, pexpect.TIMEOUT])
        if resp == 0:
            vm_list.append(conn.match.group())
        elif resp == 1:
            msg = "Error listing nova VMs due to %s" % conn.match.group()
            logging.warning(msg)
        elif resp == 3:
            msg = "Command %s timed out" % cmd
            logging.warning(msg)

    logging.info("VM list by %s: %s" % (return_value, vm_list))

    return vm_list

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


def exec_launchvmscript(conn, tenant_name):
    """ This launches a VM using the scripts created by lab_setup.  Note, we'll have to switch to
        controller-0, since that's where the scripts are.
        Inputs:
        * conn - ID of pexpect session
        * tenant_name - name of tenant to launch VMs as, e.g. tenant1, tenant2
        Outputs:
        * expectedvm_list - return list of VMs that we try to launch
        Enhancements: allow user to specify type of VM to launch and number of instances
    """

    # FIX ME: Need to adjust if we are not on controller-0

    expectedvm_list = []
    conn.prompt()
    conn.timeout = 60 

    # Get the list of VMs that are already launched on the system by name
    vm_list = get_novavms(conn, "name")

    # Types of instances to launch
    instance_types = ["avp", "virtio", "vswitch"]

    # Launch one of each type of VM for now
    for instance in instance_types:
        # Construct the name of VM to launch
        vm_name = "%s-%s1" % (tenant_name, instance)
        expectedvm_list.append(vm_name)
        if vm_name not in vm_list:
            cmd = "~/instances_group0/./launch_%s.sh" % vm_name 
            conn.sendline(cmd)
            # Should report Finished if built properly
            resp = conn.expect(["Finished", ERROR, pexpect.TIMEOUT])
            if resp == 1:
                logging.error("Encountered an error on command %s: %s" % (cmd, conn.match.group()))
            elif resp == 2:
                logging.error("Command %s timed out" % cmd)
            conn.prompt()
        else:
            logging.warning("VM %s will not be launched since it is already present on the system" % vm_name)

    # Restore timeout value at end of test
    conn.timeout = TIMEOUT

    return expectedvm_list


def get_novashowvalue(conn, vm_id, field=None):
    """ This returns a value from the nova show table, e.g. host or state 
        Inputs:
        * conn - ID of pexpect session
        * vm_id - ID of VM to query
        * field is the type of data to return from the nova show table, e.g. host, vm_state, etc.
          note1: this field needs to match with a field in the actual nova show table
          note2: this has not been tested with all field types, only host and vm_state
          note3: if field is not provided, we assume you want the host the vm is on
        Outputs:
        * hostname - hostname of machine hosting VM, e.g. compute-0, controller-1, etc. or
        * resp - non-zero value if we didn't match
    """

    # Assume the user wants the host the VM is on if field is None
    if not field:
        field == "host"

    # Pull the value field associated with the corresponding property field
    # Note, only tested with the "host" field so far
    extract = "(?<=%s)\s*\|\s(.*?)\s*\|\r\n" % field 

    cmd = "nova show %s" % vm_id

    conn.prompt()
    conn.sendline(cmd)

    resp = conn.expect([extract, ERROR, PROMPT, pexpect.TIMEOUT])
    if resp == 0:
        value = conn.match.group(1)
        conn.prompt()
        logging.info("VM %s has %s field equal to %s" % (vm_id, field, value))
    elif resp == 1:
        logging.warning("Could not determine value of field %s associated with VM %s" % (field, vm_id))
        return resp
    elif resp == 3:
        logging.warning("Command %s timed out." % cmd)
        return resp

    return value 


def exec_novaresizeconf(conn, vm_id):
    """ This issues a resize confirm after cold migration.
        Inputs:
        * conn - ID of pexpect session
        * vm_id - ID of VM to query
        Outputs:
        * Return resp - 0 for success, non-zero for fail
    """

    conn.prompt()
    cmd = "nova resize-confirm %s" % vm_id
    conn.sendline(cmd)
    resp = conn.expect([PROMPT, ERROR, pexpect.TIMEOUT])
    if resp == 1:
        logging.error("Failed to resize-confirm VM %s due to %s" % (vm_id, conn.match.group()))
    elif resp == 2:
        logging.warning("Command %s timed out." % cmd)

    return resp
    

def exec_vm_migrate(conn, vm_id, migration_type="cold", dest_host=None):
    """ This migrates a VM (either cold or live). 
        Inputs:
        * conn - ID of pexpect session
        * vm_id = ID of VM to migrate
        * migrate_type - either "cold" or "live"
        * dest_host (optional) - destination host for migration, e.g. compute-1 
        Outputs:
        * Return True if the VM migrated
        * Return False if the VM could not migrate.
    """

    logging.info("Performing a %s migrate of VM %s" % (migration_type, vm_id))

    # Determine which host we're on
    original_vm_host = get_novashowvalue(conn, vm_id, "host")
    logging.info("VM %s is on host %s" % (vm_id, original_vm_host))

    # Issue the appropriate migration type
    if migration_type == "cold":
        cmd = "nova migrate --poll %s" % vm_id
    elif migration_type == "live" and not dest_host:
        cmd = "nova live-migration %s" % vm_id
    else:
        cmd = "nova live-migration %s %s" % (vm_id, dest_host)

    # Issue migration
    conn.prompt()
    logging.info(cmd)
    conn.sendline(cmd)
    migration_start_time = datetime.datetime.now()

    resp = conn.expect(["Finished", ERROR, PROMPT, pexpect.TIMEOUT])
    if resp == 1:
        logging.error("VM %s failed to %s migration due to %s" % (vm_id, migration_type, conn.group.match()))
    elif resp == 3:
        logging.warning("Command %s timed out." % cmd)

    # if resp == 0 and cold migrate we need to confirm resize.  We'll need to poll first (TO DO)

    # If we selected live migration, poll for the VM state
    if migration_type == "live":
        status = ""
        while status != "ACTIVE":
            status = get_novashowvalue(conn, vm_id, "status")
            # check if error is correct status (NOTE)
            if status == "ERROR":
                logging.warning("VM %s is reporting error state" % vm_id)
                break
            wait_time = 2
            time.sleep(wait_time)
        if status == "ACTIVE":
            migration_end_time = datetime.datetime.now()
            logging.info("The VM is done migrating.")
            migration_time = migration_end_time - migration_start_time
            logging.info("VM %s took %s seconds to %s migrate" % (vm_id, migration_time, migration_type))
            logging.info("Margin of error in measurements is approx. %s second(s)." % (wait_time))
            # Check if we really migrated to the correct host
            postmig_vm_host = get_novashowvalue(conn, vm_id, "host")
            if dest_host:
                if postmig_vm_host == dest_host:
                    logging.info("VM %s migrated from %s to %s as expected" % (vm_id, original_vm_host, postmig_vm_host)) 
                else:
                    logging.warning("VM %s was expected to migrate to %s but instead is on %s" %
                                   (vm_id, dest_host, postmig_vm_host))
                    return False
            else:
                if postmig_vm_host != original_vm_host:
                    logging.info("VM %s migrated off of %s as expected, and is now on host %s" % (vm_id, original_vm_host, postmig_vm_host))
                else:
                    logging.warning("VM %s did not migrate off host" % (vm_id, original_vm_host)) 
                    return False
            
    return True

if __name__ == "__main__":

    # Extract command line arguments
    if len(sys.argv) < 2:
        sys.exit("Usage: ./test_live_migrate_vms.py <Floating IP of host machine>")
    else:
        floating_ip = sys.argv[1]

    # Enable logging
    logging.basicConfig(level=logging.INFO)

    # Test case name
    test_name = "test_sanityrefresh_live_migrate_vms"

    # Get time
    test_start_time = datetime.datetime.now()
    logging.info("Starting %s at %s" % (test_name, test_start_time))

    # Establish connection
    conn = Session(timeout=TIMEOUT)
    conn.connect(hostname=floating_ip, username=USERNAME, password=PASSWORD)
    conn.setecho(ECHO)

    # source /etc/nova/openrc
    source_nova(conn)

    # Get the UUID for the user we're interested in
    tenant1_id = get_userid(conn, "tenant1")

    # Get the list of VMs on the system 
    vm_list = get_novavms(conn, "name")

    # Check that there are VMs on the system
    if len(vm_list) == 0:
        # Untested
        logging.warning("There are no VMs present on the system.")
        logging.info("The test will now launch some VMs in order to proceed.")
        expectedvm_list = exec_launchvmscript(conn, "tenant1")
        vm_list = get_novavms(conn, "name")
        if vm_list != expectedvm_list:
            logging.error("Expected the following VMs: %s, instead we have the following: %s" %  
                         (expectedvm_list, vm_list))
            exit(-1)
    
    # we'll want to check what controller or compute a VM is on and then
    # live migrate without a destination host
    logging.info("Live migrating without a destination host specified")
    vm_list = get_novavms(conn, "id")
    exec_vm_migrate(conn, vm_list[1], "live")
   
    # Automatically determine another host to migrate to, could be controller or compute 
    logging.info("Live migrating with a destination host specified")
    current_vm_host = get_novashowvalue(conn, vm_list[1], "host")
    logging.info("VM %s is on host %s" % (vm_list[1], current_vm_host))
    # Get personality of VM host
    host_personality = get_hostpersonality(conn, current_vm_host)
    logging.info("Learn what hosts are on the system.")
    hostname_list, cont_hostname_list, comp_hostname_list, stor_hostname_list = get_hosts(conn)

    if host_personality == "controller":
        subset_hostname_list = cont_hostname_list
        subset_hostname_list.remove(current_vm_host)
        dest_vm_host = random.choice(subset_hostname_list)
    elif host_personality == "compute":
        subset_hostname_list = comp_hostname_list
        subset_hostname_list.remove(current_vm_host)
        dest_vm_host = random.choice(subset_hostname_list)
    logging.info("Live migrating VM %s from %s to %s" % (vm_list[1], current_vm_host, dest_vm_host)) 
    exec_vm_migrate(conn, vm_list[1], "live", dest_vm_host)
    
    # Do a cold migrate 
    #logging.info("Cold migrating instance")
    #current_vm_host = get_novashowvalue(conn, vm_list[1], "host")
    #logging.info("VM %s is on host %s" % (vm_list[1], current_vm_host))
    #exec_vm_migrate(conn, vm_list[1], "cold")

    # Test end time
    test_end_time = datetime.datetime.now()
    test_duration = test_end_time - test_start_time
    logging.info("Ending %s at %s" % (test_name, test_end_time))
    logging.info("Test ran for %s" % test_duration)
