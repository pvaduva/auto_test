import time
import re

from keywords import install_helper, network_helper, system_helper, vlm_helper, host_helper
from utils.tis_log import LOG
from utils.clients.ssh import SSHClient, ControllerClient
from consts.build_server import Server
from consts.auth import Tenant
from consts.cgcs import SysType, Prompt
from consts.filepaths import BuildServerPath, WRSROOT_HOME
from consts.proj_vars import ProjVar, InstallVars


def set_preinstall_projvars(build_dir, build_server):
    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.ADMIN)
    ProjVar.set_var(BUILD_SERVER=build_server.name + '.wrs.com')
    set_build_job(build_dir=build_dir)
    set_build_id(build_dir=build_dir, build_server_conn=build_server.ssh_conn)


def set_build_job(build_dir):
    job_regex = "(CGCS_\d+.\d+_Host)|(TC_\d+.\d+_Host)"
    match = re.search(job_regex, build_dir)
    if match:
        job = match.group(0)
        ProjVar.set_var(JOB=job)

        return job
    else:
        ProjVar.set_var(JOB='n/a')

        return 'n/a'


def set_build_id(build_dir, build_server_conn=None):
    id_regex = '\d+-\d+-\d+_\d+-\d+-\d+'

    if build_dir.endswith("/"):
        build_dir = build_dir[:-1]
    rc, output = build_server_conn.exec_cmd("readlink {}".format(build_dir))
    if rc == 0:
        output_parts = output.split("/")
        build_dir_parts = build_dir.split("/")
        for part in output_parts:
            if part not in build_dir_parts:
                if re.search(id_regex, part):
                    ProjVar.set_var(BUILD_ID=part)

                    return part
    else:
        match = re.search(id_regex, build_dir)
        if match:
            ProjVar.set_var(BUILD_ID=match.group(0))

            return match.group(0)
        else:
            ProjVar.set_var("n/a")

            return "n/a"


def do_step():
    skip_list = InstallVars.get_install_var("SKIP")
    current_step = LOG.test_step
    last_session_step = InstallVars.get_install_var("RESUME")
    do = last_session_step <= current_step and str(current_step) not in skip_list

    if not do:
        LOG.info("Skipping step")

    return do


def install_controller(security=None, low_latency=None, lab=None, sys_type=None, usb=None, patch_dir=None, patch_server_conn=None):
    if lab is None:
        lab = InstallVars.get_install_var("LAB")
    if usb is None:
        boot_type = InstallVars.get_install_var("BOOT_TYPE")
        usb = ('usb' in boot_type) or ('burn' in boot_type)
    if sys_type is None:
        sys_type = ProjVar.get_var('SYS_TYPE')
    if patch_dir is None:
        patch_dir = InstallVars.get_install_var("PATCH_DIR")
    is_cpe = sys_type == SysType.AIO_SX or sys_type == SysType.AIO_DX

    vlm_helper.power_off_hosts(lab["hosts"])
    install_helper.boot_controller(lab, small_footprint=is_cpe, boot_usb=usb, security=security, low_latency=low_latency,
                                   patch_dir_paths=patch_dir, bld_server_conn=patch_server_conn)


def download_lab_files(lab_files_server, build_server, sys_version=None, sys_type=None, lab_files_dir=None,
                       load_path=None, guest_path=None, license_path=None, lab=None):
    if lab_files_dir is None:
        lab_files_dir = InstallVars.get_install_var('LAB_FILES_DIR')
    if load_path is None or load_path == BuildServerPath.DEFAULT_HOST_BUILD_PATH:
        load_path = set_load_path(build_server_conn=build_server.ssh_conn, sys_version=sys_version)
    if guest_path is None or guest_path == BuildServerPath.DEFAULT_GUEST_IMAGE_PATH:
        guest_path = set_guest_image_var(sys_version=sys_version)
    if license_path is None or license_path == BuildServerPath.DEFAULT_LICENSE_PATH:
        license_path = set_license_var(sys_version=sys_version, sys_type=sys_type)
    if lab is None:
        lab = InstallVars.get_install_var('LAB')

    LOG.info("Downloading lab config files")
    install_helper.download_lab_config_files(lab, build_server, load_path, conf_server=lab_files_server)
    LOG.info("Downloading heat templates")
    install_helper.download_heat_templates(lab, build_server, load_path)
    LOG.info("Downloading guest image")
    install_helper.download_image(lab, build_server, guest_path)
    LOG.info("Copying license")
    install_helper.download_license(lab, build_server, license_path, dest_name="license")


