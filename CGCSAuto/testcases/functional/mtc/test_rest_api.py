import copy
import time

from consts import timeout
from consts.cgcs import HTTPPorts
from pytest import fixture, mark, skip
from keywords import html_helper, host_helper, system_helper
from utils.tis_log import LOG


#default expected number of pipelines
NUM_PIPELINES = 2
IP_ADDR = html_helper.get_ip_addr()
TOKEN = html_helper.get_user_token()[0]

HEADERS = {"Content-Type": "application/json",
           "Accept": "application/json",
           "X-Auth-Token": TOKEN}


@fixture(scope='function')
def prepare_modify_cpu(request):
    """
    Finds the first unlocked compute node.
    Creates a cpu profile.

    Returns (tuple): (name of the host, uuid of the host, uuid of the new cpu profile)

    """
    computes = host_helper.get_hosts(personality='compute', administrative='unlocked')
    if not computes:
        skip("There were no unlocked compute nodes.")
    host = computes[0]
    uuid = host_helper.get_hostshow_value(host=host, field='uuid')

    url = html_helper.create_url(IP_ADDR, HTTPPorts.SYS_PORT, HTTPPorts.SYS_VER, 'iprofile')
    data = {'hostname': 'test_compute_profile',
            'profiletype': 'cpu',
            'ihost_uuid': uuid}
    resp = html_helper.post_request(url, headers=HEADERS, data=data)
    iprofile_uuid = resp['uuid']
    LOG.info("The new profile uuid is: {}".format(iprofile_uuid))


    def unlock():
        host_helper.apply_cpu_profile(host, iprofile_uuid)
        if 'locked' == host_helper.get_hostshow_value(host, field='administrative'):
            host_helper.unlock_host(host)

        url = html_helper.create_url(IP_ADDR, HTTPPorts.SYS_PORT, HTTPPorts.SYS_VER,
                                     'iprofile/{}'.format(iprofile_uuid))
        html_helper.delete_request(url, headers=HEADERS)

    request.addfinalizer(unlock)

    return host, uuid, iprofile_uuid


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
    url = html_helper.create_url(IP_ADDR, HTTPPorts.NEUTRON_PORT, HTTPPorts.NEUTRON_VER, 'extensions')
    data = html_helper.get_request(url, headers=HEADERS)

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
    url = html_helper.create_url(IP_ADDR, HTTPPorts.CEIL_PORT, HTTPPorts.CEIL_VER, 'wrs-pipelines')
    pipelines = html_helper.get_request(url, headers=HEADERS)
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

    url = html_helper.create_url(IP_ADDR, HTTPPorts.CEIL_PORT, HTTPPorts.CEIL_VER, 'wrs-pipelines')
    pipelines = html_helper.get_request(url, headers=HEADERS)
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
    url = html_helper.create_url(IP_ADDR, HTTPPorts.CEIL_PORT, HTTPPorts.CEIL_VER, 'wrs-pipelines')
    pipelines = html_helper.get_request(url, headers=HEADERS)
    for item in pipelines:
        pipeline_id = "wrs-pipelines/" + item["name"]
        pipeline_url = html_helper.create_url(IP_ADDR, HTTPPorts.CEIL_PORT, HTTPPorts.CEIL_VER, pipeline_id)
        LOG.tc_step("Getting original pipeline data")
        payload = html_helper.get_request(pipeline_url, headers=HEADERS)
        copy_payload = copy.deepcopy(payload)

        payload['backup_count'] = 7
        payload['compress'] = False
        payload['enabled'] = False
        payload['max_bytes'] = 9000000

        LOG.tc_step("Sending modified pipeline to server")
        html_helper.put_request(pipeline_url, payload, headers=HEADERS)
        data = html_helper.get_request(pipeline_url, headers=HEADERS)

        LOG.tc_step("Reverting back to original pipeline data")
        html_helper.put_request(pipeline_url, copy_payload, headers=HEADERS)
        reset_pipeline = html_helper.get_request(pipeline_url, headers=HEADERS)
        assert payload == data, "FAIL: The pipeline {}'s values were not changed correctly.".format(item["name"])
        assert copy_payload == reset_pipeline, "FAIL: The pipeline {} was not set back to its original state."\
                                               .format(item["name"])


def test_modify_cpu(prepare_modify_cpu):
    """
    TC2043
    Modify cpu parameters through API

    Test Steps:
        - Lock a compute
        - Apply the profile to the locked compute
        - Unlock compute and verify that the correct changes were made

    Teardown:
        - Delete cpu profile
        - Revert cpu changes

    """
    name, uuid, iprofile_uuid = prepare_modify_cpu

    url = html_helper.create_url(IP_ADDR, HTTPPorts.SYS_PORT, HTTPPorts.SYS_VER, "ihosts")
    hosts = html_helper.get_request(url=url, headers=HEADERS)['ihosts']
    found = False
    for host in hosts:
        if host['uuid'] == uuid:
            found = True
            break

    assert found, "FAIL: {} is not listed in the API".format(name)

    LOG.tc_step("Locking {}".format(name))
    url = html_helper.create_url(IP_ADDR, HTTPPorts.SYS_PORT, HTTPPorts.SYS_VER, "ihosts/{}".format(uuid))
    lock_data = [{"path": "/action", "value": "lock", "op": "replace"}]
    html_helper.patch_request(url=url, headers=HEADERS, data=lock_data)
    time.sleep(timeout.HostTimeout.COMPUTE_LOCK)

    host = html_helper.get_request(url=url, headers=HEADERS)
    assert 'locked' == host['administrative'], "FAIL: Couldn't lock {}".format(name)

    res, out = host_helper.modify_host_cpu(name, 'shared', p0=1, p1=1, timeout=180)
    assert 0 == res, "FAIL: The cpus weren't even modified by cli"

    LOG.tc_step("Applying cpu profile")
    data = [{"path": "/iprofile_uuid", "value": "{}".format(iprofile_uuid), "op": "replace"},
            {"path": "/action", "value": "apply-profile", "op": "replace"}]
    resp = html_helper.patch_request(url=url, headers=HEADERS, data=data)

    res, out = host_helper.compare_host_to_cpuprofile(name, iprofile_uuid)
    assert 0 == res, "FAIL: The host doesn't have the same cpu functions as the cpu profile"
