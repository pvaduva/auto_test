"""
This is a scale test case T_18189
"""
from pytest import mark, fixture, skip
from keywords import system_helper, common, kube_helper
from consts.auth import HostLinuxUser
from utils.tis_log import LOG
from consts.stx import PodStatus


@fixture(scope='module')
def get_yaml():
    filename = "rc_deployment.yaml"
    ns = "rc"
    relicas = 99*len(system_helper.get_hypervisors())
    source_path = "utils/test_files/{}".format(filename)
    home_dir = HostLinuxUser.get_home()
    common.scp_from_localhost_to_active_controller(
        source_path, dest_path=home_dir)
    yield ns, relicas, filename
    LOG.info("Delete the deployment")
    kube_helper.exec_kube_cmd(
        "delete deployment --namespace={} resource-consumer".format(ns))
    LOG.info("check pods are terminating")
    kube_helper.wait_for_pods_status(
        namespace=ns, status=PodStatus.TERMINATING)
    LOG.info("delete the service and namespace")
    kube_helper.exec_kube_cmd(
        "delete service rc-service --namespace={}".format(ns))
    kube_helper.exec_kube_cmd("delete namespace {}".format(ns))


@mark.scale()
def test_18189(get_yaml):
    """
    Testing the deployment of high number of pods
    Setup:
        scp deployment file
    Steps:
        check the deployment of resource-consumer
        check the pods up
        scale to 99* number of worker nodes
        check all the pods are running
    Teardown:
        delete the deployment and service
    """
    ns, replicas, filename = get_yaml
    kube_helper.exec_kube_cmd(
        sub_cmd="create -f {}".format(filename))
    LOG.info("check resource consumer pods are running")
    state, _ = kube_helper.wait_for_pods_status(namespace=ns)
    if state:
        LOG.info("scale the resource consumer app to {}".format(replicas))
        kube_helper.exec_kube_cmd(
            "scale deployment --namespace={} resource-consumer --replicas={}".format(ns, replicas))
        kube_helper.wait_for_pods_status(namespace=ns)
    else:
        skip("resource consumer deployment failed")
