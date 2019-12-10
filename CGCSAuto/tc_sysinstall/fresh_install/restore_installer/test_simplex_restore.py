from pytest import skip, fixture

from consts.stx import SysType, Prompt
from consts.proj_vars import InstallVars, ProjVar, RestoreVars
from keywords import install_helper, vlm_helper
from setups import setup_tis_ssh
from utils.tis_log import LOG

from tc_sysinstall.fresh_install import fresh_install_helper
from tc_sysinstall.fresh_install.restore_installer import restore_helper


@fixture(scope='function')
def install_setup(request):
    lab = InstallVars.get_install_var("LAB")
    install_type = ProjVar.get_var('SYS_TYPE')
    if install_type != SysType.AIO_SX:
        skip("The specified lab is not {} type. It is {} and use the appropriate test install script"
             .format(SysType.AIO_SX, install_type))

    lab["hosts"] = vlm_helper.get_hostnames_from_consts(lab)
    barcodes = vlm_helper.get_barcodes_from_hostnames(lab["hosts"])
    active_con = lab["controller-0"]

    LOG.tc_setup_start("{} install".format(install_type))

    LOG.fixture_step("Reserve hosts")
    hosts = lab["hosts"]
    LOG.info("Un-reserving {}".format(hosts))
    vlm_helper.force_unreserve_hosts(hosts)
    LOG.info("Reserving {}".format(hosts))
    for barcode in barcodes:
        vlm_helper._reserve_vlm_console(barcode, "AUTO: lab installation")

    LOG.fixture_step("Attempt to reset port on controller-0")
    fresh_install_helper.reset_controller_telnet_port(active_con)

    def install_cleanup():
        fresh_install_helper.install_teardown(lab, active_con)

    request.addfinalizer(install_cleanup)

    is_subcloud = InstallVars.get_install_var("INSTALL_SUBCLOUD") is not None
    _install_setup = fresh_install_helper.setup_fresh_install(lab, subcloud=is_subcloud)
    if InstallVars.get_install_var("RESUME"):
        try:
            if active_con.ssh_conn is None:
                active_con.ssh_conn = install_helper.ssh_to_controller(active_con.host_ip)
        except:
            pass

    return _install_setup


def test_restore_simplex_install(install_setup):
    """
     Complete fresh_install steps for a simplex lab
     Test Setups:
         - Retrieve dictionary containing lab information
         - Retrieve required paths to directories, images, and licenses
         - Initialize build server and boot server objects
         - Retrieve what steps to be skipped
     Test Steps:
         - Boot controller-0
         - Run restore controller-0
         - Unlock controller-0
     """
    lab = install_setup["lab"]
    controller0_node = lab["controller-0"]
    patch_dir = install_setup["directories"]["patches"]
    patch_server = install_setup["servers"]["patches"]

    do_boot_c0 = RestoreVars.get_restore_var('RESTORE_PRE_BOOT_CONTROLLER0')
    stop_before_ansible_restore =\
        RestoreVars.get_restore_var('STOP_BEFORE_ANSIBLE_RESTORE')

    if do_boot_c0:
        fresh_install_helper.install_controller(sys_type=SysType.AIO_SX, patch_dir=patch_dir,
                                                patch_server_conn=patch_server.ssh_conn,
                                                init_global_vars=True)
    else:
        LOG.tc_step("Skipping controller-0 install")

    if stop_before_ansible_restore:
        skip("Stopping test before restoring")

    if InstallVars.get_install_var('IPV6_OAM'):
        restore_helper.setup_ipv6_oam(controller0_node)

    restore_helper.restore_platform()

    fresh_install_helper.unlock_active_controller(controller0_node)
    controller0_node.telnet_conn.hostname = r"controller\-[01]"
    controller0_node.telnet_conn.set_prompt(Prompt.CONTROLLER_PROMPT)

    if controller0_node.ssh_conn is None:
        controller0_node.ssh_conn = install_helper.ssh_to_controller(controller0_node.host_ip)
    install_helper.update_auth_url(ssh_con=controller0_node.ssh_conn)

    if lab.get("floating ip"):
        setup_tis_ssh(lab)

    fresh_install_helper.wait_for_hosts_ready(controller0_node.name, lab=lab)

    fresh_install_helper.reset_global_vars()
