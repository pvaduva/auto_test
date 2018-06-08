import pytest
import os
import re

from keywords import install_helper, vlm_helper
from utils.clients.ssh import SSHClient, ControllerClient
from utils.tis_log import LOG
from consts.cgcs import Prompt
from consts.proj_vars import InstallVars, ProjVar
from consts.filepaths import TuxlabServerPath, InstallPaths
from consts.build_server import Server, get_build_server_info
from consts.auth import SvcCgcsAuto
from consts.filepaths import BuildServerPath
from consts.auth import Tenant


@pytest.fixture(scope='session')
def install_setup():
    lab = InstallVars.get_install_var("LAB")
    lab_type = lab["system_mode"]
    lab["hosts"] = vlm_helper.get_hostnames_from_consts(lab)
    skip_feed = InstallVars.get_install_var("SKIP_FEED")
    active_con = lab["controller-0"]
    build_server = InstallVars.get_install_var('BUILD_SERVER')
    build_dir = InstallVars.get_install_var("TIS_BUILD_DIR")

    vlm_helper.reserve_hosts(lab["hosts"])
    # Initialise servers
    bld_server = get_build_server_info(build_server)
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
        file_server_prompt = Prompt.BUILD_SERVER_PROMPT_BASE.format('svc-cgcsauto', file_server)
        file_server_conn = SSHClient(file_server, user=SvcCgcsAuto.USER,
                                password=SvcCgcsAuto.PASSWORD, initial_prompt=file_server_prompt)
        file_server_conn.connect()
        file_server_conn.deploy_ssh_key(install_helper.get_ssh_public_key())
        file_server_dict = {"name": file_server, "prompt": file_server_prompt, "ssh_conn": file_server_conn}
        file_server_obj = Server(**file_server_dict)

    iso_host = InstallVars.get_install_var("ISO_HOST")
    if iso_host == bld_server["name"]:
        iso_host_obj = bld_server_obj
    else:
        iso_host_prompt = Prompt.BUILD_SERVER_PROMPT_BASE.format('svc-cgcsauto', iso_host)
        iso_host_conn = SSHClient(iso_host, user=SvcCgcsAuto.USER,
                                     password=SvcCgcsAuto.PASSWORD, initial_prompt=iso_host_prompt)
        iso_host_conn.connect()
        iso_host_conn.deploy_ssh_key(install_helper.get_ssh_public_key())
        iso_host_dict = {"name": iso_host, "prompt": iso_host_prompt, "ssh_conn": iso_host_conn}
        iso_host_obj = Server(**iso_host_dict)

    # set project variables for reporting
    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.ADMIN)
    ProjVar.set_var(BUILD_SERVER=build_server + '.wrs.com')
    job_regex = "(CGCS_\d+.\d+_Host)|(TC_\d+.\d+_Host)"
    job = re.search(job_regex, build_dir)
    ProjVar.set_var(JOB=job.group(0)) if job is not None else ProjVar.set_var(JOB='')
    build_id = bld_server_conn.exec_cmd("readlink {}".format(build_dir + "/"))[1]
    ProjVar.set_var(BUILD_ID=build_id)

    servers = {
               "build": bld_server_obj,
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

    _install_setup = {"lab": lab,
                      "servers": servers,
                      "directories": directories,
                      "paths": paths,
                      "boot": boot,
                      "skip_labsetup": InstallVars.get_install_var("SKIP_LABSETUP"),
                      "active_controller": active_con}

    bld_srv = servers["build"]

    LOG.info("Setting up {} boot".format(boot["boot_type"]))

    if "burn" in boot["boot_type"]:
        install_helper.burn_image_to_usb(iso_host_obj)

    elif "iso" in boot["boot_type"]:
        install_helper.rsync_image_to_boot_server(iso_host_obj)
        install_helper.mount_boot_server_iso(lab)

    elif not skip_feed:
        load_path = directories["build"]
        skip_cfg = InstallVars.get_install_var("SKIP_PXEBOOTCFG")
        install_helper.set_network_boot_feed(bld_srv.ssh_conn, load_path, skip_cfg=skip_cfg)

    if InstallVars.get_install_var("WIPEDISK"):
        LOG.info("wiping disks")
        install_helper.wipe_disk_hosts(lab["hosts"])

    return _install_setup


@pytest.mark.tryfirst
def pytest_runtest_teardown(item):
# Try first so that the failed tc_step can be written
    lab = InstallVars.get_install_var("LAB")
    progress_dir = InstallPaths.INSTALL_TEMP_DIR
    progress_file_path = progress_dir + "/{}_install_progress.txt".format(lab["short_name"])
    LOG.info("unreserving hosts and writing install step to {}".format(progress_dir))

    vlm_helper.unreserve_hosts(vlm_helper.get_hostnames_from_consts(lab))
    with open(progress_file_path, "w") as progress_file:
        os.chmod(progress_file_path, 0o777)
        progress_file.write(item.nodeid + "\n")
        progress_file.write("End step: {}".format(str(LOG.test_step)))
        progress_file.close()
