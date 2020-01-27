#
# Copyright (c) 2020 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#


import os
import json

from pytest import fixture, mark

from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient

from keywords import common, kube_helper, host_helper, system_helper, container_helper
from consts.stx import SysType
from consts.proj_vars import ProjVar
from consts.auth import HostLinuxUser

STX_MONITOR_TAR = 'stx-monitor.tgz'
STX_MONITOR_APP_NAME = 'stx-monitor'

MONITOR_PORT = 31001

POD_NAME = 0
POD_NODE = 1

MONITORING_HOSTS = ["controller", "compute"]

CONTROLLER_LABELS = ['elastic-client', 'elastic-controller',
                     'elastic-data', 'elastic-master']
COMPUTE_LABELS = ['elastic-master']

POD_RUNNING_ALL_HOSTS = 'all_hosts'
POD_RUNNING_ONE_INSTANCE = 'one_instance'

MON_METRICBEAT_DS = 'mon-metricbeat-YYYYY'
MON_METRICBEAT_LABEL = 'mon-metricbeat-LABEL'
MON_METRICBEAT_PATIAL_NAME = 'mon-metricbeat-'

# This is a dictionary of labels and their corresponding pods names. Each pod
# can either run on all labeled hosts or on 1 instance on a labeled host.
# Daemon set pods run on all hosts and not correspond on a label.
PODS_LABEL_MATCHING_DICT = {
    # 'daemon_set' is a custom label for automation only
    'daemon_set': {
        'mon-filebeat-': POD_RUNNING_ALL_HOSTS,
        MON_METRICBEAT_DS: POD_RUNNING_ALL_HOSTS
    },
    'elastic-client': {
        'mon-elasticsearch-client-': POD_RUNNING_ALL_HOSTS,
    },
    'elastic-controller': {
        # the curator is a transient pod so we will skip checking for it
        # 'mon-elasticsearch-curator-': POD_RUNNING_ONE_INSTANCE,
        'mon-kibana-': POD_RUNNING_ONE_INSTANCE,
        'mon-kube-state-metrics-': POD_RUNNING_ONE_INSTANCE,
        'mon-logstash-': POD_RUNNING_ALL_HOSTS,
        MON_METRICBEAT_LABEL: POD_RUNNING_ONE_INSTANCE,
        'mon-nginx-ingress-controller-': POD_RUNNING_ALL_HOSTS,
        'mon-nginx-ingress-default-backend-': POD_RUNNING_ONE_INSTANCE
    },
    'elastic-data': {
        'mon-elasticsearch-data-': POD_RUNNING_ALL_HOSTS
    },
    'elastic-master': {
        'mon-elasticsearch-master-': POD_RUNNING_ALL_HOSTS
    }
}


def stx_monitor_file_exist():
    con_ssh = ControllerClient.get_active_controller()
    home_dir = HostLinuxUser.get_home()
    stx_mon_file = '{}{}'.format(home_dir, STX_MONITOR_TAR)

    LOG.info("Check if file %s is present" % stx_mon_file)

    return con_ssh.file_exists(stx_mon_file)


@fixture()
def setup_app(request):
    LOG.fixture_step("Setup: Clean up any pre-existing stx-monitor resources")
    cleanup_app()

    def cleanup_after_test():
        LOG.fixture_step("Tear down: clean up any stx-monitor resources")
        cleanup_app()
    request.addfinalizer(cleanup_after_test)


def cleanup_app():
    LOG.info("Remove {}".format(STX_MONITOR_APP_NAME))
    container_helper.remove_app(app_name=STX_MONITOR_APP_NAME)

    LOG.info("Delete {}".format(STX_MONITOR_APP_NAME))
    container_helper.delete_app(app_name=STX_MONITOR_APP_NAME)

    hosts = system_helper.get_hosts()
    for host in hosts:
        with host_helper.ssh_to_host(hostname=host) as host_ssh:
            LOG.info("Delete {} images for host: {}".format(STX_MONITOR_APP_NAME, host))
            container_helper.remove_docker_images_with_pattern(pattern="elastic", con_ssh=host_ssh,
                                                               timeout=120)

    LOG.info("Delete labels for {}".format(STX_MONITOR_APP_NAME))
    delete_labels()

    LOG.info("Cleanup completed")


def assign_labels(system_type):
    LOG.info("Assign monitor labels to hosts")

    host_list = system_helper.get_hosts()
    host_helper.assign_host_labels("controller-0", CONTROLLER_LABELS, lock=False, unlock=False)

    if system_type != SysType.AIO_SX and "controller-1" in host_list:
        host_helper.assign_host_labels("controller-1", CONTROLLER_LABELS, lock=False, unlock=False)

    if "compute-0" in host_list:
        host_helper.assign_host_labels("compute-0", COMPUTE_LABELS, lock=False, unlock=False)


