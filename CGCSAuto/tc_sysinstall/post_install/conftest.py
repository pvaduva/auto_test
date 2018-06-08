import pytest

import setups
from consts.auth import CliAuth, Tenant
from consts.proj_vars import ProjVar, InstallVars
from utils.clients.ssh import SSHClient


@pytest.fixture(scope='session', autouse=True)
def setup_test_session(global_setup):
    """
    Setup primary tenant and Nax Box ssh before the first test gets executed.
    TIS ssh was already set up at collecting phase.
    """
    print("SysInstall test session ..." )
    ProjVar.set_var(PRIMARY_TENANT=Tenant.ADMIN)
    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.ADMIN)
    setups.setup_primary_tenant(ProjVar.get_var('PRIMARY_TENANT'))
    # con_ssh.set_prompt()
    setups.set_env_vars(con_ssh)
    setups.copy_test_files()
    # con_ssh.set_prompt()

    global natbox_ssh
    natbox = ProjVar.get_var('NATBOX')
    if natbox['ip'] == 'localhost':
        natbox_ssh = 'localhost'
    else:
        natbox_ssh = setups.setup_natbox_ssh(ProjVar.get_var('KEYFILE_PATH'), natbox, con_ssh=con_ssh)
    # setups.boot_vms(ProjVar.get_var('BOOT_VMS'))

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
    print("SysInstall test reconnect before test ..." )
    con_ssh.flush()
    con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
    if natbox_ssh and isinstance(natbox_ssh, SSHClient):
        natbox_ssh.flush()
        natbox_ssh.connect(retry=False)


def pytest_collectstart():
    """
    Set up the ssh session at collectstart. Because skipif condition is evaluated at the collecting test cases phase.
    """
    print("SysInstall collectstart ..." )
    global con_ssh
    lab = ProjVar.get_var("LAB")
    if 'vbox' in  lab['short_name']:
        con_ssh = setups.setup_vbox_tis_ssh(lab)
    else:
        con_ssh = setups.setup_tis_ssh(lab)
    ProjVar.set_var(con_ssh=con_ssh)
    CliAuth.set_vars(**setups.get_auth_via_openrc(con_ssh))
    # if setups.is_https(con_ssh):
    #     CliAuth.set_vars(HTTPS=True)
    Tenant.ADMIN['auth_url'] = CliAuth.get_var('OS_AUTH_URL')
    Tenant.ADMIN['region'] = CliAuth.get_var('OS_REGION_NAME')


def pytest_runtest_teardown(item):
    # print('')
    # message = 'Teardown started:'
    # testcase_log(message, item.nodeid, log_type='tc_teardown')
    if not con_ssh._is_connected():
        con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
    con_ssh.flush()
