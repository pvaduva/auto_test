import yaml

from pytest import mark, xfail, fixture

from utils.tis_log import LOG
from utils import rest

from consts.proj_vars import ProjVar
from consts.auth import HostLinuxUser
from consts.stx import PodStatus
from keywords import system_helper, kube_helper, common

client_pod_name = "client-pod"
server_dep = "server-pod"
service_name = "test-app"


def get_yaml_data(filepath):
    """
    Returns the yaml data in json
    Args:
        filepath(str): location of the yaml file to load
    Return(json):
        returns the json data
    """
    with open(filepath, 'r') as f:
        data = yaml.safe_load(f)
    return data


def write_to_file(data, filename):
    """
    Writes data to a file in yaml format
    Args:
        data(json): data in json format
        filename(str): filename
    Return(str):
        returns the location of the yaml file
    """
    src_path = "{}/{}".format(ProjVar.get_var('LOG_DIR'), filename)
    with open(src_path, 'w') as f:
        yaml.dump(data, f)
    return src_path


@fixture(scope="class")
def deploy_test_pods():
    """
    Fixture to deploy the server app,client app and yeild server pod ips
        - Label the nodes and add node selector to the deployment files
            if not simplex system
        - Copy the deployment files from localhost to active controller
        - Deploy server pod
        - Deploy client pod
        - Get the server pods and client pods and check status
        - Get the ip address of the server pods
        - Delete the service
        - Delete the server pod deployment
        - Delete the client pod
        - Remove the labels on the nodes if not simplex
    """
    server_pod = "server_pod.yaml"
    client_pod = "client_pod.yaml"
    home_dir = HostLinuxUser.get_home()

    server_pod_path = "utils/test_files/{}".format(server_pod)
    client_pod_path = "utils/test_files/{}".format(client_pod)

    computes = system_helper.get_hypervisors(
        operational="enabled", availability="available")
    if len(computes) > 1:
        LOG.fixture_step("Label the nodes and add node selector to the deployment files\
        if not simplex system")
        kube_helper.exec_kube_cmd(sub_cmd="label nodes {}".format(
            computes[0]), args="test=server")
        kube_helper.exec_kube_cmd(sub_cmd="label nodes {}".format(
            computes[1]), args="test=client")
        data = get_yaml_data(server_pod_path)
        data['spec']['template']['spec']['nodeSelector'] = {'test': 'server'}
        server_pod_path = write_to_file(data, server_pod)

        data = get_yaml_data(client_pod_path)
        data['spec']['nodeSelector'] = {'test': 'client'}
        client_pod_path = write_to_file(data, client_pod)

    LOG.fixture_step(
        "Copy the deployment files from localhost to active controller")
    common.scp_from_localhost_to_active_controller(
        source_path=server_pod_path, dest_path=home_dir)

    common.scp_from_localhost_to_active_controller(
        source_path=client_pod_path, dest_path=home_dir)
    LOG.fixture_step("Deploy server pods {}".format(server_pod))
    kube_helper.exec_kube_cmd(sub_cmd="create -f ", args=server_pod)
    LOG.fixture_step("Deploy client pod {}".format(client_pod))
    kube_helper.exec_kube_cmd(sub_cmd="create -f ", args=client_pod)

    LOG.fixture_step("Get the server pods and client pods and check status")
    get_server_pods = kube_helper.get_pods(labels="run=load-balancer-1")
    all_pods = get_server_pods.append(client_pod_name)

    state, output = kube_helper.wait_for_pods_status(
        pod_names=all_pods, namespace="default")

    if not state:
        xfail("Pods has the following error {},Hence failing this test".format(output))

    LOG.fixture_step("Get the ip address of the server pods")
    server_ips = []
    for i in get_server_pods:
        server_ips.append(kube_helper.get_pod_value_jsonpath(
            "pod {}".format(i), "{.status.podIP}"))

    yield server_ips
    LOG.fixture_step("Delete the service {}".format(service_name))
    kube_helper.exec_kube_cmd(sub_cmd="delete service  ", args=service_name)
    LOG.fixture_step("Delete the deployment {}".format(server_dep))
    kube_helper.exec_kube_cmd(sub_cmd="delete deployment  ", args=server_dep)
    LOG.fixture_step("Delete the pod {}".format(client_pod_name))
    kube_helper.exec_kube_cmd(sub_cmd="delete pod  ", args=client_pod_name)
    if len(computes) > 1:
        LOG.fixture_step("Remove the labels on the nodes if not simplex")
        kube_helper.exec_kube_cmd(sub_cmd="label nodes {}".format(
            computes[0]), args="test-")
        kube_helper.exec_kube_cmd(sub_cmd="label nodes {}".format(
            computes[1]), args="test-")


@mark.networking
class TestPodtoPod:
    def test_pod_to_pod_ping(self, deploy_test_pods):
        """
        Verify Ping test between pods
        Args:
            deploy_test_pods(fixture): yields the pod ips list
        Steps:
            - Ping the server pod ip from the client pod

        """
        for ip in deploy_test_pods:
            LOG.tc_step("Ping the server pod ip {} from the client pod {}".format(
                ip, client_pod_name))
            cmd = "ping -c 3 {} -w 5".format(ip)
            code, _ = kube_helper.exec_cmd_in_container(
                cmd=cmd, pod=client_pod_name)
            assert code == 0

    def test_pod_to_service_endpoints(self, deploy_test_pods):
        """
        Verify client pod to service  multiple endpoints access
        Args:
            deploy_test_pods(fixture): yields the pod ips list
        Steps:
            - Curl the server pod ip from the client pod

        """
        for ip in deploy_test_pods:
            if ProjVar.get_var('IPV6_OAM'):
                ip = "[{}]".format(ip)
            cmd = "curl -Is {}:8080".format(ip)
            LOG.tc_step("Curl({}) the server pod ip {} from the client pod {}".format(
                cmd, ip, client_pod_name))
            code, _ = kube_helper.exec_cmd_in_container(
                cmd=cmd, pod=client_pod_name)
            assert code == 0

    def test_local_host_to_service(self):
        """
        Verify the service connectivity from external network
        Steps:
            - Expose the service with NodePort
            - Check the service access from local host
        """
        LOG.tc_step("Expose the service {} with NodePort".format(service_name))
        kube_helper.expose_the_service(
            deployment_name=server_dep, type="NodePort", service_name=service_name)
        node_port = kube_helper.get_pod_value_jsonpath(
            "service {}".format(service_name), "{.spec.ports[0].nodePort}")
        out = system_helper.get_oam_values()
        ip = []
        if system_helper.is_aio_simplex():
            ip.append(out["oam_ip"])
        else:
            ip.append(out["oam_floating_ip"])
            ip.append(out["oam_c0_ip"])
            ip.append(out["oam_c1_ip"])
        for i in ip:
            url = "http://{}:{}".format(i, node_port)
            LOG.tc_step(
                "Check the service access {} from local host".format(url))
            rest.check_url(url)
