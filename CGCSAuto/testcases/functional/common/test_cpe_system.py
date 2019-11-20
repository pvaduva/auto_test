from pytest import mark, skip

from utils.tis_log import LOG
from keywords import system_helper, nova_helper, kube_helper


@mark.cpe_sanity
@mark.sx_sanity
def test_cpe_services_and_functions():
    if system_helper.host_exists(host='compute-0'):
        skip("compute-0 exists - skip for non-CPE lab")

    LOG.tc_step("Check controller+compute subfunction via system host-show")
    controllers = system_helper.get_controllers()
    for controller in controllers:
        assert system_helper.is_aio_system(controller=controller), \
            "{} does not have controller+compute subfunction in system host-show".format(controller)

    LOG.tc_step("Check CPE system services via nova service-list")
    check_params = ["nova-scheduler",
                    # "nova-cert",
                    "nova-conductor",
                    # "nova-consoleauth",  # removed in Train
                    "nova-compute"]

    binaries = nova_helper.get_compute_services(field='Binary')
    assert set(check_params) <= set(binaries), "Not all binaries from {} exist in 'nova service-list'".\
        format(check_params)

    LOG.tc_step("Check all nodes are ready in kubectl get nodes")
    kube_helper.wait_for_nodes_ready(timeout=3)
