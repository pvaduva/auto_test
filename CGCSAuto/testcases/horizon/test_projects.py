from utils.horizon.regions import messages
from utils.horizon.pages.identity import projectspage
from pytest import fixture
from utils.horizon import helper
from utils.tis_log import LOG
from testfixtures.horizon import admin_home_pg, driver
from consts import horizon


class TestProjects:

    PROJECT_NAME = None

    @fixture(scope='function')
    def projects_pg(self, admin_home_pg, request):
        LOG.fixture_step('Go to Identity > Projects')
        self.PROJECT_NAME = helper.gen_resource_name('projects')
        projects_pg = projectspage.ProjectsPage(admin_home_pg.driver)
        projects_pg.go_to_target_page()

        def teardown():
            LOG.fixture_step('Back to Groups page')
            projects_pg.go_to_target_page()

        request.addfinalizer(teardown)

        return projects_pg

    @fixture(scope='function')
    def projects_pg_action(self, admin_home_pg, request):
        LOG.fixture_step('Go to Identity > Projects')
        self.PROJECT_NAME = helper.gen_resource_name('projects')
        projects_pg = projectspage.ProjectsPage(admin_home_pg.driver)
        projects_pg.go_to_target_page()
        LOG.fixture_step('Create new project {}'.format(self.PROJECT_NAME))
        projects_pg.create_project(self.PROJECT_NAME)

        def teardown():
            LOG.fixture_step('Delete the newly created project')
            projects_pg.delete_project(self.PROJECT_NAME)
            LOG.fixture_step('Back to Groups page')
            projects_pg.go_to_target_page()

        request.addfinalizer(teardown)

        return projects_pg

    def test_create_delete_project(self, projects_pg):
        """
        Test the project creation and deletion functionality:
        
        Setups:
            - Login as Admin
            - Go to Identity > Projects

        Teardown:
            - Back to Projects page
            - Logout

        Test Steps:
            - Create a new project
            - Verify the project appears in the projects table
            - Delete the newly created project
            - Verify the project does not appear in the table after deletion
        """

        LOG.tc_step('Create new project {}'.format(self.PROJECT_NAME))
        projects_pg.create_project(self.PROJECT_NAME)
        assert projects_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not projects_pg.find_message_and_dismiss(messages.ERROR)

        LOG.tc_step('Verify the project appears in the projects table')
        assert projects_pg.is_project_present(self.PROJECT_NAME)

        LOG.tc_step('Delete project {}'.format(self.PROJECT_NAME))
        projects_pg.delete_project(self.PROJECT_NAME)
        assert projects_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not projects_pg.find_message_and_dismiss(messages.ERROR)

        LOG.tc_step('Verify the project does not appear in the table after deletion')
        assert not projects_pg.is_project_present(self.PROJECT_NAME)
        horizon.test_result = True

    def test_add_member(self, projects_pg_action):
        """
        Test the the projects add-member action functionality:

        Setups:
            - Login as Admin
            - Go to Identity > Projects
            - Create a new Project

        Teardown:
            - Delete the newly created project
            - Back to Projects page
            - Logout

        Test Steps:
            - Allocate users to the project
            - Verify the user is added to the project
        """

        LOG.tc_step('Allocate users to the project')
        projects_pg_action.manage_members(self.PROJECT_NAME, users2allocate=['tenant1', 'admin'])
        assert projects_pg_action.find_message_and_dismiss(messages.SUCCESS)
        assert not projects_pg_action.find_message_and_dismiss(messages.ERROR)

        LOG.tc_step('Verify the users are added to the project')
        user_roles = projects_pg_action.get_member_roles_at_project(self.PROJECT_NAME, 'tenant1')
        assert user_roles == {'_member_'}
        horizon.test_result = True

