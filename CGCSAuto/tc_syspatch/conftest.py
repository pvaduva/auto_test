import pytest
import setups
from consts.auth import CliAuth, Tenant
from consts import build_server as build_server_consts
from consts.proj_vars import PatchingVars
from consts.proj_vars import ProjVar
from utils.clients.ssh import SSHClient


def pytest_configure(config):
    patch_build_server = config.getoption('patch_build_server')
    patch_dir = config.getoption('patch_dir')
    controller_apply_strategy = config.getoption('controller_strategy')
    storage_apply_strategy = config.getoption('storage_strategy')
    compute_apply_strategy = config.getoption('compute_strategy')
    max_parallel_computes = config.getoption('max_parallel_computes')
    if not max_parallel_computes:
        max_parallel_computes = 2
    instance_action = config.getoption('instance_action')
    alarm_restrictions = config.getoption('alarm_restrictions')

    if not patch_build_server:
        patch_build_server = build_server_consts.DEFAULT_BUILD_SERVER['name']

    PatchingVars.set_patching_var(patch_dir=patch_dir,
                                  patch_build_server=patch_build_server,
                                  controller_apply_strategy=controller_apply_strategy,
                                  storage_apply_strategy=storage_apply_strategy,
                                  compute_apply_strategy=compute_apply_strategy,
                                  max_parallel_computes=max_parallel_computes,
                                  instance_action=instance_action,
                                  alarm_restrictions=alarm_restrictions)


@pytest.fixture(scope='session', autouse=True)
def setup_test_session():
    """
    Setup primary tenant and Nax Box ssh before the first test gets executed.
    TIS ssh was already set up at collecting phase
    Args:

    Returns:

    """
    print("Syspatch test session ...")
    ProjVar.set_var(PRIMARY_TENANT=Tenant.get('admin'))
    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.ADMIN)
    setups.setup_primary_tenant(ProjVar.get_var('PRIMARY_TENANT'))
    setups.copy_test_files()

    global natbox_ssh
    natbox = ProjVar.get_var('NATBOX')
    if natbox['ip'] == 'localhost':
        natbox_ssh = 'localhost'
    else:
        natbox_ssh = setups.setup_natbox_ssh(ProjVar.get_var('KEYFILE_PATH'), natbox, con_ssh=con_ssh)

    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.ADMIN)
    setups.set_session(con_ssh=con_ssh)


@pytest.fixture(scope='function', autouse=True)
def reconnect_before_test():
    """
    Before each test function start, Reconnect to TIS via ssh if disconnection is detected
    """
    print("Sys-patch test reconnect before test ...")
    con_ssh.flush()
    con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
    if natbox_ssh and isinstance(natbox_ssh, SSHClient):
        natbox_ssh.flush()
        natbox_ssh.connect(retry=False)


def pytest_collectstart():
    """
    Set up the ssh session at collectstart. Because skipif condition is evaluated at the collecting test cases phase.
    """
    print("Sys-patch collectstart ...")
    global con_ssh
    lab = ProjVar.get_var("LAB")
    if 'vbox' in lab['short_name']:
        con_ssh = setups.setup_vbox_tis_ssh(lab)
    else:
        con_ssh = setups.setup_tis_ssh(lab)
    ProjVar.set_var(con_ssh=con_ssh)
    CliAuth.set_vars(**setups.get_auth_via_openrc(con_ssh))
    Tenant.set_url(CliAuth.get_var('OS_AUTH_URL'))
    Tenant.set_region(CliAuth.get_var('OS_REGION_NAME'))


def pytest_runtest_teardown():

    if not con_ssh._is_connected():
        con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
    con_ssh.flush()
