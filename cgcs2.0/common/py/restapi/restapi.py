#!/usr/bin/env python

"""
Base class for REST API
"""

import json
import logging
import pprint
import requests
import sys

from constants import *

class RestAPI:
    """A base class to instantiate REST calls.
    """
    
    def __init__(self, ip=IP, port=IDENTITY_PORT, version=IDENTITY_VERSION, field="tokens", token=None,
                 tenant_name=TENANT_NAME, tenant_token=None, username=USERNAME, password=PASSWORD):
        """ This method initializes a REST API object. 
        """ 
        self.ip = ip
        self.port = port
        self.version = version
        self.field = field
        self.token = None
        self.tenant_name = tenant_name
        self.tenant_token = None
        self.username = username
        self.password = password

	logging.info("Authenticating with Keystone to get token")

	url = RestAPI._compose_url(self)
	headers = {"Content-Type": "application/json",
		   "User-Agent": "python-keystoneclient"}
	payload = {"auth": {"tenantName": self.tenant_name,
			    "passwordCredentials": {"username": self.username,
						    "password": self.password}}}

	resp = requests.post(url, headers=headers, data=json.dumps(payload))

	if resp.status_code == requests.codes.ok:
	    data = json.loads(resp.text)
            pprint.pprint(data)
	    self.token = data['access']['token']['id']
            self.tenant_token = data['access']['token']['tenant']['id']
	    logging.info("The token is: %s" % self.token)
	else:
	    logging.error("Failed to get token due to error: %s" % resp.status_code)
	    exit(resp.status_code)

    def __str__(self):
        """ Print out the class object in readable format for debugging purposes.
        """
        return str(pprint.pprint(vars(self)))

    def _compose_url(self):
	""" This method composes a URL based on the controller IP, port, 
            version and field name.  It is invoked by other methods. 
	"""

	url = "http://%s:%s/%s/%s" % (self.ip, self.port, self.version, self.field)
	return url

    def get_request(self, port, version, field):
	""" This method uses the obtained x-auth-token and performs a get request.
	"""

        self.port = port
        self.version = version
        self.field = field

	url = RestAPI._compose_url(self)
	headers = {"Content-Type": "application/json",
		   "Accept": "application/json",
		   "X-Auth-Token": self.token}

	resp = requests.get(url, headers=headers)

	if resp.status_code == requests.codes.ok:
	    data = json.loads(resp.text)
	    #logging.info("The returned data is: %s" % data)
	    #pprint.pprint(data)
	    return data
	else:
	    logging.error("Failed get request due to error: %s" % resp.status_code)
	    logging.info("GET Request Test: FAILED")
	    exit(resp.status_code)

    def put_request(self, port, version, field, payload):
	""" This method uses the obtained x-auth-token and performs a post
	    request.
	"""

        self.port = port
        self.version = version
        self.field = field

	url = RestAPI._compose_url(self)
	headers = {"Content-Type": "application/json",
		   "Accept": "application/json",
		   "X-Auth-Token": self.token}

	resp = requests.put(url, headers=headers, data=json.dumps(payload))

	if resp.status_code == requests.codes.ok:
	    payload = json.loads(resp.text)
	    #logging.info("The returned data is: %s" % payload)
	    pprint.pprint(payload)
	    return payload 
	else:
	    logging.error("Failed put request due to error: %s" % resp.status_code)
	    logging.error("We were trying to send: %s" % payload)
	    logging.info("PUT Request Test: FAILED")
	    exit(resp.status_code)

    def get_value(self, port, version, field, values):
	""" This is a generic method that performs a get request and extracts 
            specific values from the data.  Tested with sysinv only so far.

            For example, if we are querying the ihosts url, we can return all
            hostnames contained within by specifying hostname as the value
            argument.  We would obtain data in the format:

            [(u"controller-0", ), (u"controller-1", ), (u"compute-0", ), ... ]

            A list of tuples is returned.  

            We could also get multiple items, e.g. hostname and personality

            [(u"controller-0", "Controller-Active", ), (u"compute-0", )]

            ENHANCEMENT: Perfect application for recursion.
	"""

	value_list = []

	self.port = port 
	self.version = version 
	self.field = field

	data = RestAPI.get_request(self, port, version, field)
	for k, l in data.items():
	    for d in l:
                t = ()
		for key in d:
                    if isinstance(d[key], dict):
                        for item in d[key]:
                            if item in values:
                                t = t + (d[key][item], )
                    elif key in values: 
                        t = t + (d[key], )
	        value_list.append(t)

	return value_list

if __name__ == "__main__":
    # Code below is to test the methods of the class are working properly.
    # Invoke via ./<filename>    

    logging.basicConfig(level=logging.INFO)
    pp = pprint.PrettyPrinter(indent=4)

    # Init object and get token 
    logging.info("Init and display REST API object")
    x = RestAPI(ip="128.224.150.189")
    print(x)

    # Get list of hosts in the system 
    logging.info("Get list of hosts in system")
    values = [u"hostname"]
    #x.get_request(port=SYSINV_PORT, version=SYSINV_VERSION, field="ihosts")
    hostname_list = x.get_value(port=SYSINV_PORT, version=SYSINV_VERSION, field="ihosts", values=values)
    pp.pprint(hostname_list)

    # Get state of all hosts in the system 
    logging.info("Return availability of hosts in the system")
    values = [u"hostname", u"availability"]
    #x.get_request(port=SYSINV_PORT, version=SYSINV_VERSION, field="ihosts")
    hoststate_list = x.get_value(port=SYSINV_PORT, version=SYSINV_VERSION, field="ihosts", values=values)
    pp.pprint(hoststate_list)

    # Get personalities 
    logging.info("Return personalities of hosts in the system")
    values = [u"hostname", u"Personality"]
    #x.get_request(port=SYSINV_PORT, version=SYSINV_VERSION, field="ihosts")
    hoststate_list = x.get_value(port=SYSINV_PORT, version=SYSINV_VERSION, field="ihosts", values=values)
    pp.pprint(hoststate_list)
    
    # Get nova services
    logging.info("Get nova services")
    version = NOVA_VERSION + "/" + x.tenant_token
    values = [u"host", u"status", u"state", u"binary"]
    #x.get_request(port=NOVA_PORT, version=version, field="os-services")
    novaservice_list = x.get_value(port=NOVA_PORT, version=version, field="os-services", values=values)
    pp.pprint(novaservice_list) 
