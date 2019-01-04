from pytest import fixture

from consts import horizon
from utils.tis_log import LOG
from utils.horizon import helper
from utils.horizon.regions import messages
from utils.horizon.pages.identity import groupspage


@fixture(scope='function')
def groups_pg(admin_home_pg_container, request):
    LOG.fixture_step('Go to Identity > Groups')
    group_name = helper.gen_resource_name('groups')
    groups_pg = groupspage.GroupsPage(admin_home_pg_container.driver, port=admin_home_pg_container.port)
    groups_pg.go_to_target_page()

    def teardown():
        LOG.fixture_step('Back to Groups page')
        groups_pg.go_to_target_page()

    request.addfinalizer(teardown)
    return groups_pg, group_name


@fixture(scope='function')
def groups_pg_action(groups_pg, request):
    groups_pg, group_name = groups_pg
    LOG.fixture_step('Create new group {}'.format(group_name))
    groups_pg.create_group(group_name)

    def teardown():
        LOG.fixture_step('Delete group {}'.format(group_name))
        groups_pg.delete_group(group_name)

    request.addfinalizer(teardown)
    return groups_pg


def test_create_delete_group(groups_pg):
    """
    Tests the group creation and deletion functionality:

    Setups:
        - Login as Admin
        - Go to Identity > Groups

    Teardown:
        - Back to Groups page
        - Logout

    Test Steps:
        - Create a new group
        - Verify the group appears in groups table
        - Delete the newly created group
        - Verify the group does not appear in the table after deletion
    """
    groups_pg, group_name = groups_pg

    LOG.tc_step('Create new group {} and verify the group appears in groups table'.format(group_name))
    groups_pg.create_group(name=group_name, description="cgcsauto test")
    assert groups_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not groups_pg.find_message_and_dismiss(messages.ERROR)
    assert groups_pg.is_group_present(group_name)

    LOG.tc_step('Delete group {} and verify the group does not appear in the table'.format(group_name))
    groups_pg.delete_group(name=group_name)
    assert groups_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not groups_pg.find_message_and_dismiss(messages.ERROR)
    assert not groups_pg.is_group_present(group_name)
    horizon.test_result = True


def test_edit_group(groups_pg_action):
    """
    Tests the group edit row action functionality:

    Setups:
        - Login as Admin
        - Go to Identity > Groups
        - Create a new group

    Teardown:
        - Delete the newly created flavor
        - Back to Groups page
        - Logout

    Test Steps:
        - Update the group info
        - Verify the info is updated
    """
    groups_pg, group_name = groups_pg_action

    LOG.tc_step('Update the group info to {}.'.format(group_name))
    new_group_name = 'edited-' + group_name
    new_group_desc = 'edited-cgcsauto'
    groups_pg.edit_group(group_name, new_name=new_group_name, new_description=new_group_desc)

    LOG.tc_step('Verify the info is updated.')
    assert groups_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not groups_pg.find_message_and_dismiss(messages.ERROR)
    assert groups_pg.is_group_present(new_group_name)
    horizon.test_result = True
