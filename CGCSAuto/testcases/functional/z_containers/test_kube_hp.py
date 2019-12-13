from pytest import fixture, mark
from keywords import system_helper, kube_helper, common, host_helper
from consts.auth import Tenant
from utils import cli, table_parser, exceptions
from utils.tis_log import LOG
from consts.auth import HostLinuxUser
import yaml
import os


def modify_yaml(file_dir, file_name, str_to_add, hp_value):
    """
    Desc:
        This function adds the hugepages 1G value to the hugepages_pod.yaml file
    Args:
        file_dir(str) - where the yaml file exist
        file_name(str) - name of the yaml to modify
        str_to_add(str) - 2M or 1G hugepage to add
        hp_value(str) - hugepage value to assign to str_to_add
    Return(str):
        returns the filename with modified values
    """
    with open("{}/{}".format(file_dir, file_name), 'r') as f:
        data = yaml.safe_load(f)
    data['spec']['containers'][0]['resources']['limits'][str_to_add] = hp_value
    newfile = "hugepages_pod_{}.yaml".format(hp_value)
    with open("{}/{}".format(file_dir, newfile), 'w') as f:
        yaml.dump(data, f)
    return newfile


@fixture(scope="module")
def get_hp_pod_file():
    """
    Desc:
        Setup and teardown required for test_hp_pod

        1)gets the compute-0 if exist, else active controller
        2)check 2M hugepages configured,elsif 1G is configured
            else lock,configure 2G 1G hugepages,unlock host
        3)call modify_yaml function to modify the yaml
          file with the values
        4)modified file scps to host to deploy hugepages pod
        5)Deletes the hugepages pod from the host after the test

    """
    computes = system_helper.get_computes()
    if not computes:
        hostname = system_helper.get_active_controller_name()
    else:
        hostname = computes[0]
    LOG.info("checking hp values on {}".format(hostname))
    proc_id = 0
    out = host_helper.get_host_memories(
        hostname, ('app_hp_avail_2M', 'app_hp_avail_1G'), proc_id)
    if out[proc_id][0] > 0:
        hp_val = "{}Mi".format(out[proc_id][0])
        hp_str = "hugepages-2Mi"
    elif out[proc_id][1] > 0:
        hp_val = "{}Gi".format(out[proc_id][1])
        hp_str = "hugepages-1Gi"
    else:
        hp_val = "{}Gi".format(2)
        cmd = "{} -1G {}".format(proc_id, 2)
        hp_str = "hugepages-1Gi"
        host_helper.lock_host(hostname)
        cli.system('host-memory-modify {} {}'.format(hostname, cmd), ssh_client=None,
                   use_telnet=False, con_telnet=None, auth_info=Tenant.get('admin_platform'))
        host_helper.unlock_host(hostname)
    LOG.info("{} {} pod wil be configured on {} proc id {}".format(
        hp_str, hp_val, hostname, proc_id))
    file_name = modify_yaml(
        "utils/test_files/hp/", "hugepages_pod.yaml", hp_str, hp_val)
    source_path = "utils/test_files/hp/{}".format(file_name)
    home_dir = HostLinuxUser.get_home()
    common.scp_from_localhost_to_active_controller(
        source_path, dest_path=home_dir)
    LOG.info("Deleting the local file after scp to active controller")
    os.system('rm utils/test_files/hp/{}'.format(file_name))
    yield file_name
    LOG.info("Delete hugepages pod")
    kube_helper.exec_kube_cmd(
        sub_cmd="delete pod hugepages-pod")


@mark.hp()
def test_hp_pod(get_hp_pod_file):
    """
    Desc:
        verifies hugepage pod is deployed and running
    Setup:
        copies the hugepages yaml file to host

    Test:
        create hugepage pod with deployment file
        verifies hugepage pod is deployed and running

    Teardown:
        Deletes the hugepages pod from the host
    """
    LOG.info("create hugepages pod")
    kube_helper.exec_kube_cmd(
        sub_cmd="create -f {}".format(get_hp_pod_file))
    LOG.info("check hugepages pod is running")
    kube_helper.wait_for_pods_status(
        pod_names="hugepages-pod", namespace="default")
