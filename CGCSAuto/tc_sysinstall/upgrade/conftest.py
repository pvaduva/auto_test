import pytest
import os
from consts import build_server as build_server_consts
from consts.auth import SvcCgcsAuto, HostLinuxCreds
from consts.proj_vars import InstallVars, ProjVar, UpgradeVars
from keywords import install_helper,  patching_helper, upgrade_helper
from utils.ssh import ControllerClient, SSHClient
from utils import table_parser, cli
from consts.filepaths import BuildServerPath, WRSROOT_HOME
from consts.build_server import Server, get_build_server_info
from consts.cgcs import Prompt

# Import test fixtures that are applicable to upgrade test
from testfixtures.pre_checks_and_configs import *


natbox_ssh = None
con_ssh = None
SUPPORTED_UPGRADES = [['15.12', '16.10'], ['16.10', '17.00'], ['16.10', '17.06'], ['17.06', '17.07']]

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

    orchestration_help = "The point in upgrade procedure where we start to use orchestration. Possible options are:" \
                         "  default - to start orchestration after controller-1 is upgraded; " \
                         "  storage:<#> - to start orchestration after <#> storage (s) are upgraded normally; " \
                         "  compute:<#> - start orchestration after <#> compute(s) are upgraded normally; " \
                         " The default is default. Applicable only for upgrades from R3."
    apply_strategy_help = "How the orchestration strategy is applied:" \
                          "  serial - apply orchestration strategy one node  at a time; " \
                          "  parallel - apply orchestration strategy in parallel; " \
                          "  ignore - do not apply the orchestration strategy; " \
                          " If not specified,  the system will choose the option to apply the strategy. " \
                          "Applicable only for upgrades from R3."
    max_parallel_compute_help = "The maximum number of compute hosts to upgrade in parallel, if parallel apply type" \
                                " is selected"
    alarm_restriction_help = """Inidcates how to handle alarm restrictions based on the management affecting statuses
                             of any existing alarms.
                                 relaxed -  orchestration is allowed to proceed if none managment affecting alarms are
                                            present
                                 strict -  orchestration is not allowed if alarms are present
                             """

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

    parser.addoption('--orchestration', '--orchestration-after', '--orchestration_after', dest='orchestration_after',
                     action='store', metavar='HOST_PERSONALITY:NUM', default='default', help=orchestration_help)

    parser.addoption('--storage-apply-type', '--storage_apply_type', '--sstra',  dest='storage_strategy',
                     action='store',  help=apply_strategy_help)

    parser.addoption('--compute-apply-type', '--compute_apply_type', '--cstra', dest='compute_strategy',
                     action='store',  help=apply_strategy_help)

    parser.addoption('--max-parallel-computes', '--max_parallel_computes', dest='max_parallel_computes',
                     action='store',  help=max_parallel_compute_help)

    parser.addoption('--alarm-restrictions', '--alarm_restrictions', dest='alarm_restrictions',
                     action='store', default='strict',  help=alarm_restriction_help)


def pytest_configure(config):

    upgrade_version = config.getoption('upgrade_version')
    upgrade_license = config.getoption('upgrade_license')
    build_server = config.getoption('build_server')
    tis_build_dir = config.getoption('tis_build_dir')
    patch_dir = config.getoption('patch_dir')
    orchestration_after = config.getoption('orchestration_after')
    storage_apply_strategy = config.getoption('storage_strategy')
    compute_apply_strategy = config.getoption('compute_strategy')
    max_parallel_computes = config.getoption('max_parallel_computes')
    alarm_restrictions = config.getoption('alarm_restrictions')

    if upgrade_version == "16.10":
        orchestration_after = None

    print(" Pre Configure Install vars: {}".format(InstallVars.get_install_vars()))

    UpgradeVars.set_upgrade_vars(upgrade_version=upgrade_version,
                                 build_server=build_server,
                                 tis_build_dir=tis_build_dir,
                                 upgrade_license_path=upgrade_license,
                                 patch_dir=patch_dir,
                                 orchestration_after=orchestration_after,
                                 storage_apply_strategy=storage_apply_strategy,
                                 compute_apply_strategy=compute_apply_strategy,
                                 max_parallel_computes=max_parallel_computes,
                                 alarm_restrictions=alarm_restrictions)


