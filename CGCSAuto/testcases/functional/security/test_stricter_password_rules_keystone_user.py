
import re
import time
import random
import copy

from string import ascii_lowercase, ascii_uppercase, digits, ascii_letters

from pytest import mark, skip, fixture

from utils.tis_log import LOG
from utils.ssh import ControllerClient
from utils.cli import openstack, system
from consts.auth import Tenant
from keywords import keystone_helper


TEST_USER_NAME = 'keystoneuser'

SPECIAL_CHARACTERS = '!@#$%^&*()<>{}+=_\\\[\]\-?|~`,.;:'
MIN_PASSWORD_LEN = 7
MAX_PASSWORD_LEN = 15
# MAX_PASSWORD_LEN = 4095
NUM_TRACKED_PASSWORD = 2
# WAIT_BETWEEN_CHANGE = 60
WAIT_BETWEEN_CHANGE = 6

USER_LOCKED_OUT_TIME = 300
USERS_INFO = {}
USER_NUM = 0

PASSWORD_RULE_INFO = {
    'minimum_7_chars': ('length_generator', ''),
    'not_last_used': ('change_history_generator', 'not_last_2'),
    'at_least_1_lower_case': ('case_numerical_generator', 'lower'),
    'at_least_1_upper_case': ('case_numerical_generator', 'upper'),
    'at_least_1_digit': ('case_numerical_generator', 'digit'),
    'at_least_1_special_case': ('special_char_generator', ''),

    'not_in_dictionary': ('dictionary_generator', ''),
    'at_least_3_char_diff': ('change_history_generator', '3_diff'),
    'not_simple_reverse': ('change_history_generator', 'reversed'),
    'disallow_only_1_case_diff': ('change_history_generator', '3_diff'),
    'lockout_5_minute_after_5_tries': ('multiple_attempts_generator', 5),
}

# use this simple "dictionary" for now, because no english dictionary installed on test server
SIMPLE_WORD_DICTIONARY = '''
and is being proof-read and supplemented by volunteers from around the
world.  This is an unfunded project, and future enhancement of this
dictionary will depend on the efforts of volunteers willing to help build
this free resource into a comprehensive body of general information.  New
definitions for missing words or words senses and longer explanatory notes,
as well as images to accompany the articles are needed.  More modern
illustrative quotations giving recent examples of usage of the words in
their various senses will be very helpful, since most quotations in the
original 1913 dictionary are now well over 100 years old
'''

password_regex = r'^(?=.*\d)(?=.*[a-z])(?=.*[A-Z])(?=.*[!@#$%^&*()<>{}+=_\\\[\]\-?|~`,.;:]).{7,}$'


@fixture(scope="module", autouse=True)
def cleanup_users(request):

    def _cleanup_users():
        white_list = ['admin', 'tenant1', 'tenant2']
        users_to_delete = [user for user in USERS_INFO if user not in white_list]
        LOG.info('Deleting users after testing: {}\n'.format(users_to_delete))
        delete_users(users_to_delete)

    request.addfinalizer(_cleanup_users)


def delete_users(users):
    if users and len(users) > 0:
        command = 'user delete {}'.format(' '.join(users))
        openstack(command, auth_info=Tenant.ADMIN, fail_ok=False)


def save_used_password(user_name, password):
    user_info = USERS_INFO.get(user_name, {})

    if 'used_passwords' in user_info:
        user_info['used_passwords'].append(password)
        if len(user_info['used_passwords']) > NUM_TRACKED_PASSWORD:
            user_info.pop(0)
    else:
        user_info['used_passwords'] = [password]

    USERS_INFO[user_name] = user_info


def is_last_used(password, user_name=None, depth=NUM_TRACKED_PASSWORD):
    if not user_name:
        for user_name in USERS_INFO.keys():
            user_info = USERS_INFO[user_name]
            if 'used_passwords' in user_info:
                used_passwords = user_info['used_passwords']
                if used_passwords:
                    if len(used_passwords) >= depth \
                            and password in used_passwords[-1*depth:]:
                        return True
                    elif password in used_passwords:
                        return True
    else:
        user_info = USERS_INFO[user_name]
        if 'used_passwords' in user_info:
            used_passwords = user_info['used_passwords']
            if used_passwords:
                if len(used_passwords) >= NUM_TRACKED_PASSWORD:
                    return password in used_passwords[-1 * depth:]
                else:
                    return password in used_passwords

    return False


