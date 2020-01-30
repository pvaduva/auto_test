import inspect
import posixpath

from pytest import fixture, skip, mark

from utils import cli
from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient
from consts.stx import PLATFORM_APP, AppStatus, PodStatus
from consts.auth import HostLinuxUser
from keywords import container_helper, kube_helper, host_helper, system_helper

PROVISIONER_OVERRIDES_PATH = posixpath.join(HostLinuxUser.get_home(),
                                            "my-provisioner-overrides.yaml")
HELM_OVERRIDES_NEW_STORAGECLASS_PATH = posixpath.join(HostLinuxUser.get_home(),
                                                      "update-storageclass.yaml")
HELM_OVERRIDES_NEW_NAMESPACES_PATH = posixpath.join(HostLinuxUser.get_home(),
                                                    "update-namespaces.yaml")


def _delete_helm_chart(chart):
    con_ssh = ControllerClient.get_active_controller()
    con_ssh.exec_cmd("helm delete {} --purge".format(chart), fail_ok=False)


def _get_mysql_password(mysql_svc_name, namespace=None):
    cmd_args = 'secret {} -o jsonpath="{{.data.mysql-root-password}}" ' \
               '| base64 --decode; echo'.format(mysql_svc_name)
    if namespace:
        cmd_args = "-n {} ".format(namespace) + cmd_args
    mysql_password = kube_helper.exec_kube_cmd(sub_cmd="get", args=cmd_args)[1]
    return mysql_password


def _launch_mysql_chart_default_provisioner():
    con_ssh = ControllerClient.get_active_controller()
    LOG.tc_step("Launch mysql chart using general "
                "namespace without specifying a namespace or storage class")
    default_storageclasses = kube_helper.get_resources(field=("NAME", "PROVISIONER"),
                                                       resource_type="storageclass")
    assert default_storageclasses, "No storageclass is available"
    assert default_storageclasses[0] == ("general (default)", "ceph.com/rbd"), \
        "Default storageclass is not available"

    out = con_ssh.exec_cmd('helm search "Fast, reliable, scalable"')[1]
    assert "stable/mysql" in out, "Mysql chart is not available in helm"

    con_ssh.exec_cmd("helm upgrade --install my-release stable/mysql "
                     "--set persistence.storageClass=general | head -5", fail_ok=False)
    mysql_pod_label = "app=my-release-mysql"
    kube_helper.wait_for_pods_healthy(labels=mysql_pod_label)
    out = con_ssh.exec_cmd("helm list my-release")[1]
    assert out, "Mysql chart is not deployed"

    pvc = kube_helper.get_resources(field=("NAME", "VOLUME"), resource_type="pvc",
                                    resource_names="my-release-mysql", fail_ok=True)
    assert pvc, "my-release-mysql PVC is not deployed"

    volume = pvc[0][1]
    kube_cmd_args = "pv {} -o custom-columns=:.spec.rbd.image".format(volume)
    retcode, rbd_img = kube_helper.exec_kube_cmd(sub_cmd="get",
                                                 args=kube_cmd_args, fail_ok=True)
    assert retcode == 0, "Volume {} is not deployed".format(volume)

    assert con_ssh.exec_cmd("ceph osd lspools | grep kube-rbd")[0] == 0, \
        "kube-rbd pool does not exist"

    rbd_img = rbd_img.strip()
    retcode = con_ssh.exec_cmd("rbd -p kube-rbd ls -l | grep {}".format(rbd_img), fail_ok=True)[0]
    assert retcode == 0, "RBD image is not available"


