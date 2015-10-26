#!/usr/bin/env python

"""
Functions to deal with system installation and provisioning.


Usage:

Assumptions:

Objective:

General Conventions:

Future Enhancements:
"""

import os
import sys
import subprocess
import re
from constants import *
import datetime
import logging
import string
import telnetlib

def target_action(barcode="", action="findmine"):
    """ This function takes a target barcode and performs an action using
        VLM.  Default behaviour is to pass no options to this function,
        which will result in it running action "findmine", which will return
        the barcode(s) reserved by the user.  Otherwise, the user will need to
        provide a barcode and specify a valid action to perform.  It is
        assumed the barcode and action are strings.

        Actions "reboot", "turnon", "turnoff", "unreserve", "all" require a
        "reserve" action to be performed first.

        Note, a valid barcode is required for all actions other than
        "findmine".

        The function will convert all actions to the valid case for VLM, e.g.
        "turnoff" will be converted to "turnOff", so the user only needs to
        specify the action and not worry about formatting.

        The "all" option is somewhat special.  It does a vlmTool getAttr all
        command.

        Inputs:
        * barcode - target barcode, e.g. "12345"
        * action - either "reserve", "unreserve", "reboot", "turnon",
        * "turnoff", "findmine", "all"

        Outputs:
         * 0 for success, 1 for failure except if the user has requested
         "findMine" or "all" as the action.  In the case of "findMine", it will
         return a list of target barcodes, e.g. ["22352", "22351"]. In the case
         of "all", we will return a dict of target attributes, e.g. {'Terminal
         Server Port': '2', 'Terminal Server IP': '128.224.150.130', ... }

        Notes:
        * VLM successful reserve - returns barcode
        * VLM unsuccessful reserve - returns blank line
        * VLM findMine (no targets) - returns blank line
        * VLM findMine (targets) - returns list of barcodes with space between
           22352 22351
        * VLM successful getAttr - returns string of attributes
        * VLM unsuccessful getAttr - returns ??
        * All other VLM commands return 1 for success, 0 for failure
    """

    # List of valid actions and actions that require target reservation prior
    # to usage.
    action_list = ["reserve", "unreserve", "turnon", "reboot", "turnoff",
                   "findmine", "all"]
    action_prereq = ["unreserve", "turnon", "reboot", "turnoff", "all"]

    # Check if the requested action type is valid
    if action.lower() not in action_list:
        msg = "%s is an invalid action.  Valid actions are: %s" % \
              (action, action_list)
        logging.error(msg)
        return 1

    # Lower case the action to make it easier to work with
    action = action.lower()

    # Check if valid barcode is present
    if action != "findmine" and not barcode:
        msg = "You must provide a valid barcode with action %s" % action
        logging.error(msg)
        return 1

    # Check which targets the user has reserved
    cmd = [VLM, "findMine"]
    reserved_targets = subprocess.check_output(cmd)
    if re.search("\d+", reserved_targets):
        msg = "You currently have the following targets reserved: %s" % \
              reserved_targets
        reserved_targets = reserved_targets.split()
    else:
       msg = "You currently have no reserved targets"
       reserved_targets = []
    logging.info(msg)

    # Return the reserved targets if user has requested them
    if action == "findmine":
        return reserved_targets

    # Check if user has requested an action that requires pre-target
    # reservation
    if (action in action_prereq and barcode not in reserved_targets):
        msg = "The action %s you requested, requires you to reserve %s first" % \
               (action, barcode)
        logging.error(msg)
        return 1
    else:
        if action != "all":
            # Convert actions to the correct format for VLM
            if action == "turnoff":
                action = "turnOff"
            elif action == "turnOn":
                action = "turnOn"

            cmd = [VLM, action, "-t", barcode]
            resp = subprocess.check_output(cmd)

            # Check VLM response
            if resp:
                msg = "Action %s on target %s was successful" % \
                      (action, barcode)
                logging.info(msg)
                return 0
            else:
                msg = "Action %s on target %s was not successful" %  \
                      (action, barcode)
                logging.error(msg)
                return 1
        else:
            # Return dict with all target attributes
            cmd = [VLM, "getAttr", "-t", barcode, action]
            resp = subprocess.check_output(cmd)
            if resp:
                resp_dict = {}
                resp = resp.split("\n")
                for line in resp:
                    if line:
                        output = line.split(":")
                        resp_dict[output[0].strip()] = output[1].strip()
                return(resp_dict)
            else:
                msg = "Unable to get attributes of target %s" % barcode
                logging.error(msg)
                return 1

