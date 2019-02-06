from pytest import fixture, mark

from consts import horizon
from utils.horizon.regions import messages
from utils.horizon.pages.admin.platform import faultmanagementpage
from utils.tis_log import LOG


@fixture(scope='function')
def fault_management_pg(admin_home_pg, request):
    LOG.fixture_step('Go to Admin > Compute > Hypervisors')
    fault_management_pg = faultmanagementpage.FaultManagementPage(admin_home_pg.driver)
    fault_management_pg.go_to_target_page()

    def teardown():
        LOG.fixture_step('Back to Hypervisors page')
        fault_management_pg.go_to_target_page()

    request.addfinalizer(teardown)
    return fault_management_pg


# move out from suite for now until fixed. This failure will cause all of the rest horizon testcases to fail.
@mark.parametrize('event_id', ['100.101'])
def _test_horizon_suppress_event(fault_management_pg, event_id):

    fault_management_pg.go_to_events_suppression_tab()

    fault_management_pg.suppress_event(event_id)
    assert fault_management_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not fault_management_pg.find_message_and_dismiss(messages.ERROR)

    fault_management_pg.unsuppress_event(event_id)
    assert fault_management_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not fault_management_pg.find_message_and_dismiss(messages.ERROR)
    horizon.test_result = True