def _launch_mysql_chart_new_provisioner(namespace):
    mon_list_cmd = "MON_LIST=$(ceph mon dump 2>&1 | awk /^[0-2]:/'{print $2}' " \
                   "| awk -F'/' '{print \"    - \"$1}')"
    provisioner_overrides_cmd = """cat <<EOF > {}
    global:
      adminId: admin
      adminSecretName: ceph-admin
      name: cool-provisioner
      provisioner_name: "ceph.com/cool-rbd"
    classdefaults:
      monitors:
    ${{MON_LIST}}
    classes:
      - name: cool-storage
        pool_name: another-pool
        chunk_size: 64
        crush_rule_name: storage_tier_ruleset
        replication: 1
        userId: cool-user-secret
        userSecretName: cool-user-secret
    rbac:
      clusterRole: cool-provisioner
      clusterRoleBinding: cool-provisioner
      role: cool-provisioner
      roleBinding: cool-provisioner
      serviceAccount: cool-provisioner
    EOF
    """.format(PROVISIONER_OVERRIDES_PATH)
    con_ssh = ControllerClient.get_active_controller()
    LOG.tc_step("Create a persistence volume with the new provisioner")
    con_ssh.exec_cmd(mon_list_cmd, fail_ok=False)
    con_ssh.exec_cmd(inspect.cleandoc(provisioner_overrides_cmd), fail_ok=False)
    create_new_provisioner_cmd = "helm upgrade --install cool-provisioner " \
                                 "stx-platform/rbd-provisioner --namespace={} " \
                                 "--values={}".format(namespace, PROVISIONER_OVERRIDES_PATH)
    con_ssh.exec_cmd(create_new_provisioner_cmd, fail_ok=False)
    kube_helper.wait_for_pods_healthy(namespace=namespace)

    LOG.tc_step("Confirm rdb provisioner is listed with the new provisioner name")
    storageclass = kube_helper.get_resources(field="PROVISIONER", resource_type="storageclass",
                                             resource_names="cool-storage", fail_ok=True)
    assert storageclass, "cool-storage storageclass is not available"
    assert storageclass[0] == "ceph.com/cool-rbd", \
        "cool-storage has an unexpected provisioner name"

    LOG.tc_step("Install mysql helm charts to the cool-storage class")
    con_ssh.exec_cmd("helm upgrade --install my-cool-release stable/mysql --namespace={}"
                     " --set persistence.storageClass=cool-storage | head -5"
                     .format(namespace), fail_ok=False)
    kube_helper.wait_for_pods_healthy(namespace=namespace)
    out = con_ssh.exec_cmd("helm list my-cool-release")[1]
    assert out, "Mysql chart is not deployed"


def _check_mysql_pvc_new_provisioner(namespace):
    con_ssh = ControllerClient.get_active_controller()
    LOG.tc_step("Check PersistentVolumeClaim and PersistentVolume of the app")
    pvc = kube_helper.get_resources(field=("NAME", "VOLUME"), resource_type="pvc",
                                    resource_names="my-cool-release-mysql",
                                    namespace=namespace, fail_ok=True)
    assert pvc, "my-cool-release-mysql PVC is not deployed"

    volume = pvc[0][1]
    kube_cmd_args = "pv {} -o custom-columns=:.spec.rbd.image".format(volume)
    retcode, rbd_img = kube_helper.exec_kube_cmd(sub_cmd="get",
                                                 args=kube_cmd_args, fail_ok=True)
    assert retcode == 0, "Volume {} is not deployed".format(volume)

    assert con_ssh.exec_cmd("ceph osd lspools | grep another-pool")[0] == 0, \
        "another-pool does not exist in ceph"

    rbd_img = rbd_img.strip()
    retcode = con_ssh.exec_cmd("rbd -p another-pool ls -l | grep {}".format(rbd_img),
                               fail_ok=True)[0]
    assert retcode == 0, "RBD image is not available"


def _check_mysql_db_conn_internal(mysql_svc_name, mysql_password, namespace=None):
    LOG.tc_step("Test connecting to the database using the ubuntu pod as a mysql client")
    ubuntu_pod = "ubuntu"
    try:
        pod_run_cmd = "{} --image=ubuntu:16.04 --restart=Never --command sleep infinity"\
                      .format(ubuntu_pod)
        if namespace:
            pod_run_cmd = "-n {} {}".format(namespace, pod_run_cmd)
        kube_helper.exec_kube_cmd(sub_cmd="run", args=pod_run_cmd)
        kube_helper.wait_for_pods_healthy(pod_names=ubuntu_pod, namespace=namespace)
        install_mysql_cmd = 'bash -c "apt-get update && apt-get install mysql-client -y"'
        kube_helper.exec_cmd_in_container(cmd=install_mysql_cmd, pod=ubuntu_pod,
                                          namespace=namespace)
        mysql_test_conn_cmd = 'bash -c "mysql -h {} -p{} -eexit"'\
                              .format(mysql_svc_name, mysql_password)
        retcode = kube_helper.exec_cmd_in_container(cmd=mysql_test_conn_cmd, namespace=namespace,
                                                    pod=ubuntu_pod, fail_ok=True)[0]
        assert retcode == 0, "Cannot connect to MySQL from local"
    except:
        raise
    finally:
        if namespace:
            kube_helper.exec_kube_cmd(sub_cmd="delete",
                                      args="-n {} pod {}".format(namespace, ubuntu_pod))
        else:
            kube_helper.delete_resources(resource_names=ubuntu_pod, resource_types="pod")


