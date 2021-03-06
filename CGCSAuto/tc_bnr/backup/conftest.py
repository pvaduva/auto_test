
import pytest

import setups
from consts.auth import CliAuth, Tenant
from consts.proj_vars import ProjVar, BackupVars, InstallVars
from consts.stx import BackupRestore


########################
# Command line options #
########################


def pytest_configure(config):

    # Lab install params
    lab_arg = config.getoption('lab')
    use_usb = config.getoption('use_usb')
    backup_dest_path = config.getoption('backup_path')
    delete_backups = not config.getoption('keep_backups')
    dest_labs = config.getoption('dest_labs')
    cinder_backup = config.getoption('cinder_backup')
    reinstall_storage = config.getoption('reinstall_storage')
    BackupVars.set_backup_vars(reinstall_storage=reinstall_storage)

    backup_dest = 'usb' if use_usb else 'local'
    setups.set_install_params(lab=lab_arg, skip=None, resume=None, installconf_path=None,
                              drop=None, boot='usb' if use_usb else 'feed', controller0_ceph_mon_device=None, iso_path=None,
                              controller1_ceph_mon_device=None, ceph_mon_gib=None,low_latency=False, security='standard',
                              stop=None, wipedisk=False, ovs=False, patch_dir=None, boot_server=None)

    if backup_dest == 'usb':
        if not backup_dest_path or BackupRestore.USB_MOUNT_POINT not in backup_dest_path:
            backup_dest_path = BackupRestore.USB_BACKUP_PATH
    elif not backup_dest_path:
        backup_dest_path = BackupRestore.LOCAL_BACKUP_PATH
    BackupVars.set_backup_vars(backup_dest=backup_dest, backup_dest_path=backup_dest_path,
                               delete_backups=delete_backups, dest_labs=dest_labs, cinder_backup=cinder_backup)

    ProjVar.set_var(always_collect=True)


@pytest.fixture(scope='session', autouse=True)
def setup_test_session(global_setup):
    """
    Setup primary tenant  before the first test gets executed.
    TIS ssh was already set up at collecting phase.
    """

    ProjVar.set_var(PRIMARY_TENANT=Tenant.get('admin'))
    ProjVar.set_var(SOURCE_OPENRC=True)
    setups.setup_primary_tenant(ProjVar.get_var('PRIMARY_TENANT'))
    setups.copy_test_files()

    # set build id to be used to upload/write test results
    setups.set_build_info(con_ssh)
    setups.set_session(con_ssh=con_ssh)


@pytest.fixture(scope='function', autouse=True)
def reconnect_before_test():
    """
    Before each test function start, Reconnect to TIS via ssh if disconnection is detected
    """
    con_ssh.flush()
    con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)


def pytest_collectstart():
    """
    Set up the ssh session at collectstart. Because skipif condition is evaluated at the collecting test cases phase.
    """
    global con_ssh
    con_ssh = setups.setup_tis_ssh(InstallVars.get_install_var("LAB"))
    InstallVars.set_install_var(con_ssh=con_ssh)
    auth = setups.get_auth_via_openrc(con_ssh)
    if auth:
        CliAuth.set_vars(**setups.get_auth_via_openrc(con_ssh))

    Tenant.set_platform_url(CliAuth.get_var('OS_AUTH_URL'))
    Tenant.set_region(CliAuth.get_var('OS_REGION_NAME'))


def pytest_runtest_teardown(item):

    con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
    # delete any backup files from /opt/backups to save disk space
    con_ssh.exec_sudo_cmd("rm -rf /opt/backups/*")
    con_ssh.flush()

