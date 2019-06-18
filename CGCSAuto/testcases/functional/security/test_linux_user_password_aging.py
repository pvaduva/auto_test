import random
import time
from collections import defaultdict, deque

from pexpect import pxssh, spawn, TIMEOUT
from pytest import fixture, mark, skip

from consts.auth import HostLinuxCreds
from consts.stx import HostAvailState, Prompt
from keywords import security_helper, host_helper, system_helper
from utils import lab_info
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG

theLdapUserManager = security_helper.get_ldap_user_manager()

_host_users = defaultdict(list)

ALARM_ID_OUTOF_CONFIG = '250.001'
MAX_WAIT_FOR_ALARM = 600
MAX_FAILED_LOGINS = 5
MAX_NUM_PASSWORDS_TRACKED = 5
PASSWORD_LEGNTH = 13
TARGET_PASSWORD = 'Li69nux*'
SSH_OPTS = {
    'RSAAuthentication': 'no',
    'PubkeyAuthentication': 'no',
    'UserKnownHostsFile': '/dev/null',
    # 'StrictHostKeyChecking': 'no',
    'NoHostAuthenticationForLocalhost': 'yes',
    }


def change_password(connect, password, new_password, expecting_fail=False):
    LOG.info('change_password: current:{}, new_password:{}'.format(password, new_password))

    cmd_expects = (
        ('passwd', (r'\(current\) UNIX password:',), ()),
        ('current-password', (r'New password:',), ()),
        ('new-password', (r'Retype new password:',), ()),
        ('retype-new-password', (r'passwd: all authentication tokens updated successfully.',), ()),
    )

    exclude_lsit = [password]

    for cmd, normal_outputs, errror_outputs in cmd_expects:
        LOG.info('cmd:{}, normal_outputs:{}, error_outputs:{}\n'.format(cmd, normal_outputs, errror_outputs))

        send_cmd = cmd
        if cmd == 'current-password':
            send_cmd = password
        else:
            if cmd == 'new-password':
                exclude_lsit.append(new_password)
                send_cmd = new_password
            elif cmd == 'retype-new-password':
                send_cmd = new_password

        LOG.info('sending cmd:{} for {}\n'.format(send_cmd, cmd))

        connect.sendline(send_cmd)
        all_outputs = list(normal_outputs + errror_outputs)

        index = connect.expect(all_outputs)
        LOG.info('returned:{}, {}\n'.format(index, all_outputs[index]))
        if index >= len(normal_outputs):
            LOG.info('failed at cmd:{} for {}\n'.format(send_cmd, cmd))
            break

    else:
        LOG.info('OK, password changed to {}'.format(new_password))
        LOG.info('Wait for 180 seconds'.format())
        time.sleep(180)

        return True

    assert expecting_fail, 'Failed to change password to:{} from:{}'.format(new_password, password)

    LOG.info('Failed to change password to {}'.format(new_password))
    return False


def restore_sysadmin_password(current_password=None, target_password=None):
    global _host_users
    old_passwords = _host_users[('active-controller', 'sysadmin')]
    LOG.info('Restoring password for sysadmin, old_passwords:{}\n'.format(old_passwords))

    if not old_passwords or len(old_passwords) <= 1 or current_password == target_password:
        LOG.info('Password for sysadmin did not change, no need to restore')
        return

    current_password = old_passwords[-1] if current_password is None else current_password
    current_host = system_helper.get_active_controller_name()
    exclude_list = deque(old_passwords[0 - MAX_NUM_PASSWORDS_TRACKED:], MAX_NUM_PASSWORDS_TRACKED)

    for n in range(1, MAX_NUM_PASSWORDS_TRACKED+1):
        new_password = security_helper.gen_linux_password(exclude_list=list(exclude_list), length=PASSWORD_LEGNTH)
        LOG.info('chaning password {} times: from:{} to:{}\n'.format(n, current_password, new_password))

        security_helper.change_linux_user_password(current_password, new_password,host=current_host)
        HostLinuxCreds.set_password(new_password)
        current_password = new_password
        exclude_list.append(new_password)

        LOG.info('wait after chaning password of sysadmin\n')
        wait_after_change_sysadmin_password()

    # original_password = old_passwords[0] if old_passwords else 'Li69nux*'
    original_password = 'Li69nux*' if target_password is None else target_password

    LOG.info('Restore password of sysadmin to:{}'.format(original_password))

    security_helper.change_linux_user_password(current_password, original_password, user='sysadmin', host=current_host)
    HostLinuxCreds.set_password(original_password)
    LOG.info('Password for sysadmin is restored to:{}'.format(original_password))

    return original_password


