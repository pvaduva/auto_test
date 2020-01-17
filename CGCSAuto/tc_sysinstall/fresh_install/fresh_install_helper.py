import os
import time
import yaml
import pysftp
import base64

import pexpect
from pytest import skip

import setups
from utils import cli
from utils.tis_log import LOG, exceptions
from utils.node import Node
from utils.clients.ssh import ControllerClient, NATBoxClient, SSHFromSSH
from consts.lab import NatBoxes
from consts.auth import Tenant, HostLinuxUser, TestFileServer
from consts.timeout import InstallTimeout, HostTimeout, DCTimeout
from consts.stx import SysType, SubcloudStatus, HostAdminState, HostAvailState, HostOperState, \
    VSwitchType
from consts.filepaths import BuildServerPath, TuxlabServerPath
from consts.proj_vars import ProjVar, InstallVars
from keywords import install_helper, system_helper, vlm_helper, host_helper, dc_helper, \
    kube_helper, storage_helper, keystone_helper, common, container_helper

DEPLOY_TOOL = 'deploy'
DEPLOY_SOUCE_PATH = '/folk/cgts/lab/bin/'
DEPLOY_RESULTS_DEST_PATH = '/folk/cgts/lab/deployment-manager/generated-configs/'
DEPLOY_INTITIAL = 'initial'
DEPLOY_INTERIM = 'interim'
DEPLOY_LAST = 'last'

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


#
# def set_preinstall_projvars(build_dir, build_server):
#     ProjVar.set_var(SOURCE_OPENRC=True)
#     ProjVar.set_var(BUILD_SERVER=build_server.name)
#     # set_build_job(build_dir=build_dir)
#     set_build_id(build_dir=build_dir, build_server_conn=build_server.ssh_conn)


# def set_build_job(build_dir):
#     job_regex = r"(CGCS_\d+.\d+_Host)|(TC_\d+.\d+_Host)"
#     match = re.search(job_regex, build_dir)
#     if match:
#         job = match.group(0)
#         ProjVar.set_var(JOB=job)
#
#         return job
#     else:
#         ProjVar.set_var(JOB='n/a')
#
#         return 'n/a'


# def set_build_id(build_dir, build_server_conn=None):
#     id_regex = r'\d+-\d+-\d+_\d+-\d+-\d+'
#
#     if build_dir.endswith("/"):
#         build_dir = build_dir[:-1]
#     rc, output = build_server_conn.exec_cmd("readlink {}".format(build_dir))
#     if rc == 0:
#         output_parts = output.split("/")
#         build_dir_parts = build_dir.split("/")
#         for part in output_parts:
#             if part not in build_dir_parts:
#                 if re.search(id_regex, part):
#                     ProjVar.set_var(BUILD_ID=part)
#
#                     return part
#     else:
#         match = re.search(id_regex, build_dir)
#         build_id = 'n/a'
#         if match:
#             build_id = match.group(0)
#
#         ProjVar.set_var(BUILD_ID=match.group(0))
#         return build_id


def do_step(step_name=None):
    global completed_resume_step
    skip_list = InstallVars.get_install_var("SKIP")
    current_step_num = str(LOG.test_step)
    resume_step = InstallVars.get_install_var("RESUME")
    in_skip_list = False

    if step_name:
        step_name = step_name.lower().replace(' ', '_')
        if 'run_lab_setup' == step_name:
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
    # if resume flag is given do_step if it's currently the specified resume step or a step
    # after that point
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


def install_controller(security=None, low_latency=None, lab=None, sys_type=None, usb=None,
                       patch_dir=None,
                       patch_server_conn=None, final_step=None, init_global_vars=False):
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
    is_cpe = sys_type == SysType.AIO_SX or sys_type == SysType.AIO_DX or sys_type == SysType.DISTRIBUTED_CLOUD

    test_step = "Install Controller"
    LOG.tc_step(test_step)
    if do_step(test_step):
        install_helper.power_off_hosts_(lab)
        install_helper.boot_controller(lab=lab, small_footprint=is_cpe, boot_usb=usb,
                                       security=security,
                                       low_latency=low_latency, patch_dir_paths=patch_dir,
                                       bld_server_conn=patch_server_conn,
                                       init_global_vars=init_global_vars)
    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        reset_global_vars()
        skip("stopping at install step: {}".format(LOG.test_step))


def download_lab_files(lab_files_server, build_server, guest_server, sys_version=None,
                       sys_type=None,
                       lab_files_dir=None, load_path=None, guest_path=None,
                       helm_chart_server=None, license_path=None,
                       lab=None, final_step=None):
    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step

    if not sys_version:
        sys_version = ProjVar.get_var('SW_VERSION')
        sys_version = sys_version[-1] if sys_version else 'default'

    if load_path is None:
        load_path = set_load_path(sys_version=sys_version)
    if not load_path.endswith("/"):
        load_path += "/"

    if guest_path is None or guest_path == BuildServerPath.DEFAULT_GUEST_IMAGE_PATH:
        guest_path = set_guest_image_var(sys_version=sys_version)
    if license_path is None or license_path == BuildServerPath.DEFAULT_LICENSE_PATH:
        license_path = set_license_var(sys_version=sys_version, sys_type=sys_type)
    if lab is None:
        lab = InstallVars.get_install_var('LAB')

    heat_path = InstallVars.get_install_var("HEAT_TEMPLATES")

    if not heat_path:
        sys_version = sys_version if sys_version in BuildServerPath.HEAT_TEMPLATES_EXTS \
            else 'default'
        heat_path = os.path.join(load_path, BuildServerPath.HEAT_TEMPLATES_EXTS[sys_version])

    test_step = "Download lab files"
    LOG.tc_step(test_step)
    if do_step(test_step):
        con0_v6_ip = None

        if InstallVars.get_install_var('IPV6_OAM'):
            con0_v6_ip = lab['controller-0 ip']
            # Use ipv4 ip to download files temporarily
            con0_v4_ip = con0_v6_ip.rsplit(':', maxsplit=1)[-1]
            if len(con0_v4_ip) == 4 and con0_v4_ip.startswith('1'):
                con0_v4_ip = '128.224.151.{}'.format(con0_v4_ip[-3:].lstrip("0"))
            else:
                con0_v4_ip = '128.224.150.{}'.format(con0_v4_ip[-3:])
            lab['controller-0 ip'] = con0_v4_ip

        LOG.info("Downloading heat templates with best effort")
        install_helper.download_heat_templates(lab, build_server, load_path, heat_path=heat_path)
        LOG.info("Downloading guest image")
        install_helper.download_image(lab, guest_server, guest_path)
        LOG.info("Copying license")
        install_helper.download_license(lab, build_server, license_path, dest_name="license")
        LOG.info("Downloading lab config files")
        install_helper.download_lab_config_files(lab, build_server, load_path,
                                                 conf_server=lab_files_server,
                                                 lab_file_dir=lab_files_dir)

        LOG.info("Download helm charts to active controller ...")
        helm_chart_path = InstallVars.get_install_var("HELM_CHART_PATH")
        if not helm_chart_server:
            helm_chart_server = build_server
        install_helper.download_stx_helm_charts(lab, helm_chart_server,
                                                stx_helm_charts_path=helm_chart_path)

        if ProjVar.get_var('IPV6_OAM'):
            lab['controller-0 ip'] = con0_v6_ip
            if InstallVars.get_install_var('INSTALL_SUBCLOUD'):
                install_helper.config_ipv6_oam_interface(lab)
            else:
                install_helper.setup_ipv6_oam(lab['controller-0'])

        if not InstallVars.get_install_var("DEPLOY_OPENSTACK"):
            controller0_node = lab['controller-0']
            # controller0_node.telnet_conn.set_prompt(r'-[\d]+((:~\$)|( ~\(keystone_admin\)\]\$ ))')
            controller0_node.telnet_conn.set_prompt(r'(.*:~\$\s?)|(\[.*\(keystone_admin\)\]\$ )')
            controller0_node.telnet_conn.exec_cmd("touch .no_openstack_install")

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

    sys_version = sys_version if sys_version in BuildServerPath.TIS_LICENSE_PATHS else 'default'
    license_paths = BuildServerPath.TIS_LICENSE_PATHS[sys_version]
    LOG.debug(license_paths)
    LOG.debug(license_paths[index])
    license_path = license_paths[index]
    InstallVars.set_install_var(license=license_path)

    return license_path


def set_load_path(sys_version=None):
    if sys_version is None:
        sys_version = ProjVar.get_var('SW_VERSION')[-1]
    host_build_path = install_helper.get_default_latest_build_path(version=sys_version)
    load_path = host_build_path + "/"

    InstallVars.set_install_var(tis_build_dir=host_build_path)
    ProjVar.set_var(BUILD_PATH=load_path)

    return load_path


def set_guest_image_var(sys_version=None):
    if sys_version is None:
        sys_version = ProjVar.get_var('SW_VERSION')[-1]

    sys_version = sys_version if sys_version in BuildServerPath.GUEST_IMAGE_PATHS else 'default'
    guest_path = BuildServerPath.GUEST_IMAGE_PATHS[sys_version]

    InstallVars.set_install_var(guest_image=guest_path)

    return guest_path


def configure_controller_(controller0_node, config_file='TiS_config.ini_centos', lab=None,
                          banner=True, branding=True,
                          final_step=None):
    if lab is None:
        lab = InstallVars.get_install_var("LAB")
    kubernetes = InstallVars.get_install_var("KUBERNETES")
    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step

    if controller0_node.telnet_conn is None:
        controller0_node.telnet_conn = install_helper.open_telnet_session(controller0_node)

    deploy_mgr = use_deploy_manager(controller0_node, lab)
    ansible = True if deploy_mgr or use_ansible(controller0_node) else False

    if deploy_mgr:

        # This temporary solution until we implement the yaml helper functions
        vswitch_type = InstallVars.get_install_var("VSWITCH_TYPE")
        ovs_dpdk_yaml = 'deployment-config_ovs-dpdk.yaml'
        none_yaml = 'deployment-config_none.yaml'
        default_yaml = 'deployment-config.yaml'
        if vswitch_type in [VSwitchType.OVS_DPDK]:
            if controller0_node.telnet_conn.exec_cmd("test -f {}".format(ovs_dpdk_yaml))[0] == 0:
                LOG.debug("setting up ovs_dpdk deployment-config yaml")
                controller0_node.telnet_conn.exec_cmd("mv {} {} ; mv {} {}".format(
                    default_yaml, none_yaml, ovs_dpdk_yaml, default_yaml))
        # End of temporary solution

    test_step = "Configure controller"
    LOG.tc_step(test_step)
    if do_step(test_step):
        install_helper.controller_system_config(lab=lab, config_file=config_file,
                                                con_telnet=controller0_node.telnet_conn,
                                                kubernetes=kubernetes,
                                                banner=banner, branding=branding, ansible=ansible,
                                                deploy_manager=deploy_mgr)

    if controller0_node.ssh_conn is not None:
        controller0_node.ssh_conn.close()
    controller0_node.ssh_conn = install_helper.ssh_to_controller(controller0_node.host_ip)

    # WK Touch .this_didnt_work to avoid using heat for kubernetes
    controller0_node.ssh_conn.exec_cmd("cd; touch .this_didnt_work")

    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        reset_global_vars()
        skip("stopping at install step: {}".format(LOG.test_step))


