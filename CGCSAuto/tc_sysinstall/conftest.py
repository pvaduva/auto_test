
import pytest
import os
import setups
from consts.auth import CliAuth, Tenant
from consts.proj_vars import ProjVar, InstallVars
from consts.build_server import Server, get_build_server_info
from utils.ssh import ControllerClient, SSHClient
from consts import build_server as build_server_consts
from consts.filepaths import BuildServerPath
from consts.cgcs import Prompt
from utils.tis_log import LOG
from utils import lab_info


LAB_FILES = ["TiS_config.ini_centos", "hosts_bulk_add.xml", "lab_setup.conf", "settings.ini"]
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
    #custom
    file_dir_help = "directory that contains the following lab files: {}. ".format(
        ' '.join(v[1] for v in LAB_FILES)) + \
                        "Custom directories can be found at: /folk/cgts/lab/customconfigs" \
                        "Default is: <load_path>/rt/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/<lab_name>"
    controller_help = "Comma-separated list of VLM barcodes for controllers"
    compute_help = "Comma-separated list of VLM barcodes for computes"
    storage_help = "Comma-separated list of VLM barcodes for storage nodes"

    parser.addoption('--ceph-mon-dev-controller-0', '--ceph_mon_dev_controller-0',  dest='ceph_mon_dev_controller_0',
                     action='store', metavar='DISK_DEVICE',  help=ceph_mon_device_controller0_help)
    parser.addoption('--ceph-mon-dev-controller-1', '--ceph_mon_dev_controller-1',  dest='ceph_mon_dev_controller_1',
                     action='store', metavar='DISK_DEVICE',  help=ceph_mon_device_controller1_help)
    parser.addoption('--ceph-mon-gib', '--ceph_mon_dev_gib',  dest='ceph_mon_gib',
                     action='store', metavar='SIZE',  help=ceph_mon_gib_help)
    build_server_help = "TiS build server host name where the upgrade release software is downloaded from." \
                        " ( default: {})".format(build_server_consts.DEFAULT_BUILD_SERVER['name'])
    build_dir_path_help = "The path to the upgrade software release build directory in build server." \
                             " eg: /localdisk/loadbuild/jenkins/TS_16.10_Host/latest_build/. " \
                             " Otherwise the default  build dir path for the upgrade software " \
                             "version will be used"
    file_server_help = "The server that holds the lab file directory." \ 
                           "Default is the build server"
    license_help = "The full path to the new release software license file in build-server. " \
                   "e.g /folk/cgts/lab/TiS16-full.lic or /folk/cgts/lab/TiS16-CPE-full.lic." \
                   " Otherwise, default license for the upgrade release will be used"
    guest_image_help = "The full path to the tis-centos-guest.img in build-server" \
                       "( default: {} )".format(BuildServerPath.DEFAULT_GUEST_IMAGE_PATH)
    heat_help = "The full path to the python heat templates" \
                "( default: {} )".format(BuildServerPath.HEAT_TEMPLATES)

    # Custom install options
    parser.addoption('--lab_file_server', '--lab-file-server', dest='file_server',
                     action='store', default=build_server_consts.DEFAULT_BUILD_SERVER['name'], help=file_server_help)
    parser.addoption('--lab_file_dir', '--lab-file-dir', dest='file_dir',
                     action='store', metavar='DIR', help=file_dir_help)
    parser.addoption('--controller', dest='controller',
                     action='store', help=controller_help)
    parser.addoption('--build-server', '--build_server', dest='build_server',
                     action='store', metavar='SERVER', default=build_server_consts.DEFAULT_BUILD_SERVER['name'],
                     help=build_server_help)
    parser.addoption('--tis-build-dir', '--tis_build_dir', dest='tis_build_dir', action='store',
                     metavar='DIR', help=build_dir_path_help, default=BuildServerPath.DEFAULT_HOST_BUILD_PATH)
    parser.addoption('--license', dest='upgrade_license', action='store',
                     metavar='license full path', help=license_help)
    parser.addoption('--guest_image', '--guest-image', '--guest_image_path', 'guest-image-path',
                     dest='guest_image_path', action='store', metavar='guest image full path',
                     default=BuildServerPath.DEFAULT_GUEST_IMAGE_PATH, help=guest_image_help)
    parser.addoption('--heat_templates', '--heat-templates', '--heat_templates_path', '--heat-templates-path',
                     dest='heat_templates', action='store', metavar='heat templates full path',
                     default=BuildServerPath.HEAT_TEMPLATES, help=heat_help)

    # TODO: choose custom nodes to install a lab (install new labs)
    parser.addoption('--compute', dest='compute',
                     action='store', help=compute_help)
    parser.addoption('--storage', dest='storage',
                     action='store', help=storage_help)

