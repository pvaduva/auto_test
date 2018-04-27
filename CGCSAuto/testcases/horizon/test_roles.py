from utils.horizon.regions import messages
from utils.horizon.pages.identity import rolespage
from pytest import fixture
from utils.horizon import helper
from utils.tis_log import LOG
from testfixtures.horizon import admin_home_pg, driver
from consts import horizon


class TestRole:

    ROLE_NAME = None

    @fixture(scope='function')
    def roles_pg(self, admin_home_pg, request):
        LOG.fixture_step('Go to Identity > Roles')
        self.ROLE_NAME = helper.gen_resource_name('roles')
        roles_pg = rolespage.RolesPage(admin_home_pg.driver)
        roles_pg.go_to_target_page()

        def teardown():
            LOG.fixture_step('Back to Roles page')
            roles_pg.go_to_target_page()

        request.addfinalizer(teardown)
        return roles_pg

    def test_create_edit_delete_role(self, roles_pg):
        """
        Tests the role creation/edit/deletion functionality:

        Setups:
            - Login as Admin
            - Go to Identity > Roles

        Teardown:
            - Back to Roles page
            - Logout

        Test Steps:
            - Create a new role
            - Verify the role appears in groups table
            - Edit the role name
            - Verify name changed in the table
            - Delete the newly created role
            - Verify the role does not appear in the table after deletion
        """
        roles_pg.create_role(self.ROLE_NAME)
        assert roles_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not roles_pg.find_message_and_dismiss(messages.ERROR)
        assert roles_pg.is_role_present(self.ROLE_NAME)

        newname = 'edit' + self.ROLE_NAME
        roles_pg.edit_role(self.ROLE_NAME, newname)
        assert roles_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not roles_pg.find_message_and_dismiss(messages.ERROR)
        assert roles_pg.is_role_present(newname)
        self.ROLE_NAME = newname

        roles_pg.delete_role(self.ROLE_NAME)
        assert roles_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not roles_pg.find_message_and_dismiss(messages.ERROR)
        assert not roles_pg.is_role_present(self.ROLE_NAME)
        horizon.test_result = True

