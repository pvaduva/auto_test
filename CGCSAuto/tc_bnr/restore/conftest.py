import pytest
import setups
from consts.proj_vars import InstallVars, RestoreVars
from keywords import vlm_helper
from testfixtures.pre_checks_and_configs import *
from utils import node


########################
# Command line options #
########################

def pytest_configure(config):
    # Lab install params
    lab = config.getoption('lab')
    use_usb = config.getoption('use_usb')
    backup_src_path = config.getoption('backup_path')
    backup_build_id = config.getoption('backup_build_id')
    backup_src = 'USB' if use_usb else 'local'
    skip_setup_feed = config.getoption('skip_setup_feed')
    skip_reinstall = config.getoption('skip_reinstall')
    low_latency = config.getoption('low_latency')
    cinder_backup = config.getoption('cinder_backup')
    build_server = config.getoption('build_server')

    backup_builds_dir = config.getoption('backup_builds_dir')
    build_server = config.getoption('build_server')
    tis_build_dir = config.getoption('tis_build_dir')

    setups.set_install_params(lab=lab, skip_labsetup=None, resume=None, installconf_path=None,
                              controller0_ceph_mon_device=None, controller1_ceph_mon_device=None, ceph_mon_gib=None)
    RestoreVars.set_restore_vars(backup_src=backup_src, backup_src_path=backup_src_path,
                                 backup_build_id=backup_build_id,  backup_builds_dir=backup_builds_dir, build_server=build_server)

    RestoreVars.set_restore_var(skip_setup_feed=skip_setup_feed)
    RestoreVars.set_restore_var(skip_reinstall=skip_reinstall)
    RestoreVars.set_restore_var(low_latency=low_latency)
    RestoreVars.set_restore_var(cinder_backup=cinder_backup)

    ProjVar.set_var(always_collect=True)
    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.get('admin'))


def pytest_runtest_teardown(item):
    lab = InstallVars.get_install_var('LAB')
    hostnames = [k for k, v in lab.items() if isinstance(v, node.Node)]
    vlm_helper.unreserve_hosts(hostnames)
    con_ssh = ControllerClient.get_active_controller(lab['short_name'])
    # Delete any backup files from /opt/backups
    con_ssh.exec_sudo_cmd("rm -rf /opt/backups/*")
    con_ssh.flush()


@pytest.fixture(scope='session', autouse=True)
def setup_test_session(global_setup):
    """
    Setup primary tenant  before the first test gets executed.
    TIS ssh was already set up at collecting phase.
    """
    global con_ssh

    ProjVar.set_var(PRIMARY_TENANT=Tenant.get('admin'))
    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.get('admin'))
    setups.setup_primary_tenant(ProjVar.get_var('PRIMARY_TENANT'))

    con_ssh = setups.setup_tis_ssh(InstallVars.get_install_var("LAB"))
    ControllerClient.set_active_controller(ssh_client=con_ssh)

    # set build id to be used to upload/write test results
    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.get('admin'))

    setups.get_build_info(con_ssh)
    setups.set_session(con_ssh=con_ssh)


@pytest.fixture(scope='session', autouse=True)
def setup_build_vars(request):
    """
    Setup primary tenant  before the first test gets executed.
    TIS ssh was already set up at collecting phase.
    """

    def set_build_vars():
        try:
            con_ssh = ControllerClient.get_active_controller()
            setups.setup_primary_tenant(ProjVar.get_var('PRIMARY_TENANT'))
            setups.copy_test_files()

            # set build id to be used to upload/write test results
            setups.get_build_info(con_ssh)
        except:
            LOG.warning('Unable to set BUILD info')
            pass

    set_build_vars()
    request.addfinalizer(set_build_vars)

