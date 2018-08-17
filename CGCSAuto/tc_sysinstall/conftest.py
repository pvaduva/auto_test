import pytest
import os

import setups
from consts.auth import CliAuth, Tenant
from consts.proj_vars import ProjVar, InstallVars
from utils.clients.ssh import SSHClient


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

    if not install_conf:
        install_conf = setups.write_installconf(lab=lab_arg, controller=controller, compute=compute, storage=storage,
                                                lab_files_dir=lab_file_dir, patch_dir=patch_dir,
                                                tis_build_dir=tis_build_dir, build_server=build_server,
                                                license_path=install_license, guest_image=guest_image,
                                                heat_templates=heat_templates, boot=boot_type, iso_path=iso_path,
                                                security=security, low_latency=low_lat, stop=stop_step, ovs=ovs,
                                                boot_server=boot_server, resume=resume_install, skip=skiplist)

    setups.set_install_params(lab=lab_arg, skip=skiplist, resume=resume_install, wipedisk=wipedisk, drop=drop_num,
                              installconf_path=install_conf, controller0_ceph_mon_device=controller0_ceph_mon_device,
                              controller1_ceph_mon_device=controller1_ceph_mon_device, ceph_mon_gib=ceph_mon_gib,
                              boot=boot_type, iso_path=iso_path, security=security, low_latency=low_lat, stop=stop_step,
                              patch_dir=patch_dir, ovs=ovs, boot_server=boot_server)
    print(" Pre Configure Install vars: {}".format(InstallVars.get_install_vars()))


#@pytest.fixture(scope='session', autouse=True)
#def setup_test_session(global_setup):
#    """
#    Setup primary tenant and Nax Box ssh before the first test gets executed.
#    TIS ssh was already set up at collecting phase.
#    """
#    print("SysInstall test session ..." )
#    ProjVar.set_var(PRIMARY_TENANT=Tenant.ADMIN)
#    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.ADMIN)
#    setups.setup_primary_tenant(ProjVar.get_var('PRIMARY_TENANT'))
    # con_ssh.set_prompt()
#    setups.set_env_vars(con_ssh)
#    setups.copy_test_files()
    # con_ssh.set_prompt()

#    global natbox_ssh
#    natbox = ProjVar.get_var('NATBOX')
#    if natbox['ip'] == 'localhost':
#        natbox_ssh = 'localhost'
#    else:
#        natbox_ssh = setups.setup_natbox_ssh(ProjVar.get_var('KEYFILE_PATH'), natbox, con_ssh=con_ssh)
    # setups.boot_vms(ProjVar.get_var('BOOT_VMS'))

    # set build id to be used to upload/write test results
#    build_id, build_server, job = setups.get_build_info(con_ssh)
#    ProjVar.set_var(BUILD_ID=build_id)
#    ProjVar.set_var(BUILD_SERVER=build_server)
#    ProjVar.set_var(JOB=job)
#    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.ADMIN)

#    setups.set_session(con_ssh=con_ssh)


