from utils.horizon.regions import messages
from utils.horizon.pages.project.network import floatingipspage as project_floatingipspage
from utils.horizon.pages.admin.network import floatingipspage as admin_floatingipspage
from utils.horizon.pages.project.compute import instancespage
from pytest import fixture, mark
from utils.horizon import helper
from utils.tis_log import LOG


class TestFloatingip(helper.TenantTestCase):

    @fixture(scope='function')
    def floatingips_pg(self, home_pg, request):
        LOG.fixture_step('Go to Project > Network > Floating IPs')
        floatingips_pg = project_floatingipspage.FloatingipsPage(home_pg.driver)
        floatingips_pg.go_to_target_page()

        def teardown():
            LOG.fixture_step('Back to Floating IPs page')
            floatingips_pg.go_to_target_page()

        request.addfinalizer(teardown)
        return floatingips_pg

    @fixture(scope='function')
    def instances_pg(self, home_pg, request):
        LOG.fixture_step('Go to Project > Compute > Instances')
        instances_pg = instancespage.InstancesPage(home_pg.driver)
        instances_pg.go_to_target_page()

        def teardown():
            LOG.fixture_step('Back to Instances page')
            instances_pg.go_to_target_page()

        request.addfinalizer(teardown)
        return instances_pg

    def test_floatingip(self, floatingips_pg):
        """
        Tests the floating-ip allocate/release functionality:

        Setups:
            - Login as Tenant
            - Go to Project > Network > Floating IPs

        Teardown:
            - Back to Floating IPs page
            - Logout

        Test Steps:
            - Allocates floating ip
            - Verifies that the floating ip is present
            - Releases the floating ip
            - Verifies that the floating ip does not appear in the table
        """

        LOG.tc_step('Allocates floating ip')
        floating_ip = floatingips_pg.allocate_floatingip()

        LOG.tc_step('Verifies that the floating ip {} is present'.format(floating_ip))
        assert floatingips_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not floatingips_pg.find_message_and_dismiss(messages.ERROR)
        assert floatingips_pg.is_floatingip_present(floating_ip)

        LOG.tc_step('Releases the floating ip')
        floatingips_pg.release_floatingip(floating_ip)
        assert floatingips_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not floatingips_pg.find_message_and_dismiss(messages.ERROR)
        LOG.tc_step('Verifies that the floating ip does not appear in the table')
        assert not floatingips_pg.is_floatingip_present(floating_ip)

    def test_floatingip_associate_disassociate(self, instances_pg):
        """
        Tests the floating-ip allocate/release functionality:

        Setups:
            - Login as Tenant
            - Go to Project > Compute > Instances

        Teardown:
            - Back to Instances page
            - Logout

        Test Steps:
            - Create a new instance
            - Allocates floating ip
            - Associate floating ip to the instance and verify it
            - Disassociate floating ip to the instance and verify it
            - Release Floating ip
            - Delete the instance
        """
        instance_name = helper.gen_resource_name('instance')
        LOG.tc_step('Create new instance {}'.format(instance_name))
        instances_pg.create_instance(instance_name,
                                     boot_source_type='Image',
                                     create_new_volume=False,
                                     source_name='tis-centos-guest',
                                     flavor_name='small',
                                     network_names=['tenant1-mgmt-net'])
        assert not instances_pg.find_message_and_dismiss(messages.ERROR)
        assert instances_pg.is_instance_active(instance_name)

        instance_ipv4 = instances_pg.get_fixed_ipv4(instance_name)
        instance_info = "{} {}".format(instance_name, instance_ipv4)

        floatingip_page = project_floatingipspage.FloatingipsPage(instances_pg.driver)
        floatingip_page.go_to_target_page()

        LOG.tc_step('Allocates floating ip')
        floating_ip = floatingip_page.allocate_floatingip()
        assert floatingip_page.find_message_and_dismiss(messages.SUCCESS)
        assert not floatingip_page.find_message_and_dismiss(messages.ERROR)
        assert floatingip_page.is_floatingip_present(floating_ip)

        assert '-' == floatingip_page.get_floatingip_info(floating_ip, 'Mapped Fixed IP Address')

        LOG.tc_step('Associate floating ip to {} and verify'.format(instance_name))
        floatingip_page.associate_floatingip(floating_ip, instance_name, instance_ipv4)
        assert floatingip_page.find_message_and_dismiss(messages.SUCCESS)
        assert not floatingip_page.find_message_and_dismiss(messages.ERROR)
        assert instance_info == floatingip_page.get_floatingip_info(floating_ip, 'Mapped Fixed IP Address')

        LOG.tc_step('Disassociate floating ip to {} and verify'.format(instance_name))
        floatingip_page.disassociate_floatingip(floating_ip)
        assert floatingip_page.find_message_and_dismiss(messages.SUCCESS)
        assert not floatingip_page.find_message_and_dismiss(messages.ERROR)
        assert '-' == floatingip_page.get_floatingip_info(floating_ip, 'Mapped Fixed IP Address')

        LOG.tc_step('Release Floating ip')
        floatingip_page.release_floatingip(floating_ip)
        assert floatingip_page.find_message_and_dismiss(messages.SUCCESS)
        assert not floatingip_page.find_message_and_dismiss(messages.ERROR)
        assert not floatingip_page.is_floatingip_present(floating_ip)

        LOG.tc_step('Delete instance {}'.format(instance_name))
        instances_pg.go_to_target_page()
        instances_pg.delete_instance(instance_name)
        assert instances_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not instances_pg.find_message_and_dismiss(messages.ERROR)
        assert instances_pg.is_instance_deleted(instance_name)


class TestFloatingipAdmin(helper.AdminTestCase):

    @fixture(scope='function')
    def floatingips_pg(self, home_pg, request):
        LOG.fixture_step('Go to Admin > Network > Floating IPs')
        floatingips_pg = admin_floatingipspage.FloatingipsPage(home_pg.driver)
        floatingips_pg.go_to_target_page()

        def teardown():
            LOG.fixture_step('Back to Floating IPs page')
            floatingips_pg.go_to_target_page()

        request.addfinalizer(teardown)
        return floatingips_pg

    def test_allocate_floatingip_admin(self, floatingips_pg):

        LOG.tc_step('Allocates floating ip')
        floating_ip = floatingips_pg.allocate_floatingip(tenant='tenant1')

        LOG.tc_step('Verifies that the floating ip {} is present'.format(floating_ip))
        assert floatingips_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not floatingips_pg.find_message_and_dismiss(messages.ERROR)
        assert floatingips_pg.is_floatingip_present(floating_ip)

        LOG.tc_step('Releases the floating ip')
        floatingips_pg.release_floatingip(floating_ip)
        assert floatingips_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not floatingips_pg.find_message_and_dismiss(messages.ERROR)
        LOG.tc_step('Verifies that the floating ip does not appear in the table')
        assert not floatingips_pg.is_floatingip_present(floating_ip)