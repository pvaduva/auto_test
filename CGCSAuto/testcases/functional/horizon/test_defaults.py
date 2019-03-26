import random
import time

from pytest import fixture

from consts import horizon
from utils.horizon.regions import messages
from utils.horizon.pages.admin.system import defaultspage
from utils.tis_log import LOG


@fixture(scope='function')
def defaults_pg(admin_home_pg_container, request):

    LOG.fixture_step('Go to Admin > System > Defaults')
    default_pg = defaultspage.DefaultsPage(admin_home_pg_container.driver, port=admin_home_pg_container.port)
    default_pg.go_to_target_page()

    def teardown():
        LOG.fixture_step('Back to Defaults page')
        default_pg.go_to_target_page()

    request.addfinalizer(teardown)
    return default_pg


def test_horizon_update_compute_defaults(defaults_pg):
    """
    Tests the Update Compute Default Quotas functionality:

    Setups:
        - Login as Admin
        - Go to Admin > System > Defaults

    Teardown:
        - Back to Defaults page
        - Logout

    Test Steps:
        - Go to Compute Quotas Tab
        - Updates default Compute Quotas by adding a random number between 1 and 10
        - Verifies that the updated values are present in the
           Quota Compute Defaults table
        - Updates default Compute Quotas back to original status
        - Go to Volume Quotas Tab
        - Updates default Volume Quotas by adding a random number between 1 and 10
        - Verifies that the updated values are present in the
           Quota Volume Defaults table
        - Updates default Volume Quotas back to original status
    """

    add_up = random.randint(1, 10)
    defaults_pg.go_to_compute_quotas_tab()
    default_compute_quota_values = defaults_pg.compute_quota_values

    LOG.tc_step('Updates default Compute Quotas by add {}.'.format(add_up))
    defaults_pg.update_compute_defaults(add_up)
    assert defaults_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not defaults_pg.find_message_and_dismiss(messages.ERROR)

    LOG.tc_step('Verifies that the updated values are present in the Quota Default Computes table')
    assert len(default_compute_quota_values) > 0
    for quota_name in default_compute_quota_values:
        assert defaults_pg.is_compute_quota_a_match(quota_name,
                                                    default_compute_quota_values[quota_name]
                                                    + add_up)
    LOG.tc_step('Updates default Compute Quotas back to original status')
    time.sleep(1)
    defaults_pg.update_compute_defaults(-add_up)

    defaults_pg.go_to_volume_quotas_tab()
    default_volume_quota_values = defaults_pg.volume_quota_values

    LOG.tc_step('Updates default Volume Quotas by add {}.'.format(add_up))
    defaults_pg.update_volume_defaults(add_up)
    assert defaults_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not defaults_pg.find_message_and_dismiss(messages.ERROR)

    LOG.tc_step('Verifies that the updated values are present in the Quota Default Volumes table')
    assert len(default_volume_quota_values) > 0
    for quota_name in default_volume_quota_values:
        assert defaults_pg.is_volume_quota_a_match(quota_name,
                                                   default_volume_quota_values[quota_name]
                                                   + add_up)
    LOG.tc_step('Updates default Volume Quotas back to original status')
    time.sleep(1)
    defaults_pg.update_volume_defaults(-add_up)
    horizon.test_result = True
