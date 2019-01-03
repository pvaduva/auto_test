from pytest import fixture

from consts import horizon
from utils.tis_log import LOG
from utils.horizon.regions import messages
from utils.horizon.pages.admin.compute import hostaggregatespage


@fixture(scope='function')
def host_aggregates_pg(admin_home_pg_container, request):
    LOG.fixture_step('Go to Admin > Compute > Host Aggregates')
    hostaggregates_pg = hostaggregatespage.HostaggregatesPage(admin_home_pg_container.driver, port=admin_home_pg_container.port)
    hostaggregates_pg.go_to_target_page()

    def teardown():
        LOG.fixture_step('Back to Groups page')
        hostaggregates_pg.go_to_target_page()

    request.addfinalizer(teardown)
    return hostaggregates_pg


def test_host_aggregate_create(host_aggregates_pg):
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

    LOG.tc_step('Create a new host aggregate')
    host_aggregate_name = host_aggregates_pg.create_host_aggregate()
    assert host_aggregates_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not host_aggregates_pg.find_message_and_dismiss(
        messages.ERROR)
    LOG.tc_step('Verify the host aggregate appears in the host aggregates table')
    assert host_aggregates_pg.is_host_aggregate_present(host_aggregate_name)

    LOG.tc_step('Delete host aggregate {}.'.format(host_aggregate_name))
    host_aggregates_pg.delete_host_aggregate(host_aggregate_name)
    assert host_aggregates_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not host_aggregates_pg.find_message_and_dismiss(messages.ERROR)

    LOG.tc_step('Verify the host aggregate does not appear in the table after deletion')
    assert not host_aggregates_pg.is_host_aggregate_present(host_aggregate_name)
    horizon.test_result = True
