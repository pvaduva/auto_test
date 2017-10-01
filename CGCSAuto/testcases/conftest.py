import logging
import os
from time import strftime, gmtime

import pytest

import setup_consts
import setups
from consts.auth import CliAuth, Tenant
from consts.proj_vars import ProjVar
from utils.mongo_reporter.cgcs_mongo_reporter import collect_and_upload_results
from utils.tis_log import LOG
from utils import lab_info


natbox_ssh = None
con_ssh = None
initialized = False


@pytest.fixture(scope='session', autouse=True)
def setup_test_session():
    """
    Setup primary tenant and Nax Box ssh before the first test gets executed.
    TIS ssh was already set up at collecting phase.
    """
    os.makedirs(ProjVar.get_var('TEMP_DIR'), exist_ok=True)
    setups.setup_primary_tenant(ProjVar.get_var('PRIMARY_TENANT'))
    setups.set_env_vars(con_ssh)

    setups.copy_files_to_con1()

    global natbox_ssh
    natbox_ssh = setups.setup_natbox_ssh(ProjVar.get_var('KEYFILE_PATH'), ProjVar.get_var('NATBOX'), con_ssh=con_ssh)
    ProjVar.set_var(natbox_ssh=natbox_ssh)
    # setups.boot_vms(ProjVar.get_var('BOOT_VMS'))

    # set build id to be used to upload/write test results
    build_id, build_server = setups.get_build_info(con_ssh)
    ProjVar.set_var(BUILD_ID=build_id, BUILD_SERVER=build_server)

    setups.set_session(con_ssh=con_ssh)

    con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
    natbox_ssh.flush()
    natbox_ssh.connect(retry=False)


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
        Tenant._set_url(CliAuth.get_var('OS_AUTH_URL'))
        Tenant._set_region(CliAuth.get_var('OS_REGION_NAME'))
        initialized = True


def pytest_runtest_teardown(item):
    # print('')
    # message = 'Teardown started:'
    # testcase_log(message, item.nodeid, log_type='tc_teardown')
    con_ssh.flush()
    con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
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
