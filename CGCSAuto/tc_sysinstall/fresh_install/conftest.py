import pytest
import os
import re

from keywords import install_helper, vlm_helper
from keywords.network_helper import reset_telnet_port
from utils.tis_log import LOG
from consts.lab import get_lab_dict
from consts.proj_vars import InstallVars, ProjVar
from consts.filepaths import TuxlabServerPath, BuildServerPath
from setups import initialize_server, write_installconf, set_install_params, get_lab_dict
from tc_sysinstall.fresh_install import fresh_install_helper
from utils import exceptions

########################
# Command line options #
########################


def pytest_configure(config):

    # Lab fresh_install params
    lab_arg = config.getoption('lab')
    resume_install = config.getoption('resumeinstall')
    skiplist = config.getoption('skiplist')
    wipedisk = config.getoption('wipedisk')
    controller0_ceph_mon_device = config.getoption('ceph_mon_dev_controller_0')
    controller1_ceph_mon_device = config.getoption('ceph_mon_dev_controller_1')
    ceph_mon_gib = config.getoption('ceph_mon_gib')
    install_conf = config.getoption('installconf')
    lab_file_dir = config.getoption('file_dir')
    build_server = config.getoption('build_server')
    boot_server = config.getoption('boot_server')
    tis_build_dir = config.getoption('tis_build_dir')
    tis_builds_dir = config.getoption('tis_builds_dir')
    install_license = config.getoption('upgrade_license')
    heat_templates = config.getoption('heat_templates')
    guest_image = config.getoption('guest_image_path')
    boot_type = config.getoption('boot_list')
    iso_path = config.getoption('iso_path')
    low_lat = config.getoption('low_latency')
    security = config.getoption('security')
    controller = config.getoption('controller')
    compute = config.getoption('compute')
    storage = config.getoption('storage')
    stop_step = config.getoption('stop_step')
    drop_num = config.getoption('drop_num')
    patch_dir = config.getoption('patch_dir')
    ovs = config.getoption('ovs_config')
    kubernetes = config.getoption('kubernetes_config')

    if lab_arg:
        lab_dict = get_lab_dict(lab_arg)
        lab_name = lab_dict['name']
        if 'yow' in lab_name:
            lab_name = lab_name[4:]
        else:
            lab_dict = None
            lab_name = None
    else:
        raise ValueError("Lab name must be provided")

    if resume_install is True:
        resume_install = fresh_install_helper.get_resume_step(lab_dict)
        LOG.info("Resume Install step at {}".format(resume_install))

    if not install_conf:
        build_server = build_server if build_server else BuildServerPath.DEFAULT_BUILD_SERVER
        if not tis_builds_dir and not tis_build_dir:
            host_build_dir_path = BuildServerPath.DEFAULT_HOST_BUILD_PATH
        elif tis_build_dir and os.path.isabs(tis_build_dir):
            host_build_dir_path = tis_build_dir
        else:
            tis_builds_dir = tis_builds_dir if tis_builds_dir else ''
            tis_build_dir = tis_build_dir if tis_build_dir else BuildServerPath.LATEST_BUILD
            host_build_dir_path = os.path.join(BuildServerPath.DEFAULT_WORK_SPACE, tis_builds_dir, tis_build_dir)

        files_server = build_server
        if lab_file_dir:
            if lab_file_dir.find(":/") != -1:
                files_server = lab_file_dir[:lab_file_dir.find(":/")]
                lab_file_dir = lab_file_dir[lab_file_dir.find(":") + 1:]
        else:
            lab_file_dir = "{}/lab/yow/{}".format(host_build_dir_path, lab_name if lab_name else '')

        if not heat_templates or not os.path.isabs(heat_templates):
            heat_templates = os.path.join(BuildServerPath.DEFAULT_HOST_BUILD_PATH, BuildServerPath.HEAT_TEMPLATES)

        install_conf = write_installconf(lab=lab_arg, controller=controller, compute=compute, storage=storage,
                                         lab_files_dir=lab_file_dir, patch_dir=patch_dir,
                                         tis_build_dir=host_build_dir_path,
                                         build_server=build_server, files_server=files_server,
                                         license_path=install_license, guest_image=guest_image,
                                         heat_templates=heat_templates, boot=boot_type, iso_path=iso_path,
                                         security=security, low_latency=low_lat, stop=stop_step, ovs=ovs,
                                         boot_server=boot_server, resume=resume_install, skip=skiplist,
                                         kubernetes=kubernetes)

    set_install_params(lab=lab_arg, skip=skiplist, resume=resume_install, wipedisk=wipedisk, drop=drop_num,
                       installconf_path=install_conf, controller0_ceph_mon_device=controller0_ceph_mon_device,
                       controller1_ceph_mon_device=controller1_ceph_mon_device, ceph_mon_gib=ceph_mon_gib,
                       boot=boot_type, iso_path=iso_path, security=security, low_latency=low_lat, stop=stop_step,
                       patch_dir=patch_dir, ovs=ovs, boot_server=boot_server, kubernetes=kubernetes)

    frame_str = '*'*len('Install Arguments:')
    print("\n{}\nInstall Arguments:\n{}\n".format(frame_str, frame_str))
    install_vars = InstallVars.get_install_vars()
    bs = install_vars['BUILD_SERVER']
    for var, value in install_vars.items():
        if (not value and value != 0) or (value == bs and var != 'BUILD_SERVER'):
            continue
        elif var == 'LAB':
            for k, v in dict(value).items():
                if re.search('_nodes| ip', k):
                    print("{:<20}: {}".format(k, v))
        else:
            print("{:<20}: {}".format(var, value))
    print("{:<20}: {}".format('LOG_DIR', ProjVar.get_var('LOG_DIR')))
    print('')


