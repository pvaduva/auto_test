import pytest

from keywords import install_helper, vlm_helper
from utils.clients.ssh import SSHClient, ControllerClient
from setups import setup_tis_ssh
from consts.cgcs import Prompt
from utils.tis_log import LOG
from consts.proj_vars import InstallVars, ProjVar
from consts.filepaths import TuxlabServerPath
from consts.build_server import Server, get_build_server_info
from consts.auth import SvcCgcsAuto
from consts.filepaths import BuildServerPath
from consts.auth import Tenant

@pytest.fixture(scope='session')
def install_setup():
    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.ADMIN)
    lab = InstallVars.get_install_var("LAB")
    lab_type = lab["system_mode"]
    lab["hosts"] = vlm_helper.get_hostnames_from_consts(lab)
    skip_feed = InstallVars.get_install_var("SKIP_FEED")
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

    if skip_feed:

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
        file_server_prompt = Prompt.BUILD_SERVER_PROMPT_BASE.format('svc-cgcsauto', file_server)
        file_server_conn = SSHClient(file_server, user=SvcCgcsAuto.USER,
                                password=SvcCgcsAuto.PASSWORD, initial_prompt=file_server_prompt)
        file_server_conn.connect()
        file_server_conn.deploy_ssh_key(install_helper.get_ssh_public_key())
        file_server_dict = {"name": file_server, "prompt": file_server_prompt, "ssh_conn": file_server_conn}
        file_server_obj = Server(file_server_dict)

    # TODO: support a server that isn't one of the build servers
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

    servers = {
               "build": bld_server_obj,
               "lab_files": file_server_obj
               }

    directories = {"build": InstallVars.get_install_var("TIS_BUILD_DIR"),
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


def pytest_runtest_teardown(item):
    lab = InstallVars.get_install_var("LAB")

    # LOG.debug("Teardown at test step: ", LOG.test_step)
    vlm_helper.unreserve_hosts(vlm_helper.get_hostnames_from_consts(lab))

