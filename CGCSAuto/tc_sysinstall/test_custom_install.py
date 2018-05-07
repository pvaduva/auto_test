import pytest
import os
import threading
import time

from keywords import host_helper, system_helper, install_helper, vlm_helper
from utils.ssh import SSHClient, ControllerClient
from setups import setup_tis_ssh, setup_heat
from consts.cgcs import HostAvailState, HostAdminState, HostOperState, Prompt
from utils.tis_log import LOG
from consts.proj_vars import InstallVars, ProjVar
from consts.filepaths import TuxlabServerPath
from consts.build_server import Server, get_build_server_info, get_tuxlab_server_info
from consts.auth import SvcCgcsAuto
from consts.filepaths import BuildServerPath
from consts.auth import Tenant


@pytest.fixture(scope='module')
def install_setup():
    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.ADMIN)
    lab = InstallVars.get_install_var("LAB")
    lab_type = lab["system_mode"]
    lab["hosts"] = vlm_helper.get_hostnames_from_consts(lab)

    con_ssh = setup_tis_ssh(lab)
    active_con_name = "controller-0"
    active_con = lab[active_con_name]
    active_con.ssh_conn = con_ssh

    # Change default paths according to system version if skipping feed
    system_version = install_helper.get_current_system_version()

    if InstallVars.get_install_var("LICENSE") == BuildServerPath.DEFAULT_LICENSE_PATH:
        license_paths = BuildServerPath.TIS_LICENSE_PATHS[system_version]
        if "simplex" in lab_type:
            license_path = license_paths[2] if len(license_paths) > 2 else license_paths[1]
        elif "duplex" in lab_type:
            license_path = license_paths[1]
        else:
            license_path = license_paths[0]
        InstallVars.set_install_var(license=license_path)

    if InstallVars.get_install_var("SKIP_FEED"):

        if InstallVars.get_install_var("TIS_BUILD_DIR") == BuildServerPath.DEFAULT_HOST_BUILD_PATH:
            host_build_path = BuildServerPath.LATEST_HOST_BUILD_PATHS[system_version]
            InstallVars.set_install_var(tis_build_dir=host_build_path)

        if InstallVars.get_install_var("GUEST_IMAGE") == BuildServerPath.DEFAULT_GUEST_IMAGE_PATH:
            guest_image_path = BuildServerPath.GUEST_IMAGE_PATHS[system_version]
            InstallVars.set_install_var(guest_image=guest_image_path)

    # Reserve nodes
    vlm_helper.unreserve_hosts(lab["hosts"])
    vlm_helper.reserve_hosts(lab["hosts"])

    # Initialise servers
    # TODO: support different users and passwords
    # TODO: get_build_server_info might return None
    bld_server = get_build_server_info(InstallVars.get_install_var('BUILD_SERVER'))
    bld_server['prompt'] = Prompt.BUILD_SERVER_PROMPT_BASE.format('svc-cgcsauto', bld_server['name'])
    bld_server_conn = SSHClient(bld_server['name'], user=SvcCgcsAuto.USER,
                                password=SvcCgcsAuto.PASSWORD, initial_prompt=bld_server['prompt'])
    bld_server_conn.connect()
    bld_server_conn.set_prompt(bld_server['prompt'])
    bld_server_conn.deploy_ssh_key(install_helper.get_ssh_public_key())
    bld_server['ssh_conn'] = bld_server_conn
    bld_server_obj = Server(**bld_server)

    file_server = InstallVars.get_install_var("FILES_SERVER")
    if file_server == bld_server["name"]:
        file_server_obj = bld_server_obj
    else:
        file_server = get_build_server_info(file_server)
        file_server["prompt"] = Prompt.BUILD_SERVER_PROMPT_BASE.format('svc-cgcsauto', file_server['name'])
        file_server_conn = SSHClient(file_server['name'], user=SvcCgcsAuto.USER,
                                password=SvcCgcsAuto.PASSWORD, initial_prompt=file_server['prompt'])
        file_server_conn.connect()
        file_server_conn.set_prompt(bld_server['prompt'])
        file_server_conn.deploy_ssh_key(install_helper.get_ssh_public_key())
        file_server['ssh_conn'] = bld_server_conn
        file_server_obj = Server(**file_server)

    servers = {
               "build": bld_server_obj,
               "lab_files": file_server_obj
               }

    directories = {"build": InstallVars.get_install_var("TIS_BUILD_DIR"),
                   "boot": TuxlabServerPath.DEFAULT_BARCODES_DIR,
                   "lab_files": InstallVars.get_install_var("LAB_FILES_DIR")}

    paths = {"guest_img": InstallVars.get_install_var("GUEST_IMAGE"),
             "license": InstallVars.get_install_var("LICENSE")}

    skips = {"lab_setup": InstallVars.get_install_var("SKIP_LABSETUP"),
             "feed": InstallVars.get_install_var("SKIP_FEED"),
             "pxebootcfg": InstallVars.get_install_var("SKIP_PXEBOOTCFG"),
             "boot_type": InstallVars.get_install_var("BOOT_TYPE")}


    _install_setup = {"lab": lab,
                      "servers": servers,
                      "directories": directories,
                      "paths": paths,
                      "skips": skips,
                      "active_controller": active_con}

    return _install_setup


