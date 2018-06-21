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
    skips = install_setup["skips"]
    skip_labsetup = "setup" in skips
    controller_name = active_controller.name
    boot_type = install_setup["boot"]["boot_type"]
    last_session_step = install_setup["control"]["resume"]
    final_step = install_setup["control"]["stop"]

    if final_step <= 0:
        skip("stopping at install step: {}".format(LOG.test_step))

    LOG.tc_step("Install Controller")
    if fresh_install_helper.do_step():
        fresh_install_helper.install_controller(sys_type=SysType.AIO_SX)
    if LOG.test_step == final_step:
        # TODO: temporary way of doing this
        skip("stopping at install step: {}".format(LOG.test_step))

    active_controller.telnet_conn.login()
    fresh_install_helper.set_software_version_var(use_telnet=True, con_telnet=active_controller.telnet_conn)

    LOG.tc_step("Download lab files")
    lab_files_server = install_setup["servers"]["lab_files"]
    build_server = install_setup["servers"]["build"]

    if fresh_install_helper.do_step():
        fresh_install_helper.download_lab_files(lab_files_server=lab_files_server, build_server=build_server)
    if LOG.test_step == final_step:
        # TODO: temporary way of doing this
        skip("stopping at install step: {}".format(LOG.test_step))

    LOG.tc_step("Configure controller")
    if fresh_install_helper.do_step():
        fresh_install_helper.configure_controller(active_controller)
    if LOG.test_step == final_step:
        # TODO: temporary way of doing this
        skip("stopping at install step: {}".format(LOG.test_step))

    if active_controller.ssh_conn is None:
        active_controller.ssh_conn = install_helper.establish_ssh_connection(active_controller.host_ip)

    if not skip_labsetup:
        LOG.tc_step("Run lab setup for simplex lab")
        if fresh_install_helper.do_step():
            install_helper.run_lab_setup(con_ssh=active_controller.ssh_conn)
        if LOG.test_step == final_step:
            # TODO: temporary way of doing this
            skip("stopping at install step: {}".format(LOG.test_step))
    else:
        LOG.info("--skip_lab_setup specified. Skipping lab setup")
    setup_tis_ssh(lab)
    host_helper.wait_for_hosts_ready(controller_name, con_ssh=active_controller.ssh_conn)

    LOG.tc_step("Check heat resources")
    if fresh_install_helper.do_step():
        fresh_install_helper.setup_heat(con_ssh=active_controller.ssh_conn)
        host_helper.wait_for_hosts_ready(["controller-0"], con_ssh=active_controller.ssh_conn)
    if LOG.test_step == final_step:
        # TODO: temporary way of doing this
        skip("stopping at install step: {}".format(LOG.test_step))

    LOG.tc_step("Run post-install scripts (if any)")
    rc = active_controller.ssh_conn.exec_cmd("test -d /home/wrsroot/postinstall/")
    if rc != 0:
        LOG.info("no post-fresh_install directory on {}".format(active_controller.name))
    else:
        rc, msg = install_helper.post_install()
        assert rc == 0, msg
