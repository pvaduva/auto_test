import re
import time

from pytest import fixture, skip

from consts.auth import Tenant
from consts.cgcs import EventLogID, HostAvailState, AppStatus
from consts.filepaths import HeatTemplate
from consts.proj_vars import ProjVar, PatchingVars
from consts.reasons import SkipSysType
from keywords import system_helper, host_helper, keystone_helper, security_helper, container_helper, common, kube_helper
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG


@fixture(scope='function')
def stx_openstack_required(request):
    app_name = 'stx-openstack'
    if not container_helper.is_stx_openstack_deployed(applied_only=True):
        skip('stx-openstack application is not applied')

    def wait_for_recover():

        post_status = container_helper.get_apps(application=app_name)[0]
        if not post_status == AppStatus.APPLIED:
            LOG.info("Dump info for unhealthy pods")
            kube_helper.dump_pods_info()

            if not post_status.endswith('ed'):
                LOG.fixture_step("Wait for application apply finish")
                container_helper.wait_for_apps_status(apps=app_name, status=AppStatus.APPLIED, timeout=3600,
                                                      check_interval=15, fail_ok=False)
    request.addfinalizer(wait_for_recover)


@fixture(scope='session')
def skip_for_one_proc():
    hypervisor = host_helper.get_up_hypervisors()
    if not hypervisor:
        skip("No up hypervisor on system.")

    if len(host_helper.get_host_procs(hostname=hypervisor[0])) < 2:
        skip('At least two processor per compute host is required for this test.')


@fixture(scope='function')
def check_avs_pattern():
    """
    Skip test for OVS system, if test name contains certain pattern
    """
    test_name = ProjVar.get_var('TEST_NAME')
    avs_pattern = 'avp|avr|avs|dpdk|e1000'
    if re.search(avs_pattern, test_name) and not system_helper.is_avs():
        skip("Test unsupported by OVS")


@fixture(scope='session')
def avs_required():
    if not system_helper.is_avs():
        skip('Test unsupported by OVS')


@fixture(scope='session')
def no_simplex():
    LOG.fixture_step("(Session) Skip if Simplex")
    if system_helper.is_aio_simplex():
        skip(SkipSysType.SIMPLEX_SYSTEM)


@fixture(scope='session')
def simplex_only():
    LOG.fixture_step("(Session) Skip if not Simplex")
    if not system_helper.is_aio_simplex():
        skip(SkipSysType.SIMPLEX_ONLY)


@fixture(scope='session')
def check_numa_num():
    hypervisor = host_helper.get_up_hypervisors()
    if not hypervisor:
        skip("No up hypervisor on system.")

    return len(host_helper.get_host_procs(hostname=hypervisor[0]))


@fixture(scope='session')
def wait_for_con_drbd_sync_complete():
    if len(system_helper.get_controllers()) < 2:
        LOG.info("Less than two controllers on system. Do not wait for drbd sync")
        return False

    host = 'controller-1'
    LOG.fixture_step("Waiting for controller-1 drbd sync alarm gone if present")
    end_time = time.time() + 1200
    while time.time() < end_time:
        drbd_alarms = system_helper.get_alarms(alarm_id=EventLogID.CON_DRBD_SYNC, reason_text='drbd-',
                                               entity_id=host, strict=False)

        if not drbd_alarms:
            LOG.info("{} drbd sync alarm is cleared".format(host))
            break
        time.sleep(10)

    else:
        assert False, "drbd sync alarm {} is not cleared within timeout".format(EventLogID.CON_DRBD_SYNC)

    LOG.fixture_step("Wait for {} becomes available in system host-list".format(host))
    system_helper.wait_for_host_values(host, availability=HostAvailState.AVAILABLE, timeout=120, fail_ok=False,
                                       check_interval=10)

    LOG.fixture_step("Wait for {} drbd-cinder in sm-dump to reach desired state".format(host))
    host_helper.wait_for_sm_dump_desired_states(host, 'drbd-', strict=False, timeout=30, fail_ok=False)
    return True


@fixture(scope='session')
def change_admin_password_session(request, wait_for_con_drbd_sync_complete):
    more_than_one_controllers = wait_for_con_drbd_sync_complete
    prev_pswd = Tenant.get('admin')['password']
    post_pswd = '!{}9'.format(prev_pswd)

    LOG.fixture_step('(Session) Changing admin password to {}'.format(post_pswd))
    keystone_helper.set_user('admin', password=post_pswd)

    def _lock_unlock_controllers():
        LOG.fixture_step("Sleep for 120 seconds after admin password change")
        time.sleep(300)  # CGTS-6928
        if more_than_one_controllers:
            active, standby = system_helper.get_active_standby_controllers()
            if standby:
                LOG.fixture_step("(Session) Locking unlocking controllers to complete action")
                host_helper.lock_host(standby)
                host_helper.unlock_host(standby)

                host_helper.lock_host(active, swact=True)
                host_helper.unlock_host(active)
            else:
                LOG.warning("Standby controller unavailable. Skip lock unlock controllers post admin password change.")
        elif system_helper.is_aio_simplex():
            LOG.fixture_step("(Session) Simplex lab - lock/unlock controller to complete action")
            host_helper.lock_host('controller-0', swact=False)
            host_helper.unlock_host('controller-0')

    def revert_pswd():
        LOG.fixture_step("(Session) Reverting admin password to {}".format(prev_pswd))
        keystone_helper.set_user('admin', password=prev_pswd)
        _lock_unlock_controllers()

        LOG.fixture_step("(Session) Check admin password is reverted to {} in keyring".format(prev_pswd))
        assert prev_pswd == security_helper.get_admin_password_in_keyring()
    request.addfinalizer(revert_pswd)

    _lock_unlock_controllers()

    LOG.fixture_step("(Session) Check admin password is changed to {} in keyring".format(post_pswd))
    assert post_pswd == security_helper.get_admin_password_in_keyring()

    return post_pswd


@fixture(scope='function')
def collect_kpi(request):
    collect_kpi_ = ProjVar.get_var('COLLECT_KPI') and bool(request.node.get_marker('kpi'))
    log_path = ProjVar.get_var('KPI_PATH') if collect_kpi_ else None
    return log_path


@fixture(scope='session')
def ixia_required():
    if 'ixia_ports' not in ProjVar.get_var("LAB"):
        skip("This system is not configured with ixia_ports")

    try:
        from IxNetwork import IxNet, IxNetError
    except ImportError:
        skip('IxNetwork modules unavailable')


@fixture(scope='session')
def heat_files_check():
    con_ssh = ControllerClient.get_active_controller()
    heat_dir = HeatTemplate.HEAT_DIR
    if not con_ssh.file_exists(heat_dir):
        skip("HEAT templates directory not found. Expected heat dir: {}".format(heat_dir))


@fixture(scope='session')
def set_test_patch_info():

    build_path = ProjVar.get_var('BUILD_PATH')
    build_server = system_helper.get_build_info()['BUILD_SERVER']
    if not build_path or not build_server:
        skip('Build path or server not found from /etc/build.info')

    with host_helper.ssh_to_build_server(bld_srv=build_server) as bs_ssh:
        patch_dir = common.get_symlink(bs_ssh, file_path='{}/test_patches'.format(build_path))

    if not patch_dir:
        skip("Test patches are not available for {}:{}".format(build_server, build_path))

    PatchingVars.set_patching_var(patch_dir=patch_dir)
    return build_server, patch_dir
