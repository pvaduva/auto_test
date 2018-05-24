import pytest

from keywords import host_helper, install_helper
from utils.clients.ssh import ControllerClient
from setups import setup_tis_ssh, setup_heat
from consts.cgcs import HostAvailState
from utils.tis_log import LOG

def test_simplex_install(install_setup):
    """
         Complete install steps for a simplex lab

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
    skip_lab_setup = install_setup["skips"]["lab_setup"]
    active_con = install_setup["active_controller"]
    lab = install_setup["lab"]
    active_controller = install_setup["active_controller"]
    controller_name = active_controller.name
    boot_type = install_setup["skips"]["boot_type"]
    is_cpe = (lab.get('system_type', 'Standard') == 'CPE')
    usb = ('usb' in boot_type) or ('burn' in boot_type)
    LOG.tc_step("Install Controller")
    install_helper.boot_controller(lab, small_footprint=is_cpe, boot_usb=usb)

    lab_files_server = install_setup["servers"]["lab_files"]
    build_server = install_setup["servers"]["build"]
    lab_files_dir = install_setup["directories"]["lab_files"]
    load_path = install_setup["directories"]["build"] + "/"
    guest_path = install_setup["paths"]["guest_img"]
    license_path = install_setup["paths"]["license"]

    LOG.tc_step("Download lab files")
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
    host_helper.wait_for_hosts_states(controller_name, availability=HostAvailState.ONLINE,
                                      use_telnet=True, con_telnet=active_controller.telnet_conn)
    LOG.info("unlocking {}".format(controller_name))
    install_helper.unlock_controller(controller_name, con_ssh=active_controller.ssh_conn)

    if not skip_lab_setup:
        LOG.tc_step("Run lab setup for simplex lab")
        install_helper.run_lab_setup()
        install_helper.run_lab_setup()
    else:
        LOG.info("--skip_lab_setup specified. Skipping lab setup")
    host_helper.wait_for_hosts_ready(active_con.name)
    LOG.tc_step("Check heat resources")
    setup_heat()
    host_helper.wait_for_hosts_ready(["controller-0"])
    # TODO: double check if it's installed as simplex


def test_post_install():
    connection = ControllerClient.get_active_controller()

    rc = connection.exec_cmd("test -d /home/wrsroot/postinstall/")[0]
    if rc != 0:
        pytest.skip("No post install directory")
    else:
        rc, msg = install_helper.post_install()
        assert rc == 0, msg