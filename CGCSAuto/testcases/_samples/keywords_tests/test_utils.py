from pytest import mark

from keywords import host_helper
from utils.ssh import ssh_to_controller0, ControllerClient


def test_scp_files():
    con_ssh = ssh_to_controller0()
    con_ssh.scp_files_to_local_host('/home/wrsroot/instances/*', dest_password='test_pwd')

    host_helper.swact_host()
    con_ssh = ssh_to_controller0()
    con_ssh.scp_files_to_local_host('/home/wrsroot/instances/*', dest_password='test_pwd')