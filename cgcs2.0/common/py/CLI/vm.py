#!/usr/bin/python

""" This contains common functions related to VMs. 
"""

import os
import sys
import re
import time
import random
import string
import copy

# class is in non-standard location so refine python search path
sys.path.append(os.path.expanduser('~/wassp-repos/testcases/cgcs/cgcs2.0/common/py'))

from CLI.cli import *
from CLI import nova

def exec_launchvmscript(conn, tenant_name, vm_type, num_vms):
    """ This launches a VM using the scripts created by lab_setup.  Note, we'll have to switch to
        controller-0, since that's where the scripts are.
        Inputs:
        * conn (string) - ID of pexpect session
        * tenant_name (string) - name of tenant to launch VMs as, e.g. tenant1, tenant2
        * vm_type (string) - either avp, virtio or vswitch
        * num_vms (int) - number of vms of that type to launch, e.g. 3
        Outputs:
        * expectedvm_list (list) - return list of VMs that we try to launch
        Enhancements: allow user to specify type of VM to launch and number of instances
    """

    # FIX ME: Need to adjust if we are not on controller-0

    expectedvm_list = []
    # Up the timeout since VMs need additional time to launch
    conn.timeout = 60

    # Get the list of VMs that are already launched on the system by name
    vm_list = nova.get_novavms(conn, "name")

    # Cap VM launch to 4
    if num_vms > 4:
        num_vms = 4
        logging.warning("lab_setup provides launch scripts for 4 VMs of a \
                         particular type, so the number of VMs to launch will \
                         be capped at 4.")

    # Launch the desired VMs
    for vm_index in range(1, (num_vms + 1)):
        # Construct the name of VM to launch, i.e. tenant1-avp1
        vm_name = "%s-%s%s" % (tenant_name, vm_type, str(vm_index))
        expectedvm_list.append(vm_name)
        if vm_name not in vm_list:
            cmd = "~/instances_group0/./launch_%s.sh" % vm_name
            conn.sendline(cmd)
            resp = conn.expect(["Finished", ERROR, pexpect.TIMEOUT, "No such file"])
            if resp == 1:
                logging.error("Encountered an error on command %s: %s" % (cmd, conn.match.group()))
            elif resp == 2:
                logging.error("Command %s timed out" % cmd)
            elif resp == 3:
                logging.warning("Launch script %s not found" % vm_name)
            conn.prompt()
        else:
            logging.warning("VM %s will not be launched since it is already present on the system" % vm_name)

    # Restore timeout value at end of test
    conn.timeout = TIMEOUT

    return expectedvm_list