def unlock_active_controller(controller0_node, lab=None, final_step=None):
    if lab is None:
        lab = InstallVars.get_install_var("LAB")
    test_step = "unlock_active_controller"
    LOG.tc_step(test_step)
    if do_step(test_step):
        if controller0_node.ssh_conn is None:
            controller0_node.ssh_conn = install_helper.ssh_to_controller(controller0_node.host_ip)

        sys_mode = system_helper.get_system_values(fields="system_mode",
                                                   con_ssh=controller0_node.ssh_conn)[0]
        LOG.info("unlocking {}".format(controller0_node.name))
        host_helper.unlock_host(host=controller0_node.name,
                                available_only=False if sys_mode == "duplex-direct" else True,
                                con_ssh=controller0_node.ssh_conn, timeout=2400,
                                check_hypervisor_up=False, check_webservice_up=False,
                                check_subfunc=False,
                                check_first=False, con0_install=True)

    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        reset_global_vars()
        skip("stopping at install step: {}".format(LOG.test_step))


def configure_controller_dc(controller0_node, config_file='TiS_config.ini_centos',
                            lab_setup_conf_file=None,
                            lab=None, banner=True, branding=True, final_step=None):
    if lab is None:
        lab = InstallVars.get_install_var("LAB")
    kubernetes = InstallVars.get_install_var("KUBERNETES")

    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    test_step = "Configure controller"
    LOG.tc_step(test_step)
    if do_step(test_step):
        install_helper.controller_system_config(lab=lab, config_file=config_file,
                                                con_telnet=controller0_node.telnet_conn,
                                                kubernetes=kubernetes,
                                                banner=banner, branding=branding)

    if controller0_node.ssh_conn is None:
        controller0_node.ssh_conn = install_helper.ssh_to_controller(controller0_node.host_ip)
    install_helper.update_auth_url(ssh_con=controller0_node.ssh_conn)

    # WK Touch .this_didnt_work to avoid using heat for kubernetes
    controller0_node.ssh_conn.exec_cmd("cd; touch .this_didnt_work")

    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        reset_global_vars()
        skip("stopping at install step: {}".format(LOG.test_step))


def configure_subcloud(subcloud_controller0_node, main_cloud_node, subcloud='subcloud1',
                       lab=None, final_step=None):
    if lab is None:
        lab = InstallVars.get_install_var("LAB")

    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    test_step = "Configure subcloud"
    LOG.tc_step(test_step)
    if do_step(test_step):

        install_helper.controller_system_config_subcloud(subcloud, main_cloud_node,
                                                         con_telnet=subcloud_controller0_node.telnet_conn, lab=lab,
                                                         close_telnet=False, banner=True, branding=True)

        LOG.info("Auto_info before update: {}".format(Tenant.get('admin', 'RegionOne')))
        if not main_cloud_node.ssh_conn:
            main_cloud_node.ssh_conn = install_helper.ssh_to_controller(
                main_cloud_node.host_ip)
        install_helper.update_auth_url(ssh_con=main_cloud_node.ssh_conn)
        LOG.info("Auto_info after update: {}".format(Tenant.get('admin', 'RegionOne')))

    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        reset_global_vars()
        skip("stopping at install step: {}".format(LOG.test_step))


def bulk_add_hosts(lab=None, con_ssh=None, final_step=None):
    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    if not lab:
        lab = InstallVars.get_install_var('LAB')

    hosts = [host for host in lab["hosts"] if host != 'controller-0']

    if not con_ssh:
        con_ssh = lab["controller-0"].ssh_conn
    test_step = "Bulk add hosts"
    LOG.tc_step(test_step)
    if do_step(test_step):
        rc, added_hosts, msg = install_helper.bulk_add_hosts(lab, "hosts_bulk_add.xml",
                                                             con_ssh=con_ssh)
        assert rc == 0, msg
        LOG.info("system host-bulk-add added: {}".format(added_hosts))
        for host in hosts:
            assert any(host in host_list for host_list in added_hosts), \
                "The host_bulk_add command failed to all hosts {}".format(hosts)

    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))


def boot_hosts(boot_device_dict=None, hostnames=None, lab=None, final_step=None,
               wait_for_online=True):
    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step

    if lab is None:
        lab = InstallVars.get_install_var('LAB')
    if hostnames is None:
        hostnames = [hostname for hostname in lab['hosts'] if 'controller-0' not in hostname]
    use_bmc = InstallVars.get_install_var("USE_BMC")
    test_step = " Wait for mtcAgent to boot" if use_bmc else "Boot"
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
        hosts_online = False
        if not use_bmc:
            LOG.info("Wait for 2 minutes before power on other hosts")
            time.sleep(120)
        else:
            LOG.info("Wait for 2 minutes for mtcAgent to power on hosts: {}".format(hostnames))
            wait_for_mtc_to_power_on_hosts(hostnames, lab=lab)

        for hostname in hostnames:
            threads.append(install_helper.open_vlm_console_thread(hostname, lab=lab,
                                                                  boot_interface=boot_device_dict,
                                                                  wait_for_thread=False,
                                                                  vlm_power_on=True,
                                                                  close_telnet_conn=True))
        for thread in threads:
            thread.join(timeout=InstallTimeout.INSTALL_LOAD)

        if wait_for_online:
            wait_for_hosts_to_be_online(hosts=hostnames, lab=lab, fail_ok=False)
            hosts_online = True

        if InstallVars.get_install_var("DEPLOY_OPENSTACK_FROM_CONTROLLER1") and \
                'controller-1' in hostnames and hosts_online:
            controller0_node = lab['controller-0']
            controller1_node = lab['controller-1']
            if controller1_node.telnet_conn:
                controller1_node.telnet_conn.close()

            controller1_node.telnet_conn = install_helper.open_telnet_session(controller1_node)
            controller1_node.telnet_conn.set_prompt(r'-[\d]+:~\$ ')
            controller1_node.telnet_conn.login(handle_init_login=True)
            controller1_node.telnet_conn.close()

            if not controller0_node.ssh_conn:
                controller0_node.ssh_conn = install_helper.ssh_to_controller(
                    controller0_node.host_ip)

            pre_opts = 'sshpass -p "{0}"'.format(HostLinuxUser.get_password())

            controller0_node.ssh_conn.rsync(HostLinuxUser.get_home() + '*', 'controller-1',
                                            HostLinuxUser.get_home(),
                                            dest_user=HostLinuxUser.get_user(),
                                            dest_password=HostLinuxUser.get_password(),
                                            pre_opts=pre_opts)

    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))


def unlock_hosts(hostnames=None, lab=None, con_ssh=None, final_step=None):
    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    test_step = "Unlock"
    if lab is None:
        lab = InstallVars.get_install_var('LAB')
    lab_hosts = lab['hosts']
    if hostnames is None:
        hostnames = lab_hosts
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
            host_helper.unlock_host(hostnames[0], con_ssh=con_ssh, available_only=available_only,
                                    timeout=2400,
                                    check_hypervisor_up=False, check_webservice_up=False)
            kube_helper.wait_for_nodes_ready(hosts=hostnames, con_ssh=con_ssh,
                                             timeout=HostTimeout.NODES_STATUS_READY)
        else:
            host_helper.unlock_hosts(hostnames, con_ssh=con_ssh, fail_ok=False,
                                     check_nodes_ready=False)

    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))


def run_lab_setup(con_ssh, conf_file=None, final_step=None):

    # lab = InstallVars.get_install_var('LAB')
    # deploy_mgr = use_deploy_manager(lab['controller-0'], lab)

    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    vswitch_type = InstallVars.get_install_var("VSWITCH_TYPE")
    if conf_file is None:
        conf_file = 'lab_setup'

    if vswitch_type in [VSwitchType.OVS_DPDK, VSwitchType.OVS, VSwitchType.NONE] and \
            lab_setup_count == 0:
        if con_ssh.exec_cmd("test -f {}_ovs.conf".format(conf_file))[0] == 0:
            LOG.debug("setting up ovs lab_setup configuration")
            con_ssh.exec_cmd("rm {}.conf; mv {}_ovs.conf {}.conf".format(conf_file,
                                                                         conf_file, conf_file))

        rc, output = con_ssh.exec_cmd("grep \'VSWITCH_TYPE=\' {}.conf".format(conf_file),
                                      fail_ok=True)
        if rc == 0:
            vswitch_type_from_config = output.strip().split('"')[1]
        else:
            vswitch_type_from_config = None

        if vswitch_type_from_config and vswitch_type != vswitch_type_from_config:
            con_ssh.exec_cmd("sed -i \'s/VSWITCH_TYPE=\"{}\"/VSWITCH_TYPE=\"{}\"/g\' {}.conf"
                             .format(vswitch_type_from_config, vswitch_type, conf_file))
        elif not vswitch_type_from_config:
            con_ssh.exec_cmd("echo \'VSWITCH_TYPE=\"{}\"\' >> {}.conf".format(vswitch_type,
                                                                              conf_file))

        if vswitch_type in [VSwitchType.NONE, VSwitchType.OVS]:
            rc, output = con_ssh.exec_cmd("grep \'VSWITCH_PCPU=\' {}.conf".format(conf_file),
                                          fail_ok=True)
            if rc == 0:
                con_ssh.exec_cmd("sed -i \"s/VSWITCH_PCPU=./VSWITCH_PCPU=0/g\" {}.conf".format(
                    conf_file))
            else:
                con_ssh.exec_cmd("echo \'VSWITCH_PCPU=0\' >> {}.conf".format(conf_file))

    test_step = "Run lab setup"
    LOG.tc_step(test_step)
    if do_step(test_step):
        LOG.info("running lab_setup.sh")
        install_helper.run_setup_script(config=True, conf_file=conf_file, con_ssh=con_ssh,
                                        timeout=7200, fail_ok=False)
    if str(str(LOG.test_step)) == final_step or test_step.lower().replace(' ', '_') == final_step:
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
    if str(str(LOG.test_step)) == final_step or test_step.lower().replace(' ', '_') == final_step:
        reset_global_vars()
        skip("stopping at install step: {}".format(LOG.test_step))


