import pytest


from consts.cgcs import SysType, Prompt
from consts.proj_vars import InstallVars, ProjVar
from keywords import host_helper, install_helper,  dc_helper, vlm_helper, network_helper
from tc_sysinstall.fresh_install import fresh_install_helper
from setups import setup_tis_ssh, collect_sys_net_info
from utils.tis_log import LOG, exceptions


@pytest.fixture(scope='session')
def install_setup(request):
    lab = InstallVars.get_install_var("LAB")
    subclouds = []
    dist_cloud = InstallVars.get_install_var("DISTRIBUTED_CLOUD")
    if not dist_cloud:
        pytest.skip("The specified lab {} is not a distributed cloud system".format(lab['short_name']))

    subclouds.extend([k for k in lab if 'subcloud' in k])
    central_lab = lab['central_region']

    install_subcloud = ProjVar.get_var('PRIMARY_SUBCLOUD')
    if not  install_subcloud:
        raise ValueError("Subcloud name must be specified with --subcloud <subcloud> option")

    LOG.info("Subcloud Install: {}".format(install_subcloud))
    if install_subcloud not in subclouds:
        pytest.skip("The subcloud {} is not member of the distribued cloud:{}"
                    .format(install_subcloud, lab['short_name']))
    if not fresh_install_helper.is_dcloud_system_controller_healthy(central_lab):
        pytest.skip("The distribued cloud system controller {}  is not healthy; Cannot install subcloud {}"
                    .format(central_lab['short_name'], install_subcloud))

    lab[install_subcloud]["hosts"] = vlm_helper.get_hostnames_from_consts(lab[install_subcloud])
    barcodes = vlm_helper.get_barcodes_from_hostnames(lab[install_subcloud]["hosts"], lab=lab[install_subcloud])

    active_con = lab[install_subcloud]["controller-0"]
    install_type = ProjVar.get_var('SYS_TYPE')

    LOG.tc_setup_start("{} install".format(install_type))
    LOG.fixture_step("Reserve hosts")

    hosts = {install_subcloud: lab[install_subcloud]["hosts"]}

    LOG.info("Unreservering {}".format(hosts))

    vlm_helper.force_unreserve_hosts(barcodes, val="barcodes")

    LOG.info("Reservering {}".format(hosts))
    for barcode in barcodes:
        vlm_helper._reserve_vlm_console(barcode, "AUTO: lab installation")

    LOG.fixture_step("Attempt to reset port on controller-0")
    fresh_install_helper.reset_controller_telnet_port(active_con)

    def install_cleanup():
       fresh_install_helper.install_teardown(lab, active_con, lab[install_subcloud])
    request.addfinalizer(install_cleanup)

    _install_setup = fresh_install_helper.setup_fresh_install(lab,dist_cloud)
    _install_setup['install_subcloud'] = install_subcloud
    return _install_setup


def test_sub_cloud_install(install_setup):
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
    dc_lab = install_setup["lab"]

    install_subcloud = install_setup['install_subcloud']
    subcloud_lab = dc_lab[install_subcloud]

    hosts = subcloud_lab["hosts"]
    boot_device = subcloud_lab['boot_device_dict']
    controller0_node = subcloud_lab["controller-0"]
    final_step = install_setup["control"]["stop"]
    patch_dir = install_setup["directories"]["patches"]
    patch_server = install_setup["servers"]["patches"]
    guest_server = install_setup["servers"]["guest"]

    if final_step == '0' or final_step == "setup":
        pytest.skip("stopping at install step: {}".format(LOG.test_step))

    fresh_install_helper.install_controller(lab=subcloud_lab, sys_type=SysType.DISTRIBUTED_CLOUD,
                                            patch_dir=patch_dir, patch_server_conn=patch_server.ssh_conn)
    controller0_node.telnet_conn.login()
    controller0_node.telnet_conn.flush()
    fresh_install_helper.set_software_version_var(use_telnet=True, con_telnet=controller0_node.telnet_conn)

    lab_files_server = install_setup["servers"]["lab_files"]
    build_server = install_setup["servers"]["build"]
    load_path = InstallVars.get_install_var("TIS_BUILD_DIR")

    fresh_install_helper.download_lab_files(lab=subcloud_lab, lab_files_server=lab_files_server,
                                            build_server=build_server,
                                            guest_server=guest_server,
                                            load_path=load_path,
                                            license_path=InstallVars.get_install_var("LICENSE"),
                                            guest_path=InstallVars.get_install_var('GUEST_IMAGE'))

    config_file_ext = ''.join(subcloud_lab['short_name'].split('_')[0:2])
    config_file = 'TiS_config.ini_centos_{}_SysCont'.format(config_file_ext)
    lab_setup_config_file = 'lab_setup_system_controller'
    fresh_install_helper.configure_controller(controller0_node, config_file=config_file,
                                              lab_setup_conf_file=lab_setup_config_file,  lab=subcloud_lab)
    controller0_node.telnet_conn.hostname = "controller\-[01]"
    controller0_node.telnet_conn.set_prompt(Prompt.CONTROLLER_PROMPT)
    if controller0_node.ssh_conn is None:
        controller0_node.ssh_conn = install_helper.establish_ssh_connection(controller0_node.host_ip)

    file_path = load_path + "/lab/yow/{}".format(subcloud_lab['name'].replace('yow-', ''))
    LOG.info("Downloading central region's hosts bulk add xml file from path: {}".format(file_path))

    install_helper.download_hosts_bulk_add_xml_file(subcloud_lab, build_server, file_path)

    LOG.info("Adding  standby controller host xml data ...")
    fresh_install_helper.bulk_add_hosts(lab=dc_lab, con_ssh=controller0_node.ssh_conn)

    LOG.info("Booting standby controller host...")

    # TODO: get controller-1 hostname
    fresh_install_helper.boot_hosts(boot_device, hostnames=['controller-1'], lab=subcloud_lab)
    host_helper.wait_for_hosts_ready([host for host in hosts if controller0_node.name not in host],
                                     con_ssh=controller0_node.ssh_conn)

    LOG.info("Installing license  subcloud info ...")
    # TODO

    LOG.info("Running lab setup script ...")
    fresh_install_helper.run_lab_setup(con_ssh=controller0_node.ssh_conn, conf_file=lab_setup_config_file)
    fresh_install_helper.run_lab_setup(con_ssh=controller0_node.ssh_conn, conf_file=lab_setup_config_file)

    LOG.info("Unlocking controller-1 ...")
    fresh_install_helper.unlock_hosts([host for host in hosts if controller0_node.name not in host],
                                      lab=subcloud_lab, con_ssh=controller0_node.ssh_conn)

    LOG.info("Running lab setup script ...")
    fresh_install_helper.run_lab_setup(con_ssh=controller0_node.ssh_conn, conf_file=lab_setup_config_file)

    if dc_lab.get("floating ip"):
        collect_sys_net_info(dc_lab)
        setup_tis_ssh(dc_lab)

    host_helper.wait_for_hosts_ready(controller0_node.name, con_ssh=controller0_node.ssh_conn)

    subclouds = dc_helper.get_subclouds()

    LOG.info("DC subcloudes added are:{}".format(subclouds))

    fresh_install_helper.attempt_to_run_post_install_scripts(controller0_node=controller0_node)

    fresh_install_helper.reset_global_vars()