def restore_sysadmin_password_raw(connect, current_password, original_password, exclude_list):
    if current_password == original_password:
        LOG.info('Current password is the same as the original password?!, do nothing')
        return

    for n in range(1, MAX_NUM_PASSWORDS_TRACKED+1):
        new_password = security_helper.gen_linux_password(exclude_list=exclude_list, length=PASSWORD_LEGNTH)
        exclude_list.append(new_password)
        LOG.info('chaning password {} times: from:{} to:{}\n'.format(n, current_password, new_password))

        change_password(connect, current_password, new_password)
        HostLinuxCreds.set_password(new_password)
        current_password = new_password

    LOG.info('Restore password of sysadmin to:{}'.format(original_password))
    change_password(connect, current_password, original_password)

    HostLinuxCreds.set_password(original_password)
    LOG.info('Password for sysadmin is restored to:{}'.format(original_password))


@fixture(scope="function", autouse=True)
def cleanup_test_users(request):

    def delete_test_users():
        global _host_users

        restore_sysadmin_password(target_password=TARGET_PASSWORD)

        LOG.info('Deleting users created for testing\n')
        conn_to_ac = ControllerClient.get_active_controller()
        count = 0
        for (host, user), _ in _host_users.items():
            if user == 'sysadmin' or user == HostLinuxCreds.get_user():
                LOG.info('-do not delete user:{} on host:{}\n'.format(user, host))
                continue

            LOG.info('-deleting user:{} on host:{}\n'.format(user, host))

            count += 1
            if host == 'active-controller':
                conn_to_ac.exec_sudo_cmd('userdel -r {}'.format(user))
            else:
                # sleep a bit so controller-1 have same password as controller-0
                time.sleep(30)
                with host_helper.ssh_to_host(host, password='Li69nux*') as conn:
                    LOG.info('TODO: delete user:{} on host:{} by CLI: userdel -r {}\n'.format(user, host, user))
                    conn.exec_sudo_cmd("userdel -r '{}'".format(user))

        LOG.info('{} test user deleted'.format(count))

    request.addfinalizer(delete_test_users)


def is_on_action_controller(host):
    return host == system_helper.get_active_controller_name()


def login_as_linux_user(user, password, host, cmd='whoami', expecting_fail=False):

    if is_on_action_controller(host):
        LOG.info('Login to the active controller:{}\n'.format(host))
        if user != HostLinuxCreds.get_user():
            skip('Login to the active controller(will not skip if controller-1 is active), '
                 'host:{}, user:{}'.format(host, user))
            return False, ''

    if user == 'sysadmin':
        LOG.info('Login to the host:{} as "sysadmin"!\n'.format(host))

    LOG.info('Attempt to login to host:{}, user:{}, password:{}\n'.format(host, user, password))
    # todo: if host is the active-controller, ssh_to_host will ignore username
    # and using 'sysadmin', which leads to error

    cmd = '(date; uuid; hostname; {}) 2>/dev/null'.format(cmd)
    try:
        with host_helper.ssh_to_host(host, username=user, password=password) as conn:
            code, output = conn.exec_cmd(cmd, fail_ok=True)
            LOG.info('code={}, output={}\n'.format(code, output))

            if 0 != code:
                msg = 'Failed to execute cmd:{} on host:{} as user:{}, password:{}'.format(cmd, host, user, password)
                LOG.info(msg)
                assert expecting_fail, msg

                return False, output

            else:
                assert not expecting_fail, \
                    'Expecting logged in but failed: host:{} as user:{} with password:{}'.format(host, user, password)

                return True, output

    except Exception as e:
        # LOG.info('Caught exception:\n{}\n'.format(e))
        msg = 'Expecting to login but failed with exception:{}'.format(e)
        assert expecting_fail, msg
        if not 'Permission denied,' in str(e):
            LOG.warning('Login as {}/{} failed without Permission denied error.'.format(user, password))
        else:
            LOG.info('Failed to login as expected on host:{}, user:{}, password:{}, for "Permission denied"'.
                     format(host, user, password))

        return False, str(e)


