import time
import re

from pytest import mark, skip

from consts.cgcs import Prompt
from keywords import html_helper, host_helper, system_helper
from utils.tis_log import LOG
from utils.ssh import SSHClient, ControllerClient

LINUX_ROOT_PASSWORD = 'Li69nux*'


def get_ldap_admin_passwd(ssh=None):
    """
    Get the LDAP Adminstrator's password

    Args:
        ssh:

    Returns (str):
        The password of the LDAP Adminstrator

    """
    if ssh is None:
        ssh = ControllerClient.get_active_controller()

    cmd = 'grep "credentials" /etc/openldap/slapd.conf.backup'
    code, output = ssh.exec_sudo_cmd(cmd)
    if 0 != code:
        LOG.error('Failed to get the LDAP Admin password, error={}, message={}'.format(code, output))
    elif not output.strip():
        LOG.error('Failed to get the LDAP Admin password, empty output!, error={}, message={}'.format(code, output))
    else:
        for line in output.strip().splitlines():
            if 'credentials' in line:
                password = line.split('=')[1]

                if password:
                    LOG.info('OK, the LDAP Admin password is:{}'.format(password))
                    return password

        LOG.error('Failed to get the LDAP Admin password, empty output!, error={}, message={}'.format(code, output))

    return ''


def find_ldap_user(user_name, ssh=None, host=None):
    """
    Find the LDAP User with the specified name

    Args:
        user_name:
        ssh:
        host:

    Returns tuple(existing_flag, user_info):
        existing_flag (boolean)     - True, existing
                                    - False, cannot find a LDAP User with the specified name
    Notes:
        sample output of ldapuserfinger -u
        dn: uid=ldapuser01,ou=People,dc=cgcs,dc=local
        objectClass: account
        objectClass: posixAccount
        objectClass: shadowAccount
        objectClass: top
        cn: ldapuser01
        uid: ldapuser01
        uidNumber: 10011
        gidNumber: 100
        shadowLastChange: 0
        homeDirectory: /home/ldapuser01
        gecos: ldapuser01
        description: User account
        userPassword:: e1NTSEF9RmJsME9tcElzRTI3OENpWTZoQWpPR2ZrSnNYMGo5cmQ=
        loginShell: /usr/local/bin/cgcs_cli
        shadowMax: 90
        shadowWarning: 2
    """


    if ssh is None:
        if host is None:
            ssh = ControllerClient.get_active_controller()
        else:
            ssh = SSHClient(host=host)

    LOG.info('Checking if LDAP User:{} is already existing'.format(user_name))

    ssh.flush()

    cmd = 'ldapfinger -u {}'.format(user_name)
    code, output = ssh.exec_sudo_cmd(cmd, fail_ok=True, strict_passwd_prompt=True)

    if not output.strip():
        LOG.info('No LDAP User:{} existing'.format(user_name))
        return False, {}
    else:
        user_info = {}
        for line in output.strip().splitlines():
            if line.startswith('dn: '):
                user_info['dn'] = line.split()[1].strip()
            elif line.startswith('cn: '):
                user_info['cn'] = line.split()[1].strip()
            elif line.startswith('uid: '):
                user_info['uid'] = line.split()[1].strip()
            elif line.startswith('uidNumber: '):
                user_info['uid_number'] = int(line.split()[1].strip())
            elif line.startswith('gidNumber: '):
                user_info['gid_number'] = int(line.split()[1].strip())
            elif line.startswith('homeDirectory: '):
                user_info['home_directory'] = line.split()[1].strip()
            elif line.startswith('userPassword:: '):
                user_info['user_password'] = line.split()[1].strip()
            elif line.startswith('loginShell: '):
                user_info['login_shell'] = line.split()[1].strip()
            elif line.startswith('shadowMax: '):
                user_info['shadow_max'] = int(line.split()[1].strip())
            elif line.startswith('shadowWarning: '):
                user_info['shadow_warning'] = int(line.split()[1].strip())
            else:
                LOG.debug('Skip line from output of {}:\n<{}>'.format(cmd, line))

        if user_info:
            LOG.info('OK, found LDAP user:{}, user_info:{}'.format(user_name, user_info))
            return True, user_info
        else:
            LOG.info('Cannot find LDAP user:{}, user_info:{}'.format(user_name, user_info))
            return False, {}


