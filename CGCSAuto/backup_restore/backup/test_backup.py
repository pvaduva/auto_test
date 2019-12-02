import os
import pexpect

from pytest import fixture, mark, skip

from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient

from keywords import common, host_helper, system_helper
from consts.filepaths import StxPath
from consts.proj_vars import BackupVars
from consts.stx import HostAvailState
from consts.auth import Tenant, HostLinuxUser
from setups import collect_tis_logs

BACKUP_PLAYBOOK = '/usr/share/ansible/stx-ansible/playbooks/backup.yml'
BACKUP_WAIT_TIMEOUT = 1500
STORE_BACKUP_PATH = None


def collect_logs(msg):
    """
    Collect logs on the current system

    Args:

    Returns:
    """
    active_controller = ControllerClient.get_active_controller()
    try:
        LOG.info('Collecting logs: ' + msg)
        collect_tis_logs(active_controller)
    except pexpect.exceptions.ExceptionPexpect:
        active_controller.flush()
        active_controller.exec_cmd('cat /etc/build.info')


def controller_precheck(controller):
    host = system_helper.get_active_controller_name()
    if controller == 'standby':
        controllers = system_helper.get_controllers(
            availability=(HostAvailState.AVAILABLE, HostAvailState.DEGRADED,
                          HostAvailState.ONLINE))
        controllers.remove(host)
        if not controllers:
            skip('Standby controller does not exist or not in good state')
        host = controllers[0]

    return host


def analyze_ansible_output(output):
    if output and len(output) > 0:
        lastlines = output.splitlines()[-2:]
        result_line = [line for line in lastlines if "PLAY RECAP" not in line]
        result_line = result_line[0] if len(result_line) > 0 else None
        LOG.info("Ansible result line = {}".format(result_line))
        if result_line and ":" in result_line:
            result = result_line.split(':')[1].split()
            failed = [i for i in result if "failed" in i]
            if failed:
                return int(failed[0].split('=')[1]), result
            return 1, result

    return 1, None


@fixture(scope='module')
def prepare_backup_env():
    global STORE_BACKUP_PATH
    STORE_BACKUP_PATH = BackupVars.get_backup_var('BACKUP_DEST_PATH')
    if not STORE_BACKUP_PATH:
        STORE_BACKUP_PATH = '/folk/cgts-pv/bnr'
    os.makedirs(STORE_BACKUP_PATH, exist_ok=True)


@mark.backup_platform
@mark.parametrize('controller', [
    'active'
])
def test_backup_platform(prepare_backup_env, controller):
    """
    Test ansible backup
    Args:
        prepare_backup_env: module fixture
        controller: test param

    Setups:
        - Create STORE_BACKUP_PATH dir on test server

    Test Steps:
        - ssh to given controller
        - ansible-playbook backup.yml
        - copy backup.tgz from active controller to test server
    """

    host = controller_precheck(controller)

    with host_helper.ssh_to_host(hostname=host) as con_ssh:
        cmd = "ansible-playbook {} -e ".format(BACKUP_PLAYBOOK) \
              + "\"ansible_become_pass=" + HostLinuxUser.get_password() + " " \
              + "admin_password=" + Tenant.get('admin_platform')['password'] \
              + "\""
        LOG.tc_step("Run " + cmd)

        collect_logs('before backup')
        rc, output = con_ssh.exec_cmd(cmd, expect_timeout=BACKUP_WAIT_TIMEOUT)
        collect_logs('after backup')

        assert rc == 0 and analyze_ansible_output(output)[0] == 0, \
            "{} execution failed: {} {}".format(cmd, rc, output)

        cmd = "ls -tr " + StxPath.BACKUPS + " | grep backup | tail -1"
        rc, backup_archive = con_ssh.exec_cmd(cmd)

        backup_src_path = os.path.join(StxPath.BACKUPS, backup_archive)
        backup_dest_path = os.path.join(STORE_BACKUP_PATH, backup_archive)
        LOG.tc_step("Copy from controller {} to test server {}"
                    .format(backup_src_path, backup_dest_path))
        common.scp_from_active_controller_to_test_server(
            os.path.join(StxPath.BACKUPS, backup_archive),
            backup_dest_path)