def _check_mysql_db_conn_external(mysql_svc_name, mysql_password, namespace=None):
    LOG.tc_step("Test kubectl port-forwarded connection to the database")
    con_ssh = ControllerClient.get_active_controller()
    port_forward_pid = None
    ubuntu_container_id = None
    port_forward_args = "svc/{} 3306 > /dev/null 2>&1 &".format(mysql_svc_name)
    if namespace:
        port_forward_args = "-n {} {}".format(namespace, port_forward_args)
    try:
        kube_helper.exec_kube_cmd(sub_cmd="port-forward", con_ssh=con_ssh,
                                  args=port_forward_args)
        port_forward_pid = con_ssh.exec_cmd("echo $!", fail_ok=False)[1]
        if not container_helper.get_docker_images(repo="ubuntu", tag="16.04", fail_ok=True):
            container_helper.pull_docker_image(name="ubuntu", tag="16.04")
        container_run_cmd = "--rm -it -d --network host ubuntu:16.04"
        ubuntu_container_id = container_helper.exec_docker_cmd(sub_cmd="run",
                                                               args=container_run_cmd,
                                                               con_ssh=con_ssh)[1]
        install_mysql_cmd = '-it {} /bin/bash -c ' \
                            '"apt-get update && apt-get install mysql-client -y"'\
                            .format(ubuntu_container_id)
        container_helper.exec_docker_cmd(sub_cmd="exec", args=install_mysql_cmd, con_ssh=con_ssh)
        mysql_test_conn_cmd = '-it {} /bin/bash -c ' \
                              '"mysql -h 127.0.0.1 -P 3306 -uroot -p{} -eexit"' \
                              .format(ubuntu_container_id, mysql_password)
        retcode = container_helper.exec_docker_cmd(sub_cmd="exec", args=mysql_test_conn_cmd,
                                                   con_ssh=con_ssh, fail_ok=True)[0]
    except:
        raise
    finally:
        if port_forward_pid:
            con_ssh.exec_sudo_cmd("kill -9 {}".format(port_forward_pid), fail_ok=False)
        if ubuntu_container_id:
            container_helper.exec_docker_cmd(sub_cmd="stop", args=ubuntu_container_id,
                                             con_ssh=con_ssh, fail_ok=False)
    assert retcode == 0, "Cannot connect to MySQL through kubernetes port-forwarded connection"


def _host_lock_unlock_mysql_host(mysql_svc_name, namespace=None):
    LOG.tc_step("lock/unlock the host where mysql container is located")
    mysql_pod = kube_helper.get_pods(namespace=namespace,
                                     labels="app={}".format(mysql_svc_name))[0]
    LOG.info("Found mysql pod {}".format(mysql_pod))
    cmd_args = "pods {} -o jsonpath={{.spec.nodeName}};echo".format(mysql_pod)
    if namespace:
        cmd_args = "-n {} ".format(namespace) + cmd_args
    mysql_host = kube_helper.exec_kube_cmd(sub_cmd="get", args=cmd_args)[1]
    LOG.info("Locking mysql host {} ".format(mysql_host))
    host_helper.lock_host(host=mysql_host, swact=True)
    LOG.info("Unlocking mysql host {} ".format(mysql_host))
    host_helper.unlock_host(host=mysql_host)


@fixture(scope="module", autouse=True)
def is_rbd_provisoner_healthy():
    if container_helper.get_apps(application=PLATFORM_APP)[0] != AppStatus.APPLIED:
        skip("{} is not {}".format(PLATFORM_APP, AppStatus.APPLIED))
    con_ssh = ControllerClient.get_active_controller()
    ret, out = con_ssh.exec_cmd("helm list stx-rbd-provisioner")
    if not out or ret != 0:
        skip("stx-rbd-provisioner is not installed")


