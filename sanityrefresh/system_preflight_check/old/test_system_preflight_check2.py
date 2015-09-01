#!/usr/bin/env python

"""
Usage:
./test_system_preflight_check.py <FloatingIPAddress>

e.g.  ./test_system_preflight_check.py 10.10.10.2

Assumptions:
* None

Objective:
* The objective of this test is to summarize the condition of the system to 
make it easier to diagnose system failures.  

Test Steps:
1) Check all hosts are unlocked/available via system host-list
2) Check all expected services are up via nova service-list
3) Check there are no unexpected alarms via system alarm-list
4) Check VMs have been created and for HB VMs, check heartbeat services are up
5) Run sm-dump
6) Check that flavors have been created via nova flavor-list
7) Check that all images are available via glance image-list
8) List networks are available via nova providernet-list

Future Enhancements:
*
"""

# imports
import copy
import json
import logging
import pprint
import requests 
import sys

from restpkg.constants import *
from restpkg.restapi import *

def get_value_from_ihosts_table(ip, id, port, version, extension, value):
    """ This function returns a list of values from the ihosts table. 
    """

    value_list = []
 
    data = get_request(ip, id, port, version, extension)
    for k, l in data.items():
        for d in l:
            for key in d:
                if key == value:
                    #pp.pprint(d[key])    
                    value_list.append(d[key])

    return value_list 

def check_host_availability_state(ip, id, port, version, extension, host, expected_state):
    """ This function checked a host for the desired availability state. 
    """
    data = get_request(ip, id, port, version, extension)
    #for k, l in data.items():
    #    for d in l:
    #        for key in d:
    #            if d[u"hostname"] == host and d[u"availability"] == expected_state:
    #                print(host, d[u"availability"]) 



if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)
    pp = pprint.PrettyPrinter(indent=4)

    # get floating ip from command line (FIX ME: we can do better than this)
    ip = sys.argv[1]

    # get x-auth-token
    id = authenticate(ip)

    logging.info("Return the hosts in the system") 
    hostname_list = get_value_from_ihosts_table(ip, id, IHOST_PORT, IHOST_VERSION, "ihosts", u"hostname")
    pp.pprint(hostname_list)
    logging.info("Check if all hosts are in available state")
    availability_list = get_value_from_ihosts_table(ip, id, IHOST_PORT, IHOST_VERSION, "ihosts", u"availability")
    pp.pprint(availability_list)
    #for host in hostname_list:
    #    extension = "ihosts/" + host
    #    data = get_value_from_ihosts_table(ip, id, IHOST_PORT, IHOST_VERSION, extension, u"availability")
    #    pp.pprint(data) 

    exit(0)
