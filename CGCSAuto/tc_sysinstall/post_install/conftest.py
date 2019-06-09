import pytest

import setups
from consts.auth import CliAuth, Tenant
from consts.proj_vars import ProjVar, InstallVars


########################
# Command line options #
########################

def pytest_configure(config):

    # Lab fresh_install params
    lab_arg = config.getoption('lab')
    controller0_ceph_mon_device = config.getoption('ceph_mon_dev_controller_0')
    controller1_ceph_mon_device = config.getoption('ceph_mon_dev_controller_1')
    ceph_mon_gib = config.getoption('ceph_mon_gib')
    build_server = config.getoption('build_server')
    boot_server = config.getoption('boot_server')
    patch_dir = config.getoption('patch_dir')

    setups.set_install_params(installconf_path=None, lab=lab_arg,
                              controller0_ceph_mon_device=controller0_ceph_mon_device,
                              controller1_ceph_mon_device=controller1_ceph_mon_device,
                              ceph_mon_gib=ceph_mon_gib,
                              patch_dir=patch_dir,
                              build_server=build_server, boot_server=boot_server)
    print(" Pre Configure Install vars: {}".format(InstallVars.get_install_vars()))
    print("")


@pytest.fixture(scope='session', autouse=True)
def setup_test_session(global_setup):
    """
    Setup primary tenant and Nax Box ssh before the first test gets executed.
    TIS ssh was already set up at collecting phase.
    """
    ProjVar.set_var(SOURCE_OPENRC=True)
    setups.copy_test_files()

    global natbox_ssh
    natbox = ProjVar.get_var('NATBOX')
    natbox_ssh = setups.setup_natbox_ssh(natbox)

    # set build id to be used to upload/write test results
    setups.set_build_info(con_ssh)
    setups.set_session(con_ssh=con_ssh)


def pytest_collectstart():
    """
    Set up the ssh session at collectstart. Because skipif condition is evaluated at the collecting test cases phase.
    """
    global con_ssh
    lab = ProjVar.get_var("LAB")
    if 'vbox' in lab['short_name']:
        con_ssh = setups.setup_vbox_tis_ssh(lab)
    else:
        con_ssh = setups.setup_tis_ssh(lab)
    ProjVar.set_var(con_ssh=con_ssh)
    CliAuth.set_vars(**setups.get_auth_via_openrc(con_ssh))
    Tenant.set_region(region=CliAuth.get_var('OS_REGION_NAME'))
    Tenant.set_platform_url(url='OS_AUTH_URL')


def pytest_runtest_teardown():
    # print('')
    # message = 'Teardown started:'
    # testcase_log(message, item.nodeid, log_type='tc_teardown')
    con_ssh.connect(retry=True, retry_interval=3, retry_timeout=300)
    con_ssh.flush()
    if natbox_ssh:
        natbox_ssh.flush()
        natbox_ssh.connect(retry=False)
