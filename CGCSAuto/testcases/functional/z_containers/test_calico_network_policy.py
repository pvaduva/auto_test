import copy
import yaml

from pytest import mark, fixture, raises

from utils.tis_log import LOG
from utils import rest

from consts.proj_vars import ProjVar
from consts.auth import HostLinuxUser
from keywords import system_helper, kube_helper, common

CONTROLLER_PATH = HostLinuxUser.get_home()
LOCALHOST_PATH = ProjVar.get_var('LOG_DIR')


def change_network_policy(filepath, rules):
    """
    Modifies the give network policy yaml file and returns the modified file
    Args:
        filepath(str): location of the yaml file to change
        rules(list): list of dicts which each dict has the following keys
            flow(str): ingress or egress
            protocol(str): protocol to match for condition
            origin(str): source or destination
            port(int): port number
            add(boolean): "True" to add, "False" to remove
    Return(str):
        returns the modified network policy file path
    """
    try:
        with open(filepath, 'r') as f:
            data = yaml.safe_load(f)
        for i in rules:
            for j in data['spec'][i["flow"]]:
                if j["protocol"] == i["protocol"]:
                    if i["add"]:
                        j[i["origin"]]["ports"].append(i["port"])
                    else:
                        j[i["origin"]]["ports"].remove(i["port"])
        with open(filepath, 'w') as f:
            yaml.dump(data, f)
        return filepath
    except Exception as err:
        raises(err)


def get_system_service():
    """
    Checks http/https service and port and returns protocol,port and service_name
    Returns:
        return protocol,port and service_name
    """
    if system_helper.get_system_values(fields="https_enabled")[0] == 'True':
        protocol = "https"
        port = system_helper.get_service_parameter_values(name="https_port")[0]
        service_name = "{}_port".format(protocol)
    else:
        protocol = "http"
        port = system_helper.get_service_parameter_values(name="http_port")[0]
        service_name = "{}_port".format(protocol)
    return protocol, port, service_name


@fixture
def get_data(request):
    """
    Fixture to check the http/https service, port and returns
        ip, protocol, port, service_name, policy_obj
        - Back up the current globalnetwork policy to a file
        - Scp the file from controller to localhost
        - Get the resourceVersion of the current globalnetworkpolicy
        - Modify the file with the resourceVersion number
        - Write the modified network data to the file
        - Scp the file from localhost to the controller
        - Apply the original globalnetworkpolicy values with new resourceVersion
        - Check the link is accessible with original port
    """
    policy_backup_file = "policy_backup.yaml"
    ip = system_helper.get_system_iplist()
    policy_obj = {"flow": "ingress", "protocol": "TCP",
                  "origin": "destination", "port": 8887, "add": False}
    protocol, port, service_name = get_system_service()

    LOG.fixture_step("Back up the current globalnetwork policy to {} file".format(
        policy_backup_file))

    kube_helper.exec_kube_cmd(
        "get globalnetworkpolicies.crd.projectcalico.org controller-oam-if-gnp -o yaml \
        > {}/{}".format(CONTROLLER_PATH, policy_backup_file))

    LOG.fixture_step(
        "Scp the {} file from controller to localhost".format(policy_backup_file))

    common.scp_from_active_controller_to_localhost(
        source_path="{}/{}".format(CONTROLLER_PATH, policy_backup_file), dest_path=LOCALHOST_PATH)

    def teardown():
        if port != system_helper.get_service_parameter_values(name=service_name)[0]:
            system_helper.modify_service_parameter(
                protocol, "config", service_name, port, apply=True)

        LOG.fixture_step(
            "Get the resourceVersion of the current globalnetworkpolicy")

        resource_ver = kube_helper.get_pod_value_jsonpath(
            "globalnetworkpolicies.crd.projectcalico.org controller-oam-if-gnp",
            "{.metadata.resourceVersion}")

        LOG.fixture_step("Modify the {} file with the resourceVersion {} number".format(
            policy_backup_file, resource_ver))

        data = common.get_yaml_data(
            "{}/{}".format(LOCALHOST_PATH, policy_backup_file))
        data["metadata"]["resourceVersion"] = resource_ver

        LOG.fixture_step(
            "Write the modified network data to the file {}".format(policy_backup_file))

        filepath = common.write_yaml_data_to_file(data, policy_backup_file)

        LOG.fixture_step(
            "Scp the {} file from localhost to the controller".format(filepath))

        common.scp_from_localhost_to_active_controller(
            source_path=filepath, dest_path=CONTROLLER_PATH)

        LOG.fixture_step(
            "Apply the original globalnetworkpolicy values with new resourceVersion")
        kube_helper.exec_kube_cmd(
            "apply -f {}/{}".format(CONTROLLER_PATH, policy_backup_file))

        LOG.fixture_step(
            "Check the link is accessible with original port {}".format(port))
        for i in ip:
            url = "{}://{}:{}".format(protocol, i, port)
            LOG.info("Check {} is accessible".format(url))
            assert rest.check_url(url, fail=False) is True

    request.addfinalizer(teardown)
    return ip, protocol, port, service_name, policy_obj