def clear_post_install_alarms(con_ssh=None):
    system_helper.wait_for_alarms_gone([("400.001", None), ("800.001", None)], timeout=1800,
                                       check_interval=60,
                                       con_ssh=con_ssh)
    alarm = system_helper.get_alarms(alarm_id='250.001', con_ssh=con_ssh)
    if alarm:
        LOG.tc_step("Swact lock/unlock host")
        rc, msg = host_helper.lock_unlock_controllers()
        assert rc == 0, msg


def attempt_to_run_post_install_scripts(controller0_node=None, final_step=None):

    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    test_step = "Attempt to run post install scripts"
    LOG.tc_step(test_step)
    if do_step(test_step):
        # rc, msg = install_helper.post_install(controller0_node=controller0_node)
        # LOG.info(msg)
        # assert rc >= 0, msg
        reset_global_vars()
    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))


def get_resume_step(lab=None, install_progress_path=None):
    if lab is None:
        lab = ProjVar.get_var("LAB")
    if install_progress_path is None:
        install_progress_path = "{}/../{}_install_progress.txt".format(ProjVar.get_var("LOG_DIR"),
                                                                       lab["short_name"])

    with open(install_progress_path, "r") as progress_file:
        lines = progress_file.readlines()
        for line in lines:
            if "End step:" in line:
                return int(line.split("End step: ")[1].strip()) + 1


