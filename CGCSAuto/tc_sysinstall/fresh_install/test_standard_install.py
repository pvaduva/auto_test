from pytest import skip
import threading

from consts.cgcs import SysType
from consts.filepaths import BuildServerPath
from consts.proj_vars import InstallVars
from keywords import host_helper, system_helper, install_helper, vlm_helper
from tc_sysinstall.fresh_install import fresh_install_helper
from utils.clients.ssh import SSHClient
from setups import setup_tis_ssh
from utils.tis_log import LOG


def test_standard_install(install_setup):
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
    boot_device = lab['boot_device_dict']
    threads = []
    active_controller = install_setup["active_controller"]
    controller_name = active_controller.name
    boot_type = install_setup["boot"]["boot_type"]
    last_session_step = install_setup["control"]["resume"]
    final_step = install_setup["control"]["stop"]

    if final_step <= 0:
        skip("stopping at install step: {}".format(LOG.test_step))

    LOG.tc_step("Install Controller")
    if last_session_step <= LOG.test_step:
        fresh_install_helper.install_controller(sys_type=SysType.REGULAR)
    else:
        LOG.info("Skipping step because resume flag was given")
    if LOG.test_step == final_step:
        # TODO: temporary way of doing this
        skip("stopping at install step: {}".format(LOG.test_step))

    active_controller.telnet_conn.login()
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

    if active_controller.ssh_conn is None:
        active_controller.ssh_conn = install_helper.establish_ssh_connection(active_controller.host_ip)

    LOG.tc_step("Bulk add hosts")
    if last_session_step <= LOG.test_step:
        rc, added_hosts, msg = install_helper.bulk_add_hosts(lab, "hosts_bulk_add.xml", con_ssh=active_controller.ssh_conn)
        assert rc == 0, msg
        # assert added_hosts[0] + added_hosts[1] + added_hosts[2] == hosts, "hosts_bulk_add failed to add all hosts
    else:
        LOG.info("Skipping step because resume flag was given")
    if LOG.test_step == final_step:
        # TODO: temporary way of doing this
        skip("stopping at install step: {}".format(LOG.test_step))

    LOG.tc_step("Boot other lab hosts")
    if last_session_step <= LOG.test_step:
        for hostname in hosts:
            if controller_name not in hostname:
                host_thread = threading.Thread(target=install_helper.bring_node_console_up, name=hostname,
                                               args=(lab[hostname], boot_device),
                                               kwargs={'vlm_power_on': True, "close_telnet_conn": True, "boot_usb": False,
                                                       "small_footprint": False})
                threads.append(host_thread)
                LOG.info("Starting thread for {}".format(host_thread.name))
                host_thread.start()
        for thread in threads:
            thread.join()
    else:
        LOG.info("Skipping step because resume flag was given")
    if LOG.test_step == final_step:
        # TODO: temporary way of doing this
        skip("stopping at install step: {}".format(LOG.test_step))

    LOG.tc_step("Run lab setup")
    if last_session_step <= LOG.test_step:
        install_helper.run_lab_setup(con_ssh=active_controller.ssh_conn)
        install_helper.run_lab_setup(con_ssh=active_controller.ssh_conn)
    else:
        LOG.info("Skipping step because resume flag was given")
    if LOG.test_step == final_step:
        # TODO: temporary way of doing this
        skip("stopping at install step: {}".format(LOG.test_step))

    LOG.tc_step("Unlock other hosts")
    if last_session_step <= LOG.test_step:
         host_helper.unlock_hosts([host for host in hosts if controller_name not in host], con_ssh=active_controller.ssh_conn)
         host_helper.wait_for_hosts_ready(hosts, con_ssh=active_controller.ssh_conn)
    else:
        LOG.info("Skipping step because resume flag was given")
    if LOG.test_step == final_step:
        # TODO: temporary way of doing this
        skip("stopping at install step: {}".format(LOG.test_step))

    LOG.tc_step("Run lab setup")
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
        fresh_install_helper.clear_post_install_alarms()
    else:
        LOG.info("Skipping step because resume flag was given")
    if LOG.test_step == final_step:
        # TODO: temporary way of doing this
        skip("stopping at install step: {}".format(LOG.test_step))

    LOG.tc_step("Run post-fresh_install scripts if any")
    rc = active_controller.ssh_conn.exec_cmd("test -d /home/wrsroot/postinstall/")
    if rc != 0:
        LOG.info("no post-fresh_install directory on {}".format(active_controller.name))
    else:
        rc, msg = install_helper.post_install()
        assert rc == 0, msg