def apply_network_policy(np_filename, rule_list):
    """
    This method is called from testcase test_calico_network_policy to execute the list of
    repeated commands
    Args:
        np_filename(str): deployment file name
        rule_list: policy rules to edit the deployment filename(np_filename)
    """
    LOG.info(
        "Copy the contents of globalnetworkpolicy to file {}".format(np_filename))
    kube_helper.exec_kube_cmd(
        "get globalnetworkpolicies.crd.projectcalico.org controller-oam-if-gnp -o yaml \
        > {}/{}".format(CONTROLLER_PATH, np_filename))
    LOG.info(
        "Scp the {} file from controller to localhost".format(np_filename))
    common.scp_from_active_controller_to_localhost(
        source_path="{}/{}".format(CONTROLLER_PATH, np_filename), dest_path=LOCALHOST_PATH)
    LOG.info(
        "Change the contents of the file {} with new rules".format(np_filename))
    change_network_policy(
        "{}/{}".format(LOCALHOST_PATH, np_filename), rule_list)
    LOG.info(
        "Scp the {} file from localhost to the controller".format(np_filename))
    common.scp_from_localhost_to_active_controller(
        source_path="{}/{}".format(LOCALHOST_PATH, np_filename), dest_path=CONTROLLER_PATH)
    LOG.info("Apply the new globalpolicyrules")
    kube_helper.exec_kube_cmd(
        "apply -f {}/{}".format(CONTROLLER_PATH, np_filename))


