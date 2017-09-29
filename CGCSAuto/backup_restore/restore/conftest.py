
import pytest

import setups
import os
import re

from consts.auth import SvcCgcsAuto
from consts.proj_vars import InstallVars, ProjVar, RestoreVars
from keywords import install_helper, vlm_helper
from utils.ssh import ControllerClient
from utils import node
from consts.filepaths import BuildServerPath
from consts.build_server import Server, get_build_server_info
from consts.cgcs import Prompt, TIS_BLD_DIR_REGEX


# Import test fixtures that are applicable to upgrade test
from testfixtures.pre_checks_and_configs import *


########################
# Command line options #
########################

def pytest_addoption(parser):


    parser.addoption('--backup-src', '--backup_src',  dest='backup_src',
                     action='store', default='USB',  help="Where to get the bakcup files")
    parser.addoption('--backup-build-id', '--backup_build-id',  dest='backup_build_id',
                     action='store',  help="The build id of the backup")
    parser.addoption('--backup-builds-dir', '--backup_builds-dir',  dest='backup_builds_dir',
                     action='store',  help="The Titanium builds dir where the backup build id belong. "
                                           "Such as CGCS_5.0_Host or TC_17.06_Host")

def pytest_configure(config):

    # Lab install params
    lab_arg = config.getoption('lab')
    backup_src = config.getoption('backup_src')
    backup_build_id = config.getoption('backup_build_id')
    backup_builds_dir = config.getoption('backup_builds_dir')
    setups.set_install_params(lab=lab_arg, skip_labsetup=None, resume=None, installconf_path=None,
                              controller0_ceph_mon_device=None, controller1_ceph_mon_device=None, ceph_mon_gib=None)
    RestoreVars.set_restore_vars(backup_src=backup_src, backup_build_id=backup_build_id,
                                backup_builds_dir=backup_builds_dir)


@pytest.fixture(scope='session', autouse=True)
def setup_test_session():
    """

    """

    LOG.tc_func_start("RESTORE_TEST")
    # If controller is accessible, check if USB with backup files are avaialble
    lab = InstallVars.get_install_var('LAB')
    LOG.info("Lab info; {}".format(lab))
    backup_build_id = RestoreVars.get_restore_var("BACKUP_BUILD_ID")
    controller_node = lab['controller-0']
    extra_controller_prompt = Prompt.TIS_NODE_PROMPT_BASE.format(lab['name'].split('_')[0]) + '|' + Prompt.CONTROLLER_0
    controller_conn = install_helper.establish_ssh_connection(controller_node.host_ip,
                                                              initial_prompt=extra_controller_prompt,  fail_ok=True)

    if controller_conn:
        LOG.info("Connection established with controller-0 ....")
        ControllerClient.set_active_controller(ssh_client=controller_conn)
        LOG.tc_step("Checking if a USB flash drive with backup files is plugged in... ")
        usb_device_name = install_helper.get_usb_device_name(con_ssh=controller_conn)
        assert usb_device_name, "No USB found "
        LOG.tc_step("USB flash drive found, checking for backup files ... ")
        usb_part_info = install_helper.get_usb_device_partition_info(usb_device=usb_device_name,
                                                                     con_ssh=controller_conn)
        assert usb_part_info and len(usb_part_info) > 0, "No USB or partition found"

        usb_part_name = "{}2".format(usb_device_name)
        assert usb_part_name in usb_part_info.keys(), "No {} partition exist in USB"
        result, mount_point = install_helper.is_usb_mounted(usb_device=usb_part_name, con_ssh=controller_conn)
        if not result:
            assert install_helper.mount_usb(usb_device=usb_part_name, con_ssh=controller_conn), \
                "Unable to mount USB partition {}".format(usb_part_name)

        tis_backup_files = install_helper.get_titanium_backup_filenames_usb(usb_device=usb_part_name,
                                                                            con_ssh=controller_conn)
        assert len(tis_backup_files) >= 2, "Missing backup files: {}".format(tis_backup_files)

        #extract build id from the file name
        file_parts = tis_backup_files[0].split('_')

        file_backup_build_id  = '_'.join([file_parts[3], file_parts[4]])

        assert re.match(TIS_BLD_DIR_REGEX, file_backup_build_id), \
            " Invalid build id format {} extracted from backup_file {}"\
                .format(file_backup_build_id, tis_backup_files[0])

        if backup_build_id is not None:
            if backup_build_id != file_backup_build_id:
                LOG.info(" The build id extracted from backup file is different than specified; "
                         "Using the extracted build id {} ....".format(file_backup_build_id))

                backup_build_id = file_backup_build_id

                RestoreVars.set_restore_var(backup_build_id=backup_build_id)

    else:
        LOG.info(" SSH connection not available yet with controller-0;  USB will be checked after controller boot ....")

    assert backup_build_id, "The Build id of the system backup must be provided."


