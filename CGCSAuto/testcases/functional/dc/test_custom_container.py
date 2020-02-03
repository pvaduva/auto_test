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

def controller_precheck(controller):
    host = system_helper.get_active_controller_name()
    if controller == 'standby':
        controllers = system_helper.get_controllers(
            availability=(HostAvailState.AVAILABLE, HostAvailState.DEGRADED,
                          HostAvailState.ONLINE))
        controllers.remove(host)
        if not controllers:
            skip('Standby controller does not exist or not in good state')
        host = controllers[0]

    return host

@fixture(scope='module')
def subclouds_to_test(request):

    LOG.info("Enumerate subclouds")
    sc_auth = Tenant.get('admin_platform', dc_region='RegionOne')

    subcloud = ProjVar.get_var('PRIMARY_SUBCLOUD')

    def revert():
        LOG.fixture_step("Manage {} if unmanaged".format(subcloud))
        dc_helper.manage_subcloud(subcloud)

    request.addfinalizer(revert)

    managed_subclouds = dc_helper.get_subclouds(mgmt='managed', avail='online')
    if subcloud in managed_subclouds:
        managed_subclouds.remove(subcloud)

    ssh_map = ControllerClient.get_active_controllers_map()
    managed_subclouds = [subcloud for subcloud in managed_subclouds if subcloud in ssh_map]

    return subcloud, managed_subclouds

@fixture()
def delete_test_pod():
    LOG.info("Delete {} pod if exists".format(POD_NAME))
    kube_helper.delete_resources(resource_names=POD_NAME, fail_ok=True)


@fixture()
def copy_test_apps():
    cons_ssh = ControllerClient.get_active_controllers()
    home_dir = HostLinuxUser.get_home()
    app_dir = '{}/custom_apps/'.format(home_dir)
    common.scp_from_test_server_to_active_controllers(
                source_path=TestServerPath.CUSTOM_APPS, dest_dir=home_dir, dest_name='custom_apps/', cons_ssh=cons_ssh, timeout=60, is_dir=True)
   
    return app_dir

#@fixture()
#def check_precondition():
#   container_helper.get_apps

@fixture()
def cleanup_app():
    if container_helper.get_apps(application=HELM_APP_NAME):
        LOG.fixture_step("Remove {} app if applied".format(HELM_APP_NAME))
        container_helper.remove_app(app_name=HELM_APP_NAME)

        LOG.fixture_step("Delete {} app".format(HELM_APP_NAME))
        container_helper.delete_app(app_name=HELM_APP_NAME)

#def test_dc_custom_application_central(copy_test_apps, subclouds_to_test):
#
#    app_dir = copy_test_apps
#
#    LOG.tc_step("Upload helm charts via helm-upload cmd from active controller "
#                "and check charts are in /www/pages/")
#
#    file_path = container_helper.upload_helm_charts(
#        tar_file=os.path.join(app_dir, HELM_TAR), delete_first=True)[1]
#
#    if system_helper.get_standby_controller_name():
#        LOG.tc_step("Swact active controller and verify uploaded charts "
#                    "are synced over")
#        host_helper.swact_host()
#        con_ssh = ControllerClient.get_active_controller()
#        charts_exist = con_ssh.file_exists(file_path)
#        assert charts_exist, "{} does not exist after swact to {}".format(
#            file_path, con_ssh.get_hostname())
#        LOG.info("{} successfully synced after swact".format(file_path))
#
#    subcloud, managed_subclouds = subclouds_to_test
#    central_auth = Tenant.get('admin_platform', dc_region='SystemController')
#    exec_helm_upload_cmd()
#    LOG.info("subcloud dc_helper)= %s",  dc_helper.get_subclouds())
#    assert 0 == 1

def test_launch_app_via_sysinv(copy_test_apps, cleanup_app):
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
    LOG.info("paul ssh %s", central_auth)
    LOG.tc_step("Upload {} on system controller".format(app_name))
    container_helper.upload_app(app_name=app_name, app_version=HELM_APP_VERSION, tar_file=os.path.join(app_dir, HELM_TAR),  auth_info=central_auth)

