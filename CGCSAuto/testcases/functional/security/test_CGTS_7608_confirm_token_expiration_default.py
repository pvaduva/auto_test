import pytest
from utils.tis_log import LOG
from keywords import system_helper


def test_CGTS_7608_confirm_token_expiration_default():
    """
    test_CGTS_7608_confirm_token_expiration_default
    https://jira.wrs.com:8443/browse/CGTS-7608

    Args:
        n/a

    Prerequisites: system is running

    Test Setups:
        n/a
    Test Steps:
        - perform system service-parameter-list
        - search for token-expiration in table
          - should be 3600 - if not, we fail!
    Test Teardown:
        n/a
    """
    expected_default_value = "3600"

    LOG.tc_step("Perform system service-parameter-list")
    result_list = system_helper.\
                  get_service_parameter_values(name='token_expiration')

    LOG.tc_step("Search for token-expiration in table")
    for default_value in result_list:
        message = "Should be: {} Read: {}"
        LOG.info(message.format(default_value, expected_default_value))
        message = "Expected {} received {}"
        assert default_value == expected_default_value, \
            message.format(expected_default_value, default_value)
