from pytest import fixture

from utils.horizon.pages.admin.platform import providernetworkstopology
from utils import table_parser, cli
from utils.tis_log import LOG
from consts.auth import Tenant
from consts import horizon
from keywords import network_helper
from testfixtures.horizon import admin_home_pg, driver


@fixture(scope='function')
def pnet_topology_pg(admin_home_pg):
    LOG.fixture_step('Go to Admin > Platform > Provider Network Topology')
    provider_networks_topology_pg = providernetworkstopology.ProviderNetworkTopologyPage(admin_home_pg.driver)
    provider_networks_topology_pg.go_to_target_page()

    return provider_networks_topology_pg


def _test_horizon_provider_network_topology(pnet_topology_pg):
    """
        Test the network lists and display host, prov. network details:

        Setups:
            - Login as Admin
            - Go to Admin > Platform > Provider Network Topology

        Teardown:
            - Back to Provider Network Topology page
            - Logout

        Test Steps:
            - Select a compute host from the list
            - Verify the overview,related alarms, interfaces and LLDP tags
            - Select a provider network from the list
            - Verify the provider network detail and related alarms tags

    """
    pnet_topology_pg.go_to_target_page()

    pnet_name_list = network_helper.get_providernets(rtn_val='name')
    table_ = table_parser.table(cli.neutron('providernet-list', auth_info=Tenant.get('admin')))
    cli_row_dict_table = table_parser.row_dict_table(table_,'id')
    pnet_select = pnet_topology_pg.providernet_list.select_element_by_name(pnet_name_list[0])

    form = pnet_topology_pg.go_to_pnet_overview('group0-data0')

    pnet_detail_dict = pnet_topology_pg.providernet_detail
    pass




