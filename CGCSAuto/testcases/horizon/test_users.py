from utils.horizon.regions import messages
from utils.horizon.pages.identity import userspage
from pytest import fixture
from utils.horizon import helper
from utils.tis_log import LOG
from testfixtures.horizon import admin_home_pg, driver


class TestUser:

    @fixture(scope='function')
    def users_pg(self, admin_home_pg, request):
        LOG.fixture_step('Go to Identity > Users')
        users_pg = userspage.UsersPage(admin_home_pg.driver)
        users_pg.go_to_target_page()

        def teardown():
            LOG.fixture_step('Back to Users page')
            users_pg.go_to_target_page()

        request.addfinalizer(teardown)
        return users_pg

    USER_NAME = helper.gen_resource_name('user')

    def test_create_delete_user(self, users_pg):
        """
        Test the user creation and deletion functionality:

        Setups:
            - Login as Admin
            - Go to Identity > User

        Teardown:
            - Back to Users page
            - Logout

        Test Steps:
            - Create a new user
            - Verify the user appears in the users table
            - Delete the newly created user
            - Verify the user does not appear in the table after deletion
        """
        password = "Li69nux*"

        LOG.tc_step('Create new user {}'.format(self.USER_NAME))
        users_pg.create_user(self.USER_NAME, password=password,
                             project='admin', role='admin')
        assert users_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not users_pg.find_message_and_dismiss(messages.ERROR)

        LOG.tc_step('Verify the user appears in the users table')
        assert users_pg.is_user_present(self.USER_NAME)

        LOG.tc_step('Delete user {}'.format(self.USER_NAME))
        users_pg.delete_user(self.USER_NAME)
        assert users_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not users_pg.find_message_and_dismiss(messages.ERROR)

        LOG.tc_step('Verify the user does not appear in the table after deletion')
        assert not users_pg.is_user_present(self.USER_NAME)

