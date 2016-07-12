import copy
import time
import re

from consts import timeout
from consts.cgcs import HTTPPorts, Prompt
from pytest import fixture, mark, skip
from keywords import html_helper, host_helper, system_helper
from utils.tis_log import LOG
from utils.ssh import SSHClient, ControllerClient
from utils import cli


def test_horizon_login():
    skip()


def test_ssh_login():
    ip = html_helper.get_ip_addr()
    ssh = SSHClient(host=ip)
    out = ssh.connect()
    code, out = ControllerClient.get_active_controller().exec_cmd("tail /var/log/auth.log")
    lines = out.split('\n')
    for line in lines:
        print(line)
        in_line = 'Received disconnect' in line
        print(in_line)
    print("\n")
    print(ssh.close())
    code, out = ControllerClient.get_active_controller().exec_cmd("tail /var/log/auth.log")
    lines = out.split('\n')
    for line in lines:
        print(line)
        in_line = 'Received disconnect' in line
        print(in_line)
    skip()


def test_sftp_login():
    address = "wrsroot@{}".format(html_helper.get_ip_addr())
    code, out = ControllerClient.get_active_controller().exec_cmd("sftp {}\nyes\n".format(address))
    print(out)
    skip()


def exec_sudo_cmd_fail(ssh, cmd, fake_password, expect_timeout=20):
    cmd = 'sudo ' + cmd
    LOG.info("Executing sudo command: {}".format(cmd))
    ssh.send(cmd)
    index = ssh.expect([Prompt.PASSWORD_PROMPT], timeout=expect_timeout)
    if index == 1:
        ssh.send(fake_password)

        index = ssh.expect(["Sorry, try again.", Prompt.PASSWORD_PROMPT], timeout=expect_timeout)
        if index == 1:
            ssh.send(fake_password)
            LOG.info("sending fake password")
            index = ssh.expect(blob_list=["Sorry, try again.", Prompt.PASSWORD_PROMPT], timeout=expect_timeout)
            if index == 1:
                ssh.send(fake_password)
                LOG.info("sending fake password")


    cmd_output_list = ssh.cmd_output.split('\n')[0:-1]  # exclude prompt
    # LOG.debug("cmd output list: {}".format(cmd_output_list))
    # cmd_output_list[0] = ''                                       # exclude command, already done in expect
    DATE_OUTPUT = r'[0-2]\d:[0-5]\d:[0-5]\d\s[A-Z]{3}\s\d{4}$'
    if re.search(DATE_OUTPUT, cmd_output_list[-1]):
        cmd_output_list = cmd_output_list[:-1]

    cmd_output = '\n'.join(cmd_output_list)

    cmd_output = cmd_output.strip()
    return 1, cmd_output





def test_sudo_log():
    ip = html_helper.get_ip_addr()
    ssh = SSHClient(host=ip)
    ssh.connect()
    ssh.exec_sudo_cmd('ls -l', fail_ok=True)
    code, out = ssh.exec_cmd("tail /var/log/auth.log")
    ssh.close()
    print(out)
    ssh = SSHClient(host=ip)
    ssh.connect()
    print("\n\n")
    exec_sudo_cmd_fail(ssh, 'ls -l', ssh.password + "1")
    code, out = ssh.exec_cmd("tail /var/log/auth.log")
    print(out)
    skip()


def test_ssh_login_ldap():
    skip()


def test_postgress():
    ssh = ControllerClient.get_active_controller()
    code, out = ssh.exec_cmd('tail /var/log/auth.log')
    logs = out.split('\n')
    substrings = ["notice (to postgres) root on none",
                  "info pam_unix(su:session): session opened for user postgres by (uid=0)",
                  "info pam_unix(su:session): session closed for user postgres"]
    found_logs = []
    for line in logs:
        LOG.info("Current line is: {}".format(line))
        for i in range(0, len(substrings)):
            if substrings[i] in line and substrings[i] not in found_logs:
                found_logs.append(substrings[i])

    if len(found_logs) < 3:
        time.sleep(30)
        found_logs = []
        code, out = ssh.exec_cmd('tail /var/log/auth.log')
        logs = out.split('\n')
        for line in logs:
            LOG.info("Current line is: {}".format(line))
            for i in range(0, len(substrings)):
                if substrings[i] in line and substrings[i] not in found_logs:
                    found_logs.append(substrings[i])

    assert 3 == len(found_logs), "FAIL: expecting to find {} in the logs. Found {}.".format(substrings, found_logs)
    skip()


def test_sudo_su():
    skip()


