from utils.horizon.regions import messages
from utils.horizon.pages.project.network import networkspage as pro_networkspage
from utils.horizon.pages.admin.network import networkspage as adm_networkspage
from utils.horizon import helper
from pytest import fixture
from testfixtures.horizon import tenant_home_pg, admin_home_pg, driver
from utils.tis_log import LOG
from consts import horizon


@fixture(scope='function')
def project_networks_pg(tenant_home_pg, request):
    LOG.fixture_step('Go to Project > Network > Networks')
    networks_pg = pro_networkspage.NetworksPage(tenant_home_pg.driver)
    networks_pg.go_to_target_page()

    def teardown():
        LOG.fixture_step('Back to Networks page')
        networks_pg.go_to_target_page()

    request.addfinalizer(teardown)

    return networks_pg


def test_network_subnet_create_tenant(project_networks_pg):
    """
    Test the network creation and deletion functionality:

    Setups:
        - Login as Tenant
        - Go to Project > Network > Networks

    Teardown:
        - Back to Networks page
        - Logout

    Test Steps:
        - Create a new network with subnet
        - Verify the network appears in the networks table as active
        - Delete the newly created network
        - Verify the network does not appear in the table after deletion
    """
    network_name = helper.gen_resource_name('network')
    subnet_name = helper.gen_resource_name('subnet')
    LOG.tc_step('Create new network {}.'.format(network_name))
    project_networks_pg.create_network(network_name,
                                       subnet_name=subnet_name,
                                       network_address='192.168.0.0/24')
    assert project_networks_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not project_networks_pg.find_message_and_dismiss(messages.ERROR)

    LOG.tc_step('Verify the network appears in the networks table as active')
    assert project_networks_pg.is_network_present(network_name)
    assert project_networks_pg.get_network_info(network_name, "Status") == "Active"

    LOG.tc_step('Delete network {}.'.format(network_name))
    project_networks_pg.delete_network_by_row(network_name)
    assert project_networks_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not project_networks_pg.find_message_and_dismiss(messages.ERROR)

    LOG.tc_step('Verify the network does not appear in the table after deletion')
    assert not project_networks_pg.is_network_present(network_name)
    horizon.test_result = True


@fixture(scope='function')
def admin_networks_pg(admin_home_pg, request):
    LOG.fixture_step('Go to Admin > Network > Networks')
    networks_pg = adm_networkspage.NetworksPage(admin_home_pg.driver)
    networks_pg.go_to_target_page()

    def teardown():
        LOG.fixture_step('Back to Networks page')
        networks_pg.go_to_target_page()

    request.addfinalizer(teardown)

    return networks_pg


def test_network_subnet_create_admin(admin_networks_pg):
    """
    Test the network creation and deletion functionality:

    Setups:
        - Login as Admin
        - Go to Admin > Network > Networks

    Teardown:
        - Back to Networks page
        - Logout

    Test Steps:
        - Create a new network with subnet
        - Verify the network appears in the networks table as active
        - Delete the newly created network
        - Verify the network does not appear in the table after deletion
    """
    network_name = helper.gen_resource_name('network')
    subnet_name = helper.gen_resource_name('subnet')
    LOG.tc_step('Create new network {}.'.format(network_name))
    admin_networks_pg.create_network(network_name,
                                     project='tenant1',
                                     provider_network_type='vlan',
                                     physical_network='group0-data0',
                                     subnet_name=subnet_name,
                                     network_address='192.168.0.0/24')
    assert admin_networks_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not admin_networks_pg.find_message_and_dismiss(messages.ERROR)

    LOG.tc_step('Verify the network appears in the networks table as active')
    assert admin_networks_pg.is_network_present(network_name)
    assert admin_networks_pg.get_network_info(network_name, 'Status') == 'Active'

    LOG.tc_step('Delete network {}.'.format(network_name))
    admin_networks_pg.delete_network_by_row(network_name)
    assert admin_networks_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not admin_networks_pg.find_message_and_dismiss(messages.ERROR)

    LOG.tc_step('Verify the network does not appear in the table after deletion')
    assert not admin_networks_pg.is_network_present(network_name)
    horizon.test_result = True
