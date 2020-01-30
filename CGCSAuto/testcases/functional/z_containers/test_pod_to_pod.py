import yaml
import copy

from pytest import mark, fixture

from utils.tis_log import LOG
from utils import rest

from consts.proj_vars import ProjVar
from consts.auth import HostLinuxUser
from consts.stx import PodStatus
from keywords import system_helper, kube_helper, common

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
def deploy_test_pods(request):
    """
    Fixture to deploy the server app,client app and returns serverips & client pods
        - Label the nodes and add node selector to the deployment files
            if not simplex system
        - Copy the deployment files from localhost to active controller
        - Deploy server pod
        - Deploy client pods
        - Get the server pods and client pods and check status
        - Get the ip address of the server pods
        - Delete the service
        - Delete the server pod deployment
        - Delete the client pods
        - Remove the labels on the nodes if not simplex
    """
    server_pod = "server_pod.yaml"
    client_pod_template = "client_pod.yaml"
    home_dir = HostLinuxUser.get_home()
    client_pod1_name = "client-pod1"
    client_pod2_name = "client-pod2"

    server_pod_path = "utils/test_files/{}".format(server_pod)
    client_pod_path = "utils/test_files/{}".format(client_pod_template)

    server_pod_data = get_yaml_data(server_pod_path)
    client_pod1_data = get_yaml_data(client_pod_path)
    client_pod2_data = copy.deepcopy(client_pod1_data)

    client_pod1_data['metadata']['name'] = client_pod1_name
    client_pod2_data['metadata']['name'] = client_pod2_name

    computes = system_helper.get_hypervisors(
        operational="enabled", availability="available")

    if len(computes) > 1:
        LOG.fixture_step("Label the nodes and add node selector to the deployment files\
        if not simplex system")
        kube_helper.exec_kube_cmd(sub_cmd="label nodes {}".format(
            computes[0]), args="test=server")
        kube_helper.exec_kube_cmd(sub_cmd="label nodes {}".format(
            computes[1]), args="test=client")
        server_pod_data['spec']['template']['spec']['nodeSelector'] = {
            'test': 'server'}
        client_pod1_data['spec']['nodeSelector'] = {'test': 'server'}
        client_pod2_data['spec']['nodeSelector'] = {'test': 'client'}

    server_pod_path = write_to_file(server_pod_data, server_pod)
    client_pod1_path = write_to_file(
        client_pod1_data, "{}.yaml".format(client_pod1_name))
    client_pod2_path = write_to_file(
        client_pod2_data, "{}.yaml".format(client_pod2_name))

    LOG.fixture_step(
        "Copy the deployment files from localhost to active controller")
    common.scp_from_localhost_to_active_controller(
        source_path=server_pod_path, dest_path=home_dir)

    common.scp_from_localhost_to_active_controller(
        source_path=client_pod1_path, dest_path=home_dir)

    common.scp_from_localhost_to_active_controller(
        source_path=client_pod2_path, dest_path=home_dir)

    LOG.fixture_step("Deploy server pods {}".format(server_pod))
    kube_helper.exec_kube_cmd(sub_cmd="create -f ", args=server_pod)
    LOG.fixture_step("Deploy client pod {}.yaml & client pod {}.yaml".format(
        client_pod1_name, client_pod2_name))
    kube_helper.exec_kube_cmd(sub_cmd="create -f ",
                              args="{}.yaml".format(client_pod1_name))

    kube_helper.exec_kube_cmd(sub_cmd="create -f ",
                              args="{}.yaml".format(client_pod2_name))

    LOG.fixture_step("Get the server pods and client pods and check status")
    get_server_pods = kube_helper.get_pods(labels="run=load-balancer-1")
    all_pods = get_server_pods+[client_pod1_name, client_pod2_name]

    kube_helper.wait_for_pods_status(
        pod_names=all_pods, namespace="default")

    LOG.fixture_step("Get the ip address of the server pods")
    server_ips = []
    for i in get_server_pods:
        server_ips.append(kube_helper.get_pod_value_jsonpath(
            "pod {}".format(i), "{.status.podIP}"))

    def teardown():
        LOG.fixture_step("Delete the service {}".format(service_name))
        kube_helper.exec_kube_cmd(
            sub_cmd="delete service  ", args=service_name)
        LOG.fixture_step("Delete the deployment {}".format(server_dep))
        kube_helper.exec_kube_cmd(
            sub_cmd="delete deployment  ", args=server_dep)
        LOG.fixture_step("Delete the client pods {} & {}".format(
            client_pod1_name, client_pod2_name))
        kube_helper.exec_kube_cmd(
            sub_cmd="delete pod  ", args=client_pod1_name)
        kube_helper.exec_kube_cmd(
            sub_cmd="delete pod  ", args=client_pod2_name)
        if len(computes) > 1:
            LOG.fixture_step("Remove the labels on the nodes if not simplex")
            kube_helper.exec_kube_cmd(sub_cmd="label nodes {}".format(
                computes[0]), args="test-")
            kube_helper.exec_kube_cmd(sub_cmd="label nodes {}".format(
                computes[1]), args="test-")

    request.addfinalizer(teardown)
    return server_ips, [client_pod1_name, client_pod2_name]


