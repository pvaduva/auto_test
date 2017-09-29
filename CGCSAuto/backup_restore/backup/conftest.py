
import pytest


import setups
from consts.auth import CliAuth, Tenant
from consts.proj_vars import ProjVar, BackupVars, InstallVars


########################
# Command line options #
########################

def pytest_addoption(parser):

    backup_destination_help = "The destination to scp the backupfiles. Choices are usb ( 16G USB  or above must be " \
                              "plugged to controller-0) or Test server. Default is usb"

    delete_backups = "Whether to delete the backupfiles from controller-0:/opt/backups after transfer " \
                     "to the specified destination. Default is True."

    parser.addoption('--backup-dest', '--backup_dest',  dest='backup_dest',
                     action='store', default='usb',  help=backup_destination_help)
    parser.addoption('--delete-backups', '--delete_backups',  dest='delete_backups',
                     action='store', default=True,  help=delete_backups)


def pytest_configure(config):

    # Lab install params
    lab_arg = config.getoption('lab')
    backup_dest = config.getoption('backup_dest')
    delete_backups = config.getoption('delete_backups')
    setups.set_install_params(lab=lab_arg, skip_labsetup=None, resume=None, installconf_path=None,
                              controller0_ceph_mon_device=None, controller1_ceph_mon_device=None, ceph_mon_gib=None)
    BackupVars.set_backup_vars(backup_dest=backup_dest, delete_backups=delete_backups)


@pytest.fixture(scope='session', autouse=True)
def setup_test_session():
    """
    Setup primary tenant  before the first test gets executed.
    TIS ssh was already set up at collecting phase.
    """
    # os.makedirs(ProjVar.get_var('TEMP_DIR'), exist_ok=True)
    ProjVar.set_var(PRIMARY_TENANT=Tenant.ADMIN)
    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.ADMIN)
    setups.setup_primary_tenant(ProjVar.get_var('PRIMARY_TENANT'))
    con_ssh.set_prompt()
    setups.set_env_vars(con_ssh)
    setups.copy_files_to_con1()
    con_ssh.set_prompt()

    # set build id to be used to upload/write test results
    build_id, build_server = setups.get_build_info(con_ssh)
    ProjVar.set_var(BUILD_ID=build_id)
    ProjVar.set_var(BUILD_SERVER=build_server)
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
    Tenant._set_url(CliAuth.get_var('OS_AUTH_URL'))
    Tenant._set_region(CliAuth.get_var('OS_REGION_NAME'))


def pytest_runtest_teardown(item):

    con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
    # delete any backup files from /opt/backups to save disk space
    con_ssh.exec_sudo_cmd("rm -rf /opt/backups/*")
    con_ssh.flush()