def _install_subcloud(subcloud, load_path, build_server, boot_server=None, boot_type='pxe',
                      files_path=None, lab=None,
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
        install_helper.set_network_boot_feed(build_server.ssh_conn, load_path, lab=lab,
                                             boot_server=boot_server)

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

    install_helper.download_license(lab, build_server, license_path=license_path,
                                    dest_name='license')

    subcloud_controller0 = lab['controller-0']
    if subcloud_controller0 and not subcloud_controller0.ssh_conn:
        subcloud_controller0.ssh_conn = install_helper.establish_ssh_connection(
            subcloud_controller0.host_ip)

    LOG.info("Running config for subcloud {} ... ".format(subcloud))
    install_helper.run_config_subcloud(subcloud, con_ssh=subcloud_controller0.ssh_conn)
    end_time = time.time() + 60
    while time.time() < end_time:

        if subcloud in dc_helper.get_subclouds(avail=SubcloudStatus.AVAIL_ONLINE,
                                               mgmt=SubcloudStatus.MGMT_UNMANAGED):
            break

        time.sleep(20)

    else:
        assert False, "The subcloud availability did not reach {} status after config" \
            .format(SubcloudStatus.AVAIL_ONLINE)

    LOG.info(" Subcloud {}  is in {}/{} status ... ".format(subcloud, SubcloudStatus.AVAIL_ONLINE,
                                                            SubcloudStatus.MGMT_UNMANAGED))
    LOG.info("Managing subcloud {} ... ".format(subcloud))
    dc_helper.manage_subcloud(subcloud=subcloud)

    LOG.info("Running config for subcloud {} ... ".format(subcloud))
    short_name = lab['short_name']

    lab_setup_filename_ext = short_name.replace('_', '').lower() if \
        len(short_name.split('_')) <= 1 else \
        short_name.split('_')[0].lower() + short_name.split('_')[1]
    lab_setup_filename = 'lab_setup_s{}_'.format(subcloud.split('-')[1]) + \
                         lab_setup_filename_ext + '.conf'

    LOG.info("Running lab setup config file {} for subcloud {} ... ".format(
        lab_setup_filename, subcloud))

    run_lab_setup(con_ssh=subcloud_controller0.ssh_conn, conf_file=lab_setup_filename)

    LOG.info("Installing license file for subcloud {} ... ".format(subcloud))
    subcloud_license_path = HostLinuxUser.get_home() + "license.lic"
    system_helper.install_license(subcloud_license_path, con_ssh=subcloud_controller0.ssh_conn)

    LOG.info("Unlocking  active controller for subcloud {} ... ".format(subcloud))
    unlock_hosts(hostnames=['controller-0'], con_ssh=subcloud_controller0.ssh_conn)

    subcloud_nodes = get_subcloud_nodes_from_lab_dict(lab)

    LOG.info("Installing other {} hosts ... ".format(subcloud))

    if not files_path:
        system_version = system_version \
            if system_version in BuildServerPath.DEFAULT_LAB_CONFIG_PATH_EXTS else 'default'
        files_path = load_path + '/' + BuildServerPath.DEFAULT_LAB_CONFIG_PATH_EXTS[system_version]

    install_helper.download_hosts_bulk_add_xml_file(lab, build_server, files_path)
    install_helper.bulk_add_hosts(lab, "hosts_bulk_add.xml", con_ssh=subcloud_controller0.ssh_conn)
    boot_device = lab['boot_device_dict']
    hostnames = [node.host_name for node in subcloud_nodes if node.host_name != 'controller-0']
    boot_hosts(boot_device, hostnames=hostnames, wait_for_online=False)
    host_helper.wait_for_hosts_ready(hostnames, con_ssh=subcloud_controller0.ssh_conn.ssh_conn)

    run_lab_setup(con_ssh=subcloud_controller0.ssh_conn, conf_file=lab_setup_filename)
    run_lab_setup(con_ssh=subcloud_controller0.ssh_conn, conf_file=lab_setup_filename)

    unlock_hosts(hostnames=hostnames, con_ssh=subcloud_controller0.ssh_conn)

    run_lab_setup(con_ssh=subcloud_controller0.ssh_conn, conf_file=lab_setup_filename)

    host_helper.wait_for_hosts_ready(hostnames, subcloud_controller0.name,
                                     con_ssh=subcloud_controller0.ssh_conn)

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
        raise ValueError("The distributed cloud system subcloud name must be provided")

    ProjVar.set_var(SOURCE_OPENRC=True)
    if not controller0_node.ssh_conn.is_connected():
        controller0_node.ssh_conn = install_helper.ssh_to_controller(controller0_node.host_ip)

    existing_subclouds = dc_helper.get_subclouds(con_ssh=controller0_node.ssh_conn)
    if name and 'subcloud' in name and name in existing_subclouds:
        LOG.info("Subcloud {} already exits; do nothing".format(name))
        managed = dc_helper.get_subclouds(name=name, avail="managed",
                                          con_ssh=controller0_node.ssh_conn)
        if name in managed:
            LOG.info("Subcloud {} is in managed status; unamanage subcloud before install".
                     format(name))
            dc_helper.manage_subcloud(subcloud=name, con_ssh=controller0_node.ssh_conn)

        return 0, [name]

    subclouds_files = "{}*".format(name)
    subclouds_files_path = HostLinuxUser.get_home() + name[:8] + '-' + name[8:]

    cmd = "test -d {}".format(subclouds_files_path)
    cmd2 = "ls {}/{}".format(subclouds_files_path, subclouds_files)

    if controller0_node.ssh_conn.exec_cmd(cmd)[0] != 0 or controller0_node.ssh_conn.exec_cmd(cmd2)[0] != 0:
        assert False, "The subcloud {} deployment configuration files are missing in system controller {}:{}" \
            .format(name, controller0_node.host_name, subclouds_files_path)

    LOG.info("Getting subclouds deployment config files  from {}".format(subclouds_files_path))
    controller0_node.ssh_conn.exec_cmd("cp {}/{} ./".format(subclouds_files_path, subclouds_files))


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
        "One or more subclouds in {} are not in the system subclouds: {}".format(subclouds,
                                                                                 added_subclouds)

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
                rc, msg = _install_subcloud(subcloud, load_path, build_server, patch_dir=patch_dir,
                                            boot_type=boot_type,
                                            patch_server_conn=patch_server_conn,
                                            lab=dc_lab[subcloud],
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
            subcloud_boots[subcloud_boot[0]] = {'boot': 'pxe',
                                                'boot_server': 'yow-tuxlab2'}
        elif len(subcloud_boot) == 2:
            subcloud_boots[subcloud_boot[0]] = {'boot': subcloud_boot[1],
                                                'boot_server': 'yow-tuxlab2'}
        else:
            subcloud_boots[subcloud_boot[0]] = {'boot': subcloud_boot[1],
                                                'boot_server': subcloud_boot[2]}

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
        controller0_node.ssh_conn = install_helper.ssh_to_controller(controller0_node.host_ip)

    if controller0_node.ssh_conn.is_connected():
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

            LOG.info("System controller {} not  healthy: {}".format(system_controller_lab['name'],
                                                                    health))

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
        controller0_node.ssh_conn = install_helper.ssh_to_controller(controller0_node.host_ip)

    if controller0_node.ssh_conn.is_connected():
        install_helper.update_auth_url(ssh_con=controller0_node.ssh_conn)
        urls = keystone_helper.get_endpoints(field='URL', service_name='sysinv',
                                             service_type='platform', enabled='True',
                                             interface='admin', region='SystemController',
                                             con_ssh=controller0_node.ssh_conn)

        if len(urls) > 0:
            ip_addr = urls[0].strip().split('//')[1].split('/')[0].rsplit(':', 1)[0]
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
        if active_controller_node.ssh_conn:
            LOG.fixture_step("Collect system info")
            con_ssh = active_controller_node.ssh_conn
            con_ssh.connect(retry=True, retry_interval=10, retry_timeout=60)
            con_ssh.flush()
            install_helper.update_auth_url(ssh_con=con_ssh)
            con_ssh.exec_cmd('nslookup www.google.com', get_exit_code=False)
            con_ssh.exec_sudo_cmd('docker pull alpine', get_exit_code=False)
            dm_namespace = con_ssh.exec_cmd("kubectl get namespaces | grep deployment-manager | awk ' { print $1}'")[1]
            if dm_namespace and "deployment" in dm_namespace.strip():
                con_ssh.exec_cmd('kubectl -n {} describe statefulset.apps'.format(dm_namespace), get_exit_code=False,
                                 fail_ok=True)
                con_ssh.exec_cmd('kubectl -n {} describe pods'.format(dm_namespace), fail_ok=True)

            #from keywords import container_helper
            container_helper.get_apps(con_ssh=con_ssh)
            system_helper.get_alarms(con_ssh=con_ssh)
            system_helper.get_build_info(con_ssh=con_ssh)

    except (exceptions.SSHException, exceptions.SSHRetryTimeout, exceptions.SSHExecCommandFailed,
            pexpect.exceptions.TIMEOUT) \
            as e_:
        LOG.error(e_.__str__())
        unreserve_lab_hosts(lab, dist_cloud=dist_cloud)
    unreserve_lab_hosts(lab, dist_cloud=dist_cloud)
    # LOG.fixture_step("unreserving hosts")
    # if dist_cloud:
    #     vlm_helper.unreserve_hosts(vlm_helper.get_hostnames_from_consts(lab['central_region']),
    #                                lab=lab['central_region'])
    #     subclouds = [k for k, v in lab.items() if 'subcloud' in k]
    #     for subcloud in subclouds:
    #         vlm_helper.unreserve_hosts(vlm_helper.get_hostnames_from_consts(lab[subcloud]),
    #                                    lab=lab[subcloud])
    # else:
    #     vlm_helper.unreserve_hosts(vlm_helper.get_hostnames_from_consts(lab))


def setup_fresh_install(lab, dist_cloud=False, subcloud=None):
    skip_list = InstallVars.get_install_var("SKIP")
    active_con = lab["controller-0"] if not dist_cloud else lab['central_region']["controller-0"]

    build_server = InstallVars.get_install_var('BUILD_SERVER')
    build_dir = InstallVars.get_install_var("TIS_BUILD_DIR")
    boot_server = InstallVars.get_install_var('BOOT_SERVER')

    # Initialise server objects
    file_server = InstallVars.get_install_var("FILES_SERVER")
    iso_host = InstallVars.get_install_var("ISO_HOST")
    iso_path = InstallVars.get_install_var("ISO_PATH")
    helm_chart_server = InstallVars.get_install_var("HELM_CHART_SERVER")
    patch_server = InstallVars.get_install_var("PATCH_SERVER")
    guest_server = InstallVars.get_install_var("GUEST_SERVER")

    servers = list({file_server, iso_host, patch_server, guest_server, helm_chart_server})

    LOG.fixture_step("Establishing connection to {}".format(servers))

    servers_map = {server_: setups.initialize_server(server_) for server_ in servers}
    bs_obj = servers_map.get(build_server)
    file_server_obj = servers_map.get(file_server, bs_obj)
    dc_float_ip = None
    install_sub = None
    system_controller_obj = None
    if subcloud:
        dc_float_ip = InstallVars.get_install_var("DC_FLOAT_IP")
        install_sub = InstallVars.get_install_var("INSTALL_SUBCLOUD")
        dc_lab = setups.get_dc_lab(lab)
        system_controller_obj = Node(host_ip=dc_float_ip, host_name='controller-0')
        ssh_from_tuxlab2 = True if common.get_ip_version(dc_float_ip) == 6 else False
        system_controller_obj.ssh_conn = install_helper.establish_ssh_connection(system_controller_obj.host_ip,
                                                                                 ssh_from_tuxlab2=ssh_from_tuxlab2)
        dc_ipv6 = InstallVars.get_install_var("DC_IPV6")
        v6 = True if ssh_from_tuxlab2 else is_dcloud_system_controller_ipv6(file_server_obj)

        if not v6:
            if dc_ipv6:
                LOG.warning("The DC System controller is configured as IPV4; Switching to IPV4")
                dc_ipv6 = False
        else:
            LOG.warning("The DC System controller is configured as IPV6; "
                        "Configuring subcloud {} as IPV6".format(install_sub))
            dc_ipv6 = True
        InstallVars.set_install_var(dc_ipv6=dc_ipv6)
        add_subclouds(system_controller_obj, name=install_sub, ip_ver=6 if dc_ipv6 else 4)
        servers_map['dc_system_controller'] = system_controller_obj
        InstallVars.set_install_var(system_controller=system_controller_obj)
        InstallVars.set_install_var(dc_lab=dc_lab)
        LOG.info("Instal DC lab  = {}".format(InstallVars.get_install_var('DC_LAB')['name']))
    ProjVar.set_var(SOURCE_OPENRC=True)
    bmc_config_server = servers_map.get(file_server, bs_obj)
    bmc_info = get_bmc_info(lab, bmc_config_server,
                            subcloud=InstallVars.get_install_var("INSTALL_SUBCLOUD") if subcloud else None)
    lab['bmc_info'] = bmc_info
    check_bmc_config(lab=lab)
    LOG.info("Lab bmc info  = {}".format(InstallVars.get_install_var("LAB")['bmc_info']))


    boot_type = InstallVars.get_install_var("BOOT_TYPE")
    if "usb" in boot_type:
        # check if oam nic is set
        controller0_node = lab['controller-0'] if not dist_cloud else lab['central_region']['controller-0']
        if not controller0_node.host_nic:
            controller0_node.host_nic = install_helper.get_nic_from_config(conf_server=file_server_obj)

    servers = {
        "build": bs_obj,
        "lab_files": file_server_obj,
        "patches": servers_map.get(patch_server, bs_obj),
        "guest": servers_map.get(guest_server, bs_obj),
        "helm_charts": servers_map.get(helm_chart_server, bs_obj)
    }
    iso_host_obj = servers_map.get(iso_host, bs_obj)

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
                      "active_controller": active_con,
                      "dc_system_controller": system_controller_obj}

    if subcloud and install_sub:
        _install_setup['install_subcloud'] = install_sub
        _install_setup['dc_float_ip'] = dc_float_ip

    if not InstallVars.get_install_var("RESUME") and "0" not in skip_list and "setup" not in skip_list:
        LOG.fixture_step("Setting up {} boot".format(boot["boot_type"]))
        lab_dict = lab if not dist_cloud else (lab['central_region'] if not subcloud else lab[subcloud])

        if "burn" in boot["boot_type"]:
            install_helper.burn_image_to_usb(iso_host_obj, lab_dict=lab_dict)

        elif "pxe_iso" in boot["boot_type"] and 'feed' not in skip_list:
            install_helper.rsync_image_to_boot_server(iso_host_obj, lab_dict=lab_dict)
            install_helper.mount_boot_server_iso(lab_dict=lab_dict)

        elif 'iso_feed' in boot["boot_type"] and 'feed' not in skip_list:
            skip_cfg = "pxeboot" in skip_list
            install_helper.set_up_feed_from_boot_server_iso(iso_host_obj, lab_dict=lab_dict, iso_path=iso_path,
                                                            skip_cfg=skip_cfg)

        elif 'feed' in boot["boot_type"] and 'feed' not in skip_list:
            load_path = directories["build"]
            skip_cfg = "pxeboot" in skip_list
            set_default_manu = True if "grizzly" in lab["controller-0"].host_name else False
            LOG.fixture_step("Need to set default menu {}".format(set_default_manu))
            install_helper.set_network_boot_feed(bs_obj.ssh_conn, load_path, lab=lab_dict, skip_cfg=skip_cfg,
                                                 set_default_manu=set_default_manu)

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


def verify_install_uuid(lab=None, final_step=None):
    if lab is None:
        lab = InstallVars.get_install_var("LAB")

    controller0_node = lab['controller-0']

    if not controller0_node.ssh_conn:
        controller0_node.ssh_conn = install_helper.ssh_to_controller(controller0_node.host_ip)

    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    test_step = "Verify install uuid"
    LOG.tc_step(test_step)
    if do_step(test_step):

        LOG.info("Getting the install uuid from controller-0")
        install_uuid = install_helper.get_host_install_uuid(controller0_node.name,
                                                            controller0_node.ssh_conn)
        LOG.info("The install uuid from controller-0 = {}".format(install_uuid))

        LOG.info("Verify all hosts have the same install uuid {}".format(install_uuid))
        hosts = lab['hosts']
        try:
            hosts.remove('controller-0')
        except ValueError:
            pass
        for host in hosts:
            with host_helper.ssh_to_host(host) as host_ssh:
                host_install_uuid = install_helper.get_host_install_uuid(host, host_ssh)
                assert host_install_uuid == install_uuid, \
                    "The host {} install uuid {} is not same with controller-0 " \
                    "uuid {}".format(host, host_install_uuid, install_uuid)
                LOG.info("Host {} install uuid verified".format(host))
        LOG.info("Installation UUID {} verified in all lab hosts".format(install_uuid))

    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))

    return True


def send_arp_cmd(lab=None):

    if lab is None:
        lab = InstallVars.get_install_var("LAB")

    controller0_node = lab['controller-0']

    if not controller0_node.ssh_conn:
        controller0_node.ssh_conn = install_helper.ssh_to_controller(controller0_node.host_ip)

    fip = lab.get("floating ip")

    if fip:
        setups.arp_for_fip(lab, controller0_node.ssh_conn)


def wait_for_hosts_ready(hosts, lab=None, timeout=2400):
    """

    Args:
        hosts:
        lab:
        timeout (int)

    Returns:

    """
    if lab is None:
        lab = InstallVars.get_install_var("LAB")

    controller0_node = lab['controller-0']

    if not controller0_node.ssh_conn:
        controller0_node.ssh_conn = install_helper.ssh_to_controller(controller0_node.host_ip)

    fip = lab.get("floating ip")
    if fip:
        LOG.info("Checking floating ip: {} connectivity  ...".format(fip))
        source_ip = NatBoxes.NAT_BOX_HW['ip']
        NATBoxClient.set_natbox_client(source_ip)
        nat_conn = NATBoxClient.get_natbox_client(source_ip)

        try:
            fip_ssh = SSHFromSSH(ssh_client=nat_conn, host=fip, user=HostLinuxUser.get_user(),
                                 password=HostLinuxUser.get_password())
            fip_ssh.connect(retry=True, retry_timeout=60, timeout=15)
            fip_ssh.close()
        except:
            LOG.warning('Failed to ping lab fip from natbox')
            LOG.warning("No connectivity using floating ip {}; attempting to resolve fip "
                        "connectivity ...".format(fip))
            setups.arp_for_fip(lab, controller0_node.ssh_conn)

        nat_conn.close()

    kube_helper.wait_for_nodes_ready(hosts, con_ssh=controller0_node.ssh_conn, timeout=timeout)