@mark.networking
class TestPodtoPod:
    def test_pod_to_pod_ping(self, deploy_test_pods):
        """
        Verify Ping test between pods
        Args:
            deploy_test_pods(fixture): returns server ips & clientpod list
        Setup:
            - Label the nodes and add node selector to the deployment files
                if not simplex system
            - Copy the deployment files from localhost to active controller
            - Deploy server pod
            - Deploy client pods
            - Get the server pods and client pods and check status
            - Get the ip address of the server pods
        Steps:
            - Ping the server pod ip from the client pod
        Teardown:
            - Delete the service
            - Delete the server pod deployment
            - Delete the client pods
            - Remove the labels on the nodes if not simplex

        """
        server_ips, client_pods = deploy_test_pods
        for client_pod in client_pods:
            for ip in server_ips:
                LOG.tc_step("Ping the server pod ip {} from the client pod {}".format(
                    ip, client_pod))
                cmd = "ping -c 3 {} -w 5".format(ip)
                code, _ = kube_helper.exec_cmd_in_container(
                    cmd=cmd, pod=client_pod)
                assert code == 0

    def test_pod_to_service_endpoints(self, deploy_test_pods):
        """
        Verify client pod to service  multiple endpoints access
        Args:
            deploy_test_pods(fixture): returns server ips & clientpod list
        Setup:
            - Label the nodes and add node selector to the deployment files
                if not simplex system
            - Copy the deployment files from localhost to active controller
            - Deploy server pod
            - Deploy client pods
            - Get the server pods and client pods and check status
            - Get the ip address of the server pods
        Steps:
            - Curl the server pod ip from the client pod
        Teardown:
            - Delete the service
            - Delete the server pod deployment
            - Delete the client pods
            - Remove the labels on the nodes if not simplex

        """
        server_ips, client_pods = deploy_test_pods
        for client_pod in client_pods:
            for ip in server_ips:
                if ProjVar.get_var('IPV6_OAM'):
                    ip = "[{}]".format(ip)
                cmd = "curl -Is {}:8080".format(ip)
                LOG.tc_step("Curl({}) the server pod ip {} from the client pod {}".format(
                    cmd, ip, client_pod))
                code, _ = kube_helper.exec_cmd_in_container(
                    cmd=cmd, pod=client_pod)
                assert code == 0

    def test_local_host_to_service(self, deploy_test_pods):
        """
        Verify the service connectivity from external network
        Args:
            deploy_test_pods(fixture): returns server ips & clientpod list
        Setup:
            - Label the nodes and add node selector to the deployment files
                if not simplex system
            - Copy the deployment files from localhost to active controller
            - Deploy server pod
            - Deploy client pods
            - Get the server pods and client pods and check status
            - Get the ip address of the server pods
        Steps:
            - Expose the service with NodePort
            - Check the service access from local host
        Teardown:
            - Delete the service
            - Delete the server pod deployment
            - Delete the client pods
            - Remove the labels on the nodes if not simplex
        """

        LOG.tc_step("Expose the service {} with NodePort".format(service_name))
        kube_helper.expose_the_service(
            deployment_name=server_dep, type="NodePort", service_name=service_name)
        node_port = kube_helper.get_pod_value_jsonpath(
            "service {}".format(service_name), "{.spec.ports[0].nodePort}")
        out = system_helper.get_oam_values()
        ip = []
        if system_helper.is_aio_simplex():
            if ProjVar.get_var('IPV6_OAM'):
                ip.append("[{}]".format(out["oam_ip"]))
            else:
                ip.append(out["oam_ip"])
        else:
            if ProjVar.get_var('IPV6_OAM'):
                ip.extend(["[{}]".format(out["oam_floating_ip"]),
                           "[{}]".format(out["oam_c0_ip"]), "[{}]".format(out["oam_c1_ip"])])
            else:
                ip.extend([out["oam_floating_ip"],
                           out["oam_c0_ip"], out["oam_c1_ip"]])
        for i in ip:
            url = "http://{}:{}".format(i, node_port)
            LOG.tc_step(
                "Check the service access {} from local host".format(url))
            rest.check_url(url)