def delete_labels():
    LOG.info("Delete monitor labels from hosts")

    host_list = system_helper.get_hosts()
    host_helper.remove_host_labels("controller-0", CONTROLLER_LABELS, lock=False, unlock=False)

    if system_helper.get_sys_type() != SysType.AIO_SX and "controller-1" in host_list:
        host_helper.remove_host_labels("controller-1", CONTROLLER_LABELS, lock=False, unlock=False)

    if "compute-0" in host_list:
        host_helper.remove_host_labels("compute-0", COMPUTE_LABELS, lock=False, unlock=False)


def is_pod_running_on_host(pods, host, partial_pod_name):

    for pod in (_pod for _pod in pods if host == _pod[POD_NODE]):

        # Special case for 'mon-metricbeat-'. There are two running processes with that partial
        # name;
        #   - The daemon set pod 'mon-metricbeat-YYYYY'
        #   - The label 'mon-metricbeat-YYYYYYYYYY-YYYYY'. Note that the middle Y are of variable
        #   lengths. e.g. mon-metricbeat-557fb9cb7-pbbzs vs mon-kube-state-metrics-77db855d59-5s566
        if partial_pod_name == MON_METRICBEAT_DS:
            if MON_METRICBEAT_PATIAL_NAME in pod[POD_NAME] and \
                            len(pod[POD_NAME]) == len(MON_METRICBEAT_DS):
                LOG.info('Found pod matching name {} for host {}. POD: {}'.format(
                    partial_pod_name, host, pod[POD_NAME]))
                return True

        elif partial_pod_name == MON_METRICBEAT_LABEL:
            if MON_METRICBEAT_PATIAL_NAME in pod[POD_NAME] and \
                            len(pod[POD_NAME]) >= len(MON_METRICBEAT_DS)+2:
                LOG.info('Found pod matching name {} for host {}. POD: {}'.format(
                    partial_pod_name, host, pod[POD_NAME]))
                return True

        elif partial_pod_name in pod[POD_NAME]:
            LOG.info('Found pod matching name {} for host {}. POD: {}'.format(
                partial_pod_name, host, pod[POD_NAME]))

            return True

    LOG.info('Missing pod matching name {} for host {}'.format(partial_pod_name, host))
    return False


def are_monitor_pods_running(system_type):

    # Get all the pods for stx-monitor
    monitor_pods = kube_helper.get_pods(field=('NAME', 'NODE'), namespace="monitor", strict=False)

    LOG.info("Running pods for stx-monitor: %s" % monitor_pods)

    # Make a dictionary of which hosts are assigned to which stx-monitor
    # labels. e.g.
    #
    # {
    #   'daemon_set': ['controller-0', 'controller-1'],
    #   'elastic-client': ['controller-0', 'controller-1'],
    #   'elastic-controller': ['controller-0', 'controller-1'],
    #   ...
    # }
    #
    host_list = system_helper.get_host_list_data(columns=["hostname", "personality"])
    labels_to_host_dict = {}
    for host in host_list:
        hostname = host.get('hostname')
        if host.get('personality') in str(MONITORING_HOSTS):

            # Add the daemon set custom label, this is a special label only
            # for this labels_to_host_dict
            hosts_for_label = labels_to_host_dict.get('daemon_set', [])
            hosts_for_label.append(hostname)
            labels_to_host_dict.update({'daemon_set': hosts_for_label})

            # Add the host's assigned labels
            labels = host_helper.get_host_labels_info(hostname)
            for label_name, label_status in labels.items():
                if label_status == 'enabled':
                    hosts_for_label = labels_to_host_dict.get(label_name, [])
                    hosts_for_label.append(hostname)
                    labels_to_host_dict.update({label_name: hosts_for_label})

    LOG.info('labels_running_hosts:{}'.format(labels_to_host_dict))

    # For each labels currently assigned on the system, get the matching
    # POD names from PODS_LABEL_MATCHING_DICT
    for label, hosts_for_label in labels_to_host_dict.items():
        LOG.debug('----------')
        LOG.debug('label:{} hosts:{}'.format(label, hosts_for_label))

        pod_details = None
        for k, v in PODS_LABEL_MATCHING_DICT.items():
            if k == label:
                pod_details = v
                break

        if pod_details is None:
            # Label not found in dict just return True
            return True

        # Get the list of pod names we need to search for, a label can have
        # more than one pods.
        for partial_pod_name, running_type in pod_details.items():
            LOG.info('-----')
            LOG.info('partial_pod_name:{} running_type:{}'.format(partial_pod_name, running_type))

            inst_found_count = 0
            for host in hosts_for_label:
                if is_pod_running_on_host(monitor_pods, host, partial_pod_name):
                    # The pod was found, increment the no of instances running on all hosts for this
                    # pod
                    inst_found_count += 1

            # Special case for AIO-DX and mon-elasticsearch-master-x
            if partial_pod_name == 'mon-elasticsearch-master-' and system_type == SysType.AIO_DX \
                    and inst_found_count == 1:
                LOG.info('Pod {} only needs to run one instances for AIO-DX'.format(
                    partial_pod_name))
                pass
            # Some pods only run one instances even if the label is on multiple hosts
            elif inst_found_count == 1 and running_type == POD_RUNNING_ONE_INSTANCE:
                LOG.info('Pod {} only needs to run one instances'.format(partial_pod_name))
                pass
            # Pod did not match the number of hosts its supposed to run on
            elif inst_found_count != len(hosts_for_label):
                LOG.error('Pod check for {} failed, missing instances'.format(partial_pod_name))
                return False

            LOG.info('Check for pod {} SUCCESS'.format(partial_pod_name))

    return True


