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
1) Check all hosts are unlocked/available via system host-list (DONE)
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

def compose_url(ip, port, version, field):
    """ This function composes a URL based on the controller IP, port, version
        and field name 
    """

    url = "http://%s:%s/%s/%s" % (ip, port, version, field) 
    return url

def authenticate(ip):
    """ This function authenticates with Keystone and returns the
        authorization token.
    """
    logging.info("Authenticating with Keystone to get token")
    
    url = compose_url(ip, KEYSTONE_PORT, KEYSTONE_VERSION, "tokens") 
    headers = {"Content-Type": "application/json", 
               "User-Agent": "python-keystoneclient"} 
    payload = {"auth": {"tenantName": TENANT_NAME, 
                        "passwordCredentials": {"username": USERNAME, 
                                                "password": PASSWORD}}}

    resp = requests.post(url, headers=headers, data=json.dumps(payload))

    if resp.status_code == requests.codes.ok:
        data = json.loads(resp.text)
        id = data['access']['token']['id']
        logging.info("The token is: %s" % id)
        return id
    else:
        logging.error("Failed to get token due to error: %s" % resp.status_code)
        exit(resp.status_code)

def get_request(ip, id, port, version, extension):
    """ This function uses the obtained x-auth-token and performs a get request.
    """

    url = compose_url(ip, port, version, extension)
    headers = {"Content-Type": "application/json", 
               "Accept": "application/json",
               "X-Auth-Token": id} 

    resp = requests.get(url, headers=headers)

    if resp.status_code == requests.codes.ok:
        data = json.loads(resp.text)
        #logging.info("The returned data is: %s" % data)
        #pp.pprint(data)
        return data 
    else:
        logging.error("Failed get request due to error: %s" % resp.status_code)
        logging.info("GET Request Test: FAILED")
        exit(resp.status_code)

def put_request(ip, id, port, version, extension, payload):
    """ This function uses the obtained x-auth-token and performs a post
        request.
    """

    url = compose_url(ip, port, version, extension)
    headers = {"Content-Type": "application/json", 
               "Accept": "application/json",
               "X-Auth-Token": id} 

    resp = requests.put(url, headers=headers, data=json.dumps(payload))

    if resp.status_code == requests.codes.ok:
        payload = json.loads(resp.text)
        logging.info("The returned data is: %s" % payload)
        pp.pprint(data)
        return data 
    else:
        logging.error("Failed put request due to error: %s" % resp.status_code)
        logging.error("We were trying to send: %s" % payload)
        logging.info("PUT Request Test: FAILED")
        exit(resp.status_code)

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

def get_hoststate(ip, id, port, version, extension):
    """ This function returns the availability state of each host as a dict in the form 
        {controller-0: available}, {controller-1: offline} ... 
    """

    host_dict = {}

    data = get_request(ip, id, port, version, extension)
    for k, l in data.items():
        for d in l:
            for key in d:
                if key == u"availability":
                    avail = d[key]
                if key == u"hostname":
                    host = d[key]

            if avail and host:
                host_dict[host] = avail

    return host_dict

#def check_all_hosts_avail(ip, id, port, version, extension):
def check_all_hosts_avail(hoststate_dict):
    """ This function checks that all hosts are in available state.
    """
    
    #hoststate_dict = get_hoststate(ip, id, IHOST_PORT, IHOST_VERSION, "ihosts")
    #pp.pprint(hoststate_dict)
    flag = False 

    for host in hoststate_dict:
        if hoststate_dict[host] != u"available":
            print("Host %s was expected to be available but is %s") % (host, hoststate_dict[host])
            flag = True

    # Return 0 if all nodes are available
    # Return 1 if not all nodes are available            
    if flag == False:
        msg = "PASS: All nodes are in available state as expected" 
    else:
        msg = "FAIL: Not all nodes were in available state" 

    return msg

def list_nova_services(ip, id, port, version, extension):
    """ This function lists nova services.
    """

    data = get_request(ip, id, port, version, extension)
  
    return data

if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)
    pp = pprint.PrettyPrinter(indent=4)

    # get floating ip from command line (FIX ME: we can do better than this)
    ip = sys.argv[1]

    # get x-auth-token
    id = authenticate(ip)

    logging.info("1) Return the hosts in the system") 
    hostname_list = get_value_from_ihosts_table(ip, id, IHOST_PORT, IHOST_VERSION, "ihosts", u"hostname")
    pp.pprint(hostname_list)

    logging.info("2) Get host state")
    hoststate_dict = get_hoststate(ip, id, IHOST_PORT, IHOST_VERSION, "ihosts")
    pp.pprint(hoststate_dict)

    logging.info("3) Check if all hosts are in available state")
    #check_all_hosts_avail(ip, id, IHOST_PORT, IHOST_VERSION, "ihosts")
    msg = check_all_hosts_avail(hoststate_dict)
    pp.pprint(msg)

    logging.info("4) Check all expected services are up via nova service-list")
    #nova_services = list_nova_services(ip, id, NOVA_PORT, NOVA_VERSION, "OS-KSADM/services")
    #pp.pprint(services)

    nova_services = list_nova_services(ip, id, "8774", "v2.0", "os-services")
    pp.pprint(nova_services)
    exit(0)
