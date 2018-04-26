import time
from pytest import mark, fixture, skip

from keywords import host_helper, system_helper, keystone_helper, security_helper
from utils.tis_log import LOG
from consts.auth import Tenant
from consts.reasons import SkipSysType


@fixture()
def _revert_admin_pw(request):
    prev_pswd = Tenant.ADMIN['password']

    def _revert():
        # revert password
        LOG.fixture_step("Reverting admin password to '{}'".format(prev_pswd))
        keystone_helper.update_user('admin', password=prev_pswd)

        LOG.fixture_step("Sleep for 300 seconds after admin password change")
        time.sleep(300)  # CGTS-6928
        host = system_helper.get_standby_controller_name()
        assert host, "No standby controller on system"
        # lock-unlock original standby
        res, out = host_helper.lock_host(host=host)
        res = host_helper.unlock_host(host)
        LOG.info("Unlock hosts result: {}".format(res))
        # swact
        host_helper.swact_host()
        host = system_helper.get_standby_controller_name()

        # lock-unlock original active
        res, out = host_helper.lock_host(host=host)
        res = host_helper.unlock_host(host)
        LOG.info("Unlock hosts result: {}".format(res))

        assert prev_pswd == security_helper.get_admin_password_in_keyring()
    request.addfinalizer(_revert)


@fixture(scope='module')
def less_than_two_cons():
    return len(system_helper.get_controllers()) < 2


@mark.usefixtures('check_alarms')
@mark.parametrize(('scenario'), [
    # mark.p1('lock_standby_change_pswd'),
    mark.p1('enable_https')
])
def test_admin_password(scenario, less_than_two_cons, _revert_admin_pw):
    """
    Test the admin password change

    Test Steps:
        - change password CGTS-6766
        - lock standby controller change password and unlock
        - change passowrd and swact
        - check alarams
        - enable https

    """
    if 'swact' in scenario and less_than_two_cons:
        skip(SkipSysType.LESS_THAN_TWO_CONTROLLERS)

    host = system_helper.get_standby_controller_name()
    assert host, "No standby controller on system"

    if scenario == "lock_standby_change_pswd":
        # lock the standby
        LOG.tc_step("Attempting to lock {}".format(host))
        res, out = host_helper.lock_host(host=host)
        LOG.info("Result of the lock was: {}".format(res))

    # change password
    prev_pswd = Tenant.ADMIN['password']
    post_pswd = '!{}9'.format(prev_pswd)

    LOG.tc_step('Changing admin password to {}'.format(post_pswd))
    code, output = keystone_helper.update_user('admin', password=post_pswd)

    LOG.tc_step("Sleep for 300 seconds after admin password change")
    time.sleep(300)  # CGTS-6928,CGTS-6321

    # lock-unlock original standby
    LOG.tc_step("Attempting to lock {}".format(host))
    res, out = host_helper.lock_host(host=host)
    LOG.tc_step("Unlock host {}".format(host))
    res = host_helper.unlock_host(host)
    LOG.info("Unlock hosts result: {}".format(res))

    # swact
    LOG.tc_step("Swact active controller")
    host_helper.swact_host()
    host = system_helper.get_standby_controller_name()

    # lock-unlock original active
    LOG.tc_step("Attempting to lock {}".format(host))
    res, out = host_helper.lock_host(host=host)
    LOG.tc_step("Unlock host {}".format(host))
    res = host_helper.unlock_host(host)
    LOG.info("Unlock hosts result: {}".format(res))

    LOG.tc_step("Check admin password is updated in keyring")
    assert post_pswd == security_helper.get_admin_password_in_keyring()

    if scenario == "enable_https":

        if keystone_helper.is_https_lab():
            # if https lab change to http
            LOG.tc_step("Enable http on https lab")
            change_lab_security = "false"
        else:
            # if http lab change to https
            LOG.tc_step("Enable https on http lab")
            change_lab_security = "true"

        code, msg = system_helper.set_system_info(fail_ok=True, con_ssh=None, auth_info=Tenant.ADMIN,
                                                  https_enabled='{}'.format(change_lab_security))
        time.sleep(300)
        if change_lab_security == "true":
            # verify lab is now https and revert lab back to original http security state
            assert keystone_helper.is_https_lab()
            LOG.tc_step("revert http on https lab")
            system_helper.set_system_info(fail_ok=True, con_ssh=None, auth_info=Tenant.ADMIN,
                                          https_enabled='{}'.format('false'))
        else:
            # verify lab is now http and revert lab back to original https security state
            assert not keystone_helper.is_https_lab()
            LOG.tc_step("revert https on http lab")
            system_helper.set_system_info(fail_ok=True, con_ssh=None, auth_info=Tenant.ADMIN,
                                          https_enabled='{}'.format('true'))

