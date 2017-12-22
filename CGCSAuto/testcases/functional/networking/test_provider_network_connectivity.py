import time, re
from pytest import fixture, skip, mark
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
    interface_ids = table_parser.get_values(table_, 'uuid', strict=False, **kwargs)

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

    # Temporary skip for no vlan because vxlan still needs to be completed.
    if len(vlan_entry_names) < 1:
        skip("No VLAN providernets available.")

    i = 0
    loop_count = len(vlan_entry_names)
    popped_entries = []
    # Looping trough the providernet-range-list and removing entries that are not attached to the selected interface
    while i < loop_count:
        if vlan_entry_names[i] not in providernets:
            popped_entries.append(vlan_entries_table['values'][i])
            vlan_entries_table['values'].pop(i)
            vlan_entry_names.pop(i)
            loop_count -= 1
        else:
            i += 1

    id_column = table_parser.get_column_index(vlan_entries_table, 'id')
    providernet_name_column = table_parser.get_column_index(vlan_entries_table, 'providernet')
    maximum_column = table_parser.get_column_index(vlan_entries_table, 'maximum')
    minimum_column = table_parser.get_column_index(vlan_entries_table, 'minimum')
    range_id = ''
    name = ''
    min = 0
    max = 0
    # Looping through the remaining entries and saving the one with the largest 'maximum' range value
    for entry in vlan_entries_table['values']:
        temp_max = int(entry[maximum_column])
        if temp_max > max:
            range_id = entry[id_column]
            name = entry[providernet_name_column]
            min = int(entry[minimum_column])
            max = temp_max

    providernet_id = network_helper.get_providernets(name)

    if len(popped_entries) > 0:
        name = popped_entries[0][providernet_name_column]
        popped_entry = network_helper.get_providernets(name)
    else:
        popped_entry = ''

    return providernet_id, range_id, name, min, max, popped_entry


@fixture(scope='module', autouse=True)
def revert_vlan_provider_nets(request, get_vlan_providernet):
    providernet_id, range_id, providernet_name, providernet_min, providernet_max, popped_entry = get_vlan_providernet
    table_ = table_parser.table(cli.neutron("providernet-show {}".format(providernet_name), auth_info=Tenant.ADMIN))
    mtu = table_parser.get_value_two_col_table(table_, 'mtu')

    def _revert():
        LOG.fixture_step("Revert providernet {} with min:{} max:{}".format(providernet_name, providernet_min,
                                                                           providernet_max))
        cli.neutron("providernet-range-update --range {}-{} {}".format(providernet_min, providernet_max,
                                                                       range_id), auth_info=Tenant.ADMIN)
        LOG.fixture_step("Revert providernet {} with mtu:{}".format(providernet_name, mtu))
        cli.neutron("providernet-update {} --mtu {}".format(providernet_name, mtu), auth_info=Tenant.ADMIN)

    request.addfinalizer(_revert)


@fixture(scope='module', autouse=True)
def modify_neutron_config(request):
    host = system_helper.get_active_controller_name()

    def get_audit_interval():
        with host_helper.ssh_to_host(host) as host_ssh:
            cmd = 'cat /etc/neutron/neutron.conf | grep --color=never pnet_audit_interval'
            code, output = host_ssh.exec_sudo_cmd(cmd, fail_ok=False)
            pnet_audit_interval = output.split('=', 1)[-1].replace(" ", "")
            return int(pnet_audit_interval)

    def modify_pnet_audit_interval(old_interval, new_interval):
        with host_helper.ssh_to_host(host) as host_ssh:
            LOG.fixture_step("Setting pnet_audit_interval to {} seconds".format(new_interval))
            cmd = "sed -i 's/#pnet_audit_interval = {}/#pnet_audit_interval = {}/' /etc/neutron/neutron.conf".format(
                old_interval, new_interval)
            host_ssh.exec_sudo_cmd(cmd, fail_ok=False)

    old_interval = get_audit_interval()
    new_interval = 30

    def _modify():
        modify_pnet_audit_interval(old_interval, new_interval)
        assert get_audit_interval() == new_interval, "pnet_audit_interval was not changed to {}".format(new_interval)

    def _revert():
        modify_pnet_audit_interval(new_interval, old_interval)
        assert get_audit_interval() == old_interval, "pnet_audit_interval was not changed to {}".format(old_interval)

    request.addfinalizer(_revert)
    _modify()


