import os

import pytest

import setups
from consts.proj_vars import InstallVars, RestoreVars
from consts.cgcs import BackupRestore
from consts.filepaths import BuildServerPath
from keywords import vlm_helper
from testfixtures.pre_checks_and_configs import *
from utils import node


########################
# Command line options #
########################

def pytest_configure(config):
    # Lab install params
    lab = config.getoption('lab')
    use_usb = config.getoption('use_usb')
    backup_src_path = config.getoption('backup_path')
    backup_build_id = config.getoption('backup_build_id')
    backup_src = 'usb' if use_usb else 'local'
    skip_setup_feed = config.getoption('skip_setup_feed')
    skip_reinstall = config.getoption('skip_reinstall')
    low_latency = config.getoption('low_latency')
    cinder_backup = config.getoption('cinder_backup')
    # build_server = config.getoption('build_server')

    backup_builds_dir = config.getoption('backup_builds_dir')
    build_server = config.getoption('build_server')
    # tis_build_dir = config.getoption('tis_build_dir')

    setups.set_install_params(lab=lab, skip='feed' if skip_setup_feed else None, resume=None, installconf_path=None,
                              drop=None, boot='usb' if use_usb else 'feed', controller0_ceph_mon_device=None,
                              iso_path=None, controller1_ceph_mon_device=None, ceph_mon_gib=None,
                              low_latency=low_latency, security='standard',
                              stop=None, wipedisk=False, ovs=False, patch_dir=None, boot_server=None)

    if backup_src == 'usb':
        if (not backup_src_path) or (BackupRestore.USB_MOUNT_POINT not in backup_src_path):
            backup_src_path = BackupRestore.USB_BACKUP_PATH
    elif not backup_src_path:
        backup_src_path = BackupRestore.LOCAL_BACKUP_PATH

    if not backup_builds_dir:
        backup_builds_dir = os.path.basename(BuildServerPath.DEFAULT_HOST_BUILDS_DIR)

    RestoreVars.set_restore_vars(backup_src=backup_src, backup_src_path=backup_src_path, build_server=build_server,
                                 backup_build_id=backup_build_id,  backup_builds_dir=backup_builds_dir)

    reinstall_storage = config.getoption('reinstall_storage')
    RestoreVars.set_restore_var(reinstall_storage=reinstall_storage)

    RestoreVars.set_restore_var(skip_setup_feed=skip_setup_feed)
    RestoreVars.set_restore_var(skip_reinstall=skip_reinstall)
    RestoreVars.set_restore_var(low_latency=low_latency)
    RestoreVars.set_restore_var(cinder_backup=cinder_backup)

    ProjVar.set_var(always_collect=True)
    ProjVar.set_var(SOURCE_OPENRC=True)


def pytest_runtest_teardown():
    lab = InstallVars.get_install_var('LAB')
    hostnames = [k for k, v in lab.items() if isinstance(v, node.Node)]
    vlm_helper.unreserve_hosts(hostnames)
    con_ssh = ControllerClient.get_active_controller()
    # Delete any backup files from /opt/backups
    con_ssh.exec_sudo_cmd("rm -rf /opt/backups/*")
    con_ssh.flush()


@pytest.fixture(scope='session', autouse=True)
def setup_test_session(global_setup, request):
    """
    Setup primary tenant  before the first test gets executed.
    TIS ssh was already set up at collecting phase.
    """
    ProjVar.set_var(PRIMARY_TENANT='admin')
    ProjVar.set_var(SOURCE_OPENRC=True)
    setups.setup_primary_tenant('admin')

    con_ssh = setups.setup_tis_ssh(InstallVars.get_install_var("LAB"))
    ControllerClient.set_active_controller(ssh_client=con_ssh)

    # set build id to be used to upload/write test results
    setups.set_session(con_ssh=con_ssh)

    def set_build_vars():
        try:
            setups.copy_test_files()

            # set build id to be used to upload/write test results
            setups.set_build_info(con_ssh)
        except:
            LOG.warning('Unable to set BUILD info')
            pass

    set_build_vars()
    request.addfinalizer(set_build_vars)
