import os
import re
import time
from pytest import skip

from keywords import install_helper, system_helper, vlm_helper, host_helper, dc_helper, keystone_helper
from utils.tis_log import LOG, exceptions
from utils.node import Node
from utils.clients.ssh import ControllerClient
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
    complete_resume_step = set_completed_resume_step(False)

    return lab_setup_count_, complete_resume_step


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
        on_resume_step = (str(resume_step) == str(current_step_num) or resume_step == step_name) and \
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
    if not sys_version:
        sys_version = ProjVar.get_var('SW_VERSION')[0]

    if guest_path is None or guest_path == BuildServerPath.DEFAULT_GUEST_IMAGE_PATH:
        guest_path = set_guest_image_var(sys_version=sys_version)
    if license_path is None or license_path == BuildServerPath.DEFAULT_LICENSE_PATH:
        license_path = set_license_var(sys_version=sys_version, sys_type=sys_type)
    if lab is None:
        lab = InstallVars.get_install_var('LAB')

    heat_path = InstallVars.get_install_var("HEAT_TEMPLATES")

    if not heat_path:
        sys_version = sys_version if sys_version in BuildServerPath.HEAT_TEMPLATES_EXTS else 'default'
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

    if InstallVars.get_install_var("NO_OPENSTACK_INSTALL"):
        controller0_node = lab['controller-0']
        controller0_node.telnet_conn.exec_cmd("touch .no_opentack_install")

    if InstallVars.get_install_var("KUBERNETES"):
        LOG.info("WK: Downloading the helm charts to active controller ...")
        helm_chart_path = os.path.join(load_path, BuildServerPath.STX_HELM_CHARTS)
        install_helper.download_stx_helm_charts(lab, build_server, stx_helm_charts_path=helm_chart_path)


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

    sys_version = sys_version if sys_version in BuildServerPath.TIS_LICENSE_PATHS else 'default'
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

    sys_version = sys_version if sys_version in BuildServerPath.GUEST_IMAGE_PATHS else 'default'
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

    test_step = "unlock_active_controller"
    LOG.tc_step(test_step)
    if do_step(test_step):
        LOG.info("unlocking {}".format(controller0_node.name))
        host_helper.unlock_host(host=controller0_node.name, con_ssh=controller0_node.ssh_conn, timeout=2400,
                                check_hypervisor_up=False, check_webservice_up=False, check_subfunc=True,
                                check_first=False, con0_install=True)
    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        reset_global_vars()
        skip("stopping at install step: {}".format(LOG.test_step))


