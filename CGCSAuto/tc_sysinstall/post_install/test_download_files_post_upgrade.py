import pytest

from consts.auth import SvcCgcsAuto
from consts.build_server import Server, get_build_server_info
from consts.stx import Prompt
from consts.filepaths import BuildServerPath
from consts.proj_vars import ProjVar, InstallVars
from keywords import install_helper, system_helper
from utils.clients.ssh import SSHClient, ControllerClient
from utils.tis_log import LOG


@pytest.fixture(scope='function')
def pre_download_setup():

    lab = InstallVars.get_install_var('LAB')

    # establish ssh connection with controller-0
    controller0_conn = ControllerClient.get_active_controller()
    cpe = system_helper.is_aio_system(controller0_conn)

    bld_server = get_build_server_info(InstallVars.get_install_var('BUILD_SERVER'))

    output_dir = ProjVar.get_var('LOG_DIR')

    current_version = system_helper.get_sw_version(use_existing=False)
    load_path = BuildServerPath.LATEST_HOST_BUILD_PATHS[current_version]

    bld_server_attr = dict()
    bld_server_attr['name'] = bld_server['name']
    bld_server_attr['server_ip'] = bld_server['ip']

    bld_server_attr['prompt'] = Prompt.BUILD_SERVER_PROMPT_BASE.format('svc-cgcsauto', bld_server['name'])

    bld_server_conn = SSHClient(bld_server_attr['name'], user=SvcCgcsAuto.USER,
                                password=SvcCgcsAuto.PASSWORD, initial_prompt=bld_server_attr['prompt'])
    bld_server_conn.connect()
    bld_server_conn.exec_cmd("bash")
    bld_server_conn.set_prompt(bld_server_attr['prompt'])
    bld_server_conn.deploy_ssh_key(install_helper.get_ssh_public_key())
    bld_server_attr['ssh_conn'] = bld_server_conn
    bld_server_obj = Server(**bld_server_attr)

    _download_setup = {'lab': lab,
                       'cpe': cpe,
                       'output_dir': output_dir,
                       'current_version': current_version,
                       'build_server': bld_server_obj,
                       'load_path': load_path,
                      }

    return _download_setup


def test_download_post_upgrade(pre_download_setup):
    """
    This test downloads lab setup scripts and images from build server to the upgraded lab based on the version.
    The following are downloaded:
     - images
     - heat templates
     - lab config files and setup scripts

    Args:


    Returns:

    """

    lab = pre_download_setup['lab']
    current_version = pre_download_setup['current_version']
    bld_server = pre_download_setup['build_server']
    load_path = pre_download_setup['load_path']

    LOG.tc_step("Downloading images to upgraded {} lab ".format(current_version))
    install_helper.download_image(lab, bld_server, BuildServerPath.GUEST_IMAGE_PATHS[current_version])

    LOG.tc_step("Downloading heat templates to upgraded {} lab ".format(current_version))
    install_helper.download_heat_templates(lab, bld_server, load_path)

    LOG.tc_step("Downloading lab config scripts to upgraded {} lab ".format(current_version))
    install_helper.download_lab_config_files(lab, bld_server, load_path)



