from pytest import skip, fixture

from consts.stx import SysType, Prompt
from consts.proj_vars import InstallVars, ProjVar
from keywords import install_helper, vlm_helper, container_helper
from setups import setup_tis_ssh
from tc_sysinstall.fresh_install import fresh_install_helper
from utils.tis_log import LOG


@fixture(scope='function')
def install_setup(request):
    lab = InstallVars.get_install_var("LAB")
    install_type = ProjVar.get_var('SYS_TYPE')
    if install_type != SysType.AIO_SX:
        skip("The specified lab is not {} type. It is {} and use the appropriate test install script"
             .format(SysType.AIO_SX, install_type))

    lab["hosts"] = vlm_helper.get_hostnames_from_consts(lab)
    barcodes = vlm_helper.get_barcodes_from_hostnames(lab["hosts"])
    active_con = lab["controller-0"]

    LOG.tc_setup_start("{} install".format(install_type))

    LOG.fixture_step("Reserve hosts")
    hosts = lab["hosts"]
    LOG.info("Un-reserving {}".format(hosts))
    vlm_helper.force_unreserve_hosts(hosts)
    LOG.info("Reserving {}".format(hosts))
    for barcode in barcodes:
        vlm_helper._reserve_vlm_console(barcode, "AUTO: lab installation")

    LOG.fixture_step("Attempt to reset port on controller-0")
    fresh_install_helper.reset_controller_telnet_port(active_con)

    def install_cleanup():
        fresh_install_helper.install_teardown(lab, active_con)

    request.addfinalizer(install_cleanup)

    is_subcloud = InstallVars.get_install_var("INSTALL_SUBCLOUD") is not None
    _install_setup = fresh_install_helper.setup_fresh_install(lab, subcloud=is_subcloud)
    resume_step = InstallVars.get_install_var("RESUME")
    if resume_step and resume_step not in \
            ["setup", "install_controller", "configure_controller", "download_lab_files"]:

        try:
            if active_con.ssh_conn is None:
                active_con.ssh_conn = install_helper.ssh_to_controller(active_con.host_ip)
        except:
            pass

    return _install_setup


def test_simplex_install(install_setup):
    """
     Complete fresh_install steps for a simplex lab
     Test Setups:
         - Retrieve dictionary containing lab information
         - Retrieve required paths to directories, images, and licenses
         - Initialize build server and boot server objects
         - Retrieve what steps to be skipped
     Test Steps:
         - Install controller-0
         - Download configuration files, heat templates, images, and licenses
         - Configure controller-0, run lab_setup, and unlock controller-0
         - Run lab setup script if specified
         - Setup heat resources
     """
    lab = install_setup["lab"]
    controller0_node = lab["controller-0"]
    final_step = install_setup["control"]["stop"]
    patch_dir = install_setup["directories"]["patches"]
    patch_server = install_setup["servers"]["patches"]
    guest_server = install_setup["servers"]["guest"]
    install_subcloud = install_setup.get("install_subcloud")
    helm_chart_server = install_setup["servers"]["helm_charts"]

    if final_step == '0' or final_step == "setup":
        skip("stopping at install step: {}".format(LOG.test_step))

    fresh_install_helper.install_controller(sys_type=SysType.AIO_SX, patch_dir=patch_dir,
                                            patch_server_conn=patch_server.ssh_conn, init_global_vars=True)
    # controller0_node.telnet_conn.login()
    # controller0_node.telnet_conn.flush()
    # fresh_install_helper.set_software_version_var(use_telnet=True, con_telnet=controller0_node.telnet_conn)

    lab_files_server = install_setup["servers"]["lab_files"]
    build_server = install_setup["servers"]["build"]
    fresh_install_helper.download_lab_files(lab_files_server=lab_files_server, build_server=build_server,
                                            guest_server=guest_server,
                                            load_path=InstallVars.get_install_var("TIS_BUILD_DIR"),
                                            license_path=InstallVars.get_install_var("LICENSE"),
                                            guest_path=InstallVars.get_install_var('GUEST_IMAGE'),
                                            helm_chart_server=helm_chart_server)

    if install_subcloud:
        fresh_install_helper.configure_subcloud(controller0_node, install_setup["dc_system_controller"],
                                                subcloud=install_subcloud, final_step=final_step)
    else:
        fresh_install_helper.configure_controller_(controller0_node)

    deploy_mgr = fresh_install_helper.use_deploy_manager(controller0_node, lab)
    if not deploy_mgr:
        # fresh_install_helper.collect_lab_config_yaml(lab, build_server, stage=fresh_install_helper.DEPLOY_INTITIAL)

        fresh_install_helper.run_lab_setup(con_ssh=controller0_node.ssh_conn)
        fresh_install_helper.unlock_active_controller(controller0_node)
        controller0_node.telnet_conn.hostname = r"controller\-[01]"
        controller0_node.telnet_conn.set_prompt(Prompt.CONTROLLER_PROMPT)
    else:
        fresh_install_helper.wait_for_deploy_mgr_controller_config(controller0_node, lab=lab)

    if controller0_node.ssh_conn is None:
        controller0_node.ssh_conn = install_helper.ssh_to_controller(controller0_node.host_ip)
    install_helper.update_auth_url(ssh_con=controller0_node.ssh_conn)

    container_helper.wait_for_apps_status(apps='platform-integ-apps', timeout=1800,
                                          con_ssh=controller0_node.ssh_conn, status='applied')
    fresh_install_helper.run_lab_setup(controller0_node.ssh_conn)

    if lab.get("floating ip"):
        setup_tis_ssh(lab)

    fresh_install_helper.wait_for_hosts_ready(controller0_node.name, lab=lab)

    # fresh_install_helper.check_heat_resources(con_ssh=controller0_node.ssh_conn)
    if not deploy_mgr:
        fresh_install_helper.collect_lab_config_yaml(lab, build_server, stage=fresh_install_helper.DEPLOY_LAST)

    if install_subcloud:
        fresh_install_helper.wait_for_subcloud_to_be_managed(install_subcloud, install_setup["dc_system_controller"],
                                                             lab=lab)
    fresh_install_helper.attempt_to_run_post_install_scripts()

    fresh_install_helper.reset_global_vars()
