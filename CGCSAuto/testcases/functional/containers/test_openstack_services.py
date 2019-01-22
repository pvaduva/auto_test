from pytest import skip, mark,fixture

from keywords import container_helper, system_helper, host_helper, kube_helper
from consts.cgcs import HostAvailState, PodStatus, AppStatus
from utils.tis_log import LOG


def get_valid_controllers():
    controllers = system_helper.get_controllers(availability=(HostAvailState.AVAILABLE, HostAvailState.DEGRADED,
                                                              HostAvailState.ONLINE))
    return controllers


def check_openstack_pods_healthy(host, timeout):
    with host_helper.ssh_to_host(hostname=host) as con_ssh:
        kube_helper.wait_for_openstack_pods_in_status(con_ssh=con_ssh, timeout=timeout)


@mark.sanity
@mark.sx_sanity
@mark.cpe_sanity
def test_openstack_services_healthy():
    """
    Pre-requisite:
        - stx-openstack application exists

    Test steps:
        - Check stx-openstack application in applied state via system application-list
        - Check all openstack pods in running or completed state via kubectl get

    """
    LOG.tc_step("Check stx-openstack application is applied")
    status = container_helper.get_apps_values(apps=('stx-openstack',))[0][0]
    if not status:
        skip('Openstack application is not uploaded.')
    assert status == AppStatus.APPLIED, "stx-openstack is in {} status instead of applied".format(status)

    LOG.tc_step("Check openstack pods are in running or completed status via kubectl get on all controllers")
    controllers = get_valid_controllers()
    for host in controllers:
        check_openstack_pods_healthy(host=host, timeout=5)


@mark.sanity
@mark.sx_sanity
@mark.cpe_sanity
def test_reapply_stx_openstack(skip_for_no_openstack):
    """
    Args:
        skip_for_no_openstack:

    Pre-requisite:
        - stx-openstack application in applied state

    Test Steps:
        - Re-apply stx-openstack application
        - Check openstack pods healthy

    """
    LOG.tc_step("Re-apply stx-openstack application")
    container_helper.apply_app(app_name='stx-openstack')

    LOG.tc_step("Check openstack pods in good state on all controllers after stx-openstack re-applied")
    for host in get_valid_controllers():
        check_openstack_pods_healthy(host=host, timeout=120)


NEW_NOVA_COMPUTE_PODS = None


@fixture()
def reset_if_modified(request, check_openstack_pods):
    if not container_helper.is_stx_openstack_applied(applied_only=True):
        skip('stx-openstack application is not in Applied status. Skip test.')

    valid_hosts = get_valid_controllers()
    conf_path = '/etc/nova/nova.conf'

    def reset():
        user_overrides = container_helper.get_helm_override_info(chart='nova', namespace='openstack',
                                                                 fields='user_overrides')[0]
        if not user_overrides or user_overrides == 'None':
            LOG.info("No change in nova user_overrides. Do nothing.")
            return

        LOG.fixture_step("Update nova helm-override to reset values")
        container_helper.update_helm_override(chart='nova', namespace='openstack', reset_vals=True)
        user_overrides = container_helper.get_helm_override_info(chart='nova', namespace='openstack',
                                                                 fields='user_overrides')[0]
        assert not user_overrides, "nova helm user_overrides still exist after reset-values"

        LOG.fixture_step("Re-apply stx-openstack application and ensure it is applied")
        container_helper.apply_app(app_name='stx-openstack', check_first=False, applied_timeout=1800)

        check_cmd = 'grep foo {}'.format(conf_path)
        LOG.fixture_step("Ensure user_override is removed from {} in nova-compute containers".format(conf_path))
        for host in valid_hosts:
            with host_helper.ssh_to_host(host) as host_ssh:
                LOG.info("Wait for nova-cell-setup completed on {}".format(host))
                kube_helper.wait_for_openstack_pods_in_status(pod_names='nova-cell-setup', con_ssh=host_ssh,
                                                              status=PodStatus.COMPLETED)

                LOG.info("Check new release generated for nova compute pods on {}".format(host))
                nova_compute_pods = kube_helper.get_openstack_pods_info(pod_names='nova-compute', con_ssh=host_ssh)[0]
                nova_compute_pods = sorted([pod_info['name'] for pod_info in nova_compute_pods])
                if NEW_NOVA_COMPUTE_PODS:
                    assert NEW_NOVA_COMPUTE_PODS != nova_compute_pods, "No new release generated after reset values"

                LOG.info("Check custom conf is removed from {} in nova compute container on {}".format(conf_path, host))
                for nova_compute_pod in nova_compute_pods:
                    code, output = kube_helper.exec_cmd_in_container(cmd=check_cmd, pod=nova_compute_pod, fail_ok=True,
                                                                     con_ssh=host_ssh, namespace='openstack')
                    assert code == 1, "{} on {} still contains user override info after reset nova helm-override " \
                                      "values and reapply stx-openstack app: {}".format(conf_path, host, output)
    request.addfinalizer(reset)

    return valid_hosts, conf_path


