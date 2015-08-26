#!/usr/bin/python

""" This contains common functions related to VMs. 
"""

import os
import sys
import re
import time
import random

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