def test_providernet_connectivity_no_connectivity(get_vlan_providernet):
    """
        US75531 - Provider network connectivity test with no connectivity

        Skip:
            - Communication failure detected over provider network

        Setups:
            - Set pnet_audit_interval to 30 seconds from 1800 seconds

        Test Steps:
            - Update range of provider network to out of range
            - Verify the alarm is raised
            - Revert the range of vlan provider network
            - Verify the alarm is cleared

        Teardown:
            - Revert pnet_audit_interval to 1800 seconds from 30 seconds
    """
    providernet_id, range_id, providernet_name, min_range, max_range, popped_entry = get_vlan_providernet

    LOG.tc_step("Check alarms for Communication Failure")
    alarms = system_helper.get_alarms(alarm_id=EventLogID.PROVIDER_NETWORK_FAILURE, entity_id=providernet_id,
                                      strict=False)
    if len(alarms) > 0:
        skip("Communication failure detected over provider network before test starts... cannot test.")
    LOG.tc_step("Update providernet {} with min:{} max:{}".format(providernet_name, min_range, max_range + 2))
    cli.neutron("providernet-range-update --range {}-{} {}".format(min_range, max_range + 2, range_id),
                auth_info=Tenant.ADMIN)

    LOG.tc_step("Wait for alarm to appear")
    system_helper.wait_for_alarm(alarm_id=EventLogID.PROVIDER_NETWORK_FAILURE, entity_id=providernet_id, timeout=90,
                                 strict=False)

    LOG.tc_step("Revert providernet {} with min:{} max:{}".format(providernet_name, min_range, max_range))
    cli.neutron("providernet-range-update --range {}-{} {}".format(min_range, max_range, range_id),
                auth_info=Tenant.ADMIN, fail_ok=True)

    LOG.tc_step("Wait for alarm to disappear")
    system_helper.wait_for_alarm_gone(EventLogID.PROVIDER_NETWORK_FAILURE, entity_id=providernet_id, timeout=90,
                                      strict=False)