@pytest.fixture(scope='session')
def pre_check_upgrade():
    # con_ssh = ControllerClient.get_active_controller()

    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.ADMIN)
    print('precheck source_admin_value: ' + str(ProjVar.get_var('SOURCE_CREDENTIAL')))

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
    is_simplex = system_helper.is_simplex()
    if license_path is None:
        if cpe:
            license_path = BuildServerPath.TIS_LICENSE_PATHS[upgrade_version][1]
        elif is_simplex:
            license_path = BuildServerPath.TIS_LICENSE_PATHS[upgrade_version][2]
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
    # bld_server_attr['prompt'] = r'.*yow-cgts[1234]-lx.*$ '
    bld_server_attr['prompt'] = Prompt.BUILD_SERVER_PROMPT_BASE.format('svc-cgcsauto', bld_server['name'])
    # '.*yow\-cgts[34]\-lx ?~\]?\$ '
    bld_server_conn = SSHClient(bld_server_attr['name'], user=SvcCgcsAuto.USER,
                                password=SvcCgcsAuto.PASSWORD, initial_prompt=bld_server_attr['prompt'])
    bld_server_conn.connect()
    bld_server_conn.exec_cmd("bash")
    bld_server_conn.set_prompt(bld_server_attr['prompt'])
    bld_server_conn.deploy_ssh_key(install_helper.get_ssh_public_key())
    bld_server_attr['ssh_conn'] = bld_server_conn
    bld_server_obj = Server(**bld_server_attr)

    # # get upgrade license file for release
    LOG.info("Downloading the license {}:{} for target release {}".format(bld_server_obj.name,
                                                                          license_path, upgrade_version))
    install_helper.download_upgrade_license(lab, bld_server_obj, license_path)

    LOG.tc_step("Checking if target release license is downloaded......")
    cmd = "test -e " + os.path.join(WRSROOT_HOME, "upgrade_license.lic")
    assert controller0_conn.exec_cmd(cmd)[0] == 0, "Upgrade license file not present in Controller-0"
    LOG.info("Upgrade  license {} download complete".format(license_path))

    # Install the license file for release
    LOG.tc_step("Installing the target release {} license file".format(upgrade_version))
    rc = system_helper.install_upgrade_license(os.path.join(WRSROOT_HOME, "upgrade_license.lic"),
                                               con_ssh=controller0_conn)
    assert rc == 0, "Unable to install upgrade license file in Controller-0"
    LOG.info("Target release license installed......")

    # Check load already imported if not  get upgrade load iso file
    # Run the load_import command to import the new release iso image build
    if not system_helper.get_imported_load_version():
        LOG.tc_step("Downloading the {} target release  load iso image file {}:{}"
                    .format(upgrade_version, bld_server_obj.name, load_path))
        install_helper.download_upgrade_load(lab, bld_server_obj, load_path)
        upgrade_load_path = os.path.join(WRSROOT_HOME, install_helper.UPGRADE_LOAD_ISO_FILE)

        cmd = "test -e {}".format(upgrade_load_path)
        assert controller0_conn.exec_cmd(cmd)[0] == 0, "Upgrade build iso image file {} not present in Controller-0"\
            .format(upgrade_load_path)
        LOG.info("Target release load {} download complete.".format(upgrade_load_path))
        LOG.tc_step("Importing Target release  load iso file from".format(upgrade_load_path))
        system_helper.import_load(upgrade_load_path)

        # download and apply patches if patches are available in patch directory
        if patch_dir:
            LOG.tc_step("Applying  {} patches, if present".format(upgrade_version))
            apply_patches(lab, bld_server_obj, patch_dir)

    # check disk space
    check_controller_filesystem()

    # Check for simplex and return
    if is_simplex:
        _upgrade_setup_simplex = {'lab': lab,
                                  'cpe': cpe,
                                  'output_dir': output_dir,
                                  'current_version': current_version,
                                  'upgrade_version': upgrade_version,
                                  'build_server': bld_server_obj
                                  }
        return _upgrade_setup_simplex
            # check which nodes are upgraded using orchestration

    orchestration_after = UpgradeVars.get_upgrade_var('ORCHESTRATION_AFTER')
    storage_apply_strategy = UpgradeVars.get_upgrade_var('STORAGE_APPLY_TYPE')
    compute_apply_strategy = UpgradeVars.get_upgrade_var('COMPUTE_APPLY_TYPE')
    max_parallel_computes = UpgradeVars.get_upgrade_var('MAX_PARALLEL_COMPUTES')
    alarm_restrictions = UpgradeVars.get_upgrade_var('ALARM_RESTRICTIONS')

    if orchestration_after:
        LOG.info("Upgrade orchestration start option: {}".format(orchestration_after))
    if storage_apply_strategy:
        LOG.info("Storage apply type: {}".format(storage_apply_strategy))
    if compute_apply_strategy:
        LOG.info("Compute apply type: {}".format(compute_apply_strategy))
    if max_parallel_computes:
        LOG.info("Maximum parallel computes: {}".format(max_parallel_computes))
    if alarm_restrictions:
        LOG.info("Alarm restriction option: {}".format(alarm_restrictions))

    system_nodes = system_helper.get_hostnames()
    storage_nodes = [h for h in system_nodes if "storage" in h]
    compute_nodes = [h for h in system_nodes if "storage" not in h and 'controller' not in h]
    orchestration_nodes = []
    cpe = False
    if len(compute_nodes) == 0:
        cpe = True

    if not cpe and orchestration_after and (orchestration_after == 'default' or 'controller' in orchestration_after):
        orchestration_nodes.extend(system_nodes)
        orchestration_nodes.remove('controller-1')
        if 'controller' in orchestration_after:
            orchestration_nodes.remove('controller-0')

    elif not cpe and orchestration_after and 'storage' in orchestration_after:
        number_of_storages = len(storage_nodes)
        num_selected = int(orchestration_after.split(':')[1]) if len(orchestration_after.split(':')) == 2 \
            else number_of_storages
        if num_selected > number_of_storages:
            num_selected = number_of_storages
        if num_selected > 0:
            for i in range(num_selected):
                orchestration_nodes.extend([h for h in storage_nodes if h != 'storage-{}'.format(i)])
        orchestration_nodes.extend(compute_nodes)
    elif not cpe and orchestration_after and 'compute' in orchestration_after:
        number_of_computes = len(compute_nodes)
        num_selected = int(orchestration_after.split(':')[1]) if len(orchestration_after.split(':')) == 2 \
            else number_of_computes
        if num_selected > number_of_computes:
            num_selected = number_of_computes

        orchestration_nodes.extend(compute_nodes[num_selected:])
    else:
        LOG.info("System {} will be upgraded though manual procedure without orchestration.".format(lab['name']))

    man_upgrade_nodes = [h for h in system_nodes if h not in orchestration_nodes]

    LOG.info(" Nodes upgraded manually are: {}".format(man_upgrade_nodes))
    LOG.info(" Nodes upgraded through Orchestration are: {}".format(orchestration_nodes))

    _upgrade_setup = {'lab': lab,
                      'cpe': cpe,
                      'output_dir': output_dir,
                      'current_version': current_version,
                      'upgrade_version': upgrade_version,
                      'build_server': bld_server_obj,
                      'man_upgrade_nodes': man_upgrade_nodes,
                      'orchestration_nodes': orchestration_nodes,
                      'storage_apply_strategy': storage_apply_strategy,
                      'compute_apply_strategy': compute_apply_strategy,
                      'max_parallel_computes': max_parallel_computes,
                      'alarm_restrictions': alarm_restrictions,
                      }
    ver = (system_helper.get_imported_load_version()).pop()
    assert upgrade_version in ver, "Import error. Expected " \
                                   "version {} not found in imported load list" \
                                   "{}".format(upgrade_version, ver)
    LOG.info("Imported Target release  load iso {}".format(upgrade_version, ver))
    return _upgrade_setup


