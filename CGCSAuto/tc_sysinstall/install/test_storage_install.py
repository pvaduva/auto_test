import pytest
import threading

from keywords import host_helper, system_helper, install_helper, vlm_helper
from utils.clients.ssh import ControllerClient
from setups import setup_heat, setup_networking
from utils.tis_log import LOG
from consts.proj_vars import ProjVar


def test_storage_install(install_setup):
    """
         Configure the active controller

         Prerequisites:
             - pxeboot has been setup.
         Test Setups:
             - Retrieve dictionary containing lab information
             - Retrive required paths to directories, images, and licenses
             - Determine active controller
             - Initialize build server and boot server objects
             - Retrieve what steps to be skipped
         Test Steps:
             - Wipe the disks if specified
             - Turn off the active controller
             - Boot the active controller
             - rsync the required files to the the active controller
             - Run the config_controller command using the TiS_config.ini_centos file
             - Run the lab_setup.sh script
             - Unlock the active controller
         """
    lab = install_setup["lab"]
    hosts = lab["hosts"]
    lab_type = lab["system_mode"]
    active_con = install_setup["active_controller"]
    boot_device = lab['boot_device_dict']
    threads = []
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
    LOG.info("running lab setup for storage lab")
    install_helper.run_lab_setup()
    LOG.info("unlocking {}".format(controller_name))
    install_helper.unlock_controller(controller_name, con_ssh=active_controller.ssh_conn)

    if lab_type is not "storage":
        pytest.skip("lab is not a storage lab")

    LOG.tc_step("Bulk add hosts")
    rc, added_hosts, msg = install_helper.bulk_add_hosts(lab, "hosts_bulk_add.xml")
    assert rc == 0, msg
    # assert added_hosts[0] + added_hosts[1] + added_hosts[2] == hosts, "hosts_bulk_add failed to add all hosts

    LOG.tc_step("Run lab setup")
    install_helper.run_lab_setup()

    LOG.tc_step("Boot other lab hosts")
    for hostname in hosts:
        if active_con.name not in hostname:
            host_thread = threading.Thread(target=install_helper.bring_node_console_up, name=hostname,
                                           args=(lab[hostname], boot_device),
                                           kwargs={'vlm_power_on': True, "close_telnet_conn": True, "boot_usb": False})
            threads.append(host_thread)
            LOG.info("Starting thread for {}".format(host_thread.name))
            host_thread.start()
    for thread in threads:
        thread.join()

    LOG.tc_step("Run lab setup")
    install_helper.run_lab_setup()
    install_helper.run_lab_setup()

    LOG.tc_step("Unlock controller-1")
    host_helper.unlock_host("controller-1", available_only=True)

    LOG.tc_step("Run lab setup")
    install_helper.run_lab_setup()

    LOG.tc_step("Unlock storage nodes")
    host_helper.unlock_hosts([storage_host for storage_host in hosts if "storage" in storage_host])
    host_helper.wait_for_hosts_ready([storage_host for storage_host in hosts if "storage" in storage_host])

    LOG.tc_step("Run lab setup")
    install_helper.run_lab_setup()

    LOG.tc_step("Unlock compute nodes")
    host_helper.unlock_hosts([compute_host for compute_host in hosts if "compute" in compute_host])
    host_helper.wait_for_hosts_ready([compute_host for compute_host in hosts if "compute" in compute_host])

    LOG.tc_step("Run lab setup")
    install_helper.run_lab_setup()

    setup_heat()
    system_helper.wait_for_alarms_gone([("400.001", None), ("800.001", None)], timeout=1800, check_interval=60)
    alarm = system_helper.get_alarms(alarm_id='250.001')
    if alarm:
        LOG.tc_step("Swact lock/unlock host")
        rc, msg = host_helper.lock_unlock_controllers()
        assert rc == 0, msg

    LOG.tc_step("Run post-install scripts (if any)")
    rc = active_controller.ssh_conn.exec_cmd("test -d /home/wrsroot/postinstall/")
    if rc != 0:
        LOG.info("no post-install directory on {}".format(active_controller.name))
    else:
        rc, msg = install_helper.post_install()
        assert rc == 0, msg
