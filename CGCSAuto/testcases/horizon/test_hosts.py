from pytest import fixture, mark

from utils import table_parser, cli
from utils.horizon.regions import messages
from utils.horizon.pages.admin.platform import hostinventorypage
from utils.tis_log import LOG
from consts import horizon
from keywords import host_helper, system_helper
from testfixtures.horizon import admin_home_pg, driver


@fixture(scope='function')
def host_inventory_pg(admin_home_pg, request):
    LOG.fixture_step('Go to Admin > Platform > Host Inventory')
    host_inventory_pg = hostinventorypage.HostInventoryPage(admin_home_pg.driver)
    host_inventory_pg.go_to_target_page()

    def teardown():
        LOG.fixture_step('Back to Host Inventory page')
        host_inventory_pg.go_to_target_page()

    request.addfinalizer(teardown)
    return host_inventory_pg


@mark.parametrize('host_name', [
    # 'controller-1', 'compute-2'
])
def _test_host_lock_unlock(host_inventory_pg, host_name):

    """
    Test the host lock and unlock functionality:

    Setups:
        - Login as Admin
        - Go to Admin > Platform > Host Inventory

    Test Steps:
        - Lock a host
        - Verify the host is locked
        - Unlock the host
        - Verify the host is available

    Teardown:
        - Back to Host Inventory page
        - Logout

    """

    LOG.tc_step('Lock the host {}'.format(host_name))
    host_inventory_pg.lock_host(host_name)
    assert host_inventory_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not host_inventory_pg.find_message_and_dismiss(messages.ERROR)

    LOG.tc_step('Verify the host is locked')
    assert host_inventory_pg.is_host_admin_state(host_name, 'Locked')

    LOG.tc_step('Unlock the host')
    host_inventory_pg.unlock_host(host_name)
    assert host_inventory_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not host_inventory_pg.find_message_and_dismiss(messages.ERROR)

    LOG.tc_step('Verify the host is available')
    assert host_inventory_pg.is_host_availability_state(host_name, 'Available')
    horizon.test_result = True


def format_uptime(uptime):
    """
    Uptime displays in horizon may display like this format:
        2 weeks, 10 hours
        2 hours, 2 minutes
        45 minutes
        ...
    """
    uptime = int(uptime)
    min_ = 60
    hour = min_ * 60
    day = hour * 24
    week = day * 7
    month = week * 4

    uptime_months = uptime // month
    uptime_weeks = uptime % month // week
    uptime_days = uptime % month % week//day
    uptime_hours = uptime % month % week % day // hour
    uptime_mins = uptime % month % week % day % hour // min_

    if uptime < min_:
        return '0 minutes'
    elif uptime < hour:
        return '{} minute'.format(uptime_mins)
    elif uptime < day:
        return '{} hour, {} minute'.format(uptime_hours, uptime_mins)
    elif uptime < week:
        return '{} day, {} hour'.format(uptime_days, uptime_hours)
    elif uptime < month:
        return '{} week, {} day'.format(uptime_weeks, uptime_days)
    elif uptime > week:
        return '{} month'.format(uptime_months, uptime_weeks)


def test_horizon_host_inventory_display(host_inventory_pg):
    """
    Test the hosts inventory display:

    Setups:
        - Login as Admin
        - Go to Admin > Platform > Host Inventory

    Test Steps:
        - Test host tables display

    Teardown:
        - Back to Host Inventory page
        - Logout

    """
    LOG.tc_step('Test host inventory display')
    host_inventory_pg.go_to_hosts_tab()
    host_list = system_helper.get_hostnames()
    for host_name in host_list:

        fields = list(host_inventory_pg.hosts_table(host_name).HOST_TABLE_HEADERS_MAP.keys())
        expt_values = host_helper.get_hostshow_values(host_name, fields)
        expt_values['uptime'] = format_uptime(expt_values['uptime'])
        if expt_values.get('peers') is not None:
            expt_values['peers'] = eval(expt_values.get('peers')).get('name')
        horizon_vals = host_inventory_pg.horizon_vals(host_name)
        headers_map = host_inventory_pg.hosts_table(host_name).HOST_TABLE_HEADERS_MAP
        for field in headers_map:
            expt_val = expt_values[field]
            horizon_header = headers_map[field]
            horizon_val = horizon_vals[horizon_header]
            if field == 'uptime':
                # Extract the time value(int) from time string, eg: '2 days, 8 hours' --> [2, 8]
                horizon_t = [int(s) for s in horizon_val.split() if s.isdigit()]
                cli_t = [int(s) for s in expt_val.split() if s.isdigit()]
                if 0 in cli_t:
                    cli_t.remove(0)
                assert horizon_t == cli_t, 'Uptime display incorrectly'
            else:
                assert expt_val.upper() in horizon_val.upper(),\
                    '{} display incorrectly, expect: {} actual: {}'.format(horizon_header, expt_val, horizon_val)


