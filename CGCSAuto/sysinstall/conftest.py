
import pytest


import setups
from consts.auth import CliAuth, Tenant
from consts.proj_vars import ProjVar, InstallVars
from utils.tis_log import LOG
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

def pytest_addoption(parser):

    ceph_mon_device_controller0_help = "The disk device to use for ceph monitor in controller-0. " \
                                       "eg /dev/sdb or /dev/sdc"
    ceph_mon_device_controller1_help = "The disk device to use for ceph monitor in controller-1." \
                                       " eg /dev/sdb or /dev/sdc"
    ceph_mon_gib_help = "The size of the partition to allocate on a controller disk for the Ceph monitor logical " \
                        "volume, in GiB (the default value is 20)"

    parser.addoption('--ceph-mon-dev-controller-0', '--ceph_mon_dev_controller-0',  dest='ceph_mon_dev_controller_0',
                     action='store', metavar='DISK_DEVICE',  help=ceph_mon_device_controller0_help)
    parser.addoption('--ceph-mon-dev-controller-1', '--ceph_mon_dev_controller-1',  dest='ceph_mon_dev_controller_1',
                     action='store', metavar='DISK_DEVICE',  help=ceph_mon_device_controller1_help)
    parser.addoption('--ceph-mon-gib', '--ceph_mon_dev_gib',  dest='ceph_mon_gib',
                     action='store', metavar='SIZE',  help=ceph_mon_gib_help)

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
def setup_test_session():
    """
    Setup primary tenant and Nax Box ssh before the first test gets executed.
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

    global natbox_ssh
    natbox_ssh = setups.setup_natbox_ssh(ProjVar.get_var('KEYFILE_PATH'), ProjVar.get_var('NATBOX'), con_ssh=con_ssh)
    ProjVar.set_var(natbox_ssh=natbox_ssh)
    # setups.boot_vms(ProjVar.get_var('BOOT_VMS'))

    # set build id to be used to upload/write test results
    build_id, build_host = setups.get_build_info(con_ssh)
    ProjVar.set_var(BUILD_ID=build_id)
    ProjVar.set_var(BUILD_HOST=build_host)
    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.ADMIN)


@pytest.fixture(scope='function', autouse=True)
def reconnect_before_test():
    """
    Before each test function start, Reconnect to TIS via ssh if disconnection is detected
    """
    con_ssh.flush()
    con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
    natbox_ssh.flush()
    natbox_ssh.connect(retry=False)


def pytest_collectstart():
    """
    Set up the ssh session at collectstart. Because skipif condition is evaluated at the collecting test cases phase.
    """
    global con_ssh
    con_ssh = setups.setup_tis_ssh(ProjVar.get_var("LAB"))
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
    con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
    con_ssh.flush()
