import time
import re

from pytest import mark

from consts.cgcs import Prompt
from keywords import html_helper, host_helper, system_helper
from utils.tis_log import LOG
from utils.ssh import SSHClient, ControllerClient


def get_ldap_admin_passwd(ssh=None):
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
    '''
    Find the LDAP User with the specified name

    Args:
        user_name:
        ssh:
        host:

    Returns:

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
    '''
    if ssh is None:
        if host is None:
            ssh = ControllerClient.get_active_controller()
        else:
            ssh = SSHClient(host=host)

    LOG.info('Checking if LDAP User:{} is existing'.format(user_name))
    cmd = 'sudo ldapfinger -u {}'.format(user_name)
    code, output = ssh.exec_sudo_cmd(cmd, fail_ok=True)

    if 0 != code or not output.strip():
        LOG.info('No LDAP User:{} existing'.format(user_name))
        return False, {}
    else:
        user_info = {}
        for line in output.strip():
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
                pass
        if user_info:
            LOG.info('OK, found LDAP user:{}, user_info:{}'.format(user_name, user_info))
            return True, user_info
        else:
            return False, {}


def create_ldap_user(user_name, shell=2, secondary_group=False, password_expiry_days=90, password_expiry_warn_days=2,
                     fail_on_existing=True, check_if_existing=True, ssh=None, host=None):
    if ssh is None:
        if host is None:
            ssh = ControllerClient.get_active_controller()
        else:
            ssh = SSHClient(host=host)

    if check_if_existing:
        existing, user_info = find_ldap_user(user_name, ssh=ssh, host=host)
        if existing:
            if fail_on_existing:
                LOG.error('Fail, LDAP User:{} already existing:{}'.format(user_name, user_info))
                return False, user_info
            else:
                LOG.info('OK, LDAP User:{} already existing:{}'.format(user_name, user_info))
                return True, user_info
        else:
            LOG.info('OK, LDAP User:{} not existing'.format(user_name))

    cmd_expected = [
        (
            'sudo ldapusersetup',
            'Enter username to add to LDAP:',
            ''
        ),
        (
            '{}'.format(user_name),
            (
                'Select Login Shell option # [2]:.*',
                '\d+.* Bash.*',
                '\d+.* Lshell'
            ),
            ('Critical setup error: cannot add user.*', ),
        ),
        (
            '{}'.format(shell),
            ('Add m-user01 to secondary user group? (yes/NO):', ),
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
    ]

    created = True
    for cmd, outputs, errors in cmd_expected:
        ssh.send(cmd)
        expected_outputs = list(outputs) + list(errors)
        index = ssh.expect(blob_list=expected_outputs, fail_ok=True)
        if len(outputs) <= index:
            LOG.error('Failed in ldapusersetup for user:{}, error:{}'.format(user_name, errors[index - len(outputs)]))
            LOG.debug('Failed in ldapusersetup: send={}, acutal={}, expected={}'.format(cmd, errors, outputs))
            created = False
            break
        expected_outputs[:] = []

    if created:
        existing, user_info = find_ldap_user(user_name, ssh=ssh, host=host)
        if existing:
            LOG.info('OK, successfully created LDAP User:{}, user-info:{}'.format(user_name, user_info))
            return True, user_info
        else:
            LOG.error('Failed, cannot find the created LDAP User:{}, user-info:{}'.format(user_name, user_info))
            return False, user_info

    return False, {}


@mark.parametrize(('user_name'), [
    # mark.p1(('lock_standby_change_pswd')),
    mark.p1(('ldapuser01')),
])
def test_ldap_create_user(user_name):
    '''
    Create a LDAP User with the specified name
    Args:
        user_name:

    Returns:

    '''
    LOG.tc_step('Attempt to get the LDAP Admin password')
    password = get_ldap_admin_passwd()
    LOG.info('OK, got the LDAP Admin password:{}'.format(password))

    LOG.tc_step('Creating LDAP User:{}'.format(user_name))
    created, user_settings = create_ldap_user(user_name)
    if created:
        LOG.info('OK, created LDAP for User:{}, user-details:'.format(user_name, user_settings))
    else:
        assert False, 'Failed to created LDAP User:{}'.format(user_name)


@mark.p3
def _test_sudo_su():
    """
    TC5205 Test logs created by sudo su

    Test Steps:
        - Ssh to a controller and execute 'sudo su'
        - Check that logs are created by the command
        - Logout and ssh to the controller again
        - Attempt to execute 'sudo su' with an incorrect password
        - Check that there are logs created by the failed command

    """
    ip = html_helper.get_ip_addr()
    ssh = SSHClient(host=ip)
    ssh.connect()
    searching_for = ['sudo: notice  wrsroot.*PWD=/home/wrsroot ; USER=root ; COMMAND=/usr/bin/su \-',
                     'su: notice \(to root\) wrsroot on',
                     #uses su-l:session because login_as_root calls 'sudo su -'
                     'su: info pam_unix\(su-l:session\): session opened for user root by wrsroot\(uid=0\)']
    found = []

    LOG.tc_step("Logging in as su")
    with ssh.login_as_root() as root:
        code, out = root.exec_cmd('tail /var/log/auth.log')
        out = out.split('\n')
        for line in out:
            for i in range(0, len(searching_for)):
                LOG.tc_step("Searching for logs containing: {}".format(searching_for[i]))
                regex = re.compile(searching_for[i])
                if searching_for[i] not in found and re.search(regex, line):
                    found.append(searching_for[i])
                    LOG.info("Found {}".format(line))
                    break

        assert len(searching_for) == len(found), "FAIL: The sudo su command was not logged. " \
                                                 "Looking for logs resembling: {} found: {}".format(searching_for,found)

    ssh.close()

