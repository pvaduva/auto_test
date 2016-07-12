import time
import re

from consts.cgcs import Prompt
from keywords import html_helper, host_helper, system_helper
from utils.tis_log import LOG
from utils.ssh import SSHClient, ControllerClient


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


def test_sudo_log():
    """
    TC5202 Test the logs created during successful and failed sudo commands

    Test Steps:
        - Ssh to a controller and execute a sudo command
        - Search through the logs to find the log that should be created from the sudo command
        - Exit ssh and ssh to controller again
        - Execute sudo command using incorrect password
        - Find the log that should be created from the failed sudo command

    """
    ssh = SSHClient(host=html_helper.get_ip_addr())
    ssh.connect()
    cmd = 'ls -l'
    LOG.tc_step("Executing sudo command {}".format(cmd))
    ssh.exec_sudo_cmd(cmd, fail_ok=True)
    code, out = ssh.exec_cmd("tail /var/log/auth.log")
    out = out.split('\n')
    ssh.close()
    searching_for = ['sudo: notice  wrsroot.*PWD=/home/wrsroot ; USER=root ; COMMAND=/usr/bin/ls -l']
    found = []

    for line in out:
        for i in range(0, len(searching_for)):
            LOG.tc_step("Searching for logs containing: {}".format(searching_for[i]))
            regex = re.compile(searching_for[i])
            if searching_for[i] not in found and re.search(regex, line):
                found.append(searching_for[i])
                LOG.info("Found {}".format(line))
                break

    assert len(searching_for) == len(found), "FAIL: The sudo command was not logged. " \
                                             "Expecting to find: {} found: {}".format(searching_for, found)

    ssh = SSHClient(host=html_helper.get_ip_addr())
    ssh.connect()
    LOG.tc_step("Executing sudo command {} with wrong password".format(cmd))
    exec_sudo_cmd_fail(ssh, cmd)
    code, out = ssh.exec_cmd("tail /var/log/auth.log")
    out = out.split('\n')
    ssh.close()
    searching_for = ['sudo: notice pam_unix\(sudo:auth\): authentication failure; logname=wrsroot .* '
                     'ruser=wrsroot rhost=  user=wrsroot']
    found = []

    for line in out:
        for i in range(0, len(searching_for)):
            LOG.tc_step("Searching for logs containing: {}".format(searching_for[i]))
            regex = re.compile(searching_for[i])
            if searching_for[i] not in found and re.search(regex, line):
                found.append(searching_for[i])
                LOG.info("Found {}".format(line))
                break

    assert len(searching_for) == len(found), "FAIL: The failed sudo command was not logged. " \
                                             "Expecting to find: {} found: {}".format(searching_for, found)


def test_postgress():
    """
    TC5204 Test postgres login and logout logs

    Test Steps:
        - Check logs for log entries about postgres login/logout
        - If there were none found, wait 30 seconds for them to be generated then check for the logs again

    """
    ssh = ControllerClient.get_active_controller()
    LOG.tc_step("Checking the logs for postgress entries. First attempt")
    code, out = ssh.exec_cmd('tail /var/log/auth.log')
    logs = out.split('\n')
    searching_for = ["notice \(to postgres\) root on none",
                     "info pam_unix\(su:session\): session opened for user postgres by \(uid=0\)",
                     "info pam_unix\(su:session\): session closed for user postgres"]
    found = []
    for line in logs:
        for i in range(0, len(searching_for)):
            LOG.tc_step("Searching for logs containing: {}".format(searching_for[i]))
            regex = re.compile(searching_for[i])
            if searching_for[i] not in found and re.search(regex, line):
                found.append(searching_for[i])
                LOG.info("Found {}".format(line))
                break

    if len(found) != len(searching_for):
        LOG.info("Not found. Check again in 30 seconds.")
        time.sleep(30)
        found = []
        LOG.tc_step("Checking the logs for postgress entries. Second attempt")
        code, out = ssh.exec_cmd('tail /var/log/auth.log')
        logs = out.split('\n')
        for line in logs:
            for i in range(0, len(searching_for)):
                LOG.tc_step("Searching for logs containing: {}".format(searching_for[i]))
                regex = re.compile(searching_for[i])
                if searching_for[i] not in found and re.search(regex, line):
                    found.append(searching_for[i])
                    LOG.info("Found {}".format(line))
                    break

    assert len(searching_for) == len(found), "FAIL: expecting to find {} in the logs. Found {}."\
                                             .format(searching_for, found)


def test_sudo_su():
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

    ssh = SSHClient(host=ip)
    ssh.connect()

    cmd = 'su'
    LOG.tc_step("Executing sudo command {} with wrong password".format(cmd))
    exec_sudo_cmd_fail(ssh, cmd)
    code, out = ssh.exec_cmd("tail /var/log/auth.log", fail_ok=True)
    out = out.split('\n')
    ssh.close()
    searching_for = ['sudo: notice pam_unix\(sudo:auth\): authentication failure; '
                     'logname=wrsroot.*ruser=wrsroot rhost=  user=wrsroot']
    found = []

    for line in out:
        for i in range(0, len(searching_for)):
            LOG.tc_step("Searching for logs containing: {}".format(searching_for[i]))
            regex = re.compile(searching_for[i])
            if searching_for[i] not in found and re.search(regex, line):
                found.append(searching_for[i])
                LOG.info("Found {}".format(line))
                break

    assert len(searching_for) == len(found), "FAIL: The failed sudo su command was not logged. " \
                                             "Looking for logs resembling: {} found: {}".format(searching_for, found)
