from pytest import fixture, mark, skip

from consts.auth import Tenant
from consts.cgcs import EventLogID, HostAvailabilityState
from consts.timeout import EventLogTimeout
from utils import table_parser, cli
from utils.ssh import ControllerClient
from utils.tis_log import LOG
from keywords import system_helper, vm_helper, nova_helper, cinder_helper, storage_helper, host_helper


########################
# Test Fixtures Module #
########################

@fixture(scope='function')
def check_alarms(request):
    """
    Check system alarms before and after test case.

    Args:
        request: caller of this fixture. i.e., test func.
    """
    __verify_alarms(request=request, scope='function')


# @fixture(scope='session', autouse=True)
def check_alarms_session(request):
    """
    Check system alarms before and after test session.

    Args:
        request: caller of this fixture. i.e., test func.
    """
    __verify_alarms(request=request, scope='session')


def __verify_alarms(request, scope):
    LOG.fixture_step("({}) Gathering system alarms info before test {} begins.".format(scope, scope))
    before_tab = system_helper.get_alarms_table()
    before_alarms = system_helper._get_alarms(before_tab)

    def verify_alarms():
        LOG.fixture_step("({}) Verifying system alarms after test {} ended...".format(scope, scope))
        after_tab = system_helper.get_alarms_table()
        after_alarms = system_helper._get_alarms(after_tab)
        new_alarms = []

        for item in after_alarms:
            if item not in before_alarms:
                new_alarms.append(item)

        if new_alarms:
            LOG.fixture_step("New alarms detected. Waiting for new alarms to clear.")
            res, remaining_alarms = system_helper.wait_for_alarms_gone(new_alarms, fail_ok=True, timeout=300)
            assert res, "New alarm(s) found and did not clear within 5 minutes. " \
                        "Alarm IDs and Entity IDs: {}".format(remaining_alarms)

        LOG.fixture_step("({}) System alarms verified.".format(scope))

    request.addfinalizer(verify_alarms)
    return


@fixture(scope='session', autouse=True)
def pre_alarms_session():
    return __get_alarms('session')


@fixture(scope='function')
def pre_alarms_function():
    return __get_alarms('function')


def __get_alarms(scope):
    LOG.fixture_step("({}) Gathering system alarms info before test {} begins.".format(scope, scope))
    alarms = system_helper.get_alarms()
    return alarms


@fixture(scope='session')
def pre_coredumps_and_crash_reports_session():
    return __get_system_crash_and_coredumps('session')


def __get_system_crash_and_coredumps(scope):
    LOG.fixture_step("({}) Getting existing system crash reports and coredumps before test {} begins.".
                     format(scope, scope))

    core_dumps_and_reports = host_helper.get_coredumps_and_crashreports()
    return core_dumps_and_reports


@fixture()
def check_hosts(request):
    LOG.fixture_step("Gathering systems hosts status before test begins.")
    raise NotImplementedError


@fixture()
def check_vms(request):
    """
    Check Status of the VMs before and after test run.

    Args:
        request: caller of this fixture. i.e., test func.
    """
    LOG.fixture_step("Gathering system VMs info before test begins.")
    before_vms_status = nova_helper.get_field_by_vms(field="Status", auth_info=Tenant.ADMIN)

    def verify_vms():
        LOG.fixture_step("Verifying system VMs after test ended...")
        after_vms_status = nova_helper.get_field_by_vms(field="Status", auth_info=Tenant.ADMIN)

        # compare status between the status of each VMs before/after the test
        common_vms = set(before_vms_status) & set(after_vms_status)
        LOG.debug("VMs to verify: {}".format(common_vms))
        before_dict = {vm_id: before_vms_status[vm_id] for vm_id in common_vms}
        after_dict = {vm_id: after_vms_status[vm_id] for vm_id in common_vms}

        failure_msgs = []
        if not before_dict == after_dict:
            for vm, post_status in after_dict:
                if post_status.lower() != 'active' and post_status != before_vms_status[vm]:
                    msg = "VM {} is not in good state after lock. Pre status: {}. Post status: {}". \
                        format(vm, after_vms_status[vm], post_status)
                    failure_msgs.append(msg)

        assert not failure_msgs, '\n'.join(failure_msgs)
        LOG.info("System VMs verified.")
    request.addfinalizer(verify_vms)
    return


@fixture()
def ping_vms_from_nat(request):
    """
    TODO: - should only compare common vms
        - should pass as long as after test ping results are good regardless of the pre test results
        - if post test ping failed, then compare it with pre test ping to see if it's a okay failure.
        - better to re-utilize the check vm fixture so that we don't need to retrieving the info again.
            i.e., use fixture inside a fixture.

    Args:
        request:

    Returns:

    """
    LOG.info("Gathering VMs ping to NAT before test begins.")

    before_ping_result = vm_helper.ping_vms_from_natbox()

    def verify_nat_ping():
        after_ping_result = vm_helper.ping_vms_from_natbox()

        assert before_ping_result == after_ping_result

        LOG.info("Ping from NAT Box to VMs verified.")
    request.addfinalizer(verify_nat_ping)
    return


@fixture()
def ceph_precheck(request):
    """
    Run test pre-checks before running CEPH storage tests.

    Args:
        request: caller of this fixture. i.e., test func.
    """
    # yang TODO: probably can remove
    con_ssh = ControllerClient.get_active_controller()

    LOG.info('Ensure the system has storage nodes')
    nodes = system_helper.get_storage_nodes(con_ssh)
    LOG.info('System has the following storage nodes {}'.format(nodes))
    if not nodes:
        skip('SUT does not have storage nodes')

    LOG.info('Verify the health of the CEPH cluster')
    rtn, msg = storage_helper.is_ceph_healthy(con_ssh)
    LOG.info('{}'.format(msg))

    LOG.info('Verify if there are OSDs provisioned')
    osds = storage_helper.get_num_osds(con_ssh)
    LOG.info('System has {} OSDS'.format(osds))
    assert osds != 0, 'There are no OSDs assigned'

    return

