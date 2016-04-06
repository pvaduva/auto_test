import time
import pytest

from pexpect import pxssh
from pytest import fail

from utils import ssh
from utils.ssh import SSHClient
from utils.ssh import SSHFromSSH
from utils.tis_log import LOG

username = 'wrsroot'
password = 'li69nux'
# hostname = '10.10.10.3'
hostname = '128.224.150.73'
# hostname = 'yow-cgcs-ironpass-1.wrs.com'


def setup():
    global ssh_client
    ssh_client = SSHClient(host=hostname, user=username, password=password)
    ssh_client.connect()
    ssh_client.send("source /etc/nova/openrc")
    ssh_client.prompt = ssh.ADMIN_PROMPT
    ssh_client.expect()


def test_reconnect_after_swact():
    LOG.tc_start()
    setup()
    # TODO: dynamically determine active controller
    ssh_client.exec_cmd("system host-swact controller-0")
    time.sleep(10) # wait for ssh_client disconnect due to swact
    ssh_client.connect(timeout=3, retry=True, prompt=ssh.CONTROLLER_PROMPT)
    ssh_client.send("date")
    ssh_client.expect()
    assert ssh_client._is_connected()
    LOG.tc_end()


def test_credential_incorrect():
    LOG.tc_start()
    ssh_client1 = SSHClient(host=hostname, user='wrsroot', password='imwrong69')
    try:
        ssh_client1.connect(retry=True)
        fail("Test failed, how can connect pass??")
    except pxssh.ExceptionPxssh as e:
        assert "permission denied" in e.__str__()
        LOG.tc_end()


def test_connection_close():
    LOG.tc_start()
    setup()
    ssh_client.close()
    try:
        ssh_client.send('echo "hello \nworld2"')
        fail("Connection closed already, shouldn't be able to send cmd!")
    except:
        LOG.tc_end("hello world throwed exception.")


def test_send_cmd():
    LOG.tc_start()
    ssh_client.connect()
    ssh_client.send('/sbin/ip route')
    ssh_client.expect('default')
    ssh_client.expect('eth1')
    ssh_client.flush()
    output = ssh_client.exec_cmd('date')
    assert 'eth' not in output
    ssh_client.send(r'source /etc/nova/openrc')
    ssh_client.set_prompt('.*keystone_admin.*')
    ssh_client.expect()
    exit_code, output = ssh_client.exec_cmd('system host-list')
    assert exit_code == 0
    LOG.tc_end()


def test_config_fixture(tis_ssh):
    LOG.info('tis_ssh:     {}'.format(tis_ssh))
    tis_ssh.send('/sbin/ip route')
    tis_ssh.expect('default')
    tis_ssh.expect()


def test_ssh_from_ssh():
    LOG.tc_start()
    ssh_client.connect()
    compute_ssh = SSHFromSSH(ssh_client, 'compute-0', 'wrsroot', 'li69nux')
    compute_ssh.connect()
    exit_code, output = compute_ssh.exec_cmd('date1')
    assert exit_code == 127
    assert 'command not found' in output
    compute_ssh.close()
    assert not compute_ssh._is_connected()
    assert ssh_client._is_connected()
    LOG.tc_end()


def test_expect_list():
    LOG.tc_start()
    ssh_client.connect()
    ssh_client.send(r'source /etc/nova/openrc')
    ssh_client.expect('.*keystone_admin.*')
    ssh_client.set_prompt('.*keystone_admin.*')
    ssh_client.send(r'system host-list', flush=True)
    ssh_client.expect([r'compute\-0', r'controller\-1'])
    ssh_client.expect([r'compute\-0', r'compute\-1'])
    ssh_client.flush()
    LOG.tc_end()

if __name__ == "__main__":
    test_reconnect_after_swact()
    test_credential_incorrect()
    test_connection_close()
    test_send_cmd()
    test_expect_list()
    test_ssh_from_ssh()