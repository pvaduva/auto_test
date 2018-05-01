import time
from pytest import mark, fixture, skip

from keywords import security_helper, keystone_helper
from utils.tis_log import LOG
from consts.auth import Tenant,CliAuth


@fixture(scope='function')
def revert_lab_state(request):
    lab_is_https = keystone_helper.is_https_lab()

    def _revert():
        # revert https version
        if lab_is_https:
            LOG.fixture_step("revert http lab back to https lab")
            security_helper.modify_https(enable_https=True)
        else:
            LOG.fixture_step("revert https lab back to http lab")
            security_helper.modify_https(enable_https=False)
    request.addfinalizer(_revert)

    return lab_is_https


@mark.usefixtures('check_alarms')
def test_enable_https(revert_lab_state):
    """
    Test enable https on lab

    Test Steps:
        - enable https
        - check proper warnings are set after change
        - revert back to previous http state

    """
    lab_is_https = revert_lab_state
    if lab_is_https:
        skip("Cannot enable https when lab is already in https")
    LOG.tc_step("enable https on http lab")
    security_helper.modify_https(enable_https=True)
    assert keystone_helper.is_https_lab()


@mark.usefixtures('check_alarms')
def test_disable_https(revert_lab_state):
    """
    Test disable https on lab

    Test Steps:
        - disable https
        - check proper warnings are set after change
        - revert back to previous https state

    """
    lab_is_https = revert_lab_state
    if not lab_is_https:
        skip("Cannot disable https when lab is already in http")
    LOG.tc_step("disable https on https lab")
    security_helper.modify_https(enable_https=False)
    assert not keystone_helper.is_https_lab()

