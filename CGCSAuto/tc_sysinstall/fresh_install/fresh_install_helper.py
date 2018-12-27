import os
import re
import time
from pytest import skip

from keywords import install_helper, system_helper, vlm_helper, host_helper, dc_helper, network_helper
from utils.tis_log import LOG, exceptions
from utils.node import Node
from setups import initialize_server
from consts.auth import Tenant
from consts.timeout import InstallTimeout
from consts.cgcs import SysType, SubcloudStatus
from consts.filepaths import BuildServerPath, WRSROOT_HOME, TuxlabServerPath
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
    lab_setup_count_ = set_lab_setup_count(0)
    completed_resume_step_ = set_completed_resume_step(False)

    return lab_setup_count_, completed_resume_step_


def set_preinstall_projvars(build_dir, build_server):
    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.ADMIN)
    ProjVar.set_var(BUILD_SERVER=build_server.name + '.wrs.com')
    set_build_job(build_dir=build_dir)
    set_build_id(build_dir=build_dir, build_server_conn=build_server.ssh_conn)


def set_build_job(build_dir):
    job_regex = r"(CGCS_\d+.\d+_Host)|(TC_\d+.\d+_Host)"
    match = re.search(job_regex, build_dir)
    if match:
        job = match.group(0)
        ProjVar.set_var(JOB=job)

        return job
    else:
        ProjVar.set_var(JOB='n/a')

        return 'n/a'


def set_build_id(build_dir, build_server_conn=None):
    id_regex = r'\d+-\d+-\d+_\d+-\d+-\d+'

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
    skip_list = InstallVars.get_install_var("SKIP")
    current_step_num = str(LOG.test_step)
    resume_step = InstallVars.get_install_var("RESUME")
    in_skip_list = False

    if step_name:
        step_name = step_name.lower().replace(' ', '_')
        if step_name == 'run_lab_setup':
            global lab_setup_count
            step_name = step_name + '-{}'.format(lab_setup_count)
            lab_setup_count += 1
        for skip_step in skip_list:
            if step_name in skip_step.lower() or current_step_num == skip_step:
                if "lab_setup" in step_name and "lab_setup" in skip_step:
                    in_skip_list = step_name[-1] == skip_step[-1]
                else:
                    in_skip_list = True
    else:
        in_skip_list = current_step_num in skip_list
    # if resume flag is given do_step if it's currently the specified resume step or a step after that point
    if resume_step:
        on_resume_step = (int(resume_step) == int(current_step_num) or resume_step == step_name) and \
                         not completed_resume_step
    else:
        on_resume_step = True

    do = (completed_resume_step or on_resume_step) and not in_skip_list
    if not do:
        LOG.info("Skipping step")
    elif not completed_resume_step:
        set_completed_resume_step(True)
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
        vlm_helper.power_off_hosts(lab["hosts"], lab=lab)
        install_helper.boot_controller(lab=lab, small_footprint=is_cpe, boot_usb=usb, security=security,
                                       low_latency=low_latency, patch_dir_paths=patch_dir,
                                       bld_server_conn=patch_server_conn)
    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:

        reset_global_vars()
        skip("stopping at install step: {}".format(LOG.test_step))


def download_lab_files(lab_files_server, build_server, guest_server, sys_version=None, sys_type=None,
                       lab_files_dir=None, load_path=None, guest_path=None, license_path=None, lab=None,
                       final_step=None):

    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    if load_path is None:
        load_path = set_load_path(build_server_conn=build_server.ssh_conn, sys_version=sys_version)
    if not load_path.endswith("/"):
        load_path += "/"
    if guest_path is None or guest_path == BuildServerPath.DEFAULT_GUEST_IMAGE_PATH:
        guest_path = set_guest_image_var(sys_version=sys_version)
    if license_path is None or license_path == BuildServerPath.DEFAULT_LICENSE_PATH:
        license_path = set_license_var(sys_version=sys_version, sys_type=sys_type)
    if lab is None:
        lab = InstallVars.get_install_var('LAB')

    heat_path = InstallVars.get_install_var("HEAT_TEMPLATES")
    if not sys_version:
        sys_version = ProjVar.get_var('SW_VERSION')[0]
    if not heat_path:
        heat_path = os.path.join(load_path, BuildServerPath.HEAT_TEMPLATES_EXTS[sys_version])

    test_step = "Download lab files"
    LOG.tc_step(test_step)
    if do_step(test_step):
        LOG.info("Downloading heat templates")
        install_helper.download_heat_templates(lab, build_server, load_path, heat_path=heat_path)
        LOG.info("Downloading guest image")
        install_helper.download_image(lab, guest_server, guest_path)
        LOG.info("Copying license")
        install_helper.download_license(lab, build_server, license_path, dest_name="license")
        LOG.info("Downloading lab config files")
        install_helper.download_lab_config_files(lab, build_server, load_path, conf_server=lab_files_server,
                                                 lab_file_dir=lab_files_dir)
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
    host_build_path = install_helper.get_default_latest_build_path(version=sys_version)
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


