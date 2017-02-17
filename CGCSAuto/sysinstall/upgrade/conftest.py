import pytest
import os
import setups
from consts import build_server as build_server_consts
from consts.auth import CliAuth, Tenant, SvcCgcsAuto, Host
from consts.proj_vars import InstallVars, ProjVar, UpgradeVars
from keywords import system_helper, install_helper,  patching_helper
from utils.ssh import ControllerClient, SSHClient
from utils import table_parser, cli
from utils.tis_log import LOG
from consts.filepaths import BuildServerPath, WRSROOT_HOME
from consts.build_server import Server, get_build_server_info
from consts.cgcs import Prompt

# Import test fixtures that are applicable to upgrade test
from testfixtures.pre_checks_and_configs import *

# Import test fixtures that are applicable to upgrade test
from testfixtures.pre_checks_and_configs import *

natbox_ssh = None
con_ssh = None
SUPPORTED_UPGRADES = [['15.12', '16.10'], ['16.10', '17.00']]

########################
# Command line options #
########################


def pytest_addoption(parser):
    upgrade_version_help = "TiS next software version that the lab is upgraded to. " \
                           "Valid options are: {}".format(' '.join(v[1] for v in SUPPORTED_UPGRADES))
    build_server_help = "TiS build server host name where the upgrade release software is downloaded from." \
                        " ( default: {})".format(build_server_consts.DEFAULT_BUILD_SERVER['name'])
    upgrade_build_dir_path = "The path to the upgrade software release build directory in build server." \
                             " eg: /localdisk/loadbuild/jenkins/TS_16.10_Host/latest_build/. " \
                             " Otherwise the default  build dir path for the upgrade software " \
                             "version will be used"

    license_help = "The full path to the new release software license file in build-server. " \
                   "e.g /folk/cgts/lab/TiS16-full.lic or /folk/cgts/lab/TiS16-CPE-full.lic." \
                   " Otherwise, default license for the upgrade release will be used"

    patch_dir_help = "The path to the directory in build server where the patch files are located"

    parser.addoption('--upgrade-version', '--upgrade_version', '--upgrade', dest='upgrade_version',
                     action='store', metavar='VERSION', required=True,  help=upgrade_version_help)
    parser.addoption('--build-server', '--build_server',  dest='build_server',
                     action='store', metavar='SERVER', default=build_server_consts.DEFAULT_BUILD_SERVER['name'],
                     help=build_server_help)
    parser.addoption('--tis-build-dir', '--tis_build_dir',  dest='tis_build_dir',
                     action='store', metavar='DIR',  help=upgrade_build_dir_path)
    parser.addoption('--license',  dest='upgrade_license', action='store',
                     metavar='license full path', help=license_help)

    parser.addoption('--patch-dir', '--patch_dir',  dest='patch_dir',
                     action='store', metavar='DIR',  help=patch_dir_help)


def pytest_configure(config):

    upgrade_version = config.getoption('upgrade_version')
    upgrade_license = config.getoption('upgrade_license')
    build_server = config.getoption('build_server')
    tis_build_dir = config.getoption('tis_build_dir')
    patch_dir = config.getoption('patch_dir')
    print(" Pre Configure Install valrs: {}".format(InstallVars.get_install_vars()))

    UpgradeVars.set_upgrade_vars(upgrade_version=upgrade_version,
                                 build_server=build_server,
                                 tis_build_dir=tis_build_dir,
                                 upgrade_license_path=upgrade_license,
                                 patch_dir=patch_dir)


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
    natbox_ssh = setups.setup_natbox_ssh(ProjVar.get_var('KEYFILE_PATH'), ProjVar.get_var('NATBOX'), con_ssh=con_ssh)
    ProjVar.set_var(natbox_ssh=natbox_ssh)
    # setups.boot_vms(ProjVar.get_var('BOOT_VMS'))

    # set build id to be used to upload/write test results
    build_id, build_host = setups.get_build_info(con_ssh)
    ProjVar.set_var(BUILD_ID=build_id)
    ProjVar.set_var(BUILD_HOST=build_host)
    ProjVar.set_var(SOURCE_ADMIN=True)
    print('precheck source_admin_value: ' + str(ProjVar.get_var('SOURCE_ADMIN')))


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
    Tenant.ADMIN['auth_url'] = CliAuth.get_var('OS_AUTH_URL')
    Tenant.ADMIN['region'] = CliAuth.get_var('OS_REGION_NAME')


