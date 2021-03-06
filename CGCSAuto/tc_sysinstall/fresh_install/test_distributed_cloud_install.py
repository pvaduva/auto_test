import pytest

from consts.stx import SysType, Prompt
from consts.proj_vars import InstallVars, ProjVar
from keywords import host_helper, install_helper, vlm_helper, container_helper
from tc_sysinstall.fresh_install import fresh_install_helper
from setups import setup_tis_ssh, collect_sys_net_info
from utils.tis_log import LOG


@pytest.fixture(scope='session')
def install_setup(request):
    lab = InstallVars.get_install_var("LAB")
    subclouds = []
    dist_cloud = InstallVars.get_install_var("DISTRIBUTED_CLOUD")
    if not dist_cloud:
        pytest.skip("The specified lab {} is not a distributed cloud system".format(lab['short_name']))

    subclouds.extend([k for k in lab if 'subcloud' in k])
    central_lab = lab['central_region']

    lab['central_region']['hosts'] = vlm_helper.get_hostnames_from_consts(central_lab)
    barcodes = vlm_helper.get_barcodes_from_hostnames(lab['central_region']["hosts"], lab=central_lab)

    for subcloud in subclouds:
        lab[subcloud]["hosts"] = vlm_helper.get_hostnames_from_consts(lab[subcloud])
        barcodes.extend(vlm_helper.get_barcodes_from_hostnames(lab[subcloud]["hosts"], lab=lab[subcloud]))

    active_con = central_lab["controller-0"]
    install_type = ProjVar.get_var('SYS_TYPE')

    LOG.tc_setup_start("{} install".format(install_type))
    LOG.fixture_step("Reserve hosts")

    LOG.tc_setup_start("{} install".format(install_type))
    LOG.fixture_step("Reserve hosts")

    hosts = {'central_region': central_lab['hosts']}
    for subcloud in subclouds:
        hosts[subcloud] = lab[subcloud]["hosts"]

    LOG.info("Un-reserving {}".format(hosts))

    vlm_helper.force_unreserve_hosts(barcodes, val="barcodes")

    LOG.info("Reserving {}".format(hosts))
    for barcode in barcodes:
        vlm_helper._reserve_vlm_console(barcode, "AUTO: lab installation")

    LOG.fixture_step("Attempt to reset port on controller-0")
    fresh_install_helper.reset_controller_telnet_port(active_con)

    def install_cleanup():
        fresh_install_helper.install_teardown(lab, active_con, central_lab)

    request.addfinalizer(install_cleanup)

    _install_setup = fresh_install_helper.setup_fresh_install(lab, dist_cloud)
    resume_step = InstallVars.get_install_var("RESUME")
    if resume_step and resume_step not in \
            ["setup", "install_controller", "configure_controller", "download_lab_files"]:
        try:
            if active_con.ssh_conn is None:
                active_con.ssh_conn = install_helper.ssh_to_controller(active_con.host_ip)
        except:
            pass

    return _install_setup


def test_distributed_cloud_install(install_setup):
    """
         Configure the active controller

         Prerequisites:
             - pxeboot has been setup.
         Test Setups:
             - Retrieve dictionary containing lab information
             - Retrieve required paths to directories, images, and licenses
             - Determine active controller
             - Initialize build server and boot server objects
             - Retrieve what steps to be skipped
         Test Steps:
             - Install controller-0
             - Download configuration files, heat templates, images, and licenses
             - Configure controller-0, run lab_setup, and unlock controller-0
             - Add the other hosts
             - Boot the other hosts
             - Run lab setup
             - Unlock the other hosts
             - Run lab setup
             - Setup heat resources and clear any install related alarms
         """
    dc_lab = install_setup["lab"]
    central_region_lab = dc_lab['central_region']

    hosts = dc_lab['central_region']["hosts"]
    boot_device = central_region_lab['boot_device_dict']
    controller0_node = central_region_lab["controller-0"]
    final_step = install_setup["control"]["stop"]
    patch_dir = install_setup["directories"]["patches"]
    patch_server = install_setup["servers"]["patches"]
    guest_server = install_setup["servers"]["guest"]

    if final_step == '0' or final_step == "setup":
        pytest.skip("stopping at install step: {}".format(LOG.test_step))

    fresh_install_helper.install_controller(lab=central_region_lab, sys_type=SysType.DISTRIBUTED_CLOUD,
                                            patch_dir=patch_dir, patch_server_conn=patch_server.ssh_conn,
                                            init_global_vars=True)
    # controller0_node.telnet_conn.login()
    # controller0_node.telnet_conn.flush()
    # fresh_install_helper.set_software_version_var(use_telnet=True, con_telnet=controller0_node.telnet_conn)

    lab_files_server = install_setup["servers"]["lab_files"]
    build_server = install_setup["servers"]["build"]
    load_path = InstallVars.get_install_var("TIS_BUILD_DIR")
    ipv6_install = InstallVars.get_install_var("DC_IPV6")

    fresh_install_helper.download_lab_files(lab=central_region_lab, lab_files_server=lab_files_server,
                                            build_server=build_server,
                                            guest_server=guest_server,
                                            load_path=load_path,
                                            license_path=InstallVars.get_install_var("LICENSE"),
                                            guest_path=InstallVars.get_install_var('GUEST_IMAGE'))

    # TODO Change config and lab setup files to common name
    fresh_install_helper.configure_controller_(controller0_node, lab=central_region_lab, banner=False, branding=False)

    fresh_install_helper.wait_for_deploy_mgr_controller_config(controller0_node, lab=central_region_lab)

    controller0_node.telnet_conn.hostname = "controller\-[01]"
    controller0_node.telnet_conn.set_prompt(Prompt.CONTROLLER_PROMPT)
    if controller0_node.ssh_conn is None:
        controller0_node.ssh_conn = install_helper.ssh_to_controller(controller0_node.host_ip)

    fresh_install_helper.wait_for_deployment_mgr_to_bulk_add_hosts(controller0_node, lab=central_region_lab)

    LOG.info("Booting standby controller host...")

    # TODO: get controller-1 hostname
    fresh_install_helper.boot_hosts(boot_device, hostnames=['controller-1'], lab=central_region_lab,
                                    wait_for_online=False)
    host_helper.wait_for_hosts_ready([host for host in hosts if controller0_node.name not in host],
                                     con_ssh=controller0_node.ssh_conn)

    fresh_install_helper.wait_for_deploy_mgr_lab_config(controller0_node, lab=central_region_lab)

    fresh_install_helper.wait_for_hosts_ready(["controller-1"], lab=central_region_lab)
    container_helper.wait_for_apps_status(apps='platform-integ-apps', timeout=1800,
                                          con_ssh=controller0_node.ssh_conn, status='applied')
    LOG.info("Running lab setup script ...")
    fresh_install_helper.run_lab_setup(con_ssh=controller0_node.ssh_conn)

    if dc_lab.get("floating ip"):
        collect_sys_net_info(dc_lab)
        setup_tis_ssh(dc_lab)

    fresh_install_helper.wait_for_hosts_ready(controller0_node.name, lab=central_region_lab)

    fresh_install_helper.attempt_to_run_post_install_scripts(controller0_node=controller0_node)

    fresh_install_helper.reset_global_vars()
    fresh_install_helper.verify_install_uuid(lab=central_region_lab)
    fresh_install_helper.validate_deployment_mgr_install(controller0_node, central_region_lab)