def configure_controller(controller0_node, config_file='TiS_config.ini_centos', lab_setup_conf_file=None,
                         lab=None, final_step=None):

    if lab is None:
        lab = InstallVars.get_install_var("LAB")
    kubernetes = InstallVars.get_install_var("KUBERNETES")

    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    test_step = "Configure controller"
    LOG.tc_step(test_step)
    if do_step(test_step):

        install_helper.controller_system_config(lab=lab, config_file=config_file,
                                                con_telnet=controller0_node.telnet_conn, kubernetes=kubernetes)
        if controller0_node.ssh_conn is None:
            controller0_node.ssh_conn = install_helper.establish_ssh_connection(controller0_node.host_ip)
        install_helper.update_auth_url(ssh_con=controller0_node.ssh_conn)
        LOG.info("Run lab_setup after config controller")
        run_lab_setup(con_ssh=controller0_node.ssh_conn, conf_file=lab_setup_conf_file)
        if do_step("unlock_active_controller"):
            LOG.info("unlocking {}".format(controller0_node.name))
            host_helper.unlock_host(host=controller0_node.name, con_ssh=controller0_node.ssh_conn, timeout=2400,
                                    check_hypervisor_up=False, check_webservice_up=False, check_subfunc=True,
                                    check_first=False, con0_install=True)
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
        LOG.info("system host-bulk-add added: {}".format(added_hosts))
        # assert added_hosts[0] + added_hosts[1] + added_hosts[2] == hosts, "hosts_bulk_add failed to add all hosts
    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))


def boot_hosts(boot_device_dict=None, hostnames=None, lab=None, final_step=None):
    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    test_step = "Boot"

    if lab is None:
        lab = InstallVars.get_install_var('LAB')
    if hostnames is None:
        hostnames = [hostname for hostname in lab['hosts'] if 'controller-0' not in hostname]
    if boot_device_dict is None:
        lab = InstallVars.get_install_var('LAB')
        boot_device_dict = lab.get('boot_device_dict')
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

    threads = []
    LOG.tc_step(test_step)
    if do_step(test_step):
        for hostname in hostnames:
            threads.append(install_helper.open_vlm_console_thread(hostname, lab=lab, boot_interface=boot_device_dict,
                                                                  wait_for_thread=False, vlm_power_on=True,
                                                                  close_telnet_conn=True))
        for thread in threads:
            thread.join(timeout=InstallTimeout.INSTALL_LOAD)

    if LOG.test_step == final_step or test_step == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))


def unlock_hosts(hostnames=None, lab=None, con_ssh=None, final_step=None):
    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    test_step = "Unlock"
    if lab is None:
        lab = InstallVars.get_install_var('LAB')
    if hostnames is None:
        hostnames = lab['hosts'].remove("controller-0")
    if isinstance(hostnames, str):
        hostnames = [hostnames]
    if con_ssh is None:
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
        host_helper.wait_for_hosts_ready(hostnames, con_ssh=con_ssh, timeout=3600)
    if LOG.test_step == final_step or test_step == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))


def run_lab_setup(con_ssh, conf_file=None, final_step=None, ovs=None):
    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    ovs = InstallVars.get_install_var("OVS") if ovs is None else ovs
    if conf_file is None:
        conf_file = 'lab_setup'
    if ovs and lab_setup_count == 0:
        if con_ssh.exec_cmd("test -f {}_ovs.conf".format(conf_file))[0] == 0:
            LOG.debug("setting up ovs lab_setup configuration")
            con_ssh.exec_cmd("rm {}.conf; mv {}_ovs.conf {}.conf".format(conf_file, conf_file, conf_file))
    test_step = "Run lab setup"
    LOG.tc_step(test_step)
    if do_step(test_step):
        LOG.info("running lab_setup.sh")
        install_helper.run_setup_script(conf_file=conf_file, con_ssh=con_ssh, fail_ok=False, config=True)
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