def create_linux_user(user, password, host, verify_cmd='id', fail_ok=False, verify_after_creation=True):
    LOG.info('Creating user:{} with password:{} on host:{}\n'.format(user, password, host))

    command = r"useradd '{}'; echo '{}' | sudo passwd '{}' --stdin".format(user, password, user)

    with host_helper.ssh_to_host(host) as connection:
        code, output = connection.exec_sudo_cmd(command, fail_ok=fail_ok)

    if verify_after_creation:
        command = "hostname; sudo su - '{}' -c '{}'".format(user, verify_cmd if verify_cmd else 'id')

        with host_helper.ssh_to_host(host) as connection:
            code, output = connection.exec_sudo_cmd(command, fail_ok=False)

    LOG.info('OK, verified user:{} with password:{} on host:{} was created\n'.format(user, password, host))

    return code, output


def update_host_user(host, user, password):
    global _host_users
    _host_users[(host, user)].append(password)
    LOG.info('TODO: _host_users:{}'.format(_host_users))


@mark.parametrize(('user', 'password', 'host'), (
    ('testuser01', 'Li69nux*', 'controller-0'),
    ('testuser02', 'Li69nux*', 'controller-1'),
    ('testuser03', 'Li69nux*', 'compute-0'),
))
def test_non_sysadmin_not_propagating(user, password, host):
    '''create only non sysadmin users'''

    LOG.tc_step('Create user for test, user:{}, password:"{}", host:{}\n'.format(user, password, host))

    if user == 'sysadmin':
        skip('User name "sysadmin" is dedicated to the special Local Linux Account used by Administrator.')
        return

    hosts = system_helper.get_hosts(availability=[HostAvailState.AVAILABLE])
    if len(hosts) < 2:
        LOG.info('Only 1 host: {}\n'.format(hosts))
        skip('Only 1 host: {}, needs 2+ hosts to test\n'.format(hosts))

    elif host == "compute-0" and len(hosts) < 3:
        LOG.info('Only controller lab cannot execute compute test {}\n'.format(hosts))
        skip('Only controllers are avaliable {}, needs 2+ hosts to test\n'.format(hosts))

    else:

        active_controller = system_helper.get_active_controller_name()

        create_linux_user(user, password, host, fail_ok=False)
        update_host_user(host, user, password)

        LOG.info('OK, created user for test, user:{}, password:"{}", host:{}\n'.format(user, password, host))

        LOG.info('Randomly choice another host to test logging on, expecting to fail')

        other_host = random.choice([h for h in hosts if h != host])
        # check for CPE option

        LOG.tc_step('Attempt to login to other host as user, other-host:{}, this-host:{}, user:{}, password:{}'.format(
            other_host, host, user, password))

        logged_in, output = login_as_linux_user(user, password, other_host, cmd='hostname; id', expecting_fail=True)

        if logged_in:
            msg = 'actually logged in to host:{}\noutput:{}\n'.format(host, output)
            assert False, 'Expecting to fail in logging to host, but ' + msg
        else:
            LOG.info('OK, been rejected to login other host as local linux user, host:{}, '
                     'other host:{}, user:{}, password:{}\n'.format(host, other_host, user, password))