horizon.test_result = True


@mark.parametrize('host_name', ['controller-0'])
def test_horizon_host_details_display(host_inventory_pg, host_name):
    """
    Test the host details display:

    Setups:
        - Login as Admin
        - Go to Admin > Platform > Host Inventory > Controller-0

    Test Steps:
        - Test host controller-0 overview display
        - Test host controller-0 processor display
        - Test host controller-0 memory display
        - Test host controller-0 storage display
        - Test host controller-0 ports display
        - Test host controller-0 lldp display

    Teardown:
        - Logout
    """
    host_table = host_inventory_pg.hosts_table(host_name)
    host_details_pg = host_inventory_pg.go_to_host_detail_page(host_name)
#   --------------------------------------OVERVIEW TAB------------------------------------------------------------------
    LOG.tc_step('Test host: {} overview display'.format(host_name))
    host_details_pg.go_to_overview_tab()
    horizon_vals = host_details_pg.host_detail_overview(host_table.driver).get_content()
    fields_map = host_details_pg.host_detail_overview(host_table.driver).OVERVIEW_INFO_HEADERS_MAP
    cli_host_vals = host_helper.get_hostshow_values(host_name, fields_map.keys())
    for field in fields_map:
        horizon_header = fields_map[field]
        cli_host_val = cli_host_vals[field]
        horizon_val = horizon_vals.get(horizon_header)
        if horizon_val is None:
            horizon_val = 'None'
            assert cli_host_val == horizon_val, '{} display incorrectly'.format(horizon_header)
        else:
            assert cli_host_val.upper() in horizon_val.upper(), '{} display incorrectly'.format(horizon_header)
    LOG.info('Host: {} overview display correct'.format(host_name))

#   --------------------------------------PROCESSOR TAB-----------------------------------------------------------------
    LOG.tc_step('Test host {} processor display'.format(host_name))
    host_details_pg.go_to_processor_tab()
    cpu_table = table_parser.table(cli.system('host-cpu-list {}'.format(host_name)))
    expt_cpu_info = {}
    expt_cpu_info['Processor Model:'] = table_parser.get_values(cpu_table, 'processor_model')[0]
    expt_cpu_info['Processors:'] = str(len(set(table_parser.get_values(cpu_table, 'processor'))))
    horizon_cpu_info = host_details_pg.inventory_details_processor_info.get_content()
    assert horizon_cpu_info['Processor Model:'] == expt_cpu_info['Processor Model:']
    assert horizon_cpu_info['Processors:'] == expt_cpu_info['Processors:']

#   --------------------------------------MEMORY TABLE------------------------------------------------------------------
    LOG.tc_step('Test host {} memory display'.format(host_name))
    checking_list = ['mem_total(MiB)', 'mem_avail(MiB)']

    host_details_pg.go_to_memory_tab()
    memory_table = table_parser.table(cli.system('host-memory-list {}'.format(host_name)))
    colume_names = host_details_pg.memory_table.column_names
    processor_list = table_parser.get_values(memory_table, colume_names[0])
    cli_memory_table_dict = table_parser.row_dict_table(memory_table, colume_names[0], lower_case=False)

    for processor in processor_list:
        horizon_vm_pages_val = host_details_pg.get_memory_table_info(processor, colume_names[2])
        horizon_memory_val = host_details_pg.get_memory_table_info(processor, 'Memory')
        if cli_memory_table_dict[processor]['hugepages(hp)_configured'] == 'False':
            assert horizon_vm_pages_val is None, 'Horizon {} display incorrectly'.format(colume_names[2])
        else:
            for field in checking_list:
                assert cli_memory_table_dict[processor][field] in horizon_memory_val, 'Memory {} display incorrectly'

