import pytest
import os
import re

from keywords import install_helper, vlm_helper
from utils.tis_log import LOG
from consts.proj_vars import InstallVars, ProjVar
from consts.filepaths import TuxlabServerPath, InstallPaths
from consts.auth import Tenant
from setups import initialize_server
from tc_sysinstall.fresh_install import fresh_install_helper
from utils import exceptions, local_host


@pytest.fixture(scope='session')
def install_setup():
    lab = InstallVars.get_install_var("LAB")
    lab["hosts"] = vlm_helper.get_hostnames_from_consts(lab)
    skip_list = InstallVars.get_install_var("SKIP")
    active_con = lab["controller-0"]
    if active_con.telnet_conn is None:
        active_con.telnet_conn = install_helper.open_telnet_session(active_con)
    build_server = InstallVars.get_install_var('BUILD_SERVER')
    build_dir = InstallVars.get_install_var("TIS_BUILD_DIR")

    vlm_helper.reserve_hosts(lab["hosts"])

    # Initialise server objects
    file_server = InstallVars.get_install_var("FILES_SERVER")
    iso_host = InstallVars.get_install_var("ISO_HOST")

    bld_server = initialize_server(build_server)
    if file_server == bld_server.name:
        file_server_obj = bld_server
    else:
        file_server_obj = initialize_server(file_server)
    if iso_host == bld_server.name:
        iso_host_obj = bld_server
    else:
        iso_host_obj = initialize_server(iso_host)

    fresh_install_helper.set_preinstall_projvars(build_dir=build_dir, build_server=bld_server)

    servers = {
               "build": bld_server,
               "lab_files": file_server_obj
               }

    directories = {"build": build_dir,
                   "boot": TuxlabServerPath.DEFAULT_BARCODES_DIR,
                   "lab_files": InstallVars.get_install_var("LAB_FILES_DIR")}

    paths = {"guest_img": InstallVars.get_install_var("GUEST_IMAGE"),
             "license": InstallVars.get_install_var("LICENSE")}

    boot = {"boot_type": InstallVars.get_install_var("BOOT_TYPE"),
            "security": InstallVars.get_install_var("SECURITY"),
            "low_latency": InstallVars.get_install_var("LOW_LATENCY")}

    control = {"resume": InstallVars.get_install_var("RESUME"),
               "stop": InstallVars.get_install_var("STOP")}

    _install_setup = {"lab": lab,
                      "servers": servers,
                      "directories": directories,
                      "paths": paths,
                      "boot": boot,
                      "control": control,
                      "skips": skip_list,
                      "active_controller": active_con}

    LOG.info("Setting up {} boot".format(boot["boot_type"]))
    if not InstallVars.get_install_var("RESUME") and "0" not in skip_list:

        if "burn" in boot["boot_type"]:
            install_helper.burn_image_to_usb(iso_host_obj)

        elif "iso" in boot["boot_type"]:
            install_helper.rsync_image_to_boot_server(iso_host_obj)
            install_helper.mount_boot_server_iso(lab)

        elif "feed" not in skip_list:
            load_path = directories["build"]
            skip_cfg = "pxe" in skip_list
            install_helper.set_network_boot_feed(bld_server.ssh_conn, load_path, skip_cfg=skip_cfg)

        if InstallVars.get_install_var("WIPEDISK"):
            LOG.info("attempting to wipe disks")
            try:
                active_con.telnet_conn.login()
                install_helper.wipe_disk_hosts(lab["hosts"])
            except exceptions.TelnetException as e:
                LOG.error("Failed to wipedisks because of telnet exception: {}".format(e.message))

    return _install_setup


@pytest.mark.tryfirst
def pytest_runtest_teardown(item):
# Try first so that the failed tc_step can be written
    final_step = LOG.test_step
    lab = InstallVars.get_install_var("LAB")
    progress_dir = ProjVar.get_var("LOG_DIR") + "/.."
    progress_file_path = progress_dir + "/{}_install_progress.txt".format(lab["short_name"])
    LOG.info("unreserving hosts and writing install step to {}".format(progress_dir))

    vlm_helper.unreserve_hosts(vlm_helper.get_hostnames_from_consts(lab))
    file_exists = os.path.isfile(progress_file_path)
    if file_exists:
        # delete the file in case the user does not have write permissions
        os.remove(progress_file_path)
    with open(progress_file_path, "w") as progress_file:
        progress_file.write(item.nodeid + "\n")
        progress_file.write("End step: {}".format(str(LOG.test_step)))
        progress_file.close()
    LOG.info("Fresh Install Completed")
