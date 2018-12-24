from keywords import kube_helper
from consts.cgcs import PodStatus
from utils.tis_log import LOG


def test_platform_pods():
    """

    Returns:

    """
    kube_system_info = kube_helper.get_namespace_info(namespace='kube-system',
                                                      names=('pod', 'service', 'deployment.apps'),
                                                      keep_name_prefix=False)
    LOG.tc_step("Check kube-system pods status")
    for pod_info in kube_system_info['pod']:
        assert PodStatus.RUNNING == pod_info['status'], "Pod {} status is {} instead of {}".\
            format(pod_info['name'], pod_info['status'], PodStatus.RUNNING)

    services = ('calico-typha', 'kube-dns', 'tiller-deploy')
    LOG.tc_step("Check kube-system services: {}".format(services))
    existing_services = kube_system_info['service']
    existing_services = [service['name'] for service in existing_services]
    for service in services:
        assert service in existing_services, "{} not in kube-system service table".format(service)

    deployments = ('calico-typha', 'coredns', 'tiller-deploy')
    LOG.tc_step("Check kube-system deployments: {}".format(deployments))
    existing_deployments = kube_system_info['deployment.apps']
    existing_deployments = [deployment['name'] for deployment in existing_deployments]
    for deployment in deployments:
        assert deployment in existing_deployments, "{} not in kube-system deployment.apps table".format(deployment)