def wait_after_change_sysadmin_password():
    total_wait_time = MAX_WAIT_FOR_ALARM
    each_wait_time = 60
    waited_time = 0

    time.sleep(10)

    alarm_id = ALARM_ID_OUTOF_CONFIG
    while waited_time < total_wait_time:
        waited_time += each_wait_time

        found = system_helper.wait_for_alarm(alarm_id=alarm_id, fail_ok=True, timeout=each_wait_time)
        if found:
            LOG.info('OK, found alarm for password change, alarm-id:{}'.format(alarm_id))
            alarm_gone = system_helper.wait_for_alarm_gone(alarm_id, fail_ok=True, timeout=each_wait_time)
            if alarm_gone:
                LOG.info('OK, found alarms were cleared for password change, alarm-id:{}'.format(alarm_id))
                break
    else:
        assert False, 'Failed to find alarms/or alarms not cleared for password change within {} seconds, ' \
                      'expecting alarm-id:{}'.format(waited_time, alarm_id)
    return True


def test_sysadmin_password_propagation():
    global _host_users

    LOG.tc_step('Attemp to change the password for sysadmin')

    user = 'sysadmin'
    if user != HostLinuxCreds.get_user():
        LOG.error('HostLinuxCreds.get_user() is NOT sysadmin')
        skip('HostLinuxCreds.get_user() is NOT sysadmin')
        return

    password = HostLinuxCreds.get_password()
    update_host_user('active-controller', user, password)

    new_password = security_helper.gen_linux_password(exclude_list=_host_users[('active-controller', user)],length=PASSWORD_LEGNTH)

    current_host = system_helper.get_active_controller_name()

    changed, changed_password = security_helper.change_linux_user_password(
        password, new_password, user='sysadmin', host=current_host)

    assert changed, \
        'Failed to change sysadmin password, from {} to {} on host {}'.format(password, new_password, current_host)

    LOG.info('OK, password changed for sysadmin, new password:{}, old password:{} on host:{}\n'.format(
        new_password, password, current_host))

    HostLinuxCreds.set_password(new_password)
    update_host_user('active-controller', user, new_password)

    LOG.tc_step('Wait alarms for password changed raised and cleared')

    wait_after_change_sysadmin_password()
    LOG.info('OK, alarms raised and cleared after previous password change')

    LOG.tc_step('Verify the new password populated to other hosts by logging to them')
    LOG.info('Select another host to login')
    hosts = [ch for ch in system_helper.get_hosts(availability=[HostAvailState.AVAILABLE]) if current_host != ch]

    if len(hosts) < 1:
        skip('No other host can test sysadmin with new password')
        return

    hosts = random.sample(hosts, min(len(hosts), 2))
    LOG.info('OK, will verify if new password were propagated to other hosts:{}'.format(hosts))

    for other_host in hosts:
        login_as_linux_user(user, new_password, host=other_host, expecting_fail=False)

    LOG.tc_step('Try to change the password again using the original password')
    # try to change the password again using the original password
    LOG.info('Change password from  {} to {} again should not be successful'.format(password, new_password))
    changed, changed_password = security_helper.change_linux_user_password(
        password, new_password, user='sysadmin', host=current_host)

    assert not changed, \
        'Password change from {} to {} on host {} should fail'.format(password, new_password, current_host)



def swact_host_after_reset_sysadmin_raw(connect, active_controller_name):
    cmd = 'source /etc/platform/openrc; system host-swact {}'.format(active_controller_name)
    prompt = r'controller-[01] \~\(keystone_admin\)'
    index, output = execute_cmd(connect, cmd, allow_fail=True, prompt=prompt)
    LOG.info('returned: index:{}, output:{}, cmd:{}\n'.format(index, output, cmd))