@fixture(scope="function", autouse=True)
def update_helm_repo():
    con_ssh = ControllerClient.get_active_controller()
    con_ssh.exec_cmd("helm repo update", fail_ok=False)


@fixture(scope="function")
def delete_mysql_chart_default_provisioner(request):
    def teardown():
        LOG.fixture_step("Deleting my-release helm chart")
        _delete_helm_chart("my-release")
        mysql_pod = kube_helper.get_pods(labels="app=my-release-mysql")[0]
        kube_helper.wait_for_resources_gone(resource_names=mysql_pod)
    request.addfinalizer(teardown)


@fixture(scope="function")
def delete_mysql_chart_new_provisioner(request):
    def teardown():
        con_ssh = ControllerClient.get_active_controller()
        namespace = "cool-stuff"
        LOG.fixture_step("Deleting my-cool-release helm chart")
        pvc = kube_helper.get_resources(field="VOLUME", resource_type="pvc",
                                        resource_names="my-cool-release-mysql",
                                        namespace=namespace, fail_ok=True)
        if pvc:
            volume = pvc[0]
            kube_cmd_args = "pv {}".format(volume)
            kube_helper.exec_kube_cmd(sub_cmd="delete", args=kube_cmd_args, fail_ok=True)
        _delete_helm_chart("my-cool-release")
        _delete_helm_chart("cool-provisioner")
        kube_helper.delete_resources(resource_names="cool-stuff", resource_types="namespace",
                                     fail_ok=True)
        pool_del_cmd = "ceph osd pool delete another-pool another-pool " \
                       "--yes-i-really-really-mean-it"
        retcode = con_ssh.exec_cmd(pool_del_cmd, fail_ok=True)[0]
        if retcode:
            modify_pool_delete_cmd = "ceph tell mon.\\* injectargs '--mon-allow-pool-delete={}'"
            con_ssh.exec_cmd(modify_pool_delete_cmd.format("true"), fail_ok=False)
            con_ssh.exec_cmd(pool_del_cmd, fail_ok=False)
            con_ssh.exec_cmd(modify_pool_delete_cmd.format("false"), fail_ok=False)
        controllers = system_helper.get_hosts_per_personality(rtn_tuple=True)[0]
        for controller in controllers:
            with host_helper.ssh_to_host(hostname=controller) as host_ssh:
                host_ssh.exec_cmd("rm {}".format(PROVISIONER_OVERRIDES_PATH), fail_ok=True)
    request.addfinalizer(teardown)


@fixture(scope="function")
def delete_mysql_chart_new_storageclass(request):
    def teardown():
        con_ssh = ControllerClient.get_active_controller()
        namespace = "new-sc-app"
        LOG.fixture_step("Deleting my-new-sc-app helm chart")
        pvc = kube_helper.get_resources(field="VOLUME", resource_type="pvc",
                                        resource_names="my-new-sc-app-mysql",
                                        namespace=namespace, fail_ok=True)
        if pvc:
            volume = pvc[0]
            kube_cmd_args = "pv {}".format(volume)
            kube_helper.exec_kube_cmd(sub_cmd="delete", args=kube_cmd_args, fail_ok=True)
        _delete_helm_chart("my-new-sc-app")
        kube_helper.delete_resources(resource_names=namespace, resource_types="namespace",
                                     fail_ok=True)
        kube_helper.exec_kube_cmd(sub_cmd="delete", args="sc special-storage-class", fail_ok=True)
        pool_del_cmd = "ceph osd pool delete {0} {0} " \
                       "--yes-i-really-really-mean-it".format("new-sc-app-pool")
        retcode = con_ssh.exec_cmd(pool_del_cmd, fail_ok=True)[0]
        if retcode:
            modify_pool_delete_cmd = "ceph tell mon.\\* injectargs '--mon-allow-pool-delete={}'"
            con_ssh.exec_cmd(modify_pool_delete_cmd.format("true"), fail_ok=False)
            con_ssh.exec_cmd(pool_del_cmd, fail_ok=False)
            con_ssh.exec_cmd(modify_pool_delete_cmd.format("false"), fail_ok=False)
        controllers = system_helper.get_hosts_per_personality(rtn_tuple=True)[0]
        for controller in controllers:
            with host_helper.ssh_to_host(hostname=controller) as host_ssh:
                host_ssh.exec_cmd("rm {}".format(HELM_OVERRIDES_NEW_STORAGECLASS_PATH),
                                  fail_ok=True)
        cli.system("helm-override-delete platform-integ-apps rbd-provisioner kube-system")
        container_helper.apply_app(app_name=PLATFORM_APP)
    request.addfinalizer(teardown)


