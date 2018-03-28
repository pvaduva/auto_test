from utils.horizon.regions import messages
from utils.horizon.pages.admin.platform import hostinventorypage
from pytest import fixture, mark
from utils.horizon import helper
from utils.tis_log import LOG


class TestHosts(helper.AdminTestCase):

    @fixture(scope='function')
    def host_inventory_pg(self, home_pg, request):
        LOG.fixture_step('Go to Admin > Platform > Host Inventory')
        host_inventory_pg = hostinventorypage.HostInventoryPage(home_pg.driver)
        host_inventory_pg.go_to_target_page()

        def teardown():
            LOG.fixture_step('Back to Host Inventory page')
            host_inventory_pg.go_to_target_page()

        request.addfinalizer(teardown)
        return host_inventory_pg

    @mark.parametrize('host_name', [
        # 'controller-1', 'compute-2'
    ])
    def test_host_lock_unlock(self, host_inventory_pg, host_name):

        """
        Test the host lock and unlock functionality:

        Setups:
            - Login as Admin
            - Go to Admin > Platform > Host Inventory

        Teardown:
            - Back to Host Inventory page
            - Logout

        Test Steps:
            - Lock a host
            - Verify the host is locked
            - Unlock the host
            - Verify the host is available
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