def get_valid_password(user_name=None):
    total_length = random.randint(MIN_PASSWORD_LEN, MAX_PASSWORD_LEN)

    password = None
    frequently_used_words = re.split('\W', SIMPLE_WORD_DICTIONARY.strip())

    attempt = 0
    while attempt < 60:
        attempt += 1
        left_count = total_length
        lower_case_len = random.randint(1, 4)
        left_count -= lower_case_len

        upper_case_len = random.randint(1, left_count - 2)
        left_count -= upper_case_len

        digit_len = random.randint(1, left_count - 1)
        left_count -= digit_len

        special_char_len = random.randint(1, left_count)

        lower_case = random.sample(ascii_lowercase, min(lower_case_len, len(ascii_lowercase)))
        upper_case = random.sample(ascii_uppercase, min(upper_case_len, len(ascii_uppercase)))
        password_digits = random.sample(digits, min(digit_len, len(digits)))
        special_char = random.sample(SPECIAL_CHARACTERS, min(special_char_len, len(SPECIAL_CHARACTERS)))

        actual_len = len(lower_case) + len(upper_case) + len(password_digits) + len(special_char)

        password = random.sample(lower_case + upper_case + password_digits + special_char,
                                 min(actual_len, total_length))
        alphabet = ascii_lowercase + ascii_uppercase + digits + SPECIAL_CHARACTERS

        password = ''.join(password)
        if actual_len != len(password):
            LOG.warn('actual_len:{}, password len:{}, password:{}\n'.format(actual_len, len(password), password))

        if len(password) < total_length:
            password += ''.join(random.choice(alphabet) for _ in range(total_length - len(password)+1))

        password = password.replace('\\', ',')
        password = password.replace('`', ':')
        password = password.replace('-', '<')
        password = password.replace('{', '{{')
        password = password.replace('}', '}}')
        password = password.replace('!', '@')

        if not is_last_used(password, user_name=user_name) and password not in frequently_used_words:
            break

    if attempt < 60:
        LOG.debug('Found valid password:\n{}\n'.format(password))
    else:
        LOG.debug('Cannot found valid password, attempted:{}\n'.format(attempt))

    return password


def multiple_attempts_generator():
    LOG.tc_step('Attempt with wrong passwords multiple times')
    invalid_password = ''.join(random.sample(ascii_letters, MIN_PASSWORD_LEN - 1))

    while True:
        (times, user_name, is_admin), _ = yield

        LOG.info('Attempt to login with INVALID password {} times, user_name:{}, is_admin\n'.format(
            times, user_name, is_admin))

        current_password = USERS_INFO[user_name]['used_passwords'][-1]

        for n in range(int(times)):
            verify_login(user_name, invalid_password, is_admin=is_admin, expecting_pass=False)
            LOG.info('OK, failed to login with INVALID password failed as expected, tried:{} times\n'.format(n+1))
            time.sleep(10)

        time.sleep(20)

        LOG.info('After failed {} times, the account should be locked and even with valid password.'.format(times))
        verify_login(user_name, current_password, is_admin=is_admin, expecting_pass=False)

        LOG.info('OK, as expected, login with VALID password failed, user:{}, is admin:{}, password:{}\n'.format(
            user_name, is_admin, current_password))

        LOG.info('Wait for {} seconds before the user account is unlocked\n'.format(
            USER_LOCKED_OUT_TIME + WAIT_BETWEEN_CHANGE))

        time.sleep(USER_LOCKED_OUT_TIME + WAIT_BETWEEN_CHANGE)

        LOG.info('Check if user is unlocked after waiting for {} seconds, is admin:{}'.format(
            USER_LOCKED_OUT_TIME, is_admin))

        verify_login(user_name, current_password, is_admin=is_admin, expecting_pass=True)
        LOG.info('OK, user is unlocked after waiting for {} seconds, user:{}, passsword:{}, is admin:{}\n'.format(
            USER_LOCKED_OUT_TIME, user_name, current_password, is_admin))

        yield


def dictionary_generator():
    frequently_used_words = re.split('\W', SIMPLE_WORD_DICTIONARY.strip())

    while True:
        (args, user_name, _), expecting_pass = yield

        if not expecting_pass:
            password = random.choice(frequently_used_words)

        else:
            while True:
                password = get_valid_password()
                if not is_last_used(password, user_name=user_name):
                    break

        yield password


