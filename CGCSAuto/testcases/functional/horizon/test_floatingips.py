from pytest import fixture

from consts import horizon
from consts.stx import GuestImages
from consts.auth import Tenant
from keywords import nova_helper
from utils.tis_log import LOG
from utils.horizon import helper
from utils.horizon.regions import messages
from utils.horizon.pages.project.network import floatingipspage as project_floatingipspage
from utils.horizon.pages.admin.network import floatingipspage as admin_floatingipspage
from utils.horizon.pages.project.compute import instancespage


@fixture(scope='function')
def floating_ips_pg_tenant(tenant_home_pg_container, request):
    LOG.fixture_step('Go to Project > Network > Floating IPs')
    floatingips_pg = project_floatingipspage.FloatingipsPage(tenant_home_pg_container.driver,
                                                             port=tenant_home_pg_container.port)
    floatingips_pg.go_to_target_page()

    def teardown():
        LOG.fixture_step('Back to Floating IPs page')
        floatingips_pg.go_to_target_page()

    request.addfinalizer(teardown)
    return floatingips_pg


@fixture(scope='function')
def instances_pg(tenant_home_pg_container, request):
    LOG.fixture_step('Go to Project > Compute > Instances')
    instances_page = instancespage.InstancesPage(tenant_home_pg_container.driver, port=tenant_home_pg_container.port)
    instances_page.go_to_target_page()

    def teardown():
        LOG.fixture_step('Back to Instances page')
        instances_page.go_to_target_page()

    request.addfinalizer(teardown)
    return instances_page


def test_horizon_floating_ip(floating_ips_pg_tenant):
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
    floating_ip = floating_ips_pg_tenant.allocate_floatingip()

    LOG.tc_step('Verifies that the floating ip {} is present'.format(floating_ip))
    assert floating_ips_pg_tenant.find_message_and_dismiss(messages.SUCCESS)
    assert not floating_ips_pg_tenant.find_message_and_dismiss(messages.ERROR)
    assert floating_ips_pg_tenant.is_floatingip_present(floating_ip)

    LOG.tc_step('Releases the floating ip')
    floating_ips_pg_tenant.release_floatingip(floating_ip)
    assert floating_ips_pg_tenant.find_message_and_dismiss(messages.SUCCESS)
    assert not floating_ips_pg_tenant.find_message_and_dismiss(messages.ERROR)
    LOG.tc_step('Verifies that the floating ip does not appear in the table')
    assert not floating_ips_pg_tenant.is_floatingip_present(floating_ip)
    horizon.test_result = True


def test_horizon_floating_ip_associate_disassociate(instances_pg):
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
    mgmt_net_name = '-'.join([Tenant.get_primary()['tenant'], 'mgmt', 'net'])
    flv_name = nova_helper.get_basic_flavor(rtn_id=False)
    guest_img = GuestImages.DEFAULT['guest']

    instances_pg.create_instance(instance_name,
                                 boot_source_type='Image',
                                 create_new_volume=False,
                                 source_name=guest_img,
                                 flavor_name=flv_name,
                                 network_names=[mgmt_net_name])
    assert not instances_pg.find_message_and_dismiss(messages.ERROR)
    assert instances_pg.is_instance_active(instance_name)

    instance_ipv4 = instances_pg.get_fixed_ipv4(instance_name)
    instance_info = "{} {}".format(instance_name, instance_ipv4)

    floating_ips_page = project_floatingipspage.FloatingipsPage(instances_pg.driver, port=instances_pg.port)
    floating_ips_page.go_to_target_page()

    LOG.tc_step('Allocates floating ip')
    floating_ip = floating_ips_page.allocate_floatingip()
    assert floating_ips_page.find_message_and_dismiss(messages.SUCCESS)
    assert not floating_ips_page.find_message_and_dismiss(messages.ERROR)
    assert floating_ips_page.is_floatingip_present(floating_ip)

    assert '-' == floating_ips_page.get_floatingip_info(floating_ip, 'Mapped Fixed IP Address')

    LOG.tc_step('Associate floating ip to {} and verify'.format(instance_name))
    floating_ips_page.associate_floatingip(floating_ip, instance_name, instance_ipv4)
    assert floating_ips_page.find_message_and_dismiss(messages.SUCCESS)
    assert not floating_ips_page.find_message_and_dismiss(messages.ERROR)
    assert instance_info == floating_ips_page.get_floatingip_info(floating_ip, 'Mapped Fixed IP Address')

    LOG.tc_step('Disassociate floating ip to {} and verify'.format(instance_name))
    floating_ips_page.disassociate_floatingip(floating_ip)
    assert floating_ips_page.find_message_and_dismiss(messages.SUCCESS)
    assert not floating_ips_page.find_message_and_dismiss(messages.ERROR)
    assert '-' == floating_ips_page.get_floatingip_info(floating_ip, 'Mapped Fixed IP Address')

    LOG.tc_step('Release Floating ip')
    floating_ips_page.release_floatingip(floating_ip)
    assert floating_ips_page.find_message_and_dismiss(messages.SUCCESS)
    assert not floating_ips_page.find_message_and_dismiss(messages.ERROR)
    assert not floating_ips_page.is_floatingip_present(floating_ip)

    LOG.tc_step('Delete instance {}'.format(instance_name))
    instances_pg.go_to_target_page()
    instances_pg.delete_instance(instance_name)
    assert instances_pg.find_message_and_dismiss(messages.INFO)
    assert not instances_pg.find_message_and_dismiss(messages.ERROR)
    assert instances_pg.is_instance_deleted(instance_name)
    horizon.test_result = True


@fixture(scope='function')
def floating_ips_pg_admin(admin_home_pg_container, request):
    LOG.fixture_step('Go to Admin > Network > Floating IPs')
    floating_ips_pg = admin_floatingipspage.FloatingipsPage(admin_home_pg_container.driver,
                                                            port=admin_home_pg_container.port)
    floating_ips_pg.go_to_target_page()

    def teardown():
        LOG.fixture_step('Back to Floating IPs page')
        floating_ips_pg.go_to_target_page()

    request.addfinalizer(teardown)
    return floating_ips_pg


def test_horizon_allocate_floating_ip_admin(floating_ips_pg_admin):
    LOG.tc_step('Allocates floating ip')
    floating_ip = floating_ips_pg_admin.allocate_floatingip(tenant=Tenant.get_primary()['tenant'])

    LOG.tc_step('Verifies that the floating ip {} is present'.format(floating_ip))
    assert floating_ips_pg_admin.find_message_and_dismiss(messages.SUCCESS)
    assert not floating_ips_pg_admin.find_message_and_dismiss(messages.ERROR)
    assert floating_ips_pg_admin.is_floatingip_present(floating_ip)

    LOG.tc_step('Releases the floating ip')
    floating_ips_pg_admin.release_floatingip(floating_ip)
    assert floating_ips_pg_admin.find_message_and_dismiss(messages.SUCCESS)
    assert not floating_ips_pg_admin.find_message_and_dismiss(messages.ERROR)
    LOG.tc_step('Verifies that the floating ip does not appear in the table')
    assert not floating_ips_pg_admin.is_floatingip_present(floating_ip)
    horizon.test_result = True
