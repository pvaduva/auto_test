import time
from pytest import fixture, skip
from keywords import host_helper, system_helper, network_helper
from utils.tis_log import LOG
from utils import cli, table_parser
from consts.auth import Tenant
from consts.cgcs import EventLogID
from testfixtures.recover_hosts import HostsToRecover


@fixture(scope='module')
def get_vlan_providernet():
    LOG.fixture_step("Get available hypervisors")
    hypervisors = host_helper.get_up_hypervisors()

    if len(hypervisors) < 1:
        skip("No up hypervisors are available")
    hypervisor = hypervisors[0]

    LOG.fixture_step("Get data interface with at least two provider networks on {}".format(hypervisor))
    table_ = system_helper.get_host_interfaces_table(hypervisor)
    kwargs = {'type': 'ethernet', 'network type': 'data', 'provider networks': ','}
    interface_ids = table_parser.get_values(table_, 'uuid', **kwargs, strict=False)

    if len(interface_ids) < 1:
        skip("No interfaces with at least two provider networks attached")
    target_interface_id = interface_ids[0]

    LOG.fixture_step("Get provider network with the greatest max segmentation range")
    kwargs = {'uuid': '{}'.format(target_interface_id)}
    providernets = table_parser.get_values(table_, 'provider networks', **kwargs)[0].split(",")

    cmd = cli.neutron("providernet-range-list --nowrap", auth_info=Tenant.ADMIN)
    table_ = table_parser.table(cmd)
    kwargs = {'type': 'vlan'}
    vlan_entries_table = table_parser.filter_table(table_, **kwargs)

    vlan_entry_names = table_parser.get_values(vlan_entries_table, 'providernet')

    i = 0
    loop_count = len(vlan_entry_names)
    # Looping trough the providernet-range-list and removing entries that are not attached to the selected interface
    while i < loop_count:
        if vlan_entry_names[i] not in providernets:
            vlan_entries_table['values'].pop(i)
            vlan_entry_names.pop(i)
            loop_count -= 1
        else:
            i += 1

    id_column = table_parser.get_column_index(vlan_entries_table, 'id')
    providernet_name_column = table_parser.get_column_index(vlan_entries_table, 'providernet')
    maximum_column = table_parser.get_column_index(vlan_entries_table, 'maximum')
    minimum_column = table_parser.get_column_index(vlan_entries_table, 'minimum')
    id = ''
    name = ''
    min = 0
    max = 0
    # Looping through the remaining entries and saving the one with the largest 'maximum' range value
    for entry in vlan_entries_table['values']:
        temp_max = int(entry[maximum_column])
        if temp_max > max:
            id = entry[id_column]
            name = entry[providernet_name_column]
            min = int(entry[minimum_column])
            max = temp_max

    return id, name, min, max


@fixture(scope='module', autouse=True)
def modify_neutron_config(request):
    host = system_helper.get_active_controller_name()
    with host_helper.ssh_to_host(host) as con_ssh:
        cmd = 'cat /etc/neutron/neutron.conf | grep --color=never pnet_audit_interval'
        code, pnet_audit_interval = con_ssh.exec_sudo_cmd(cmd)

    def _modify():
        with host_helper.ssh_to_host(host) as con_ssh:
            LOG.fixture_step("Setting pnet_audit_interval to 30 seconds")
            cmd = "sed -i 's/{}/#pnet_audit_interval = 30/' /etc/neutron/neutron.conf".format(pnet_audit_interval)
            con_ssh.exec_sudo_cmd(cmd)

    def _revert():
        with host_helper.ssh_to_host(host) as con_ssh:
            LOG.fixture_step("Reverting pnet_audit_interval to original value")
            cmd = "sed -i 's/#pnet_audit_interval = 30/{}/' /etc/neutron/neutron.conf".format(pnet_audit_interval)
            con_ssh.exec_sudo_cmd(cmd)

    request.addfinalizer(_revert)
    _modify()