def pytest_runtest_teardown(item):
    # print('')
    # message = 'Teardown started:'
    # testcase_log(message, item.nodeid, log_type='tc_teardown')
    con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
    con_ssh.flush()


@pytest.fixture(scope='session')
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
    assert [current_version, upgrade_version] in SUPPORTED_UPGRADES, "Upgrade from {} to {} is not supported"


@pytest.fixture(scope='session')
def upgrade_setup(pre_check_upgrade):

    LOG.tc_func_start("UPGRADE_TEST")
    lab = InstallVars.get_install_var('LAB')

    # establish ssh connection with controller-0
    controller0_conn = ControllerClient.get_active_controller()
    cpe = system_helper.is_small_footprint(controller0_conn)
    upgrade_version = UpgradeVars.get_upgrade_var('UPGRADE_VERSION')
    license_path = UpgradeVars.get_upgrade_var('UPGRADE_LICENSE')
    if license_path is None:
        if cpe:
            license_path = BuildServerPath.TIS_LICENSE_PATHS[upgrade_version][1]
        else:
            license_path = BuildServerPath.TIS_LICENSE_PATHS[upgrade_version][0]

    bld_server = get_build_server_info(UpgradeVars.get_upgrade_var('BUILD_SERVER'))
    load_path = UpgradeVars.get_upgrade_var('TIS_BUILD_DIR')
    output_dir = ProjVar.get_var('LOG_DIR')
    patch_dir = UpgradeVars.get_upgrade_var('PATCH_DIR')

    current_version = install_helper.get_current_system_version()

    bld_server_attr = dict()
    bld_server_attr['name'] = bld_server['name']
    bld_server_attr['server_ip'] = bld_server['ip']
    #bld_server_attr['prompt'] = r'.*yow-cgts[1234]-lx.*$ '
    bld_server_attr['prompt'] = Prompt.BUILD_SERVER_PROMPT_BASE.format('svc-cgcsauto', bld_server['name'])
    # '.*yow\-cgts[34]\-lx ?~\]?\$ '
    bld_server_conn = SSHClient(bld_server_attr['name'], user=SvcCgcsAuto.USER,
                                password=SvcCgcsAuto.PASSWORD, initial_prompt=bld_server_attr['prompt'])
    bld_server_conn.connect()
    bld_server_conn.exec_cmd("bash")
    bld_server_conn.set_prompt(bld_server_attr['prompt'])
    bld_server_conn.deploy_ssh_key(install_helper.PUBLIC_SSH_KEY)
    bld_server_attr['ssh_conn'] = bld_server_conn

    bld_server_obj = Server(**bld_server_attr)

    # # get upgrade license file for release
    LOG.info("Dowloading the license {}:{} for target release {}".format(bld_server_obj.name,
                                                                         license_path, upgrade_version))
    install_helper.download_upgrade_license(lab, bld_server_obj, license_path)

    LOG.tc_step("Checking if target release license is downloaded......")
    cmd = "test -e " + os.path.join(WRSROOT_HOME, "upgrade_license.lic")
    assert controller0_conn.exec_cmd(cmd)[0] == 0, "Upgrade license file not present in Controller-0"
    LOG.info("Upgrade  license {} download complete".format(license_path))

    # get upgrade load iso file
    LOG.tc_step("Dowloading the {} target release  load iso image file {}:{}".format(
            upgrade_version, bld_server_obj.name, load_path))
    install_helper.download_upgrade_load(lab, bld_server_obj, load_path)
    upgrade_load_path = os.path.join(WRSROOT_HOME, install_helper.UPGRADE_LOAD_ISO_FILE)

    cmd = "test -e {}".format(upgrade_load_path)
    assert controller0_conn.exec_cmd(cmd)[0] == 0, "Upgrade build iso image file {} not present " \
                                                   "in Controller-0".format(upgrade_load_path)
    LOG.info("Target release load {} download complete.".format(upgrade_load_path))

    # Install the license file for release
    LOG.tc_step("Installing the target release {} license file".format(upgrade_version))
    rc = system_helper.install_upgrade_license(os.path.join(WRSROOT_HOME, "upgrade_license.lic"),
                                               con_ssh=controller0_conn)
    assert rc == 0, "Unable to install upgrade license file in Controller-0"
    LOG.info("Target release license installed......")

    # Run the load_import command to import the new release iso image build
    LOG.tc_step("Importing the target release  load iso file".format(upgrade_load_path))
    output = system_helper.import_load(upgrade_load_path)

    # check if upgrade load software is imported successfully
    if output[0] == 0:
        ver = output[2]
    else:
        ver = (system_helper.get_imported_load_version()).pop()

    LOG.tc_step("Checking if target release load is imported......")
    assert upgrade_version in ver, "Import error. Expected " \
                                   "version {} not found in imported load list" \
                                   "{}".format(upgrade_version, ver)
    LOG.info("The target release  load iso file {} imported".format(upgrade_load_path))

    # download and apply patches if patches are available in patch directory
    if patch_dir:
        LOG.tc_step("Applying  {} patches, if present".format(upgrade_version))
        apply_patches(lab, bld_server_obj, patch_dir)

    _upgrade_setup = {'lab': lab,
                      'cpe': cpe,
                      'output_dir': output_dir,
                      'current_version': current_version,
                      'upgrade_version': upgrade_version,
                      'build_server': bld_server_obj,
                      }

    return _upgrade_setup


