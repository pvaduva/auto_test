import uuid

from pytest import mark, skip, fixture, param
from consts.auth import Tenant

from utils.tis_log import LOG
from utils.clients.telnet import TelnetClient
from utils.clients.ssh import ControllerClient
from utils import node, cli
from consts.proj_vars import ProjVar
from consts.cgcs import Prompt
from consts.filepaths import WRSROOT_HOME
from keywords import security_helper, system_helper


theLdapUserManager = security_helper.get_ldap_user_manager()


def _make_sure_user_exist(user_name, sudoer=False, secondary_group=False, password_expiry_days=90,
                          password_expiry_warn_days=2, delete_if_existing=True):
    """
    Make sure there is a LDAP User with the specified name existing, create one if not.

    Args:
        user_name (str):
                                    the user name of the LDAP User
        sudoer (bool):               create sudoer or not
        secondary_group (str):
                                    the second group the user belongs to
        password_expiry_days (int):

        password_expiry_warn_days (int):

        delete_if_existing (bool):
                                    Delete the existing user if True, otherwise keep the user

    Returns:
        bool                -   True if successful, False otherwise
        user_info (dict)    -   user settings
    """

    code, user_info = theLdapUserManager.create_ldap_user(
        user_name, check_if_existing=True, delete_if_existing=delete_if_existing, sudoer=sudoer,
        secondary_group=secondary_group, password_expiry_days=password_expiry_days,
        password_expiry_warn_days=password_expiry_warn_days)

    if code > 0:
        LOG.error('Failed to make sure the LDAP User {} exist with code {}'.format(user_name, code))
        return False, user_info

    return True, user_info


@mark.parametrize(('user_name', 'change_own_password'), [
    param('ldapuser04', True, marks=mark.p1),
    # param('ldapuser05', False, marks=mark.p1),
])
def test_ldap_change_password(user_name, change_own_password):
    """
    Test changing the password of the specified LDAP User

    User Stories:   US70961

    Args:
        user_name:
        change_own_password:

    Returns:

    """
    LOG.tc_step('Make sure LDAP user exist:{}, create it if not'.format(user_name))
    created, user_info = _make_sure_user_exist(user_name, delete_if_existing=True)
    if not created:
        skip('No LDAP User:{} existing or created to test changing password'.format(user_name))
        return

    password = user_info['passwords'][-1]
    new_password = 'N{}!'.format(str(uuid.uuid1()))
    LOG.tc_step('Change password for user:{}, current password:{}, new password:{}'.format(
        user_name, password, new_password))
    if change_own_password:
        changed = theLdapUserManager.change_ldap_user_password(
            user_name, password, new_password, change_own_password=change_own_password, disconnect_after=True)
        assert changed, \
            'Failed to change password for user:{} from old:{} to new password:{}'.format(
                user_name, password, new_password)
    else:
        # TODO CGTS-6638
        LOG.info('not implemented yet')
        skip('Skip rest of the test due to CGTS-6638')
        return

    LOG.info('OK, password of user {} was successfully changed from {} to {}'.format(
        user_name, password, new_password))


@mark.parametrize(('user_name', 'pre_store_credential'), [
    param('ldapuser04', False, marks=mark.p1),
    param('ldapuser05', True, marks=mark.p1),
])
def test_ldap_login_as_user(user_name, pre_store_credential):
    """
    Test login using the specified LDAP User

    User Stories:   US70961

    Args:
        user_name (str):    User name
        pre_store_credential (bool):    whether to store the keystone credentials

    Returns:

    Steps:
        1   Create a LDAP User with the specified name (delete it if any existing already)
        2   Login as the user (exit the login session after test)
    """

    LOG.tc_step('Make sure LDAP user exist:{}, create it if not'.format(user_name))
    created, user_info = _make_sure_user_exist(user_name, delete_if_existing=True)

    if not created:
        skip('No LDAP User:{} existing to delete'.format(user_name))
        return

    LOG.tc_step('Get the password of the user {}'.format(user_name))
    password = theLdapUserManager.get_ldap_user_password(user_name)
    LOG.debug('The password of the user: {}'.format(password))

    LOG.tc_step('Login as the LDAP User:{}'.format(user_name))
    logged_in, password, _ = theLdapUserManager.login_as_ldap_user(
        user_name, password, pre_store=pre_store_credential, disconnect_after=True)

    assert logged_in, 'Failed to login as the LDAP User:{}, password:{}'.format(user_name, password)

    LOG.info('OK, succeeded to login as the LDAP User: {}, password: {}'.format(user_name, password))


