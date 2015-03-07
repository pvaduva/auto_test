#!/usr/bin/env python

"""
This script will be used to return all the hosts on the system in a dict
format that is usable by WASSP.  It will do so, by making a REST API
query on:

http://oamFloatingIP:systemPort/version/ihosts

e.g.

http://128.224.150.94:6385/v1/ihosts

Using the returned data, the script will pull out the hostnames and
return a data structure in the following format:

{"HOST":"[{'node':'controller-0'},{'node':'controller-1'},{'node':'compute-0'}]"} 

Prior to doing the REST API query for hosts, the script will need to 
obtain the X-Auth-Token. 


"""

# imports
import json
import logging
import pprint
import requests 
import sys

# constants
TENANT_NAME = "admin"
USERNAME = "admin"
PASSWD = "admin"

KEYSTONE_PORT = 5000 
KEYSTONE_VERSION = "v2.0"

SYSTEM_PORT = 6385 
SYSTEM_VERSION = "v1"

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
                                                "password": PASSWD}}}

    resp = requests.post(url, headers=headers, data=json.dumps(payload))

    if resp.status_code == requests.codes.ok:
        data = json.loads(resp.text)
        id = data['access']['token']['id']
        logging.info("The token is: %s" % id)
        return id
    else:
        logging.error("Failed to get token due to error: %s" % resp.status_code)
        exit(resp.status_code)

def get_request (ip, id, extension):
    """ This function uses the obtained x-auth-token and performs a get request.
    """

    url = compose_url(ip, SYSTEM_PORT, SYSTEM_VERSION, extension)
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

def extract_hostinfo(hosts):
    """ This function extracts host information and puts it in an ugly dict format 
        to be usable by our existing wassp code.
    """

    host_list = [] 

    for k, l in hosts.items():
        for d in l:
            for key in d:
                if key == "hostname":
                    host = {"node": d[key]}
                    host_list.append(host)                    
    
    host_dict = {"HOST": str(host_list)}
   
    return(host_dict) 

if __name__ == "__main__":

    #logging.basicConfig(level=logging.DEBUG)
    pp = pprint.PrettyPrinter(indent=4)

    # get floating ip from command line
    ip = sys.argv[1]

    # get x-auth-token
    id = authenticate(ip)

    # check that we can make a REST API query for the extensions and then
    # validate the extension data to ensure we get data of the right type
    logging.info("GET host information")
    hosts = get_request(ip, id, "ihosts")
    #pp.pprint(hosts)
    host_dict = extract_hostinfo(hosts)

    exit(0)