@mark.sanity
@mark.sx_sanity
@mark.cpe_sanity
def test_stx_openstack_helm_override_update_and_reset(skip_for_no_openstack, reset_if_modified):
    """
    Test helm override for openstack nova chart and reset
    Args:
        skip_for_no_openstack:

    Pre-requisite:
        - stx-openstack application in applied state

    Test Steps:
        - Update nova helm-override default conf
        - Check nova helm-override is updated in system helm-override-show
        - Re-apply stx-openstack application and ensure it is applied (in applied status and alarm cleared)
        - On all controller(s):
            - Check nova compute pods names are changed in kubectl get
            - Check actual nova-compute.conf is updated in all nova-compute containers

    Teardown:
        - Update nova helm-override to reset values
        - Re-apply stx-openstack application and ensure it is applied

    """
    valid_hosts, conf_path = reset_if_modified
    new_conf = 'conf.nova.DEFAULT.foo=bar'

    LOG.tc_step("Update nova helm-override: {}".format(new_conf))
    container_helper.update_helm_override(chart='nova', namespace='openstack',
                                          kv_pairs={'conf.nova.DEFAULT.foo': 'bar'})

    LOG.tc_step("Check nova helm-override is updated in system helm-override-show")
    fields = ('combined_overrides', 'system_overrides', 'user_overrides')
    combined_overrides, system_overrides, user_overrides = \
        container_helper.get_helm_override_info(chart='nova', namespace='openstack', fields=fields)

    assert 'bar' == user_overrides['conf']['nova']['DEFAULT'].get('foo'), \
        "{} is not shown in user overrides".format(new_conf)
    assert 'bar' == combined_overrides['conf']['nova']['DEFAULT'].get('foo'), \
        "{} is not shown in combined overrides".format(new_conf)
    assert not system_overrides['conf']['nova']['DEFAULT'].get('foo'), \
        "User override {} listed in system overrides unexpectedly".format(new_conf)

    prev_nova_cell_setup_pods, prev_nova_compute_pods = \
        kube_helper.get_openstack_pods_info(pod_names=('nova-cell-setup', 'nova-compute'))
    prev_count = len(prev_nova_cell_setup_pods)
    prev_nova_compute_names = sorted([pod['name'] for pod in prev_nova_compute_pods])

    LOG.tc_step("Re-apply stx-openstack application and ensure it is applied")
    container_helper.apply_app(app_name='stx-openstack', check_first=False, applied_timeout=1800, fail_ok=False,
                               check_interval=10)

    post_names = None
    for host in valid_hosts:
        with host_helper.ssh_to_host(hostname=host) as host_ssh:
            LOG.tc_step("Wait for all nova-cell-setup pods reach completed status on {}".format(host))
            kube_helper.wait_for_openstack_pods_in_status(pod_names='nova-cell-setup',
                                                          status=PodStatus.COMPLETED,
                                                          con_ssh=host_ssh)

            LOG.tc_step("Check nova compute pods names are changed in kubectl get on {}".format(host))
            post_nova_cell_setup_pods, post_nova_compute_pods = \
                kube_helper.get_openstack_pods_info(pod_names=('nova-cell-setup', 'nova-compute'), con_ssh=host_ssh)

            assert prev_count+1 == len(post_nova_cell_setup_pods), "No new nova cell setup pod created"
            post_nova_compute_pod_names = sorted([pod_info['name'] for pod_info in post_nova_compute_pods])
            if post_names:
                assert post_nova_compute_pod_names == post_names,  "nova compute pods names differ on two controllers"
            else:
                post_names = post_nova_compute_pod_names
                assert prev_nova_compute_names != post_names, "No new release generated for nova compute pods"

            LOG.tc_step("Check actual {} is updated in nova-compute containers on {}".format(conf_path, host))
            check_cmd = 'grep foo {}'.format(conf_path)
            for nova_compute_pod in post_nova_compute_pod_names:
                kube_helper.exec_cmd_in_container(cmd=check_cmd, pod=nova_compute_pod, fail_ok=False, con_ssh=host_ssh,
                                                  namespace='openstack')
