from pytest import fixture, mark
from keywords import kube_helper, common
from consts.auth import HostLinuxUser
from utils.tis_log import LOG
import json


@fixture(scope='module')
def copy_pod_yamls():
    home_dir = HostLinuxUser.get_home()
    LOG.info("Copying yaml files")
    common.scp_from_localhost_to_active_controller(
        source_path="utils/test_files/qos/", dest_path=home_dir, is_dir=True)
    LOG.info("Create qos-example namespace")
    kube_helper.exec_kube_cmd(sub_cmd="create namespace qos-example")
    yield
    LOG.info("Delete all pods in namespace qos-example")
    kube_helper.exec_kube_cmd(
        sub_cmd="delete pods --all --namespace=qos-example")
    LOG.info("Delete the namespace")
    kube_helper.exec_kube_cmd(sub_cmd="delete namespace qos-example")


@mark.qos()
@mark.parametrize('expected,pod', [("Guaranteed", "qos-pod.yaml"),
                                   ("Burstable", "qos-pod-2.yaml"),
                                   ("BestEffort", "qos-pod-3.yaml"),
                                   ("Burstable", "qos-pod-4.yaml")])
def test_qos_tests(copy_pod_yamls, expected, pod):
    """
    Testing the Qos for pods
    Setup:
        scp qos pod yaml files
        create a namespace for the qos pods
    Steps:
        create qos pod
        check status of the pod
        check the qos-class type is as expected
    Teardown:
        delete all pods in qos-example namespace
        delete the namespace

    """
    kube_helper.exec_kube_cmd(
        sub_cmd="create -f {}/{}".format("qos_pods", pod))
    kube_helper.wait_for_pods_status(pod_names=pod.split(".")[
                                     0], namespace="qos-example")
    _, out = kube_helper.exec_kube_cmd(
        sub_cmd="get pod {} --namespace=qos-example --output=json".format(pod.split(".")[0]))
    out = json.loads(out)
    assert out["status"]["qosClass"] == expected