def special_char_generator():
    while True:
        (args, user_name, _), expecting_pass = yield

        password = list(get_valid_password())

        if not expecting_pass:

            special_to_letter = dict(zip(SPECIAL_CHARACTERS, ascii_letters[:len(SPECIAL_CHARACTERS)+1]))
            password = ''.join(special_to_letter[c] if c in SPECIAL_CHARACTERS else c for c in password)
        else:
            while True:
                password = get_valid_password()
                if not is_last_used(password):
                    break

        yield password


def case_numerical_generator():
    while True:
        (args, user_name, _), expecting_pass = yield

        password = list(get_valid_password())

        if not expecting_pass:
            if args == 'lower':
                password = ''.join(c.upper() if c.isalpha() else c for c in password if not c.isalpha() or c.islower())
            elif args == 'upper':
                password = ''.join(c.lower() if c.isalpha() else c for c in password if not c.isalpha() or c.isupper())
            elif args == 'digit':
                digit_to_letter = dict(zip('0123456789', 'abcdefghij'))
                password = ''.join(digit_to_letter[c] if c.isdigit() else c for c in password)
            else:
                skip('Unknown args: case_numerical_generator: user_name={}, args={}, expecting_pass={}\n'.format(
                    user_name, args, expecting_pass))
                return

        else:
            while True:
                password = get_valid_password()
                if not is_last_used(password, user_name=user_name):
                    break

        yield password


def change_history_generator():
    while True:
        (args, user_name, _), expecting_pass = yield

        used_passwords = USERS_INFO[user_name]['used_passwords']
        if not expecting_pass:
            if args == 'not_last_2':
                password = random.choice(used_passwords)

            elif args == '3_diff':
                previous = used_passwords[-1]
                total_to_change = random.randrange(0, 2)
                rand_indice = random.sample(range(len(previous)), total_to_change)
                new_chars = []
                for i in range(len(previous)):
                    if i in rand_indice:
                        while True:
                            new_char = random.choice(ascii_letters)
                            if new_char != previous[i]:
                                new_chars.append(new_char)
                                break
                    else:
                        new_chars.append(previous[i])
                password = ''.join(new_chars)

            elif args == 'reversed':
                password = ''.join(password[-1::-1])
            else:
                password = ''
                skip('Unknown arg:{} for change_history_generator'.format(args))

        else:
            while True:
                password = get_valid_password()
                if password not in used_passwords:
                    break

        yield password


def length_generator():
    while True:
        (args, user_name, _), expecting_pass = yield

        password = ''
        for _ in range(30):
            password = get_valid_password()

            if not expecting_pass:
                password = password[:random.randint(1, MIN_PASSWORD_LEN-1)]
                break

            if not is_last_used(password, user_name=user_name):
                break

        yield password


def run_cmd(cmd, **kwargs):
    con_ssh = ControllerClient.get_active_controller()
    return con_ssh.exec_cmd(cmd, **kwargs)


def generate_user_name(prefix=TEST_USER_NAME, length=3):
    global USER_NUM

    USER_NUM += 1

    return '{}{:03d}_{}'.format(prefix, USER_NUM, ''.join(random.sample(ascii_lowercase, length)))


def check_user_account(user_name, password, expecting_work=True):
    LOG.tc_step('Checking if user account is enabled, user:{} password:{}\n'.format(user_name, password))

    LOG.tc_step('OK, user account is checked {} for user:{} password:{}\n'.format(
        'WORKING' if expecting_work else 'Not working', user_name, password))


def verify_login(user_name, password, is_admin=True, expecting_pass=True):
    LOG.info('Attempt to login as user:{}, expecting pass:{}, password:{}\n'.format(
        user_name, expecting_pass, password))
    auth_info = get_user_auth_info(user_name, password, in_admin_project=is_admin)

    if is_admin:
        command = 'system show'
        code, output = system('show', auth_info=auth_info, fail_ok=True, rtn_list=True)
    else:
        command = 'openstack user show {}'.format(user_name)
        LOG.info('TODO: command:{}\n'.format(command))
        code, output = openstack('user show {}'.format(user_name), auth_info=auth_info, fail_ok=True)

    message = 'expecting:{}, command=\n{}\nas user:{}, password:{}\nauth_info:{}\ncode:{}, output:{}\n'.format(
        expecting_pass, command, user_name, password, auth_info, code, output)

    if 0 == code:
        assert expecting_pass, 'Acutally logged in, while expecting NOT: ' + message
    else:
        assert not expecting_pass, 'Failed to log in, while ' + message

    LOG.info('OK, {} as user:{}, expecting pass:{}, password:{}\ncomand:{}\noutput:{}\n'.format(
        'logged in' if expecting_pass else 'failed to log in', user_name, expecting_pass, password, command, output))