def pytest_collectstart():
    """
    Set up the ssh session at collectstart. Because skipif condition is evaluated at the collecting test cases phase.
    """
    global con_ssh
    lab = ProjVar.get_var("LAB")
    lab_name = lab['name']
    con_ssh = None


def pytest_runtest_teardown(item):
    lab = InstallVars.get_install_var('LAB')
    hostnames = [ k for k, v in lab.items() if isinstance(v, node.Node)]
    vlm_helper.unreserve_hosts(hostnames)
    con_ssh = ControllerClient.get_active_controller(lab['short_name'])
    # Delete any backup files from /opt/backups
    con_ssh.exec_sudo_cmd("rm -rf /opt/backups/*")
    con_ssh.flush()



@pytest.fixture(scope='session')
def restore_setup():

    lab = InstallVars.get_install_var('LAB')
    LOG.info("Lab info; {}".format(lab))
    hostnames = [ k for k, v in lab.items() if  isinstance(v, node.Node)]
    LOG.info("Lab hosts; {}".format(hostnames))
    bld_server = get_build_server_info(InstallVars.get_install_var('BUILD_SERVER'))
    backup_build_id = RestoreVars.get_restore_var("BACKUP_BUILD_ID")
    output_dir = ProjVar.get_var('LOG_DIR')

    LOG.info("Connecting to Build Server {} ....".format(bld_server['name']))
    bld_server_attr = dict()
    bld_server_attr['name'] = bld_server['name']
    bld_server_attr['server_ip'] = bld_server['ip']
    bld_server_attr['prompt'] = r'{}@{}\:(.*)\$ '.format(SvcCgcsAuto.USER, bld_server['name'])

    bld_server_conn = install_helper.establish_ssh_connection(bld_server_attr['name'], user=SvcCgcsAuto.USER,
                                password=SvcCgcsAuto.PASSWORD, initial_prompt=bld_server_attr['prompt'])

    bld_server_conn.exec_cmd("bash")
    bld_server_conn.set_prompt(bld_server_attr['prompt'])
    bld_server_conn.deploy_ssh_key(install_helper.get_ssh_public_key())
    bld_server_attr['ssh_conn'] = bld_server_conn
    bld_server_obj = Server(**bld_server_attr)

    # If controller is accessible, check if USB with backup files is avaialble
    controller_node = lab['controller-0']

    load_path = os.path.join(BuildServerPath.DEFAULT_WORK_SPACE, RestoreVars.get_restore_var("BACKUP_BUILDS_DIR"),
                             backup_build_id)

    InstallVars.set_install_var(tis_build_dir=load_path)

    # set up feed for controller
    if not 'vbox' in lab['name']:
        assert install_helper.set_network_boot_feed(bld_server_conn, load_path), "Fail to set up feed for controller"

    # power off hosts
    install_helper.power_off_host(hostnames)

    install_helper.boot_controller(bld_server_conn,load_path)

    # establish ssh connection with controller
    controller_prompt = Prompt.TIS_NODE_PROMPT_BASE.format(lab['name'].split('_')[0]) + '|' + Prompt.CONTROLLER_0

    controller_node.ssh_conn = install_helper.establish_ssh_connection(controller_node.host_ip,
                                                                       initial_prompt=controller_prompt)
    controller_node.ssh_conn.deploy_ssh_key()

    ControllerClient.set_active_controller(ssh_client=controller_node.ssh_conn)

    _restore_setup = {'lab': lab, 'output_dir': output_dir, 'build_server': bld_server_obj }

    return _restore_setup
