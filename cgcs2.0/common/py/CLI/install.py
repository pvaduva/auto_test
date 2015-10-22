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