def test_vlan_no_connectivity_two_providernets(get_vlan_providernet):
    """
        US75531 - Provider network connectivity test with two provider networks

        Skip:
            - Less than two computes up and available

        Setups:
            - Set pnet_audit_interval to 30 seconds from 1800 seconds
            - Attach one provider network to two different computes

        Test Steps:
            - Verify the provider network connectivity test is listed
            - Create invalid range for one of the provider networks
            - Verify the provider network connectivity test lists the failure

        Teardown:
            - Revert the provider networks that are attached to the compute back to the original
            - Revert the invalid range on the provider network
            - Revert pnet_audit_interval to 1800 seconds from 30 seconds
    """
    providernet_id, range_id, providernet_name, min_range, max_range, popped_entry = get_vlan_providernet
    if popped_entry == '':
        skip("All vlan providernets are attached to the same interface.")
    LOG.tc_step("Check alarms for Communication Failure on providernet under test")
    alarms = system_helper.get_alarms(alarm_id=EventLogID.PROVIDER_NETWORK_FAILURE, entity_id=popped_entry,
                                      strict=False)
    if len(alarms) > 0:
        skip("Communication failure detected over provider network before test starts... cannot test.")
    LOG.tc_step("Update providernet {} with min:{} max:{}".format(providernet_name, min_range, max_range + 2))
    cli.neutron("providernet-range-update --range {}-{} {}".format(min_range, max_range + 2, range_id),
                auth_info=Tenant.ADMIN)

    LOG.tc_step("Verify no alarms appear for the providernet under test")
    alarm = system_helper.wait_for_alarm(alarm_id=EventLogID.PROVIDER_NETWORK_FAILURE, entity_id=popped_entry,
                                         timeout=90, strict=False, fail_ok=True)[0]

    assert alarm is False, "Providernet was effected by another modified providernet"

    LOG.tc_step("Revert providernet {} with min:{} max:{}".format(providernet_name, min_range, max_range))
    cli.neutron("providernet-range-update --range {}-{} {}".format(min_range, max_range, range_id),
                auth_info=Tenant.ADMIN, fail_ok=True)

    LOG.tc_step("Verify no alarms for the providernet under test")
    alarms = system_helper.get_alarms(alarm_id=EventLogID.PROVIDER_NETWORK_FAILURE, entity_id=popped_entry,
                                      strict=False)
    assert len(alarms) == 0, "Providernet has alarms"


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
    if len(hypervisors) < 2:
        skip("There are less than two hypervisors")

    small_footprint = system_helper.is_small_footprint()

    if small_footprint:
        hypervisors.remove(system_helper.get_active_controller_name())
        slave_computes = hypervisors
    else:
        master_compute = hypervisors[0]
        slave_computes = hypervisors[1:]

    LOG.tc_step("Count pre-passed providernet tests")
    pre_passed = network_helper.get_providernet_connectivity_test_results(rtn_val='segmentation_ids', status='PASS')

    LOG.tc_step("Reboot hosts: {}".format(slave_computes))
    HostsToRecover.add(slave_computes)
    host_helper.reboot_hosts(slave_computes, wait_for_reboot_finish=False)

    LOG.tc_step("Verify the providernet connectivity test does not list {} as PASS".format(slave_computes))
    audit_id = network_helper.schedule_providernet_connectivity_test()
    slave_status = network_helper.get_providernet_connectivity_test_results(audit_id=audit_id, host_name=slave_computes)
    assert not slave_status, "Connectivity test still list results for rebooting computes"
    master_status = network_helper.get_providernet_connectivity_test_results(audit_id=audit_id,
                                                                             host_name=master_compute)
    assert set(master_status) == {'UNKNOWN'}, "Master host is not in Unknown state after other computes reboot"

    if not small_footprint:
        LOG.tc_step("Reboot the last compute host: {}".format(master_compute))
        HostsToRecover.add(master_compute)
        host_helper.reboot_hosts(master_compute, wait_for_reboot_finish=False)

        network_helper.schedule_providernet_connectivity_test()
        LOG.tc_step("Verify the providernet connectivity test does not list PASS for any host")
        status = network_helper.get_providernet_connectivity_test_results()
        assert not status, "At least one compute is not rebooting"

    LOG.tc_step("Wait for {} to be available".format(hypervisors))
    host_helper.wait_for_hosts_ready(hypervisors)

    LOG.tc_step("Verify all the providernet connectivity tests PASS")
    end_time = time.time() + 60
    while time.time() < end_time:
        network_helper.schedule_providernet_connectivity_test()
        post_passed = network_helper.get_providernet_connectivity_test_results(rtn_val='segmentation_ids',
                                                                               status='PASS')
        if sorted(pre_passed) == sorted(post_passed):
            break

    assert sorted(pre_passed) == sorted(post_passed), "Passed segments before the after host reboots are different"


def test_vlan_providernet_connectivity_cli_filters(get_vlan_providernet):
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
            value = get_vlan_providernet[2]

        elif param_filter == '--providernet_id':
            header = 'providernet_id'
            cmd = cli.neutron("providernet-list", auth_info=Tenant.ADMIN)
            table_ = table_parser.table(cmd)
            value = table_parser.get_values(table_, 'id')[0]

        elif param_filter == '--host_name':
            header = 'host_name'
            value = host_helper.get_up_hypervisors()[0]
        elif param_filter == '--segmentation_id':
            header = 'segmentation_ids'
            cmd = cli.neutron("providernet-range-list", auth_info=Tenant.ADMIN)
            table_ = table_parser.table(cmd)
            filtered_table = table_parser.filter_table(table_, **{'type': 'vlan'})
            value = table_parser.get_values(filtered_table, 'minimum')[0]
        LOG.tc_step("Verify output of providernet-connectivity-test-list using the {} filter".format(param_filter))
        cmd = cli.neutron('providernet-connectivity-test-list {} {}'.format(param_filter, value),
                          auth_info=Tenant.ADMIN)
        queried_table = table_parser.table(cmd)
        columns = ['status', 'message', 'segmentation_ids']
        queried_table = table_parser.remove_columns(queried_table, columns)
        cmd = cli.neutron('providernet-connectivity-test-list', auth_info=Tenant.ADMIN)
        kwargs = {header: value}
        table_ = table_parser.table(cmd, combine_multiline_entry=True)

        if param_filter == '--segmentation_id':
            filtered_table = table_parser.filter_table(table_, **{'type': 'vlan'})
            filtered_with_keyword_table = table_segment_id_filter(filtered_table, value)
        else:
            filtered_with_keyword_table = table_parser.filter_table(table_, strict=False, **kwargs)
        columns = ['status', 'message', 'segmentation_ids']
        filtered_with_keyword_table = table_parser.remove_columns(filtered_with_keyword_table, columns)
        result, error = table_parser.compare_tables(queried_table, filtered_with_keyword_table)
        assert result == 0, "Tables are not the same. Filtered using: {}. Error: {}".format(param_filter, error)


