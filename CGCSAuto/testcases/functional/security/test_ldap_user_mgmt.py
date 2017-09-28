import uuid

from pytest import mark, skip

from utils.tis_log import LOG
from keywords import security_helper


theLdapUserManager = security_helper.get_ldap_user_manager()


def _make_sure_user_exist(user_name, shell=2, secondary_group=False, password_expiry_days=90,
                          password_expiry_warn_days=2, delete_if_existing=True):
    """
    Make sure there is a LDAP User with the specified name existing, create one if not.

    Args:
        user_name (str):
                                    the user name of the LDAP User
        shell (int):
                                    1   -   bash
                                    2   -   lshell (limited shell)
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
        user_name, check_if_existing=True, delete_if_existing=delete_if_existing, shell=shell,
        secondary_group=secondary_group, password_expiry_days=password_expiry_days,
        password_expiry_warn_days=password_expiry_warn_days)

    if 0 != code and 1 != code:
        LOG.error('Failed to make sure the LDAP User {} exist'.format(user_name))
        return False, user_info

    return True, user_info


@mark.parametrize(('user_name', 'change_own_password'), [
    mark.p1(('ldapuser04', True)),
    # mark.p1(('ldapuser05', False)),
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
    LOG.tc_step('Make sure the specified LDAP User existing:{}, create it if not'.format(user_name))
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
    mark.p1(('ldapuser04', False)),
    mark.p1(('ldapuser05', True)),
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

    LOG.tc_step('Make sure the specified LDAP User existing:{}, create it if not'.format(user_name))
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


@mark.parametrize(('user_name', ), [
    mark.p1(('ldapuser04', )),
])
def test_ldap_delete_user(user_name):
    """
    Delete the LDAP User with the specified name

    User Stories:   US70961

    Args:
        user_name (str):    User name

    Returns:

    Steps:
        1   Create a LDAP User with the specified name (using the existing one if there's any)
        2   Delete the LDAP User
    """
    LOG.tc_step('Make sure the specified LDAP User existing:{}, create it if not'.format(user_name))
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
    mark.p1(('ldapuser01', )),
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


@mark.parametrize(('user_name', 'shell', 'sudoer', 'secondary_group', 'expiry_days', 'expiry_warn_days'), [
    mark.p1(('ldap_defaul_user01', None, None, None, None, None)),
    mark.p1(('ldap_bash_user02', 1, None, None, None, None)),
    mark.p1(('ldap_bash_sudoer_user03', 1, True, None, None, None)),
    mark.p1(('ldap_bash_sudoer_2nd_grp_user04', 1, True, True, None, None)),
    mark.p1(('ldap_bash_sudoer_2nd_grp_2days_user05', 1, True, True, 2, None)),
    mark.p1(('ldap_bash_sudoer_2nd_grp_2days_1day_user06', 1, True, True, 2, 1)),
])
def test_ldap_create_user(user_name, shell, sudoer, secondary_group, expiry_days, expiry_warn_days):

    """
    Create a LDAP User with the specified name

    User Stories:   US70961

    Args:
        user_name:

    Returns:

    Steps:
        1   create a LDAP User with the specified name
        2   verify the LDAP User is successfully created and get its details

    Teardown:

            0   -- successfully created a LDAP User withe specified name and attributes
            1   -- a LDAP User already existing with the same name (don't care other attributes for now)
            -1  -- a LDAP User already existing but fail_on_existing specified
            -2  -- CLI to create a user succeeded but cannot find the user after
            -3  -- failed to create a LDAP User (the CLI failed)

    """

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
        shell=shell,
        sudoer=sudoer,
        secondary_group=secondary_group,
        # secondary_group_name='',
        password_expiry_days=expiry_days,
        password_expiry_warn_days=expiry_warn_days,
        check_if_existing=True,
        delete_if_existing=True)

    if 0 == code:
        LOG.info('OK, created LDAP for User:{}, user-details:\n{}'.format(user_name, user_settings))
    else:
        if -1 == code:
            msg = 'Already exists the LDAP User:{}.'.format(user_name)
        elif -2 == code:
            msg = 'Failed to find the created LDAP User:{} although creating succeeded.'.format(user_name)
        elif -3 == code:
            msg = 'Failed to create the LDAP User:{}.'.format(user_name)
        else:
            msg = 'Failed to create the LDAP User:{} for unknown reason.'.format(user_name)

        LOG.error(msg)
        assert False, msg

    LOG.info('OK, successfully created the LDAP User {}'.format(user_name))
