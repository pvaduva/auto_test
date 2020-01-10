import requests
import yaml

from pytest import mark, skip, fixture, raises

from utils.tis_log import LOG

from consts.proj_vars import ProjVar
from consts.auth import HostLinuxUser
from keywords import system_helper, kube_helper, common


def check_url(url, fail=False, insecure=False):
    """
    Checks the access to the given url and returns True or False based on fail condition
    Args:
        url(str): url to check the access
        fail(boolean): True or False
        insure(boolean): default is false(insecure mode for https) for
                        both http and https protocol
    Return(boolean):
        returns True or False based on expected behaviour
    """
    try:
        r = requests.get(url, timeout=10, verify=insecure)
        return True if r.status_code == 200 and fail is False else False
    except requests.exceptions.Timeout:
        return True if fail else False


def change_network_policy(filepath, rules):
    """
    Modifies the give network policy yaml file and returns the modified file
    Args:
        src_path(str): location of the yaml file to change
        dst_path(str): location of the modified
        rule_dict: list of dicts
            flow(str): ingress or egress
            protocol(str): protocol to match for condition
            origin(str): source or destination
            port_no(int): port number
            add(boolean): "True" to add, "False" to remove
    Return(json):
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


def apply_network_policy(controller_path, localhost_path, np_filename,
                         rule_list):
    """
    This method is called from testcase test_calico_network_policy  to execute the list of
    repeated commands
    Args:
        controller_path(str): file location of controller
        localhost_path(str): file location of local host
        np_filename(str): deployment file name
        rule_list: policy rules to edit the deployment filename(np_filename)
    """
    LOG.tc_step(
        "Copy the contents of globalnetworkpolicy to file {}".format(np_filename))
    kube_helper.exec_kube_cmd(
        "get globalnetworkpolicies.crd.projectcalico.org controller-oam-if-gnp -o yaml \
        > {}/{}".format(controller_path, np_filename))
    LOG.tc_step(
        "Scp the {} file from controller to localhost".format(np_filename))
    common.scp_from_active_controller_to_localhost(
        source_path="{}/{}".format(controller_path, np_filename), dest_path=localhost_path)
    LOG.tc_step(
        "Change the contents of the file {} with new rules".format(np_filename))
    change_network_policy(
        "{}/{}".format(localhost_path, np_filename), rule_list)
    LOG.tc_step(
        "Scp the {} file from localhost to the controller".format(np_filename))
    common.scp_from_localhost_to_active_controller(
        source_path="{}/{}".format(localhost_path, np_filename), dest_path=controller_path)
    LOG.tc_step("Apply the new globalpolicyrules")
    kube_helper.exec_kube_cmd(
        "apply -f {}/{}".format(controller_path, np_filename))


@fixture
def get_port():
    """
    Fixture used to return the ip,protocol,port and policy_obj
        - Get the oam_ip if simplex, else oam_floating_ip
        - Check http or https is reachable with their repective
            ports or else skip the testcase
        - Return the repective protocol,ip,port and policy_obj
            to the testcase
    """
    policy_obj = {"flow": "ingress", "protocol": "TCP",
                  "origin": "destination", "port": 8887, "add": False}
    out = system_helper.get_oam_values()
    data = [{"protocol": "http", "port": 8080},
            {"protocol": "https", "port": 8443}]
    if system_helper.is_aio_simplex():
        ip = out["oam_ip"]
    else:
        ip = out["oam_floating_ip"]
    for i in data:
        url = "{}://{}:{}".format(i["protocol"], ip, i["port"])
        LOG.fixture_step("Check {} is accessible".format(url))
        if check_url(url, fail=False):
            LOG.fixture_step("return test input {},{},{}".format(
                ip, i["protocol"], i["port"]))
            return ip, i["protocol"], i["port"], policy_obj
    skip("Horizon is not accessible on both http and https,hence skiping the test")


@mark.calico
def test_calico_network_policy(get_port):
    """
    Verify the horizon is accessible with port change
    Args:
        get_port(tuple) : ip,protocol,port,rule obj

    Steps:
        - Remove the respective protocol port and apply new
            deployment file
        - Check the link is not accessible
        - Modify the service to new port number
        - Change the deployment file and apply
        - Check the link is accessible with new port number

    Teardown:
        - Modify the service to the previous port number
        - Change the deployment file and apply
    """
    ip, protocol, port, obj2 = get_port
    obj1 = dict(obj2)
    obj1["port"], obj1["add"] = port, False
    url = "{}://{}:{}".format(protocol, ip, port)
    np_file = "np_new.yaml"
    controller_path = HostLinuxUser.get_home()
    localhost_path = ProjVar.get_var('LOG_DIR')
    name = "{}_port".format(protocol)

    LOG.tc_step("Remove the port {} from {}".format(obj1["port"], np_file))
    apply_network_policy(controller_path, localhost_path, np_file, [obj1])
    LOG.tc_step("Check {} is not accessible".format(url))
    assert check_url(url, fail=True) is True

    LOG.tc_step("Modify the service {} port to {}".format(
        protocol, obj2["port"]))
    system_helper.modify_service_parameter(
        protocol, "config", name, str(obj2["port"]), apply=True)

    obj2["add"] = True
    LOG.tc_step("Add the port {} to {}".format(obj2["port"], np_file))
    apply_network_policy(controller_path, localhost_path, np_file, [obj2])
    url = "{}://{}:{}".format(protocol, ip, obj2["port"])
    LOG.tc_step("Check {} is accessible".format(url))
    assert check_url(url, fail=False) is True

    LOG.tc_step("Modify the service {} port to {}".format(
        protocol, obj1["port"]))
    system_helper.modify_service_parameter(
        protocol, "config", name, str(obj1["port"]), apply=True)

    obj1["add"], obj2["add"] = True, False
    LOG.tc_step("Revove port {} and add port {} to {}".format(
        obj2["port"], obj1["port"], np_file))
    apply_network_policy(controller_path, localhost_path,
                         np_file, [obj1, obj2])
    url = "{}://{}:{}".format(protocol, ip, obj1["port"])
    LOG.tc_step("Check {} is accessible".format(url))
    assert check_url(url, fail=False) is True
