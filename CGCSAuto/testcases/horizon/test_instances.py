from utils.horizon.regions import messages
from utils.horizon.pages.project.compute import instancespage
from pytest import fixture, mark
from utils.horizon import helper
from utils.tis_log import LOG


class TestInstances(helper.TenantTestCase):

    INSTANCE_NAME = None

    @fixture(scope='function')
    def instances_pg(self, home_pg, request):
        LOG.fixture_step('Go to Project > Compute > Instance')
        self.INSTANCE_NAME = helper.gen_resource_name('instance')
        instances_pg = instancespage.InstancesPage(home_pg.driver)
        instances_pg.go_to_target_page()

        def teardown():
            LOG.fixture_step('Back to Groups page')
            if instances_pg.is_instance_present(self.INSTANCE_NAME):
                instances_pg.delete_instance(self.INSTANCE_NAME)
            instances_pg.go_to_target_page()

        request.addfinalizer(teardown)

        return instances_pg

    @mark.parametrize(('source_type', 'source_name', 'flavor_name', 'network_names'), [
        ('Image', 'tis-centos-guest', 'small', ['tenant1-mgmt-net']),
    ])
    def test_create_delete_instance(self, instances_pg, source_type, source_name,
                                    flavor_name, network_names):
        """
        Test the instance creation and deletion functionality:

        Setups:
            - Login as Tenant
            - Go to Project > Compute > Instance

        Teardown:
            - Back to Instances page
            - Logout

        Test Steps:
            - Create a new instance
            - Verify the instance appears in the instances table as active
            - Delete the newly lunched instance
            - Verify the instance does not appear in the table after deletion
        """

        LOG.tc_step('Create new instance {}'.format(self.INSTANCE_NAME))
        instances_pg.create_instance(self.INSTANCE_NAME,
                                     source_type=source_type,
                                     source_name=source_name,
                                     flavor_name=flavor_name,
                                     network_names=network_names)
        assert not instances_pg.find_message_and_dismiss(messages.ERROR)

        LOG.tc_step('Verify the instance appears in the instances table as active')
        assert instances_pg.is_instance_active(self.INSTANCE_NAME)

        LOG.tc_step('Delete instance {}'.format(self.INSTANCE_NAME))
        instances_pg.delete_instance(self.INSTANCE_NAME)
        assert instances_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not instances_pg.find_message_and_dismiss(messages.ERROR)

        LOG.tc_step('Verify the instance does not appear in the table after deletion')
        assert instances_pg.is_instance_deleted(self.INSTANCE_NAME)