def test_ldap_delete_user():
    """
    Delete the LDAP User with the specified name

    Steps:
        1   Create a LDAP User with the specified name (using the existing one if there's any)
        2   Delete the LDAP User
    """
    user_name = 'ldapuser04'
    
    LOG.tc_step('Make sure LDAP user exist:{}, create it if not'.format(user_name))
    if not _make_sure_user_exist(user_name, delete_if_existing=False):
        skip('No LDAP User:{} existing to delete'.format(user_name))
        return

    LOG.tc_step('Delete the LDAP User:{}'.format(user_name))
    code, output = theLdapUserManager.rm_ldap_user(user_name)
    assert 0 == code, 'Failed to delete the LDAP User, message={}'.format(output)

    LOG.tc_step('Verify that no user can be found with name:{}'.format(user_name))

    found, user_info = theLdapUserManager.find_ldap_user(user_name)
    assert not found, \
        'Failed, still can find the user after deleting, user_name:{}, user_info'.format(user_name, user_info)

    password = theLdapUserManager.get_ldap_user_password(user_name)
    logged_in, password, _ = theLdapUserManager.login_as_ldap_user(user_name, password=password, disconnect_after=True)
    assert not logged_in, 'Failed, still can login as the user:{} with password:{}'.format(user_name, password)

    LOG.info('The LDAP User:{} is successfully deleted'.format(user_name))


@mark.parametrize(('user_name', ), [
    param('ldapuser01', marks=mark.p1),
])
def test_ldap_find_user(user_name):
    """
    Search for the specified LDAP user

    User Stories:   US70961

    Args:
        user_name:

    Returns:

    Steps:
        1   Search the existing user using 'ldapfinger -u <user_name>'
        2   Verify the user can log in
    """

    LOG.tc_step('Make sure the LDAP User:{} exists, create one if it is not')
    if not _make_sure_user_exist(user_name):
        skip('No LDAP User:{} existing to delete'.format(user_name))
        return

    LOG.tc_step('Search for LDAP User with name:{}'.format(user_name))
    existing, user_info = theLdapUserManager.find_ldap_user(user_name)

    assert existing, 'Failed to find user:{}'.format(user_name)


