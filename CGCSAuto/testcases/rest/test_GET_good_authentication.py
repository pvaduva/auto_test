import pytest
from utils.tis_log import LOG
from utils.rest import Rest
import sys

def get(resource):
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
    r = Rest('sysinv')
    message = "Using requests GET {} with proper authentication"
    LOG.tc_step(message.format(resource))

    status_code, text = r.get(resource=resource, auth=True)
    message = "Retrieved: status_code: {} message: {}"
    LOG.info(message.format(status_code, text))

    if status_code == 404:
        pytest.skip("Unsupported resource in this configuration.")
    else:
        LOG.tc_step("Determine if expected status_code of 200 is received")
        message = "Expected status_code of 200 - received {} and message {}"
        assert status_code == 200, message.format(status_code, text)

@pytest.mark.parametrize(
    'operation,resource', [
        ('GET','/addrpools'),
        ('GET','/ceph_mon'),
        ('GET','/clusters'),
        ('GET','/controller_fs'),
        ('GET','/drbdconfig'),
        ('GET','/event_log'),
        ('GET','/event_suppression'),
        ('GET','/health'),
        ('GET','/health/upgrade'),
        ('GET','/ialarms'),
        ('GET','/icommunity'),
        ('GET','/idns'),
        ('GET','/iextoam'),
        ('GET','/ihosts'),
        ('GET','/ihosts/bulk_export'),
        ('GET','/iinfra'),
        ('GET','/intp'),
        ('GET','/ipm'),
        ('GET','/iprofiles'),
        ('GET','/istorconfig'),
        ('GET','/isystems'),
        ('GET','/itrapdest'),
        ('GET','/lldp_agents'),
        ('GET','/lldp_neighbors'),
        ('GET','/loads'),
        ('GET','/networks'),
        ('GET','/remotelogging'),
        ('GET','/sdn_controller'),
        ('GET','/servicegroup'),
        ('GET','/servicenodes'),
        ('GET','/service_parameter'),
        ('GET','/services'),
        ('GET','/storage_backend'),
        ('GET','/storage_backend/usage'),
        ('GET','/storage_ceph'),
        ('GET','/storage_lvm'),
        # ('GET','/tpmconfig'),
        ('GET','/upgrade'),
        ('GET','/')
    ]
)
def test_good_authentication(operation, resource):
    if operation == "GET":
        LOG.info("getting... {}".format(resource))
        get(resource)


        