@fixture(scope='module', autouse=True)
def revert_vlan_provider_nets(request, get_vlan_providernet):
    providernet_id, providernet_name, providernet_min, providernet_max = get_vlan_providernet
    table_ = table_parser.table(cli.neutron("providernet-show {}".format(providernet_name), auth_info=Tenant.ADMIN))
    mtu = table_parser.get_value_two_col_table(table_, 'mtu')

    def _revert():
        LOG.fixture_step("Revert providernet {} with min:{} max:{}".format(providernet_name, providernet_min,
                                                                           providernet_max))
        cli.neutron("providernet-range-update --range {}-{} {}".format(providernet_min, providernet_max,
                                                                       providernet_id), auth_info=Tenant.ADMIN)
        LOG.fixture_step("Revert providernet {} with mtu:{}".format(providernet_name, mtu))
        cli.neutron("providernet-update {} --mtu {}".format(providernet_name, mtu), auth_info=Tenant.ADMIN)

    request.addfinalizer(_revert)


def test_vlan_no_connectivity(get_vlan_providernet):
    """
        US75531 - Provider network connectivity test of type vlan with no connectivity

        Skip:
            - Communication failure detected over provider network

        Setups:
            - Set pnet_audit_interval to 30 seconds from 1800 seconds

        Test Steps:
            - Update range of vlan provider network to out of range
            - Verify the alarm is raised
            - Revert the range of vlan provider network
            - Verify the alarm is cleared

        Teardown:
            - Revert pnet_audit_interval to 1800 seconds from 30 seconds
    """
    LOG.tc_step("Check alarms for Communication Failure")
    alarms = system_helper.get_alarms(reason_text="Communication failure detected over provider network")
    if len(alarms) > 0:
        skip("Communication failure detected over provider network before test starts... cannot test.")
    providernet_id, providernet_name, min_range, max_range = get_vlan_providernet
    LOG.tc_step("Update providernet {} with min:{} max:{}".format(providernet_name, min_range, max_range + 2))
    cli.neutron("providernet-range-update --range {}-{} {}".format(min_range, max_range + 2, providernet_id),
                auth_info=Tenant.ADMIN)

    LOG.tc_step("Wait for alarm to appear")
    system_helper.wait_for_alarm(reason="Communication failure detected over provider network", timeout=90)

    LOG.tc_step("Revert providernet {} with min:{} max:{}".format(providernet_name, min_range, max_range))
    cli.neutron("providernet-range-update --range {}-{} {}".format(min_range, max_range, providernet_id),
                auth_info=Tenant.ADMIN, fail_ok=True)

    LOG.tc_step("Wait for alarm to disappear")
    system_helper.wait_for_alarm_gone(EventLogID.PROVIDER_NETWORK_FAILURE, timeout=90)


# TODO talk to senthil about this testcase. Do not understand what it is asking / how to accomplish
# def test_vlan_connectivity_two_providernets():
#     """
#         US75531 - Provider network connectivity test with two provider networks
#
#         Skip:
#             - Less than two computes up and available
#
#         Setups:
#             - Set pnet_audit_interval to 30 seconds from 1800 seconds
#             - Attach one provider network to two different computes
#
#         Test Steps:
#             - Verify the provider network connectivity test is listed
#             - Create invalid range for one of the provider networks
#             - Verify the provider network connectivity test lists the failure
#
#         Teardown:
#             - Revert the provider networks that are attached to the compute back to the original
#             - Revert the invalid range on the provider network
#             - Revert pnet_audit_interval to 1800 seconds from 30 seconds
#     """

