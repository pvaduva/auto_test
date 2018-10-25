import pexpect

from keywords import host_helper
from utils import exceptions, cli
from utils.clients.ssh import ssh_to_controller0, ControllerClient
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
    # LOG.tc_step("ping vm")
    # vm_id = vm_helper.boot_vm(name="utiltest")[1]
    # vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id, fail_ok=False)

    LOG.tc_step("tc1,1")
    try:
        code, output = con_ssh.exec_cmd('ping -c 3 128.223.122.21')
        LOG.info(code, output)
        assert(0, "should have thrown timeout exception")
    except pexpect.TIMEOUT:
        LOG.info("tc1 passed")

    LOG.tc_step("tc1.2")
    try:
        code, output = con_ssh.exec_cmd('ping -c 3 128.223.122.21')
        LOG.info(code, output)
        assert(0, "should have thrown timeout exception")
    except pexpect.TIMEOUT:
        LOG.info("tc1.2 passed")

    LOG.tc_step("tc2")
    try:
        with host_helper.ssh_to_host('compute-200'):
            assert (0, "should not appear 2")
    except exceptions.SSHException:
        LOG.info("tc2 passed")

    LOG.tc_step("tc3")
    try:
        with host_helper.ssh_to_host('128.223.122.21'):
            assert (0, "should not appear 3")
    except pexpect.TIMEOUT:
        print("tc3 passed")

    LOG.tc_step("tc4")
    with host_helper.ssh_to_host('compute-1'):
        LOG.info("yeah test passed.")


def test_cli_timeout():
    LOG.tc_step("event-list")
    cli.fm('event-list', fail_ok=True, timeout=3)

    LOG.tc_step("nova list")
    cli.nova('list', '--a', fail_ok=False)

    LOG.tc_step("cat log")
    # This fails because of the terminal display is slower than cat cmd. No easy solution so far.
    # This is an issue automation should fix anyways.
    # http://stackoverflow.com/questions/18607570/how-to-terminate-cat-command
    # http://unix.stackexchange.com/questions/176917/how-to-kill-a-runaway-cat
    con_ssh.exec_cmd('cat /var/log/sm-scheduler.log', expect_timeout=3)

    LOG.tc_step('nova list')
    cli.nova('list', '--a', fail_ok=False)
