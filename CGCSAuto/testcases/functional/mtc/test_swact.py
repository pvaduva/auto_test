from pytest import mark, skip

from utils.tis_log import LOG
from utils.kpi import kpi_log_parser
from consts.reasons import SkipSysType
from consts.kpi_vars import Swact, SwactUncontrolled, KPI_DATE_FORMAT
from keywords import host_helper, system_helper, vm_helper, network_helper, common, kube_helper


@mark.sanity
@mark.cpe_sanity
def test_swact_controllers(wait_for_con_drbd_sync_complete):
    """
    Verify swact active controller

    Test Steps:
        - Boot a vm on system and check ping works
        - Swact active controller
        - Verify standby controller and active controller are swapped
        - Verify vm is still pingable

    """
    if system_helper.is_simplex():
        skip("Simplex system detected")

    if not wait_for_con_drbd_sync_complete:
        skip(SkipSysType.LESS_THAN_TWO_CONTROLLERS)

    LOG.tc_step('retrieve active and available controllers')
    pre_active_controller, pre_standby_controller = system_helper.get_active_standby_controllers()
    assert pre_standby_controller, "No standby controller available"

    pre_res_sys, pre_msg_sys = system_helper.wait_for_services_enable(timeout=20, fail_ok=True)
    up_hypervisors = host_helper.get_up_hypervisors()
    pre_res_neutron, pre_msg_neutron = network_helper.wait_for_agents_alive(up_hypervisors, timeout=20,
                                                                            fail_ok=True)

    LOG.tc_step("Boot a vm from image and ping it")
    vm_id_img = vm_helper.boot_vm(name='swact_img', source='image', cleanup='function')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id_img)

    LOG.tc_step("Boot a vm from volume and ping it")
    vm_id_vol = vm_helper.boot_vm(name='swact', cleanup='function')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id_vol)

    LOG.tc_step("Swact active controller and ensure active controller is changed")
    exit_code, output = host_helper.swact_host(hostname=pre_active_controller)
    assert 0 == exit_code, "{} is not recognized as active controller".format(pre_active_controller)

    LOG.tc_step("Verify standby controller and active controller are swapped")
    post_active_controller = system_helper.get_active_controller_name()
    post_standby_controller = system_helper.get_standby_controller_name()

    assert pre_standby_controller == post_active_controller, "Prev standby: {}; Post active: {}".format(
            pre_standby_controller, post_active_controller)
    assert pre_active_controller == post_standby_controller, "Prev active: {}; Post standby: {}".format(
            pre_active_controller, post_standby_controller)

    LOG.tc_step("Check boot-from-image vm still pingable after swact")
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id_img, timeout=30)
    LOG.tc_step("Check boot-from-volume vm still pingable after swact")
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id_vol, timeout=30)

    LOG.tc_step("Check system services and neutron agents after swact from {}".format(pre_active_controller))
    post_res_sys, post_msg_sys = system_helper.wait_for_services_enable(fail_ok=True)
    post_res_neutron, post_msg_neutron = network_helper.wait_for_agents_alive(hosts=up_hypervisors, fail_ok=True)

    assert post_res_sys, "\nPost-evac system services stats: {}\nPre-evac system services stats: {}". \
        format(post_msg_sys, pre_msg_sys)
    assert post_res_neutron, "\nPost evac neutron agents stats: {}\nPre-evac neutron agents stats: {}". \
        format(pre_msg_neutron, post_msg_neutron)

    LOG.tc_step("Check hosts are Ready in kubectl get nodes after swact")
    kube_helper.wait_for_nodes_ready(hosts=(pre_active_controller, pre_standby_controller), timeout=30)


@mark.kpi
def test_swact_controlled_kpi(collect_kpi):
    if not collect_kpi:
        skip("KPI only test. Skip due to kpi collection is not enabled.")
    start_host, end_host = system_helper.get_active_standby_controllers()
    if not end_host:
        skip("No standby host to swact to")

    init_time = common.get_date_in_format(date_format=KPI_DATE_FORMAT)
    host_helper.swact_host(hostname=start_host)
    kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=Swact.NAME, init_time=init_time,
                              log_path=Swact.LOG_PATH, end_pattern=Swact.END, host=end_host, start_host=start_host,
                              start_pattern=Swact.START, start_path=Swact.START_PATH, uptime=1, fail_ok=False)


@mark.kpi
def test_swact_uncontrolled_kpi(collect_kpi):
    if not collect_kpi:
        skip("KPI only test. Skip due to kpi collection is not enabled.")
    start_host, end_host = system_helper.get_active_standby_controllers()
    if not end_host:
        skip("No standby host to swact to")

    init_time = common.get_date_in_format(date_format=KPI_DATE_FORMAT)
    host_helper.reboot_hosts(hostnames=start_host)
    kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=SwactUncontrolled.NAME, init_time=init_time,
                              log_path=SwactUncontrolled.LOG_PATH, end_pattern=SwactUncontrolled.END, host=end_host,
                              start_host=start_host, start_pattern=SwactUncontrolled.START,
                              start_path=SwactUncontrolled.START_PATH, uptime=5, fail_ok=False)