@mark.networking
def test_calico_network_policy(get_data):
    """
    Verify the horizon is accessible with port change
    Args:
        get_data(fixture) : iplist,protocol,port,service_name,rule obj
    Setup:
        - Back up the current globalnetwork policy to a file
        - Scp the file from controller to localhost
    Steps:
        - Remove the port and apply the new network policy
        - Check the link is not accessible('curl -Is <url>' should not return code '200')
        - Modify the service to new port number
        - Change the network policy with the new port and apply
        - Check the link is accessible('curl -Is <url>' should return code '200')
        - Modify the service to the previous port number
        - Change the network policy file and apply
        - Check the link is accessible with previous port
    Teardown:
        - Get the resourceVersion of the current globalnetworkpolicy
        - Modify the file with the resourceVersion number
        - Write the modified network data to the file
        - Scp the file from localhost to the controller
        - Apply the original globalnetworkpolicy values with new resourceVersion
        - Check the link is accessible with original port
    """
    iplist, protocol, port, service_name, obj2 = get_data

    for ip in iplist:
        url = "{}://{}:{}".format(protocol, ip, port)
        LOG.info("Check {} is accessible".format(url))
        assert rest.check_url(url, fail=False) is True

    obj1 = copy.deepcopy(obj2)
    obj1["port"], obj1["add"] = int(port), False

    np_file = "np_new.yaml"

    LOG.tc_step("Remove the port and apply the new network policy")
    LOG.info("Remove the port {} from {}".format(obj1["port"], np_file))
    apply_network_policy(np_file, [obj1])

    LOG.tc_step(
        "Check the link is not accessible('curl -Is <url>' should not return code '200')")

    for ip in iplist:
        url = "{}://{}:{}".format(protocol, ip, port)
        LOG.info("Check {} is not accessible".format(url))
        assert rest.check_url(url, fail=True) is True

    LOG.tc_step("Modify the service to new port number")
    LOG.info("Modify the service {} port to {}".format(
        protocol, obj2["port"]))
    system_helper.modify_service_parameter(
        protocol, "config", service_name, str(obj2["port"]), apply=True)

    obj2["add"] = True
    LOG.tc_step("Change the network policy with the new port and apply")
    LOG.info("Add the port {} to {}".format(obj2["port"], np_file))
    apply_network_policy(np_file, [obj2])

    LOG.tc_step(
        "Check the link is accessible('curl -Is <url>' should return code '200')")
    for ip in iplist:
        url = "{}://{}:{}".format(protocol, ip, obj2["port"])
        LOG.info("Check {} is accessible".format(url))
        assert rest.check_url(url, fail=False) is True


@fixture
def get_deny_policy(request):
    """
    Fixture to check the http/https accessible and returns the ip,protocol,port,policy_name
    and filename to the testcase
        - Copy the policy file from localhost to controller
        - Delete the deny policy
        - Check the link is accessible('curl -Is <url>' should
          return code '200')
    """
    iplist = system_helper.get_system_iplist()
    protocol, port, _ = get_system_service()
    policy_name = "controller-oam-if-gnp-10"
    if protocol == "http":
        filename = "deny_policy_http.yaml"
    else:
        filename = "deny_policy_https.yaml"
    LOG.fixture_step("Copy the policy file from localhost to controller")
    LOG.info("Copy the policy file {} from localhost to controller".format(filename))
    common.scp_from_localhost_to_active_controller(
        source_path="utils/test_files/{}".format(filename), dest_path=CONTROLLER_PATH)

    def teardown():
        LOG.fixture_step("Delete the deny policy")
        kube_helper.exec_kube_cmd(
            sub_cmd="delete globalnetworkpolicies.crd.projectcalico.org {}".format(policy_name))
        LOG.fixture_step("Check the link is accessible('curl -Is <url>' should\
        return code '200')")
        for ip in iplist:
            url = "{}://{}:{}".format(protocol, ip, port)
            LOG.info("Check {} is accessible".format(url))
            assert rest.check_url(url, fail=False) is True
    request.addfinalizer(teardown)
    return iplist, protocol, port, filename


@mark.networking
def test_calico_deny_policy(get_deny_policy):
    """
    Add a higher order rule with deny action
    Args:
        get_deny_policy(fixture) :  returns
            iplist,protocol,port,filename
    Setup:
        - Copy the policy file from localhost to controller

    Steps:
        - Apply the deny policy
        - Check the link is not accessible('curl -Is <url>' should not
            return code '200')
    Teardown:
        - Delete the deny policy
        - Check the link is accessible('curl -Is <url>' should
          return code '200')
    """

    iplist, protocol, port, filename = get_deny_policy

    LOG.tc_step("Apply the deny policy")
    kube_helper.exec_kube_cmd(sub_cmd="apply -f {}".format(filename))

    LOG.tc_step("Check the link is not accessible('curl -Is <url>' should not\
    return code '200')")
    for ip in iplist:
        url = "{}://{}:{}".format(protocol, ip, port)
        LOG.info("Check {} is not accessible".format(url))
        assert rest.check_url(url, fail=True) is True
