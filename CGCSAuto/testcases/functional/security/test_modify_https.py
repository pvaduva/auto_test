from pytest import fixture

from keywords import security_helper, keystone_helper
from utils.tis_log import LOG


@fixture(scope='module')
def https_config(request):
    is_https = keystone_helper.is_https_enabled()

    def _revert():
        if not is_https:
            LOG.fixture_step("Revert system to https {}.".format('enabled' if is_https else 'disabled'))
            security_helper.modify_https(enable_https=is_https)
    request.addfinalizer(_revert)

    return is_https


# TODO: disable for now and re-enable it when HTTPS feature is ready
def _test_modify_https(https_config):
    """
    Test enable/disable https

    Test Steps:
        - Enable/Disable https via system modify
        - Ensure config-out-of-date alarm is cleared
        - Ensure openstack endpint list updated
        - Repeat above steps for disable/enable

    """
    is_https = https_config
    configs = (False, True) if is_https else (True, False)

    for config in configs:
        LOG.tc_step("{} https on system".format('Enable' if config else 'Disable'))
        security_helper.modify_https(enable_https=config)