@mark.skipif(not stx_monitor_file_exist(), reason="Missing stx-monitor tar file from system")
@mark.platform_sanity
def test_stx_monitor(setup_app):
    """
    Test stx-monitor application

    Assumptions: /home/sysadmin/stx-monitor.tgz is present on controller-0

    Args:
        setup_app: fixture

    Setups:
        - application remove and delete stx-monitor,
            application-remove stx-monitor
            application-delete stx-monitor
        - delete images from all registries on all hosts.
             docker images  | grep elastic | awk '{print $3}'
             docker image rm --force <image>
        - remove labels (varies depending on type of system and hosts). Supported labels are
        elastic-client, elastic-controller, elastic-master and elastic-data
            e.g. host-label-remove controller-0 elastic-client

    Test Steps:
        - Assign labels (varies depending on type of system and hosts).  Supported labels are
        elastic-client, elastic-controller, elastic-master and elastic-data
            e.g. host-label-assign controller-0 elastic-client=enabled

        - Application upload.
            application-upload -n stx-monitor /home/sysadmin/stx-monitor.tgz

        - Application apply.
            application-apply stx-monitor

        - Check for pods Ready state.
            kubectl wait --namespace=monitor --for=condition=Ready pods --timeout=30s --all
                --selector=app!=elasticsearch-curator

        - Verify all Pods are assigned according to the specified labels and
        DaemonSets.

        - Check the cluster health (cluster health status will be yellow for AIO-SX as there will be
        no replicated shards). Validate status, active_shards,unassigned_shards values
            curl <ip>:31001/mon-elasticsearch-client/_cluster/health?pretty

    Teardown:
        - application remove and delete stx-monitor,
            application-remove stx-monitor
            application-delete stx-monitor
        - delete images from all registries on all hosts.
            docker images  | grep elastic | awk '{print $3}'
            docker image rm --force <image>
        - remove labels (varies depending on type of system and hosts)

    """

    system_type = system_helper.get_sys_type()

    # Assign the stx-monitor labels.
    LOG.tc_step("Assign labels")
    assign_labels(system_type)

    # Do application upload stx-monitor.
    app_dir = HostLinuxUser.get_home()
    tar_file = os.path.join(app_dir, STX_MONITOR_TAR)
    LOG.tc_step("Upload %s" % tar_file)
    container_helper.upload_app(tar_file=tar_file, app_name=STX_MONITOR_APP_NAME)

    # Do application apply stx-monitor.
    LOG.tc_step("Apply %s" % STX_MONITOR_APP_NAME)
    container_helper.apply_app(app_name=STX_MONITOR_APP_NAME, applied_timeout=3600,
                               check_interval=60)

    # Check for pods Ready state.
    LOG.tc_step("Check Pod Ready state")
    params = \
        '--namespace=monitor --for=condition=Ready pods --timeout=30s --all ' \
        '--selector=app!=elasticsearch-curator'
    kube_helper.exec_kube_cmd(sub_cmd="wait", args=params, fail_ok=False)

    # Verify all Pods are assigned according to the specified labels and
    # DaemonSets
    LOG.tc_step("Verify all Pods are assigned properly")
    assert are_monitor_pods_running(system_type), "Error: Some monitor pods are not running"

    # Check the cluster health (cluster health status will be yellow for
    # AIO-SX as there will be no replicated shards)
    LOG.tc_step("Check the cluster health")

    # Running curl command from test server ensures IPV6 will work
    with host_helper.ssh_to_test_server() as ssh_client:
        prefix = 'http'
        oam_ip = ProjVar.get_var('LAB')['floating ip']
        if common.get_ip_version(oam_ip) == 6:
            oam_ip = '[{}]'.format(oam_ip)

        code, output = ssh_client.exec_cmd(
            'curl {}://{}:31001/mon-elasticsearch-client/_cluster/health?pretty'.format(
                prefix, oam_ip), fail_ok=False)

    if output:
        data_dict = json.loads(output)

        # check status is green
        if not (data_dict['status'] == 'green' or
                (system_type == SysType.AIO_SX and data_dict['status'] == 'yellow')):
            raise AssertionError("status not green or in case of AIO-SX yellow")

        # check unassigned shards is 0
        if system_type != SysType.AIO_SX and data_dict['unassigned_shards'] != 0:
            raise AssertionError("unassigned_shards not 0")

        # check active_shards is 0
        if data_dict['active_shards'] == 0:
            raise AssertionError("active_shards not 0")
    else:
        raise AssertionError("curl command failed")
