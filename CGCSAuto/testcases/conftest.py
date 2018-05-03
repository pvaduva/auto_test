import os

import pytest
from threading import Event

import setups
from consts.auth import CliAuth, Tenant
from consts.proj_vars import ProjVar
from consts.cgcs import REGION_MAP


natbox_ssh = None
con_ssh = None
initialized = False


@pytest.fixture(scope='session', autouse=True)
def setup_test_session(global_setup):
    """
    Setup primary tenant and Nax Box ssh before the first test gets executed.
    TIS ssh was already set up at collecting phase.
    """
    setups.setup_primary_tenant(ProjVar.get_var('PRIMARY_TENANT'))
    setups.set_env_vars(con_ssh)

    setups.copy_files_to_con1()

    global natbox_ssh
    try:
        natbox_ssh = setups.setup_natbox_ssh(ProjVar.get_var('KEYFILE_PATH'), ProjVar.get_var('NATBOX'),
                                             con_ssh=con_ssh)
    except:
        if ProjVar.get_var('COLLECT_SYS_NET_INFO'):
            setups.collect_sys_net_info(lab=ProjVar.get_var('LAB'))
        raise
    # setups.boot_vms(ProjVar.get_var('BOOT_VMS'))

    # set build id to be used to upload/write test results
    build_id, build_server, job = setups.get_build_info(con_ssh)
    ProjVar.set_var(BUILD_ID=build_id, BUILD_SERVER=build_server, JOB=job)

    if ProjVar.get_var('KEYSTONE_DEBUG'):
        setups.enable_disable_keystone_debug(enable=True, con_ssh=con_ssh)

    setups.set_session(con_ssh=con_ssh)

    con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
    natbox_ssh.flush()
    natbox_ssh.connect(retry=True)

    if ProjVar.get_var('COLLECT_TELNET'):
        end_event = Event()
        threads = setups.collect_telnet_logs_for_nodes(end_event=end_event)
        ProjVar.set_var(TELNET_THREADS=(threads, end_event))

    setups.set_sys_type(con_ssh=con_ssh)


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
        Tenant.set_url(CliAuth.get_var('OS_AUTH_URL'))
        setups.set_region(region=None)
        initialized = True


def pytest_runtest_teardown(item):
    # print('')
    # message = 'Teardown started:'
    # testcase_log(message, item.nodeid, log_type='tc_teardown')
    if con_ssh:
        con_ssh.flush()
        con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
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
