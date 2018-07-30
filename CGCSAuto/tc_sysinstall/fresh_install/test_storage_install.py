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
             - Install controller-0
             - Download configuration files, heat templates, images, and licenses
             - Configure controller-0, run lab_setup, and unlock controller-0
             -
         """
    lab = install_setup["lab"]
    hosts = lab["hosts"]
    boot_device = lab['boot_device_dict']
    controller0_node = lab["controller-0"]
    final_step = install_setup["control"]["stop"]
    patch_dir = install_setup["directories"]["patches"]
    patch_server = install_setup["servers"]["patches"]
    guest_server = install_setup["servers"]["guest"]

    if final_step == '0' or final_step == "setup":
        skip("stopping at install step: {}".format(LOG.test_step))

    fresh_install_helper.install_controller(sys_type=SysType.STORAGE, patch_dir=patch_dir,
                                            patch_server_conn=patch_server.ssh_conn)
    controller0_node.telnet_conn.login()
    controller0_node.telnet_conn.flush()
    fresh_install_helper.set_software_version_var(use_telnet=True, con_telnet=controller0_node.telnet_conn)

    lab_files_server = install_setup["servers"]["lab_files"]
    build_server = install_setup["servers"]["build"]
    fresh_install_helper.download_lab_files(lab_files_server=lab_files_server, build_server=build_server,
                                            guest_server=guest_server,
                                            load_path=InstallVars.get_install_var("TIS_BUILD_DIR"),
                                            license_path=InstallVars.get_install_var("LICENSE"),
                                            guest_path=InstallVars.get_install_var('GUEST_IMAGE'))

    fresh_install_helper.configure_controller(controller0_node)
    if controller0_node.ssh_conn is None:
        controller0_node.ssh_conn = install_helper.establish_ssh_connection(controller0_node.host_ip)

    fresh_install_helper.bulk_add_hosts(lab=lab, con_ssh=controller0_node.ssh_conn)

    fresh_install_helper.boot_hosts(boot_device)

    fresh_install_helper.run_lab_setup(con_ssh=controller0_node.ssh_conn)

    fresh_install_helper.unlock_hosts(["controller-1"], con_ssh=controller0_node.ssh_conn)

    fresh_install_helper.run_lab_setup(con_ssh=controller0_node.ssh_conn)

    fresh_install_helper.unlock_hosts([storage_host for storage_host in hosts if "storage" in storage_host],
                                       con_ssh=controller0_node.ssh_conn)

    fresh_install_helper.run_lab_setup(con_ssh=controller0_node.ssh_conn)

    fresh_install_helper.unlock_hosts([compute_host for compute_host in hosts if "compute" in compute_host],
                                      con_ssh=controller0_node.ssh_conn)

    fresh_install_helper.run_lab_setup(con_ssh=controller0_node.ssh_conn)

    if lab.get("floating ip"):
        collect_sys_net_info(lab)
        setup_tis_ssh(lab)

    fresh_install_helper.check_heat_resources(con_ssh=controller0_node.ssh_conn)

    fresh_install_helper.attempt_to_run_post_install_scripts()
    fresh_install_helper.reset_global_vars()
