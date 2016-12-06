import pytest

import setups
from consts import build_server as build_server_consts
from consts.auth import CliAuth, Tenant
from consts.proj_vars import InstallVars, ProjVar, UpgradeVars
from keywords import system_helper
# from utils.ssh import ControllerClient
from utils import table_parser, cli
from utils.tis_log import LOG

natbox_ssh = None
con_ssh = None
SUPPORTED_UPRADES = [['15.12', '16.10'], ['16.10', '17.00']]

########################
# Command line options #
########################


def pytest_addoption(parser):
    upgrade_version_help = "TiS next software version that the lab is upgraded to. " \
                           "Valid options are: {}".format(' '.join(v[1] for v in SUPPORTED_UPRADES))
    build_server_help = "TiS build server host name where the upgrade release software is downloaded from." \
                        " ( default: {})".format(build_server_consts.DEFAULT_BUILD_SERVER['name'])
    upgrade_build_dir_path = "The path to the upgrade software release build directory in build server." \
                             " eg: /localdisk/loadbuild/jenkins/TS_16.10_Host/latest_build/. " \
                             " Otherwise the default  build dir path for the upgrade software " \
                             "version will be used"

    license_help = "The full path to the new release software license file in build-server. " \
                   "e.g /folk/cgts/lab/TiS16-full.lic or /folk/cgts/lab/TiS16-CPE-full.lic." \
                   " Otherwise, default license for the upgrade release will be used"
    parser.addoption('--upgrade-version', '--upgrade_version', '--upgrade', dest='upgrade_version',
                     action='store', metavar='VERSION', required=True,  help=upgrade_version_help)
    parser.addoption('--build-server', '--build_server',  dest='build_server',
                     action='store', metavar='SERVER', default=build_server_consts.DEFAULT_BUILD_SERVER['name'],
                     help=build_server_help)
    parser.addoption('--tis-build-dir', '--tis_build_dir',  dest='tis_build_dir',
                     action='store', metavar='DIR',  help=upgrade_build_dir_path)
    parser.addoption('--license',  dest='upgrade_license', action='store', metavar='license full path', help=license_help)


def pytest_configure(config):

    upgrade_version = config.getoption('upgrade_version')
    upgrade_license = config.getoption('upgrade_license')
    build_server = config.getoption('build_server')
    tis_build_dir = config.getoption('tis_build_dir')
    print(" Pre Configure Install valrs: {}".format(InstallVars.get_install_vars()))

    UpgradeVars.set_upgrade_vars(upgrade_version=upgrade_version,
                                 build_server=build_server,
                                 tis_build_dir=tis_build_dir,
                                 upgrade_license_path=upgrade_license)



    print("Upgrade vars: {}".format(UpgradeVars.get_upgrade_vars()))


@pytest.fixture(scope='session', autouse=True)
def setup_test_session():
    """
    Setup primary tenant and Nax Box ssh before the first test gets executed.
    TIS ssh was already set up at collecting phase.
    """
    # os.makedirs(ProjVar.get_var('TEMP_DIR'), exist_ok=True)
    ProjVar.set_var(PRIMARY_TENANT=Tenant.ADMIN)
    setups.setup_primary_tenant(ProjVar.get_var('PRIMARY_TENANT'))
    con_ssh.set_prompt()
    setups.set_env_vars(con_ssh)

    setups.copy_files_to_con1()

    global natbox_ssh
    natbox_ssh = setups.setup_natbox_ssh(ProjVar.get_var('KEYFILE_PATH'), ProjVar.get_var('NATBOX'))
    ProjVar.set_var(natbox_ssh=natbox_ssh)
    # setups.boot_vms(ProjVar.get_var('BOOT_VMS'))

    # set build id to be used to upload/write test results
    build_id = setups.get_build_id(con_ssh)
    ProjVar.set_var(BUILD_ID=build_id)


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
    Tenant._set_url(CliAuth.get_var('OS_AUTH_URL'))
    Tenant._set_region(CliAuth.get_var('OS_REGION_NAME'))


def pytest_runtest_teardown(item):
    # print('')
    # message = 'Teardown started:'
    # testcase_log(message, item.nodeid, log_type='tc_teardown')
    con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
    con_ssh.flush()


@pytest.fixture(scope='session', autouse=True)
def pre_check_upgrade():
    # con_ssh = ControllerClient.get_active_controller()

    ProjVar.set_var(SOURCE_ADMIN=True)
    print('precheck source_admin_value: ' + str(ProjVar.get_var('SOURCE_ADMIN')))

    # check if all nodes are unlocked
    assert system_helper.are_hosts_unlocked(con_ssh), \
        'All nodes must be unlocked. Upgrade cannot be started when there ' \
        'are locked nodes.'

    # check no active alarms in system

    table_ = table_parser.table(cli.system('alarm-list'))
    alarm_severity_list = table_parser.get_column(table_, "Severity")

    LOG.info("Alarm Severity List: {}".format(alarm_severity_list))
    assert "major" or "critical" not in alarm_severity_list,\
        "Active alarms in system. Clear alarms before beginning upgrade"

    # check if system is patch current
    assert system_helper.is_patch_current(con_ssh), "System is not patch current"

    # check if Controller-0 is the active
    active_controller = system_helper.get_active_controller_name(con_ssh=con_ssh)
    assert active_controller == "controller-0", "The active controller is " \
                                                "not controller-0. Make controller-0 " \
                                                "active before starting upgrade. Current " \
                                                "active controller is {}".format(active_controller)

    # check if upgrade version is supported
    current_version = system_helper.get_system_software_version()
    upgrade_version = UpgradeVars.get_upgrade_var('upgrade_version')
    assert [current_version, upgrade_version] in SUPPORTED_UPRADES, "Upgrade from {} to {} is not supported"

#
# def get_system_active_controller():
#     con_ssh = ControllerClient.get_active_controller()
#     cmd = "source /etc/nova/openrc; system servicegroup-list"
#     table_ = table_parser.table(con_ssh.exec_cmd(cmd)[1])
#     table_ = table_parser.filter_table(table_, service_group_name='controller-services')
#     controllers = table_parser.get_values(table_, 'hostname', state='active', strict=False)
#     LOG.debug(" Active controller(s): {}".format(controllers))
#     if isinstance(controllers, str):
#         controllers = [controllers]
#
#     return controllers
