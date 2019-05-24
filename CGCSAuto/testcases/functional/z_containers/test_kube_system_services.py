from pytest import mark, skip

from keywords import kube_helper, system_helper, host_helper
from consts.cgcs import PodStatus, HostAvailState
from utils.tis_log import LOG


def check_host(controller):
    host = system_helper.get_active_controller_name()
    if controller == 'standby':
        controllers = system_helper.get_controllers(availability=(HostAvailState.AVAILABLE, HostAvailState.DEGRADED,
                                                                  HostAvailState.ONLINE))
        controllers.remove(host)
        if not controllers:
            skip('Standby controller does not exist or not in good state')
        host = controllers[0]
    return host


@mark.platform_sanity
@mark.parametrize('controller', [
    'active',
    'standby'
])
def test_kube_system_services(controller):
    """
    Test kube-system pods are deployed and running

    Test Steps:
        - ssh to given controller
        - Check all kube-system pods are running
        - Check kube-system services displayed: 'calico-typha', 'kube-dns', 'tiller-deploy'
        - Check kube-system deployments displayed: 'calico-typha', 'coredns', 'tiller-deploy'

    """
    host = check_host(controller=controller)

    with host_helper.ssh_to_host(hostname=host) as con_ssh:
        kube_system_info = kube_helper.get_pods_info(namespace='kube-system', con_ssh=con_ssh,
                                                     type_names=('pod', 'service', 'deployment.apps'),
                                                     keep_type_prefix=False)
        LOG.tc_step("Check kube-system pods status on {}".format(controller))
        # allow max 1 coredns pending on aio-sx
        coredns_pending = False if system_helper.is_simplex() else True
        for pod_info in kube_system_info['pod']:
            pod_status = pod_info['status']
            pod_name = pod_info['name']
            if not coredns_pending and 'coredns-' in pod_name and pod_status == PodStatus.PENDING:
                coredns_pending = True
                continue

            valid_status = [PodStatus.RUNNING]
            if 'audit-' in pod_name:
                valid_status.append(PodStatus.COMPLETED)
            elif 'init-' in pod_name:
                valid_status = [PodStatus.COMPLETED]

            assert pod_status in valid_status, "Pod {} status is {} instead of {}".\
                format(pod_name, pod_status, valid_status)

        services = ('kube-dns', 'tiller-deploy')
        LOG.tc_step("Check kube-system services on {}: {}".format(controller, services))
        existing_services = kube_system_info['service']
        existing_services = [service['name'] for service in existing_services]
        for service in services:
            assert service in existing_services, "{} not in kube-system service table".format(service)

        deployments = ('calico-kube-controllers', 'coredns', 'tiller-deploy')
        LOG.tc_step("Check kube-system deployments on {}: {}".format(controller, deployments))
        existing_deployments = kube_system_info['deployment.apps']
        existing_deployments = [deployment['name'] for deployment in existing_deployments]
        for deployment in deployments:
            assert deployment in existing_deployments, "{} not in kube-system deployment.apps table".format(deployment)