def telnet_conn(ip_addr, port=23):
    """ This is used to establish a telnet connection to target.  When an IP
        address and a port are supplied, there is no need to explicitly open
        the connection.

        Inputs:
        * ip_addr - IP address
        * port - Port to use.  Default is port 23.

        Outputs:
        * tn_conn - returns a telnet connection ID
    """

    tn_conn = telnetlib.Telnet(ip_addr, port)

    return tn_conn

def telnet_login(tn_conn, timeout=TIMEOUT, username=USERNAME,
                 password=PASSWORD):
    """ This is used to wait for the login prompt on a target and then
        authenticate
        Inputs:
        * tn_conn - telnet connection ID
        * timeout - how long to wait for a response (seconds)
        * username - name of user to login as
        * password - password of user that is logging in
        Outputs:
        * tn_conn - returns a telnet connect ID
    """

    resp = tn_conn.read_until("ogin:", timeout)
    if not resp:
        msg = "Login prompt not found in % seconds" % timeout
        logging.error(msg)
        exit(1)
    tn_conn.write(username + "\n")

    resp = tn_conn.read_until("assword:")
    if not resp:
        msg = "Password prompt not found"
        logging.error(msg)
        exit(1)
    tn_conn.write(password + "\n")

    return tn_conn

def telnet_send(tn_conn, cmd):
    """ This is used to send a command over the telnet connection.
        Inputs:
        * tn_conn - telnet connection ID
        * cmd - The command you want to send, e.g. wipedisk
        Outputs:
        * resp - return value from write command
    """

    resp = tn_conn.write(cmd + "\n")

    return resp

def telnet_wipedisk(tn_conn):
    """ This is used to send the wipedisk command to a target.
        Inputs:
        * tn_conn - telnet connection ID
        Outputs:
        * resp - return value from write command 
    """

    tn_conn.write("wipedisk\n")
    tn_conn.read_until("ompletely:")
    resp = tn_conn.write("wipediskscompletely\n")

    return resp

def telnet_biosboot(tn_conn):
    """ This is used to drop into the BIOS to select the appropriate boot
        device.
        Inputs:
        * tn_conn -telnet connection ID
        Outputs:
        * resp - 0 for success or just exits since we can't proceed if we can't
          boot
    """

    boot_device = "01"

    # Determine what type of machine we're on
    bios_type = ["Hewlett-Packard", "American Megatrends", "Phoenix"]

    resp = tn_conn.expect(bios_type, timeout)
    if not resp:
        msg = "BIOS not match any known BIOS type: %s" % \
               bios_type
        logging.error(msg)
        exit(1)

    if resp[0] == bios_type[0]:
        bios_key = ESC + "@"
    elif resp[0] == bios_type[1]:
        bios_key = F6
    elif resp[0] == bios_type[2]:
        bios_key = F12

    # Look for prompt asking user to Press a key
    tn_conn.read_until("Press")
    tn_conn.write(bios_key)

    # Look for some variant of text boot menu
    tn_conn.read_util("oot")

    # Loop through list and look for boot device
    while True:
        line = tn_conn.read_until("\n")
        if line and boot_device in line:
            tn_conn.write("\n")
            break
        elif line:
            tn_conn.write(DOWN)
        else:
            msg = "Could not find boot device named: %s" % boot_device
            logging.error(msg)
            exit(1)

    return 0

if __name__ == "__main__":

    # Name of test
    test_name = "system_install_self_test"

    # Extract command line arguments
    if len(sys.argv) < 2:
        sys.exit("Usage: ./%s.py <Barcode of Controller-0>" % test_name)
    else:
        cont0_barcode = sys.argv[1]

    # Enable logging
    test_start_time = datetime.datetime.now()
    logfile_name = test_name + "_" + test_start_time.strftime("%Y%m%d-%H%M%S")
    logfile_path = LOGFILE_BASE + logfile_name
    logging.basicConfig(level=logging.INFO, filename=logfile_path)
    logging.info("Starting %s at %s" % (test_name, test_start_time))

    # Reserve target
    resp = target_action(barcode=cont0_barcode, action="reserve")
    if resp:
        logging.error("Target reservation action failed.  Exiting program.")
        exit(1)

    # Get target attributes in order to get serial port information$
    target_attr = target_action(barcode=cont0_barcode, action="all")
    if not isinstance(target_attr, dict):
        msg = "Unable to retrieve attributes of target %s" % barcode
        logging.error(msg)
        exit(1)
    logging.info(target_attr)

    # Test end time
    test_end_time = datetime.datetime.now()
    test_duration = test_end_time - test_start_time
    logging.info("Ending %s at %s" % (test_name, test_end_time))
    logging.info("Test ran for %s" % test_duration)