def attempt_to_run_post_install_scripts(controller0_node=None):
    test_step = "Attempt to run post install scripts"
    LOG.tc_step(test_step)
    if do_step(test_step):
        rc, msg = install_helper.post_install(controller0_node=controller0_node)
        LOG.info(msg)
        assert rc >= 0, msg
    reset_global_vars()


def get_resume_step(lab=None, install_progress_path=None):
    if lab is None:
        lab = ProjVar.get_var("LAB")
    if install_progress_path is None:
        install_progress_path = "{}/../{}_install_progress.txt".format(ProjVar.get_var("LOG_DIR"), lab["short_name"])

    with open(install_progress_path, "r") as progress_file:
        lines = progress_file.readlines()
        for line in lines:
            if "End step:" in line:
                return int(line.split("End step: ")[1].strip()) + 1


def install_subcloud(subcloud, load_path, build_server, boot_server=None, boot_type='pxe', files_path=None, lab=None,
                     patch_dir=None, patch_server_conn=None, final_step=None):

    if not subcloud:
        raise ValueError("The subcloud name must be provided")

    if not lab:
        dc_lab = InstallVars.get_install_var("LAB")
        if not dc_lab:
            raise ValueError("Distributed cloud lab dictionary not set")
        lab = dc_lab[subcloud]

    test_step = "Install subcloud {}".format(subcloud)
    LOG.tc_step(test_step)
    LOG.info("Setting network feed for subcloud={}".format(subcloud))
    usb = False
    if "burn" in boot_type:
        install_helper.burn_image_to_usb(build_server, lab_dict=lab)
        usb = True
    elif "boot-usb" in boot_type:
        usb = True

    elif "iso" in boot_type:
        install_helper.rsync_image_to_boot_server(build_server, lab_dict=lab)
        install_helper.mount_boot_server_iso(lab_dict=lab)

    else:
        install_helper.set_network_boot_feed(build_server.ssh_conn, load_path, lab=lab, boot_server=boot_server)

    if InstallVars.get_install_var("WIPEDISK"):
        LOG.fixture_step("Attempting to wipe disks")
        try:
            install_helper.wipe_disk_hosts(lab["hosts"], lab=lab)

        except exceptions.TelnetError as e:
            LOG.error("Failed to wipedisks because of telnet exception: {}".format(e.message))

    LOG.info("Installing {} controller... ".format(subcloud))
    install_controller(sys_type=SysType.REGULAR, lab=lab, usb=usb, patch_dir=patch_dir,
                       patch_server_conn=patch_server_conn)

    LOG.info("SCPing  config files from system controller to {} ... ".format(subcloud))
    install_helper.copy_files_to_subcloud(subcloud)

    system_version = install_helper.extract_software_version_from_string_path(load_path)
    sys_type = lab['system_mode']
    if sys_type == SysType.REGULAR:
        license_path = BuildServerPath.DEFAULT_LICENSE_PATH[system_version][0]
    elif sys_type == SysType.AIO_DX:
        license_path = BuildServerPath.DEFAULT_LICENSE_PATH[system_version][1]
    elif sys_type == SysType.AIO_SX:
        license_path = BuildServerPath.DEFAULT_LICENSE_PATH[system_version][2]
    else:
        license_path = BuildServerPath.DEFAULT_LICENSE_PATH[system_version][0]

    install_helper.download_license(lab, build_server, license_path=license_path, dest_name='license')

    subcloud_controller0 = lab['controller-0']
    if subcloud_controller0 and not subcloud_controller0.ssh_conn:
        subcloud_controller0.ssh_conn = install_helper.establish_ssh_connection(subcloud_controller0.host_ip)

    LOG.info("Running config for subcloud {} ... ".format(subcloud))
    install_helper.run_config_subcloud(subcloud, con_ssh=subcloud_controller0.ssh_conn)
    end_time = time.time() + 60
    while time.time() < end_time:

        if subcloud in dc_helper.get_subclouds(avail=SubcloudStatus.AVAIL_ONLINE,
                                               mgmt=SubcloudStatus.MGMT_UNMANAGED):
            break

        time.sleep(20)

    else:
        assert False, "The subcloud availability did not reach {} status after config"\
            .format(SubcloudStatus.AVAIL_ONLINE)

    LOG.info(" Subcloud {}  is in {}/{} status ... ".format(subcloud, SubcloudStatus.AVAIL_ONLINE,
                                                            SubcloudStatus.MGMT_UNMANAGED))
    LOG.info("Managing subcloud {} ... ".format(subcloud))
    dc_helper.manage_subcloud(subcloud=subcloud)

    LOG.info("Running config for subcloud {} ... ".format(subcloud))
    short_name = lab['short_name']

    lab_setup_filename_ext = short_name.replace('_', '').lower() if len(short_name.split('_')) <= 1 else \
        short_name.split('_')[0].lower() + short_name.split('_')[1]
    lab_setup_filename = 'lab_setup_s{}_'.format(subcloud.split('-')[1]) + lab_setup_filename_ext + '.conf'

    LOG.info("Running lab setup config file {} for subcloud {} ... ".format(lab_setup_filename, subcloud))

    run_lab_setup(con_ssh=subcloud_controller0.ssh_conn, conf_file=lab_setup_filename)

    LOG.info("Installing license file for subcloud {} ... ".format(subcloud))
    subcloud_license_path = WRSROOT_HOME + "license.lic"
    system_helper.install_license(subcloud_license_path, con_ssh=subcloud_controller0.ssh_conn)

    LOG.info("Unlocking  active controller for subcloud {} ... ".format(subcloud))
    unlock_hosts(hostnames=['controller-0'], con_ssh=subcloud_controller0.ssh_conn)

    subcloud_nodes = get_subcloud_nodes_from_lab_dict(lab)

    LOG.info("Installing other {} hosts ... ".format(subcloud))

    if not files_path:
        files_path = load_path + '/' + BuildServerPath.DEFAULT_LAB_CONFIG_PATH_EXTS[system_version]

    install_helper.download_hosts_bulk_add_xml_file(lab, build_server, files_path)
    install_helper.bulk_add_hosts(lab, "hosts_bulk_add.xml", con_ssh=subcloud_controller0.ssh_conn)
    boot_device = lab['boot_device_dict']
    hostnames = [node.name for node in subcloud_nodes if node.name != 'controller-0']
    boot_hosts(boot_device, hostnames=hostnames)
    host_helper.wait_for_hosts_ready(hostnames,  con_ssh=subcloud_controller0.ssh_conn.ssh_conn)

    run_lab_setup(conf_file=lab_setup_filename, con_ssh=subcloud_controller0.ssh_conn)
    run_lab_setup(conf_file=lab_setup_filename, con_ssh=subcloud_controller0.ssh_conn)

    unlock_hosts(hostnames=hostnames, con_ssh=subcloud_controller0.ssh_conn)

    run_lab_setup(conf_file=lab_setup_filename, con_ssh=subcloud_controller0.ssh_conn)

    host_helper.wait_for_hosts_ready(hostnames, subcloud_controller0.name, con_ssh=subcloud_controller0.ssh_conn)

    LOG.info("Subcloud {} installed successfully ... ".format(subcloud))