@pytest.fixture(scope='function')
def check_system_health_query_upgrade():
    # Check system health for upgrade
    LOG.tc_func_start("UPGRADE_TEST")
    LOG.tc_step("Checking if system health is OK to start upgrade......")
    rc, health = system_helper.get_system_health_query_upgrade()
    print("HEALTH: {}".format(health))
    if rc == 0:
        LOG.info("system health is OK to start upgrade......")
        return 0, None
    elif rc != 0 and len(health) > 2:
        LOG.error("System health query upgrade failed: {}".format(health))
        return 1, health
    elif rc == 1 and len(health) == 1 and 'No alarms' in health:
        # Check if it alarm
        table_ = table_parser.table(cli.system('alarm-list'))
        alarm_severity_list = table_parser.get_column(table_, "Severity")
        if len(alarm_severity_list) > 0 and ("major" not in alarm_severity_list
                                             and "critical" not in alarm_severity_list):
            # minor alarm present
            LOG.warn("System health query upgrade found minor alarms: {}".format(alarm_severity_list))
            return 2, health

    LOG.error("System health query upgrade failed: {}".format(health))
    return 1, health


def get_system_active_controller():
    global con_ssh
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    cmd = "source /etc/nova/openrc; system servicegroup-list"
    table_ = table_parser.table(con_ssh.exec_cmd(cmd)[1])
    table_ = table_parser.filter_table(table_, service_group_name='controller-services')
    controllers = table_parser.get_values(table_, 'hostname', state='active', strict=False)
    LOG.debug(" Active controller(s): {}".format(controllers))
    if isinstance(controllers, str):
        controllers = [controllers]

    return controllers


def apply_patches(lab, server, patch_dir):
    """

    Args:
        lab:
        server:
        patch_dir:

    Returns:

    """
    patch_names = []
    rc = server.ssh_conn.exec_cmd("test -d " + patch_dir)[0]
    assert rc == 0, "Patch directory path {} not found".format(patch_dir)

    rc, output = server.ssh_conn.exec_cmd("ls -1 --color=none {}/*.patch".format(patch_dir))
    assert rc == 0, "Failed to list patch files in directory path {}.".format(patch_dir)

    #LOG.info("No path found in {} ".format(patch_dir))

    if output is not None:
        for item in output.splitlines():
            # Remove ".patch" extension
            patch_name = os.path.splitext(item)[0]
            LOG.info("Found patch named: " + patch_name)
            patch_names.append(patch_name)

        patch_dest_dir = WRSROOT_HOME + "/upgrade_patches"

        pre_opts = 'sshpass -p "{0}"'.format(Host.PASSWORD)
        server.ssh_conn.rsync(patch_dir + "/*.patch",
                          lab['controller-0 ip'],
                          patch_dest_dir, pre_opts=pre_opts)

        avail_patches = " ".join(patch_names)
        LOG.info("List of patches:\n {}".format(avail_patches))

        LOG.info("Uploading  patches ... ")
        assert patching_helper.run_patch_cmd("upload-dir", args=patch_dest_dir)[0] == 0, \
            "Failed to upload  patches : {}".format(avail_patches)

        LOG.info("Quering patches ... ")
        assert patching_helper.run_patch_cmd("query")[0] == 0, "Failed to query patches"

        LOG.info("Applying patches ... ")
        rc = patching_helper.run_patch_cmd("apply", args='--all')[0]
        assert rc == 0, "Failed to apply patches"

        LOG.info("Quering patches ... ")
        assert patching_helper.run_patch_cmd("query")[0] == 0, "Failed to query patches"