@pytest.fixture(scope='session')
def install_setup(request):
    lab = InstallVars.get_install_var("LAB")
    subclouds = []
    dist_cloud = InstallVars.get_install_var("DISTRIBUTED_CLOUD")
    if dist_cloud:
        subclouds.extend([k for k in lab if 'subcloud' in k])
        central_lab = lab['central_region']
        vlm_helper.get_hostnames_from_consts(central_lab)
        lab['central_region']['hosts'] = vlm_helper.get_hostnames_from_consts(central_lab)
        barcodes = vlm_helper.get_barcodes_from_hostnames(lab['central_region']["hosts"], lab=central_lab)

        for subcloud in subclouds:
            lab[subcloud]["hosts"] = vlm_helper.get_hostnames_from_consts(lab[subcloud])
            barcodes.extend(vlm_helper.get_barcodes_from_hostnames(lab[subcloud]["hosts"], lab=lab[subcloud]))
    else:
        lab["hosts"] = vlm_helper.get_hostnames_from_consts(lab)
        barcodes = vlm_helper.get_barcodes_from_hostnames(lab["hosts"])

    skip_list = InstallVars.get_install_var("SKIP")
    active_con = lab["controller-0"] if not dist_cloud else lab['central_region']["controller-0"]
    install_type = ProjVar.get_var('SYS_TYPE')

    LOG.tc_setup_start("{} install".format(install_type))
    LOG.fixture_step("Reserve hosts")

    if dist_cloud:
        hosts = {'central_region': lab['central_region']['hosts']}
        for subcloud in subclouds:
            hosts[subcloud] = lab[subcloud]["hosts"]
    else:
        hosts = lab["hosts"]
    LOG.info("Unreservering {}".format(hosts))
    if not dist_cloud:
        vlm_helper.force_unreserve_hosts(hosts)
    else:
        vlm_helper.force_unreserve_hosts(barcodes, val="barcodes")

    LOG.info("Reservering {}".format(hosts))
    for barcode in barcodes:
        vlm_helper._reserve_vlm_console(barcode, "AUTO: lab installation")

    LOG.info("Attempt to reset port on controller-0")
    if active_con.telnet_conn is None:
        active_con.telnet_conn = install_helper.open_telnet_session(active_con)
        try:
            reset_telnet_port(active_con.telnet_conn)
        except (exceptions.TelnetException, exceptions.TelnetEOF, exceptions.TelnetTimeout):
            pass

    def install_teardown():
        LOG.fixture_step("Unreserving hosts")
        if dist_cloud:
            vlm_helper.unreserve_hosts(vlm_helper.get_hostnames_from_consts(lab['central_region']),
                                       lab=lab['central_region'])
            subclouds = [k for k, v in lab.items() if 'subcloud' in k]
            for subcloud_ in subclouds:
                vlm_helper.unreserve_hosts(vlm_helper.get_hostnames_from_consts(lab[subcloud_]),
                                           lab=lab[subcloud_])
        else:
            vlm_helper.unreserve_hosts(vlm_helper.get_hostnames_from_consts(lab))

        try:
            active_con.telnet_conn.flush()
            active_con.telnet_conn.login(handle_init_login=True)
            output = active_con.telnet_conn.exec_cmd("cat /etc/build.info", fail_ok=True, get_exit_code=False)[1]
            LOG.info(output)
        except (exceptions.TelnetException, exceptions.TelnetEOF, exceptions.TelnetTimeout) as e_:
            LOG.error(e_.__str__())
    request.addfinalizer(install_teardown)

    build_server = InstallVars.get_install_var('BUILD_SERVER')
    build_dir = InstallVars.get_install_var("TIS_BUILD_DIR")

    # Initialise server objects
    file_server = InstallVars.get_install_var("FILES_SERVER")
    iso_host = InstallVars.get_install_var("ISO_HOST")
    patch_server = InstallVars.get_install_var("PATCH_SERVER")
    guest_server = InstallVars.get_install_var("GUEST_SERVER")
    servers = list({file_server, iso_host, patch_server, guest_server})
    LOG.fixture_step("Establish connection to {}".format(servers))

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
    elif patch_server:
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
        LOG.fixture_step("Set up {} boot".format(boot["boot_type"]))
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
            LOG.fixture_step("Attempt to wipe disks")
            try:
                active_con.telnet_conn.login()
                if dist_cloud:
                    install_helper.wipe_disk_hosts(lab['central_region']["hosts"], lab=lab['central_region'])
                else:
                    install_helper.wipe_disk_hosts(lab["hosts"])
            except exceptions.TelnetException as e:
                LOG.error("Failed to wipedisks because of telnet exception: {}".format(e.message))

    return _install_setup


def pytest_runtest_teardown(item):
    install_testcases = ["test_simplex_install.py", "test_duplex_install.py", "test_standard_install.py",
                         "test_storage_install.py", "test_distributed_cloud_install.py"]
    for install_testcase in install_testcases:
        if install_testcase in item.nodeid:
            final_step = LOG.test_step
            lab = InstallVars.get_install_var("LAB")
            progress_dir = ProjVar.get_var("LOG_DIR") + "/.."
            progress_file_path = progress_dir + "/{}_install_progress.txt".format(lab["short_name"])

            LOG.info("Writing install step to {}".format(progress_file_path))
            with open(progress_file_path, "w+") as progress_file:
                progress_file.write(item.nodeid + "\n")
                progress_file.write("End step: {}".format(str(final_step)))

            os.chmod(progress_file_path, 0o755)
            break