@mark.parametrize(('user_name', 'sudoer', 'secondary_group', 'expiry_days', 'expiry_warn_days'), [
    # param('ldap_defaul_user01', None, None, None, None),
    param('ldap_bash_user02', None, None, None, None, marks=mark.p1),
    param('ldap_bash_sudoer_user03', 'sudoer', None, None, None, marks=mark.p1),
    param('ldap_bash_sudoer_2nd_grp_user04', 'sudoer', 'secondary_group', None, None, marks=mark.p1),
    param('ldap_bash_sudoer_2nd_grp_2days_user05', 'sudoer', 'secondary_group', 2, None, marks=mark.p1),
    param('ldap_bash_sudoer_2nd_grp_2days_1day_user06', 'sudoer', 'secondary_group', 2, 1, marks=mark.p1),
])
def test_ldap_create_user(user_name, sudoer, secondary_group, expiry_days, expiry_warn_days):

    """
    Create a LDAP User with the specified name

    User Stories:   US70961

    Steps:
        1   create a LDAP User with the specified name
        2   verify the LDAP User is successfully created and get its details

    """
    sudoer = True if sudoer == 'sudoer' else False
    secondary_group = True if secondary_group == 'secondary_group' else False

    LOG.tc_step('Check if any LDAP User with name:{} existing'.format(user_name))
    existing, user_info = theLdapUserManager.find_ldap_user(user_name)
    if existing:
        LOG.warn('LDAP User:{} already existing! Delete it for testing user-creation'.format(user_name))
        code, output = theLdapUserManager.rm_ldap_user(user_name)
        if 0 != code:
            skip('LDAP User:{} already existing and failed to delete!')
        else:
            LOG.warn('Existing LDAP User:{} is successfully deleted'.format(user_name))
    else:
        LOG.warn('OK, LDAP User:{} is not existing, continue to create one'.format(user_name))

    LOG.tc_step('Creating LDAP User:{}'.format(user_name))

    code, user_settings = theLdapUserManager.create_ldap_user(
        user_name,
        sudoer=sudoer,
        secondary_group=secondary_group,
        password_expiry_days=expiry_days,
        password_expiry_warn_days=expiry_warn_days,
        check_if_existing=True,
        delete_if_existing=True)

    if 0 == code:
        LOG.info('OK, created LDAP for User:{}, user-details:\n{}'.format(user_name, user_settings))
    else:
        if 1 == code:
            msg = 'Already exists the LDAP User:{}.'.format(user_name)
        elif 2 == code:
            msg = 'Failed to find the created LDAP User:{} although creating succeeded.'.format(user_name)
        elif 3 == code:
            msg = 'Failed to create the LDAP User:{}.'.format(user_name)
        else:
            msg = 'Failed to create the LDAP User:{} for unknown reason.'.format(user_name)

        LOG.error(msg)
        assert False, msg

    LOG.info('OK, successfully created the LDAP User {}'.format(user_name))


@fixture(scope='function')
def ldap_user_for_test(request):

    user_name = 'ldapuser04'
    LOG.fixture_step('Make sure LDAP user exist:{}, create it if not exist'.format(user_name))
    created, user_info = _make_sure_user_exist(user_name, delete_if_existing=True)

    if not created:
        skip('No LDAP User:{} existing to delete'.format(user_name))
        return

    def _delete_ldap_user():
        theLdapUserManager.rm_ldap_user(user_name)
    request.addfinalizer(_delete_ldap_user)

    return user_name


def test_ldap_user_password(ldap_user_for_test):
    """

    Args:
        ldap_user_for_test:

    CGTS-6468
    Test Steps:
        create a ldapuser
        login as the ldapuser
        try to set a new simple password it should fail
        try to set a new complex password it should pass
    Teardown:
        remove ldapuser

    """
    user_name = ldap_user_for_test
    simple_password = 'test123'
    complex_password = 'Fa43sby!'

    LOG.tc_step('Get the password of the user {}'.format(user_name))
    password = theLdapUserManager.get_ldap_user_password(user_name)
    LOG.debug('The password of the user: {}'.format(password))

    # change password to simple using ssh_con verify it fail
    LOG.tc_step('Set the new simple password should fail: {}'.format(simple_password))
    rc, output = security_helper.set_ldap_user_password(user_name, simple_password, check_if_existing=False,
                                                        fail_ok=True)
    # change password to complex using ssh_con and verify it pass
    assert 'Error' in output, 'Expect to {} but see {} instead'.format('Error', output)
    LOG.info('OK, succeeded  as the LDAP User: {}, password: {}'.format(user_name, password))

    # change password to complex using ssh_con verify it fail
    LOG.tc_step('Set the new complex password should work: {}'.format(complex_password))
    rc, output = security_helper.set_ldap_user_password(user_name, complex_password, check_if_existing=False,
                                                        fail_ok=True)
    # change password to complex using ssh_con and verify it pass
    assert 'Success' in output, 'Expect to {} but see {} instead'.format('Success', output)
    LOG.info('OK, succeeded  as the LDAP User: {}, password: {}'.format(user_name, complex_password))