def wait_for_hosts_to_be_online(hosts, lab=None, fail_ok=True):
    """

    Args:
        hosts:
        lab:
        fail_ok:

    Returns:

    """
    if lab is None:
        lab = InstallVars.get_install_var("LAB")

    controller0_node = lab['controller-0']

    if not controller0_node.ssh_conn:
        controller0_node.ssh_conn = install_helper.ssh_to_controller(controller0_node.host_ip)
    if InstallVars.get_install_var("INSTALL_SUBCLOUD"):
        deploy_mgr = True
    else:
        deploy_mgr = use_deploy_manager(controller0_node, lab=lab)

    LOG.info("Verifying {} is Locked, Disabled and Online ...".format(hosts))
    if not deploy_mgr:
        system_helper.wait_for_hosts_states(hosts, check_interval=10,
                                            con_ssh=controller0_node.ssh_conn,
                                            administrative=HostAdminState.LOCKED,
                                            operational=HostOperState.DISABLED,
                                            availability=HostAvailState.ONLINE, fail_ok=fail_ok)
    else:
        end_time = time.time() + HostTimeout.REBOOT
        while time.time() < end_time:

            LOG.info("Verifying {} to be online ...")

            offline_hosts = kube_helper.get_resources(field=['NAME', 'AVAILABILITY', 'INSYNC'],
                                                      namespace='deployment', resource_type='hosts',
                                                      con_ssh=controller0_node.ssh_conn,
                                                      availability='offline')
            if not offline_hosts:
                LOG.info("Waiting for hosts {} to become online".format(offline_hosts))
                time.sleep(20)
            else:
                return
        else:
            msg = "Timed out waiting for {}  in online state"
            LOG.warning(msg)
            raise exceptions.HostTimeout(msg)


def wait_for_deployed_hosts_ready(hosts, lab=None, final_step=None):
    """
    Waiting for deployed hosts to be ready.
    Args:
        hosts:
        lab:

    Returns:

    """
    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    test_step = "Wait for deployed hosts ready"
    LOG.tc_step(test_step)
    if do_step(test_step):
        wait_for_hosts_ready(hosts, lab=lab)

    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))


def wait_for_deploy_mgr_controller_config(controller0_node, lab=None, fail_ok=False, final_step=None):
    """

    Args:
        controller0_node:
        lab:
        fail_ok:

    Returns:

    """
    if lab is None:
        lab = InstallVars.get_install_var("LAB")

    if controller0_node is None:
        controller0_node = lab['controller-0']
    subcloud = InstallVars.get_install_var("INSTALL_SUBCLOUD")
    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    test_step = "Wait for Deployment Mgr to configure active controller"
    LOG.tc_step(test_step)
    if do_step(test_step):
        if subcloud:
            system_controller_node = InstallVars.get_install_var("SYSTEM_CONTROLLER")

            dc_helper.wait_for_subcloud_status(subcloud, avail=SubcloudStatus.AVAIL_ONLINE,
                                               mgmt=SubcloudStatus.MGMT_UNMANAGED, timeout=DCTimeout.SUBCLOUD_CONFIG,
                                               con_ssh=system_controller_node.ssh_conn)

            LOG.info(" Subcloud {}  is in {}/{} status ... ".format(
                subcloud, SubcloudStatus.AVAIL_ONLINE, SubcloudStatus.MGMT_UNMANAGED))
            if controller0_node.ssh_conn is None:
                controller0_node.ssh_conn = install_helper.ssh_to_controller(controller0_node.host_ip)
            else:
                controller0_node.ssh_conn.connect(retry=True, retry_timeout=120)
            ControllerClient.set_active_controller(controller0_node.ssh_conn)
        else:

            host_helper._wait_for_simplex_reconnect(con_ssh=controller0_node.ssh_conn,
                                                    timeout=HostTimeout.CONTROLLER_UNLOCK)

        LOG.info("Verifying for controller-0 to be online ...")
        end_time = time.time() + HostTimeout.REBOOT
        while time.time() < end_time:
            available_host = kube_helper.get_resources(field=['NAME', 'AVAILABILITY', 'INSYNC'],
                                                       namespace='deployment',
                                                       resource_type='hosts',
                                                       con_ssh=controller0_node.ssh_conn,
                                                       name='controller-0', availability='available')

            # if not available_host or ('true' not in available_host[0]):
            if not available_host:
                LOG.info("Waiting for controller-0 to become available and true: {}"
                         .format(list(available_host[0]) if available_host else available_host))
                time.sleep(20)
            else:
                LOG.info("The controller-0 is available and insync: {}".format(
                    list(available_host[0])))
                return
        else:
            sys_values = system_helper.get_system_values(fields=["system_mode", "system_type"],
                                                         con_ssh=controller0_node.ssh_conn)
            if "All-in-one" in sys_values and 'duplex' in sys_values[0]:
                current_avail = kube_helper.get_resources(field=['NAME', 'AVAILABILITY', 'INSYNC'],
                                                          namespace='deployment',
                                                          resource_type='hosts',
                                                          con_ssh=controller0_node.ssh_conn,
                                                          name='controller-0',
                                                          availability=['degraded', 'available'])
                if current_avail:
                    LOG.info("The controller-0 is degraded/available and insync: {}".format(
                        list(current_avail)))
                    return

            msg = "Timed out waiting for controller-0  to become available state after deployment"
            if fail_ok:
                LOG.warning(msg)
                return False
            raise exceptions.HostTimeout(msg)

    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))


def wait_for_subcloud_to_be_managed(subcloud, dc_system_controller, lab=None, final_step=None):
    """

    Args:
        subcloud:
        dc_system_controller:
        lab:

    Returns:

    """

    if lab is None:
        lab = InstallVars.get_install_var("LAB")

    controller0_node = lab['controller-0']

    if not controller0_node.ssh_conn:
        controller0_node.ssh_conn = install_helper.ssh_to_controller(controller0_node.host_ip)

    if dc_system_controller.ssh_conn is not None:
        if not dc_system_controller.ssh_conn.is_connected():
            dc_system_controller.ssh_conn.connect()
    else:
        dc_system_controller.ssh_conn = install_helper.ssh_to_controller(dc_system_controller.host_ip)

    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    test_step = "Wait for subcloud to be managed"
    LOG.tc_step(test_step)
    if do_step(test_step):

        if dc_helper.get_subcloud_status(subcloud, field='management', con_ssh=dc_system_controller.ssh_conn) == \
                SubcloudStatus.MGMT_UNMANAGED:

            dc_helper.wait_for_subcloud_status(subcloud, avail=SubcloudStatus.AVAIL_ONLINE,
                                               mgmt=SubcloudStatus.MGMT_UNMANAGED,
                                               con_ssh=dc_system_controller.ssh_conn)

            LOG.info(" Subcloud {}  is in {}/{} status ... ".format(
                subcloud, SubcloudStatus.AVAIL_ONLINE, SubcloudStatus.MGMT_UNMANAGED))

        no_manage = InstallVars.get_install_var("NO_MANAGE")
        if not no_manage:
            LOG.info("Managing subcloud {} ... ".format(subcloud))
            LOG.info("Auto_info before manage: {}".format(Tenant.get('admin', 'RegionOne')))
            install_helper.update_auth_url(ssh_con=dc_system_controller.ssh_conn)
            dc_helper.manage_subcloud(subcloud=subcloud, con_ssh=dc_system_controller.ssh_conn,
                                      fail_ok=True)

            dc_helper.wait_for_subcloud_status(subcloud, avail=SubcloudStatus.AVAIL_ONLINE,
                                               mgmt=SubcloudStatus.MGMT_MANAGED,
                                               sync=SubcloudStatus.SYNCED,
                                               timeout=DCTimeout.SUBCLOUD_MANAGE,
                                               con_ssh=dc_system_controller.ssh_conn)

    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))


def get_host_ceph_osd_devices_from_conf(active_controller_node, host, conf_file='lab_setup.conf'):
    """

    Args:
        active_controller_node:
        host:
        conf_file:

    Returns:

    """

    if not active_controller_node.ssh_conn:
        active_controller_node.ssh_conn = install_helper.ssh_to_controller(
            active_controller_node.host_ip)

    devices_pci = []
    rc, output = active_controller_node.ssh_conn.exec_cmd("grep OSD_DEVICES {}".format(conf_file))
    if rc == 0 and output:
        lines = output.splitlines()
        host_line = None
        common_line = None
        for line in lines:
            if host.upper().replace('-', '') in line:
                host_line = line.split('=')[1].replace('\"', '').strip()
            elif line.startswith("OSD_DEVICES"):
                common_line = line.split('=')[1].replace('\"', '').strip()
            else:
                pass
        osd_devices = host_line if host_line else common_line
        if osd_devices:
            osd_devices = osd_devices.split(' ')
            for osd_dev in osd_devices:
                devices_pci.append(osd_dev.split('|')[0].strip())

    LOG.info("OSD disks for host {} are {}".format(host, devices_pci))

    return devices_pci


def add_ceph_ceph_mon_to_host(active_controller_node, host, final_step=None):
    """

    Args:
        active_controller_node
        host
        final_step

    Returns:

    """
    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    if not active_controller_node.ssh_conn:
        active_controller_node.ssh_conn = install_helper.ssh_to_controller(
            active_controller_node.host_ip)
    test_step = "adding ceph mon to {}".format(host)
    LOG.tc_step(test_step)
    if do_step(test_step):
        storage_helper.add_ceph_mon(host, con_ssh=active_controller_node.ssh_conn)
        LOG.info("Added ceph mon to host {} ...".format(host))
        active_controller_node.ssh_conn.exec_cmd(
            "touch {}/.lab_setup.done.group0.ceph-mon".format(
                HostLinuxUser.get_home()))
    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))


