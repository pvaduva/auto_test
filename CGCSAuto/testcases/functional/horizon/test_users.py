import time
from pytest import fixture, skip

from consts import horizon
from consts.auth import Tenant
from keywords import system_helper
from utils.tis_log import LOG
from utils.horizon import helper
from utils.horizon.regions import messages
from utils.horizon.pages import loginpage
from utils.horizon.pages.identity import userspage
from utils.horizon.pages.settings import usersettingspage
from utils.horizon.pages.settings import changepasswordpage


def test_horizon_dashboard_help_redirection(admin_home_pg_container):
    """Verifies Help link redirects to the right URL."""

    if not system_helper.is_avs():
        skip('No support page available for STX')

    admin_home_pg_container.go_to_help_page()
    admin_home_pg_container._wait_until(
        lambda _: admin_home_pg_container.is_nth_window_opened(2))

    admin_home_pg_container.switch_window()
    time.sleep(2)
    assert 'http://www.windriver.com/support/' == \
           admin_home_pg_container.get_current_page_url()

    admin_home_pg_container.close_window()
    admin_home_pg_container.switch_window()
    horizon.test_result = True


NEW_PASSWORD1 = "Li96nux*"
NEW_PASSWORD2 = "LI69nux*"
TEST_PASSWORD = "Li69nux*"


@fixture(scope='function')
def new_user(admin_home_pg_container, request):
    """
    Args:
        admin_home_pg_container:
        request:

    Setups:
        - Login as Admin
        - Go to Identity > User
        - Create a new user
        - Verify the user appears in the users table

    Teardown:
        - Delete the newly created user
        - Verify the user does not appear in the table after deletion
        - Back to Users page
        - Logout

    """
    LOG.fixture_step('Go to Identity > Users')
    users_pg = userspage.UsersPage(admin_home_pg_container.driver, port=admin_home_pg_container.port)
    users_pg.go_to_target_page()
    username = helper.gen_resource_name('user')
    password = TEST_PASSWORD

    LOG.fixture_step('Create new user {}'.format(username))
    users_pg.create_user(username, password=password,
                         project='admin', role='admin')
    assert users_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not users_pg.find_message_and_dismiss(messages.ERROR)

    LOG.fixture_step('Verify the user appears in the users table')
    assert users_pg.is_user_present(username)
    login_pg = loginpage.LoginPage(users_pg.driver, port=users_pg.port)

    def delete_test_user():
        LOG.fixture_step('Go to users page and delete user {}'.format(username))
        users_pg.log_out()
        login_pg.go_to_target_page()
        login_pg.login(user='admin', password=Tenant.get('admin')['password'])
        users_pg.go_to_target_page()
        users_pg.delete_user(username)
        assert users_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not users_pg.find_message_and_dismiss(messages.ERROR)

        LOG.fixture_step('Verify the user does not appear in the table after deletion')
        assert not users_pg.is_user_present(username)

        LOG.fixture_step('Back to Users page')
        users_pg.go_to_target_page()
    request.addfinalizer(delete_test_user)

    LOG.fixture_step("Login as new user, and go to user password change page")
    users_pg.log_out()
    login_pg.go_to_target_page()
    home_pg = login_pg.login(user=username, password=TEST_PASSWORD)
    password_change_pg = changepasswordpage.ChangepasswordPage(home_pg.driver, port=home_pg.port)
    password_change_pg.go_to_target_page()
    return password_change_pg, username


def test_horizon_password_change(new_user):
    # Changes the password, verifies it was indeed changed and
    # resets to default password.
    # !!!!! the password cannot be change to previous password

    password_change_pg, username = new_user
    password_change_pg.change_password(TEST_PASSWORD, NEW_PASSWORD1)
    login_pg = loginpage.LoginPage(password_change_pg.driver)
    assert login_pg.is_logout_reason_displayed(), \
        "The logout reason message was not found on the login page"
    home_pg = login_pg.login(username, NEW_PASSWORD1)
    assert home_pg.is_logged_in, "Failed to login with new password"
    password_change_pg.go_to_target_page()
    time.sleep(2)
    password_change_pg.change_password(NEW_PASSWORD1, NEW_PASSWORD2)
    assert login_pg.is_logout_reason_displayed(), \
        "The logout reason message was not found on the login page"
    home_pg = login_pg.login(username, NEW_PASSWORD2)
    assert home_pg.is_logged_in, "Failed to login with new password"
    password_change_pg.go_to_target_page()
    time.sleep(2)
    password_change_pg.reset_to_default_password(NEW_PASSWORD2)
    home_pg = login_pg.login(username, TEST_PASSWORD)
    assert home_pg.is_logged_in, "Failed to login with new password"
    horizon.test_result = True


@fixture(scope='function')
def user_setting_pg(admin_home_pg_container):
    user_setting_pg = usersettingspage.UsersettingsPage(admin_home_pg_container.driver,
                                                        port=admin_home_pg_container.port)
    user_setting_pg.go_to_target_page()
    return user_setting_pg


def verify_user_settings_change(settings_page, changed_settings):
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


def test_horizon_user_settings_change(user_setting_pg):
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
    verify_user_settings_change(user_setting_pg, changed_settings)

    user_setting_pg.return_to_default_settings()
    verify_user_settings_change(user_setting_pg, user_setting_pg.DEFAULT_SETTINGS)
    horizon.test_result = True