@pytest.fixture(scope='function')
def check_system_health_query_upgrade():
    # Check system health for upgrade
    LOG.tc_func_start("UPGRADE_TEST")
    LOG.tc_step("Checking if system health is OK to start upgrade......")
    rc, health = upgrade_helper.get_system_health_query_upgrade()
    print("HEALTH: {}, {}".format(rc, health))
    return rc, health


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

    # LOG.info("No path found in {} ".format(patch_dir))

    if output is not None:
        for item in output.splitlines():
            # Remove ".patch" extension
            patch_name = os.path.splitext(item)[0]
            LOG.info("Found patch named: " + patch_name)
            patch_names.append(patch_name)

        patch_dest_dir = WRSROOT_HOME + "upgrade_patches/"

        dest_server = lab['controller-0 ip']
        ssh_port = None

        if 'vbox' in lab['name']:
            dest_server = lab['external_ip']
            ssh_port = lab['external_port']

        pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.get_password())
        server.ssh_conn.rsync(patch_dir + "/*.patch", dest_server, patch_dest_dir, ssh_port=ssh_port,pre_opts=pre_opts)

        avail_patches = " ".join(patch_names)
        LOG.info("List of patches:\n {}".format(avail_patches))

        LOG.info("Uploading  patches ... ")
        assert patching_helper.run_patch_cmd("upload-dir", args=patch_dest_dir)[0] == 0, \
            "Failed to upload  patches : {}".format(avail_patches)

        LOG.info("Querying patches ... ")
        assert patching_helper.run_patch_cmd("query")[0] == 0, "Failed to query patches"

        LOG.info("Applying patches ... ")
        rc = patching_helper.run_patch_cmd("apply", args='--all')[0]
        assert rc == 0, "Failed to apply patches"

        LOG.info("Querying patches ... ")
        assert patching_helper.run_patch_cmd("query")[0] == 0, "Failed to query patches"


