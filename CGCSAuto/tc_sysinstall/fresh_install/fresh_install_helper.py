import re
from pytest import skip

from keywords import install_helper, system_helper, vlm_helper, host_helper
from utils.tis_log import LOG
from consts.auth import Tenant
from consts.cgcs import SysType
from consts.filepaths import BuildServerPath
from consts.proj_vars import ProjVar, InstallVars

lab_setup_count = 0
completed_resume_step = False


def set_lab_setup_count(val=0):
    global lab_setup_count
    lab_setup_count = val

    return lab_setup_count


def set_completed_resume_step(val=False):
    global completed_resume_step
    completed_resume_step = val

    return completed_resume_step


def reset_global_vars():
    lab_setup_count = set_lab_setup_count(0)
    completed_resume_step = set_completed_resume_step(False)

    return lab_setup_count, completed_resume_step


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


def do_step(step_name=None):
    global completed_resume_step
    if step_name:
        step_name = step_name.lower().replace(' ', '_')
    skip_list = InstallVars.get_install_var("SKIP")
    current_step_num = str(LOG.test_step)
    last_session_step = InstallVars.get_install_var("RESUME")
    if 'lab_setup' in step_name:
        global lab_setup_count
        step_name = step_name + '-{}'.format(lab_setup_count)
        lab_setup_count += 1
    # if resume flag is given do_step if it's currently the specified resume step or a step after that point
    if last_session_step:
        resume = last_session_step == current_step_num or last_session_step == step_name and not completed_resume_step
    else:
        resume = True
    in_skip_list = False
    for skip_step in skip_list:
        if step_name in skip_step:
            if "lab_setup" in step_name and "lab_setup" in skip_step:
                in_skip_list = step_name[-1] == skip_step[-1]
            else:
                in_skip_list = True
    do = resume and current_step_num not in skip_list and not in_skip_list
    for step_to_skip in skip_list:
        step_to_skip = step_to_skip.lower()
        if step_to_skip in step_name:
            do = False
            break
    if not do:
        LOG.info("Skipping step")
    completed_resume_step = resume

    return do


def install_controller(security=None, low_latency=None, lab=None, sys_type=None, usb=None, patch_dir=None,
                       patch_server_conn=None, final_step=None):
    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
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

    test_step = "Install Controller"
    LOG.tc_step(test_step)
    if do_step(test_step):
        vlm_helper.power_off_hosts(lab["hosts"])
        install_helper.boot_controller(lab, small_footprint=is_cpe, boot_usb=usb, security=security,
                                       low_latency=low_latency, patch_dir_paths=patch_dir, bld_server_conn=patch_server_conn)
    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:

        reset_global_vars()
        skip("stopping at install step: {}".format(LOG.test_step))


def download_lab_files(lab_files_server, build_server, guest_server, sys_version=None, sys_type=None, lab_files_dir=None,
                       load_path=None, guest_path=None, license_path=None, lab=None, final_step=None):
    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    if lab_files_dir is None:
        lab_files_dir = InstallVars.get_install_var('LAB_FILES_DIR')
    if load_path is None or load_path == BuildServerPath.DEFAULT_HOST_BUILD_PATH:
        load_path = set_load_path(build_server_conn=build_server.ssh_conn, sys_version=sys_version)
    if not load_path.endswith("/"):
        load_path += "/"
    if guest_path is None or guest_path == BuildServerPath.DEFAULT_GUEST_IMAGE_PATH:
        guest_path = set_guest_image_var(sys_version=sys_version)
    if license_path is None or license_path == BuildServerPath.DEFAULT_LICENSE_PATH:
        license_path = set_license_var(sys_version=sys_version, sys_type=sys_type)
    if lab is None:
        lab = InstallVars.get_install_var('LAB')

    test_step = "Download lab files"
    LOG.tc_step(test_step)
    if do_step(test_step):
        LOG.info("Downloading heat templates")
        install_helper.download_heat_templates(lab, build_server, load_path)
        LOG.info("Downloading guest image")
        install_helper.download_image(lab, guest_server, guest_path)
        LOG.info("Copying license")
        install_helper.download_license(lab, build_server, license_path, dest_name="license")
        LOG.info("Downloading lab config files")
        install_helper.download_lab_config_files(lab, build_server, load_path, conf_server=lab_files_server)
    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        reset_global_vars()
        skip("stopping at install step: {}".format(LOG.test_step))


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


def configure_controller(controller0_node, final_step=None):
    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    test_step = "Configure controller"
    LOG.tc_step(test_step)
    if do_step(test_step):
        install_helper.controller_system_config(con_telnet=controller0_node.telnet_conn)
        if controller0_node.ssh_conn is None:
            controller0_node.ssh_conn = install_helper.establish_ssh_connection(controller0_node.host_ip)
        if do_step("lab_setup"):
            LOG.info("running lab setup")
            install_helper.run_lab_setup(con_ssh=controller0_node.ssh_conn)
        if do_step("unlock_active_controller"):
            LOG.info("unlocking {}".format(controller0_node.name))
            install_helper.unlock_controller(controller0_node.name, con_ssh=controller0_node.ssh_conn, available_only=False)
    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        reset_global_vars()
        skip("stopping at install step: {}".format(LOG.test_step))


