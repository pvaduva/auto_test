from pytest import skip
import threading

from consts.cgcs import SysType
from consts.filepaths import BuildServerPath
from consts.proj_vars import InstallVars
from keywords import host_helper, system_helper, install_helper, vlm_helper
from tc_sysinstall.fresh_install import fresh_install_helper
from utils.clients.ssh import SSHClient
from setups import setup_tis_ssh, collect_sys_net_info
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
    lab = install_setup["lab"]
    hosts = lab["hosts"]
    boot_device = lab['boot_device_dict']
    controller0_node = lab["controller-0"]
    final_step = install_setup["control"]["stop"]
    patch_dir = install_setup["directories"]["patches"]
    patch_server = install_setup["servers"]["patches"]

    if final_step <= 0:
        skip("stopping at install step: {}".format(LOG.test_step))

    LOG.tc_step("Install Controller")
    if fresh_install_helper.do_step():
        fresh_install_helper.install_controller(sys_type=SysType.AIO_SX, patch_dir=patch_dir,
                                                patch_server_conn=patch_server.ssh_conn)
    if LOG.test_step == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))

    controller0_node.telnet_conn.login()
    fresh_install_helper.set_software_version_var(use_telnet=True, con_telnet=controller0_node.telnet_conn)

    LOG.tc_step("Download lab files")
    lab_files_server = install_setup["servers"]["lab_files"]
    build_server = install_setup["servers"]["build"]
    if fresh_install_helper.do_step():
        fresh_install_helper.download_lab_files(lab_files_server=lab_files_server, build_server=build_server)
    if LOG.test_step == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))

    LOG.tc_step("Configure controller")
    if fresh_install_helper.do_step():
        fresh_install_helper.configure_controller(controller0_node)
    if LOG.test_step == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))

    if controller0_node.ssh_conn is None:
        controller0_node.ssh_conn = install_helper.establish_ssh_connection(controller0_node.host_ip)

    LOG.tc_step("Bulk add hosts")
    if fresh_install_helper.do_step():
        rc, added_hosts, msg = install_helper.bulk_add_hosts(lab, "hosts_bulk_add.xml", con_ssh=controller0_node.ssh_conn)
        assert rc == 0, msg
        # assert added_hosts[0] + added_hosts[1] + added_hosts[2] == hosts, "hosts_bulk_add failed to add all hosts
    if LOG.test_step == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))

    # TODO: improve logging, possibly create keyword, and use multi_thread module
    LOG.tc_step("Boot other lab hosts")
    if fresh_install_helper.do_step():
        host_objects = [lab[hostname] for hostname in hosts if controller0_node.name not in hostname]
        install_helper.boot_hosts(boot_device, nodes=host_objects)
    if LOG.test_step == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))

    LOG.tc_step("Run lab setup")
    if fresh_install_helper.do_step():
        install_helper.run_lab_setup(con_ssh=controller0_node.ssh_conn)
        install_helper.run_lab_setup(con_ssh=controller0_node.ssh_conn)
    if LOG.test_step == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))

    LOG.tc_step("Unlock other hosts")
    if fresh_install_helper.do_step():
        host_helper.unlock_hosts([host for host in hosts if controller0_node.name not in host],
                                 con_ssh=controller0_node.ssh_conn)
        host_helper.wait_for_hosts_ready(hosts, con_ssh=controller0_node.ssh_conn)
    if LOG.test_step == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))

    LOG.tc_step("Run lab setup")
    if fresh_install_helper.do_step():
        install_helper.run_lab_setup(con_ssh=controller0_node.ssh_conn)
    if LOG.test_step == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))

    collect_sys_net_info(lab)
    setup_tis_ssh(lab)
    host_helper.wait_for_hosts_ready(controller0_node.name, con_ssh=controller0_node.ssh_conn)

    LOG.tc_step("Check heat resources")
    if fresh_install_helper.do_step():
        install_helper.setup_heat()
        fresh_install_helper.clear_post_install_alarms()
    if LOG.test_step == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))

    LOG.tc_step("Attempt to run post install scripts")
    if fresh_install_helper.do_step():
        rc, msg = install_helper.post_install()
        LOG.info(msg)
        assert rc >= 0, msg