def add_ceph_osds_to_controller(lab=None, conf_file='lab_setup.conf', final_step=None):
    """

    Args:
        lab:
        conf_file:
        final_step

    Returns:

    """
    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    if lab is None:
        lab = InstallVars.get_install_var("LAB")

    controller0_node = lab['controller-0']
    controller1_node = lab['controller-1']
    floating_ip = lab.get('floating ip')

    active_node_ssh = install_helper.ssh_to_controller(floating_ip, fail_ok=True)
    if not active_node_ssh:
        active_node_ssh = install_helper.ssh_to_controller(controller0_node.host_ip)

    ControllerClient.set_active_controller(active_node_ssh)
    test_step = "add ceph osds to controllers"
    LOG.tc_step(test_step)
    if do_step(test_step):

        controller0_disk_paths = get_host_ceph_osd_devices_from_conf(controller0_node,
                                                                     controller0_node.name)
        controller1_disk_paths = get_host_ceph_osd_devices_from_conf(controller0_node,
                                                                     controller1_node.name)
        assert len(controller0_disk_paths) > 0 and len(controller1_disk_paths) > 0, \
            "Unable to find OSD devices from conf file {} for the controllers".format(conf_file)

        if system_helper.is_active_controller(controller0_node.name, con_ssh=active_node_ssh):
            hosts = [controller1_node.name, controller0_node.name]
            active_node = controller0_node
        else:
            hosts = [controller0_node.name, controller1_node.name]
            active_node = controller1_node

        tier_uuid = storage_helper.get_storage_tiers("ceph_cluster", con_ssh=active_node_ssh)

        for host in hosts:
            LOG.info("Adding ceph osd to {} ..".format(host))
            if not host_helper.is_host_locked(host, con_ssh=active_node_ssh):
                host_helper.lock_host(host, con_ssh=active_node_ssh)

            disk_paths = controller1_disk_paths if host == 'controller-1' else \
                controller0_disk_paths

            for disk_path in disk_paths:
                disk_uuid = storage_helper.get_host_disks(host, device_path=disk_path,
                                                          con_ssh=active_node_ssh)[0]
                storage_helper.add_host_storage(host, disk_uuid, tier_uuid=tier_uuid[0],
                                                con_ssh=active_node_ssh)

            LOG.info("Unlocking host {} after adding ceph osds ..".format(host))
            host_helper.unlock_host(host, con_ssh=active_node_ssh, check_containers=False)
            host_helper.swact_host(active_node.name, con_ssh=active_node_ssh)
            active_node = lab[host]
            active_node_ssh.close()
            active_node_ssh = install_helper.ssh_to_controller(floating_ip)
            ControllerClient.set_active_controller(active_node_ssh)

        storage_helper.wait_for_ceph_health_ok()

    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))


def apply_node_labels(hosts, active_controller_node):
    """

    Args:
        hosts:
        active_controller_node:

    Returns:

    """
    if not active_controller_node:
        raise ValueError("Active controller node object must be provided")
    if not active_controller_node.ssh_conn:
        active_controller_node.ssh_conn = install_helper.ssh_to_controller(
            active_controller_node.host_ip)

    if isinstance(hosts, str):
        hosts = [hosts]
    if "controller-0" in hosts:
        hosts.remove('controller-0')
    cmd = "host-label-assign {}"
    for host in hosts:
        LOG.info("Applying node label for host {}".format(host))
        if "controller" not in host:
            cli.system(cmd.format(host), "openstack-compute-node=enabled",
                       ssh_client=active_controller_node.ssh_conn)
            cli.system(cmd.format(host), "openvswitch=enabled",
                       ssh_client=active_controller_node.ssh_conn)
            cli.system(cmd.format(host), "sriov=enabled",
                       ssh_client=active_controller_node.ssh_conn)
        else:
            cli.system(cmd.format(host), "openstack-control-plane=enabled",
                       ssh_client=active_controller_node.ssh_conn)


def collect_lab_config_yaml(lab, server, stage=DEPLOY_LAST, final_step=None):
    """

    Args:
        lab:
        server
        stage:
        final_step

    Returns:

    """

    # if not InstallVars.get_install_var("EXTRACT_DEPLOY_CONFIG"):
    #     return 0

    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step

    if lab is None:
        lab = InstallVars.get_install_var("LAB")

    controller0_node = lab['controller-0']
    lab_name = lab['name']
    if not controller0_node.ssh_conn:
        controller0_node.ssh_conn = install_helper.ssh_to_controller(controller0_node.host_ip)
    ControllerClient.set_active_controller(controller0_node.ssh_conn)
    deploy_mgr = use_deploy_manager(controller0_node, lab)
    deploy_tool_full_path = HostLinuxUser.get_home() + DEPLOY_TOOL

    test_step = "collect lab configuration {}".format(stage)
    LOG.tc_step(test_step)
    if do_step(test_step) and not deploy_mgr:

        cmd = "test -f {}".format(deploy_tool_full_path)
        err_msg = ''
        if controller0_node.ssh_conn.exec_cmd(cmd)[0] != 0:
            # download deploy tool

            pre_opts = 'sshpass -p "{0}"'.format(HostLinuxUser.get_password())

            rc, output = server.ssh_conn.rsync(DEPLOY_SOUCE_PATH + DEPLOY_TOOL,
                                               controller0_node.host_ip,
                                               HostLinuxUser.get_home(),
                                               dest_user=HostLinuxUser.get_user(),
                                               dest_password=HostLinuxUser.get_password(),
                                               pre_opts=pre_opts,
                                               fail_ok=True)
            if rc != 0:
                err_msg = err_msg + output
            run_deploy = True if rc == 0 else False
            if run_deploy:
                controller0_node.ssh_conn.exec_cmd("mkdir -p {}deploy_yaml_files".format(
                    HostLinuxUser.get_home()))
        else:
            run_deploy = True

        if run_deploy and controller0_node.ssh_conn.exec_cmd(cmd)[0] == 0:
            controller0_node.ssh_conn.exec_cmd("chmod 777 {}".format(deploy_tool_full_path))
        else:
            LOG.warning("The deploy script  is missing in  controller-0: {}".format(err_msg))

        cmd2 = None
        if run_deploy:
            if stage == DEPLOY_INTITIAL:
                cmd1 = "{} build -s {} -o {}_initial.yaml".format(deploy_tool_full_path,
                                                                  lab_name, lab_name)
            elif stage == DEPLOY_INTERIM:
                cmd1 = "{} build -s {} -o {}_before.yaml".format(deploy_tool_full_path,
                                                                 lab_name, lab_name)
            else:
                cmd1 = "{} build -s {} -o {}.yaml --minimal-config".format(deploy_tool_full_path,
                                                                           lab_name, lab_name)
                cmd2 = "{} build -s {} -o {}_full.yaml".format(deploy_tool_full_path, lab_name,
                                                               lab_name)

            if cmd1:
                rc, output = controller0_node.ssh_conn.exec_cmd(
                    "source /etc/platform/openrc; " + cmd1)
                if rc != 0:
                    LOG.warning("The deploy command {} failed: {}".format(cmd1, output))
            if cmd2:
                rc, output = controller0_node.ssh_conn.exec_cmd(
                    "source /etc/platform/openrc; " + cmd2)
                if rc != 0:
                    LOG.warning("The deploy command {} failed: {}".format(cmd2, output))

            # check if yaml files are generated:
            yaml_files = "{}{}_*.yaml".format(HostLinuxUser.get_home(), lab_name)
            last_file = "{}{}.yaml".format(HostLinuxUser.get_home(), lab_name)
            cmd = "ls {}".format(yaml_files)
            unfiltered_dest_results_path = DEPLOY_RESULTS_DEST_PATH + "unfiltered/"
            if controller0_node.ssh_conn.exec_cmd(cmd)[0] == 0:
                if not server.server_ip:
                    rc, server_ip = server.ssh_conn.exec_cmd("hostname -i")
                    if rc == 0:
                        server.server_ip = server_ip.strip()
                pre_opts = 'sshpass -p "{0}"'.format(TestFileServer.get_password())
                rc, output = controller0_node.ssh_conn.rsync(yaml_files, server.server_ip,
                                                             unfiltered_dest_results_path,
                                                             dest_user=TestFileServer.get_user(),
                                                             dest_password=TestFileServer.get_password(),
                                                             extra_opts=["--chmod=Fugo=rw"],
                                                             pre_opts=pre_opts, fail_ok=True)
                if rc != 0:
                    LOG.warning("Fail to copy {} to  destination {}:{}".format(
                        yaml_files, server.name, unfiltered_dest_results_path))
                else:
                    controller0_node.ssh_conn.exec_cmd("mv {} {}deploy_yaml_files/".format(
                        yaml_files, HostLinuxUser.get_home()))
            if stage == DEPLOY_LAST:
                cmd = "ls {}".format(last_file)
                if controller0_node.ssh_conn.exec_cmd(cmd)[0] == 0:
                    if not server.server_ip:
                        rc, server_ip = server.ssh_conn.exec_cmd("hostname -i")
                        if rc == 0:
                            server.server_ip = server_ip.strip()

                    pre_opts = 'sshpass -p "{0}"'.format(TestFileServer.get_password())
                    rc, output = controller0_node.ssh_conn.rsync(
                        last_file, server.server_ip,
                        DEPLOY_RESULTS_DEST_PATH,
                        dest_user=TestFileServer.get_user(),
                        dest_password=TestFileServer.get_password(),
                        extra_opts=["--chmod=Fugo=rw"],
                        pre_opts=pre_opts, fail_ok=True)
                    if rc != 0:
                        LOG.warning("Fail to copy {} to  destination {}:{}".format(
                            last_file, server.name, DEPLOY_RESULTS_DEST_PATH))
                    else:
                        controller0_node.ssh_conn.exec_cmd("mv {} {}deploy_yaml_files/".format(
                            last_file, HostLinuxUser.get_home()))

    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))


def check_ansible_configured_mgmt_interface(controller0_node, lab):
    """

    Args:
        controller0_node:
        lab:

    Returns:

    """
    host = 'controller-0'
    if controller0_node.telnet_conn is None:
        controller0_node.telnet_conn = install_helper.open_telnet_session(controller0_node)

    ansible = True if controller0_node.telnet_conn.exec_cmd(
        "test -f {}localhost.yml".format(HostLinuxUser.get_home()),
        fail_ok=True)[0] == 0 else False
    simplex = install_helper.is_simplex(lab)
    if ansible and not simplex:
        LOG.info("LAB uses ansible and removing the lo mgmt interface in controller-0 if "
                 "present; ")
        controller0_node.telnet_conn.exec_cmd("system host-if-modify {} lo -c none".format(host),
                                              fail_ok=True)


