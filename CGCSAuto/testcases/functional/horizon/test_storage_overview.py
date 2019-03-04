from pytest import fixture, skip, mark

from consts import horizon
from keywords import system_helper, storage_helper
from utils import table_parser, cli
from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient
from utils.horizon.pages.admin.platform import storageoverviewpage


@fixture(scope='module')
def storage_precheck():
    if not system_helper.is_storage_system():
        skip('This test only applies to storage systems')


@fixture()
def storage_overview_pg(storage_precheck, admin_home_pg):
    LOG.fixture_step('Go to Admin > Platform > Storage Overview')
    storage_overview_pg = storageoverviewpage.StorageOverviewPage(admin_home_pg.driver)
    storage_overview_pg.go_to_target_page()

    return storage_overview_pg


@mark.usefixtures('storage_precheck')
def test_horizon_storage_overview_service_display(storage_overview_pg):
    """
    Tests the storage overview display:

    Setups:
        - Login as Admin
        - Go to Admin > Platform > Storage Overview

    Teardown:
        - Logout

    Test Steps:
        - Test Storage cluster UUID, Health Status and Details display
        - Test host and rank table display
        - Test osd.# table and status display
    """
    storage_overview_pg.go_to_services_tab()
    con_ssh = ControllerClient.get_active_controller()
    LOG.tc_step('Check storage cluster UUID, ceph health and storage usage display')
    cli_storage_service_info = []

    uuid = system_helper.get_cluster_values(header='cluster_uuid')[0]
    cli_storage_service_info.append(uuid)

#   'ceph health' cmd output sample:
#   HEALTH_ERR 1728 pgs are stuck inactive for more than 300 seconds; 1728 pgs stuck inactive; 1728 pgs stuck unclean;\
#   1 mons down, quorum 0,1 controller-0,controller-1
    health_details = con_ssh.exec_cmd('ceph health')[1]
    health_status = health_details.split(' ')[0]
    cli_storage_service_info.append(health_status)

    if health_status == 'HEALTH_ERR':
        health_details = health_details.split('HEALTH_ERR ')[1]
    cli_storage_service_info.append(health_details)

    horizon_ceph_info = storage_overview_pg.storage_service_info.get_content()
    for info in cli_storage_service_info:
        assert info in horizon_ceph_info.values(), 'Horizon storage cluster info does not match to cli info'
    LOG.tc_step('Storage service details display correct')

    LOG.info('Test host and rank table display')
    ceph_mon_status = eval(con_ssh.exec_cmd('ceph mon_status')[1])
    mon_map = ceph_mon_status.get('monmap')
    cli_ceph_monitor = {}
    # mon_map.get('mons') returns a dict list
    for mon_info_dict in mon_map.get('mons'):
        host_name = mon_info_dict.get('name')
        host_rank = mon_info_dict.get('rank')
        cli_ceph_monitor[host_name] = str(host_rank)

    for host_name in cli_ceph_monitor.keys():
        cli_rank_val = cli_ceph_monitor[host_name]
        horizon_rank_val = storage_overview_pg.get_storage_overview_monitor_info(host_name, 'Rank')
        assert horizon_rank_val == cli_rank_val, '{} rank display incorrectly'.format(host_name)

    LOG.info('Host and rank table table display correct')

    LOG.tc_step('Test osd table and status display')
    osd_list = storage_helper.get_osds()
    for osd_id in osd_list:
        expt_horizon = {}
        for header in storage_overview_pg.osds_table.column_names:
            host_name = storage_helper.get_osd_host(osd_id)[0]
            osd_name = 'osd.{}'.format(osd_id)
            expt_horizon['Host'] = host_name
            expt_horizon['Name'] = osd_name
            expt_horizon['Status'] = 'up'
            if not storage_helper.is_osd_up(osd_id, con_ssh):
                expt_horizon['Status'] = 'down'
            horizon_val = storage_overview_pg.get_storage_overview_osd_info(osd_name, header)
            assert expt_horizon[header] == horizon_val, '{}{} display incorrect'.format(osd_name, header)
    LOG.info('Osd table display correct')
    horizon.test_result = True


def test_horizon_storage_overview_usage_display(storage_overview_pg):
    """
    Tests the storage overview display:

    Setups:
        - Login as Admin
        - Go to Admin > Platform > Storage Overview

    Teardown:
        - Logout

    Test Steps:
        - Test backend type and name, service name, total capacity and free capacity(GiB) display
    """
    LOG.tc_step('Test usage details display')
    storage_overview_pg.go_to_usage_tab()
    usage_table = table_parser.table(cli.system('storage-usage-list --nowrap'))
    horizon_headers = ['Backend type', 'Backend name', 'Service name', 'Free Capacity (GiB)', 'Total Capacity (GiB)']
    rows = storage_overview_pg.get_rows_from_usage_table()
    horizon_rows_val = []
    for row in rows:
        row_dict = []
        for header in horizon_headers:
            row_dict.append(row.cells[header].text)
        horizon_rows_val.append(row_dict)
    cli_rows_val = usage_table.get('values')

    for row in cli_rows_val:
        assert row in horizon_rows_val, 'row {} not found in usage table.'.format(row)

    LOG.info('Storage overview usage details display correct')
    horizon.test_result = True