#    LOG.tc_step("Apply {}".format(app_name))
    container_helper.apply_app(app_name=app_name, auth_info=central_auth)

#    LOG.tc_step("Remove applied app")
#    container_helper.remove_app(app_name=app_name, auth_info=central_auth)

#    LOG.tc_step("Delete uninstalled app")
#    container_helper.delete_app(app_name=app_name, auth_info=central_auth)

#    LOG.tc_step("Wait for pod terminate")
#    kube_helper.wait_for_resources_gone(resource_names=HELM_POD_FULL_NAME, con_ssh=central_ssh, check_interval=10, namespace='default')
    LOG.tc_step("Check docker image stored in System controller registry.local")
    code, output = cli.system(cmd="registry-image-list | fgrep hello", ssh_client=central_ssh)
#    LOG.info("code %s, output %s", code, output)
    LOG.tc_step("Upload/apply custom app on subcloud")
    for subcloud in subclouds:
        subcloud_auth = Tenant.get('admin_platform', dc_region=subcloud)
        platform_app = container_helper.get_apps(auth_info=subcloud_auth, application='platform-integ-apps')
        LOG.info('Test platform-integ-apps is applied')
        assert len(platform_app)!=0 and platform_app[0] == 'applied'

        LOG.info("paul subcloud_auth %s", subcloud_auth)
        container_helper.upload_app(app_name=app_name, app_version=HELM_APP_VERSION, tar_file=os.path.join(app_dir, HELM_TAR),  auth_info=subcloud_auth)
        container_helper.apply_app(app_name=app_name, auth_info=subcloud_auth)
        code, output = cli.system(cmd="registry-image-list | fgrep hello", ssh_client=central_ssh, auth_info=subcloud_auth)




#@mark.parametrize('controller', [
#    'active',
#    'standby'
#])
#def test_launch_pod_via_kubectl(copy_test_apps, delete_test_pod, controller):
#    """
#    Test custom pod apply and delete
#    Args:
#        copy_test_apps (str): module fixture
#        delete_test_pod: fixture
#        controller: test param
#
#    Setups:
#        - Copy test files from test server to tis system (module)
#        - Delete test pod if already exists on system
#
#    Test Steps:
#        - ssh to given controller
#        - kubectl apply custom pod yaml and verify custom pod is added to
#            both controllers (if applicable)
#        - kubectl delete custom pod and verify it is removed from both
#            controllers (if applicable)
#
#    """
#    host = controller_precheck(controller)
#
#    LOG.info("paul check host %s", host)
#
#    cons_ssh = ControllerClient.get_active_controllers_map()
#
#    LOG.info("paul ssh map %s", cons_ssh)
#
#    managed_subclouds = dc_helper.get_subclouds(mgmt='managed', avail='online')
#
#    LOG.info("paul managed_clouds %s", managed_subclouds)
#    with host_helper.ssh_to_host(hostname=host) as con_ssh:
#        app_path = os.path.join(copy_test_apps, POD_YAML)
#        LOG.tc_step('kubectl apply {}, and check {} pod is created and '
#                    'running'.format(POD_YAML, POD_NAME))
#        kube_helper.apply_pod(file_path=app_path, pod_name=POD_NAME,
#                              check_both_controllers=True, con_ssh=con_ssh)
#
#        LOG.tc_step("Delete {} pod and check it's removed from both "
#                    "controllers if applicable".format(POD_NAME))
#        kube_helper.delete_resources(resource_names=POD_NAME, con_ssh=con_ssh)



#def test_dc_custom_application(subclouds_to_test):
#    subcloud, managed_subclouds = subclouds_to_test
#    central_auth = Tenant.get('admin_platform', dc_region='SystemController')
#    LOG.info("subcloud dc_helper)= %s",  dc_helper.get_subclouds())
#    assert 0 == 1
