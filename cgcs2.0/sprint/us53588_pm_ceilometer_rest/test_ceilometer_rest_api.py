#!/usr/bin/env python

"""
This script will be used to validate the feature US58533: PM: Ceilometer
REST API: Proper Handling of Extensions.  This script will need to initiate 
a get on three queries:

http://<ipaddress>:8777/v2/extensions
http://<ipaddress>:8777/v2/wrs-pipelines
http://<ipaddress>:8777/v2/wrs-pipelines/<pipeline_id>

and validate the output. Where pipeline_id is the name of one of the returned
pipelines.

In addition, the script should do a put on a single pipeline using the
pipeline_id and modify one or more of the parameters.

In order to achieve this, first the script will need to authenticate with
Keystone.

The script should be updated so that command line options for IP, username, etc.
can be supplied by the user, or that the needed parameters are pulled from the 
barcode.ini files.

Lastly, any values modified by the put requests should be restored at the end of the
test.

The script is design to be invoked by WASSP using CALL.  CALL will fail if the exit
code of the script is not zero.  This program can be invoked without WASSP via:

./test_ceilometer_rest_api.py <FloatingIPAddress>

e.g.  ./test_ceilometer_rest.api.py 10.10.10.2

Future Enhancements:
* Do proper command line arg handling including adding a help, validating args, etc.
* Better handle the data type validation

"""

# imports
import copy
import json
import logging
import pprint
import requests 
import sys

# constants
TENANT_NAME = "admin"
USERNAME = "admin"
PASSWD = "admin"
#IP = "10.10.10.2"

KEYSTONE_PORT = 5000 
KEYSTONE_VERSION = "v2.0"

TELEMETRY_PORT = 8777
TELEMETRY_VERSION = "v2"

NUM_PIPELINES = 2

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

    url = compose_url(ip, TELEMETRY_PORT, TELEMETRY_VERSION, extension)
    headers = {"Content-Type": "application/json", 
               "Accept": "application/json",
               "X-Auth-Token": id} 

    resp = requests.get(url, headers=headers)

    if resp.status_code == requests.codes.ok:
        data = json.loads(resp.text)
        logging.info("The returned data is: %s" % data)
        #pp.pprint(data)
        return data 
    else:
        logging.error("Failed get request due to error: %s" % resp.status_code)
        logging.info("GET Request Test: FAILED")
        exit(resp.status_code)

def put_request(ip, id, extension, payload):
    """ This function uses the obtained x-auth-token and performs a post
        request.
    """

    url = compose_url(ip, TELEMETRY_PORT, TELEMETRY_VERSION, extension)
    headers = {"Content-Type": "application/json", 
               "Accept": "application/json",
               "X-Auth-Token": id} 

    resp = requests.put(url, headers=headers, data=json.dumps(payload))

    if resp.status_code == requests.codes.ok:
        payload = json.loads(resp.text)
        logging.info("The returned data is: %s" % payload)
        #pp.pprint(data)
        return data 
    else:
        logging.error("Failed put request due to error: %s" % resp.status_code)
        logging.error("We were trying to send: %s" % payload)
        logging.info("PUT Request Test: FAILED")
        exit(resp.status_code)

def validate_extension(data):
    """ This function validates that the extension contains the correct data
        types, as defined by the API doc, namely, unicode string or list.
    """
    
    for k, l in data.iteritems():
        for d in l:
            for key in d:
                if key != u"links":	
                    if type(d[key]) is not unicode:
                        logging.error("Received wrong data type for key %s" % key)
                        logging.error("Unicode expected, %s received" % type(d[key]))
                        logging.error("Extension data type test: FAILED")
                        exit(1) 
                else:
                     if type(d[key]) is not list:
                        logging.error("Received wrong data type for key %s" % key)
                        logging.error("List expected, %s received" % type(d[key]))
                        logging.error("Extension data type test: FAILED")
                        exit(1) 

def validate_pipelines(data):
    """ This function validates that the pipelines contains the correct data
        types, as defined by the API doc.
    """

    # We should probably report which field is of the wrong type if we have a fail
    if type(data["name"]) is not unicode or \
       type(data["meters"]) is not list or \
       type(data["location"]) is not unicode or \
       type(data["compress"]) is not bool or \
       type(data["enabled"]) is not bool or \
       type(data["backup_count"]) is not int or \
       type(data["max_bytes"]) is not int:
        logging.error("Received wrong data type")
        logging.error("Pipelines data type test: FAILED")
        exit(1)    

if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)
    pp = pprint.PrettyPrinter(indent=4)

    # get floating ip from command line
    ip = sys.argv[1]

    # get x-auth-token
    id = authenticate(ip)

    # check that we can make a REST API query for the extensions and then
    # validate the extension data to ensure we get data of the right type
    logging.info("TEST 1 - Get Extensions")
    data = get_request(ip, id, "extensions")
    validate_extension(data) 

    # Do a bulk query of all pipelines and see if we receive the expected
    # number of pipelines.  We expect at least 2.
    logging.info("TEST 2 - Get All Pipelines")
    pipelines = get_request(ip, id, "wrs-pipelines") 
    if len(pipelines) < NUM_PIPELINES:
        logging.error("ERROR: %s pipelines expected but %s were received" % 
                      (NUM_PIPELINES, len(pipelines)))
        logging.error("Pipelines test: FAILED")
        exit(1)

    # Construct a query requesting a specific pipeline and validate the
    # data to ensure it is of the right type
    logging.info("TEST 3 - Get Individual Pipelines")
    for item in pipelines:
        pipeline_id = "wrs-pipelines/" + item["name"]
        data = get_request(ip, id, pipeline_id) 
        validate_pipelines(data)

    # Modify a specific pipeline by changing a few of the parameters, and
    # confirm the data has been appropriately modified.  Restore the pipeline 
    #parameters at the end of the test
    logging.info("TEST 4 - Modify Individual Pipelines")
    for item in pipelines:
        pipeline_id = "wrs-pipelines/" + item["name"]
        payload = get_request(ip, id, pipeline_id)
        copy_payload = copy.deepcopy(payload) 
        payload['backup_count'] = 7
        payload['compress'] = False 
        payload['enabled'] = False 
        payload['max_bytes'] = 9000000 
        put_request(ip, id, pipeline_id, payload)
        data = get_request(ip, id, pipeline_id) 
        if payload != data:
            logging.error("ERROR: Data was not properly provisioned on PUT") 
            logging.error("Pipelines modification test: FAILED")
            exit(1)

        # Undo changes after test is done
        put_request(ip, id, pipeline_id, copy_payload)
        data = get_request(ip, id, pipeline_id) 
        logging.info(data)
        if copy_payload != data:
            logging.error("Failed to restore data to original values")
            logging.error("Test Teardown: FAILED")
            exit(1)

    exit(0)
