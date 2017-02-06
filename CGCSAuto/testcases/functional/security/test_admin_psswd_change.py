from pytest import mark, fixture
from keywords import host_helper, system_helper, keystone_helper
from utils.tis_log import LOG
from consts.auth import Tenant


@fixture()
def _revert_admin_pw(request):
    prev_pswd = Tenant.ADMIN['password']

    def _revert():
        # revert password
        LOG.fixture_step("Reverting admin password to '{}'".format(prev_pswd))
        keystone_helper.update_user('admin', password=prev_pswd)
    request.add(_revert)


@mark.usefixtures('check_alarms')
@mark.parametrize(('scenario'), [
    # mark.p1(('lock_standby_change_pswd')),
    mark.p1(('change_pswd_swact')),
])
def test_admin_password(scenario):
    """
    Test the admin password change

    Test Steps:
        - lock standby controller change password and unlock
        - change passowrd and swact
        - check alarams

    """

    host = system_helper.get_standby_controller_name()
    if scenario == "lock_standby_change_pswd":
        # lock the standby
        LOG.tc_step("Attempting to lock {}".format(host))
        res, out = host_helper.lock_host(host=host)
        LOG.tc_step("Result of the lock was: {}".format(res))

    # change password
    prev_pswd = Tenant.ADMIN['password']
    post_pswd = "'!{}9'".format(prev_pswd)

    LOG.tc_step('Changing admin password to {}'.format(post_pswd))
    keystone_helper.update_user('admin', password=post_pswd)

    if scenario == "change_pswd_swact":
        host_helper.swact_host()
    else:
        LOG.tc_step("Unlock host {}".format(host))
        res = host_helper.unlock_host(host)
        LOG.info("Unlock hosts result: {}".format(res))
