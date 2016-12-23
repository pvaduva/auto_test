# import pytest
#
# import setups
from consts import build_server as build_server_consts
# from consts.auth import CliAuth, Tenant
from consts.proj_vars import ProjVar, PatchingVars
# from keywords import system_helper
# from utils import table_parser, cli
# from utils.tis_log import LOG

# natbox_ssh = None
# con_ssh = None


def pytest_addoption(parser):
    patch_build_server_help = "TiS Patch build server host name where the upgrade release software is downloaded from." \
                        " ( default: {})".format(build_server_consts.DEFAULT_BUILD_SERVER['name'])
    patch_dir_help = "Directory on the Build Server where the patch files located"

    parser.addoption('--patch-build-server', '--patch_build_server',  dest='patch_build_server',
                     action='store', metavar='SERVER', default=build_server_consts.DEFAULT_BUILD_SERVER['name'],
                     help=patch_build_server_help)
    parser.addoption('--patch-dir', '--patch_dir',  dest='patch_dir', default=None,
                     action='store', metavar='DIR',  help=patch_dir_help)


def pytest_configure(config):
    patch_build_server = config.getoption('patch_build_server')
    patch_dir = config.getoption('patch_dir')

    if patch_dir is not None:
        PatchingVars.set_patching_var(patch_build_server=patch_build_server,
                                      patch_dir=patch_dir)

#
# @pytest.fixture(scope='session', autouse=True)
# def setup_test_session():
#     """
#     Setup primary tenant and Nax Box ssh before the first test gets executed.
#     TIS ssh was already set up at collecting phase.
#     """
#     # os.makedirs(ProjVar.get_var('TEMP_DIR'), exist_ok=True)
#     ProjVar.set_var(PRIMARY_TENANT=Tenant.ADMIN)
#     setups.setup_primary_tenant(ProjVar.get_var('PRIMARY_TENANT'))
#     con_ssh.set_prompt()
#     setups.set_env_vars(con_ssh)
#
#     setups.copy_files_to_con1()
#
#     global natbox_ssh
#     natbox_ssh = setups.setup_natbox_ssh(ProjVar.get_var('KEYFILE_PATH'), ProjVar.get_var('NATBOX'))
#     ProjVar.set_var(natbox_ssh=natbox_ssh)
#     # setups.boot_vms(ProjVar.get_var('BOOT_VMS'))
#
#     # set build id to be used to upload/write test results
#     build_id = setups.get_build_id(con_ssh)
#     ProjVar.set_var(BUILD_ID=build_id)
#
#
# @pytest.fixture(scope='function', autouse=True)
# def reconnect_before_test():
#     """
#     Before each test function start, Reconnect to TIS via ssh if disconnection is detected
#     """
#     con_ssh.flush()
#     con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
#     natbox_ssh.flush()
#     natbox_ssh.connect(retry=False)
#
#
# def pytest_collectstart():
#     """
#     Set up the ssh session at collectstart. Because skipif condition is evaluated at the collecting test cases phase.
#     """
#     global con_ssh
#     con_ssh = setups.setup_tis_ssh(ProjVar.get_var("LAB"))
#     ProjVar.set_var(con_ssh=con_ssh)
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
#
#
# @pytest.fixture(scope='session', autouse=True)
# def pre_check_patching():
#
#     ProjVar.set_var(SOURCE_ADMIN=True)
#
#     # check if all nodes are unlocked
#     assert system_helper.are_hosts_unlocked(con_ssh), \
#         'All nodes must be unlocked. Upgrade cannot be started when there ' \
#         'are locked nodes.'
#
#     # check no active alarms in system
#     table_ = table_parser.table(cli.system('alarm-list'))
#     alarm_severity_list = table_parser.get_column(table_, "Severity")
#
#     LOG.info("Alarm Severity List: {}".format(alarm_severity_list))
#     assert "major" or "critical" not in alarm_severity_list,\
#         "Active alarms in system. Clear alarms before beginning upgrade"
#
#     # check if system is patch current
#     assert system_helper.is_patch_current(con_ssh), "System is not patch current"
#
