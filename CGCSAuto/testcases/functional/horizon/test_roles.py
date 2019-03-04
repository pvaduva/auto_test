from pytest import fixture

from consts import horizon
from utils.tis_log import LOG
from utils.horizon import helper
from utils.horizon.regions import messages
from utils.horizon.pages.identity import rolespage


@fixture(scope='function')
def roles_pg(admin_home_pg_container, request):
    LOG.fixture_step('Go to Identity > Roles')
    role_name = helper.gen_resource_name('roles')
    roles_pg = rolespage.RolesPage(admin_home_pg_container.driver, port=admin_home_pg_container.port)
    roles_pg.go_to_target_page()

    def teardown():
        LOG.fixture_step('Back to Roles page')
        roles_pg.go_to_target_page()

    request.addfinalizer(teardown)
    return roles_pg, role_name


def test_horizon_create_edit_delete_role(roles_pg):
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
    roles_pg, role_name = roles_pg

    roles_pg.create_role(role_name)
    assert roles_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not roles_pg.find_message_and_dismiss(messages.ERROR)
    assert roles_pg.is_role_present(role_name)

    newname = 'edit' + role_name
    roles_pg.edit_role(role_name, newname)
    assert roles_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not roles_pg.find_message_and_dismiss(messages.ERROR)
    assert roles_pg.is_role_present(newname)

    roles_pg.delete_role(newname)
    assert roles_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not roles_pg.find_message_and_dismiss(messages.ERROR)
    assert not roles_pg.is_role_present(newname)
    horizon.test_result = True