def pytest_configure(config):

    # Lab install params
    lab_arg = config.getoption('lab')
    resume_install = config.getoption('resumeinstall')
    skip_labsetup = config.getoption('skiplabsetup')
    #TODO: Add functionality to wipedisk
    wipedisk = config.getoption('wipedisk')
    controller0_ceph_mon_device = config.getoption('ceph_mon_dev_controller_0')
    controller1_ceph_mon_device = config.getoption('ceph_mon_dev_controller_1')
    ceph_mon_gib = config.getoption('ceph_mon_gib')
    install_conf = config.getoption('installconf')
    # TODO: fix up naming a bit
    lab_file_server = config.getoption("file_server")
    lab_file_dir = config.getoption('file_dir')
    build_server = config.getoption('build_server')
    tis_build_dir = config.getoption('tis_build_dir')
    install_license = config.getoption('upgrade_license')
    heat_templates = config.getoption('heat_templates')
    guest_image = config.getoption('guest_image_path')

    controller = config.getoption('controller')
    compute = config.getoption('compute')
    storage = config.getoption('storage')


    if not install_conf:
        install_conf = setups.write_installconf(lab=lab_arg, controller=controller, compute=compute, storage=storage,
                                                lab_files_dir=lab_file_dir, lab_files_server=lab_file_server,
                                                tis_build_dir=tis_build_dir, build_server=build_server,
                                                license_path=install_license, guest_image=guest_image,
                                                heat_templates=heat_templates)

    setups.set_install_params(lab=lab_arg, skip_labsetup=skip_labsetup, resume=resume_install, wipedisk=wipedisk,
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
    ProjVar.set_var(PRIMARY_TENANT=Tenant.ADMIN)
    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.ADMIN)
    setups.setup_primary_tenant(ProjVar.get_var('PRIMARY_TENANT'))
    con_ssh.set_prompt()
    setups.set_env_vars(con_ssh)
    setups.copy_files_to_con1()
    con_ssh.set_prompt()

    global natbox_ssh
    natbox = ProjVar.get_var('NATBOX')
    if natbox['ip'] == 'localhost':
        natbox_ssh = 'localhost'
    else:
        natbox_ssh = setups.setup_natbox_ssh(ProjVar.get_var('KEYFILE_PATH'), natbox, con_ssh=con_ssh)
    # setups.boot_vms(ProjVar.get_var('BOOT_VMS'))

    # set build id to be used to upload/write test results
    build_id, build_server = setups.get_build_info(con_ssh)
    ProjVar.set_var(BUILD_ID=build_id)
    ProjVar.set_var(BUILD_SERVER=build_server)
    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.ADMIN)

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
    Tenant.ADMIN['auth_url'] = CliAuth.get_var('OS_AUTH_URL')
    Tenant.ADMIN['region'] = CliAuth.get_var('OS_REGION_NAME')


def pytest_runtest_teardown(item):
    # print('')
    # message = 'Teardown started:'
    # testcase_log(message, item.nodeid, log_type='tc_teardown')
    if not con_ssh._is_connected():
        con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
    con_ssh.flush()