def set_license_var(sys_version=None, sys_type=None):
    if sys_version is None:
        sys_version = ProjVar.get_var('SW_VERSION')[0]
    if sys_type is None:
        sys_type = ProjVar.get_var('SYS_TYPE')
    LOG.debug("SYSTEM_TYPE: {}".format(sys_type))

    if sys_type == SysType.AIO_SX:
        index = 2
    elif sys_type == SysType.AIO_DX:
        index = 1
    else:
        index = 0

    license_paths = BuildServerPath.TIS_LICENSE_PATHS[sys_version]
    LOG.debug(license_paths)
    LOG.debug(license_paths[index])
    license_path = license_paths[index]
    InstallVars.set_install_var(license=license_path)

    return license_path


def set_load_path(build_server_conn, sys_version=None):
    if sys_version is None:
        sys_version = ProjVar.get_var('SW_VERSION')[0]
    host_build_path = BuildServerPath.LATEST_HOST_BUILD_PATHS[sys_version]
    load_path = host_build_path + "/"

    InstallVars.set_install_var(tis_build_dir=host_build_path)
    set_build_id(host_build_path, build_server_conn)

    return load_path


def set_guest_image_var(sys_version=None):
    if sys_version is None:
        sys_version = ProjVar.get_var('SW_VERSION')[0]
    guest_path = BuildServerPath.GUEST_IMAGE_PATHS[sys_version]

    InstallVars.set_install_var(guest_image=guest_path)

    return guest_path


def set_software_version_var(con_ssh=None, use_telnet=False, con_telnet=None):
    system_version = system_helper.get_system_software_version(con_ssh=con_ssh, use_telnet=use_telnet,
                                                               con_telnet=con_telnet)
    ProjVar.set_var(append=True, sw_version=system_version)

    return system_version


def configure_controller(controller0_node):
    rc, output = install_helper.controller_system_config(con_telnet=controller0_node.telnet_conn)
    if controller0_node.ssh_conn is None:
        controller0_node.ssh_conn = install_helper.establish_ssh_connection(controller0_node.host_ip)
    LOG.info("running lab setup")
    install_helper.run_lab_setup(con_ssh=controller0_node.ssh_conn)
    LOG.info("unlocking {}".format(controller0_node.name))
    install_helper.unlock_controller(controller0_node.name, con_ssh=controller0_node.ssh_conn, available_only=False)


def clear_post_install_alarms(con_ssh=None):
    system_helper.wait_for_alarms_gone([("400.001", None), ("800.001", None)], timeout=1800, check_interval=60,
                                       con_ssh=con_ssh)
    alarm = system_helper.get_alarms(alarm_id='250.001', con_ssh=con_ssh)
    if alarm:
        LOG.tc_step("Swact lock/unlock host")
        rc, msg = host_helper.lock_unlock_controllers()
        assert rc == 0, msg


def get_resume_step(lab=None, install_progress_path=None):
    if lab is None:
        lab = InstallVars.get_install_var("LAB")
    if install_progress_path is None:
        install_progress_path = "{}/../{}_install_progress.txt".format(ProjVar.get_var("LOG_DIR"), lab["short_name"])

    with open(install_progress_path, "r") as progress_file:
        lines = progress_file.readlines()
        for line in lines:
            if "End step:" in line:
                return int(line[line.find("End Step: "):].strip()) + 1
