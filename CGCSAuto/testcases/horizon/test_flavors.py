import random
from utils.horizon.regions import messages
from utils.horizon.pages.admin.compute import flavorspage
from pytest import fixture
from utils.horizon import helper
from utils.tis_log import LOG


class TestFlavors(helper.AdminTestCase):
    
    FLAVOR_NAME = None

    @fixture(scope='function')
    def flavors_pg(self, home_pg, request):
        LOG.fixture_step('Go to Admin > Compute > Flavors')
        self.FLAVOR_NAME = helper.gen_resource_name('flavors')
        flavors_pg = flavorspage.FlavorsPage(home_pg.driver)
        flavors_pg.go_to_target_page()

        def teardown():
            LOG.fixture_step('Back to Flavors page')
            flavors_pg.go_to_target_page()

        request.addfinalizer(teardown)
        return flavors_pg

    @fixture(scope='function')
    def flavors_pg_action(self, flavors_pg, request):
        LOG.fixture_step('Create new flavor {}'.format(self.FLAVOR_NAME))
        self._create_flavor(flavors_pg, self.FLAVOR_NAME)

        def teardown():
            LOG.fixture_step('Delete flavor {}'.format(self.FLAVOR_NAME))
            self._delete_flavor(flavors_pg, self.FLAVOR_NAME)

        request.addfinalizer(teardown)
        return flavors_pg

    def _create_flavor(self, flavorspage, flavor_name):
        flavorspage.create_flavor(
            name=flavor_name,
            vcpus=1,
            ram=1024,
            root_disk=20,
            ephemeral_disk=0,
            swap_disk=0,
            rxtx_factor=1
        )
        assert flavorspage.find_message_and_dismiss(messages.SUCCESS)
        assert not flavorspage.find_message_and_dismiss(messages.ERROR)
        assert flavorspage.is_flavor_present(self.FLAVOR_NAME)

    def _delete_flavor(self, flavorspage, flavor_name):
        flavorspage.delete_flavor_by_row(flavor_name)
        assert flavorspage.find_message_and_dismiss(messages.SUCCESS)
        assert not flavorspage.find_message_and_dismiss(messages.ERROR)
        assert not flavorspage.is_flavor_present(self.FLAVOR_NAME)

    def test_flavor_create(self, flavors_pg):
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
        LOG.tc_step('Creates flavor {} and verifies it appears in flavors table'.format(self.FLAVOR_NAME))
        self._create_flavor(flavors_pg, self.FLAVOR_NAME)
        LOG.tc_step('Deletes flavor {} and verifies it does not appear in flavors table'.format(self.FLAVOR_NAME))
        self._delete_flavor(flavors_pg, self.FLAVOR_NAME)

    def test_flavor_update_info(self, flavors_pg_action):
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

        add_up = random.randint(1, 10)
        old_vcpus = int(flavors_pg_action.get_flavor_info(self.FLAVOR_NAME, "VCPUs"))

        LOG.tc_step('Updates the flavor info and verifies it is updated successfully'.format(self.FLAVOR_NAME))

        newname = 'edit-' + self.FLAVOR_NAME
        flavors_pg_action.edit_flavor(self.FLAVOR_NAME, newname=newname, vcpus=old_vcpus+add_up)

        assert flavors_pg_action.find_message_and_dismiss(messages.SUCCESS)
        assert not flavors_pg_action.find_message_and_dismiss(messages.ERROR)
        assert flavors_pg_action.is_flavor_present(newname)

        new_vcpus = flavors_pg_action.get_flavor_info(newname, "VCPUs")
        assert not old_vcpus == new_vcpus

        self.FLAVOR_NAME = newname

    '''def test_flavor_update_access(self, flavors_pg_action):
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
        flavors_pg_action.modify_access(self.FLAVOR_NAME, allocate_projects=projects)

        assert flavors_pg_action.get_flavor_info(self.FLAVOR_NAME, "Public") == "No"

        LOG.tc_step('Update flavor access back to public and verify'.format(projects))
        flavors_pg_action.modify_access(self.FLAVOR_NAME, deallocate_projects=projects)
        assert flavors_pg_action.get_flavor_info(self.FLAVOR_NAME, "Public") == "Yes"'''

    def test_create_flavor_with_excessive_vcpu_negative(self, flavors_pg):
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
        flavors_pg.create_flavor(
            name=self.FLAVOR_NAME,
            vcpus=129,
            ram=1024,
            root_disk=20,
            ephemeral_disk=0,
            swap_disk=0,
            rxtx_factor=1
        )
        assert not flavors_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not flavors_pg.is_flavor_present(self.FLAVOR_NAME)

