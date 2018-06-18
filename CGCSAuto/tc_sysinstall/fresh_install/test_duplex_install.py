from pytest import skip

from consts.cgcs import SysType
from consts.filepaths import BuildServerPath
from consts.proj_vars import InstallVars
from keywords import host_helper, install_helper, vlm_helper, system_helper
from tc_sysinstall.fresh_install import fresh_install_helper
from setups import setup_tis_ssh
from utils.tis_log import LOG


def test_duplex_install(install_setup):
    """
         Complete fresh_install steps for a duplex lab

         Prerequisites:
             - Controller is online
             - Controller has been configured
             - heat and lab setup files are on the active controller
         Test Setups:
             - Retrieve dictionary containing lab information
             - Retrieve required paths to directories, images, and licenses
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
    active_controller = install_setup["active_controller"]
    controller_name = active_controller.name
    standby_con = lab["controller-1"]
    boot_type = install_setup["boot"]["boot_type"]
    last_session_step = install_setup["control"]["resume"]
    final_step = install_setup["control"]["stop"]

    if final_step <= 0:
        skip("stopping at install step: {}".format(LOG.test_step))

    LOG.tc_step("Install Controller")
    if last_session_step <= LOG.test_step:
        fresh_install_helper.install_controller(sys_type=SysType.AIO_DX)
    else:
        LOG.info("Skipping step because resume flag was given")
    if LOG.test_step == final_step:
        # TODO: temporary way of doing this
        skip("stopping at install step: {}".format(LOG.test_step))

    fresh_install_helper.set_software_version_var(use_telnet=True, con_telnet=active_controller.telnet_conn)

    LOG.tc_step("Download lab files")
    lab_files_server = install_setup["servers"]["lab_files"]
    build_server = install_setup["servers"]["build"]

    if last_session_step <= LOG.test_step:
        fresh_install_helper.download_lab_files(lab_files_server=lab_files_server, build_server=build_server)
    else:
        LOG.info("Skipping step because resume flag was given")
    if LOG.test_step == final_step:
        # TODO: temporary way of doing this
        skip("stopping at install step: {}".format(LOG.test_step))

    LOG.tc_step("Configure controller")
    if last_session_step <= LOG.test_step:
        fresh_install_helper.configure_controller(active_controller)
    else:
        LOG.info("Skipping step because resume flag was given")
    if LOG.test_step == final_step:
        # TODO: temporary way of doing this
        skip("stopping at install step: {}".format(LOG.test_step))

    if not active_controller.ssh_conn:
        active_controller.ssh_conn = install_helper.establish_ssh_connection(active_controller.host_ip)

    LOG.tc_step("Bulk add hosts for CPE lab")
    if last_session_step <= LOG.test_step:
        rc, added_hosts, msg = install_helper.bulk_add_hosts(lab, "hosts_bulk_add.xml", con_ssh=active_controller.ssh_conn)
        assert rc == 0, msg
        # assert added_hosts[0] + added_hosts[1] + added_hosts[2] == hosts, "hosts_bulk_add failed to add all hosts"
    else:
        LOG.info("Skipping step because resume flag was given")
    if LOG.test_step == final_step:
        # TODO: temporary way of doing this
        skip("stopping at install step: {}".format(LOG.test_step))

    LOG.tc_step("Run lab setup for CPE lab")
    if last_session_step <= LOG.test_step:
        install_helper.run_lab_setup(con_ssh=active_controller.ssh_conn)
        # TODO: Find out if necessary
        install_helper.run_lab_setup(con_ssh=active_controller.ssh_conn)
    else:
        LOG.info("Skipping step because resume flag was given")
    if LOG.test_step == final_step:
        # TODO: temporary way of doing this
        skip("stopping at install step: {}".format(LOG.test_step))

    LOG.tc_step("Boot standby controller for CPE lab")
    if last_session_step <= LOG.test_step:
        install_helper.bring_node_console_up(standby_con, boot_device, small_footprint=True, vlm_power_on=True,
                                             close_telnet_conn=True, boot_usb=False)
    else:
        LOG.info("Skipping step because resume flag was given")
    if LOG.test_step == final_step:
        # TODO: temporary way of doing this
        skip("stopping at install step: {}".format(LOG.test_step))

    LOG.tc_step("Run lab setup for CPE lab")
    if last_session_step <= LOG.test_step:
        install_helper.run_lab_setup(con_ssh=active_controller.ssh_conn)
        install_helper.run_lab_setup(con_ssh=active_controller.ssh_conn)
    else:
        LOG.info("Skipping step because resume flag was given")
    if LOG.test_step == final_step:
        # TODO: temporary way of doing this
        skip("stopping at install step: {}".format(LOG.test_step))

    LOG.tc_step("Unlock standby controller for CPE lab")
    if last_session_step <= LOG.test_step:
        host_helper.unlock_host(standby_con.name, available_only=True, con_ssh=active_controller.ssh_conn)
    else:
        LOG.info("Skipping step because resume flag was given")
    if LOG.test_step == final_step:
        # TODO: temporary way of doing this
        skip("stopping at install step: {}".format(LOG.test_step))

    LOG.tc_step("Run lab setup for CPE lab")
    if last_session_step <= LOG.test_step:
        install_helper.run_lab_setup(con_ssh=active_controller.ssh_conn)
    else:
        LOG.info("Skipping step because resume flag was given")
    if LOG.test_step == final_step:
        # TODO: temporary way of doing this
        skip("stopping at install step: {}".format(LOG.test_step))

    setup_tis_ssh(lab)

    LOG.tc_step("Check heat resources")
    if last_session_step <= LOG.test_step:
        fresh_install_helper.setup_heat()
        host_helper.wait_for_hosts_ready(hosts)
    else:
        LOG.info("Skipping step because resume flag was given")
    if LOG.test_step == final_step:
        # TODO: temporary way of doing this
        skip("stopping at install step: {}".format(LOG.test_step))

    LOG.tc_step("Run post install scripts (if any)")
    rc = active_controller.ssh_conn.exec_cmd("test -d /home/wrsroot/postinstall/")
    if rc != 0:
        LOG.info("no post-fresh_install directory on {}".format(active_controller.name))
    else:
        rc, msg = install_helper.post_install()
        assert rc == 0, msg
