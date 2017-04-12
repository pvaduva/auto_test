
import time
import random
from pexpect import EOF
from consts.cgcs import Prompt
from consts.auth import Tenant, HostLinuxCreds
from utils.ssh import ControllerClient, SSHClient


class LinuxUser:
    users = {HostLinuxCreds.USER: HostLinuxCreds.PASSWORD}
    con_ssh = None

    def __init__(self, user, password, con_ssh=None):
        self.user = user
        self.password = password
        self.added = False
        self.con_ssh = con_ssh if con_ssh is not None else ControllerClient.get_active_controller()

    def add_user(self):
        self.added = True
        LinuxUser.users[self.user] = self.password
        raise NotImplementedError

    def modify_password(self):
        raise NotImplementedError

    def delete_user(self):
        raise NotImplementedError

    def login(self):
        raise NotImplementedError

    @classmethod
    def get_user_password(cls):
        raise NotImplementedError

    @classmethod
    def get_current_user_password(cls):
        if not cls.con_ssh:
            cls.con_ssh = ControllerClient.get_active_controller()
        user = cls.con_ssh.get_current_user()
        return user, cls.users[user]


class Singleton(type):
    """
    A singleton used to make sure only one instance of a class is allowed to create
    """

    __instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls.__instances:
            cls.__instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls.__instances[cls]


def get_ldap_user_manager():
    """
    Get the only instance of the LDAP User Manager

    Returns (LdapUserManager):
        the only instance of the LDAP User Manager
    """
    return LdapUserManager()