def use_deploy_manager(controller0_node, lab):

    if "DEPLOY_MGR" in InstallVars.get_install_vars().keys():
        return InstallVars.get_install_var("DEPLOY_MGR")

    if lab is None:
        lab = InstallVars.get_install_var("LAB")
    if controller0_node.telnet_conn is None:
        controller0_node.telnet_conn = install_helper.open_telnet_session(controller0_node)
    deploy_config_file = "deployment-config.yaml"
    # deploy_config_file_2 = "{}.yaml".format(lab['name'])

    # cmd = "test -f {}{}".format(HostLinuxUser.get_home(), deploy_config_file_2)
    cmd = "test -f {}{}".format(HostLinuxUser.get_home(), deploy_config_file)
    deploy_mgr = True if controller0_node.telnet_conn.exec_cmd(cmd, fail_ok=True)[0] == 0 else False
    InstallVars.set_install_var(deploy_mgr=deploy_mgr)
    return deploy_mgr


def use_ansible(controller0_node):

    if "ANSIBLE_CONFIG" in InstallVars.get_install_vars().keys():
        return InstallVars.get_install_var("ANSIBLE_CONFIG")

    if controller0_node.telnet_conn is None:
        controller0_node.telnet_conn = install_helper.open_telnet_session(controller0_node)
    local_host_file = "localhost.yml"
    ansible_config = True if controller0_node.telnet_conn.exec_cmd(
        "test -f {}{}".format(HostLinuxUser.get_home(), local_host_file), fail_ok=True)[0] == 0 \
        else False
    InstallVars.set_install_var(ansible_config=ansible_config)
    return ansible_config


def wait_for_deployment_mgr_to_bulk_add_hosts(lab=None, final_step=None, fail_ok=False):

    if not lab:
        lab = InstallVars.get_install_var('LAB')

    hosts_ = [host for host in lab["hosts"] if host != 'controller-0']

    con_ssh = lab["controller-0"].ssh_conn
    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    test_step = "Wait for Deployment Mgr to bulk add hosts"
    LOG.tc_step(test_step)
    if do_step(test_step):
        LOG.info("Verifying {} are bulk added  ...".format(hosts_))
        end_time = time.time() + 60
        while time.time() < end_time:
            added_hosts = kube_helper.get_resources(namespace='deployment', resource_type='hosts',
                                                    con_ssh=con_ssh,
                                                    name=hosts_)
            if not added_hosts or any(host for host in hosts_ if host not in added_hosts):
                LOG.info("Waiting for {} to be bulk added by Deployment Mgr"
                         .format([host for host in hosts_ if host not in added_hosts]))
                time.sleep(20)
            else:
                LOG.info("All hosts are bulk added by Deployment Mgr: {}".format(added_hosts))
                return
        else:
            msg = "Timed out waiting for hosts: {} to be bulk added by Deployment Mgr".format(
                hosts_)
            if fail_ok:
                LOG.warning(msg)
                return False
            raise exceptions.HostTimeout(msg)

    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))


def validate_deployment_mgr_install(controller0_node, lab):

    if not lab:
        lab = InstallVars.get_install_var('LAB')

    hosts = lab["hosts"]
    lab_name = lab['name']
    if not controller0_node:
        controller0_node = lab['controller-0']

    if not controller0_node.ssh_conn:
        controller0_node.ssh_conn = install_helper.ssh_to_controller(
            controller0_node.host_ip)
    ControllerClient.set_active_controller(controller0_node.ssh_conn)
    con_ssh = controller0_node.ssh_conn
    test_step = "Validate Deployment Mgr install"
    LOG.tc_step(test_step)
    if do_step(test_step):
        LOG.info("Verifying Deployment Mgr install  ...")

        added_hosts = kube_helper.get_resources(field=['NAME', 'AVAILABILITY', 'INSYNC'],
                                                namespace='deployment',
                                                resource_type='hosts', con_ssh=con_ssh,
                                                name=hosts, insync='true')

        if len(added_hosts) < len(hosts):
            not_completed = [host for host in hosts if host not in [host_state[0] for
                                                                    host_state in added_hosts]]

            msg = "Hosts {} are not in available and insync state.".format(not_completed)
            LOG.warning(msg)
        else:
            LOG.info("All hosts are in available  and insync state: {}".format(added_hosts))

        system_info = kube_helper.get_resources(field=['NAME', 'MODE', 'TYPE', 'INSYNC'],
                                                namespace='deployment',
                                                resource_type='systems', con_ssh=con_ssh,
                                                insync='true')

        if system_info and lab_name.replace('-', '_') == \
                list(system_info[0])[0].replace('-', '_') and (list(system_info[0])[3] == 'true'):

            LOG.info("Lab system: {} validated".format(system_info))
        else:
            msg = "Lab system info not as expected: {}".format(system_info)
            LOG.warning(msg)

        data_net_info = kube_helper.get_resources(field=['NAME', 'INSYNC'], namespace='deployment',
                                                  resource_type='datanetworks', con_ssh=con_ssh)

        if not data_net_info or any(data_info for data_info in data_net_info if 'true' not in
                                                                                data_info):
            msg = "All Data networks are not insyc : {}".format(data_net_info)
            LOG.warning(msg)


def wait_for_deploy_mgr_lab_config(controller0_node, lab=None, fail_ok=False):

    test_step = "Wait for Deployment Mgr to configure other hosts"
    LOG.tc_step(test_step)
    if do_step(test_step):

        wait_for_deploy_mgr_hosts_config(controller0_node, lab=lab, fail_ok=fail_ok)
        wait_for_deploy_mgr_data_networks_config(controller0_node, lab=lab, timeout=30,
                                                 fail_ok=fail_ok)
        wait_for_deploy_mgr_system_config(controller0_node, lab=lab, timeout=1800, fail_ok=fail_ok)


def wait_for_deploy_mgr_hosts_config(controller0_node, lab=None, fail_ok=False):
    """

    Args:
        controller0_node:
        lab:
        fail_ok:

    Returns:

    """

    if lab is None:
        lab = InstallVars.get_install_var("LAB")

    if controller0_node is None:
        controller0_node = lab['controller-0']
    hosts = [host for host in lab['hosts'] if host != 'controller-0']

    if not controller0_node.ssh_conn:
        controller0_node.ssh_conn = install_helper.ssh_to_controller(
            controller0_node.host_ip, fail_ok=True)
        ControllerClient.set_active_controller(controller0_node.ssh_conn)

    LOG.info("Waiting for Deploy Mgr to configure and unlock hosts: {}  ...".format(hosts))
    no_of_hosts_configured = 0
    debug_msg = "Waiting for {} to become availability=available and insync=true: {}"
    end_time = time.time() + HostTimeout.INSTALL_LOAD
    while time.time() < end_time:
        hosts_states = kube_helper.get_resources(field=['NAME', 'AVAILABILITY', 'INSYNC'],
                                                 namespace='deployment',
                                                 resource_type='hosts',
                                                 con_ssh=controller0_node.ssh_conn,
                                                 name=hosts, insync='true')

        if not hosts_states or any(host for host in hosts if host not in [host_state[0] for
                                                                          host_state in hosts_states]):
            if len(hosts_states) > no_of_hosts_configured:
                LOG.info(debug_msg.format(hosts, list(hosts_states)))
                no_of_hosts_configured = len(hosts_states)
            else:
                LOG.debug(debug_msg.format(hosts, list(hosts_states)))

            time.sleep(20)
        else:
            LOG.info("All hosts are in available state and insync: {}".format(hosts_states))
            return
    else:
        msg = "Timed out waiting for {} to become in available state and insync".format(hosts)
        if fail_ok:
            LOG.warning(msg)
            return False
        raise exceptions.HostTimeout(msg)


def wait_for_deploy_mgr_system_config(controller0_node, lab=None, timeout=1800, fail_ok=False):
    """

    Args:
        controller0_node:
        lab:
        timeout:
        fail_ok:

    Returns:

    """

    if lab is None:
        lab = InstallVars.get_install_var("LAB")

    if controller0_node is None:
        controller0_node = lab['controller-0']
    lab_name = lab['name']

    if not controller0_node.ssh_conn:
        controller0_node.ssh_conn = install_helper.ssh_to_controller(
            controller0_node.host_ip, fail_ok=True)
        ControllerClient.set_active_controller(controller0_node.ssh_conn)

    LOG.info("Waiting for Deploy Mgr to configure {} system  ...".format(lab_name))

    end_time = time.time() + timeout
    while time.time() < end_time:

        system_state = kube_helper.get_resources(field=['NAME', 'INSYNC'], namespace='deployment',
                                                 resource_type='system',
                                                 con_ssh=controller0_node.ssh_conn,
                                                 insync='true')

        if not system_state:
            time.sleep(10)
        else:
            LOG.info("{} system insync: {}".format(lab_name, system_state))
            return
    else:
        msg = "Timed out waiting for {} system to become in available state and insync".format(
            lab_name)
        if fail_ok:
            LOG.warning(msg)
            return False
        raise exceptions.HostTimeout(msg)


def wait_for_deploy_mgr_data_networks_config(controller0_node, lab=None, timeout=30,
                                             fail_ok=False):
    """

    Args:
        controller0_node:
        lab:
        timeout:
        fail_ok:

    Returns:

    """

    if lab is None:
        lab = InstallVars.get_install_var("LAB")

    if controller0_node is None:
        controller0_node = lab['controller-0']

    if not controller0_node.ssh_conn:
        controller0_node.ssh_conn = install_helper.ssh_to_controller(
            controller0_node.host_ip, fail_ok=True)
        ControllerClient.set_active_controller(controller0_node.ssh_conn)

    configured_data_nets = system_helper.get_data_networks(con_ssh=controller0_node.ssh_conn)
    LOG.info("Waiting for Deploy Mgr to configure {} data networks ...".format(
        configured_data_nets))

    end_time = time.time() + timeout

    while time.time() < end_time:

        d_states = kube_helper.get_resources(field=['NAME', 'INSYNC'], namespace='deployment',
                                             resource_type='datanetworks',
                                             con_ssh=controller0_node.ssh_conn,
                                             name=configured_data_nets, insync='true')

        if not d_states or any(p for p in configured_data_nets if p not in [d_state[0] for d_state in d_states]):
            time.sleep(10)
        else:
            LOG.info("{} datanetworks insync: {}".format(configured_data_nets, d_states))
            return
    else:
        msg = "Timed out waiting for {} data networks to become insync".format(configured_data_nets)
        if fail_ok:
            LOG.warning(msg)
            return False
        raise exceptions.HostTimeout(msg)