def configure_subcloud(subcloud_controller0_node, main_cloud_node, subcloud='subcloud-1', lab=None, final_step=None):

    if lab is None:
        lab = InstallVars.get_install_var("LAB")

    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    test_step = "Configure subcloud"
    LOG.tc_step(test_step)
    if do_step(test_step):

        subcloud_config = subcloud.replace('-', '') + '.config'

        install_helper.controller_system_config(lab=lab, config_file=subcloud_config,
                                                con_telnet=subcloud_controller0_node.telnet_conn,
                                                subcloud=True)

        if subcloud_controller0_node.ssh_conn is None:
            subcloud_controller0_node.ssh_conn = install_helper.establish_ssh_connection(
                subcloud_controller0_node.host_ip)

        ControllerClient.set_active_controller(subcloud_controller0_node.ssh_conn)
        # install_helper.update_auth_url(ssh_con=subcloud_controller0_node.ssh_conn)
        LOG.info("Auto_info before update: {}".format(Tenant.get('admin', 'RegionOne')))
        if not main_cloud_node.ssh_conn:
            main_cloud_node.ssh_conn = install_helper.establish_ssh_connection(main_cloud_node.host_ip)
        install_helper.update_auth_url(ssh_con=main_cloud_node.ssh_conn)
        LOG.info("Auto_info after update: {}".format(Tenant.get('admin', 'RegionOne')))
        dc_helper.wait_for_subcloud_status(subcloud, avail=SubcloudStatus.AVAIL_ONLINE,
                                           mgmt=SubcloudStatus.MGMT_UNMANAGED, con_ssh=main_cloud_node.ssh_conn)

        LOG.info(" Subcloud {}  is in {}/{} status ... ".format(subcloud, SubcloudStatus.AVAIL_ONLINE,
                                                                SubcloudStatus.MGMT_UNMANAGED))
        LOG.info("Managing subcloud {} ... ".format(subcloud))
        LOG.info("Auto_info before manage: {}".format(Tenant.get('admin', 'RegionOne')))
        install_helper.update_auth_url(ssh_con=main_cloud_node.ssh_conn)
        dc_helper.manage_subcloud(subcloud=subcloud, conn_ssh=main_cloud_node.ssh_conn, fail_ok=True)

        dc_helper.wait_for_subcloud_status(subcloud, avail=SubcloudStatus.AVAIL_ONLINE,
                                           mgmt=SubcloudStatus.MGMT_MANAGED, sync=SubcloudStatus.SYNCED,
                                           con_ssh=main_cloud_node.ssh_conn)

        LOG.info("Running config for subcloud {} ... ".format(subcloud))
        install_helper.update_auth_url(ssh_con=subcloud_controller0_node.ssh_conn)
        LOG.info("Run lab_setup after config controller")

        run_lab_setup(con_ssh=subcloud_controller0_node.ssh_conn)
        if do_step("unlock_active_controller"):
            LOG.info("unlocking {}".format(subcloud_controller0_node.name))
            host_helper.unlock_host(host=subcloud_controller0_node.name, con_ssh=subcloud_controller0_node.ssh_conn,
                                    timeout=2400, check_hypervisor_up=False, check_webservice_up=False,
                                    check_subfunc=True, check_first=False, con0_install=True)

        LOG.info("Installing license file for subcloud {} ... ".format(subcloud))
        subcloud_license_path = WRSROOT_HOME + "license.lic"
        system_helper.install_license(subcloud_license_path, con_ssh=subcloud_controller0_node.ssh_conn)

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
            host_helper.unlock_host(hostnames[0], con_ssh=con_ssh, available_only=available_only, timeout=2400)
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

    # TODO Workaround for kubernetes install
    if InstallVars.get_install_var("KUBERNETES"):
        kubernetes_post_install()

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


