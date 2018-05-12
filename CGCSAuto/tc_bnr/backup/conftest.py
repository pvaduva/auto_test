
import pytest

import setups
from consts.auth import CliAuth, Tenant
from consts.proj_vars import ProjVar, BackupVars, InstallVars


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

    backup_dest = 'USB' if use_usb else 'local'
    setups.set_install_params(lab=lab_arg, skip_labsetup=None, resume=None, installconf_path=None,
                              controller0_ceph_mon_device=None, controller1_ceph_mon_device=None, ceph_mon_gib=None)
    BackupVars.set_backup_vars(backup_dest=backup_dest, backup_dest_path=backup_dest_path,
                               delete_backups=delete_backups, dest_labs=dest_labs)

    ProjVar.set_var(always_collect=True)


@pytest.fixture(scope='session', autouse=True)
def setup_test_session(global_setup):
    """
    Setup primary tenant  before the first test gets executed.
    TIS ssh was already set up at collecting phase.
    """

    ProjVar.set_var(PRIMARY_TENANT=Tenant.ADMIN)
    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.ADMIN)
    setups.setup_primary_tenant(ProjVar.get_var('PRIMARY_TENANT'))
    setups.set_env_vars(con_ssh)
    setups.copy_test_files()

    # set build id to be used to upload/write test results
    build_id, build_server, job = setups.get_build_info(con_ssh)
    ProjVar.set_var(BUILD_ID=build_id)
    ProjVar.set_var(BUILD_SERVER=build_server)
    ProjVar.set_var(JOB=job)
    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.ADMIN)

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
    CliAuth.set_vars(**setups.get_auth_via_openrc(con_ssh))
    Tenant.set_url(CliAuth.get_var('OS_AUTH_URL'))
    Tenant.set_region(CliAuth.get_var('OS_REGION_NAME'))


def pytest_runtest_teardown(item):

    con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
    # delete any backup files from /opt/backups to save disk space
    con_ssh.exec_sudo_cmd("rm -rf /opt/backups/*")
    con_ssh.flush()

