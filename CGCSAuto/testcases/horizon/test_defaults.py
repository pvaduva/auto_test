import random
from utils.horizon.regions import messages
from time import sleep
from utils.horizon.pages.admin.system import defaultspage
from pytest import fixture
from utils.horizon import helper
from utils.tis_log import LOG


class TestDefaults(helper.AdminTestCase):

    add_up = random.randint(1, 10)

    @fixture(scope='function')
    def defaults_pg(self, home_pg, request):
        LOG.fixture_step('Go to Admin > System > Defaults')
        defaults_pg = defaultspage.DefaultsPage(home_pg.driver)
        defaults_pg.go_to_target_page()

        def teardown():
            LOG.fixture_step('Back to Defaults page')
            defaults_pg.go_to_target_page()

        request.addfinalizer(teardown)
        return defaults_pg

    def test_update_defaults(self, defaults_pg):
        """Tests the Update Default Quotas functionality:

        Setups:
            - Login as Admin
            - Go to Admin > System > Defaults

        Teardown:
            - Back to Defaults page
            - Logout

        Test Steps:
            - Updates default Quotas by adding a random number between 1 and 10
            - Verifies that the updated values are present in the
               Quota Defaults table
            - Updates default Quotas back to original status
        """
        default_quota_values = defaults_pg.quota_values

        LOG.tc_step('Updates default Quotas by add {}.'.format(self.add_up))
        defaults_pg.update_defaults(self.add_up)
        assert defaults_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not defaults_pg.find_message_and_dismiss(messages.ERROR)

        LOG.tc_step('Verifies that the updated values are present in the Quota Defaults table')
        assert len(default_quota_values) > 0
        for quota_name in default_quota_values:
            assert defaults_pg.is_quota_a_match(quota_name,
                                                default_quota_values[quota_name]
                                                + self.add_up)
        LOG.tc_step('Updates default Quotas back to original status')
        sleep(1)
        defaults_pg.update_defaults(-self.add_up)