def bulk_add_hosts(lab=None, con_ssh=None, final_step=None):
    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    if not lab:
        lab = InstallVars.get_install_var('LAB')
    if not con_ssh:
        con_ssh = lab["controller-0"].ssh_conn
    test_step = "Bulk add hosts"
    LOG.tc_step(test_step)
    if do_step(test_step):
        rc, added_hosts, msg = install_helper.bulk_add_hosts(lab, "hosts_bulk_add.xml", con_ssh=con_ssh)
        assert rc == 0, msg
        # assert added_hosts[0] + added_hosts[1] + added_hosts[2] == hosts, "hosts_bulk_add failed to add all hosts
    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))


def boot_hosts(boot_device_dict=None, host_objects=None, final_step=None):
    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    test_step = "Boot"
    if host_objects is None:
        lab = InstallVars.get_install_var('LAB')
        host_objects = [lab[hostname] for hostname in lab['hosts'] if 'controller-0' not in hostname]
    if boot_device_dict is None:
        lab = InstallVars.get_install_var('LAB')
        boot_device_dict = lab['boot_device_dict']
    hostnames = [host.name for host in host_objects]
    controllers = []
    computes = []
    storages = []
    for hostname in hostnames:
        if 'controller' in hostname:
            controllers.append(hostname)
        elif 'compute' in hostname:
            computes.append(hostname)
        elif 'storage' in hostname:
            storages.append(hostname)
    if controllers and not computes and not storages:
        if 'controller-0' in controllers and 'controller-1' not in controllers:
            test_step += ' active controller'
        elif 'controller-1' in controllers and 'controller-0' not in controllers:
            test_step += ' standby controller'
        else:
            test_step += ' controller nodes'
    elif computes and not controllers and not storages:
        if len(computes) > 1:
            test_step += ' compute nodes'
        else:
            test_step += " {}".format(computes[0])
    elif storages and not controllers and not computes:
        if len(storages) > 1:
            test_step += ' storage nodes'
        else:
            test_step += " {}".format(storages[0])
    else:
        test_step += " other lab hosts"

    LOG.tc_step(test_step)
    if do_step(test_step):
        install_helper.boot_hosts(boot_device_dict, nodes=host_objects)
    if LOG.test_step == InstallVars.get_install_var("STOP") or test_step == InstallVars.get_install_var("STOP"):
        skip("stopping at install step: {}".format(LOG.test_step))


def unlock_hosts(hostnames=None, con_ssh=None, final_step=None):
    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    test_step = "Unlock"
    if hostnames is None:
        lab = InstallVars.get_install_var('LAB')
        hostnames = lab['hosts'].remove("controller-0")
    if isinstance(hostnames, str):
        hostnames = [hostnames]
    if con_ssh is None:
        lab = InstallVars.get_install_var('LAB')
        con_ssh = lab['controller-0'].ssh_conn
    controllers = []
    computes = []
    storages = []
    available_only = False
    for hostname in hostnames:
        if 'controller' in hostname:
            controllers.append(hostname)
        elif 'compute' in hostname:
            computes.append(hostname)
        elif 'storage' in hostname:
            storages.append(hostname)
    if controllers and not computes and not storages:
        available_only = True
        if 'controller-0' in controllers and 'controller-1' not in controllers:
            test_step += ' active controller'
        elif 'controller-1' in controllers and 'controller-0' not in controllers:
            test_step += ' standby controller'
        else:
            test_step += ' controller nodes'
    elif computes and not controllers and not storages:
        if len(computes) > 1:
            test_step += ' compute nodes'
        else:
            test_step += " {}".format(computes[0])
    elif storages and not controllers and not computes:
        if len(storages) > 1:
            test_step += ' storage nodes'
        else:
            test_step += " {}".format(storages[0])
    else:
        test_step += " other lab hosts"

    LOG.tc_step(test_step)
    if do_step(test_step):
        if len(hostnames) == 1:
            host_helper.unlock_host(hostnames[0], con_ssh=con_ssh, available_only=available_only)
        else:
            host_helper.unlock_hosts(hostnames, con_ssh=con_ssh)
        host_helper.wait_for_hosts_ready(hostnames, con_ssh=con_ssh)
    if LOG.test_step == final_step or test_step == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))


def run_lab_setup(con_ssh, final_step=None):
    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    test_step = "Run lab setup"
    LOG.tc_step(test_step)
    if do_step(test_step):
        rc, msg = install_helper.run_lab_setup(con_ssh=con_ssh)
        assert rc == 0, msg
    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        reset_global_vars()
        skip("stopping at install step: {}".format(LOG.test_step))


def check_heat_resources(con_ssh, sys_type=None, final_step=None):
    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    if not sys_type:
        sys_type = ProjVar.get_var('SYS_TYPE')
    test_step = "Check heat resources"
    LOG.tc_step(test_step)
    if do_step(test_step):
        install_helper.setup_heat(con_ssh=con_ssh)
        if sys_type != SysType.AIO_SX:
            clear_post_install_alarms(con_ssh=con_ssh)
    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        reset_global_vars()
        skip("stopping at install step: {}".format(LOG.test_step))


def clear_post_install_alarms(con_ssh=None):
    system_helper.wait_for_alarms_gone([("400.001", None), ("800.001", None)], timeout=1800, check_interval=60,
                                       con_ssh=con_ssh)
    alarm = system_helper.get_alarms(alarm_id='250.001', con_ssh=con_ssh)
    if alarm:
        LOG.tc_step("Swact lock/unlock host")
        rc, msg = host_helper.lock_unlock_controllers()
        assert rc == 0, msg


def attempt_to_run_post_install_scripts():
    test_step = "Attempt to run post install scripts"
    LOG.tc_step(test_step)
    if do_step(test_step):
        rc, msg = install_helper.post_install()
        LOG.info(msg)
        assert rc >= 0, msg
    reset_global_vars()


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
