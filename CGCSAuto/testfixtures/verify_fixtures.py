from pytest import fixture, skip

from consts.auth import Tenant
from consts.cgcs import SysType
from keywords import system_helper, vm_helper, nova_helper, storage_helper, host_helper, common, check_helper, \
    kube_helper
from utils.tis_log import LOG


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


@fixture(scope='module')
def check_alarms_module(request):
    """
    Check system alarms before and after test session.

    Args:
        request: caller of this fixture. i.e., test func.
    """
    __verify_alarms(request=request, scope='module')


def __verify_alarms(request, scope):
    before_alarms = __get_alarms(scope=scope)

    def verify_alarms():
        LOG.fixture_step("({}) Verifying system alarms after test {} ended...".format(scope, scope))
        check_helper.check_alarms(before_alarms=before_alarms)
        LOG.info("({}) System alarms verified.".format(scope))

    request.addfinalizer(verify_alarms)
    return


@fixture(scope='function', autouse=False)
def check_i40e_hosts(request):
    hosts = ['compute-4', 'compute-5']
    start_time = common.get_date_in_format(date_format="%Y-%m-%dT%T")

    def check_kern_log():
        cmd = """cat /var/log/kern.log | grep -i --color=never "(i40e): transmit queue" | awk '$0 > "{}"'""".\
            format(start_time)
        i40e_errs = []
        host_helper.wait_for_hosts_ready(hosts=hosts)
        for host in hosts:
            with host_helper.ssh_to_host(hostname=host) as host_ssh:
                output = host_ssh.exec_cmd(cmd)[1]
                if output:
                    i40e_errs.append("{}: {}".format(host, output))
        assert not i40e_errs, "i40e errors: {}".format(i40e_errs)

    request.addfinalizer(check_kern_log)


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
def check_vms(request):
    """
    Check Status of the VMs before and after test run.

    Args:
        request: caller of this fixture. i.e., test func.
    """
    LOG.fixture_step("Gathering system VMs info before test begins.")
    before_vms_status = nova_helper.get_field_by_vms(field="Status", auth_info=Tenant.get('admin'))

    def verify_vms():
        LOG.fixture_step("Verifying system VMs after test ended...")
        after_vms_status = nova_helper.get_field_by_vms(field="Status", auth_info=Tenant.get('admin'))

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
def ceph_precheck():
    """
    Run test pre-checks before running CEPH storage tests.

    """
    LOG.info('Ensure the system has storage nodes')
    sys_type = system_helper.get_sys_type()
    if not sys_type == SysType.STORAGE:
        skip('SUT does not have storage nodes')

    LOG.info('Verify the health of the CEPH cluster')
    rtn, msg = storage_helper.is_ceph_healthy()
    LOG.info('{}'.format(msg))

    LOG.info('Verify if there are OSDs provisioned')
    osds = storage_helper.get_num_osds()
    LOG.info('System has {} OSDS'.format(osds))
    assert osds != 0, 'There are no OSDs assigned'

    LOG.info('Query storage usage info')
    storage_helper.get_storage_usage()


@fixture()
def check_openstack_pods(request):
    __verify_openstack_pods(request=request, scope='function')


@fixture()
def check_openstack_pods_module(request):
    __verify_openstack_pods(request=request, scope='module')


def __verify_openstack_pods(request, scope):
    prev_bad_pods = kube_helper.is_openstack_pods_in_status()[1]

    def verify():
        LOG.fixture_step("({}) Verifying openstack pod status after test {} ended...".format(scope, scope))
        post_bad_pods = kube_helper.is_openstack_pods_in_status()[1]
        new_bad_pods = [{k, post_bad_pods[k]} for k in post_bad_pods if k not in prev_bad_pods]
        assert not new_bad_pods, "Some openstack pod(s) in unexpected status: {}".format(new_bad_pods)
    request.addfinalizer(verify)

    return