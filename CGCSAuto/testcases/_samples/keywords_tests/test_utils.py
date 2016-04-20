from pytest import mark

from keywords import host_helper
from utils.ssh import ssh_to_controller0, ControllerClient

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