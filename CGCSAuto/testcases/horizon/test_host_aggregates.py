from utils.horizon.regions import messages
from utils.horizon.pages.admin.compute import hostaggregatespage
from pytest import fixture
from utils.horizon import helper
from utils.tis_log import LOG


class TestHostAggregates(helper.AdminTestCase):
    HOST_AGGREGATE_NAME = helper.gen_resource_name('aggregate')
    HOST_AGGREGATE_AVAILABILITY_ZONE = "nova"

    @fixture(scope='function')
    def hostaggregates_pg(self, home_pg, request):
        LOG.fixture_step('Go to Admin > Compute > Host Aggregates')
        hostaggregates_pg = hostaggregatespage.HostaggregatesPage(home_pg.driver)
        hostaggregates_pg.go_to_target_page()

        def teardown():
            LOG.fixture_step('Back to Groups page')
            hostaggregates_pg.go_to_target_page()

        request.addfinalizer(teardown)
        return hostaggregates_pg

    def test_host_aggregate_create(self, hostaggregates_pg):
        """
        Test the host aggregate creation and deletion functionality:

        Setups:
            - Login as Admin
            - Go to Admin > Compute > Host Aggregates

        Teardown:
            - Back to Host Aggregates page
            - Logout

        Test Steps:
            - Create a new host aggregate
            - Verify the host aggregate appears in the host aggregates table
            - Delete the newly created host aggregate
            - Verify the host aggregate does not appear in the table after deletion
        """

        LOG.tc_step('Create a new host aggregate {}.'.format(self.HOST_AGGREGATE_NAME))
        hostaggregates_pg.create_host_aggregate(
            name=self.HOST_AGGREGATE_NAME,
            availability_zone=self.HOST_AGGREGATE_AVAILABILITY_ZONE)
        assert hostaggregates_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not hostaggregates_pg.find_message_and_dismiss(
            messages.ERROR)
        LOG.tc_step('Verify the host aggregate appears in the host aggregates table')
        assert hostaggregates_pg.is_host_aggregate_present(self.HOST_AGGREGATE_NAME)

        LOG.tc_step('Delete host aggregate {}.'.format(self.HOST_AGGREGATE_NAME))
        hostaggregates_pg.delete_host_aggregate(self.HOST_AGGREGATE_NAME)
        assert hostaggregates_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not hostaggregates_pg.find_message_and_dismiss(messages.ERROR)

        LOG.tc_step('Verify the host aggregate does not appear in the table after deletion')
        assert not hostaggregates_pg.is_host_aggregate_present(self.HOST_AGGREGATE_NAME)
