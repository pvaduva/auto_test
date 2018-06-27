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
    skips = install_setup["skips"]
    skip_labsetup = "setup" in skips
    final_step = install_setup["control"]["stop"]

    if final_step <= 0:
        skip("stopping at install step: {}".format(LOG.test_step))

    LOG.tc_step("Install Controller")
    if fresh_install_helper.do_step():
        fresh_install_helper.install_controller(sys_type=SysType.AIO_SX)
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

    LOG.tc_step("Run lab setup for simplex lab")
    if fresh_install_helper.do_step() and not skip_labsetup:
        install_helper.run_lab_setup(con_ssh=controller0_node.ssh_conn)
    if LOG.test_step == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))

    setup_tis_ssh(lab)
    host_helper.wait_for_hosts_ready(controller0_node.name, con_ssh=controller0_node.ssh_conn)

    LOG.tc_step("Check heat resources")
    if fresh_install_helper.do_step():
        install_helper.setup_heat(con_ssh=controller0_node.ssh_conn)