def _install_subcloud(subcloud, load_path, build_server, boot_server=None, boot_type='pxe', files_path=None, lab=None,
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
    license_version = system_version if system_version in BuildServerPath.DEFAULT_LICENSE_PATH else 'default'
    sys_type = lab['system_mode']
    if sys_type == SysType.REGULAR:
        license_path = BuildServerPath.DEFAULT_LICENSE_PATH[license_version][0]
    elif sys_type == SysType.AIO_DX:
        license_path = BuildServerPath.DEFAULT_LICENSE_PATH[license_version][1]
    elif sys_type == SysType.AIO_SX:
        license_path = BuildServerPath.DEFAULT_LICENSE_PATH[license_version][2]
    else:
        license_path = BuildServerPath.DEFAULT_LICENSE_PATH[license_version][0]

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
        system_version = system_version if system_version in BuildServerPath.DEFAULT_LAB_CONFIG_PATH_EXTS else 'default'
        files_path = load_path + '/' + BuildServerPath.DEFAULT_LAB_CONFIG_PATH_EXTS[system_version]

    install_helper.download_hosts_bulk_add_xml_file(lab, build_server, files_path)
    install_helper.bulk_add_hosts(lab, "hosts_bulk_add.xml", con_ssh=subcloud_controller0.ssh_conn)
    boot_device = lab['boot_device_dict']
    hostnames = [node.host_name for node in subcloud_nodes if node.host_name != 'controller-0']
    boot_hosts(boot_device, hostnames=hostnames)
    host_helper.wait_for_hosts_ready(hostnames,  con_ssh=subcloud_controller0.ssh_conn.ssh_conn)

    run_lab_setup(conf_file=lab_setup_filename, con_ssh=subcloud_controller0.ssh_conn)
    run_lab_setup(conf_file=lab_setup_filename, con_ssh=subcloud_controller0.ssh_conn)

    unlock_hosts(hostnames=hostnames, con_ssh=subcloud_controller0.ssh_conn)

    run_lab_setup(conf_file=lab_setup_filename, con_ssh=subcloud_controller0.ssh_conn)

    host_helper.wait_for_hosts_ready(hostnames, subcloud_controller0.name, con_ssh=subcloud_controller0.ssh_conn)

    LOG.info("Subcloud {} installed successfully ... ".format(subcloud))


def add_subclouds(controller0_node, name=None, ip_ver=4):
    """

    Args:
        controller0_node:
        name
        ip_ver:

    Returns:

    """

    if controller0_node is None:
        raise ValueError("The distributed cloud system controller node object must be provided")
    if ip_ver not in [4, 6]:
        raise ValueError("The distributed cloud IP version must be either ipv4 or ipv6;  currently set to {}"
                         .format("ipv" + str(ip_ver)))
    if name is None:
        name = 'subcloud'

    if not controller0_node.ssh_conn._is_connected():
        controller0_node.ssh_conn = install_helper.establish_ssh_connection(controller0_node.host_ip)

    existing_subclouds = dc_helper.get_subclouds(con_ssh=controller0_node.ssh_conn, source_openrc=True)
    if name and 'subcloud' in name and name in existing_subclouds:
        LOG.info("Subcloud {} already exits; do nothing".format(name))
        managed = dc_helper.get_subclouds(name=name, avail="managed", con_ssh=controller0_node.ssh_conn,
                                          source_openrc=True)
        if name in managed:
            LOG.info("Subcloud {} is in managed status; unamanage subcloud before install".format(name))
            dc_helper._manage_unmanage_subcloud(subcloud=name, con_ssh=controller0_node.ssh_conn)

        return 0, [name]


    if name is not None and name is not '':
        subclouds_file = "{}_ipv6.txt".format(name) if ip_ver == 6 else "{}.txt".format(name)
        subclouds_file_path = WRSROOT_HOME + name + '/' + subclouds_file
    else:
        subclouds_file = "subcloud_ipv6.txt" if ip_ver == 6 else "subcloud.txt"
        subclouds_file_path = WRSROOT_HOME + subclouds_file

    cmd = "test -f {}".format(subclouds_file_path)
    cmd2 = "chmod 777 {}".format(subclouds_file_path)

    if controller0_node.ssh_conn.exec_cmd(cmd)[0] == 0:
        controller0_node.ssh_conn.exec_cmd(cmd2)
    else:
        assert False, "The subclouds text file {} is missing in system controller {}"\
            .format(subclouds_file, controller0_node.host_name)

    LOG.info("Generating subclouds config info from {}".format(subclouds_file))
    controller0_node.ssh_conn.exec_cmd("{}".format(subclouds_file_path))
    LOG.info("Checking if subclouds are added and config files are generated.....")
    subclouds = dc_helper.get_subclouds(con_ssh=controller0_node.ssh_conn, source_openrc=True)
    added_subclouds = [sub for sub in subclouds if sub not in existing_subclouds]
    if name not in added_subclouds:
        msg = "Fail to add subcloud {}. Existing subclouds= {}; Added subclouds = {}".format(name, existing_subclouds,
                                                                                             added_subclouds)
        LOG.warning(msg)
        assert False, msg

    config_generated = []
    for subcloud in added_subclouds:
        if re.match(r'subcloud-\d{1,2}', subcloud):
            subcloud_config = subcloud.replace('-', '') + ".config"
        else:
            subcloud_config = subcloud + ".config"

        rc = controller0_node.ssh_conn.exec_cmd("test -f {}{}".format(WRSROOT_HOME, subcloud_config))[0]
        if rc == 0:
            config_generated.append(subcloud_config)
            config_path = WRSROOT_HOME + subcloud
            controller0_node.ssh_conn.exec_cmd("mv {}{} {}/".format(WRSROOT_HOME, subcloud_config, config_path))
        else:
            msg = "Subcloud {} config file {} not generated or missing".format(subcloud, subcloud_config)
            LOG.warning(msg)
            assert False, msg

    if len(added_subclouds) == len(config_generated):
        LOG.info("Subclouds added and config files generated successfully; subclouds: {}"
                 .format(list(zip(added_subclouds, config_generated))))
    else:
        LOG.info("One or more subcloud config are missing, please try to generate the missing configs manually")

    return 0, added_subclouds


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
                rc, msg = _install_subcloud(subcloud, load_path, build_server, patch_dir=patch_dir, boot_type=boot_type,
                                            patch_server_conn=patch_server_conn, lab=dc_lab[subcloud],
                                            final_step=final_step)
                LOG.info(msg)
                assert rc >= 0, msg


def get_subcloud_nodes_from_lab_dict(subcloud_lab):
    """

    Args:
        subcloud_lab:

    Returns (list of Node):

    """
    if not isinstance(subcloud_lab, dict):
        raise ValueError("The subcloud lab info dictionary must be provided")

    return [v for v in subcloud_lab.values() if isinstance(v, Node)]


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
            if len(health) == 1:
                if 'No alarms' in health:
                    # alarm_ids = system_helper.get_alarms(combine_entries=False)
                    # if all([alarm for alarm in alarm_ids if 'subcloud-' in alarm[1]]):
                    LOG.info("System controller {} report alarms; ignoring the alarm".
                             format(system_controller_lab['name']))
                    return True

            LOG.info("System controller {} not  healthy: {}".format(system_controller_lab['name'], health))

    else:
        LOG.warning("System controller not reachable: {}")
        return False


def is_dcloud_system_controller_ipv6(controller0_node):
    """
    Checks if the system controller in dc system is configured as ipv6 by checking endpoints urls.
    Args:
        controller0_node:

    Returns:

    """
    if controller0_node is None:
        raise ValueError("The distributed cloud system controller lab dictionary must be provided")

    if not controller0_node.ssh_conn:
        controller0_node.ssh_conn = install_helper.establish_ssh_connection(controller0_node.host_ip)

    if controller0_node.ssh_conn._is_connected():
        install_helper.update_auth_url(ssh_con=controller0_node.ssh_conn)
        urls = keystone_helper.get_endpoints(rtn_val='URL', service_name='sysinv', service_type='platform', enabled='True',
                                      interface='admin', region='SystemController', con_ssh=controller0_node.ssh_conn)

        if len(urls) > 0:
            ip_addr = urls[0].strip().split('//')[1].split('/')[0].rsplit(':',1)[0]
            if len(ip_addr.split(':')) > 1:
                LOG.info("System controller {} is ipv6".format(controller0_node.host_name))
                return True

    LOG.warning("System controller {} is ipv4".format(controller0_node.host_name))
    return False


def reset_controller_telnet_port(controller_node):

    if not controller_node:
        raise ValueError("Controller node object must be specified")

    LOG.info("Attempting to reset port on {}".format(controller_node.name))

    if controller_node.telnet_conn is None:
        controller_node.telnet_conn = install_helper.open_telnet_session(controller_node)
        try:
            install_helper.reset_telnet_port(controller_node.telnet_conn)
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

    try:
        if active_controller_node.ssh_conn:
            active_controller_node.ssh_conn.connect(retry=True, retry_interval=3, retry_timeout=300)
            active_controller_node.ssh_conn.flush()
    except (exceptions.SSHException, exceptions.SSHRetryTimeout, exceptions.SSHExecCommandFailed) as e_:
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


def setup_fresh_install(lab, dist_cloud=False, subcloud=None):

    skip_list = InstallVars.get_install_var("SKIP")
    active_con = lab["controller-0"] if not dist_cloud else lab['central_region']["controller-0"]

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
    dc_float_ip = None
    install_sub = None
    if subcloud:
        dc_float_ip = InstallVars.get_install_var("DC_FLOAT_IP")
        install_sub = InstallVars.get_install_var("INSTALL_SUBCLOUD")
        file_server_obj = Node(host_ip=dc_float_ip, host_name='controller-0')
        file_server_obj.ssh_conn = install_helper.establish_ssh_connection(file_server_obj.host_ip)
        ipv6_config = InstallVars.get_install_var("IPV6_CONFIG")
        v6 = is_dcloud_system_controller_ipv6(file_server_obj)
        if not v6:
            if ipv6_config:
                LOG.warning("The DC System controller is configured as IPV4; Switching to IPV4")
                ipv6_config = False
        else:
            LOG.warning("The DC System controller is configured as IPV6; Configuring subcloud {} as IPV6"
                        .format(install_sub))
            ipv6_config = True
        InstallVars.set_install_var(ipv6_config=ipv6_config)
        add_subclouds(file_server_obj, name=install_sub, ip_ver=6 if ipv6_config else 4)
    else:
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

    boot_type = InstallVars.get_install_var("BOOT_TYPE")
    if "usb" in boot_type:
        # check if oam nic is set
        controller0_node = lab['controller-0'] if not dist_cloud else lab['central_region']['controller-0']
        if not controller0_node.host_nic:
            controller0_node.host_nic = install_helper.get_nic_from_config(conf_server=file_server_obj)

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

    boot = {"boot_server": boot_server,
            "boot_type": InstallVars.get_install_var("BOOT_TYPE"),
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

    if subcloud and install_sub:
        _install_setup['install_subcloud'] = install_sub
        _install_setup['dc_float_ip'] = dc_float_ip

    if not InstallVars.get_install_var("RESUME") and "0" not in skip_list and "setup" not in skip_list:
        LOG.fixture_step("Setting up {} boot".format(boot["boot_type"]))
        lab_dict = lab if not dist_cloud else (lab['central_region'] if not subcloud else lab[subcloud])

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


def verify_install_uuid(lab=None):

    if lab is None:
        lab = InstallVars.get_install_var("LAB")

    controller0_node = lab['controller-0']

    if not controller0_node.ssh_conn:
        controller0_node.ssh_conn = install_helper.establish_ssh_connection(controller0_node.host_ip)

    LOG.info("Getting the install uuid from controller-0")
    install_uuid = install_helper.get_host_install_uuid(controller0_node.name, controller0_node.ssh_conn)
    LOG.info("The install uuid from controller-0 = {}".format(install_uuid))

    LOG.info("Verify all hosts have the same install uuid {}".format(install_uuid))
    hosts = lab['hosts']
    hosts.remove('controller-0')
    for host in hosts:
        with host_helper.ssh_to_host(host) as host_ssh:
            host_install_uuid = install_helper.get_host_install_uuid(host, host_ssh)
            assert host_install_uuid == install_uuid, "The host {} install uuid {} is not same with controller-0 " \
                                                      "uuid {}".format(host, host_install_uuid, install_uuid)
            LOG.info("Host {} install uuid verified".format(host))
    LOG.info("Installation UUID {} verified in all lab hosts".format(install_uuid))

    return True


def kubernetes_post_install():
    """
    Installs kubernetes work arounds post install
    Args:
        # server(build server object): The build server object where helm charts reside.
        # load_path(str): The path to helm charts

    Returns:

    """
    # if lab is None or server is None or load_path is None:
    #     raise ValueError("The lab dictionary, build server object and load path must be specified")
    lab = InstallVars.get_install_var("LAB")
    controller0_node = lab['controller-0']

    if not controller0_node.ssh_conn:
        controller0_node.ssh_conn = install_helper.establish_ssh_connection(controller0_node.host_ip)

    # LOG.info("WK: Trying to execute workaround for neutron-ovs-agent on each hypervisor ...")
    # hypervisors = host_helper.get_hypervisors(con_ssh=controller0_node.ssh_conn)
    # for hypervisor in hypervisors:
    #     with host_helper.ssh_to_host(hypervisor) as host_ssh:
    #         host_ssh.exec_sudo_cmd('sh -c "echo 1 > /proc/sys/net/bridge/bridge-nf-call-arptables"')
    # LOG.info("WK: Executed workaround for neutron-ovs-agentr ...")
    #
    # LOG.info("WK: Adding DNS for cluster ...")
    # nameservers = ["8.8.8.8"]
    # rc, output = controller0_node.ssh_conn.exec_cmd("kubectl describe svc -n kube-system kube-dns | "
    #                                                 "awk /IP:/'{print $2}'")
    # if rc == 0:
    #     nameservers.append(output)
    #
    # system_helper.set_dns_servers(nameservers)
    # LOG.info("WK: Added DNS  for the cluster...")
    #
    # LOG.info("WK: Generating the stx-openstack application tarball ...")
    # LOG.info("WK: Downloading the helm charts to active controller ...")
    # helm_chart_path = os.path.join(load_path, BuildServerPath.STX_HELM_CHARTS)
    # install_helper.download_stx_help_charts(lab, server, stx_helm_charts_path=helm_chart_path)

    # LOG.info("WK: Creating hosts and binding interface ...")
    # hosts = lab['hosts']
    # nodes = kube_helper.get_nodes_values(rtn_val='NAME', con_ssh=controller0_node.ssh_conn)
    # cmd_auth = "export OS_AUTH_URL=http://keystone.openstack.svc.cluster.local/v3"
    # for host in nodes:
    #
    #     uuid = host_helper.get_hostshow_value(host, 'uuid')
    #     controller0_node.ssh_conn.exec_cmd(cmd_auth)
    #     cmd = "neutron host-create {} --id {} --availablitiy up".format(host, uuid)
    #     controller0_node.ssh_conn.exec_cmd(cmd)
    #
    # for node in nodes:
    #     install_helper.update_auth_url(ssh_con=controller0_node.ssh_conn)
    #     data0_info = system_helper.get_host_if_show_values(node, "data0", ["uuid", "providernetworks"],
    #                                                        con_ssh=controller0_node.ssh_conn)
    #     data1_info = system_helper.get_host_if_show_values(node, "data1", ["uuid", "providernetworks"],
    #                                                        con_ssh=controller0_node.ssh_conn)
    #
    #     cmd0 = "neutron host-bind-interface --interface {} --providernets {} --mtu 1500 {}"\
    #             .format(data0_info[0], data0_info[1], node)
    #     cmd1 = "neutron host-bind-interface --interface {} --providernets {} --mtu 1500 {}"\
    #         .format(data1_info[0], data1_info[1], node)
    #     controller0_node.ssh_conn.exec_cmd(cmd_auth)
    #     controller0_node.ssh_conn.exec_cmd(cmd0)
    #     controller0_node.ssh_conn.exec_cmd(cmd1)
    #
    # install_helper.update_auth_url(ssh_con=controller0_node.ssh_conn)


def wait_for_hosts_ready(hosts,  lab=None):
    """

    Args:
        hosts:
        lab:
        con_ssh:

    Returns:

    """
    if lab is None:
        lab = InstallVars.get_install_var("LAB")

    controller0_node = lab['controller-0']

    if not controller0_node.ssh_conn:
        controller0_node.ssh_conn = install_helper.establish_ssh_connection(controller0_node.host_ip)

    # kubernetes = InstallVars.get_install_var("KUBERNETES")
    # if kubernetes:
    #     # kube_helper.wait_for_nodes_ready(hosts, con_ssh=controller0_node.ssh_conn)
    # else:
    host_helper.wait_for_hosts_ready(hosts, con_ssh=controller0_node.ssh_conn)