def exec_vm_migrate(conn, vm_id, migration_type="cold", option=None):
    """ This migrates a VM (either cold or live).
        Inputs:
        * conn - ID of pexpect session
        * vm_id = ID of VM to migrate
        * migrate_type - either "cold" or "live"
        * option (optional) - destination host for migration, e.g. compute-1, if we
                              selected "live" migrate
                            - "confirm" or "revert" if we selected "cold" migrate
        Outputs:
        * Return True if the VM migrated
        * Return False if the VM could not migrate.
    """

    logging.info("Performing a %s migrate of VM %s" % (migration_type, vm_id))

    # Determine which host we're on
    original_vm_host = nova.get_novashowvalue(conn, vm_id, "host")

    # Issue the appropriate migration type
    if migration_type == "cold":
        cmd = "nova migrate --poll %s" % vm_id
    elif migration_type == "live" and not option:
        cmd = "nova live-migration %s" % vm_id
    else:
        cmd = "nova live-migration %s %s" % (vm_id, option)

    # Maria add
    original_status = nova.get_novashowvalue(conn, vm_id, "status")
    # Maria add end

    # Issue migration
    #conn.prompt()
    logging.info(cmd)
    conn.sendline(cmd)
    migration_start_time = datetime.datetime.now()

    resp = conn.expect(["Finished", ERROR, PROMPT, pexpect.TIMEOUT])
    if resp == 1:
        logging.error("VM %s failed to %s migration due to %s" % (vm_id, migration_type, conn.group.match()))
    elif resp == 3:
        logging.warning("Command %s timed out." % cmd)
    #conn.prompt()

    # If we selected live migration, poll for the VM state
    if migration_type == "live":
        status = ""
        while status != original_status: 
        #while status != "ACTIVE":
            status = nova.get_novashowvalue(conn, vm_id, "status")
            # check if error is correct status (NOTE)
            if status == "ERROR":
                logging.warning("VM %s is reporting error state" % vm_id)
                break
            wait_time = 3
            time.sleep(wait_time)
        if status == original_status: 
        #if status == "ACTIVE":
            migration_end_time = datetime.datetime.now()
            logging.info("The VM is done migrating.")
            #migration_time = migration_end_time - migration_start_time
            #logging.info("VM %s took %s seconds to %s migrate" % (vm_id, migration_time, migration_type))
            #logging.info("Margin of error in measurements is approx. %s second(s) for polling." % (wait_time))
            #logging.info("Loss due to automation process is approx. 10 second(s)")
            # Check if we really migrated to the correct host
            postmig_vm_host = nova.get_novashowvalue(conn, vm_id, "host")
            if option:
                if postmig_vm_host == option:
                    logging.info("VM %s %s migrated from %s to %s as expected" %
                                (vm_id, migration_type, original_vm_host, postmig_vm_host))
                    migration_time = migration_end_time - migration_start_time
                    logging.info("VM %s took %s seconds to %s migrate" % (vm_id, migration_time, migration_type))
                else:
                    logging.warning("VM %s was expected to migrate to %s but instead is on %s" %
                                   (vm_id, option, postmig_vm_host))
                    return False
            else:
                if postmig_vm_host != original_vm_host:
                    logging.info("VM %s %s migrated off of %s as expected, and is now on host %s" %
                                (vm_id, migration_type, original_vm_host, postmig_vm_host))
                    migration_time = migration_end_time - migration_start_time
                    logging.info("VM %s took %s seconds to %s migrate" % (vm_id, migration_time, migration_type))
                else:
                    logging.warning("VM %s did not migrate off host %s" % (vm_id, original_vm_host))
                    return False
    else:
       # If we selected cold migrate
        # Once the status is set to verify resize, we're ready to go to the next step
        status = ""
        while status != "VERIFY_RESIZE":
            status = nova.get_novashowvalue(conn, vm_id, "status")
            if status == "ERROR":
                logging.warning("VM %s is reporting error state." % vm_id)
                break
            wait_time = 2
            time.sleep(wait_time)
        if status == "VERIFY_RESIZE":
            if option == "revert":
                nova.exec_novaresizeorrevert(conn, vm_id, "revert")
            else:
                nova.exec_novaresizeorrevert(conn, vm_id)
            migration_end_time = datetime.datetime.now()
            while status != "ACTIVE":
                status = nova.get_novashowvalue(conn, vm_id, "status")
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
               #logging.info("Margin of error in measurements is approx. %s second(s) for polling." % (wait_time))
               #logging.info("Loss due to automation process is approx. 10 second(s)")
               postmig_vm_host = nova.get_novashowvalue(conn, vm_id, "host")
               if option:
                   if postmig_vm_host == original_vm_host:
                       logging.info("VM %s was on host %s, reverted cold migration, and is now back on host %s as expected" %
                                   (vm_id, original_vm_host, postmig_vm_host))
                   else:
                       logging.warning("VM %s should have been on host %s after cold migrate revert, but is instead on host %s" %
                                      (vm_id, original_vm_host, postmig_vm_host))
               else:
                   if postmig_vm_host != original_vm_host:
                       logging.info("VM %s %s migrated off of %s as expected, and is now on host %s" %
                                   (vm_id, migration_type, original_vm_host, postmig_vm_host))
                   else:
                       logging.warning("VM %s did not migrate off host" % (vm_id, original_vm_host))
                       return False

    return True


def get_vm_mgmt_ips(conn):
    """ This function returns the management IPs for all VMs on the system.
        We make the assumption that the management IPs start with "192"
        Inputs:
        conn - ID of pexpect session
        Outputs:
        vm_mgmtiplist - list of all VM management IPs
    """

    vm_list = nova.get_novavms(conn, "id")
    all_public_mgmt_iplist = []
    for item in vm_list:
        public_mgmt_iplist = []
        vm_ip = nova.get_novashowvalue(conn, item, "mgmt-net network")
        vm_ip_list = string.split(vm_ip, ", ")
        for ip in vm_ip_list:
            if ip.startswith("192"):
                public_mgmt_iplist.append(ip)
        logging.info("VM %s has the following public mgmt network IPs: %s" % (item, public_mgmt_iplist))
        all_public_mgmt_iplist = all_public_mgmt_iplist + public_mgmt_iplist

    return all_public_mgmt_iplist

