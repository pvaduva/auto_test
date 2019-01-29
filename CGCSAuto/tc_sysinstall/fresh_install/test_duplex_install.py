from pytest import skip, fixture

from consts.cgcs import SysType, Prompt
from consts.proj_vars import InstallVars, ProjVar
from keywords import host_helper, install_helper, vlm_helper
from tc_sysinstall.fresh_install import fresh_install_helper
from setups import setup_tis_ssh, collect_sys_net_info
from utils.tis_log import LOG


@fixture(scope='function')
def install_setup(request):
    lab = InstallVars.get_install_var("LAB")
    install_type = ProjVar.get_var('SYS_TYPE')
    if install_type != SysType.AIO_DX:
        skip("The specified lab is not {} type. It is {} and use the appropriate test install script".
             format(SysType.AIO_DX, install_type))

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

    return _install_setup


def test_duplex_install(install_setup):
    """
         Complete fresh_install steps for a duplex lab
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
             - Add the standby controller
             - Run the lab_setup.sh script
             - Re-add the standby controller
             - Run the lab_setup.sh script
             - Install the Standby Controller
             - Run the lab_setup.sh script twice
             - Unlock the standby controller
             - Run the lab_setup.sh script
         """
    lab = install_setup["lab"]
    boot_device = lab["boot_device_dict"]
    controller0_node = lab["controller-0"]
    final_step = install_setup["control"]["stop"]
    patch_dir = install_setup["directories"]["patches"]
    patch_server = install_setup["servers"]["patches"]
    guest_server = install_setup["servers"]["guest"]
    install_subcloud = install_setup.get("install_subcloud")
    lab_files_server = install_setup["servers"]["lab_files"]

    if final_step == '0' or final_step == "setup":
        skip("stopping at install step: {}".format(LOG.test_step))

    fresh_install_helper.install_controller(sys_type=SysType.AIO_DX, patch_dir=patch_dir,
                                            patch_server_conn=patch_server.ssh_conn)
    controller0_node.telnet_conn.login()
    controller0_node.telnet_conn.flush()
    fresh_install_helper.set_software_version_var(use_telnet=True, con_telnet=controller0_node.telnet_conn)

    build_server = install_setup["servers"]["build"]
    fresh_install_helper.download_lab_files(lab_files_server=lab_files_server, build_server=build_server,
                                            guest_server=guest_server,
                                            load_path=InstallVars.get_install_var("TIS_BUILD_DIR"),
                                            license_path=InstallVars.get_install_var("LICENSE"),
                                            guest_path=InstallVars.get_install_var('GUEST_IMAGE'))

    if install_subcloud:
        fresh_install_helper.configure_subcloud(controller0_node, lab_files_server, subcloud=install_subcloud,
                                                final_step=final_step)
    else:
        fresh_install_helper.configure_controller(controller0_node)

    controller0_node.telnet_conn.hostname = r"controller\-[01]"
    controller0_node.telnet_conn.set_prompt(Prompt.CONTROLLER_PROMPT)
    if controller0_node.ssh_conn is None:
        controller0_node.ssh_conn = install_helper.establish_ssh_connection(controller0_node.host_ip)

    fresh_install_helper.bulk_add_hosts(lab=lab, con_ssh=controller0_node.ssh_conn)

    fresh_install_helper.run_lab_setup(con_ssh=controller0_node.ssh_conn)

    fresh_install_helper.boot_hosts(boot_device)

    host_helper.wait_for_hosts_ready(["controller-1"], con_ssh=controller0_node.ssh_conn)
    fresh_install_helper.run_lab_setup(con_ssh=controller0_node.ssh_conn)
    fresh_install_helper.run_lab_setup(con_ssh=controller0_node.ssh_conn)

    fresh_install_helper.unlock_hosts(["controller-1"], con_ssh=controller0_node.ssh_conn)

    fresh_install_helper.run_lab_setup(con_ssh=controller0_node.ssh_conn)

    if lab.get("floating ip"):
        collect_sys_net_info(lab)
        setup_tis_ssh(lab)
    fresh_install_helper.wait_for_hosts_ready(controller0_node.name, lab=lab)

    fresh_install_helper.check_heat_resources(con_ssh=controller0_node.ssh_conn)

    #fresh_install_helper.attempt_to_run_post_install_scripts()
    fresh_install_helper.reset_global_vars()
    fresh_install_helper.verify_install_uuid(lab)
