import os
import re

from pytest import fixture, mark, skip

from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient
from utils.clients.local import LocalHostClient

from keywords import common, kube_helper, host_helper, system_helper, container_helper, keystone_helper
from consts.filepaths import TestServerPath, WRSROOT_HOME, TiSPath
from consts.cgcs import HostAvailState
from consts.proj_vars import ProjVar

POD_YAML = 'hellokitty.yaml'
POD_NAME = 'hellokitty'

HELM_TAR = 'hello-kitty.tgz'
HELM_APP_NAME = 'hello-kitty'
HELM_POD_FULL_NAME = 'hk-hello-kitty-hello-kit'
HELM_MSG = '<h3>Hello Kitty World!</h3>'

TEST_IMAGE = 'busybox'


@fixture(scope='module')
def copy_test_apps():
    con_ssh = ControllerClient.get_active_controller()
    app_dir = os.path.join(WRSROOT_HOME, 'custom_apps/')
    if not con_ssh.file_exists(app_dir + POD_YAML):
        common.scp_from_test_server_to_active_controller(source_path=TestServerPath.CUSTOM_APPS, con_ssh=con_ssh,
                                                         dest_dir=WRSROOT_HOME, timeout=60, is_dir=True)

    if not system_helper.is_simplex():
        dest_host = 'controller-1' if con_ssh.get_hostname() == 'controller-0' else 'controller-0'
        con_ssh.rsync(source=app_dir, dest_server=dest_host, dest=app_dir, timeout=60)

    return app_dir


@fixture()
def delete_test_pod():
    LOG.info("Delete {} pod if exists".format(POD_NAME))
    kube_helper.delete_pods(pod_names=POD_NAME, fail_ok=True)


@mark.platform
@mark.parametrize('controller', [
    'active',
    'standby'
])
def test_launch_app_via_kubectl(copy_test_apps, delete_test_pod, controller):
    """
    Test custom pod apply and delete
    Args:
        copy_test_apps (str): module fixture
        delete_test_pod: fixture
        controller: test param

    Setups:
        - Copy test files from test server to tis system (module)
        - Delete test pod if already exists on system

    Test Steps:
        - ssh to given controller
        - kubectl apply custom pod yaml and verify custom pod is added to both controllers (if applicable)
        - kubectl delete custom pod and verify it is removed from both controllers (if applicable)

    """
    host = controller_precheck(controller)

    with host_helper.ssh_to_host(hostname=host) as con_ssh:
        app_path = os.path.join(copy_test_apps, POD_YAML)
        LOG.tc_step('kubectl apply {}, and check {} pod is created and running'.format(POD_YAML, POD_NAME))
        kube_helper.apply_pod(file_path=app_path, pod_name=POD_NAME, check_both_controllers=True, con_ssh=con_ssh)

        LOG.tc_step("Delete {} pod and check it's removed from both controllers if applicable".format(POD_NAME))
        kube_helper.delete_pods(pod_names=POD_NAME, con_ssh=con_ssh)


@fixture()
def cleanup_app():
    if container_helper.get_apps_values(apps=HELM_APP_NAME)[0]:
        LOG.fixture_step("Remove {} app if applied".format(HELM_APP_NAME))
        container_helper.remove_app(app_name=HELM_APP_NAME)

        LOG.fixture_step("Delete {} app".format(HELM_APP_NAME))
        container_helper.delete_app(app_name=HELM_APP_NAME)


