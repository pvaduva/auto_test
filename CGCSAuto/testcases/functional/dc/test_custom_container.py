import os, pdb
from pytest import fixture, skip, mark

from keywords import security_helper, keystone_helper, dc_helper
from utils import cli
from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient
from utils.clients.local import LocalHostClient
from consts.filepaths import TestServerPath, StxPath
from consts.auth import Tenant, HostLinuxUser
from consts.stx import HostAvailState, Container
from consts.proj_vars import ProjVar
from keywords import common, dc_helper, system_helper, host_helper, container_helper, kube_helper

POD_YAML = 'hellokitty.yaml'
POD_NAME = 'hellokitty'

HELM_TAR = 'hello-kitty.tgz'
HELM_APP_NAME = 'hello-kitty'
HELM_APP_VERSION = '1.16'
HELM_POD_FULL_NAME = 'hk-hello-kitty-hello-kit'
HELM_MSG = '<h3>Hello MONSTER Kitty World!</h3>'


@fixture()
def copy_test_apps():
    cons_ssh = ControllerClient.get_active_controllers()
    home_dir = HostLinuxUser.get_home()
    app_dir = '{}/custom_apps/'.format(home_dir)
    common.scp_from_test_server_to_active_controllers(
                source_path=TestServerPath.CUSTOM_APPS, dest_dir=home_dir, dest_name='custom_apps/', cons_ssh=cons_ssh, timeout=60, is_dir=True)
  
    return app_dir


def test_launch_app_via_sysinv(copy_test_apps):
    """
    Test upload, apply, remove, delete custom app via system cmd
    Args:
        copy_test_apps (str): module fixture
        cleanup_app: fixture

    Setups:
        - Copy test files from test server to tis system (module)
        - Remove and delete test app if exists

    Test Steps:
        - system application-upload test app tar file and wait for it to be
            uploaded
        - system application-apply test app and wait for it to be applied
        - wget <oam_ip>:<app_targetPort> from remote host
        - Verify app contains expected content
        - system application-remove test app and wait for it to be uninstalled
        - system application-delete test app from system

    """
    app_dir = copy_test_apps
    app_name = HELM_APP_NAME

    central_ssh = ControllerClient.get_active_controller(name='RegionOne')
    central_auth = Tenant.get('admin_platform', dc_region='SystemController')
    platform_app = container_helper.get_apps(auth_info=central_auth, application='platform-integ-apps')
    LOG.info('Test platform-integ-apps is applied')
    assert len(platform_app)!=0 and platform_app[0] == 'applied'
    subclouds = dc_helper.get_subclouds()
    LOG.tc_step("Upload and apply {} on system controller".format(app_name))
    container_helper.upload_app(app_name=app_name, app_version=HELM_APP_VERSION, tar_file=os.path.join(app_dir, HELM_TAR),  auth_info=central_auth)

    container_helper.apply_app(app_name=app_name, auth_info=central_auth)
    LOG.tc_step("Check docker image stored in System controller registry.local")
    code, output = cli.system(cmd="registry-image-list | fgrep hellokitty", ssh_client=central_ssh, fail_ok=True)
    assert code == 0
#    LOG.info("code %s, output %s", code, output)
    for subcloud in subclouds:
        subcloud_auth = Tenant.get('admin_platform', dc_region=subcloud)
        LOG.tc_step("Upload/apply custom app on subcloud: {}".format(subcloud))
        platform_app = container_helper.get_apps(auth_info=subcloud_auth, application='platform-integ-apps')
        LOG.info('Test platform-integ-apps is applied, on subcloud {}'.format(subcloud))
        assert len(platform_app)!=0 and platform_app[0] == 'applied'

        LOG.tc_step("Upload and apply {} on subcloud: {}".format(app_name, subcloud))
        container_helper.upload_app(app_name=app_name, app_version=HELM_APP_VERSION, tar_file=os.path.join(app_dir, HELM_TAR),  auth_info=subcloud_auth)
        container_helper.apply_app(app_name=app_name, auth_info=subcloud_auth)
        LOG.tc_step("Check docker image stored on {} registry.central".format(subcloud))
        code, output = cli.system(cmd="registry-image-list | fgrep hellokitty", ssh_client=central_ssh, auth_info=subcloud_auth, fail_ok=True)
        assert code == 0