def swact_host_after_reset_sysadmin(active_controller):

    current_host = system_helper.get_active_controller_name()
    LOG.info('swact host:{}'.format(current_host))
    command = 'system host-swact {}'.format(current_host)
    try:
        code, output = active_controller.exec_cmd(command)
        LOG.info('after send host-swact, got output:{}, code:{}\n'.format(output, code))
    except Exception as e:
        LOG.info('ignore the exception for now, error:{}'.format(e))

    LOG.info('Close the current connection to the active-controller')

    wait_time = 180
    LOG.info('wait {} seconds after host-swact {}'.format(wait_time, current_host))
    time.sleep(wait_time)


def first_login_to_floating_ip(user, current_password, new_password):
    floating_ip = lab_info.get_lab_floating_ip()
    return login_host_first_time(floating_ip, user, current_password, new_password, expect_fail=False)


def execute_sudo_cmd(connect, cmd, password, expecting_fail=False, prompt=Prompt.CONTROLLER_PROMPT):
    LOG.info('Sending cmd:{}\n'.format(cmd))
    connect.flush()
    if not cmd.startswith('sudo '):
        cmd = 'sudo ' + cmd
    connect.sendline(cmd)

    index = 0
    output = ''
    try:
        index = connect.expect(['[pP]assword:', prompt])
        if index == 0:
            LOG.info('asking the password for sudoer\n')
            LOG.info('send:{}\n'.format(password))
            connect.sendline(password)
            index = connect.expect([prompt])

        LOG.info('get result: index:{}\n'.format(index))
        output = connect.before + connect.after
        LOG.info('got output:{}, index:{}\n'.format(output, index))
    except Exception as e:
        LOG.info('Failed to execute cmd:{}, error:{}'.format(cmd, e))
        if not expecting_fail:
            raise

    if not expecting_fail:
        assert index == 0, 'Failed to execute cmd:{}'.format(cmd)

    return index, output


def execute_cmd(connect, cmd, allow_fail=False, prompt=Prompt.CONTROLLER_PROMPT):
    # prompt = prompt if prompt else '\[.*@controller\-[01]'.format()
    LOG.info('Sending cmd:{}\n'.format(cmd))
    connect.flush()
    connect.sendline(cmd)

    index = 0
    output = ''
    try:
        index = connect.expect([prompt])
        LOG.info('get result: index:{}\n'.format(index))

        output = connect.before + connect.after
        LOG.info('got output:{}, index:{}\n'.format(output, index))
    except Exception as e:
        LOG.info('Failed to execute cmd:{}, error:{}'.format(cmd, e))
        if not allow_fail:
            raise
    else:
        return index, output

    if not allow_fail:
        assert index == 0, 'Failed to execute cmd:{}'.format(cmd)

    return index, output