def test_providernet_connectivity_reboot():
    """
        US75531 - Provider network connectivity test after slave and master compute reboots

        Skip:
            - No computes up and available

        Setups:
            - Set pnet_audit_interval to 30 seconds from 1800 seconds

        Test Steps:
            - Reboot the slave computes
            - Verify the provider network connectivity test is listed as unknown for the rebooting computes
            - Reboot the remaining master compute
            - Verify the provider network connectivity test lists an empty table (no status)
            - Wait for hosts to be available and ready
            - Verify the provider network connectivity test lists PASS for all tests

        Teardown:
            - Revert pnet_audit_interval to 1800 seconds from 30 seconds
    """
    LOG.tc_step("Get list of compute hosts")
    hypervisors = host_helper.get_up_hypervisors()
    small_footprint = system_helper.is_small_footprint()
    if small_footprint:
        if len(hypervisors) < 1:
            skip("Small footprint: Only one hypervisor available")
        hypervisors.remove(system_helper.get_active_controller_name())
        slave_computes = hypervisors
    else:
        if len(hypervisors) < 2:
            skip("There are less than two hypervisors")
        master_compute = hypervisors[0]
        hypervisors.pop(0)
        slave_computes = hypervisors

    LOG.tc_step("Count pre-passed providernet tests")
    cmd = cli.neutron("providernet-connectivity-test-list", auth_info=Tenant.ADMIN)
    connectivity_table = table_parser.table(cmd)
    pre_passed_connectivity_tests = table_parser.filter_table(connectivity_table, **{'status': 'PASS'})

    LOG.tc_step("Reboot hosts: {}".format(slave_computes))
    HostsToRecover.add(slave_computes)
    host_helper.reboot_hosts(slave_computes, wait_for_reboot_finish=False)

    if not small_footprint:
        LOG.tc_step("Verify the providernet connectivity test does not list {} as PASS".format(slave_computes))
        cmd = cli.neutron("providernet-connectivity-test-list", auth_info=Tenant.ADMIN)
        connectivity_table = table_parser.table(cmd)
        passed_connectivity_tests = table_parser.filter_table(connectivity_table, **{'status': 'PASS'})
        hosts_passed = table_parser.get_column(passed_connectivity_tests, 'host_name')
        for test_host in hosts_passed:
            assert test_host == master_compute, "Host: {} did not reboot".format(test_host)

        LOG.tc_step("Reboot host: {}".format(master_compute))
        HostsToRecover.add(master_compute)
        host_helper.reboot_hosts(master_compute, wait_for_reboot_finish=False)

    LOG.tc_step("Verify the providernet connectivity test does not list PASS for any host")
    cmd = cli.neutron("providernet-connectivity-test-list", auth_info=Tenant.ADMIN)
    connectivity_table = table_parser.table(cmd)
    assert connectivity_table == {'headers': [], 'values': []}, "Atleast one compute is not rebooting"

    if not small_footprint:
        hypervisors.append(master_compute)
    LOG.tc_step("Wait for {} to be available".format(hypervisors))
    host_helper.wait_for_hosts_ready(hypervisors)

    LOG.tc_step("Verify all the providernet connectivity tests PASS")
    end_time = time.time() + 120
    while time.time() < end_time:
        cmd = cli.neutron("providernet-connectivity-test-list", auth_info=Tenant.ADMIN)
        connectivity_table = table_parser.table(cmd)
        post_passed_connectivity_tests = table_parser.filter_table(connectivity_table, **{'status': 'PASS'})
        if len(pre_passed_connectivity_tests['values']) == len(post_passed_connectivity_tests['values']):
            break
    assert len(pre_passed_connectivity_tests['values']) == len(post_passed_connectivity_tests['values'])


def test_providernet_connectivity_cli_filters(get_vlan_providernet):
    """
        US75531 - Providernet Connectivity Test List using CLI

        Skip:
            - No computes up and available

        Setups:
            - Set pnet_audit_interval to 30 seconds from 1800 seconds

        Test Steps:
            - Verify only the filtered options are displayed in the output of providernet-connectivity-test-list:
                --providernet_name
                --providernet_id
                --host_name
                --segmentation_id (Supported on vlan providernets only)

        Teardown:
            - Revert pnet_audit_interval to 1800 seconds from 30 seconds
    """
    filters = ['--providernet_name', '--providernet_id', '--host_name', '--segmentation_id']
    for param_filter in filters:
        header = ''
        value = ''
        if param_filter == '--providernet_name':
            header = 'providernet_name'
            value = get_vlan_providernet[1]

        elif param_filter == '--providernet_id':
            header = 'providernet_id'
            cmd = cli.neutron("providernet-list", auth_info=Tenant.ADMIN)
            table_ = table_parser.table(cmd)
            value = table_parser.get_values(table_, 'id')[0]

        elif param_filter == '--host_name':
            header = 'host_name'
            value = system_helper.get_hostnames(personality='compute')[0]

        elif param_filter == '--segmentation_id':
            header = 'segmentation_ids'
            cmd = cli.neutron("providernet-range-list", auth_info=Tenant.ADMIN)
            table_ = table_parser.table(cmd)
            filtered_table = table_parser.filter_table(table_, **{'type': 'vlan'})
            value = table_parser.get_values(filtered_table, 'minimum')[0]

        LOG.tc_step("Verify output of providernet-connectivity-test-list using the {} filter".format(param_filter))
        cmd = cli.neutron('providernet-connectivity-test-list {} {}'.format(param_filter, value),
                          auth_info=Tenant.ADMIN)
        pre_filtered_table = table_parser.table(cmd)
        kwargs = {'{}'.format(header): '{}'.format(value)}
        post_filtered_table = table_parser.filter_table(pre_filtered_table, **kwargs)
        assert len(pre_filtered_table['values']) == len(post_filtered_table['values']), \
            "Table filtered with '{}': '{}' does not return the same number of entries as the unfiltered table" \
            .format(header, value)


