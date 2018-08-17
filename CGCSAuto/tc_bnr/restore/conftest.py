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
    lab_arg = config.getoption('lab')
    use_usb = config.getoption('use_usb')
    backup_src_path = config.getoption('backup_path')
    backup_build_id = config.getoption('backup_build_id')
    backup_builds_dir = config.getoption('backup_builds_dir')
    backup_src = 'USB' if use_usb else 'local'
    skip_setup_feed = config.getoption('skip_setup_feed')
    skip_reinstall = config.getoption('skip_reinstall')
    low_latency = config.getoption('low_latency')

    setups.set_install_params(lab=lab_arg, skip_labsetup=None, resume=None, installconf_path=None,
                              controller0_ceph_mon_device=None, controller1_ceph_mon_device=None, ceph_mon_gib=None)
    RestoreVars.set_restore_vars(backup_src=backup_src, backup_src_path=backup_src_path,
                                 backup_build_id=backup_build_id,  backup_builds_dir=backup_builds_dir)

    RestoreVars.set_restore_var(skip_setup_feed=skip_setup_feed)
    RestoreVars.set_restore_var(skip_reinstall=skip_reinstall)
    RestoreVars.set_restore_var(low_latency=low_latency)

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
    request.addfinalizer(set_build_vars)