def table_segment_id_filter(table_, value):

    # filter out the number of rows in the table that match value or the number range contain value

    if not table_['headers']:
        LOG.warning("Empty table supplied")
        return table_

    column = table_parser.get_column(table_, 'segmentation_ids')

    # create new table
    new_table = dict()
    new_table['headers'] = table_['headers']
    new_table['values'] = []
    for i in range(len(column)):
        item = column[i]
        # check for number set such as 1,1-2,3,4-5
        number_obj = item.split(',')
        for num_pair in number_obj:
            num = num_pair.split('-')
            # check if the value is between any number pair
            if int(num[0]) <= int(value) <= int(num[-1]):
                new_table['values'].append(table_['values'][i])
                # only need one match per row
                break

    return new_table


# Invalid test. Update needed. CGTS-8520
# 1. Need to create new providernet so it's not associated to any networks
# 2. Should schedule the connectivity test after mtu change, otherwise it's likely still displaying the result
# from previous audit
def _test_vlan_providernet_connectivity_different_mtu(get_vlan_providernet):
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

    providernet_name = get_vlan_providernet[2]
    LOG.tc_step("Update mtu=576 for providernet {}".format(providernet_name))
    cli.neutron("providernet-update {} --mtu 576".format(providernet_name), auth_info=Tenant.ADMIN)

    LOG.tc_step("Verify the mtu change did not effect the providernet-connectivity-test-list")
    cmd = cli.neutron("providernet-connectivity-test-list", auth_info=Tenant.ADMIN)
    second_test = table_parser.table(cmd)
    assert first_test == second_test, "MTU change impacted providernet-connectivity-test-list"


@fixture(scope='function')
def create_delete_range(get_vlan_providernet, request):
    providernet = get_vlan_providernet[2]
    min_range = 4080
    max_range = 4085
    LOG.fixture_step("Create range on {} with the values {}".format(providernet, '{}-{}'.format(min_range, max_range)))
    range_name = network_helper.create_providernet_range(providernet, min_range, max_range, rtn_val='name')[1]

    def del_range():
        if DEL_RANGE:
            LOG.fixture_step("Delete providernet range {}".format(range_name))
            network_helper.delete_providernet_range(range_name)
    request.addfinalizer(del_range)
    return range_name, min_range, max_range


DEL_RANGE = True


def test_vlan_providernet_connectivity_delete_segment(create_delete_range):
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
    range_name, min_range, max_range = create_delete_range

    global DEL_RANGE
    DEL_RANGE = True

    LOG.tc_step("Schedule providernet-connectivity-test and ensure newly created range to be listed in "
                "providernet-connectivity-test-list")

    kwargs = {'segmentation_ids': '{}-{}'.format(min_range, max_range)}
    network_helper.schedule_providernet_connectivity_test()

    res_for_seg = network_helper.get_providernet_connectivity_test_results(**kwargs)
    assert res_for_seg, "Seg range {}-{} is not listed in providernet-connectivity-test".format(min_range, max_range)

    LOG.tc_step("Delete the providernet range")
    network_helper.delete_providernet_range(range_name)
    DEL_RANGE = False

    network_helper.schedule_providernet_connectivity_test()
    LOG.tc_step("Verify the providernet-connectivity-test-list no longer shows the providernet range")
    res_after_del = network_helper.get_providernet_connectivity_test_results(**kwargs)
    assert not res_after_del, "Segmentation range {}-{} is still listed in providernet-connectivity-test after " \
                              "deletion".format(min_range, max_range)
