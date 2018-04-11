from utils.horizon.regions import messages
from utils.horizon.pages.identity import groupspage
from pytest import fixture
from utils.horizon import helper
from utils.tis_log import LOG


class TestGroup(helper.AdminTestCase):

    GROUP_NAME = None
    GROUP_DESCRIPTION = helper.gen_resource_name('description')

    @fixture(scope='function')
    def groups_pg(self, home_pg, request):
        LOG.fixture_step('Go to Identity > Groups')
        self.GROUP_NAME = helper.gen_resource_name('groups')
        groups_pg = groupspage.GroupsPage(home_pg.driver)
        groups_pg.go_to_target_page()

        def teardown():
            LOG.fixture_step('Back to Groups page')
            groups_pg.go_to_target_page()

        request.addfinalizer(teardown)
        return groups_pg

    @fixture(scope='function')
    def groups_pg_action(self, groups_pg, request):
        LOG.fixture_step('Create new group {}'.format(self.GROUP_NAME))
        self._test_create_group(groups_pg)

        def teardown():
            LOG.fixture_step('Delete group {}'.format(self.GROUP_NAME))
            self._test_delete_group(groups_pg)

        request.addfinalizer(teardown)
        return groups_pg

    def _test_create_group(self, groupspage):
        groupspage.create_group(name=self.GROUP_NAME,
                                description=self.GROUP_DESCRIPTION)
        assert groupspage.find_message_and_dismiss(messages.SUCCESS)
        assert not groupspage.find_message_and_dismiss(messages.ERROR)
        assert groupspage.is_group_present(self.GROUP_NAME)

    def _test_delete_group(self, groupspage):
        groupspage.delete_group(name=self.GROUP_NAME)
        assert groupspage.find_message_and_dismiss(messages.SUCCESS)
        assert not groupspage.find_message_and_dismiss(messages.ERROR)
        assert not groupspage.is_group_present(self.GROUP_NAME)

    def test_create_delete_group(self, groups_pg):
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

        LOG.tc_step('Create new group {} and verify the group appears in groups table'.format(self.GROUP_NAME))
        self._test_create_group(groups_pg)
        LOG.tc_step('Delete group {} and verify the group does not appear in the table'.format(self.GROUP_NAME))
        self._test_delete_group(groups_pg)

    def test_edit_group(self, groups_pg):
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

        LOG.tc_step('Create new group {}.'.format(self.GROUP_NAME))
        self._test_create_group(groups_pg)

        LOG.tc_step('Update the group info to {}.'.format(self.GROUP_NAME))
        new_group_name = 'edited-' + self.GROUP_NAME
        new_group_desc = 'edited-' + self.GROUP_DESCRIPTION
        groups_pg.edit_group(self.GROUP_NAME, new_name=new_group_name, new_description=new_group_desc)

        LOG.tc_step('Verify the info is updated.')
        assert groups_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not groups_pg.find_message_and_dismiss(messages.ERROR)
        assert groups_pg.is_group_present(new_group_name)
        self.GROUP_NAME = new_group_name

        LOG.tc_step('Delete group {}.'.format(new_group_name))
        self._test_delete_group(groups_pg)