@mark.parametrize(('swact'), (
    ('swact'),
    ('no-swact'),
))
def test_sysadmin_aging_and_swact(swact):
    """
    Test password aging.

    Args:

    Test Steps:
    1   change the aging setting, forcing current password expired, new password be set and required by next login
    2   verify the new password is required upon login to the floating IP

    Returns:

    """
    global _host_users

    LOG.tc_step('Change the aging settings of sysadmin')
    if 'sysadmin' != HostLinuxCreds.get_user():
        skip('Current User:{} is not sysadmin'.format(HostLinuxCreds.get_user()))
        return

    user = 'sysadmin'
    original_password = HostLinuxCreds.get_password()
    active_controller = ControllerClient.get_active_controller()
    active_controller_name = system_helper.get_active_controller_name()
    host = lab_info.get_lab_floating_ip()
    _host_users[('active-controller', 'sysadmin')] = [original_password]

    LOG.info('Closing ssh connection to the active controller\n')
    active_controller.flush()
    active_controller.close()

    wait_time = 10
    LOG.info('wait for {} seconds after closing the ssh connect to the active-controller'.format(wait_time))
    time.sleep(wait_time)

    # command = 'chage -d 0 -M 0 sysadmin'
    # this is from the test plan
    # sudo passwd -e sysadmin
    command = 'sudo passwd -e sysadmin'
    LOG.info('changing password aging using command:\n{}'.format(command))
    connect = log_in_raw(host, user, original_password)
    LOG.info('sudo execute:{}\n'.format(command))
    code, output = execute_sudo_cmd(connect, command, original_password, expecting_fail=False)
    # code, output = active_controller.exec_sudo_cmd(command)
    LOG.info('OK, aging settings of sysadmin was successfully changed with command:\n{}\ncode:{}, output:{}'.format(
        command, code, output))


    LOG.tc_step('Verify new password needs to be set upon login')
    exclude_list = [original_password]

    # verify password was expired
    new_password = security_helper.gen_linux_password(exclude_list=exclude_list, length=PASSWORD_LEGNTH)
    set_password = first_login_to_floating_ip(user, original_password, new_password)[1]
    if set_password != new_password:
        message = 'first time login did not ask for new password:{}, ' \
                  'current password should still been in effective\n'.format(new_password, original_password)
        LOG.warn(message)
        assert False, message

    # and reset with new password
    new_password = set_password
    if new_password != original_password:
        _host_users[('active-controller', 'sysadmin')].append(new_password)

    HostLinuxCreds.set_password(new_password)
    exclude_list.append(new_password)
    LOG.info('OK, new password was required and logged in\n')

    # reconnect after set new password
    LOG.info('reconnect to the active controller')
    host = lab_info.get_lab_floating_ip()
    connect = log_in_raw(host, user, new_password)

    cmd = 'hostname; id; date'
    LOG.info('attempt to run cmd:{}\n'.format(cmd))

    code, output = execute_cmd(connect, cmd)
    LOG.info('output:\n{}\n, code:{}, cmd:{}\n'.format(output, code, cmd))

    # perform swact and verify swact is working
    wait_time = 300
    LOG.info('wait for {} seconds after aging settings been modified'.format(wait_time))
    time.sleep(wait_time)

    if swact == 'swact':
        LOG.tc_step('Swact host')
        swact_host_after_reset_sysadmin_raw(connect, active_controller_name)
        LOG.info('OK, host swact')

    LOG.info('Closing raw ssh connection to the active controller\n')
    connect.logout()

    wait_time = 180
    LOG.info('wait for {} after swact and closing own ssh connection'.format(wait_time))
    time.sleep(wait_time)

    # reconnect to active after swact
    LOG.info('reconnect to the active controller')
    host = lab_info.get_lab_floating_ip()
    connect = log_in_raw(host, user, new_password)

    LOG.tc_step('Restore the password ')

    # restore_sysadmin_password_raw(connect, new_password, original_password, exclude_list=exclude_list)
    restore_sysadmin_password_raw(connect, current_password=new_password, original_password="Li69nux*", exclude_list=exclude_list)

    HostLinuxCreds.set_password(original_password)
    LOG.info('Close the connection to {} as user:{} with password:{}'.format(host, user, original_password))
    connect.close()

    LOG.info('reconnect to the active controller using ControllerClient.get_active_controller()\n')
    active_controller.connect()


def get_pxssh_session():
    # connect = pxssh.pxssh(encoding='utf-8', searchwindowsize=None)
    connect = pxssh.pxssh(encoding='utf-8', searchwindowsize=4096)
    connect.force_password = True
    connect.maxread = 4096

    return connect


