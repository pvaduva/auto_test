from pytest import skip

from consts.cgcs import SysType
from consts.filepaths import BuildServerPath
from consts.proj_vars import InstallVars
from keywords import host_helper, install_helper, vlm_helper, system_helper
from utils.clients.ssh import SSHClient
from setups import setup_tis_ssh
from tc_sysinstall.fresh_install import fresh_install_helper
from utils.tis_log import LOG


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

    fresh_install_helper.set_final_step(final_step)
    if final_step == '0' or final_step == "setup":
        skip("stopping at install step: {}".format(LOG.test_step))

    fresh_install_helper.install_controller(sys_type=SysType.AIO_SX, patch_dir=patch_dir,
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

    fresh_install_helper.run_lab_setup(controller0_node.ssh_conn)

    if lab.get("floating ip"):
        setup_tis_ssh(lab)
    host_helper.wait_for_hosts_ready(controller0_node.name, con_ssh=controller0_node.ssh_conn)

    fresh_install_helper.check_heat_resources(con_ssh=controller0_node.ssh_conn)

    fresh_install_helper.attempt_to_run_post_install_scripts()
    fresh_install_helper.reset_global_vars()
