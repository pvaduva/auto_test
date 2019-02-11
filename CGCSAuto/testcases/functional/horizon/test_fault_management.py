from utils.horizon.regions import messages
from utils.horizon.pages.admin.fault_management import eventssuppressionpage
from pytest import fixture, mark
from testfixtures.horizon import admin_home_pg, driver
from utils.tis_log import LOG
from consts import horizon


@fixture(scope='function')
def events_suppression_pg(admin_home_pg, request):
    LOG.fixture_step('Go to Admin > Fault Management > Events Suppression')
    events_suppression_pg = eventssuppressionpage.EventsSuppressionPage(admin_home_pg.driver)
    events_suppression_pg.go_to_target_page()

    def teardown():
        LOG.fixture_step('Back to Events Suppression page')
        events_suppression_pg.go_to_target_page()

    request.addfinalizer(teardown)
    return events_suppression_pg


@mark.parametrize('event_id', ['100.101'])
def test_suppress_event(events_suppression_pg, event_id):
    """
        Test Steps:
        -Suppress event
        -Check for success message
        -Unsuppress event
        -Check for success message
    """
    events_suppression_pg.suppress_event(event_id)
    assert events_suppression_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not events_suppression_pg.find_message_and_dismiss(messages.ERROR)

    events_suppression_pg.unsuppress_event(event_id)
    assert events_suppression_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not events_suppression_pg.find_message_and_dismiss(messages.ERROR)
    horizon.test_result = True