def add_subclouds(controller0_node, ip_ver=4):
    """

    Args:
        controller0_node:
        ip_ver:

    Returns:

    """

    if controller0_node is None:
        raise ValueError("The distributed cloud system controller node object must be provided")
    if ip_ver not in [4, 6]:
        raise ValueError("The distributed cloud IP version must be either ipv4 or ipv6;  currently set to {}"
                         .format("ipv" + str(ip_ver)))

    if not controller0_node.ssh_conn._is_connected():
        controller0_node.ssh_conn = install_helper.establish_ssh_connection(controller0_node.host_ip)

    subclouds_file = "subcloud_ipv6.txt" if ip_ver == 6 else "subcloud.txt"

    if controller0_node.ssh_conn.exec_cmd("test -f {}{}".format(WRSROOT_HOME, subclouds_file))[0] == 0:
        controller0_node.ssh_conn.exec_cmd("chmod 777 {}{}".format(WRSROOT_HOME, subclouds_file))
    else:
        assert False, "The subclouds text file {} is missing in system controller {}"\
            .format(subclouds_file, controller0_node.name)

    LOG.info("Generating subclouds config info from {}".format(subclouds_file))
    controller0_node.ssh_conn.exec_cmd("cd; ./{}".format(subclouds_file))
    LOG.info("Checking if subclouds are added and config files are generated.....")
    subclouds = dc_helper.get_subclouds()

    for subcloud in subclouds:
        if re.match(r'subcloud-\d{1,2}', subcloud):
            subcloud_config = subcloud.replace('-', '') + ".config"
        else:
            subcloud_config = subcloud + ".config"

        assert controller0_node.ssh_conn.exec_cmd("test -f {}{}".format(WRSROOT_HOME, subcloud_config))[0] == 0, \
            "Subcloud {} config file {} not generated or missing".format(subcloud, subcloud_config)

    LOG.info("Subclouds added and config files generated successfully; subclouds: {}".format(subclouds))

    return subclouds


