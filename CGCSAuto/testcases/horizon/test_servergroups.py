from utils.horizon.regions import messages
from utils.horizon.pages.project.compute import servergroupspage
from pytest import fixture, mark
from utils.horizon import helper
from utils.tis_log import LOG


class TestServerGroup(helper.TenantTestCase):

    GROUP_NAME = None

    @fixture(scope='function')
    def server_groups_pg(self, home_pg, request):
        LOG.fixture_step('Go to Project > Compute > Server Groups')
        self.GROUP_NAME = helper.gen_resource_name('groups')
        groups_pg = servergroupspage.ServerGroupsPage(home_pg.driver)
        groups_pg.go_to_target_page()

        def teardown():
            LOG.fixture_step('Back to Groups page')
            groups_pg.go_to_target_page()

        request.addfinalizer(teardown)
        return groups_pg

    @mark.parametrize(('policy', 'is_best_effort', 'group_size'),
                      [('affinity', True, 10),
                       ('anti-affinity', None, None)])
    def test_create_delete_group(self, server_groups_pg, policy, is_best_effort, group_size):
        """
        Tests the server group creation and deletion functionality:

        Setups:
            - Login as Tenant
            - Go to Project > Compute > Server Groups page

        Teardown:
            - Back to Server Groups page
            - Logout

        Test Steps:
            - Create a new server group
            - Verify the group appears in server groups table
            - Delete the newly created server group
            - Verify the server group does not appear in the table after deletion
        """
        server_groups_pg.create_group(name=self.GROUP_NAME,
                                      policy=policy,
                                      is_best_effort=is_best_effort,
                                      group_size=group_size)
        assert not server_groups_pg.find_message_and_dismiss(messages.ERROR)
        assert server_groups_pg.is_group_present(self.GROUP_NAME)

        server_groups_pg.delete_group(name=self.GROUP_NAME)
        assert server_groups_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not server_groups_pg.find_message_and_dismiss(messages.ERROR)
        assert not server_groups_pg.is_group_present(self.GROUP_NAME)