@fixture(scope="function")
def delete_mysql_chart_new_namespaces(request):
    def teardown():
        namespace = "new-app3"
        LOG.fixture_step("Deleting my-cool-release helm chart")
        pvc = kube_helper.get_resources(field="VOLUME", resource_type="pvc",
                                        resource_names="my-app3-mysql",
                                        namespace=namespace, fail_ok=True)
        if pvc:
            volume = pvc[0]
            kube_cmd_args = "pv {}".format(volume)
            kube_helper.exec_kube_cmd(sub_cmd="delete", args=kube_cmd_args, fail_ok=True)
        _delete_helm_chart("my-app3")
        kube_helper.delete_resources(resource_names=namespace, resource_types="namespace",
                                     fail_ok=True)
        controllers = system_helper.get_hosts_per_personality(rtn_tuple=True)[0]
        for controller in controllers:
            with host_helper.ssh_to_host(hostname=controller) as host_ssh:
                host_ssh.exec_cmd("rm {}".format(HELM_OVERRIDES_NEW_NAMESPACES_PATH),
                                  fail_ok=True)
        cli.system("helm-override-delete platform-integ-apps rbd-provisioner kube-system")
        container_helper.apply_app(app_name=PLATFORM_APP)
    request.addfinalizer(teardown)


def test_pvc_default_provisioner(delete_mysql_chart_default_provisioner):
    """
    Test persistence volume using general(default) provisioner

    Args:
        delete_mysql_chart_default_provisioner

    Prerequisites: stx-rbd-provisioner is healthy

    Test Setups:
        n/a
    Test Steps:
        - Launch mysql chart using general namespace without specifying a namespace or storage class
        - Test connecting to the database using the ubuntu pod as a mysql client
        - Test kubectl port-forward connection to the database

    Test Teardown:
        - Delete the launched mysql chart
    """
    mysql_svc_name = "my-release-mysql"
    _launch_mysql_chart_default_provisioner()
    mysql_password = _get_mysql_password(mysql_svc_name)
    _check_mysql_db_conn_internal(mysql_svc_name, mysql_password)
    _check_mysql_db_conn_external(mysql_svc_name, mysql_password)


def test_pvc_default_provisioner_lock_unlock(delete_mysql_chart_default_provisioner):
    """
    Test persistence volume using general(default) provisioner

    Args:
        delete_mysql_chart_default_provisioner

    Prerequisites: stx-rbd-provisioner is healthy

    Test Setups:
        n/a
    Test Steps:
        - Launch mysql chart using general namespace without specifying a namespace or storage class
        - lock/unlock the host where mysql container located
        - Test connecting to the database using the ubuntu pod as a mysql client
        - Test kubectl port-forward connection to the database

    Test Teardown:
        - Delete the launched mysql chart
    """
    mysql_svc_name = "my-release-mysql"
    _launch_mysql_chart_default_provisioner()
    _host_lock_unlock_mysql_host(mysql_svc_name)
    mysql_password = _get_mysql_password(mysql_svc_name)
    _check_mysql_db_conn_internal(mysql_svc_name, mysql_password)
    _check_mysql_db_conn_external(mysql_svc_name, mysql_password)


def test_pvc_default_provisioner_swact(no_simplex, delete_mysql_chart_default_provisioner):
    """
    Test persistence volume using general(default) provisioner

    Args:
        no_simplex
        delete_mysql_chart_default_provisioner

    Prerequisites: stx-rbd-provisioner is healthy

    Test Setups:
        n/a
    Test Steps:
        - Launch mysql chart using general namespace without specifying a namespace or storage class
        - Swact controller
        - Test connecting to the database using the ubuntu pod as a mysql client
        - Test kubectl port-forward connection to the database

    Test Teardown:
        - Delete the launched mysql chart
    """

    mysql_svc_name = "my-release-mysql"
    _launch_mysql_chart_default_provisioner()
    LOG.tc_step("Swact controller")
    host_helper.swact_host()
    mysql_password = _get_mysql_password(mysql_svc_name)
    _check_mysql_db_conn_internal(mysql_svc_name, mysql_password)
    _check_mysql_db_conn_external(mysql_svc_name, mysql_password)


