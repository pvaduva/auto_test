from pytest import fixture

from consts import horizon
from utils.tis_log import LOG
from utils.horizon import helper
from utils.horizon.regions import messages
from utils.horizon.pages.identity import projectspage


@fixture(scope='function')
def projects_pg(admin_home_pg_container, request):
    LOG.fixture_step('Go to Identity > Projects')
    project_name = helper.gen_resource_name('projects')
    projects_pg = projectspage.ProjectsPage(admin_home_pg_container.driver, port=admin_home_pg_container.port)
    projects_pg.go_to_target_page()

    def teardown():
        LOG.fixture_step('Back to Groups page')
        projects_pg.go_to_target_page()

    request.addfinalizer(teardown)

    return projects_pg, project_name


@fixture(scope='function')
def projects_pg_action(self, admin_home_pg_container, request):
    LOG.fixture_step('Go to Identity > Projects')
    project_name = helper.gen_resource_name('projects')
    projects_pg = projectspage.ProjectsPage(admin_home_pg_container.driver, port=admin_home_pg_container.port)
    projects_pg.go_to_target_page()
    LOG.fixture_step('Create new project {}'.format(self.PROJECT_NAME))
    projects_pg.create_project(self.PROJECT_NAME)

    def teardown():
        LOG.fixture_step('Delete the newly created project')
        projects_pg.delete_project(self.PROJECT_NAME)
        LOG.fixture_step('Back to Groups page')
        projects_pg.go_to_target_page()

    request.addfinalizer(teardown)

    return projects_pg, project_name


def test_create_delete_project(projects_pg):
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
    projects_pg, project_name = projects_pg
    LOG.tc_step('Create new project {}'.format(project_name))
    projects_pg.create_project(project_name)
    assert projects_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not projects_pg.find_message_and_dismiss(messages.ERROR)

    LOG.tc_step('Verify the project appears in the projects table')
    assert projects_pg.is_project_present(project_name)

    LOG.tc_step('Delete project {}'.format(project_name))
    projects_pg.delete_project(project_name)
    assert projects_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not projects_pg.find_message_and_dismiss(messages.ERROR)

    LOG.tc_step('Verify the project does not appear in the table after deletion')
    assert not projects_pg.is_project_present(project_name)
    horizon.test_result = True


def test_add_member(projects_pg_action):
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
    projects_pg, project_name = projects_pg_action

    LOG.tc_step('Allocate users to the project')
    projects_pg.manage_members(project_name, users2allocate=['tenant1', 'admin'])
    assert projects_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not projects_pg.find_message_and_dismiss(messages.ERROR)

    LOG.tc_step('Verify the users are added to the project')
    user_roles = projects_pg.get_member_roles_at_project(self.PROJECT_NAME, 'tenant1')
    assert user_roles == {'_member_'}
    horizon.test_result = True