@mark.parametrize(('user_name', 'sudo_type'), [
    param('ldapuser06', 'sudoer', marks=mark.p1),
    param('ldapuser07', 'non-sudoer', marks=mark.p1),
])
def test_cmds_login_as_ldap_user(user_name, sudo_type):
    """
    this test cover both CGTS-4909 and CGTS-6623
    Args:
        user_name: username of the ldap user should be admin for this test
        sudo_type

    Test Steps:
        - created ldap user
        - execute sudo user command for sudoer
        - execute openstack user list command for non-sudoer

    Teardowns:
        - delete created ldap user

    """
    hostname = system_helper.get_active_controller_name()

    LOG.tc_step('Make sure LDAP user exist:{}, create it if not exist'.format(user_name))
    _make_sure_user_exist(user_name, sudoer=(sudo_type == 'sudoer'), delete_if_existing=True)

    LOG.tc_step('Get the password of the user {}'.format(user_name))
    password = theLdapUserManager.get_ldap_user_password(user_name)
    LOG.debug('The password of the user: {}'.format(password))

    LOG.tc_step('Login as the LDAP User:{}'.format(user_name))

    original_con = ControllerClient.get_active_controller()
    original_prompt = original_con.get_prompt()
    original_password = original_con.password
    logged_in, password, ssh_con = theLdapUserManager.login_as_ldap_user(user_name, password,
                                                                         host=hostname, pre_store=True,
                                                                         disconnect_after=False)

    try:
        # set password/prompt for ldap user login
        ssh_con.set_prompt(Prompt.CONTROLLER_PROMPT)
        ssh_con.password = password
        ssh_con.flush()

        LOG.tc_step("Attemt to execute sudo command 'sudo ls'")
        code, out = ssh_con.exec_sudo_cmd("ls", fail_ok=True)
        if sudo_type == 'sudoer':
            assert code == 0, "Sudoer ldap user {} failed to run sudo cmd".format(user_name)
        else:
            assert code == 1, "Non-sudoer ldap user {} is able to run sudo cmd".format(user_name)

        LOG.tc_step("Execute openstack command 'openstack user list'")
        cli.openstack('user list', ssh_client=ssh_con, auth_info=Tenant.get('admin'))

    finally:
        if logged_in:
            # reset password/prompt back to original
            ssh_con.send('exit')    # exit from user login
            ssh_con.set_prompt(original_prompt)
            ssh_con.password = original_password
            ssh_con.flush()


@mark.parametrize('user_name', [
    mark.p1('admin'),
    # param('operator', 'operator', 'controller-0'),
])
# TODO: disable for now and re-evaluate later when the features
#  regarding 'admin' user are ready
def _test_telnet_ldap_admin_access(user_name):
    """
    Args:
        user_name: username of the ldap user should be admin for thist test

    Test Steps:
        - telnet to active controller
        - login as admin password admin.
        - verify that it can ls /home/wrsroot

    Teardowns:
        - Disconnect telnet
    """

    if ProjVar.get_var('COLLECT_TELNET'):
        skip('Telnet is in use for collect log. This test which require telnet will be skipped')

    lab = ProjVar.get_var('LAB')
    nodes_info = node.create_node_dict(lab['controller_nodes'], 'controller')
    hostname = system_helper.get_active_controller_name()
    controller_node = nodes_info[hostname]
    password = "admin"
    new_password = "Li69nux*"

    telnet = TelnetClient(controller_node.telnet_ip, port=controller_node.telnet_port, hostname=hostname,
                          user=user_name, password=new_password, timeout=10)
    try:
        LOG.tc_step("Telnet to lab as {} user with password {}".format(user_name, password))
        telnet.login(expect_prompt_timeout=30, handle_init_login=True)

        code, output = telnet.exec_cmd('ls {}'.format(WRSROOT_HOME), fail_ok=False)
        LOG.info('output from test {}'.format(output))
        assert '*** forbidden' not in output, 'not able to ls to /home/wrsroot as admin user'
    finally:
        telnet.send('exit')
        telnet.close()
