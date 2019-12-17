from pytest import fixture, mark, skip
from keywords import kube_helper, common
from consts.auth import HostLinuxUser
from utils.tis_log import LOG
import json


@fixture(scope='module')
def copy_pod_yamls():
    home_dir = HostLinuxUser.get_home()
    filename = "qos_deployment.yaml"
    ns = "qos"
    LOG.info("Copying deployment yaml file")
    common.scp_from_localhost_to_active_controller(
        source_path="utils/test_files/{}".format(filename), dest_path=home_dir)
    kube_helper.exec_kube_cmd(
        sub_cmd="create -f {}".format(filename))
    yield ns
    LOG.info("Delete all pods in namespace {}".format(ns))
    kube_helper.exec_kube_cmd(
        sub_cmd="delete pods --all --namespace={}".format(ns))
    LOG.info("Delete the namespace")
    kube_helper.exec_kube_cmd(sub_cmd="delete namespace {}".format(ns))


@mark.qos()
@mark.parametrize('expected,pod', [("Guaranteed", "qos-pod"),
                                   ("Burstable", "qos-pod-2"),
                                   ("BestEffort", "qos-pod-3"),
                                   ("Burstable", "qos-pod-4")])
def test_qos_tests(copy_pod_yamls, expected, pod):
    """
    Testing the Qos class for pods
    Setup:
        scp qos pod yaml files
        create the deployment of namespace and qos pods
    Steps:
        check status of the pod
        check the qos-class type is as expected
    Teardown:
        delete all pods in qos-example namespace
        delete the namespace

    """
    ns = copy_pod_yamls
    kube_helper.wait_for_pods_status(pod_names=pod, namespace=ns)
    _, out = kube_helper.exec_kube_cmd(
        sub_cmd="get pod {} --namespace={} --output=json".format(pod, ns))
    out = json.loads(out)
    LOG.info("pod qos class is {} and expected is {}".format(
        out["status"]["qosClass"], expected))
    assert out["status"]["qosClass"] == expected
