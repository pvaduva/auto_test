from pytest import fixture, mark

from consts.auth import Tenant
from utils import table_parser
from utils.ssh import ControllerClient
from utils.tis_log import LOG
from keywords import system_helper, vm_helper, nova_helper, cinder_helper, storage_helper


########################
# Test Fixtures Module #
########################


@fixture()
def check_alarms(request):
    """
    Check system alarms before and after test run.

    Args:
        request: caller of this fixture. i.e., test func.
    """
    LOG.fixture_step("(function) Gathering system alarms info before test begins.")
    before_tab = system_helper.get_alarms()
    before_rows = table_parser.get_all_rows(before_tab)

    def verify_alarms():
        LOG.fixture_step("(function) Verifying system alarms after test ended...")
        after_tab = system_helper.get_alarms()
        after_rows = table_parser.get_all_rows(after_tab)
        new_alarms = []
        for item in after_rows:
            if item not in before_rows:
                new_alarms.append(item)
        assert not new_alarms, "New alarm(s) found: {}".format(new_alarms)
        LOG.info("System alarms verified.")
    request.addfinalizer(verify_alarms)
    return


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
def ping_vm_from_vm(request):
    # TODO: Everything below
    LOG.info("Gathering VM ping to other VMs before test begins.")

    before_ping_result = vm_helper.ping_vms_from_vm()

    def verify_vms_ping():
        after_ping_result = vm_helper.ping_vms_from_vm()

        assert before_ping_result == after_ping_result

        LOG.info("Ping from VM to other VMs verified.")
    request.addfinalizer(verify_vms_ping)
    return


@fixture()
def ceph_precheck(request): # yang TODO: can be auto used if needed
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
    # yang TODO: better to skip
    assert nodes, 'SUT does not have storage nodes'

    LOG.info('Verify the health of the CEPH cluster')
    rtn, msg = storage_helper.is_ceph_healthy(con_ssh)
    LOG.info('{}'.format(msg))

    LOG.info('Verify if there are OSDs provisioned')
    osds = storage_helper.get_num_osds(con_ssh)
    LOG.info('System has {} OSDS'.format(osds))
    assert osds != 0, 'There are no OSDs assigned'

    return

