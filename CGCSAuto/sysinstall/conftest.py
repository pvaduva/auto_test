
import pytest


import setups
from consts.auth import CliAuth, Tenant
from consts.proj_vars import ProjVar, InstallVars
from utils.tis_log import LOG


con_ssh = None
has_fail = False


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
    # print('')
    # message = 'Teardown started:'
    # testcase_log(message, item.nodeid, log_type='tc_teardown')
    con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
    con_ssh.flush()


########################
# Command line options #
########################

def pytest_configure(config):

    # Lab install params
    lab_arg = config.getoption('lab')
    resume_install = config.getoption('resumeinstall')
    install_conf = config.getoption('installconf')
    skip_labsetup = config.getoption('skiplabsetup')

    setups.set_install_params(lab=lab_arg, skip_labsetup=skip_labsetup, resume=resume_install,
                              installconf_path=install_conf)


def pytest_unconfigure():

    tc_res_path = ProjVar.get_var('LOG_DIR') + '/test_results.log'

    with open(tc_res_path, mode='a') as f:
        f.write('\n\nLab: {}\n'
                'Build ID: {}\n'
                'Automation LOGs DIR: {}\n'.format(ProjVar.get_var('LAB_NAME'),
                                                   InstallVars.get_install_var('BUILD_ID'),
                                                   ProjVar.get_var('LOG_DIR')))

    LOG.info("Test Results saved to: {}".format(tc_res_path))
    with open(tc_res_path, 'r') as fin:
        print(fin.read())