def test_pvc_new_provisioner(delete_mysql_chart_new_provisioner):
    """
    Test persistence volume using newly created provisioner

    Args:
        delete_mysql_chart_new_provisioner

    Prerequisites: stx-rbd-provisioner is healthy

    Test Setups:
        n/a
    Test Steps:
        - Create a persistence volume with the new provisioner
        - Confirm rdb provisioner is listed with the new provisioner name
        - Install mysql helm charts to the cool-storage class
        - Check PersistentVolumeClaim and PersistentVolume of the app
        - Test connecting to the database using the ubuntu pod as a mysql client
        - Test kubectl port-forward connection to the database

    Test Teardown:
        - Delete the launched mysql chart
        - Delete the new rbd provisioner
    """
    mysql_svc_name = "my-cool-release-mysql"
    new_namespace = "cool-stuff"
    _launch_mysql_chart_new_provisioner(new_namespace)
    _check_mysql_pvc_new_provisioner(new_namespace)
    mysql_password = _get_mysql_password(mysql_svc_name, new_namespace)
    _check_mysql_db_conn_internal(mysql_svc_name, mysql_password, new_namespace)
    _check_mysql_db_conn_external(mysql_svc_name, mysql_password, new_namespace)


def test_pvc_new_provisioner_lock_unlock(delete_mysql_chart_new_provisioner):
    """
    Test persistence volume using newly created provisioner

    Args:
        delete_mysql_chart_new_provisioner

    Prerequisites: stx-rbd-provisioner is healthy

    Test Setups:
        n/a
    Test Steps:
        - Create a persistence volume with the new provisioner
        - Confirm rdb provisioner is listed with the new provisioner name
        - Install mysql helm charts to the cool-storage class
        - Check PersistentVolumeClaim and PersistentVolume of the app
        - Test connecting to the database using the ubuntu pod as a mysql client
        - Test kubectl port-forward connection to the database
        - lock/unlock the host where mysql container located
        - Test connecting to the database using the ubuntu pod as a mysql client after lock/unlock
        - Test kubectl port-forward connection to the database after lock/unlock
        - Check PersistentVolumeClaim and PersistentVolume of the app

    Test Teardown:
        - Delete the launched mysql chart
        - Delete the new rbd provisioner
    """
    mysql_svc_name = "my-cool-release-mysql"
    new_namespace = "cool-stuff"
    _launch_mysql_chart_new_provisioner(new_namespace)
    _check_mysql_pvc_new_provisioner(new_namespace)
    mysql_password = _get_mysql_password(mysql_svc_name, new_namespace)
    _check_mysql_db_conn_internal(mysql_svc_name, mysql_password, new_namespace)
    _check_mysql_db_conn_external(mysql_svc_name, mysql_password, new_namespace)
    _host_lock_unlock_mysql_host(mysql_svc_name, new_namespace)
    _check_mysql_db_conn_internal(mysql_svc_name, mysql_password, new_namespace)
    _check_mysql_db_conn_external(mysql_svc_name, mysql_password, new_namespace)
    _check_mysql_pvc_new_provisioner(new_namespace)


