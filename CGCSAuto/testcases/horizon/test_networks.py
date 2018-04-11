from utils.horizon.regions import messages
from utils.horizon.pages.project.network import networkspage as pro_networkspage
from utils.horizon.pages.admin.network import networkspage as adm_networkspage
from pytest import fixture, mark
from utils.horizon import helper
from utils.tis_log import LOG


class TestNetworks(helper.TenantTestCase):

    NETWORK_NAME = None
    SUBNET_NAME = None

    @fixture(scope='function')
    def networks_pg(self, home_pg, request):
        self.NETWORK_NAME = helper.gen_resource_name('network')
        self.SUBNET_NAME = helper.gen_resource_name('subnet')
        LOG.fixture_step('Go to Project > Network > Networks')
        networks_pg = pro_networkspage.NetworksPage(home_pg.driver)
        networks_pg.go_to_target_page()

        def teardown():
            LOG.fixture_step('Back to Networks page')
            networks_pg.go_to_target_page()

        request.addfinalizer(teardown)

        return networks_pg

    def test_network_subnet_create_tenant(self, networks_pg):
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
        LOG.tc_step('Create new network {}.'.format(self.NETWORK_NAME))
        networks_pg.create_network(self.NETWORK_NAME,
                                   subnet_name=self.SUBNET_NAME,
                                   network_address='192.168.0.0/24')
        assert networks_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not networks_pg.find_message_and_dismiss(messages.ERROR)

        LOG.tc_step('Verify the network appears in the networks table as active')
        assert networks_pg.is_network_present(self.NETWORK_NAME)
        assert networks_pg.get_network_info(self.NETWORK_NAME, "Status") == "Active"

        LOG.tc_step('Delete network {}.'.format(self.NETWORK_NAME))
        networks_pg.delete_network_by_row(self.NETWORK_NAME)
        assert networks_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not networks_pg.find_message_and_dismiss(messages.ERROR)

        LOG.tc_step('Verify the network does not appear in the table after deletion')
        assert not networks_pg.is_network_present(self.NETWORK_NAME)


class TestNetworksAdmin(helper.AdminTestCase):
    NETWORK_NAME = None
    SUBNET_NAME = None

    @fixture(scope='function')
    def networks_pg(self, home_pg, request):
        self.NETWORK_NAME = helper.gen_resource_name('network')
        self.SUBNET_NAME = helper.gen_resource_name('subnet')
        LOG.fixture_step('Go to Admin > Network > Networks')
        networks_pg = adm_networkspage.NetworksPage(home_pg.driver)
        networks_pg.go_to_target_page()

        def teardown():
            LOG.fixture_step('Back to Networks page')
            networks_pg.go_to_target_page()

        request.addfinalizer(teardown)

        return networks_pg

    def test_network_subnet_create_admin(self, networks_pg):
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

        LOG.tc_step('Create new network {}.'.format(self.NETWORK_NAME))
        networks_pg.create_network(self.NETWORK_NAME,
                                   project='tenant1',
                                   provider_network_type='vlan',
                                   physical_network='group0-data0',
                                   subnet_name=self.SUBNET_NAME,
                                   network_address='192.168.0.0/24')
        assert networks_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not networks_pg.find_message_and_dismiss(messages.ERROR)

        LOG.tc_step('Verify the network appears in the networks table as active')
        assert networks_pg.is_network_present(self.NETWORK_NAME)
        assert networks_pg.get_network_info(self.NETWORK_NAME, 'Status') == 'Active'

        LOG.tc_step('Delete network {}.'.format(self.NETWORK_NAME))
        networks_pg.delete_network_by_row(self.NETWORK_NAME)
        assert networks_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not networks_pg.find_message_and_dismiss(messages.ERROR)

        LOG.tc_step('Verify the network does not appear in the table after deletion')
        assert not networks_pg.is_network_present(self.NETWORK_NAME)