def test_providernet_connectivity_different_mtu(get_vlan_providernet):
    """
        US75531 - Providernet Connectivity Test with different MTU size

        Skip:
            - No computes up and available

        Setups:
            - Set pnet_audit_interval to 30 seconds from 1800 seconds

        Test Steps:
            - Change the MTU size to 1500
            - Verify there is no impact in providernet-connectivity-test-list

        Teardown:
            - Revert pnet_audit_interval to 1800 seconds from 30 seconds
            - Revert MTU size to original
    """
    cmd = cli.neutron("providernet-connectivity-test-list", auth_info=Tenant.ADMIN)
    first_test = table_parser.table(cmd)

    providernet_name = get_vlan_providernet[1]
    LOG.tc_step("Update mtu=576 for providernet {}".format(providernet_name))
    cli.neutron("providernet-update {} --mtu 576".format(providernet_name), auth_info=Tenant.ADMIN)

    LOG.tc_step("Verify the mtu change did not effect the providernet-connectivity-test-list")
    cmd = cli.neutron("providernet-connectivity-test-list", auth_info=Tenant.ADMIN)
    second_test = table_parser.table(cmd)
    assert first_test == second_test, "MTU change impacted providernet-connectivity-test-list"


def test_providernet_connectivity_delete_vlan_segment(get_vlan_providernet):
    """
        US75531 - Providernet Connectivity Test after deleting vlan segment range

        Skip:
            - No computes up and available
            - providernet-connectivity-test-list has prior failures

        Setups:
            - Set pnet_audit_interval to 30 seconds from 1800 seconds

        Test Steps:
            - Create segmentation range on a vlan provider network
            - Verify providernet-connectivity-test-list shows the segmentation range
            - Delete the segmentation range
            - Verify providernet-connectivity-test-list does not show the segmentation range that was deleted

        Teardown:
            - Revert pnet_audit_interval to 1800 seconds from 30 seconds
            - Revert MTU size to original
    """
    providernet = get_vlan_providernet[1]

    LOG.tc_step("Create range on {} with the values {}".format(providernet, '4080-4085'))
    code, range = network_helper.create_providernet_range(providernet, 4080, 4085, rtn_val='name')

    LOG.tc_step("Wait for the providernet-connectivity-test-list to show the new range")
    kwargs = {'segmentation_ids': '4080-4085', 'status': 'PASS'}
    timeout = time.time() + 240
    while time.time() < timeout:
        cmd = cli.neutron("providernet-connectivity-test-list", auth_info=Tenant.ADMIN)
        providernet_test_table = table_parser.table(cmd)
        filtered_test_table = table_parser.filter_table(providernet_test_table, **kwargs, strict=False)
        if len(filtered_test_table['values']) > 0:
            break

    LOG.tc_step("Delete the providernet range")
    network_helper.delete_providernet_range(range)
    assert len(filtered_test_table['values']) > 0, "Segmentation range did not show up or pass during test"

    LOG.tc_step("Verify the providernet-connectivity-test-list no longer shows the providernet range")
    cmd = cli.neutron("providernet-connectivity-test-list", auth_info=Tenant.ADMIN)
    providernet_test_table = table_parser.table(cmd)
    filtered_test_table = table_parser.filter_table(providernet_test_table, **kwargs)
    assert len(filtered_test_table['values']) == 0, "Segmentation range did not delete"
