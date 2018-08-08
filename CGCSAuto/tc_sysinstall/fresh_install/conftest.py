import pytest
import os

from keywords import install_helper, vlm_helper
from keywords.network_helper import reset_telnet_port
from utils.tis_log import LOG
from consts.proj_vars import InstallVars, ProjVar
from consts.filepaths import TuxlabServerPath
from setups import initialize_server
from tc_sysinstall.fresh_install import fresh_install_helper
from utils import exceptions, local_host


@pytest.fixture(scope='session')
def install_setup():
    lab = InstallVars.get_install_var("LAB")
    lab["hosts"] = vlm_helper.get_hostnames_from_consts(lab)
    barcodes = vlm_helper.get_barcodes_from_hostnames(lab["hosts"])
    skip_list = InstallVars.get_install_var("SKIP")
    active_con = lab["controller-0"]
    install_type = ProjVar.get_var('SYS_TYPE')

    LOG.tc_setup_start("{} install".format(install_type))
    LOG.fixture_step("Reserve hosts")
    LOG.info("Unreservering {}".format(lab["hosts"]))
    vlm_helper.force_unreserve_hosts(lab["hosts"])
    LOG.info("Reservering {}".format(lab["hosts"]))
    for barcode in barcodes:
        local_host.reserve_vlm_console(barcode, "AUTO: lab installation")
    LOG.fixture_step("Attempt to reset port on controller-0")
    if active_con.telnet_conn is None:
        active_con.telnet_conn = install_helper.open_telnet_session(active_con)
        try:
            reset_telnet_port(active_con.telnet_conn)
        except:
            pass
    build_server = InstallVars.get_install_var('BUILD_SERVER')
    build_dir = InstallVars.get_install_var("TIS_BUILD_DIR")

    # Initialise server objects
    file_server = InstallVars.get_install_var("FILES_SERVER")
    iso_host = InstallVars.get_install_var("ISO_HOST")
    patch_server = InstallVars.get_install_var("PATCH_SERVER")
    guest_server = InstallVars.get_install_var("GUEST_SERVER")
    servers = [file_server, iso_host, patch_server, guest_server]
    LOG.fixture_step("Establishing connection to {}".format(servers))

    bld_server = initialize_server(build_server)
    if file_server == bld_server.name:
        file_server_obj = bld_server
    else:
        file_server_obj = initialize_server(file_server)
    if iso_host == bld_server.name:
        iso_host_obj = bld_server
    else:
        iso_host_obj = initialize_server(iso_host)
    if patch_server == bld_server.name:
        patch_server = bld_server
    else:
        patch_server = initialize_server(patch_server)
    if guest_server == bld_server.name:
        guest_server_obj = bld_server
    else:
        guest_server_obj = initialize_server(guest_server)


    fresh_install_helper.set_preinstall_projvars(build_dir=build_dir, build_server=bld_server)

    servers = {
               "build": bld_server,
               "lab_files": file_server_obj,
               "patches": patch_server,
               "guest": guest_server_obj
               }

    directories = {"build": build_dir,
                   "boot": TuxlabServerPath.DEFAULT_BARCODES_DIR,
                   "lab_files": InstallVars.get_install_var("LAB_FILES_DIR"),
                   "patches": InstallVars.get_install_var("PATCH_DIR")}

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

    if not InstallVars.get_install_var("RESUME") and "0" not in skip_list and "setup" not in skip_list:
        LOG.fixture_step("Setting up {} boot".format(boot["boot_type"]))

        if "burn" in boot["boot_type"]:
            install_helper.burn_image_to_usb(iso_host_obj)

        elif "iso" in boot["boot_type"]:
            install_helper.rsync_image_to_boot_server(iso_host_obj)
            install_helper.mount_boot_server_iso(lab)

        elif "feed" not in skip_list and "pxe" in boot["boot_type"]:
            load_path = directories["build"]
            skip_cfg = "pxe" in skip_list
            install_helper.set_network_boot_feed(bld_server.ssh_conn, load_path, skip_cfg=skip_cfg)

        if InstallVars.get_install_var("WIPEDISK"):
            LOG.fixture_step("Attempting to wipe disks")
            try:
                active_con.telnet_conn.login()
                install_helper.wipe_disk_hosts(lab["hosts"])
            except exceptions.TelnetException as e:
                LOG.error("Failed to wipedisks because of telnet exception: {}".format(e.message))

    return _install_setup


@pytest.mark.tryfirst
def pytest_runtest_teardown(item):
# Try first so that the failed fixture_step can be written
    final_step = LOG.test_step
    lab = InstallVars.get_install_var("LAB")
    progress_dir = ProjVar.get_var("LOG_DIR") + "/.."
    progress_file_path = progress_dir + "/{}_install_progress.txt".format(lab["short_name"])
    lab = InstallVars.get_install_var("LAB")

    LOG.tc_teardown_start(item.nodeid)
    try:
        controller0_node = lab["controller-0"]
        if controller0_node.telnet_conn is None:
            controller0_node.telnet_conn = install_helper.open_telnet_session(controller0_node)
            controller0_node.telnet_conn.login()
        rc, output = controller0_node.telnet_conn.exec_cmd("cat /etc/build.info", fail_ok=True)
        LOG.info(output)
    except Exception:
        pass
    LOG.fixture_step("unreserving hosts")
    vlm_helper.unreserve_hosts(vlm_helper.get_hostnames_from_consts(lab))

    install_testcases = ["test_simplex_install.py", "test_duplex_install.py", "test_standard_install.py", "test_storage_install.py"]
    for install_testcase in install_testcases:
        if install_testcase in item.nodeid:
            LOG.fixture_step("Writing install step to {}".format(progress_file_path))
            with open(progress_file_path, "w+") as progress_file:
                progress_file.write(item.nodeid + "\n")
                progress_file.write("End step: {}".format(str(final_step)))
                progress_file.close()
            os.chmod(progress_file_path, 0o755)
            break
    LOG.info("Fresh Install Completed")