class LdapUserManager(object, metaclass=Singleton):
    """
    The LDAP User Manager

    """

    LINUX_ROOT_PASSWORD = HostLinuxCreds.PASSWORD
    KEYSTONE_USER_NAME = Tenant.ADMIN['user']
    KEYSTONE_USER_DOMAIN_NAME = 'Default'
    KEYSTONE_PASSWORD = Tenant.ADMIN['password']
    PROJECT_NAME = 'admin'
    PROJECT_DOMAIN_NAME = 'Default'

    def __init__(self, ssh_con=None):
        if ssh_con is not None:
            self.ssh_con = ssh_con
        else:
            self.ssh_con = ControllerClient.get_active_controller()

        self.users_info = {}

    def ssh_to_host(self, host=None):
        """
        Get the ssh connection to the active controller or the specified host (if it's the case)

        Args:
            host (str):     the host to ssh to, using the active controller if it's unset or None

        Returns (object):
            the ssh connection session to the active controller

        """
        if host is None:
            return self.ssh_con
        else:
            return SSHClient(host=host)

    def get_ldap_admin_password(self):
        """
        Get the LDAP Administrator's password

        Args:

        Returns (str):
            The password of the LDAP Administrator

        """
        cmd = 'grep "credentials" /etc/openldap/slapd.conf.backup'
        self.ssh_con.flush()
        code, output = self.ssh_con.exec_sudo_cmd(cmd)

        if 0 == code and output.strip():
            for line in output.strip().splitlines():
                if 'credentials' in line and '=' in line:
                    password = line.split('=')[1]
                    return password

        return ''

    def get_ldap_user_password(self, user_name):
        """
        Get the password of the LDAP User

        Args:
            user_name (str):
                    the user name

        Returns (str):
            the password of the user
        """
        if user_name in self.users_info and self.users_info[user_name]['passwords']:
            return self.users_info[user_name]['passwords'][-1]

        return None

    def login_as_ldap_user_first_time(self, user_name, new_password=None, host=None):
        """
        Login with the specified LDAP User for the first time,
            during which change the initial password as a required step.

        Args:
            user_name (str):        user name of the LDAP user
            new_password (str):     password of the LDAP user
            host (str):             host name to which the user will login

        Returns (tuple):
            results (bool):         True if success, otherwise False
            password (str):         new password of the LDAP user

        """

        hostname_ip = 'controller-1' if host is None else host

        if new_password is not None:
            password = new_password
        else:
            password = 'new_{}_Li69nux!'.format(''.join(random.sample(user_name, len(user_name))))

        cmd_expected = [
            (
                'ssh -l {} -o UserKnownHostsFile=/dev/null {}'.format(user_name, hostname_ip),
                ('Are you sure you want to continue connecting (yes/no)?',),
                'Failed to get "continue connecting" prompt'
            ),
            (
                'yes',
                # ("{}@{}'s password:".format(user_name, hostname_ip),),
                (".*@.*'s password: ".format(hostname_ip),),
                'Failed to get password prompt'
            ),
            (
                '{}'.format(user_name),
                ('\(current\) LDAP Password: ',),
                'Failed to get password prompt for current password'
            ),
            (
                '{}'.format(user_name),
                ('New password: ',),
                'Failed to get password prompt for new password'
            ),
            (
                '{}'.format(password),
                ('Retype new password: ',),
                'Failed to get confirmation password prompt for new password'
            ),
            (
                '{}'.format(password),
                (
                    'passwd: all authentication tokens updated successfully.',
                    'Connection to controller-1 closed.',
                ),
                'Failed to change to new password for current user:{}'.format(user_name)
            ),
            (
                '',
                (Prompt.CONTROLLER_PROMPT,),
                'Failed in last step of first-time login as LDAP User:{}'.format(user_name)
            ),
        ]

        result = True
        self.ssh_con.flush()
        for cmd, expected, error in cmd_expected:
            self.ssh_con.send(cmd)
            index = self.ssh_con.expect(blob_list=list(expected))
            if len(expected) <= index:
                result = False
                break

        self.ssh_con.flush()

        return result, password

    def find_ldap_user(self, user_name):
        """
        Find the LDAP User with the specified name

        Args:
            user_name (str):            - user name of the LDAP User to search for

        Returns:
            existing_flag (boolean)     - True, the LDAP User with the specified name existing
                                        - False, cannot find a LDAP User with the specified name

            user_info (dict):           - user information
        """

        cmd = 'ldapfinger -u {}'.format(user_name)
        self.ssh_con.flush()
        code, output = self.ssh_con.exec_sudo_cmd(cmd, fail_ok=True, strict_passwd_prompt=True)

        found = False
        user_info = {}
        if output.strip():
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
                    pass
            else:
                found = True

        return found, user_info

    def rm_ldap_user(self, user_name):
        """
        Delete the LDAP User with the specified name

        Args:
            user_name:

        Returns (tuple):
            code   -   0    successfully deleted the specified LDAP User
                        otherwise: failed
            output  -   message from the deleting CLI
        """

        cmd = 'ldapdeleteuser {}'.format(user_name)

        self.ssh_con.flush()
        code, output = self.ssh_con.exec_sudo_cmd(cmd, fail_ok=True)

        if 0 == code and user_name in self.users_info:
            del self.users_info[user_name]

        return code, output

    @staticmethod
    def validate_user_settings(shell=2,
                               sudoer=False,
                               secondary_group=False,
                               secondary_group_name=None,
                               password_expiry_days=90,
                               password_expiry_warn_days=2
                               ):
        """
        Validate the settings to be used as attributes of a LDAP User

        Args:
            shell (int):
                1   -   Bash
                2   -   LShell (limited shell)

            sudoer (boo)
                True    -   Add the user to sudoer list
                False   -   Do not add the user to sudoer list

            secondary_group (bool):
                True    -   Secondary group to add user to
                False   -   No secondary group

            secondary_group_name (str):     Name of secondary group (will be ignored if secondary_group is False

            password_expiry_days (int):

            password_expiry_warn_days (int):

        Returns:

        """

        try:
            opt_shell = int(shell)
            opt_expiry_days = int(password_expiry_days)
            opt_expiry_warn_days = int(password_expiry_warn_days)
            bool(secondary_group)
            str(secondary_group_name)
        except ValueError:
            return -1, 'invalid input: {}, {}, {}'.format(shell, password_expiry_days, password_expiry_warn_days)

        if opt_shell not in [1, 2]:
            return -2, 'input error: unknown SHELL:{}, only 1) Bash 2) LShell are supported'.format(shell)

        if sudoer and 1 != opt_shell:
            return -3, 'input error: sudoer only supported when 1) Bash is selected'

        if opt_expiry_days <= 0:
            return -4, 'invalid password expiry days:{}'.format(opt_expiry_days)

        if opt_expiry_warn_days <= 0:
            return -5, 'invalid password expiry days:{}'.format(opt_expiry_warn_days)

        return 0, ''

    def create_ldap_user(self,
                         user_name,
                         shell=2,
                         sudoer=False,
                         secondary_group=False,
                         secondary_group_name=None,
                         password_expiry_days=90,
                         password_expiry_warn_days=2,
                         delete_if_existing=True,
                         check_if_existing=True):
        """

        Args:
            user_name (str):        user name of the LDAP User

            shell (int):
                1   -   Bash
                2   -   LShell (limited shell)

            sudoer (boo)
                True    -   Add the user to sudoer list
                False   -   Do not add the user to sudoer list

            secondary_group (bool):
                True    -   Secondary group to add user to
                False   -   No secondary group

            secondary_group_name (str):     Name of secondary group (will be ignored if secondary_group is False

            password_expiry_days (int):

            password_expiry_warn_days (int):

            delete_if_existing (bool):
                True    -   Delete the user if it is already existing
                False   -   Return the existing LDAP User

            check_if_existing (bool):
                True    -   Check if the LDAP User existing with the specified name
                False   -   Do not check if any LDAP Users with the specified name existing

        Returns tuple(code, user_infor):
            code (int):
                0   -- successfully created a LDAP User withe specified name and attributes
                1   -- a LDAP User already existing with the same name (don't care other attributes for now)
                -1  -- a LDAP User already existing but fail_on_existing specified
                -2  -- CLI to create a user succeeded but cannot find the user after
                -3  -- failed to create a LDAP User (the CLI failed)
                -4  -- failed to change the initial password and login the first time
                -5  -- invalid inputs
        """
        shell = 2 if shell is None else shell
        password_expiry_days = 90 if password_expiry_days is None else password_expiry_days
        password_expiry_warn_days = 2 if password_expiry_warn_days is None else password_expiry_warn_days
        secondary_group = False if secondary_group is None else secondary_group
        secondary_group_name = '' if secondary_group_name is None else secondary_group_name

        code, message = self.validate_user_settings(shell=shell, sudoer=sudoer, secondary_group=secondary_group,
                                                    secondary_group_name=secondary_group_name,
                                                    password_expiry_days=password_expiry_days,
                                                    password_expiry_warn_days=password_expiry_warn_days)
        if 0 != code:
            return -5, {}

        if check_if_existing:
            existing, user_info = self.find_ldap_user(user_name)
            if existing:
                if delete_if_existing:
                    code, message = self.rm_ldap_user(user_name)
                    if 0 != code:
                        return -1, user_info
                else:
                    return 1, user_info
        cmds_expectings = [
            (
                'sudo ldapusersetup',
                ('Enter username to add to LDAP:',),
                ''
            ),
            (
                '{}'.format(user_name),
                (
                    'Select Login Shell option # \[2\]:.*',
                    '\d+.* Bash.*',
                    '\d+.* Lshell'
                ),
                ('Critical setup error: cannot add user.*',),
            ),
        ]
        if 1 == shell:
            cmds_expectings += [
                (
                    '1',
                    ('Add {} to sudoer list? (yes/NO): '.format(user_name), ),
                    ()
                ),
                (
                    'yes' if sudoer else 'NO',
                    ('Add .* to secondary user group\? \(yes/NO\):', ),
                    ()
                ),
            ]
        elif 2 == shell:
            cmds_expectings += [
                (
                    '2',
                    ('Add .* to secondary user group\? \(yes/NO\):', ),
                    ()
                )
            ]
        # else:
        #     # fatal error: unknow shell
        #     return -5, {}

        if secondary_group:
            cmds_expectings += [
                (
                    'yes',
                    ('Secondary group to add user to? [wrs_protected]: ',),
                    ()
                ),
                (
                    '{}'.format(secondary_group_name),
                    ('Enter days after which user password must be changed \[{}\]:'.format(password_expiry_days),),
                    ()
                )

            ]
        else:
            cmds_expectings += [
                (
                    'NO',
                    ('Enter days after which user password must be changed \[{}\]:'.format(password_expiry_days), ),
                    (),
                ),
            ]

        cmds_expectings += [
            (
                '{}'.format(password_expiry_days),
                ('Enter days before password is to expire that user is warned \[{}\]:'.format(
                    password_expiry_warn_days), ),
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
        self.ssh_con.flush()
        for cmd, outputs, errors in cmds_expectings:
            self.ssh_con.send(cmd)
            expected_outputs = list(outputs) + list(errors)

            index = self.ssh_con.expect(blob_list=expected_outputs, fail_ok=True)
            if len(outputs) <= index:
                created = False
                break
            expected_outputs[:] = []

        time.sleep(3)

        user_info = {}
        if created:
            existing, user_info = self.find_ldap_user(user_name)
            if existing:
                success, password = self.login_as_ldap_user_first_time(user_name)
                if not success:
                    code = -4
                else:
                    user_info['passwords'] = [password]
                    self.users_info[user_name] = user_info
                    code = 0
            else:
                code = - 2
        else:
            code = -3

        return code, user_info

    def login_as_ldap_user(self, user_name, password, host=None, pre_store=False, disconnect_after=False):
        """
        Login as the specified user name and password onto the specified host

        Args:
            user_name (str):        user name
            password (str):         password
            host (str):             host to login to
            pre_store (bool):
                    True    -       pre-store keystone user credentials for session
                    False   -       chose 'N' (by default) meaning do not pre-store keystone user credentials
            disconnect_after (bool):
                    True    -       disconnect the logged in session
                    False   -       keep the logged in session

        Returns (tuple):
            logged_in (bool)    -   True if seccessfully logged into the specified host
                                    using the specified user/password
            password (str)      -   the password used to login
            ssh_con (object)    -   the ssh session logged in
        """

        hostname_ip = 'controller-1' if host is None else host

        prompt_keystone_user_name = 'Enter Keystone username \[{}\]: '.format(user_name)
        cmd_expected = (
            (
                'ssh -l {} -o UserKnownHostsFile=/dev/null {}'.format(user_name, hostname_ip),
                ('Are you sure you want to continue connecting \(yes/no\)\?',),
                ('ssh: Could not resolve hostname {}: Name or service not known'.format(hostname_ip),),
            ),
            (
                'yes',
                ('{}@{}\'s password: '.format(user_name, hostname_ip),),
                (),
            ),
            (
                '{}'.format(password),
                ('Pre-store Keystone user credentials for this session\? \(y/N\): ',),
                ('Permission denied, please try again\.',),
            ),
            (
                '{}'.format('y' if pre_store else 'N'),
                (
                    prompt_keystone_user_name,
                    Prompt.CONTROLLER_PROMPT,
                ),
                (),
            ),
            (
                '{}'.format(self.KEYSTONE_USER_NAME),
                ('Enter Keystone user domain name: ',),
                (),
            ),
            (
                '{}'.format(self.KEYSTONE_USER_DOMAIN_NAME),
                ('Enter Project name: ',),
                (),
            ),
            (
                '{}'.format(self.PROJECT_NAME),
                ('Enter Project domain name: ',),
                (),
            ),
            (
                '{}'.format(self.PROJECT_DOMAIN_NAME),
                ('Enter Keystone password:',),
                (),
            ),
            (
                '{}'.format(password),
                ('Keystone credentials preloaded\!.*\[{}@{} \({}\)\]\$'.format(
                    user_name, hostname_ip, self.KEYSTONE_USER_NAME),),
                (),
            ),
        )

        logged_in = False
        self.ssh_con.flush()
        for i in range(len(cmd_expected)):
            cmd, expected, errors = cmd_expected[i]
            self.ssh_con.send(cmd)

            index = self.ssh_con.expect(blob_list=list(expected) + list(errors))
            if len(expected) <= index:
                break
            elif 3 == i:
                if expected[index] == prompt_keystone_user_name:
                    assert pre_store, \
                        'pre_store is False, while selecting "y" to "Pre-store Keystone user credentials ' \
                        'for this session!"'
                else:
                    logged_in = True
                    break
        else:
            logged_in = True

        if logged_in:
            if disconnect_after:
                self.ssh_con.send('exit')

        return logged_in, password, self.ssh_con

    def change_ldap_user_password(self, user_name, password, new_password, change_own_password=True,
                                  check_if_existing=True, host=None, disconnect_after=False):
        """
        Modify the password of the specified user to the new one

        Args:
            user_name (str):
                -   name of the LDAP User

            password (str):
                -   password of the LDAP User

            new_password (str):
                -   new password to change to

            check_if_existing (bool):
                -   True:   check if the user already existing first
                    False:  change the password without checking the existence of the user

            host (str):
                -   The host to log into

            disconnect_after (bool)
                -   True:   disconnect the ssh connection after changing the password
                -   False:  keep the ssh connection

        Returns (bool):
                True if successful, False otherwise
        """

        if check_if_existing:
            found, user_info = self.find_ldap_user(user_name)
            if not found:
                return False

        if not change_own_password:
            return False

        logged_in, password, ssh_con = self.login_as_ldap_user(user_name,
                                                               password=password, host=host, disconnect_after=False)

        if not logged_in or not password or not ssh_con:
            return False, ssh_con

        cmds_expected = (
            (
                'passwd',
                ('\(current\) LDAP Password: ',),
                (),
            ),
            (
                password,
                ('New password: ',),
                ('passwd: Authentication token manipulation error', EOF,),
            ),
            (
                new_password,
                ('Retype new password: ',),
                (
                    'BAD PASSWORD: The password is too similar to the old one',
                    'BAD PASSWORD: No password supplied',
                    'passwd: Have exhausted maximum number of retries for service',
                    EOF,
                ),
            ),
            (
                new_password,
                ('passwd: all authentication tokens updated successfully.',),
                (),
            ),
        )

        changed = True
        ssh_con.flush()
        for cmd, expected, errors in cmds_expected:
            ssh_con.send(cmd)
            index = ssh_con.expect(blob_list=list(expected) + list(errors))
            if len(expected) <= index:
                changed = False
                break

        if disconnect_after:
            ssh_con.send('exit')

        return changed, ssh_con
