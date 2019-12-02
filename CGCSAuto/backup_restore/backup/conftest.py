import pytest

import setups

from consts.proj_vars import BackupVars
from consts.auth import CliAuth, Tenant
from consts.proj_vars import ProjVar, BackupVars, InstallVars
from consts.stx import BackupRestore

from utils.clients.ssh import ControllerClient, SSHClient

########################
# Command line options #
########################


def pytest_configure(config):

    # Params
    backup_dest_path = config.getoption('backup_path')

    BackupVars.set_backup_vars(backup_dest_path=backup_dest_path)


def pytest_collectstart():
    """
    Set up the ssh session at collectstart.
    """
    global con_ssh
    con_ssh = setups.setup_tis_ssh(InstallVars.get_install_var("LAB"))
    InstallVars.set_install_var(con_ssh=con_ssh)
    auth = setups.get_auth_via_openrc(con_ssh)
    if auth:
        CliAuth.set_vars(**setups.get_auth_via_openrc(con_ssh))

    Tenant.set_platform_url(CliAuth.get_var('OS_AUTH_URL'))
    Tenant.set_region(CliAuth.get_var('OS_REGION_NAME'))
