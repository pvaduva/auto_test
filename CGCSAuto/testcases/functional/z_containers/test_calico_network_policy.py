import yaml

from pytest import mark, skip, fixture, raises

from utils.tis_log import LOG
from utils import rest

from consts.proj_vars import ProjVar
from consts.auth import HostLinuxUser
from keywords import system_helper, kube_helper, common


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


def get_protocol():
    """
    Checks if horizon is working on http & https and return ip,protocol and port,else skip
    """
    out = system_helper.get_oam_values()
    data = [{"protocol": "http", "port": 8080},
            {"protocol": "https", "port": 8443}]
    ip = []
    if system_helper.is_aio_simplex():
        ip.append(out["oam_ip"])
    else:
        ip.append(out["oam_floating_ip"])
        ip.append(out["oam_c0_ip"])
        ip.append(out["oam_c1_ip"])
    for i in data:
        url = "{}://{}:{}".format(i["protocol"],
                                  ip[0], i["port"])
        LOG.info("Check {} is accessible".format(url))
        if rest.check_url(url, fail=False):
            LOG.info("return {},{},{}".format(ip, i["protocol"], i["port"]))
            return ip, i["protocol"], i["port"]
    skip("Horizon is not accessible on both http and https,hence skiping the test")


def apply_network_policy(controller_path, localhost_path, np_filename,
                         rule_list):
    """
    This method is called from testcase test_calico_network_policy to execute the list of
    repeated commands
    Args:
        controller_path(str): file location of controller
        localhost_path(str): file location of local host
        np_filename(str): deployment file name
        rule_list: policy rules to edit the deployment filename(np_filename)
    """
    LOG.info(
        "Copy the contents of globalnetworkpolicy to file {}".format(np_filename))
    kube_helper.exec_kube_cmd(
        "get globalnetworkpolicies.crd.projectcalico.org controller-oam-if-gnp -o yaml \
        > {}/{}".format(controller_path, np_filename))
    LOG.info(
        "Scp the {} file from controller to localhost".format(np_filename))
    common.scp_from_active_controller_to_localhost(
        source_path="{}/{}".format(controller_path, np_filename), dest_path=localhost_path)
    LOG.info(
        "Change the contents of the file {} with new rules".format(np_filename))
    change_network_policy(
        "{}/{}".format(localhost_path, np_filename), rule_list)
    LOG.info(
        "Scp the {} file from localhost to the controller".format(np_filename))
    common.scp_from_localhost_to_active_controller(
        source_path="{}/{}".format(localhost_path, np_filename), dest_path=controller_path)
    LOG.info("Apply the new globalpolicyrules")
    kube_helper.exec_kube_cmd(
        "apply -f {}/{}".format(controller_path, np_filename))


@fixture
def get_data():
    """
    Fixture used to return the ip,protocol,port and policy_obj
        - Check http or https is accessible and return protocol,ip,port and policy_obj
            to the testcase
    """
    policy_obj = {"flow": "ingress", "protocol": "TCP",
                  "origin": "destination", "port": 8887, "add": False}
    LOG.fixture_step("Check http or https is accessible and return protocol,ip,port and policy_obj\
    to the testcase")
    return get_protocol(), policy_obj