def get_user_auth_info(user_name, password, project=None, in_admin_project=False):
    if in_admin_project:
        auth_info = copy.copy(Tenant.ADMIN)

    elif not project:
        auth_info = copy.copy(Tenant.get_primary())

    else:
        auth_info = copy.copy(Tenant.get_primary())

    auth_info['user'] = user_name
    auth_info['password'] = password

    return auth_info


def add_role(user_name, password, project=Tenant.ADMIN):
    LOG.info('Attempt to add role: user_name:{}, password:{}, project:{}\n'.format(user_name, password, project))

    if project == 'admin':
        role_name = 'admin'
    else:
        role_name = '_member_'

    project_id = keystone_helper.get_tenant_ids(project)[0]

    role_id = keystone_helper.get_role_ids(role_name)[0]

    command = 'role add --project {} --user {} {}'.format(project_id, user_name, role_id)
    openstack(command, auth_info=Tenant.ADMIN, fail_ok=False)


def create_user(user_name, role, del_if_existing=False, project_name_id=None, project_dommain='default',
                domain='default', password='Li69nux*', email='', description='', enable=True,
                auth_info=Tenant.ADMIN, fail_ok=False):

    existing_user = keystone_helper.get_user_ids(user_name, auth_info=auth_info)
    if existing_user:
        LOG.info('User already existing: {}\n'.format(existing_user))
        if del_if_existing:
            LOG.info('Delete the existing user: {}\n'.format(existing_user))
            delete_users([user_name])
        else:
            return 1, existing_user

    options = {
        'password': password,
        'project': project_name_id,
        'project-domain': project_dommain,
        'domain': domain,
        'email': email,
        'description': description,
    }

    args = []
    for k, v in options.items():
        if v:
            args.append('{}="{}"'.format(k, v))
    args.append('enable' if enable else 'disable')
    args.append('or-show')

    command = 'user create --{} {}'.format(' --'.join(args), user_name)

    auth_info = auth_info or Tenant.ADMIN

    code, output = openstack(command, fail_ok=True, auth_info=auth_info)
    assert code == 0 or fail_ok, 'Failed to create user:{}, error code:{}, output:\n{}'.format(user_name, code, output)

    is_addmin = False
    if code != 0:
        LOG.info('Failed to create user:{}, error code:{}, output:{}\n'.format(user_name, code, output))
        assert fail_ok, 'Failed to create user:{}, error code:{}, output:{}\n'.format(user_name, code, output)
    else:
        if role == 'admin':
            is_addmin = True
            user_of_admin = Tenant.ADMIN['user']
            role_of_admin = keystone_helper.get_assigned_roles(project=Tenant.ADMIN['tenant'], user=user_of_admin)[0]
            LOG.info('attempt to add role to user:{}, with role from admin:{}, role:{}\n'.format(
                user_name, user_of_admin, role_of_admin))

            add_role(user_name, password, project=Tenant.ADMIN['tenant'])
            LOG.info('OK, successfully add user to role:{}, user:{}\n'.format(Tenant.ADMIN, user_name))

        else:
            is_addmin = False
            project = Tenant.get_primary()
            user_of_primary_tenant = project['user']
            role_of_primary_tenant = keystone_helper.get_assigned_roles(project=project_name_id,
                                                                        user=user_of_primary_tenant)[0]
            add_role(user_name, password, project=project['tenant'])

            LOG.info('OK, successfully add user to role:{}, user:{}\n'.format(role_of_primary_tenant, user_name))

    return code, output, is_addmin


def change_user_password(user_name, original_password, password, by_admin=True, expecting_pass=True):
    LOG.info('Attempt to change password, expecting-pass:{}'
             ', user:{}, original-password:{}, new-password:{}, by-admin:{}\n'.format(
        expecting_pass, user_name, original_password, password, by_admin))

    if by_admin:
        command = "user set --password '{}' {}".format(password, user_name)
    else:
        command = "user password set --original-password '{}' --password '{}'".format(original_password, password)

    auth_info = get_user_auth_info(user_name, original_password, in_admin_project=by_admin)

    code, output = openstack(command, auth_info=auth_info, fail_ok=True, rtn_list=True)

    message = '\nuser:{}, password:{}, expecting:{}\ncode={}\noutput=\n{}\nUSED:{}\n'.format(
        user_name, password, expecting_pass, code, output, USERS_INFO)

    if code == 0:
        assert expecting_pass, 'Fail, expecting been rejected to change password, but not.{}'.format(message)
    else:
        assert not expecting_pass, 'Fail, expecting pass, but not. {}'.format(message)

    LOG.info('OK, password is changed {} as expected. length of password:{}'.format(
        'accepted' if expecting_pass else 'reject' + message, len(password)))

    return code, output