def test_pvc_new_provisioner_swact(no_simplex, delete_mysql_chart_new_provisioner):
    """
    Test persistence volume using newly created provisioner

    Args:
        no_simplex
        delete_mysql_chart_new_provisioner

    Prerequisites: stx-rbd-provisioner is healthy

    Test Setups:
        n/a
    Test Steps:
        - Create a persistence volume with the new provisioner
        - Confirm rdb provisioner is listed with the new provisioner name
        - Install mysql helm charts to the cool-storage class
        - Check PersistentVolumeClaim and PersistentVolume of the app
        - Test connecting to the database using the ubuntu pod as a mysql client
        - Test kubectl port-forward connection to the database
        - Swact controller
        - Test connecting to the database using the ubuntu pod as a mysql client after lock/unlock
        - Test kubectl port-forward connection to the database after lock/unlock
        - Check PersistentVolumeClaim and PersistentVolume of the app

    Test Teardown:
        - Delete the launched mysql chart
        - Delete the new rbd provisioner
    """
    mysql_svc_name = "my-cool-release-mysql"
    new_namespace = "cool-stuff"
    _launch_mysql_chart_new_provisioner(new_namespace)
    _check_mysql_pvc_new_provisioner(new_namespace)
    mysql_password = _get_mysql_password(mysql_svc_name, new_namespace)
    _check_mysql_db_conn_internal(mysql_svc_name, mysql_password, new_namespace)
    _check_mysql_db_conn_external(mysql_svc_name, mysql_password, new_namespace)
    LOG.tc_step("Swact controller")
    host_helper.swact_host()
    _check_mysql_db_conn_internal(mysql_svc_name, mysql_password, new_namespace)
    _check_mysql_db_conn_external(mysql_svc_name, mysql_password, new_namespace)
    _check_mysql_pvc_new_provisioner(new_namespace)


def test_enabling_additional_storage_classes(delete_mysql_chart_new_storageclass):
    """
    Test enabling additional storage classes

    Args:
        delete_mysql_chart_new_storageclass

    Prerequisites: stx-rbd-provisioner is healthy

    Test Setups:
        n/a
    Test Steps:
        - Update helm overrides with the new storageclass
        - Install mysql helm chart using the new storageclass
        - Check if the mysql app has been installed successfully

    Test Teardown:
        - Delete the launched mysql chart
        - Delete the helm overrides
    """
    helm_overrides_new_sc = """cat <<EOF > {}
    classes:
    - additionalNamespaces: [default, kube-public, new-app, new-app2, new-app3]
      chunk_size: 64
      crush_rule_name: storage_tier_ruleset
      name: general
      pool_name: kube-rbd
      replication: 1
      userId: ceph-pool-kube-rbd
      userSecretName: ceph-pool-kube-rbd
    - additionalNamespaces: [ new-sc-app ]
      chunk_size: 64
      crush_rule_name: storage_tier_ruleset
      name: special-storage-class
      pool_name: new-sc-app-pool
      replication: 1
      userId: ceph-pool-new-sc-app
      userSecretName: ceph-pool-new-sc-app
    EOF
    """.format(HELM_OVERRIDES_NEW_STORAGECLASS_PATH)
    namespace = "new-sc-app"
    con_ssh = ControllerClient.get_active_controller()
    LOG.tc_step("Update helm overrides with the new storageclass")
    con_ssh.exec_cmd(inspect.cleandoc(helm_overrides_new_sc), fail_ok=False)
    cli.system("helm-override-update --values {} platform-integ-apps rbd-provisioner kube-system"
               .format(HELM_OVERRIDES_NEW_STORAGECLASS_PATH))
    container_helper.apply_app(app_name=PLATFORM_APP)
    secret = kube_helper.get_resources(field="NAME", resource_type="secrets", fail_ok=True,
                                       resource_names="ceph-pool-new-sc-app", namespace=namespace)
    assert secret, "new-sc-app secret is not available"

    LOG.tc_step("Install mysql helm chart using the new storageclass")
    storageclass = kube_helper.get_resources(field="PROVISIONER", resource_type="storageclass",
                                             resource_names="special-storage-class", fail_ok=True)
    assert storageclass, "special-storage-class storageclass is not available"
    assert storageclass[0] == "ceph.com/rbd", \
        "special-storage-class has an unexpected provisioner name"
    launch_mysql_chart_cmd = "helm upgrade --install my-new-sc-app stable/mysql --namespace={} " \
                             "--set persistence.storageClass=special-storage-class | head -5" \
                             .format(namespace)
    con_ssh.exec_cmd(launch_mysql_chart_cmd, fail_ok=False)

    LOG.tc_step("Check if the mysql app has been installed successfully")
    kube_helper.wait_for_pods_healthy(namespace=namespace)
    out = con_ssh.exec_cmd("helm list my-new-sc-app")[1]
    assert out, "Mysql chart is not deployed"
    pvc = kube_helper.get_resources(field=("VOLUME", "STORAGECLASS"), resource_type="pvc",
                                    resource_names="my-new-sc-app-mysql",
                                    namespace=namespace, fail_ok=True)
    assert pvc, "my-cool-release-mysql PVC is not deployed"
    assert pvc[0][1] == "special-storage-class", "PVC has incorrect storageclass"
    volume = pvc[0][0]
    kube_cmd_args = "pv {} -o custom-columns=:.spec.rbd.image".format(volume)
    retcode, rbd_img = kube_helper.exec_kube_cmd(sub_cmd="get",
                                                 args=kube_cmd_args, fail_ok=True)
    assert retcode == 0, "Volume {} is not deployed".format(volume)

    assert con_ssh.exec_cmd("ceph osd lspools | grep new-sc-app-pool")[0] == 0, \
        "new-sc-app-pool does not exist in ceph"
    rbd_img = rbd_img.strip()
    retcode = con_ssh.exec_cmd("rbd -p new-sc-app-pool ls -l | grep {}".format(rbd_img),
                               fail_ok=True)[0]
    assert retcode == 0, "RBD image is not available"