def login_host_first_time(host, user, password, new_password, expect_fail=False, timeout=120):
    cmd_expected = [
        (
            # 'ssh -l {} -o UserKnownHostsFile=/dev/null {}'.format(user, host),
            # 'ssh -t -q -l {} {}'.format(user, host),
            'ssh',
            ('Are you sure you want to continue connecting (yes/no)?',),
            ('Failed to get "continue connecting" prompt',)
        ),
        (
            'yes',
            ("{}@{}\'s password:".format(user, host),),
            (),
        ),
        (
            password,
            (r'\(current\) UNIX password:',),
            (Prompt.CONTROLLER_PROMPT, TIMEOUT),
        ),
        (
            password,
            ('New password:',),
            (),
        ),
        (
            new_password,
            ('Retype new password:',),
            (),
        ),
        (
            new_password,
            ('passwd: all authentication tokens updated successfully.',),
            (),
        ),
    ]

    message = ' host:{} as user:{} with password:{}\n'.format(host, user, password)

    LOG.info('Attempt to login the first time, {}'.format(message))

    connect = get_pxssh_session()

    try:
        first_cmd = True

        for cmd, expected_output, errors in cmd_expected:
            LOG.info('cmd:{}, \nexpected:{}\n'.format(cmd, expected_output))

            if first_cmd:
                options = ' '.join(['-o "{}={}"'.format(k, v) for k, v in SSH_OPTS.items()])

                # cmd = '{} {} -l {} {}'.format(cmd, options, user, host)
                cmd = '{} {} -l {} {}'.format(cmd, options, user, host)
                LOG.info('first time login: sending cmd:{}, \nexpected:{}\n'.format(cmd, expected_output))

                spawn._spawn(connect, cmd)
                connect.force_password = True
                first_cmd = False

            else:
                LOG.info('sending cmd:{}\n'.format(cmd))
                connect.sendline(cmd)

            all_output = list(expected_output + errors)
            LOG.info('expecting outputs:{}\n'.format(all_output))

            index = connect.expect(all_output)
            LOG.info('actually got: index:{}, output:{}\n\n'.format(index, all_output[index]))
            LOG.info('actually got: before:\n{}\nafter:{}\n\n'.format(connect.before, connect.after))
            if index >= len(expected_output):
                LOG.info('error: sent:{}, returned:{}, returned-index:{}\n'.format(cmd, all_output[index], index))
                LOG.info('OUTPUT:before:{}\nafter:{}\n'.format(connect.before, connect.after))
                if r'\(current\) UNIX password:' in expected_output:
                    LOG.info('connection broke when expecting "\(current\) UNIX password:", take as good?')
                    return True, password
                break

            time.sleep(2)

    except Exception as e:
        message = 'failed to connect to {}, got error: {}\nbefore:{}\nafter:{}\n'.format(
            message, e, connect.before, connect.after)
        LOG.info(message)
        assert expect_fail, message

    else:
        LOG.info('OK, logged in for the first time, new password set:{}\n'.format(new_password))
        LOG.info('close the connection')
        try:
            connect.logout()
        except Exception as e:
            LOG.info('got error when closing connection:{}\n'.format(e))

        wait_time = 180
        LOG.info('Wait {} seconds after change/reset the password of sysadmin'.format(wait_time))
        time.sleep(wait_time)

        return True, new_password

    finally:
        pass
        # if close_at_exit:
        #     LOG.info('close ssh connection to {}'.format(host))
        #     connect.close()
    return False, ''