def ping_vms_from_natbox(conn, ping_duration=None):
    """ This function pings all VM management IPs from the NAT box
        Inputs:
        * conn - Id of pexpect session
        * ping_time - integer value for how long you want to ping the VMs (seconds)
        Outputs:
        * testFailed_flag - True if the test failed, or False if it didn't 
    """
  
    testFailed_flag = False

    # get the management ips
    all_public_mgmt_iplist = get_vm_mgmt_ips(conn) 

    # if ping_duration was not provided, default to 10 seconds
    if not ping_duration:
        ping_duration= 10

    logging.info("Establishing connection to NAT box")
    connNAT = Session(timeout=TIMEOUT)
    connNAT.connect(hostname=NAT_HOSTNAME, username=NAT_USERNAME, password=NAT_PASSWORD)
    connNAT.setecho(ECHO)

    # Construct monitor script command
    addresses = ",".join(all_public_mgmt_iplist)
    tools_path = "cd /home/cgcs/tools"
    monitor_cmd = "python monitor.py --addresses %s" % addresses
    cmd = tools_path + " && " + monitor_cmd

    connNAT.sendline(cmd)

    total_ips = str(len(all_public_mgmt_iplist))
    # We are looking for the (X/X) field in the monitor script to see if it's done
    # Once it's done, wait and then quit.  We wait to give the ping time to 
    # run for a bit
    extract = "\(" + total_ips + "\/" + total_ips + "\).*"
    resp = connNAT.expect([extract, pexpect.TIMEOUT])
    if resp == 0:
        time.sleep(ping_duration)
        connNAT.sendline("q\n")
        connNAT.sendline("exit\n")
    monitor_output = connNAT.before + connNAT.after

    # VM can be reachable, not reachable, or reachable with packet loss
    extract_pos = "%s is reachable"
    extract_neg1 = "is not reachable"
    extract_neg2 = "is reachable (missing.*)"
    for ip in all_public_mgmt_iplist:
        match1 = re.findall(extract_neg1, monitor_output)
        match2 = re.findall(extract_neg2, monitor_output)
        if match1 or match2:
            testFailed_flag = True

    return testFailed_flag

def ping_between_vms(conn, no_packets=10):
    """ This function pings all VM management IPs from a VM.  It will ssh to the NAT box, and
        then ssh to each VM, ping all management IPs and then exit the VM.
        Inputs:
        * conn - Id of pexpect session
        * no_packets (integer) - number of ping packets for each VM 
        Outputs:
        * testFailed_flag - True if the test failed, False if the test passed 
    """

    # Authentication sequences to try 
    vm_auth = {"root": "root", "ubuntu": "ubuntu"}
 
    testFailed_flag = False

    # Get the management ips
    all_public_mgmt_iplist = get_vm_mgmt_ips(conn) 

    logging.info("Establishing connection to NAT box")
    connNAT = Session(timeout=TIMEOUT)
    connNAT.connect(hostname=NAT_HOSTNAME, username=NAT_USERNAME, password=NAT_PASSWORD)
    connNAT.setecho(ECHO)

    for ip in all_public_mgmt_iplist:
        # Revise the ping list so we don't bother ping our own IP
        revised_ping_list = copy.deepcopy(all_public_mgmt_iplist)
        revised_ping_list.remove(ip) 
        loginfailures = 0
        for item in vm_auth:
            logging.info("Trying to ssh into %s with %s credentials" % (ip, item))
            ssh_opts = "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
            cmd = "ssh %s %s@%s" % (ssh_opts, item, ip)
            connNAT.sendline(cmd)
            resp = connNAT.expect(["assword:", pexpect.TIMEOUT])
            if resp == 0:
                connNAT.sendline(vm_auth[item])
                # Might need to revisit how PROMPT is detected
                resp = connNAT.expect(["~#", PROMPT, pexpect.TIMEOUT])
                if resp == 0 or resp == 1:
		    # Increase the timeout while we're pinging (assume each
		    # ping is 1 sec) and add some buffer
                    connNAT.timeout = no_packets + 5
                    for vm_ip in revised_ping_list: 
                        cmd = "ping -c%s %s" % (str(no_packets), vm_ip)
                        connNAT.sendline(cmd)
                        resp = connNAT.expect(["([\d]{1,3})\% packet loss", pexpect.TIMEOUT])
                        if resp == 0:
                            #print("Conn.match.group: %s" % connNAT.match.group())
                            #print("Conn.match.group1: %s" % connNAT.match.group(1))
                            percent_pktloss = connNAT.match.group(1)
                            if int(percent_pktloss) == 100:
                                logging.error("100% packet loss observed when pinging IP %s" % vm_ip)
                                testFailed_flag = True 
                            elif int(percent_pktloss) > 0:
				logging.warning("%d\% packet loss observed when pinging IP %s" % (percent_pktloss, vm_ip))
                            else:
                                logging.info("No packet loss observed when ping IP %s" % (vm_ip))
                        else:
                            logging.warning("Command %s timed out" % cmd)
                        connNAT.tiemout = TIMEOUT
                        connNAT.prompt()
                    # Restore timeout to original values
                    connNAT.timeout = TIMEOUT
                    # Test writing to VM filesystem    
                    connNAT.sendline("touch writingtovmfilesystem.txt\n")
                    # FIXME: Confirm that the file exists
                    connNAT.sendline("exit\n") 
                    break
                else:
                    # send Ctrl-C and then try the other username/password
                    logging.warning("Command %s timed out" % cmd) 
                    connNAT.sendline('\003') 
                    loginfailures = loginfailures + 1 
            else:
                logging.warning("Command %s timed out" % cmd)
        # If we tried all the login options and failed, the test has failed.
        if loginfailures == len(vm_auth):
            logging.error("System was not able to ssh to VM with IP %s" % ip)
            testFailed_flag = True

    # Logout when we're done with the NAT box
    connNAT.logout()  

    return testFailed_flag

