from pytest import mark, skip

from keywords import kube_helper, system_helper, host_helper
from consts.cgcs import PodStatus
from utils.tis_log import LOG


@mark.parametrize('controller', [
    'controller-0',
    'controller-1'
])
def test_kube_platform_pods(controller):
    """
    Test kube-system pods are deployed and running

    Test Steps:
        - Check all kube-system pods are running
        - Check kube-system services displayed: 'calico-typha', 'kube-dns', 'tiller-deploy'
        - Check kube-system deployments displayed: 'calico-typha', 'coredns', 'tiller-deploy'

    """
    controllers = system_helper.get_controllers()
    if controller not in controllers:
        skip('{} does not exist on system'.format(controller))

    with host_helper.ssh_to_host(hostname=controller) as con_ssh:
        kube_system_info = kube_helper.get_pods_info(namespace='kube-system', con_ssh=con_ssh,
                                                     types=('pod', 'service', 'deployment.apps'),
                                                     keep_name_prefix=False)
        LOG.tc_step("Check kube-system pods status on {}".format(controller))
        for pod_info in kube_system_info['pod']:
            assert PodStatus.RUNNING == pod_info['status'], "Pod {} status is {} instead of {}".\
                format(pod_info['name'], pod_info['status'], PodStatus.RUNNING)

        services = ('calico-typha', 'kube-dns', 'tiller-deploy')
        LOG.tc_step("Check kube-system services on {}: {}".format(controller, services))
        existing_services = kube_system_info['service']
        existing_services = [service['name'] for service in existing_services]
        for service in services:
            assert service in existing_services, "{} not in kube-system service table".format(service)

        deployments = ('calico-typha', 'coredns', 'tiller-deploy')
        LOG.tc_step("Check kube-system deployments on {}: {}".format(controller, deployments))
        existing_deployments = kube_system_info['deployment.apps']
        existing_deployments = [deployment['name'] for deployment in existing_deployments]
        for deployment in deployments:
            assert deployment in existing_deployments, "{} not in kube-system deployment.apps table".format(deployment)
