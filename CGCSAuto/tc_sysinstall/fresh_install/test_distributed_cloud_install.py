from pytest import skip

from consts.cgcs import SysType, Prompt
from consts.proj_vars import InstallVars
from keywords import host_helper, install_helper,  dc_helper
from tc_sysinstall.fresh_install import fresh_install_helper
from setups import setup_tis_ssh, collect_sys_net_info
from utils.tis_log import LOG


def test_distributed_cloud_install(install_setup):
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
    central_region_lab = dc_lab['central_region']

    hosts = dc_lab['central_region']["hosts"]
    boot_device = central_region_lab['boot_device_dict']
    controller0_node = central_region_lab["controller-0"]
    final_step = install_setup["control"]["stop"]
    patch_dir = install_setup["directories"]["patches"]
    patch_server = install_setup["servers"]["patches"]
    guest_server = install_setup["servers"]["guest"]

    if final_step == '0' or final_step == "setup":
        skip("stopping at install step: {}".format(LOG.test_step))

    fresh_install_helper.install_controller(lab=central_region_lab, sys_type=SysType.DISTRIBUTED_CLOUD,
                                            patch_dir=patch_dir, patch_server_conn=patch_server.ssh_conn)
    controller0_node.telnet_conn.login()
    controller0_node.telnet_conn.flush()
    fresh_install_helper.set_software_version_var(use_telnet=True, con_telnet=controller0_node.telnet_conn)

    lab_files_server = install_setup["servers"]["lab_files"]
    build_server = install_setup["servers"]["build"]
    load_path = InstallVars.get_install_var("TIS_BUILD_DIR")

    fresh_install_helper.download_lab_files(lab=central_region_lab, lab_files_server=lab_files_server,
                                            build_server=build_server,
                                            guest_server=guest_server,
                                            load_path=load_path,
                                            license_path=InstallVars.get_install_var("LICENSE"),
                                            guest_path=InstallVars.get_install_var('GUEST_IMAGE'))

    config_file_ext = ''.join(central_region_lab['short_name'].split('_')[0:2])
    config_file = 'TiS_config.ini_centos_{}_SysCont'.format(config_file_ext)
    lab_setup_config_file = 'lab_setup_system_controller'
    fresh_install_helper.configure_controller(controller0_node, config_file=config_file,
                                              lab_setup_conf_file=lab_setup_config_file,  lab=central_region_lab)
    controller0_node.telnet_conn.hostname = "controller\-[01]"
    controller0_node.telnet_conn.set_prompt(Prompt.CONTROLLER_PROMPT)
    if controller0_node.ssh_conn is None:
        controller0_node.ssh_conn = install_helper.establish_ssh_connection(controller0_node.host_ip)

    file_path = load_path + "/lab/yow/{}".format(central_region_lab['name'].replace('yow-', ''))
    LOG.info("Downloading central region's hosts bulk add xml file from path: {}".format(file_path))

    install_helper.download_hosts_bulk_add_xml_file(central_region_lab, build_server, file_path)

    LOG.info("Adding  standby controller host xml data ...")
    fresh_install_helper.bulk_add_hosts(lab=dc_lab, con_ssh=controller0_node.ssh_conn)

    LOG.info("Booting standby controller host...")

    # TODO: get controller-1 hostname
    fresh_install_helper.boot_hosts(boot_device, hostnames=['controller-1'], lab=central_region_lab)
    host_helper.wait_for_hosts_ready([host for host in hosts if controller0_node.name not in host],
                                     con_ssh=controller0_node.ssh_conn)

    LOG.info("Installing license  subcloud info ...")
    # TODO

    LOG.info("Running lab setup script ...")
    fresh_install_helper.run_lab_setup(con_ssh=controller0_node.ssh_conn, conf_file=lab_setup_config_file)
    fresh_install_helper.run_lab_setup(con_ssh=controller0_node.ssh_conn, conf_file=lab_setup_config_file)

    LOG.info("Unlocking controller-1 ...")
    fresh_install_helper.unlock_hosts([host for host in hosts if controller0_node.name not in host],
                                      lab=central_region_lab, con_ssh=controller0_node.ssh_conn)

    LOG.info("Running lab setup script ...")
    fresh_install_helper.run_lab_setup(con_ssh=controller0_node.ssh_conn, conf_file=lab_setup_config_file)

    if dc_lab.get("floating ip"):
        collect_sys_net_info(dc_lab)
        setup_tis_ssh(dc_lab)

    host_helper.wait_for_hosts_ready(controller0_node.name, con_ssh=controller0_node.ssh_conn)

    LOG.tc_step("Installing subcloud for {} .....".format(dc_lab['name']))

    LOG.info("Adding subcloud info ...")

    subclouds = dc_helper.get_subclouds()

    LOG.info("DC subcloudes added are:{}".format(subclouds))

    LOG.info("Installing subcloud controller-0  ...")
    fresh_install_helper.install_subclouds(subclouds, load_path, build_server, lab=dc_lab, patch_dir=patch_dir,
                                           patch_server_conn=patch_server.ssh_conn)

    fresh_install_helper.attempt_to_run_post_install_scripts()
    fresh_install_helper.reset_global_vars()