def check_controller_filesystem(con_ssh=None):

    LOG.info("Checking controller root fs size ... ")
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    patch_dest_dir1 = WRSROOT_HOME + "patches/"
    patch_dest_dir2 = WRSROOT_HOME + "upgrade_patches/"
    upgrade_load_path = os.path.join(WRSROOT_HOME, install_helper.UPGRADE_LOAD_ISO_FILE)
    current_version = install_helper.get_current_system_version()
    cmd = "df | grep /dev/root | awk ' { print $5}'"
    rc, output = con_ssh.exec_cmd(cmd)
    if rc == 0 and output:
        LOG.info("controller root fs size is {} full ".format(output))
        percent = int(output.strip()[:-1])
        if percent > 69:
            con_ssh.exec_cmd("rm {}/*".format(patch_dest_dir1))
            con_ssh.exec_cmd("rm {}/*".format(patch_dest_dir2))
            con_ssh.exec_cmd("rm {}".format(upgrade_load_path))
            with host_helper.ssh_to_host('controller-1') as host_ssh:
                host_ssh.exec_cmd("rm {}/*".format(patch_dest_dir1))
                host_ssh.exec_cmd("rm {}/*".format(patch_dest_dir2))
                host_ssh.exec_cmd("rm {}".format(upgrade_load_path))

            if current_version == '15.12':
                time.sleep(120)
            else:
                entity_id = 'host=controller-0.filesystem=/'
                system_helper.wait_for_alarms_gone([(EventLogID.FS_THRESHOLD_EXCEEDED, entity_id)], check_interval=10,
                                           fail_ok=True, timeout=180)

