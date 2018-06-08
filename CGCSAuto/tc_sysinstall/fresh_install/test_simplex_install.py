import pytest

from consts.filepaths import BuildServerPath
from consts.proj_vars import InstallVars
from keywords import host_helper, install_helper, vlm_helper, system_helper
from utils.clients.ssh import SSHClient
from setups import setup_heat, setup_networking, setup_tis_ssh
from utils.tis_log import LOG


def test_simplex_install(install_setup):
    """
         Complete fresh_install steps for a simplex lab

         Prerequisites:
             - Controller is online
             - Controller has been configured
             - heat and lab setup files are on the active controller
         Test Setups:
             - Retrieve dictionary containing lab information
             - Retrive required paths to directories, images, and licenses
             - Determine active controller
             - Initialize build server and boot server objects
             - Retrieve what steps to be skipped
         Test Steps:
             - run lab setup script if specified
             - Setup heat resources
         """
    lab = install_setup["lab"]
    active_controller = install_setup["active_controller"]
    skip_labsetup = install_setup["skip_labsetup"]
    controller_name = active_controller.name
    boot_type = install_setup["boot"]["boot_type"]

    LOG.tc_step("Install Controller")
    security = install_setup["boot"]["security"]
    usb = ('usb' in boot_type) or ('burn' in boot_type)
    is_cpe = (lab.get('system_type', 'Standard') == 'CPE')
    low_lat = install_setup["boot"]["low_latency"]
    vlm_helper.power_off_hosts(lab["hosts"])
    install_helper.boot_controller(lab, small_footprint=is_cpe, boot_usb=usb, security=security, low_latency=low_lat)
    if usb:
        setup_networking(active_controller)

    LOG.tc_step("Download lab files")
    lab_files_server = install_setup["servers"]["lab_files"]
    build_server = install_setup["servers"]["build"]
    lab_files_dir = install_setup["directories"]["lab_files"]
    load_path = install_setup["directories"]["build"] + "/"
    guest_path = install_setup["paths"]["guest_img"]
    license_path = install_setup["paths"]["license"]
    system_version = system_helper.get_system_software_version(use_telnet=True, con_telnet=active_controller.telnet_conn)

    if license_path == BuildServerPath.DEFAULT_LICENSE_PATH:
        license_paths = BuildServerPath.TIS_LICENSE_PATHS[system_version]
        license_path = license_paths[2]
        InstallVars.set_install_var(license=license_path)

    if install_setup["directories"]["build"] == BuildServerPath.DEFAULT_HOST_BUILD_PATH:
        host_build_path = BuildServerPath.LATEST_HOST_BUILD_PATHS[system_version]
        load_path = host_build_path + "/"
        InstallVars.set_install_var(tis_build_dir=host_build_path)

    if guest_path == BuildServerPath.DEFAULT_GUEST_IMAGE_PATH:
        guest_path = BuildServerPath.GUEST_IMAGE_PATHS[system_version]
        InstallVars.set_install_var(guest_image=guest_path)

    LOG.info("Downloading lab config files")
    install_helper.download_lab_config_files(lab, lab_files_server, load_path, custom_path=lab_files_dir)
    LOG.info("Downloading heat templates")
    install_helper.download_heat_templates(lab, build_server, load_path)
    LOG.info("Downloading guest image")
    install_helper.download_image(lab, build_server, guest_path)
    LOG.info("Copying license")
    install_helper.download_license(lab, build_server, license_path, dest_name="license")

    LOG.tc_step("Configure controller")
    rc, output = install_helper.controller_system_config(active_controller, telnet_conn=active_controller.telnet_conn)
    if not active_controller.ssh_conn:
        active_controller.ssh_conn = install_helper.establish_ssh_connection(active_controller.host_ip)
    LOG.info("running lab setup for simplex lab")
    install_helper.run_lab_setup(con_ssh=active_controller.ssh_conn)
    LOG.info("unlocking {}".format(controller_name))

    install_helper.unlock_controller(controller_name, con_ssh=active_controller.ssh_conn)

    if not skip_labsetup:
        LOG.tc_step("Run lab setup for simplex lab")
        install_helper.run_lab_setup(con_ssh=active_controller.ssh_conn)
    else:
        LOG.info("--skip_lab_setup specified. Skipping lab setup")
    setup_tis_ssh(lab)
    host_helper.wait_for_hosts_ready(controller_name, con_ssh=active_controller.ssh_conn)

    LOG.tc_step("Check heat resources")
    setup_heat(con_ssh=active_controller.ssh_conn)
    host_helper.wait_for_hosts_ready(["controller-0"], con_ssh=active_controller.ssh_conn)

    LOG.tc_step("Run post-fresh_install scripts (if any)")
    rc = active_controller.ssh_conn.exec_cmd("test -d /home/wrsroot/postinstall/")
    if rc != 0:
        LOG.info("no post-fresh_install directory on {}".format(active_controller.name))
    else:
        rc, msg = install_helper.post_install()
        assert rc == 0, msg
