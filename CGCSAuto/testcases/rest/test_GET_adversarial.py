import pytest
from utils.tis_log import LOG
from utils.rest import Rest
from keywords import system_helper, host_helper
import string

def test_GET_ihosts_host_id_shortUUID():
    """
    Test GET of <resource> with valid authentication and upper 
         case UUID values.
         RFC 4122 covers the need for uppercase UUID values

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
    path = "/ihosts/{}/addresses"
    r = Rest('sysinv')
    LOG.info(path)
    LOG.info(system_helper.get_hostnames())
    for host in system_helper.get_hostnames():
        uuid = host_helper.get_hostshow_value(host, 'uuid')
        LOG.info("host: {} uuid: {}".format(host,uuid))
        message = "Using requests GET {} with proper authentication"
        LOG.tc_step(message.format(path))

        short_uuid = uuid[:-1]
        status_code, text = r.get(resource=path.format(short_uuid), 
                                  auth=True)
        message = "Retrieved: status_code: {} message: {}"
        LOG.info(message.format(status_code, text))
        LOG.tc_step("Determine if expected code of 400 is received")
        message = "Expected code of 400 - received {} and message {}"
        assert status_code == 400, message.format(status_code, text)

def test_GET_ihosts_host_id_invalidUUID():
    """
    Test GET of <resource> with valid authentication and upper 
         case UUID values.
         RFC 4122 covers the need for uppercase UUID values

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
    path = "/ihosts/{}/addresses"
    r = Rest('sysinv')
    LOG.info(path)
    LOG.info(system_helper.get_hostnames())
    for host in system_helper.get_hostnames():
        uuid = host_helper.get_hostshow_value(host, 'uuid')
        LOG.info("host: {} uuid: {}".format(host,uuid))
        message = "Using requests GET {} with proper authentication"
        LOG.tc_step(message.format(path))

        # shift a->g, b->h, etc - all to generate invalid uuid
        shifted_uuid = ''.join(map(lambda x: chr((ord(x) 
                                                  - ord('a') + 6) 
                                                 % 26 + ord('a')) 
                                   if x in string.ascii_lowercase 
                                   else x, uuid.lower()))
        status_code, text = r.get(resource=path.format(shifted_uuid), 
                                  auth=True)
        message = "Retrieved: status_code: {} message: {}"
        LOG.info(message.format(status_code, text))
        LOG.tc_step("Determine if expected code of 400 is received")
        message = "Expected code of 400 - received {} and message {}"
        assert status_code == 400, message.format(status_code, text)


def test_GET_ihosts_host_id_uppercaseUUID():
    """
    Test GET of <resource> with valid authentication and upper 
         case UUID values.
         RFC 4122 covers the need for uppercase UUID values

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
    path = "/ihosts/{}/addresses"
    r = Rest('sysinv')
    LOG.info("This test case will FAIL until CGTS-8265 is resolved")
    LOG.info(system_helper.get_hostnames())
    for host in system_helper.get_hostnames():
        uuid = host_helper.get_hostshow_value(host, 'uuid')
        message = "Using requests GET {} with proper authentication"
        LOG.tc_step(message.format(path))

        status_code, text = r.get(resource=path.format(uuid.upper()), 
                                  auth=True)
        message = "Retrieved: status_code: {} message: {}"
        LOG.info(message.format(status_code, text))
        LOG.tc_step("Determine if expected code of 200 is received")
        message = "Expected code of 200 - received {} and message {}"
        assert status_code == 200, message.format(status_code, text)