@mark.platform
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
        - system application-upload test app tar file and wait for it to be uploaded
        - system application-apply test app and wait for it to be applied
        - wget <oam_ip>:<app_targetPort> from remote host
        - Verify app contains expected content
        - system application-remove test app and wait for it to be uninstalled
        - system application-delete test app from system

    """
    app_dir = copy_test_apps
    app_name = HELM_APP_NAME

    # Test fails at upload, possible workaround: sudo install -d -o www -g root -m 755 /www/pages/helm_charts
    LOG.tc_step("Upload {} helm charts".format(app_name))
    container_helper.upload_app(app_name=app_name, tar_file=os.path.join(app_dir, HELM_TAR))

    LOG.tc_step("Apply {}".format(app_name))
    container_helper.apply_app(app_name=app_name)

    LOG.tc_step("wget app via <oam_ip>:<targetPort>")
    json_path = '{.spec.ports[0].nodePort}'
    node_port = kube_helper.get_pod_value_jsonpath(type_name='service/{}'.format(HELM_POD_FULL_NAME),
                                                   jsonpath=json_path)
    assert re.match(r'\d+', node_port), "Unable to get nodePort via jsonpath '{}'".format(json_path)

    localhost = LocalHostClient(connect=True)
    prefix = 'https' if keystone_helper.is_https_lab() else 'http'
    oam_ip = ProjVar.get_var('LAB')['floating ip']
    output_file = '{}/{}.html'.format(ProjVar.get_var('TEMP_DIR'), HELM_APP_NAME)
    localhost.exec_cmd('wget {}://{}:{} -O {}'.format(prefix, oam_ip, node_port, output_file), fail_ok=False)

    LOG.tc_step("Verify app contains expected content")
    app_content = localhost.exec_cmd('cat {}; echo'.format(output_file), get_exit_code=False)[1]
    assert app_content.startswith(HELM_MSG), "App does not start with expected message."

    LOG.tc_step("Remove applied app")
    container_helper.remove_app(app_name=app_name)

    LOG.tc_step("Delete uninstalled app")
    container_helper.delete_app(app_name=app_name)


def remove_cache_and_pull(con_ssh, name, fail_ok=False):
    container_helper.remove_docker_images(images=(TEST_IMAGE, name), con_ssh=con_ssh, fail_ok=fail_ok)
    container_helper.pull_docker_image(name=name, con_ssh=con_ssh)


@mark.platform
@mark.parametrize('controller', [
    'active',
    'standby'
])
def test_push_docker_image_to_local_registry(controller):
    """

    Args:
        controller:

    Setup:
        - Copy test files from test server to tis system (module)

    Test Steps:
      On specified controller (active or standby):
        - Pull test image busybox and get its ID
        - Remove busybox repo from local registry if exists
        - Tag image with local registry
        - Push test image to local registry
        - Remove cached test images
        - Pull test image from local registry
      On the other controller if exists, verify local registry is synced:
        - Remove cached test images
        - Pull test image from local registry

    """
    host = controller_precheck(controller)
    controllers = system_helper.get_controllers(availability=(HostAvailState.AVAILABLE, HostAvailState.DEGRADED,
                                                              HostAvailState.ONLINE))
    controllers.remove(host)

    with host_helper.ssh_to_host(hostname=host) as con_ssh:

        LOG.tc_step("Pull {} image from external on {} controller {}".format(TEST_IMAGE, controller, host))
        image_id = container_helper.pull_docker_image(name=TEST_IMAGE, con_ssh=con_ssh)[1]

        LOG.tc_step("Remove {} from local registry if exists".format(TEST_IMAGE))
        con_ssh.exec_sudo_cmd('rm -rf {}/{}'.format(TiSPath.DOCKER_REPO, TEST_IMAGE))

        reg_addr = container_helper.get_docker_reg_addr(con_ssh=con_ssh)
        target_name = '{}/{}'.format(reg_addr, TEST_IMAGE)

        LOG.tc_step("Tag image with local registry")
        container_helper.tag_docker_image(source_image=image_id, target_name=target_name, con_ssh=con_ssh)

        LOG.tc_step("Push test image to local registry from {} controller {}".format(controller, host))
        container_helper.push_docker_image(target_name, con_ssh=con_ssh)

        LOG.tc_step("Remove cached test images and pull from local registry on {}".format(host))
        remove_cache_and_pull(con_ssh=con_ssh, name=target_name)
        container_helper.remove_docker_images(images=(target_name, ), con_ssh=con_ssh)

        if controllers:
            other_host = controllers[0]
            with host_helper.ssh_to_host(other_host, con_ssh=con_ssh) as other_ssh:
                LOG.tc_step( "Remove cached test images on the other controller {} if exists and pull from local "
                             "registry".format(other_host))
                remove_cache_and_pull(con_ssh=other_ssh, name=target_name, fail_ok=True)
                container_helper.remove_docker_images(images=(target_name,), con_ssh=other_ssh)

        LOG.tc_step("Cleanup {} from local docker registry after test".format(TEST_IMAGE))
        con_ssh.exec_sudo_cmd('rm -rf {}/{}'.format(TiSPath.DOCKER_REPO, TEST_IMAGE))


@mark.platform
@mark.parametrize('controller', [
    'active',
    'standby'
])
def test_upload_helm_charts(copy_test_apps, controller):
    """
    Test upload helm charts from given controller
    Args:
        copy_test_apps:
        controller:

    Setups:
        - Copy test files from test server to tis system (module)

    Test Steps:
        - Upload helm charts from given controller
        - Verify the charts appear on both controllers (if applicable)

    """
    app_dir = copy_test_apps
    host = controller_precheck(controller)

    LOG.tc_step("Upload helm charts from {} controller {}, and verify it appears on both controllers (if applicable)".
                format(controller, host))
    with host_helper.ssh_to_host(hostname=host) as con_ssh:
        container_helper.upload_helm_charts(tar_file=os.path.join(app_dir, HELM_TAR), delete_first=True,
                                            con_ssh=con_ssh)


def controller_precheck(controller):
    host = system_helper.get_active_controller_name()
    if controller == 'standby':
        controllers = system_helper.get_controllers(availability=(HostAvailState.AVAILABLE, HostAvailState.DEGRADED,
                                                                  HostAvailState.ONLINE))
        controllers.remove(host)
        if not controllers:
            skip('Standby controller does not exist or not in good state')
        host = controllers[0]

    return host