def test_setup_network_feed(install_setup):
    bld_srv = install_setup["servers"]["build"]
    load_path = install_setup["directories"]["build"]
    skip = install_setup["skips"]["feed"] or 'pxe' not in install_setup["skips"]["boot_type"]

    if skip:
        pytest.skip("Skip setup network boot feed was specified")

    assert install_helper.set_network_boot_feed(bld_srv.ssh_conn, load_path), "Failed to setup network boot feed"


def test_burn_usb(install_setup):
    iso_path = InstallVars.get_install_var('ISO_PATH')
    bld_srv = install_setup["servers"]["build"].ssh_conn
    lab = install_setup["lab"]
    skip = 'burn' not in install_setup["skips"]["boot_type"]

    if skip:
        pytest.skip('lab will boot using {}'.format(install_setup["skips"]["boot_type"]))

    assert install_helper.scp_cloned_image_to_another(lab, boot_lab=False, clone_image_iso_full_path=iso_path,
                                                      con_ssh=bld_srv.ssh_conn)


def test_iso_install(install_setup):
    skip = 'iso' not in install_setup["skips"]["boot_type"]

    if skip:
        pytest.skip('lab will boot using {}'.format(install_setup["skips"]["boot_type"]))

    pytest.fail("iso install not implemented")


def test_config_controller(install_setup):
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
    wipedisk = InstallVars.get_install_var("WIPEDISK")
    active_controller = install_setup["active_controller"]
    controller_name = active_controller.name
    boot_type = install_setup["skips"]["boot_type"]
    is_cpe = (lab.get('system_type', 'Standard') == 'CPE')
    usb = ('usb' in boot_type) or ('burn' in boot_type)

    LOG.tc_step("Install controller-0")
    if wipedisk:
        LOG.info("wiping disks")
        install_helper.wipe_disk_hosts(hosts)
    LOG.info("powering off hosts ...")
    vlm_helper.power_off_hosts(hosts)
    LOG.info("powered off hosts. booting {} ...".format(controller_name))
    install_helper.boot_controller(lab, small_footprint=is_cpe, boot_usb=usb)

    lab_files_server = install_setup["servers"]["lab_files"]
    build_server = install_setup["servers"]["build"]
    lab_files_dir = install_setup["directories"]["lab_files"]
    build_dir = install_setup["directories"]["build"] + "/"
    guest_path = install_setup["paths"]["guest_img"]
    license_path = install_setup["paths"]["license"]

    LOG.tc_step("Download lab files")
    # TODO: possible peformance boost: multithreading
    LOG.info("Downloading lab config files")
    install_helper.download_lab_config_files(lab, lab_files_server, build_dir, custom_path=lab_files_dir)
    LOG.info("Downloading heat templates")
    install_helper.download_heat_templates(lab, build_server, build_dir)
    LOG.info("Downloading guest image")
    install_helper.download_image(lab, build_server, guest_path)
    LOG.info("Copying license")
    install_helper.download_license(lab, build_server, license_path, dest_name="license")

    LOG.tc_step("Configure controller")
    # TODO: add wait for host states and reconnect in controller_system_config
    # TODO: controller_system_config doesn't exit if it failed
    rc, output = install_helper.controller_system_config(active_controller, telnet_conn=active_controller.telnet_conn)
    host_helper.wait_for_hosts_states(controller_name, availability=HostAvailState.ONLINE,
                                      use_telnet=True, con_telnet=active_controller.telnet_conn)
    active_controller.ssh_conn.connect(prompt=Prompt.CONTROLLER_PROMPT, retry=True, retry_timeout=30)
    LOG.info("running lab setup")
    install_helper.run_lab_setup(con_ssh=active_controller.ssh_conn)
    LOG.info("unlocking {}".format(controller_name))
    install_helper.unlock_controller(controller_name, con_ssh=active_controller.ssh_conn)


