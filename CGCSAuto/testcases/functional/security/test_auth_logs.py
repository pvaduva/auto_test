import re
import time

from pytest import mark

from consts.stx import Prompt
from consts.auth import HostLinuxUser
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG


def exec_sudo_cmd_fail(ssh, cmd):
    cmd = 'sudo ' + cmd
    ssh.send(cmd)
    index = ssh.expect(blob_list=[ssh.prompt, Prompt.PASSWORD_PROMPT])
    fake_password = ssh.password + '1'

    if index == 1:
        ssh.send(fake_password)
        ssh.expect(blob_list=[".* "])
        ssh.send_control('c')
        ssh.expect(blob_list=[ssh.prompt])


def wait_for_log(ssh_client, patterns, log_path, start_time, timeout=30, interval=3):

    LOG.tc_step("Waiting for expected logs in {}: {}".format(log_path, patterns))
    end_time = time.time() + timeout
    start_time = start_time[:-3] + '000'

    found = []
    while time.time() < end_time:
        code, out = ssh_client.exec_cmd("""cat {} | awk '$0 > "{}"'""".format(log_path, start_time))
        out = out.split('\n')
        found = []

        for line in out:
            for i in range(len(patterns)):
                regex = re.compile(patterns[i])
                if patterns[i] not in found and re.search(regex, line):
                    found.append(patterns[i])
                    LOG.info("Found {}".format(line))
                    break

        if len(found) == len(patterns):
            LOG.info("All expected logs found: {}".format(found))
            break
        time.sleep(interval)

    return found


@mark.p2
def test_auth_log_sudo_cmd():
    """
    TC5202 Test the logs created during successful and failed sudo commands

    Test Steps:
        - Ssh to a controller and execute a sudo command
        - Search through the logs to find the log that should be created from the sudo command
        - Exit ssh and ssh to controller again
        - Execute sudo command using incorrect password
        - Find the log that should be created from the failed sudo command

    """
    log_path = '/var/log/auth.log'

    con_ssh = ControllerClient.get_active_controller()

    LOG.tc_step("Get timestamp for last line in auth.log")
    start_time = con_ssh.exec_cmd("tail -1 {} | awk '{{print $1}}'".format(log_path))[1]

    cmd = '-k ls -l'
    LOG.tc_step("Executing sudo command {}".format(cmd))
    con_ssh.exec_sudo_cmd(cmd, fail_ok=True)

    user = HostLinuxUser.get_user()
    searching_for = ['sudo: notice  {}.*PWD=/home/{} ; USER=root ; '
                     'COMMAND=/usr/bin/ls -l'.format(user, user)]
    found = wait_for_log(log_path=log_path, ssh_client=con_ssh,
                         patterns=searching_for, start_time=start_time)

    assert len(searching_for) == len(found), "FAIL: The sudo command was not logged. " \
                                             "Expecting to find: {} found: {}".format(searching_for, found)

    LOG.tc_step("Executing sudo command {} with wrong password".format(cmd))
    start_time = con_ssh.exec_cmd("tail -1 {} | awk '{{print $1}}'".format(log_path))[1]
    exec_sudo_cmd_fail(con_ssh, cmd)

    searching_for = ['sudo: notice pam_unix\(sudo:auth\): authentication '
                     'failure; logname={} .* '
                     'ruser={} rhost=  user={}'.format(user, user, user)]
    found = wait_for_log(log_path=log_path, ssh_client=con_ssh,
                         patterns=searching_for, start_time=start_time)

    assert len(searching_for) == len(found), "FAIL: The failed sudo command was not logged. " \
                                             "Expecting to find: {} found: {}".format(searching_for, found)


@mark.p2
def test_auth_log_postgres():
    """
    TC5204 Test postgres login and logout logs

    Test Steps:
        - Check logs for log entries about postgres login/logout
        - If there were none found, wait 30 seconds for them to be generated then check for the logs again

    """
    log_path = '/var/log/auth.log'
    con_ssh = ControllerClient.get_active_controller()

    LOG.tc_step("Checking the logs for postgress entries")
    start_time = con_ssh.exec_cmd("tail -1 {} | awk '{{print $1}}'".format(log_path))[1]

    searching_for = [
                     r'info pam_unix\(runuser:session\): session opened for user postgres by \(uid=0\)',
                     r'info pam_unix\(runuser:session\): session closed for user postgres']

    found = wait_for_log(con_ssh, searching_for, log_path=log_path, start_time=start_time, timeout=45, interval=10)

    assert len(searching_for) == len(found), "FAIL: expecting to find {} in the logs. Found {}."\
                                             .format(searching_for, found)


@mark.p3
def test_auth_log_sudo_su():
    """
    TC5205 Test logs created by sudo su

    Test Steps:
        - Ssh to a controller and execute 'sudo su'
        - Check that logs are created by the command
        - Logout and ssh to the controller again
        - Attempt to execute 'sudo su' with an incorrect password
        - Check that there are logs created by the failed command

    """
    con_ssh = ControllerClient.get_active_controller()
    user = HostLinuxUser.get_user()
    searching_for = ['sudo: notice  {}.*PWD=/home/{} ; USER=root ; '
                     'COMMAND=/usr/bin/su \-'.format(user, user),
                     'su: notice \(to root\) {} on'.format(user),
                     # uses su-l:session because login_as_root calls 'sudo su -'
                     'su: info pam_unix\(su-l:session\): session opened for '
                     'user root by {}\(uid=0\)'.format(user)]

    log_path = '/var/log/auth.log'
    start_time = con_ssh.exec_cmd("tail -1 {} | awk '{{print $1}}'".format(log_path))[1]

    LOG.tc_step("Logging in as su")
    with con_ssh.login_as_root() as root:
        LOG.info("Logged in as root")

    found = wait_for_log(con_ssh, patterns=searching_for, log_path=log_path, start_time=start_time)
    assert len(searching_for) == len(found), "FAIL: The sudo su command was not logged. " \
                                             "Looking for logs resembling: {} found: {}".format(searching_for,found)

    cmd = '-k su'
    LOG.tc_step("Executing sudo command {} with wrong password".format(cmd))
    searching_for = ['sudo: notice pam_unix\(sudo:auth\): authentication failure; '
                     'logname={}.*ruser={} rhost=  user={}'.format(
        user, user, user)]
    start_time = con_ssh.exec_cmd("tail -1 {} | awk '{{print $1}}'".format(log_path))[1]
    exec_sudo_cmd_fail(con_ssh, cmd)
    found = wait_for_log(con_ssh, searching_for, log_path=log_path, start_time=start_time)

    assert len(searching_for) == len(found), "FAIL: The failed sudo su command was not logged. " \
                                             "Looking for logs resembling: {} found: {}".format(searching_for, found)
