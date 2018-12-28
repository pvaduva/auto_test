import os
from pytest import fixture, mark, skip

from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient
from keywords import common, kube_helper, host_helper, system_helper
from consts.filepaths import TestServerPath, WRSROOT_HOME

POD_NAME = 'hellokitty'
APP_FILE = 'hellokitty.yaml'
HELM_CHART_FILE = 'hello-kitty.tgx'


@fixture(scope='module')
def copy_test_apps():
    con_ssh = ControllerClient.get_active_controller()
    app_dir = os.path.join(WRSROOT_HOME, 'custom_apps/')
    if not con_ssh.file_exists(app_dir + APP_FILE):
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
    'controller-0',
    'controller-1'
])
def test_kube_pod_apply_and_delete(copy_test_apps, delete_test_pod, controller):
    controllers = system_helper.get_controllers()
    if controller not in controllers:
        skip('{} does not exist on system'.format(controller))

    with host_helper.ssh_to_host(hostname=controller) as con_ssh:
        app_path = os.path.join(copy_test_apps, APP_FILE)
        LOG.tc_step('Kubectrl apply {}, and check {} pod is created and running'.format(APP_FILE, POD_NAME))
        kube_helper.apply_pod(file_path=app_path, pod_name=POD_NAME, check_both_controllers=True, con_ssh=con_ssh)

        LOG.tc_step("Delete {} pod and check it's removed from both controllers if applicable".format(POD_NAME))
        kube_helper.delete_pods(pod_names=POD_NAME, con_ssh=con_ssh)
