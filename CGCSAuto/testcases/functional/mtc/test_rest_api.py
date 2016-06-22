import json
import requests
import copy

from pytest import fixture, mark, skip
from keywords import keystone_helper
from utils.tis_log import LOG
from consts.proj_vars import ProjVar

NEUTRON_PORT = 9696
NEUTRON_VER = "v2.0"
CEIL_PORT = 8777
CEIL_VER = "v2"

#default expected number of pipelines
NUM_PIPELINES = 2
IP_ADDR = ProjVar.get_var('lab')['floating ip']
TOKEN = keystone_helper.get_user_token()[0]


def create_url(ip, port, ver, extension):
    url = "http://{}:{}/{}/{}".format(ip, port, ver, extension)
    return url


def get_request(url):
    """
    Sends a GET request to the server

    Args:
        url (str): the url to access

    Returns: the response from the GET request

    """
    headers = {"Content-Type": "application/json",
               "Accept": "application/json",
               "X-Auth-Token": TOKEN}
    resp = requests.get(url, headers=headers)

    if resp.status_code == requests.codes.ok:
        data = json.loads(resp.text)
        LOG.info("The returned data is: {}".format(data))
        return data


def put_request(url, payload):
    """
    Sends a PUT request to the server

    Args:
        url (str): the url to access
        payload (dict): the data to PUT to the server

    Returns (dict): the data that got PUT to the server

    """
    headers = {"Content-Type": "application/json",
               "Accept": "application/json",
               "X-Auth-Token": TOKEN}
    resp = requests.put(url, headers=headers, data=json.dumps(payload))

    if resp.status_code == requests.codes.ok:
        payload = json.loads(resp.text)
        LOG.info("The returned data is: {}".format(payload))

        return payload


def validate_extensions(data):
    """
    This function validates that the extension contains the correct data
    types, as defined by the API doc, namely, unicode string or list.
    """

    for k, l in data.items():
        for d in l:
            for key in d:
                if key != u"links":
                    #it seems in Python3 all strings are in unicode
                    if not isinstance(d[key], str):
                        LOG.error("Received wrong data type for key %s" % key)
                        LOG.error("Unicode expected, %s received" % type(d[key]))
                        LOG.error("Extension data type test: FAILED")
                        return 1
                else:
                    if type(d[key]) is not list:
                        LOG.error("Received wrong data type for key %s" % key)
                        LOG.error("List expected, %s received" % type(d[key]))
                        LOG.error("Extension data type test: FAILED")
                        return 1

    return 0


def validate_pipelines(data):
    """
    This function validates that the pipelines contains the correct data
    Types, as defined by the API doc.
    """

    # We should probably report which field is of the wrong type if we have a fail
    #The json objects don't seem to have a 'meters' attribute anymore.
    # type(data["meters"]) is not list or \
    if type(data["name"]) is not str or \
        type(data["location"]) is not str or \
        type(data["compress"]) is not bool or \
        type(data["enabled"]) is not bool or \
        type(data["backup_count"]) is not int or \
        type(data["max_bytes"]) is not int:
            LOG.error("Received wrong data type")
            LOG.error("Pipelines data type test: FAILED")
            return 1

    return 0


def test_get_extensions():
    """
    Test that we can REST API query for extensions and that we receive valid data from the query.

    Test Steps:
        - Send HTTP GET request to the server (Neutron port) for extensions
        - Check that the data received is in a valid form

    """
    url = create_url(IP_ADDR, NEUTRON_PORT, NEUTRON_VER, 'extensions')
    data = get_request(url)

    res = validate_extensions(data)
    assert res == 0, "FAIL: The extensions returned are not valid."


def test_get_host_pipelines():
    """
    Do a bulk query of all pipelines and see if we get the expected number of pipelines.
    Expect at least 2 pipelines.

    Test Steps:
        - Send HTTP GET request to the server (Ceilometer port) to get the pipelines
        - Check that we get at least 2 pipelines

    """
    url = create_url(IP_ADDR, CEIL_PORT, CEIL_VER, 'wrs-pipelines')
    pipelines = get_request(url)
    LOG.tc_step("Checking how many pipelines were returned. Expecting at least {}.".format(NUM_PIPELINES))
    assert len(pipelines) >= NUM_PIPELINES, "FAIL: Expected {} pipelines. Only {} pipelines were found."\
                                            .format(NUM_PIPELINES, len(pipelines))


def test_get_individual_pipelines():
    """
    Check that Each pipeline's information is in a valid form.

    Test Steps:
        - Send HTTP GET request to the server (Ceilometer port) to get the pipelines
        - Validate the information of each returned pipeline

    """

    url = create_url(IP_ADDR, CEIL_PORT, CEIL_VER, 'wrs-pipelines')
    pipelines = get_request(url)
    for item in pipelines:
        LOG.tc_step("Validating {}".format(item))
        res = validate_pipelines(item)
        #might not work if there is no name attribute
        assert res == 0, "FAIL: Pipeline {} has invalid information.".format(item["name"])


def test_put_pipelines():
    """
    Modify some of the parameters of a pipeline and confirm that they are modifiied correctly.

    Test Steps:
        - Send HTTP GET request to the server (Ceilometer port) to get the pipelines
        - Record the current values of the pipelines
        - Change some of the parameters of each pipeline and use HTTP PUT to get them to the server
        - Use HTTP GET to make sure that each pipeline changed as intended

    Teardown:
        - Use HTTP PUT to bring the original pipelines back to the server
        - Check that the pipelines are the same as they were originally

    """
    url = create_url(IP_ADDR, CEIL_PORT, CEIL_VER, 'wrs-pipelines')
    pipelines = get_request(url)
    for item in pipelines:
        pipeline_id = "wrs-pipelines/" + item["name"]
        pipeline_url = create_url(IP_ADDR, CEIL_PORT, CEIL_VER, pipeline_id)
        LOG.tc_step("Getting original pipeline data")
        payload = get_request(pipeline_url)
        copy_payload = copy.deepcopy(payload)

        payload['backup_count'] = 7
        payload['compress'] = False
        payload['enabled'] = False
        payload['max_bytes'] = 9000000

        LOG.tc_step("Sending modified pipeline to server")
        put_request(pipeline_url, payload)
        data = get_request(pipeline_url)

        LOG.tc_step("Reverting back to original pipeline data")
        put_request(pipeline_url, copy_payload)
        reset_pipeline = get_request(pipeline_url)
        assert payload == data, "FAIL: The pipeline {}'s values were not changed correctly.".format(item["name"])
        assert copy_payload == reset_pipeline, "FAIL: The pipeline {} was not set back to its original state."\
                                               .format(item["name"])