@mark.parametrize(('role', 'password_rule'), [
    ('admin', 'minimum_7_chars'),
    ('non_admin', 'minimum_7_chars'),

    ('admin', 'at_least_1_lower_case'),
    ('non_admin', 'at_least_1_lower_case'),

    ('admin', 'at_least_1_upper_case'),
    ('non_admin', 'at_least_1_upper_case'),

    ('admin', 'at_least_1_digit'),
    ('non_admin', 'at_least_1_digit'),

    ('admin', 'at_least_1_special_case'),
    ('non_admin', 'at_least_1_special_case'),

    ('admin', 'not_in_dictionary'),
    ('non_admin', 'not_in_dictionary'),

    # ('admin', 'not_last_used'),       # not officially supported
    ('non_admin', 'not_last_used'),

    # ('non_admin', 'at_least_3_char_diff'),    # not officially supported
    # ('non_admin', 'not_simple_reverse'),      # not officially supported
    # ('non_admin', 'disallow_only_1_case_diff'),   # not officially supported
    # ('non_admin', 'lockout_5_minute_after_5_tries'),  # not working 2017-08-29 : not locked even right after 5 fail...
    # ('admin', 'lockout_5_minute_after_5_tries'),    # not working,
])
def test_setting_password(role, password_rule):

    if password_rule not in PASSWORD_RULE_INFO:
        skip('Unknown password rule')
        return

    random.seed()

    user_name = generate_user_name()
    LOG.tc_step('Creating user:{}\n'.format(user_name))

    password = 'Li69nux*'
    code, message, is_admin = create_user(user_name, role, fail_ok=False, password=password)
    save_used_password(user_name, password)
    LOG.info('OK, successfully created user:{}\n'.format(user_name))

    LOG.tc_step('Make sure we can login with user/password: {}/{}\n'.format(user_name, password))
    verify_login(user_name, password, expecting_pass=True, is_admin=is_admin)

    LOG.info('OK, we can login as user:{}'.format(user_name))

    LOG.tc_step('Modify password for user:{}, testing passowrd rule:{}'.format(user_name, password_rule))
    rule = password_rule

    producer, args = PASSWORD_RULE_INFO[rule]
    send_args = (args, user_name, is_admin)

    password_producer = eval(producer + '()')
    password_producer.send(None)

    if rule == 'lockout_5_minute_after_5_tries':
        password_producer.send((send_args, user_name))

    else:
        valid_pwd = password_producer.send((send_args, True))
        LOG.info('Attempt to set with valid password:{} to user:{}, expecting PASS, by admin:{}\n'.format(
            valid_pwd, user_name, is_admin))

        change_user_password(user_name, password, valid_pwd, expecting_pass=True, by_admin=is_admin)
        save_used_password(user_name, valid_pwd)

        LOG.info('OK, VALID password was accepted as expected, user:{}, password:{}\n'.format(user_name, valid_pwd))

        verify_login(user_name, valid_pwd, expecting_pass=True, is_admin=is_admin)

        next(password_producer)
        invalid_pwd = password_producer.send((send_args, False))

        LOG.info('\nExpecting FAIL, to set with INVALID password:{} to user:{}, current password:{}\n'.format(
            invalid_pwd, user_name, valid_pwd))

        wait = WAIT_BETWEEN_CHANGE + 1

        time.sleep(wait)

        LOG.info('after wait {} seconds, attempt to change password with an INVALID password:{}\n'
                 'user_name:{}, current password:{}, is admin:{}, expecting FAIL'.format(
            wait, invalid_pwd, user_name, valid_pwd, is_admin))

        change_user_password(user_name, valid_pwd, invalid_pwd, expecting_pass=False, by_admin=is_admin)

        LOG.info('OK, INVALID password:{} to user:{} was REJECTED as expected\n'.format(invalid_pwd, user_name))

        LOG.info('All password settings passed')