def test_enabling_additional_namespaces_for_applications(delete_mysql_chart_new_namespaces):
    """
    Test enabling additional namespaces for applications

    Args:
        delete_mysql_chart_new_namespaces

    Prerequisites: stx-rbd-provisioner is healthy

    Test Setups:
        n/a
    Test Steps:
        - Update helm overrides with the new namespaces
        - Install mysql helm chart using the new namespace
        - Check if the mysql app has been installed successfully

    Test Teardown:
        - Delete the launched mysql chart
        - Delete the helm overrides
    """
    helm_overrides_new_ns = """cat <<EOF > {}
    classes:
    - additionalNamespaces: [default, kube-public, new-app, new-app2, new-app3]
      chunk_size: 64
      crush_rule_name: storage_tier_ruleset
      name: general
      pool_name: kube-rbd
      replication: 1
      userId: ceph-pool-kube-rbd
      userSecretName: ceph-pool-kube-rbd
    EOF
    """.format(HELM_OVERRIDES_NEW_NAMESPACES_PATH)
    namespace = "new-app3"
    con_ssh = ControllerClient.get_active_controller()
    LOG.tc_step("Update helm overrides with the new namespaces")
    con_ssh.exec_cmd(inspect.cleandoc(helm_overrides_new_ns), fail_ok=False)
    cli.system("helm-override-update --values {} platform-integ-apps rbd-provisioner kube-system"
               .format(HELM_OVERRIDES_NEW_NAMESPACES_PATH))
    container_helper.apply_app(app_name=PLATFORM_APP)
    secret = kube_helper.get_resources(field="NAME", resource_type="secrets", fail_ok=True,
                                       resource_names="ceph-pool-kube-rbd", namespace=namespace)
    assert secret, "new-app3 secret is not available"

    LOG.tc_step("Install mysql helm chart using the new namespace")
    launch_mysql_chart_cmd = "helm upgrade --install my-app3 stable/mysql --namespace={} | head -5" \
                             .format(namespace)
    con_ssh.exec_cmd(launch_mysql_chart_cmd, fail_ok=False)

    LOG.tc_step("Check if the mysql app has been installed successfully")
    kube_helper.wait_for_pods_healthy(namespace=namespace)
    pvc = kube_helper.get_resources(field="VOLUME", resource_type="pvc",
                                    resource_names="my-app3-mysql",
                                    namespace=namespace, fail_ok=True)
    assert pvc, "my-app3-mysql PVC is not deployed"
    volume = pvc[0]
    kube_cmd_args = "pv {} -o custom-columns=:.spec.rbd.image".format(volume)
    retcode = kube_helper.exec_kube_cmd(sub_cmd="get",
                                        args=kube_cmd_args, fail_ok=True)[0]
    assert retcode == 0, "Volume {} is not deployed".format(volume)
    default_storageclasses = kube_helper.get_resources(field=("NAME", "PROVISIONER"),
                                                       resource_type="storageclass")
    assert default_storageclasses, "No storageclass is available"
    assert default_storageclasses[0] == ("general (default)", "ceph.com/rbd"), \
        "Default storageclass is not available"
    out = con_ssh.exec_cmd("helm list my-app3")[1]
    assert out, "Mysql chart is not deployed"