def create_ldap_user(user_name, shell=2, secondary_group=False, password_expiry_days=90, password_expiry_warn_days=2,
                     fail_on_existing=True, check_if_existing=True, ssh=None, host=None):
    """

    Args:
        user_name:
        shell:
        secondary_group:
        password_expiry_days:
        password_expiry_warn_days:
        fail_on_existing:
        check_if_existing:
        ssh:
        host:

    Returns tuple(code, user_infor):
        code (int):
            0   -- successfully created a LDAP User withe specified name and attributes
            1   -- a LDAP User already existing with the same name (don't care other attributes for now)
            -1  -- a LDAP User already existing but fail_on_existing specified
            -2  -- CLI to create a user succeeded but cannot find the user after
            -3  -- failed to create a LDAP User (the CLI failed)

    """

    if ssh is None:
        if host is None:
            ssh = ControllerClient.get_active_controller()
        else:
            ssh = SSHClient(host=host)

    if check_if_existing:
        existing, user_info = find_ldap_user(user_name, ssh=ssh, host=host)
        if existing:
            if fail_on_existing:
                LOG.error('Fail, LDAP User:{} already existing:{}, return -1'.format(user_name, user_info))
                return -1, user_info
            else:
                LOG.info('OK, LDAP User:{} already existing:{}, return 1'.format(user_name, user_info))
                return 1, user_info
        else:
            LOG.info('OK, LDAP User:{} not existing'.format(user_name))

    cmd_expected = [
        (
            'sudo ldapusersetup',
            ('Enter username to add to LDAP:', ),
            ''
        ),
        (
            '{}'.format(user_name),
            (
                'Select Login Shell option # \[2\]:.*',
                '\d+.* Bash.*',
                '\d+.* Lshell'
            ),
            ('Critical setup error: cannot add user.*', ),
        ),
        (
            '{}'.format(shell),
            ('Add .* to secondary user group\? \(yes/NO\):', ),
            (),
        ),
        (
            '{}'.format('NO' if not secondary_group else 'yes'),
            ('Enter days after which user password must be changed \[{}\]:'.format(password_expiry_days), ),
            (),
        ),
        (
            '{}'.format(password_expiry_days),
            ('Enter days before password is to expire that user is warned \[{}\]:'.format(password_expiry_warn_days), ),
            (),
        ),
        (
            '{}'.format(password_expiry_warn_days),
            (
                'Successfully modified user entry uid=m-user01,ou=People,dc=cgcs,dc=local in LDAP',
                'Updating password expiry to {} days'.format(password_expiry_warn_days),
            ),
            (),
        ),
        (
            '',
            (Prompt.CONTROLLER_PROMPT, ),
            (),
        ),
    ]

    created = True
    for cmd, outputs, errors in cmd_expected:
        LOG.debug('cmd={}\nexpected_outputs=\n{}\nerrors=\n{}'.format(cmd, outputs, errors))
        ssh.send(cmd)
        expected_outputs = list(outputs) + list(errors)

        index = ssh.expect(blob_list=expected_outputs, fail_ok=True)
        if len(outputs) <= index:
            LOG.error('Failed in ldapusersetup for user:{}, error:{}'.format(user_name, errors[index - len(outputs)]))
            LOG.debug('Failed in ldapusersetup: send={}, acutal={}, expected={}'.format(cmd, errors, outputs))
            created = False
            break
        expected_outputs[:] = []

    time.sleep(3)

    if created:
        existing, user_info = find_ldap_user(user_name, ssh=ssh, host=host)
        if existing:
            LOG.info('OK, successfully created LDAP User:{}, user-info:{}'.format(user_name, user_info))
            return 0, user_info
        else:
            LOG.error('Failed, cannot find the created LDAP User:{}, user-info:{}'.format(user_name, user_info))
            return -2, user_info

    return -3, {}


def rm_ldap_user(user_name, ssh=None, host=None):
    """
    Delete the LDAP User with the specified name

    Args:
        user_name:
        ssh:
        host:

    Returns:

    """
    if ssh is None:
        if host is None:
            ssh = ControllerClient.get_active_controller()
        else:
            ssh = SSHClient(host=host)

    cmd = 'ldapdeleteuser {}'.format(user_name)
    code, output = ssh.exec_sudo_cmd(cmd)
    if 0 != code:
        LOG.error('Failed to delete the LDAP User:{}, code={}, output={}'.format(user_name, code, output))
    else:
        LOG.debug('OK, successfully deleted the LDAP User:{}'.format(user_name))

    return (0 == code, output)



@mark.parametrize(('user_name'), [
    # mark.p1(('lock_standby_change_pswd')),
    mark.p1(('ldapuser01')),
])
def test_ldap_delete_user(user_name):
    """
    Delete the LDAP User with the specified name

    Args:
        user_name:

    Returns:

    """
    LOG.tc_step('Make sure the specified LDAP User existing:{}, create it if not'.format(user_name))
    code, user_info = create_ldap_user(user_name, check_if_existing=True, fail_on_existing=False)
    if 0 != code and 1 != code:
        skip('No LDAP User:{} existing to delete'.format(user_name))
        return

    LOG.tc_step('Delete the LDAP User:{}'.format(user_name))
    success, output = rm_ldap_user(user_name)
    assert success, 'Failed to delete the LDAP User, message={}'.format(output)


@mark.parametrize(('user_name'), [
    # mark.p1(('lock_standby_change_pswd')),
    mark.p1(('ldapuser01')),
])
def test_ldap_find_user(user_name):
    """

    Args:
        user_name:

    Returns:

    Steps:
        1   search the existing user using 'ldapfinger -u <user_name>'

    User Stories:   US70961
    """

    LOG.tc_step('Make sure the LDAP User:{} exists, create one if it is not')
    code, user_info = create_ldap_user(user_name, fail_on_existing=False, check_if_existing=True)
    if 0 != code and 1 != code:
        skip('No LDAP User:{} existing to search for'.format(user_name))
        return

    LOG.tc_step('Search for LDAP User with name:{}'.format(user_name))
    existing, user_info = find_ldap_user(user_name)

    assert existing, 'Failed to find user:{}'.format(user_name)


@mark.parametrize(('user_name'), [
    mark.p1(('ldapuser01')),
])
def test_ldap_create_user(user_name):

    """
    Create a LDAP User with the specified name

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

    User Stories:   US70961
    """

    ssh = ControllerClient.get_active_controller()

    LOG.tc_step('Check if any existing LDAP User with name:{}'.format(user_name))
    existing, user_info = find_ldap_user(user_name, ssh=ssh)
    if existing:
        LOG.warn('LDAP User:{} already existing before attempting to create one!'.format(user_name))
        deleted, output = rm_ldap_user(user_name)
        if not deleted:
            skip('LDAP User:{} already existing and failed to delete!')
    else:
        LOG.warn('OK, LDAP User:{} is not existing, continue to create one'.format(user_name))

    LOG.tc_step('Creating LDAP User:{}'.format(user_name))
    code, user_settings = create_ldap_user(user_name, ssh=ssh, check_if_existing=True, fail_on_existing=True)

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
