from threading import Event

import pytest

import setups
from consts.auth import CliAuth, Tenant
from consts.filepaths import WRSROOT_HOME
from consts.proj_vars import ProjVar
from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient

natbox_ssh = None
initialized = False


@pytest.fixture(scope='session', autouse=True)
def setup_test_session(global_setup, request):
    """
    Setup primary tenant and Nax Box ssh before the first test gets executed.
    TIS ssh was already set up at collecting phase.
    """
    LOG.fixture_step("(session) Setting up test session...")
    setups.setup_primary_tenant(ProjVar.get_var('PRIMARY_TENANT'))

    # set up natbox connection and copy keyfile
    global natbox_ssh
    try:
        natbox_ssh = setups.setup_natbox_ssh(ProjVar.get_var('NATBOX'))
    except:
        if ProjVar.get_var('COLLECT_SYS_NET_INFO'):
            setups.collect_sys_net_info(lab=ProjVar.get_var('LAB'))
        raise
    # setups.boot_vms(ProjVar.get_var('BOOT_VMS'))

    con_ssh = ControllerClient.get_active_controller()
    # set build id to be used to upload/write test results
    setups.set_build_info(con_ssh)

    # Enable keystone debug
    if ProjVar.get_var('KEYSTONE_DEBUG'):
        setups.enable_disable_keystone_debug(enable=True, con_ssh=con_ssh)

    # Set global vars
    setups.set_session(con_ssh=con_ssh)

    # Ensure tis and natbox still connected
    con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
    natbox_ssh.flush()
    natbox_ssh.connect(retry=True)
    # copy private key to natbox and public key to localhost (if remote cli)
    setups.setup_keypair(nat_ssh=natbox_ssh, con_ssh=con_ssh)

    # collect telnet logs for all hosts
    if ProjVar.get_var('COLLECT_TELNET'):
        end_event = Event()
        threads = setups.collect_telnet_logs_for_nodes(end_event=end_event)
        ProjVar.set_var(TELNET_THREADS=(threads, end_event))

    # set global var for sys_type
    setups.set_sys_type(con_ssh=con_ssh)

    # rsync files between controllers
    setups.copy_test_files()

    # set up remote cli clients
    client = con_ssh
    if ProjVar.get_var('REMOTE_CLI'):
        LOG.fixture_step("(session) Install remote cli clients in virtualenv")
        client = setups.setup_remote_cli_client()
        ProjVar.set_var(USER_FILE_DIR=ProjVar.get_var('TEMP_DIR'))

        def remove_remote_cli():
            LOG.fixture_step("(session) Remove remote cli clients")
            client.exec_cmd('rm -rf {}/*'.format(ProjVar.get_var('TEMP_DIR')))
            client.close()
            from utils.clients.local import RemoteCLIClient
            RemoteCLIClient.remove_remote_cli_clients()
            ProjVar.set_var(REMOTE_CLI=None)
            ProjVar.set_var(USER_FILE_DIR=WRSROOT_HOME)
        request.addfinalizer(remove_remote_cli)


def pytest_collectstart():
    """
    Set up the ssh session at collectstart. Because skipif condition is evaluated at the collecting test cases phase.
    """
    global initialized
    if not initialized:
        global con_ssh
        con_ssh = setups.setup_tis_ssh(ProjVar.get_var("LAB"))
        ProjVar.set_var(con_ssh=con_ssh)
        CliAuth.set_vars(**setups.get_auth_via_openrc(con_ssh))
        if setups.is_https(con_ssh):
            CliAuth.set_vars(HTTPS=True)

        auth_url = CliAuth.get_var('OS_AUTH_URL')
        Tenant.set_url(auth_url)
        setups.set_region(region=None)
        if ProjVar.get_var('IS_DC'):
            Tenant.set_url(url=auth_url, central_region=True)
        initialized = True


def pytest_runtest_teardown(item):
    # print('')
    # message = 'Teardown started:'
    # testcase_log(message, item.nodeid, log_type='tc_teardown')
    for con_ssh_ in ControllerClient.get_active_controllers(current_thread_only=True):
        con_ssh_.flush()
        con_ssh_.connect(retry=True, retry_interval=3, retry_timeout=300)
    if natbox_ssh:
        natbox_ssh.flush()
        natbox_ssh.connect(retry=False)

#
# def pytest_unconfigure():
#
#     tc_res_path = ProjVar.get_var('LOG_DIR') + '/test_results.log'
#     build_id = setups.get_build_id(con_ssh)
#
#     with open(tc_res_path, mode='a') as f:
#         f.write('\n\nLab: {}\n'
#                 'Build ID:{}\n'
#                 'Automation LOGs DIR: {}\n'.format(ProjVar.get_var('LAB_NAME'), build_id, ProjVar.get_var('LOG_DIR')))
#
#     LOG.info("Test Results saved to: {}".format(tc_res_path))
#     with open(tc_res_path, 'r') as fin:
#         print(fin.read())
