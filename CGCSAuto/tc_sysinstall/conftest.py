import pytest

import setups
from consts.auth import CliAuth, Tenant
from consts.proj_vars import ProjVar, InstallVars
from utils.clients.ssh import SSHClient


#
#
# con_ssh = None
# has_fail = False
#
#
# @pytest.fixture(scope='function', autouse=True)
# def reconnect_before_test():
#     """
#     Before each test function start, Reconnect to TIS via ssh if disconnection is detected
#     """
#     con_ssh.flush()
#     con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
#
# def pytest_collectstart():
#     """
#     Set up the ssh session at collectstart. Because skipif condition is evaluated at the collecting test cases phase.
#     """
#     global con_ssh
#     con_ssh = setups.setup_tis_ssh(InstallVars.get_install_var("LAB"))
#     InstallVars.set_install_var(con_ssh=con_ssh)
#     CliAuth.set_vars(**setups.get_auth_via_openrc(con_ssh))
#     Tenant._set_url(CliAuth.get_var('OS_AUTH_URL'))
#     Tenant._set_region(CliAuth.get_var('OS_REGION_NAME'))
#
#
# def pytest_runtest_teardown(item):
#     # print('')
#     # message = 'Teardown started:'
#     # testcase_log(message, item.nodeid, log_type='tc_teardown')
#     con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
#     con_ssh.flush()


########################
# Command line options #
########################

def pytest_configure(config):

    # Lab install params
    lab_arg = config.getoption('lab')
    resume_install = config.getoption('resumeinstall')
    install_conf = config.getoption('installconf')
    skip_labsetup = config.getoption('skiplabsetup')
    controller0_ceph_mon_device = config.getoption('ceph_mon_dev_controller_0')
    controller1_ceph_mon_device = config.getoption('ceph_mon_dev_controller_1')
    ceph_mon_gib = config.getoption('ceph_mon_gib')
    setups.set_install_params(lab=lab_arg, skip_labsetup=skip_labsetup, resume=resume_install,
                              installconf_path=install_conf, controller0_ceph_mon_device=controller0_ceph_mon_device,
                              controller1_ceph_mon_device=controller1_ceph_mon_device, ceph_mon_gib=ceph_mon_gib)
    print(" Pre Configure Install vars: {}".format(InstallVars.get_install_vars()))
#
#
# def pytest_unconfigure():
#
#     tc_res_path = ProjVar.get_var('LOG_DIR') + '/test_results.log'
#
#     with open(tc_res_path, mode='a') as f:
#         f.write('\n\nLab: {}\n'
#                 'Build ID: {}\n'
#                 'Automation LOGs DIR: {}\n'.format(ProjVar.get_var('LAB_NAME'),
#                                                    InstallVars.get_install_var('BUILD_ID'),
#                                                    ProjVar.get_var('LOG_DIR')))
#
#     LOG.info("Test Results saved to: {}".format(tc_res_path))
#     with open(tc_res_path, 'r') as fin:
#         print(fin.read())


@pytest.fixture(scope='session', autouse=True)
def setup_test_session(global_setup):
    """
    Setup primary tenant and Nax Box ssh before the first test gets executed.
    TIS ssh was already set up at collecting phase.
    """
    print("SysInstall test session ..." )
    ProjVar.set_var(PRIMARY_TENANT=Tenant.get('admin'))
    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.get('admin'))
    setups.setup_primary_tenant(ProjVar.get_var('PRIMARY_TENANT'))
    setups.copy_test_files()

    global natbox_ssh
    natbox = ProjVar.get_var('NATBOX')
    if natbox['ip'] == 'localhost':
        natbox_ssh = 'localhost'
    else:
        natbox_ssh = setups.setup_natbox_ssh(ProjVar.get_var('KEYFILE_PATH'))
        setups.copy_keyfiles(nat_ssh=natbox_ssh, con_ssh=con_ssh)

    # set build id to be used to upload/write test results
    setups.get_build_info(con_ssh)
    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.get('admin'))

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
    Tenant.set_url(CliAuth.get_var('OS_AUTH_URL'))
    Tenant.set_region(CliAuth.get_var('OS_REGION_NAME'))


def pytest_runtest_teardown(item):
    # print('')
    # message = 'Teardown started:'
    # testcase_log(message, item.nodeid, log_type='tc_teardown')
    if not con_ssh._is_connected():
        con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
    con_ssh.flush()
