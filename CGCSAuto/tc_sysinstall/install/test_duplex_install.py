import pytest

from keywords import host_helper, install_helper, vlm_helper
from utils.clients.ssh import ControllerClient
from setups import setup_heat, setup_networking
from utils.tis_log import LOG
from consts.proj_vars import ProjVar


def test_duplex_install(install_setup):
    """
         Complete install steps for a duplex lab

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
    hosts = lab["hosts"]
    lab_type = lab["system_mode"]
    boot_device = lab["boot_device_dict"]
    output_dir = ProjVar.get_var("LOG_DIR")
    active_controller = install_setup["active_controller"]
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
    LOG.info("running lab setup for CPE lab")
    install_helper.run_lab_setup()
    LOG.info("unlocking {}".format(controller_name))
    install_helper.unlock_controller(controller_name, con_ssh=active_controller.ssh_conn, available_only=False)

    if "duplex" not in lab_type:
        pytest.skip("lab is not a duplex lab")

    LOG.tc_step("Bulk add hosts for CPE lab")
    rc, added_hosts, msg = install_helper.bulk_add_hosts(lab, "hosts_bulk_add.xml")
    assert rc == 0, msg
    # assert added_hosts[0] + added_hosts[1] + added_hosts[2] == hosts, "hosts_bulk_add failed to add all hosts"

    LOG.tc_step("Run lab setup for CPE lab")
    install_helper.run_lab_setup()
    # TODO: Find out if necessary
    install_helper.run_lab_setup()

    LOG.tc_step("Boot standby controller for CPE lab")
    standby_con = lab["controller-1"]
    install_helper.bring_node_console_up(standby_con, boot_device,
                                                 small_footprint=True,
                                                 vlm_power_on=True,
                                                 close_telnet_conn=True,
                                                 boot_usb=False)

    LOG.tc_step("Run lab setup for CPE lab")
    install_helper.run_lab_setup()
    install_helper.run_lab_setup()

    LOG.tc_step("Unlock standby controller for CPE lab")
    host_helper.unlock_host(standby_con.name, available_only=True)

    LOG.tc_step("Run lab setup for CPE lab")
    install_helper.run_lab_setup()

    LOG.tc_step("Check heat resources")
    setup_heat()
    host_helper.wait_for_hosts_ready(hosts)


def test_post_install():
    connection = ControllerClient.get_active_controller()

    rc = connection.exec_cmd("test -d /home/wrsroot/postinstall/")[0]
    if rc != 0:
        pytest.skip("No post install directory")
    else:
        rc, msg = install_helper.post_install()
        assert rc == 0, msg