def test_simplex_install(install_setup):
    """
         Complete install steps for a simplex lab

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
    lab_type = install_setup["lab"]["system_mode"]
    hosts = install_setup["lab"]["hosts"]
    skip_lab_setup = install_setup["skips"]["lab_setup"]
    active_con = install_setup["active_controller"]

    if "simplex" not in lab_type:
        pytest.skip("lab is not a simplex lab")

    if not skip_lab_setup:
        LOG.tc_step("Run lab setup for simplex lab")
        install_helper.run_lab_setup()
        LOG.tc_step("Run lab setup for simplex lab")
        install_helper.run_lab_setup()
    else:
        LOG.info("--skip_lab_setup specified. Skipping lab setup")
    host_helper.wait_for_hosts_ready(active_con.name)
    LOG.tc_step("Check heat resources")
    setup_heat()
    host_helper.wait_for_hosts_ready(hosts)


def test_duplex_install(install_setup):
    """
         Complete install steps for a duplex lab

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
    output_dir = ProjVar.get_var("LOG_DIR")

    if "duplex" not in lab_type:
        pytest.skip("lab is not a duplex lab")

    LOG.tc_step("Bulk add hosts for CPE lab")
    rc, added_hosts, msg = install_helper.bulk_add_hosts(lab, "hosts_bulk_add.xml")
    assert rc == 0, msg
    # assert added_hosts[0] + added_hosts[1] + added_hosts[2] == hosts, "hosts_bulk_add failed to add all hosts"

    LOG.tc_step("Run lab setup for CPE lab")
    install_helper.run_lab_setup()

    LOG.tc_step("Run lab setup for CPE lab")
    install_helper.run_lab_setup()

    LOG.tc_step("Boot standby controller for CPE lab")
    standby_con = lab["controller-1"]
    install_helper.bring_node_console_up(standby_con, boot_device, output_dir,
                                                 small_footprint=True,
                                                 vlm_power_on=True,
                                                 close_telnet_conn=True)

    LOG.tc_step("Run lab setup for CPE lab")
    install_helper.run_lab_setup()

    LOG.tc_step("Run lab setup for CPE lab")
    install_helper.run_lab_setup()

    LOG.tc_step("Unlock standby controller for CPE lab")
    host_helper.unlock_host(standby_con.name, available_only=True)

    LOG.tc_step("Run lab setup for CPE lab")
    install_helper.run_lab_setup()

    LOG.tc_step("Check heat resources")
    setup_heat()
    host_helper.wait_for_hosts_ready(hosts)


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
    output_dir = ProjVar.get_var("LOG_DIR")
    active_con = install_setup["active_controller"]
    threads = []

    if "standard" not in lab_type:
        pytest.skip("lab is not a standard lab")

    LOG.tc_step("Bulk add hosts")
    rc, added_hosts, msg = install_helper.bulk_add_hosts(lab, "hosts_bulk_add.xml")
    assert rc == 0, msg
    # assert added_hosts[0] + added_hosts[1] + added_hosts[2] == hosts, "hosts_bulk_add failed to add all hosts

    LOG.tc_step("Boot other lab hosts")
    for hostname in hosts:
        if active_con.name not in hostname:
            host_thread = threading.Thread(target=install_helper.bring_node_console_up, name=hostname,
                                           args=(lab[hostname], boot_device, output_dir),
                                           kwargs={'vlm_power_on': True, "close_telnet_conn": True})
            threads.append(host_thread)
            LOG.info("Starting thread for {}".format(host_thread.name))
            host_thread.start()
    for thread in threads:
        thread.join()

    # TODO: Figure out how skiplabsetup is supposed to work here
    LOG.tc_step("Run lab setup")
    install_helper.run_lab_setup()
    # TODO: why twice?
    LOG.tc_step("Run lab setup")
    install_helper.run_lab_setup()
    LOG.tc_step("Unlock other hosts")
    host_helper.unlock_hosts([host for host in hosts if active_con.name not in host])
    host_helper.wait_for_hosts_ready(hosts)
    LOG.tc_step("Run lab setup")
    install_helper.run_lab_setup()

    LOG.tc_step("Check heat resources")
    setup_heat()
    # TODO: We could just delete the alarms
    system_helper.wait_for_alarms_gone([("400.001", None), ("800.001", None)], timeout=1800, check_interval=60)
    alarm = system_helper.get_alarms(alarm_id='250.001')
    if alarm:
        LOG.tc_step("Swact lock/unlock host")
        rc, msg = host_helper.lock_unlock_controllers()
        assert rc == 0, msg


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
    active_con = install_setup["active_controller"]
    boot_device = lab['boot_device_dict']
    output_dir = ProjVar.get_var("LOG_DIR")
    threads = []

    if lab_type is not "storage":
        pytest.skip("lab is not a storage lab")

    LOG.tc_step("Bulk add hosts")
    rc, added_hosts, msg = install_helper.bulk_add_hosts(lab, "hosts_bulk_add.xml")
    assert rc == 0, msg
    # assert added_hosts[0] + added_hosts[1] + added_hosts[2] == hosts, "hosts_bulk_add failed to add all hosts

    LOG.tc_step("Run lab setup")
    install_helper.run_lab_setup()

    LOG.tc_step("Boot other lab hosts")
    for hostname in hosts:
        if active_con.name not in hostname:
            host_thread = threading.Thread(target=install_helper.bring_node_console_up, name=hostname,
                                           args=(lab[hostname], boot_device, output_dir),
                                           kwargs={'vlm_power_on': True, "close_telnet_conn": True})
            threads.append(host_thread)
            LOG.info("Starting thread for {}".format(host_thread.name))
            host_thread.start()
    for thread in threads:
        thread.join()

    LOG.tc_step("Run lab setup")
    install_helper.run_lab_setup()
    install_helper.run_lab_setup()

    LOG.tc_step("Unlock controller-1")
    host_helper.unlock_host("controller-1", available_only=True)

    LOG.tc_step("Run lab setup")
    install_helper.run_lab_setup()

    LOG.tc_step("Unlock storage nodes")
    host_helper.unlock_hosts([storage_host for storage_host in hosts if "storage" in storage_host])
    host_helper.wait_for_hosts_ready([storage_host for storage_host in hosts if "storage" in storage_host])

    LOG.tc_step("Run lab setup")
    install_helper.run_lab_setup()

    LOG.tc_step("Unlock compute nodes")
    host_helper.unlock_hosts([compute_host for compute_host in hosts if "compute" in compute_host])
    host_helper.wait_for_hosts_ready([compute_host for compute_host in hosts if "compute" in compute_host])

    LOG.tc_step("Run lab setup")
    install_helper.run_lab_setup()

    setup_heat()
    system_helper.wait_for_alarms_gone([("400.001", None), ("800.001", None)], timeout=1800, check_interval=60)
    alarm = system_helper.get_alarms(alarm_id='250.001')
    if alarm:
        LOG.tc_step("Swact lock/unlock host")
        rc, msg = host_helper.lock_unlock_controllers()
        assert rc == 0, msg


def test_post_install():
    connection = ControllerClient.get_active_controller()

    rc = connection.exec_cmd("test -d /home/wrsroot/postinstall/")[0]
    if rc != 0:
        pytest.skip("No post install directory")
    else:
        rc, msg = install_helper.post_install()
        assert rc == 0, msg