def log_in_raw(host, user, password, expect_fail=False):
    message = ' host:{} as user:{} with password:{}\n'.format(host, user, password)
    LOG.info('logging onto {}, expecting failure:{}\n'.format(message, expect_fail))

    connect = get_pxssh_session()
    options = ' '.join(['-o {}={}'.format(k, v) for k, v in SSH_OPTS.items()])
    cmd = 'ssh {} -l {} {}'.format(options, user, host)
    # cmd = 'ssh -q -l {} {}'.format(user, host)
    LOG.info('send cmd:{}\n'.format(cmd))
    spawn._spawn(connect, cmd)
    connect.force_password = True

    index = connect.expect(['Are you sure you want to continue connecting (yes/no)?'])
    if index != 0:
        LOG.info('failed to get expected result from cmd, \ncmd:{}\nindex:{}\n'.format(cmd, index))

    cmd = 'yes'
    LOG.info('send cmd:{}\n'.format(cmd))
    connect.sendline(cmd)
    index = connect.expect(['password:'])
    if index != 0:
        LOG.info('failed to get expected result from cmd, \ncmd:{}\nindex:{}\n'.format(cmd, index))

    LOG.info('send password:{}\n'.format(password))
    connect.sendline(password)
    prompt = Prompt.CONTROLLER_PROMPT
    error = 'Permission denied, please try again.'
    index = connect.expect([prompt, error])
    if index != 0:
        msg = '{}, got index:{}'.format(message, index)
        if not expect_fail:
            LOG.info('failed to get expected prompt, {}'.format(msg))
            assert False, 'failed to get expected/login, {}'.format(msg)
        else:
            LOG.info('as expected, failed to login, {}\n'.format(msg))
            return None
    else:
        msg = 'logged in, {}\noutput before:{}, after:{}\n'.format(message, connect.before, connect.after)
        if expect_fail:
            LOG.info('Error, expecting to fail but actually {}'.format(msg))
            assert False, 'Error, expecting to fail but actually {}'.format(msg)
        else:
            LOG.info('OK, logged in, will verify it, {}\n'.format(message))

            cmd = '(date; uuid; hostname; id; ifconfig | \grep 128.224 -B1 -A7) 2>/dev/null'
            LOG.info('send cmd: {}\n'.format(cmd))
            connect.sendline(cmd)
            index = connect.expect([prompt, TIMEOUT])
            LOG.info('returned:\nbefore:{}\nafter:{}\n'.format(connect.before, connect.after))
            if 1 == index:
                LOG.info('timeout:')
                return None

            return connect


def test_linux_user_lockout():
    """
    Verify linux user account will be lockout after 5? failed attempts

    Test Steps:
        - attempt to login with invalid password as sysadmin 5 times
        - verify cannot login as sysadmin anymore
    Returns:

    """

    LOG.tc_step('Attempt to login with WRONG password as sysadmin {} times'.format(MAX_FAILED_LOGINS))
    user = 'sysadmin'
    if HostLinuxCreds.get_user() != user:
        skip('Error: user name from HostLinuxCreds.get_user() != sysadmin, it is:{}'.format(HostLinuxCreds.get_user()))
        return

    password = HostLinuxCreds.get_password()
    invalid_password = '123'
    host = lab_info.get_lab_floating_ip()

    LOG.info('verify we can login in at beginning')
    connect = log_in_raw(host, user, password, expect_fail=False)
    assert connect, 'Failed to login in at beginning with password'.format(password)

    for n in range(1, MAX_FAILED_LOGINS+1):
        message = '{}: Expecting to fail to login with invalid password, host:{}, user:{}, password:{}\n'.format(
            n, host, user, invalid_password)
        LOG.info(message)
        connect = log_in_raw(host, user, invalid_password, expect_fail=True)
        assert not connect, 'Expecting to fail but not.' + message

    LOG.info('OK, failed {} times to login with invalid password:{} as user:{} to host:{}\n'.format(
        MAX_FAILED_LOGINS, invalid_password, user, host))

    LOG.tc_step('Now attempt to login with CORRECT password:{}, expecting to fail\n'.format(password))
    connect = log_in_raw(host, user, password, expect_fail=True)
    message = 'host:{}, user:{}, password:{}\n'.format(host, user, password)
    assert not connect, 'Expecting to fail but not.' + message
    LOG.info('OK, failed to login with CORRECT password due to the user account was locked down\n')

    LOG.tc_step('Wait for 5 minutes + 20 seconds for the account been automatically unlocked\n')
    time.sleep(320)
    LOG.info('verify we can login again after waiting for 5 minutes')
    connect = log_in_raw(host, user, password, expect_fail=False)
    assert connect, 'Failed to login again after waiting for 5 minutes.' + message
