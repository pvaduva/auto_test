import os
import re

from pytest import fixture, mark, skip

from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient
from utils.clients.local import LocalHostClient

from keywords import common, kube_helper, host_helper, system_helper, container_helper, keystone_helper
from consts.filepaths import TestServerPath, WRSROOT_HOME
from consts.cgcs import HostAvailState
from consts.proj_vars import ProjVar

POD_YAML = 'hellokitty.yaml'
POD_NAME = 'hellokitty'

HELM_TAR = 'hello-kitty.tgz'
HELM_APP_NAME = 'hello-kitty'
HELM_POD_FULL_NAME = 'hk-hello-kitty-hello-kit'
HELM_MSG = '<h3>Hello Kitty World!</h3>'


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


@mark.parametrize('controller', [
    'active',
    'standby'
])
def test_pod_apply_and_delete(copy_test_apps, delete_test_pod, controller):
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
        - kubectl apply custom pod yaml and verify custom pod is added to system
        - kubectl delete custom pod and verify it is removed from system

    """
    host = system_helper.get_active_controller_name()
    if controller == 'standby':
        controllers = system_helper.get_controllers(availability=(HostAvailState.AVAILABLE, HostAvailState.DEGRADED,
                                                                  HostAvailState.ONLINE))
        controllers.remove(host)
        if not controllers:
            skip('Standby controller does not exist or not in good state')
        host = controllers[0]

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


def test_app_launch_via_helmchart(copy_test_apps, cleanup_app):
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
