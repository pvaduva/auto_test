import pytest
from utils.tis_log import LOG
from utils.rest import Rest
from consts.cgcs import HTTPPort


@pytest.fixture(scope='module')
def gnocchi_rest():
    r = Rest('gnocchi')
    return r


def get(rest_client, resource):
    """
    Test GET of <resource> with valid authentication.

    Args:
        n/a

    Prerequisites: system is running
    Test Setups:
        n/a
    Test Steps:
        - Using requests GET <resource> with proper authentication
        - Determine if expected status_code of 200 is received
    Test Teardown:
        n/a
    """
    message = "Using requests GET {} with proper authentication"
    LOG.tc_step(message.format(resource))

    status_code, text = rest_client.get(resource=resource, auth=True)
    message = "Retrieved: status_code: {} message: {}"
    LOG.debug(message.format(status_code, text))

    if status_code == 404:
        pytest.skip("Unsupported resource in this configuration.")
    else:
        LOG.tc_step("Determine if expected status_code of 200 is received")
        message = "Expected status_code of 200 - received {} and message {}"
        assert status_code == 200, message.format(status_code, text)


@pytest.mark.parametrize(('operation', 'resource'), [
    ('GET', '/v1/metric?limit=2'),
    ('GET', '/v1/resource'),
    ('GET', '/v1/resource_type'),
    ('GET', '/')
])
def test_good_authentication(gnocchi_rest, operation, resource):
    if operation == "GET":
        LOG.info("getting... {}".format(resource))
        get(gnocchi_rest, resource)
