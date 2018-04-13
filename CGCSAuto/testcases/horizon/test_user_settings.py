from utils.horizon.regions import messages
from utils.horizon.pages import loginpage
from time import sleep
from utils.horizon.pages.settings import usersettingspage
from utils.horizon.pages.settings import changepasswordpage
from pytest import fixture
from testfixtures.horizon import admin_home_pg, driver


class TestDashboardHelp:

    def test_dashboard_help_redirection(self, admin_home_pg):
        """Verifies Help link redirects to the right URL."""

        admin_home_pg.go_to_help_page()
        admin_home_pg._wait_until(
            lambda _: admin_home_pg.is_nth_window_opened(2))

        admin_home_pg.switch_window()
        sleep(2)
        assert 'http://www.windriver.com/support/' == \
               admin_home_pg.get_current_page_url()

        admin_home_pg.close_window()
        admin_home_pg.switch_window()


class TestPasswordChange:
    NEW_PASSWORD1 = "Li96nux*"
    NEW_PASSWORD2 = "LI69nux*"
    TEST_PASSWORD = 'Li69nux*'
    TEST_USER_NAME = 'admin'

    @fixture(scope='function')
    def password_change_pg(self, admin_home_pg):
        password_change_pg = changepasswordpage.ChangepasswordPage(admin_home_pg.driver)
        password_change_pg.go_to_target_page()
        return password_change_pg

    def test_password_change(self, password_change_pg):
        # Changes the password, verifies it was indeed changed and
        # resets to default password.
        # !!!!! the password cannot be change to previous password

        password_change_pg.change_password(self.TEST_PASSWORD, self.NEW_PASSWORD1)
        login_pg = loginpage.LoginPage(password_change_pg.driver)
        assert login_pg.is_logout_reason_displayed(), \
            "The logout reason message was not found on the login page"
        home_pg = login_pg.login(self.TEST_USER_NAME, self.NEW_PASSWORD1)
        assert home_pg.is_logged_in, "Failed to login with new password"
        password_change_pg.go_to_target_page()
        sleep(2)
        password_change_pg.change_password(self.NEW_PASSWORD1, self.NEW_PASSWORD2)
        assert login_pg.is_logout_reason_displayed(), \
            "The logout reason message was not found on the login page"
        home_pg = login_pg.login(self.TEST_USER_NAME, self.NEW_PASSWORD2)
        assert home_pg.is_logged_in, "Failed to login with new password"
        password_change_pg.go_to_target_page()
        sleep(2)
        password_change_pg.reset_to_default_password(self.NEW_PASSWORD2)
        home_pg = login_pg.login(self.TEST_USER_NAME, self.TEST_PASSWORD)
        assert home_pg.is_logged_in, "Failed to login with new password"


class TestUserSettings:

    @fixture(scope='function')
    def user_setting_pg(self, admin_home_pg):
        user_setting_pg = usersettingspage.UsersettingsPage(admin_home_pg.driver)
        user_setting_pg.go_to_target_page()
        return user_setting_pg

    def verify_user_settings_change(self, settings_page, changed_settings):
        language = settings_page.settings_form.language.value
        timezone = settings_page.settings_form.timezone.value
        pagesize = settings_page.settings_form.pagesize.value
        loglines = settings_page.settings_form.instance_log_length.value

        user_settings = (("Language", changed_settings["language"], language),
                         ("Timezone", changed_settings["timezone"], timezone),
                         ("Pagesize", changed_settings["pagesize"], pagesize),
                         ("Loglines", changed_settings["loglines"], loglines))

        for (setting, expected, observed) in user_settings:
            assert expected == observed, "expected %s: %s, instead found: %s"\
                                         % (setting, expected, observed)

    def test_user_settings_change(self, user_setting_pg):
        """tests the user's settings options:

        * changes the system's language
        * changes the timezone
        * changes the number of items per page (page size)
        * changes the number of log lines to be shown per instance
        * verifies all changes were successfully executed
        """

        user_setting_pg.change_language("es")
        assert user_setting_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not user_setting_pg.find_message_and_dismiss(messages.ERROR)

        user_setting_pg.change_timezone("Asia/Jerusalem")
        assert user_setting_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not user_setting_pg.find_message_and_dismiss(messages.ERROR)

        user_setting_pg.change_pagesize("30")
        assert user_setting_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not user_setting_pg.find_message_and_dismiss(messages.ERROR)

        user_setting_pg.change_loglines("50")
        assert user_setting_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not user_setting_pg.find_message_and_dismiss(messages.ERROR)

        changed_settings = {"language": "es", "timezone": "Asia/Jerusalem",
                            "pagesize": "30", "loglines": "50"}
        self.verify_user_settings_change(user_setting_pg, changed_settings)

        user_setting_pg.return_to_default_settings()
        self.verify_user_settings_change(user_setting_pg,
                                         user_setting_pg.DEFAULT_SETTINGS)
