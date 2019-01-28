import os
import re

from utils.tis_log import LOG
from utils.node import Node
from consts.proj_vars import InstallVars, ProjVar
from consts.filepaths import BuildServerPath, WRSROOT_HOME
from setups import write_installconf, set_install_params, get_lab_dict, is_lab_subcloud
from tc_sysinstall.fresh_install import fresh_install_helper

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
    no_openstack_install = config.getoption('no_openstack_install')

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

    is_subcloud, sublcoud_name, dc_float_ip = is_lab_subcloud(lab_dict)

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

        if sublcoud_name and not lab_file_dir:
            lab_file_dir = "{}:{}{}".format(dc_float_ip, WRSROOT_HOME, sublcoud_name)
            files_server = Node(host_ip=dc_float_ip, host_name='controller-0')

        if lab_file_dir:
            if lab_file_dir.find(":/") != -1:
                files_server = lab_file_dir[:lab_file_dir.find(":/")]
                lab_file_dir = lab_file_dir[lab_file_dir.find(":") + 1:]
        else:
            lab_file_dir = "{}/lab/yow/{}".format(host_build_dir_path, lab_name if lab_name else '')

        if not heat_templates:
            heat_templates = os.path.join(host_build_dir_path, BuildServerPath.HEAT_TEMPLATES)
        elif not os.path.isabs(heat_templates):
            heat_templates = os.path.join(host_build_dir_path, heat_templates)

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
                           patch_dir=patch_dir, ovs=ovs, boot_server=boot_server, dc_float_ip=dc_float_ip,
                           install_subcloud=sublcoud_name, kubernetes=kubernetes,
                           no_openstack_install=no_openstack_install)

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