def wait_for_deploy_mgr_platform_networks_config(controller0_node, lab=None, timeout=30,
                                                 fail_ok=False):
    """

    Args:
        controller0_node:
        lab:
        timeout:
        fail_ok:

    Returns:

    """

    if lab is None:
        lab = InstallVars.get_install_var("LAB")

    if controller0_node is None:
        controller0_node = lab['controller-0']

    if not controller0_node.ssh_conn:
        controller0_node.ssh_conn = install_helper.ssh_to_controller(controller0_node.host_ip,
                                                                     fail_ok=True)
        ControllerClient.set_active_controller(controller0_node.ssh_conn)

    configured_data_nets = system_helper.get_data_networks(con_ssh=controller0_node.ssh_conn)
    LOG.info("Waiting for Deploy Mgr to configure {} data networks ...".format(
        configured_data_nets))

    end_time = time.time() + timeout

    while time.time() < end_time:

        p_states = kube_helper.get_resources(field=['NAME', 'INSYNC'], namespace='deployment',
                                             resource_type='platformnetworks',
                                             con_ssh=controller0_node.ssh_conn,
                                             insync='true')

        if not p_states:
            time.sleep(10)
        else:
            LOG.info("platform networks insync: {}".format(configured_data_nets, p_states))
            return
    else:
        msg = "Timed out waiting for platform networks to become insync"
        if fail_ok:
            LOG.warning(msg)
            return False
        raise exceptions.HostTimeout(msg)


def restore_wait_for_hosts_to_be_online(hosts, lab=None, fail_ok=True):
    """

    Args:
        hosts:
        lab:
        fail_ok:

    Returns:

    """
    if lab is None:
        lab = InstallVars.get_install_var("LAB")

    controller0_node = lab['controller-0']

    if not controller0_node.ssh_conn:
        controller0_node.ssh_conn = install_helper.ssh_to_controller(controller0_node.host_ip)

    LOG.info("Verifying {} is Locked, Disabled and Online ...".format(hosts))
    system_helper.wait_for_hosts_states(hosts, check_interval=10,
                                        con_ssh=controller0_node.ssh_conn,
                                        administrative=HostAdminState.LOCKED,
                                        operational=HostOperState.DISABLED,
                                        availability=HostAvailState.ONLINE, fail_ok=fail_ok)


def restore_boot_hosts(boot_device_dict=None, hostnames=None, lab=None, final_step=None, wait_for_online=True):
    """

    Args:
        boot_device_dict:
        hostnames:
        lab:
        final_step:
        wait_for_online:

    Returns:

    """
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
        hosts_online = False
        for hostname in hostnames:
            threads.append(install_helper.open_vlm_console_thread(hostname, lab=lab,
                                                                  boot_interface=boot_device_dict,
                                                                  wait_for_thread=False,
                                                                  vlm_power_on=True,
                                                                  close_telnet_conn=True))
        for thread in threads:
            thread.join(timeout=InstallTimeout.INSTALL_LOAD)

        if wait_for_online:
            restore_wait_for_hosts_to_be_online(hosts=hostnames, lab=lab, fail_ok=False)
            hosts_online = True

        if InstallVars.get_install_var("DEPLOY_OPENSTACK_FROM_CONTROLLER1") and \
                'controller-1' in hostnames and hosts_online:
            controller0_node = lab['controller-0']
            controller1_node = lab['controller-1']
            if controller1_node.telnet_conn:
                controller1_node.telnet_conn.close()

            controller1_node.telnet_conn = install_helper.open_telnet_session(controller1_node)
            controller1_node.telnet_conn.set_prompt(r'-[\d]+:~\$ ')
            controller1_node.telnet_conn.login(handle_init_login=True)
            controller1_node.telnet_conn.close()

            if not controller0_node.ssh_conn:
                controller0_node.ssh_conn = install_helper.ssh_to_controller(
                    controller0_node.host_ip)

            pre_opts = 'sshpass -p "{0}"'.format(HostLinuxUser.get_password())

            controller0_node.ssh_conn.rsync(HostLinuxUser.get_home() + '*', 'controller-1',
                                            HostLinuxUser.get_home(),
                                            dest_user=HostLinuxUser.get_user(),
                                            dest_password=HostLinuxUser.get_password(),
                                            pre_opts=pre_opts)

    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))


def unreserve_lab_hosts(lab, dist_cloud=False):

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


def get_bmc_info(lab, conf_server=None, lab_file_dir=None, subcloud=None):
    if lab is None:
        lab = InstallVars.get_install_var("LAB")

    if not lab_file_dir:
        lab_file_dir = InstallVars.get_install_var("LAB_SETUP_PATH")
    if subcloud:
        lab_file_dir = "{}/{}".format(lab_file_dir, subcloud[:-1] + '-' + subcloud[-1:])

    if not os.path.isabs(lab_file_dir):
        raise ValueError("Abs path required for {}".format(lab_file_dir))

    lab_name = lab['name']
    lab_name = lab_name.split('yow-', maxsplit=1)[-1]

    lab_bmc_info = {}
    LOG.info("Getting lab config file from specified path: {}".format(lab_file_dir))
    cmd = "test -e " + lab_file_dir
    if conf_server and conf_server.ssh_conn.exec_cmd(cmd, rm_date=False, fail_ok=True)[0] == 0:
        vswitch_type = InstallVars.get_install_var("VSWITCH_TYPE")
        dm_file = "{}-deploy-standard.yaml".format(subcloud) if subcloud \
            else ("deployment-config.yaml" if vswitch_type == 'none' else "deployment-config_avs.yaml")

        dm_file_path = "{}/{}".format(lab_file_dir, dm_file)
        cmd = "test -e {}".format(dm_file_path)
        if conf_server.ssh_conn.exec_cmd(cmd, rm_date=False)[0] == 0:
            try:

                with pysftp.Connection(host=conf_server.name, username=TestFileServer.get_user(),
                                       password=TestFileServer.get_password()) as sftp:
                    dm_file = sftp.open(dm_file_path)
                    docs = yaml.load_all(dm_file)
                    for document in docs:
                        if document:
                            if document['kind'] == 'Secret' and document['metadata']['name'] == 'bmc-secret':
                                lab_bmc_info['username'] = base64.b64decode(document['data']['username']).decode()
                                lab_bmc_info['password'] = base64.b64decode(document['data']['password']).decode()
                            elif document['kind'] == 'Host':
                                if 'boardManagement' in document['spec']['overrides']:
                                    lab_bmc_info[document['metadata']['name']] = \
                                        document['spec']['overrides']['boardManagement']['address']

            except IOError as e:
                LOG.info("Fail to open  deployment-config file {} for lab {}: {}".format(lab_file_dir, lab_name, e.message))
        else:
            LOG.info("No deployment-config file exist for lab {} in specified path: {}".format(lab_name, dm_file_path))

    return lab_bmc_info


def check_bmc_config(lab):
    if lab is None:
        lab = InstallVars.get_install_var("LAB")
    bmc_info = lab.get("bmc_info")
    bmc_ok = []
    #use_bmc = install_helper.use_bmc(lab['hosts'], lab=lab)
    use_bmc = False
    if "username" in bmc_info and "password" in bmc_info:
        bmc_hosts = [host for host in lab["hosts"] if host in bmc_info]
        if len(bmc_hosts) > 0:
            LOG.info("Using BMC to power on/off hosts; Ensure BMC hosts {} are VLM powered on ...".format(bmc_hosts))
            vlm_helper.power_on_hosts(bmc_hosts, post_check=False)
            time.sleep(60)
            test_client = install_helper.test_server_client()
            for host in bmc_hosts:
                code, output = test_client.ping_server(bmc_info[host], fail_ok=True)
                if code != 0:
                    msg = 'Unable to ping BMC address {} from Test Server: {}'.format(bmc_info[host], output)
                    LOG.info(msg)
                    use_bmc = False
                else:
                    bmc_ok.append(host)
            if "controller-0" in bmc_ok:
                use_bmc = True

    bmc_info['bmc_ok'] = bmc_ok
    lab["bmc_info"] = bmc_info

    # if not use_bmc:
    #     lab["bmc_info"].clear()

    InstallVars.set_install_var(lab=lab)
    InstallVars.set_install_var(use_bmc=use_bmc)


def wait_for_mtc_to_power_on_hosts(hosts, lab=None, timeout=120, fail_ok=False):
    """
    Waits for mtcAgent to power on hosts
    Args:
        hosts:
        lab:
        timeout:
        fail_ok:

    Returns:

    """
    if lab is None:
        lab = InstallVars.get_install_var("LAB")

    if isinstance(hosts, str):
        hosts = [hosts]
    powered_on_hosts = []
    end_time = time.time() + timeout
    while time.time() < end_time:

        for host in hosts:
            status, output = install_helper.get_bmc_power_status(host, lab=lab, fail_ok=True)
            if status == 'on':
                LOG.info("The mtcAgent has power on {}: {}".format(host, output))
                if host not in powered_on_hosts:
                    powered_on_hosts.append(host)

        if len(powered_on_hosts) == len(hosts):
            LOG.info("The mtcAgent has power on all hosts: {}".format(powered_on_hosts))
            return 0, None
        else:
            time.sleep(30)
    else:
        msg = "Timed out waiting for mtcAgent to power on hosts {};  powered on hosts: {}".format(hosts, powered_on_hosts)
        if fail_ok:
            LOG.warning(msg)
            return False
        raise exceptions.HostTimeout(msg)


def wait_for_platform_integ_app_applied(controller0_node, lab=None, fail_ok=False, final_step=None):
    """

    Args:
        controller0_node:
        lab:
        fail_ok:
        final_step:

    Returns:

    """
    if lab is None:
        lab = InstallVars.get_install_var("LAB")

    if controller0_node is None:
        controller0_node = lab['controller-0']

    final_step = InstallVars.get_install_var("STOP") if not final_step else final_step
    test_step = "Wait for platform integ app applied"
    LOG.tc_step(test_step)
    if do_step(test_step):
        container_helper.wait_for_apps_status(apps='platform-integ-apps', timeout=1800,
                                              con_ssh=controller0_node.ssh_conn, status='applied', fail_ok=fail_ok)
    if str(LOG.test_step) == final_step or test_step.lower().replace(' ', '_') == final_step:
        skip("stopping at install step: {}".format(LOG.test_step))

