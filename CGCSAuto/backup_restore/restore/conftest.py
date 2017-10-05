
import pytest

import setups
from consts.proj_vars import InstallVars, ProjVar, RestoreVars
from keywords import vlm_helper
from utils.ssh import ControllerClient
from utils import node

# Import test fixtures that are applicable to upgrade test
from testfixtures.pre_checks_and_configs import *


########################
# Command line options #
########################

def pytest_addoption(parser):

    backup_src_path_help = "The path to  backup files in the backup source, if source is not a USB. If source is USB," \
                           " by default, the backup files are found at the mount point: /media/wrsroot/backups. " \
                           " For local (Test Server) the default is /sandbox/backups."

    parser.addoption('--backup-src', '--backup_src',  dest='backup_src', action='store', default='USB',
                     help="Where to get the bakcup files: choices are 'usb' and 'local'")
    parser.addoption('--backup-src-path', '--backup_src_path',  dest='backup_src_path',
                     action='store', metavar='DIR', help=backup_src_path_help)

    parser.addoption('--backup-build-id', '--backup_build-id',  dest='backup_build_id',
                     action='store',  help="The build id of the backup")
    parser.addoption('--backup-builds-dir', '--backup_builds-dir',  dest='backup_builds_dir',
                     action='store',  help="The Titanium builds dir where the backup build id belong. "
                                           "Such as CGCS_5.0_Host or TC_17.06_Host")


def pytest_configure(config):
    # Lab install params
    lab_arg = config.getoption('lab')
    backup_src = config.getoption('backup_src')
    backup_src_path = config.getoption('backup_src_path')
    backup_build_id = config.getoption('backup_build_id')
    backup_builds_dir = config.getoption('backup_builds_dir')
    setups.set_install_params(lab=lab_arg, skip_labsetup=None, resume=None, installconf_path=None,
                              controller0_ceph_mon_device=None, controller1_ceph_mon_device=None, ceph_mon_gib=None)
    RestoreVars.set_restore_vars(backup_src=backup_src, backup_src_path=backup_src_path,
                                 backup_build_id=backup_build_id,  backup_builds_dir=backup_builds_dir)


@pytest.fixture(scope='session', autouse=True)
def setup_test_session():
    """

    """
    LOG.tc_func_start("RESTORE_TEST")


def pytest_collectstart():
    """
    Set up the ssh session at collectstart. Because skipif condition is evaluated at the collecting test cases phase.
    """
    global con_ssh
    lab = ProjVar.get_var("LAB")
    lab_name = lab['name']
    con_ssh = None


def pytest_runtest_teardown(item):
    lab = InstallVars.get_install_var('LAB')
    hostnames = [ k for k, v in lab.items() if isinstance(v, node.Node)]
    vlm_helper.unreserve_hosts(hostnames)
    con_ssh = ControllerClient.get_active_controller(lab['short_name'])
    # Delete any backup files from /opt/backups
    con_ssh.exec_sudo_cmd("rm -rf /opt/backups/*")
    con_ssh.flush()


