import pytest
from utils.tis_log import LOG
from utils.rest import Rest
from keywords import system_helper, host_helper


@pytest.mark.parametrize(
    'path', [
        ('/ihosts/{}/addresses'),
        ('/ihosts/{}/idisks'),
        ('/ihosts/{}/ilvgs'),
        ('/ihosts/{}/imemories'),
        ('/ihosts/{}/ipvs'),
        ('/ihosts/{}/isensors'),
        ('/ihosts/{}/isensorgroups'),
        ('/ihosts/{}/istors'),
        ('/ihosts/{}/pci_devices'),
        ('/ihosts/{}/routes'),
        ('/ihosts/{}'),
    ]
)
def test_GET_various_host_id_valid(path):
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
    LOG.info(path)
    LOG.info(system_helper.get_hostnames())
    for host in system_helper.get_hostnames():
        uuid = host_helper.get_hostshow_value(host, 'uuid')
        res = path.format(uuid)
        message = "Using requests GET {} with proper authentication"
        LOG.tc_step(message.format(res))
        status_code, text = r.get(resource=res, auth=True)
        message = "Retrieved: status_code: {} message: {}"
        LOG.info(message.format(status_code, text))
        if status_code == 404:
            pytest.skip("Unsupported resource in this configuration.")
        else:
            message = "Determine if expected code of 200 is received"
            LOG.tc_step(message)
            message = "Expected code of 200 - received {} and message {}"
            assert status_code == 200, message.format(status_code, text)
