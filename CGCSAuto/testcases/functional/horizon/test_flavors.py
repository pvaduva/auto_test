import random

from pytest import fixture

from consts import horizon
from utils.tis_log import LOG
from utils.horizon.regions import messages
from utils.horizon.pages.admin.compute import flavorspage
from utils.horizon import helper


@fixture(scope='function')
def flavors_pg(admin_home_pg_container, request):
    LOG.fixture_step('Go to Admin > Compute > Flavors')
    flavor_name = helper.gen_resource_name('flavors')
    flavors_pg = flavorspage.FlavorsPage(admin_home_pg_container.driver, port=admin_home_pg_container.port)
    flavors_pg.go_to_target_page()

    def teardown():
        LOG.fixture_step('Back to Flavors page')
        flavors_pg.go_to_target_page()

    request.addfinalizer(teardown)
    return flavors_pg, flavor_name


@fixture(scope='function')
def flavors_pg_action(flavors_pg, request):
    flavors_pg, flavor_name = flavors_pg
    LOG.fixture_step('Create new flavor {}'.format(flavor_name))
    flavors_pg.create_flavor(flavor_name)

    def teardown():
        LOG.fixture_step('Delete flavor {}'.format(flavor_name))
        flavors_pg.delete_flavor(flavor_name)

    request.addfinalizer(teardown)
    return flavors_pg, flavor_name


def test_horizon_flavor_create(flavors_pg):
    """
    Tests the flavor creation and deletion functionality:

    Setups:
        - Login as Admin
        - Go to Admin > Compute > Flavors

    Teardown:
        - Back to Flavors Page
        - Logout

    Test Steps:
        - Creates a new flavor
        - Verifies the flavor appears in the flavors table
        - Deletes the newly created flavor
        - Verifies the flavor does not appear in the table after deletion
    """
    flavors_pg, flavor_name = flavors_pg
    
    LOG.tc_step('Creates flavor {} and verifies it appears in flavors table'.format(flavor_name))
    flavors_pg.create_flavor(flavor_name)
    assert flavors_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not flavors_pg.find_message_and_dismiss(messages.ERROR)
    assert flavors_pg.is_flavor_present(flavor_name)

    LOG.tc_step('Deletes flavor {} and verifies it does not appear in flavors table'.format(flavor_name))
    flavors_pg.delete_flavor_by_row(flavor_name)
    assert flavors_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not flavors_pg.find_message_and_dismiss(messages.ERROR)
    assert not flavors_pg.is_flavor_present(flavor_name)
    horizon.test_result = True


def test_horizon_flavor_update_info(flavors_pg_action):
    """
    Tests the flavor Edit row action functionality:

    Setups:
        - Login as Admin
        - Go to Admin > Compute > Flavors
        - Create a new flavor

    Teardown:
        - Delete the newly created flavor
        - Back to Flavors Page
        - Logout

    Test Steps:
        - Updates the flavor info and verify the info
    """

    flavors_pg, flavor_name = flavors_pg_action
    add_up = random.randint(1, 10)
    old_vcpus = int(flavors_pg_action.get_flavor_info(flavor_name, "VCPUs"))

    LOG.tc_step('Updates the flavor info and verifies it is updated successfully'.format(flavor_name))
    newname = 'edit-' + flavor_name
    flavors_pg.edit_flavor(flavor_name, newname=newname, vcpus=old_vcpus+add_up)

    assert flavors_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not flavors_pg.find_message_and_dismiss(messages.ERROR)
    assert flavors_pg.is_flavor_present(newname)

    new_vcpus = flavors_pg.get_flavor_info(newname, "VCPUs")
    assert old_vcpus != new_vcpus
    horizon.test_result = True


'''def test_flavor_update_access(flavors_pg_action):     JIRA
    """
    Tests the flavor update access functionality:

    Setups:
        - Login as Admin
        - Go to Admin > Compute > Flavors
        - Create a new flavor

    Teardown:
        - Delete the newly created flavor
        - Back to Flavors Page
        - Logout

    Test Steps:
        - Update flavor access to a project and verify flavor is not Public
        - Update flavor access to Public and verify it
    """
    projects = ['admin', 'tenant1']

    LOG.tc_step('Update flavor access by adding projects: {} and verify not public'.format(projects))
    flavors_pg_action.modify_access(flavor_name, allocate_projects=projects)

    assert flavors_pg_action.get_flavor_info(flavor_name, "Public") == "No"

    LOG.tc_step('Update flavor access back to public and verify'.format(projects))
    flavors_pg_action.modify_access(flavor_name, deallocate_projects=projects)
    assert flavors_pg_action.get_flavor_info(flavor_name, "Public") == "Yes"
    horizon.test_result = True
    '''


def test_horizon_create_flavor_with_excessive_vcpu_negative(flavors_pg):
    """
    Test that flavor creation fails:

    Setups:
        - Login as Admin
        - Go to Admin > Compute > Flavors

    Teardown:
        - Back to Flavors Page
        - Logout

    Test Steps:
       - Try to create a new flavor with 129 vCPUs
       - Check that the flavor cannot be created
    """
    flavors_pg, flavor_name = flavors_pg
    flavors_pg.create_flavor(flavor_name, vcpus=129)
    assert not flavors_pg.find_message_and_dismiss(messages.SUCCESS)
    assert not flavors_pg.is_flavor_present(flavor_name)
    horizon.test_result = True