def install_subclouds(subclouds, subcloud_boots, load_path, build_server, lab=None, patch_dir=None,
                      patch_server_conn=None, final_step=None):
    """

    Args:
        subclouds:
        subcloud_boots:
        load_path:
        build_server:
        lab:
        patch_dir:
        patch_server_conn:
        final_step:

    Returns:

    """

    if not subclouds:
        raise ValueError("List of subcloud names must be provided")
    if isinstance(subclouds, str):
        subclouds = [subclouds]

    added_subclouds = dc_helper.get_subclouds()
    assert all(subcloud in added_subclouds for subcloud in subclouds), \
        "One or more subclouds in {} are not in the system subclouds: {}".format(subclouds, added_subclouds)

    dc_lab = lab
    if not dc_lab:
        dc_lab = InstallVars.get_install_var('LAB')

    LOG.info("Subcloud boot info: {}".format(subcloud_boots))

    for subcloud in subclouds:

        test_step = "Attempt to install {}".format(subcloud)
        LOG.tc_step(test_step)
        if do_step(test_step):
            if subcloud in subcloud_boots.keys():
                boot_type = subcloud_boots.get(subcloud, 'pxe')
                rc, msg = install_subcloud(subcloud, load_path, build_server, patch_dir=patch_dir, boot_type=boot_type,
                                           patch_server_conn=patch_server_conn, lab=dc_lab[subcloud],
                                           final_step=final_step)
                LOG.info(msg)
                assert rc >= 0, msg


def get_subcloud_nodes_from_lab_dict(subcloud_lab):
    """

    Args:
        subcloud_lab:

    Returns:

    """
    if not isinstance(subcloud_lab, dict):
        raise ValueError("The subcloud lab info dictionary must be provided")

    return [v for k, v in subcloud_lab.items() if isinstance(v, Node)]


def parse_subcloud_boot_info(subcloud_boot_info):

    subcloud_boots = {}
    for subcloud_boot in subcloud_boot_info:
        if len(subcloud_boot) == 0:
            continue
        if len(subcloud_boot) == 1:
            subcloud_boots[subcloud_boot[0]] = {'boot': 'pxe', 'boot_server': 'yow-tuxlab2'}
        elif len(subcloud_boot) == 2:
            subcloud_boots[subcloud_boot[0]] = {'boot': subcloud_boot[1], 'boot_server': 'yow-tuxlab2'}
        else:
            subcloud_boots[subcloud_boot[0]] = {'boot': subcloud_boot[1], 'boot_server': subcloud_boot[2]}

    return subcloud_boots


def is_dcloud_system_controller_healthy(system_controller_lab):
    """

    Args:
        system_controller_lab:

    Returns:

    """
    if system_controller_lab is None:
        raise ValueError("The distributed cloud system controller lab dictionary must be provided")

    controller0_node = system_controller_lab['controller-0']
    if not controller0_node.ssh_conn:
        controller0_node.ssh_conn = install_helper.establish_ssh_connection(controller0_node.host_ip)

    if controller0_node.ssh_conn._is_connected():
        rc, health = system_helper.get_system_health_query(controller0_node.ssh_conn)
        if rc == 0:
            LOG.info("System controller {} is healthy".format(system_controller_lab['name']))
            return True
        else:
            LOG.warning("System controller is not healthy: {}".format(health))
            return False
    else:
        LOG.warning("System controller not reachable: {}")
        return False