@mark.networking
def test_calico_network_policy(get_data):
    """
    Verify the horizon is accessible with port change
    Args:
        get_data(tuple) : iplist,protocol,port,rule obj

    Steps:
        - Remove the port and apply the new network policy
        - Check the link is not accessible('curl -Is <url>' should not return code '200')
        - Modify the service to new port number
        - Change the network policy with the new port and apply
        - Check the link is accessible('curl -Is <url>' should return code '200')
        - Modify the service to the previous port number
        - Change the network policy file and apply
        - Check the link is accessible with previous port
    """
    (iplist, protocol, port), obj2 = get_data
    obj1 = dict(obj2)
    obj1["port"], obj1["add"] = port, False

    np_file = "np_new.yaml"
    controller_path = HostLinuxUser.get_home()
    localhost_path = ProjVar.get_var('LOG_DIR')
    name = "{}_port".format(protocol)
    LOG.tc_step("Remove the port and apply the new network policy")
    LOG.info("Remove the port {} from {}".format(obj1["port"], np_file))
    apply_network_policy(controller_path, localhost_path, np_file, [obj1])

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
        protocol, "config", name, str(obj2["port"]), apply=True)

    obj2["add"] = True
    LOG.tc_step("Change the network policy with the new port and apply")
    LOG.info("Add the port {} to {}".format(obj2["port"], np_file))
    apply_network_policy(controller_path, localhost_path, np_file, [obj2])

    LOG.tc_step(
        "Check the link is accessible('curl -Is <url>' should return code '200')")
    for ip in iplist:
        url = "{}://{}:{}".format(protocol, ip, obj2["port"])
        LOG.info("Check {} is accessible".format(url))
        assert rest.check_url(url, fail=False) is True

    LOG.tc_step("Modify the service to the previous port number")
    LOG.info("Modify the service {} port to {}".format(
        protocol, obj1["port"]))
    system_helper.modify_service_parameter(
        protocol, "config", name, str(obj1["port"]), apply=True)

    obj1["add"], obj2["add"] = True, False

    LOG.tc_step("Change the network policy file and apply")
    LOG.info("Remove port {} and add port {} to {}".format(
        obj2["port"], obj1["port"], np_file))
    apply_network_policy(controller_path, localhost_path,
                         np_file, [obj1, obj2])

    LOG.tc_step("Check the link is accessible with previous port")
    for ip in iplist:
        url = "{}://{}:{}".format(protocol, ip, obj1["port"])
        LOG.info("Check {} is accessible".format(url))
        assert rest.check_url(url, fail=False) is True


@fixture
def get_deny_policy():
    """
    Fixture to check the http/https accessible and returns the ip,protocol,port,policy_name
    and filename to the testcase
        - Copy the policy file from localhost to controller
    """
    iplist, protocol, port = get_protocol()
    policy_name = "controller-oam-if-gnp-10"
    if protocol == "http":
        filename = "deny_policy_http.yaml"
    else:
        filename = "deny_policy_https.yaml"
    controller_path = HostLinuxUser.get_home()
    LOG.fixture_step("Copy the policy file from localhost to controller")
    LOG.info("Copy the policy file {} from localhost to controller".format(filename))
    common.scp_from_localhost_to_active_controller(
        source_path="utils/test_files/{}".format(filename), dest_path=controller_path)
    return iplist, protocol, port, policy_name, filename


@mark.networking
def test_calico_deny_policy(get_deny_policy):
    """
    Add a higher order rule with deny action
    Args:
        get_deny_policy(tuple) : module fixture, returns
            iplist,protocol,port,policy_name,filename

    Steps:
        - Apply the deny policy
        - Check the link is not accessible('curl -Is <url>' should not
            return code '200')
        - Delete the deny policy
        - Check the link is accessible('curl -Is <url>' should
            return code '200')"
    """
    iplist, protocol, port, policy_name, filename = get_deny_policy

    LOG.tc_step("Apply the deny policy")
    kube_helper.exec_kube_cmd(sub_cmd="apply -f {}".format(filename))

    LOG.tc_step("Check the link is not accessible('curl -Is <url>' should not\
    return code '200')")
    for ip in iplist:
        url = "{}://{}:{}".format(protocol, ip, port)
        LOG.info("Check {} is not accessible".format(url))
        assert rest.check_url(url, fail=True) is True

    LOG.tc_step("Delete the deny policy")
    kube_helper.exec_kube_cmd(
        sub_cmd="delete globalnetworkpolicies.crd.projectcalico.org {}".format(policy_name))

    LOG.tc_step("Check the link is accessible('curl -Is <url>' should\
    return code '200')")
    for ip in iplist:
        url = "{}://{}:{}".format(protocol, ip, port)
        LOG.info("Check {} is accessible".format(url))
        assert rest.check_url(url, fail=False) is True
