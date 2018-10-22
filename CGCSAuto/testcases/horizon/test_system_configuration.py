from pytest import fixture, skip, mark

from utils import cli, table_parser
from utils.tis_log import LOG
from utils.horizon import helper
from utils.horizon.pages.admin.platform import systemconfigurationpage
from consts import horizon
from keywords import system_helper, filesystem_helper
from testfixtures.horizon import admin_home_pg

TEST_ADDRESS_NAME = None


@fixture()
def storage_precheck():
    if not system_helper.is_storage_system():
        skip("This test only applies to storage nodes")


@fixture()
def sys_config_pg(admin_home_pg):
    LOG.fixture_step('Go to Admin > Platform > System Configuration')
    system_configuration_pg = systemconfigurationpage.SystemConfigurationPage(admin_home_pg.driver)
    system_configuration_pg.go_to_target_page()

    return system_configuration_pg


def test_horizon_sysconfig_system_display(sys_config_pg):

    """
    Test the systems tag details display:

    Setups:
        - Login as Admin
        - Go to Admin > Platform > System Configuration

    Teardown:
        - Back to System Configuration Page
        - Logout

    Test Steps:
        - Check systems display
    """
    LOG.tc_step('Check system details display')
    headers_map = sys_config_pg.systems_table.SYSTEMS_MAP
    expt_horizon = {}
    for cli_header in headers_map:
        horizon_header = headers_map[cli_header]
        expt_horizon[horizon_header] = system_helper.get_system_value(cli_header)
    table_name = sys_config_pg.systems_table.name
    sys_config_pg.check_horizon_displays(table_name=table_name, expt_horizon=expt_horizon)
    horizon.test_result = True


def test_horizon_sysconfig_addrpool_add_delete(sys_config_pg):

    """
    Test the address pools edit and display:

    Setups:
        - Login as Admin
        - Go to Admin > Platform > System Configuration

    Teardown:
        - Back to System Configuration Page
        - Logout

    Test Steps:
        - Check address pools display
        - Create a new address pool
        - Check the address pool is in the list
        - Delete the address pool
        - Check the address pool is absent in the list
    """
    sys_config_pg.go_to_address_pools_tab()
    LOG.tc_step('Check address pools display')
    addr_table = table_parser.table(cli.system('addrpool-list'))
    uuid_list = table_parser.get_values(addr_table, target_header='uuid')
    for uuid in uuid_list:
        expt_horizon = {}
        name = table_parser.get_values(addr_table, target_header='name', **{'uuid': uuid})[0]
        expt_horizon['Name'] = name

        prefix = table_parser.get_values(addr_table, target_header='prefix', **{'uuid': uuid})[0]
        cli_network_val = table_parser.get_values(addr_table, 'network', **{'uuid': uuid})
        cli_network_val = cli_network_val[0][0] + cli_network_val[0][1] + '/' + prefix
        expt_horizon['Network'] = cli_network_val

        cli_order_val = table_parser.get_values(addr_table, 'order', **{'uuid': uuid})[0]
        expt_horizon['Allocation Order'] = cli_order_val

        cli_ranges_list = eval(table_parser.get_values(addr_table, 'ranges', **{'uuid': uuid})[0])
        cli_ranges = ','.join(cli_ranges_list)
        expt_horizon['Address Ranges'] = cli_ranges
        table_name = sys_config_pg.address_pools_table.name
        sys_config_pg.check_horizon_displays(table_name=table_name, expt_horizon=expt_horizon)

    LOG.tc_step('Create a new address pool')
    address_name = helper.gen_resource_name('address_name')
    sys_config_pg.create_address_pool(name=address_name, network='192.168.0.0/24')
    assert sys_config_pg.is_address_present(address_name)

    LOG.tc_step('Delete the address pool')
    sys_config_pg.delete_address_pool(address_name)

    LOG.tc_step('Check the address pool is absent in the list')
    assert not sys_config_pg.is_address_present(address_name)
    horizon.test_result = True


def test_horizon_sysconfig_dns_cancel_edit(sys_config_pg):

    """
    Test dns edit and display:

    Setups:
        - Login as Admin
        - Go to Admin > Platform > System Configuration

    Teardown:
        - Back to System Configuration Page
        - Logout

    Test Steps:
        - Check DNS display
        - Edit DNS but not submit
    """
    LOG.tc_step('check DNS display')
    sys_config_pg.go_to_dns_tab()
    dns_list = system_helper.get_dns_servers()
    for i in range(len(dns_list)):
        cli_dns = dns_list[i]
        horizon_dns = sys_config_pg.get_dns_info(ip=dns_list[0], header='DNS Server {} IP'.format(i+1))
        assert cli_dns == horizon_dns, 'DNS Server {} IP display incorrectly'

    LOG.tc_step('Edit DNS but not submit')
    sys_config_pg.edit_dns(cancel=True)
    horizon.test_result = True


def test_horizon_sysconfig_ntp_cancel_edit(sys_config_pg):

    """
    Test ntp edit and display:

    Setups:
        - Login as Admin
        - Go to Admin > Platform > System Configuration

    Teardown:
        - Back to System Configuration Page
        - Logout

    Test Steps:
        - Check NTP details display
        - Edit DNS but not submit
    """
    LOG.tc_step('Check NTP display')
    sys_config_pg.go_to_ntp_tab()
    ntp_addr_list = system_helper.get_ntp_vals()[0].split(',')
    for i in range(len(ntp_addr_list)):
        cli_ntp = ntp_addr_list[i]
        horizon_ntp = sys_config_pg.get_ntp_info(addr=ntp_addr_list[0], header='NTP Server {} Address'.format(i+1))
        assert cli_ntp == horizon_ntp, 'NTP Server {} Address display incorrectly'.format(i+1)

    LOG.tc_step('Edit NTP but not submit')
    sys_config_pg.edit_ntp(cancel=True)
    horizon.test_result = True