def reset_controller_telnet_port(controller_node):

    if not controller_node:
        raise ValueError("Controller node object must be specified")

    LOG.info("Attempting to reset port on {}".format(controller_node.name))

    if controller_node.telnet_conn is None:
        controller_node.telnet_conn = install_helper.open_telnet_session(controller_node)
        try:
            network_helper.reset_telnet_port(controller_node.telnet_conn)
        except (exceptions.TelnetError, exceptions.TelnetEOF, exceptions.TelnetTimeout):
            pass


def install_teardown(lab, active_controller_node, dist_cloud=False):
    """

    Args:
        lab:
        active_controller_node:
        dist_cloud:

    Returns:

    """

    try:
        active_controller_node.telnet_conn.login(handle_init_login=True)
        output = active_controller_node.telnet_conn.exec_cmd("cat /etc/build.info", fail_ok=True)[1]
        LOG.info(output)
    except (exceptions.TelnetError, exceptions.TelnetEOF, exceptions.TelnetTimeout) as e_:
        LOG.error(e_.__str__())

    LOG.fixture_step("unreserving hosts")
    if dist_cloud:
        vlm_helper.unreserve_hosts(vlm_helper.get_hostnames_from_consts(lab['central_region']),
                                   lab=lab['central_region'])
        subclouds = [k for k, v in lab.items() if 'subcloud' in k]
        for subcloud in subclouds:
            vlm_helper.unreserve_hosts(vlm_helper.get_hostnames_from_consts(lab[subcloud]),
                                       lab=lab[subcloud])
    else:
        vlm_helper.unreserve_hosts(vlm_helper.get_hostnames_from_consts(lab))


def setup_fresh_install(lab, dist_cloud=False):

    skip_list = InstallVars.get_install_var("SKIP")
    active_con = lab["controller-0"] if not dist_cloud else lab['central_region']["controller-0"]
    install_type = ProjVar.get_var('SYS_TYPE')

    build_server = InstallVars.get_install_var('BUILD_SERVER')
    build_dir = InstallVars.get_install_var("TIS_BUILD_DIR")
    boot_server = InstallVars.get_install_var('BOOT_SERVER')

    # Initialise server objects
    file_server = InstallVars.get_install_var("FILES_SERVER")
    iso_host = InstallVars.get_install_var("ISO_HOST")
    patch_server = InstallVars.get_install_var("PATCH_SERVER")
    guest_server = InstallVars.get_install_var("GUEST_SERVER")
    servers = list({file_server, iso_host, patch_server, guest_server})
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

    set_preinstall_projvars(build_dir=build_dir, build_server=bld_server)

    servers = {
               "build": bld_server,
               "lab_files": file_server_obj,
               "patches": patch_server,
               "guest": guest_server_obj
               }

    directories = {"build": build_dir,
                   "boot": TuxlabServerPath.DEFAULT_BARCODES_DIR,
                   "lab_files": InstallVars.get_install_var("LAB_SETUP_PATH"),
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
        lab_dict = lab if not dist_cloud else lab['central_region']

        if "burn" in boot["boot_type"]:
            install_helper.burn_image_to_usb(iso_host_obj, lab_dict=lab_dict)

        elif "pxe_iso" in boot["boot_type"]:
            install_helper.rsync_image_to_boot_server(iso_host_obj, lab_dict=lab_dict)
            install_helper.mount_boot_server_iso(lab_dict=lab_dict)

        elif 'feed' in boot["boot_type"] and 'feed' not in skip_list:
            load_path = directories["build"]
            skip_cfg = "pxeboot" in skip_list
            install_helper.set_network_boot_feed(bld_server.ssh_conn, load_path, lab=lab_dict, skip_cfg=skip_cfg)

        if InstallVars.get_install_var("WIPEDISK"):
            LOG.fixture_step("Attempting to wipe disks")
            try:
                active_con.telnet_conn.login()
                if dist_cloud:
                    install_helper.wipe_disk_hosts(lab['central_region']["hosts"], lab=lab['central_region'])
                else:
                    install_helper.wipe_disk_hosts(lab["hosts"])
            except exceptions.TelnetError as e:
                LOG.error("Failed to wipedisks because of telnet exception: {}".format(e.message))

    return _install_setup