#   --------------------------------------STORAGE TABLE-----------------------------------------------------------------
#   This test will loop each table and test their display
#   Test may fail in following case:
#   1. disk table's Size header eg. Size(GiB) used different unit such as Size (MiB), Size (TiB)
#   2. lvg table may display different:
#       Case 1: Name | State | Access | Size (GiB) | Avail Size(GiB) | Current Physical Volume - Current Logical Volumes
#       Case 2: Name | State | Access | Size                         | Current Physical Volume - Current Logical Volumes
#   Case 2 Size values in horizon are rounded by 2 digits but in CLI not rounded

    LOG.tc_step('Test host {} storage display'.format(host_name))
    host_details_pg.go_to_storage_tab()

    cmd_list = ['host-disk-list {}'.format(host_name), 'host-disk-partition-list {}'.format(host_name),
                'host-lvg-list {}'.format(host_name), 'host-pv-list {}'.format(host_name)]
    table_names = ['disk table', 'disk partition table', 'local volume groups table', 'physical volumes table']

    horizon_storage_tables = [host_details_pg.storage_disks_table,
                              host_details_pg.storage_partitions_table,
                              host_details_pg.storage_lvg_table,
                              host_details_pg.storage_pv_table]
    cli_storage_tables = []
    for cmd in cmd_list:
        cli_storage_tables.append(table_parser.table(cli.system(cmd)))

    for i in range(len(horizon_storage_tables)):
        horizon_table = horizon_storage_tables[i]
        unique_key = horizon_table.column_names[0]
        horizon_row_dict_table = host_details_pg.get_horizon_row_dict(horizon_table, key_header_index=0)
        cli_table = cli_storage_tables[i]
        table_dict_unique_key = list(horizon_table.HEADERS_MAP.keys())[
            list(horizon_table.HEADERS_MAP.values()).index(unique_key)]

        cli_row_dict_storage_table = table_parser.row_dict_table(cli_table, table_dict_unique_key, lower_case=False)
        for key_header in horizon_row_dict_table:
            for cli_header in horizon_table.HEADERS_MAP:
                horizon_header = horizon_table.HEADERS_MAP[cli_header]
                horizon_row_dict = horizon_row_dict_table[key_header]
                cli_row_dict = cli_row_dict_storage_table[key_header]
                # Solve parser issue: e.g. Size (GiB)' should be '558.029' not ['5589.', '029']
                cli_val = cli_row_dict[cli_header]
                if isinstance(cli_val, list):
                    cli_row_dict[cli_header] = ''.join(cli_val)
                assert horizon_row_dict[horizon_header] == cli_row_dict[cli_header], \
                    'In {}: disk: {} {} display incorrectly'.format(table_names[i], key_header, horizon_header)
        LOG.info('{} display correct'.format(table_names[i]))

#   --------------------------------------PORT TABLE--------------------------------------------------------------------
    LOG.tc_step('Test host {} port display'.format(host_name))
    host_details_pg.go_to_ports_tab()
    horizon_port_table = host_details_pg.ports_table()
    cli_port_table = table_parser.table(cli.system('host-ethernet-port-list {}'.format(host_name)))
    horizon_row_dict_port_table = host_details_pg.get_horizon_row_dict(horizon_port_table, key_header_index=0)

    cli_row_dict_port_table = table_parser.row_dict_table(cli_port_table, 'name', lower_case=False)
    for ethernet_name in cli_row_dict_port_table:
        for cli_header in horizon_port_table.HEADERS_MAP:
            horizon_header = horizon_port_table.HEADERS_MAP[cli_header]
            horizon_row_dict = horizon_row_dict_port_table[ethernet_name]
            cli_row_dict = cli_row_dict_port_table[ethernet_name]
            cli_val = cli_row_dict[cli_header]
            horizon_val = horizon_row_dict[horizon_header]
            # Solve table parser issue: MAC Address returns list eg: ['a4:bf:01:35:4a:', '32']
            if isinstance(cli_val, list):
                cli_val = ''.join(cli_val)
            assert cli_val in horizon_val, '{} display incorrectly'.format(horizon_header)

#   --------------------------------------LLDP TABLE--------------------------------------------------------------------
    LOG.tc_step('Test host {} lldp display'.format(host_name))
    host_details_pg.go_to_lldp_tab()
    lldp_list_table = table_parser.table(cli.system('host-lldp-neighbor-list {}'.format(host_name)))
    lldp_uuid_list = table_parser.get_values(lldp_list_table, 'uuid')
    horizon_lldp_table = host_details_pg.lldp_table()
    cli_row_dict_lldp_table = {}
    horizon_row_dict_lldp_table = host_details_pg.get_horizon_row_dict(horizon_lldp_table, key_header_index=1)
    for uuid in lldp_uuid_list:
        cli_row_dict = {}
        lldp_show_table = table_parser.table(cli.system('lldp-neighbor-show {}'.format(uuid)))
        row_dict_key = table_parser.get_value_two_col_table(lldp_show_table, 'port_identifier')
        for cli_header in horizon_lldp_table.HEADERS_MAP:
            horizon_header = horizon_lldp_table.HEADERS_MAP[cli_header]
            horizon_row_dict = horizon_row_dict_lldp_table[row_dict_key]
            cli_row_dict[cli_header] = table_parser.get_value_two_col_table(lldp_show_table, cli_header)
            cli_row_dict_lldp_table[row_dict_key] = cli_row_dict
            assert cli_row_dict[cli_header] == horizon_row_dict[horizon_header], \
                'lldp neighbor:{} {} display incorrectly'.format(row_dict_key, horizon_header)

    horizon.test_result = True
