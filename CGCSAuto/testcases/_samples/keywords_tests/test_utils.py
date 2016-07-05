from pytest import mark
import pexpect

from keywords import host_helper
from utils.ssh import ssh_to_controller0, ControllerClient
from utils import exceptions
from utils.tis_log import LOG

con_ssh = ControllerClient.get_active_controller()

def test_scp_files():
    con_ssh = ssh_to_controller0()
    con_ssh.scp_files_to_local_host('/home/wrsroot/instances/*', dest_password='test_pwd')

    host_helper.swact_host()
    con_ssh = ssh_to_controller0()
    con_ssh.scp_files_to_local_host('/home/wrsroot/instances/*', dest_password='test_pwd')


def test_sudo_cmd():
    code, output = con_ssh.exec_sudo_cmd(cmd='ifconfig')
    assert 'eth0' in output and 'TX bytes' in output


def test_sudo_su():
    with con_ssh.login_as_root() as root_ssh:
        code, output = root_ssh.exec_cmd('ifconfig')
        assert code == 0 and 'eth0' in output

    assert con_ssh.get_current_user() == 'wrsroot'


def test_cmd_timeout():
    LOG.tc_step("tc0")
    try:
        code, output = con_ssh.exec_cmd('ping -c 3 128.223.122.21')
        LOG.info("should not appear 0")
        LOG.info(code, output)
    except pexpect.TIMEOUT:
        LOG.info("tc0 passed")

    LOG.tc_step("tc1")
    try:
        with host_helper.ssh_to_host('compute-3'):
            LOG.info("should not appear 1")
    except exceptions.SSHException:
        LOG.info("tc1 passed")

    LOG.tc_step("tc2")
    try:
        with host_helper.ssh_to_host('128.223.122.21'):
            print("should not appear 2")
    except pexpect.TIMEOUT:
        print("tc2 passed")

    LOG.tc_step("tc3")
    with host_helper.ssh_to_host('compute-1'):
        LOG.info("yeah test passed.")