def test_horizon_sysconfig_ptp_cancel_edit(sys_config_pg):

    """
    Test ptp edit and display:

    Setups:
        - Login as Admin
        - Go to Admin > Platform > System Configuration

    Teardown:
        - Back to System Configuration Page
        - Logout

    Test Steps:
        - Check PTP details display
        - Edit PTP but not submit
    """
    sys_config_pg.go_to_ptp_tab()
    LOG.tc_step('Check PTP display')
    headers_map = sys_config_pg.ptp_table.PTP_MAP
    cli_headers = list(headers_map.keys())
    cli_vals = system_helper.get_ptp_vals(cli_headers)
    expt_horizon = {}
    for i in range(len(cli_headers)):
        horizon_header = headers_map[cli_headers[i]]
        expt_horizon[horizon_header] = cli_vals[i]
    table_name = sys_config_pg.ptp_table.name
    sys_config_pg.check_horizon_displays(expt_horizon = expt_horizon, table_name = table_name)

    LOG.tc_step('Edit PTP but not submit')
    sys_config_pg.edit_ptp(cancel=True)
    horizon.test_result = True


def test_horizon_sysconfig_oam_cancel_edit(sys_config_pg):

    """
    Test oam edit and display:

    Setups:
        - Login as Admin
        - Go to Admin > Platform > System Configuration

    Teardown:
        - Back to System Configuration Page
        - Logout

    Test Steps:
        - Check oam details display
        - Edit the OAM but not submit
    """
    LOG.tc_step('Check OAM IP display')
    sys_config_pg.go_to_oam_ip_tab()
    oam_table = table_parser.table(cli.system('oam-show'))
    expt_horizon = {}
    if system_helper.get_system_value(field='system_mode') == 'simplex':
        headers_map = sys_config_pg.oam_table.SIMPLEX_OAM_MAP
    else:
        headers_map = sys_config_pg.oam_table.OAM_MAP
    for cli_header in headers_map:
        horizon_header = headers_map[cli_header]
        expt_horizon[horizon_header] = table_parser.get_value_two_col_table(oam_table, field=cli_header)
    table_name = sys_config_pg.oam_table.name
    sys_config_pg.check_horizon_displays(table_name=table_name, expt_horizon=expt_horizon)


    LOG.tc_step('Edit the OAM but not submit')
    sys_config_pg.edit_oam(cancel=True)
    horizon.test_result = True


def test_horizon_sysconfig_controllerfs_cancel_edit(sys_config_pg):
    """
    Test controller filesystem edit and display:

    Setups:
        - Login as Admin
        - Go to Admin > Platform > System Configuration

    Teardown:
        - Back to System Configuration Page
        - Logout

    Test Steps:
        - Check storage name and its size
        - Edit controller filesystem but not submit
    """
    LOG.tc_step('Check controller filesystem display')
    sys_config_pg.go_to_controller_filesystem_tab()
    controllerfs_table = table_parser.table(cli.system('controllerfs-list'))
    headers_map = sys_config_pg.controllerfs_table.CONTROLERFS_MAP
    storage_names = table_parser.get_values(controllerfs_table, target_header='FS Name')
    for name in storage_names:
        expt_horzion = {}
        for cli_header in headers_map:
            horizon_header = headers_map[cli_header]
            expt_horzion[horizon_header] = filesystem_helper.get_controllerfs(filesystem=name, rtn_value=cli_header)
        table_name = sys_config_pg.controllerfs_table.name
        sys_config_pg.check_horizon_displays(table_name=table_name, expt_horizon=expt_horzion)

    LOG.tc_step('Edit controller filesystem but not submit')
    sys_config_pg.edit_filesystem(cancel=True)
    horizon.test_result = True


@mark.usefixtures('storage_precheck')
def test_horizon_sysconfig_ceph_storage_pools_cancel_edit(sys_config_pg):

    """
    Test ceph storage pools edit and display:

    Setups:
        - Login as Admin
        - Go to Admin > Platform > System Configuration

    Teardown:
        - Back to System Configuration Page
        - Logout

    Test Steps:
        - Check ceph storage pools display
        - Edit ceph storage pools but not submit
    """
    LOG.tc_step('Check ceph storage pools display')
    sys_config_pg.go_to_ceph_storage_pools_tab()
    ceph_table = table_parser.table(cli.system('storage-backend-show ceph-store'))
    expt_horizon = {}
    headers_map = sys_config_pg.ceph_storage_pools_table.CEPH_STORAGE_POOLS_MAP
    table_name = sys_config_pg.ceph_storage_pools_table.name
    for cli_header in headers_map:
        horizon_header = headers_map[cli_header]
        cli_val = table_parser.get_value_two_col_table(ceph_table, field=cli_header)
        if cli_val != 'None':
            expt_horizon[horizon_header] = cli_val
        else:
            expt_horizon[horizon_header] = '-'
    sys_config_pg.check_horizon_displays(table_name=table_name, expt_horizon=expt_horizon)

    LOG.tc_step('Edit ceph storage pools but not submit')
    tier_name = expt_horizon.get('Ceph Storage Tier')
    sys_config_pg.edit_storage_pool(tier_name=tier_name, cancel=True)
    horizon.test_result = True
