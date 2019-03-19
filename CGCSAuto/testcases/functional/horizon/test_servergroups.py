import time

from pytest import fixture, mark

from consts import horizon
from consts.auth import Tenant
from consts.cgcs import GuestImages
from keywords import nova_helper
from utils.tis_log import LOG
from utils.horizon import helper
from utils.horizon.regions import messages
from utils.horizon.pages.project.compute import servergroupspage, instancespage


@fixture(scope='function')
def server_groups_pg(tenant_home_pg_container, request):
    LOG.fixture_step('Go to Project > Compute > Server Groups')
    group_name = helper.gen_resource_name('groups')
    instance_name = helper.gen_resource_name('instance_groups')
    instances_pg = instancespage.InstancesPage(tenant_home_pg_container.driver, port=tenant_home_pg_container.port)
    groups_pg = servergroupspage.ServerGroupsPage(tenant_home_pg_container.driver, port=tenant_home_pg_container.port)
    groups_pg.go_to_target_page()

    def teardown():
        instances_pg.go_to_target_page()
        if instances_pg.is_instance_present(instance_name):
            instances_pg.delete_instance_by_row(instance_name)
        groups_pg.go_to_target_page()
        time.sleep(5)
        if groups_pg.is_server_group_present(group_name):
            groups_pg.delete_server_group(name=group_name)

    request.addfinalizer(teardown)
    return groups_pg, group_name, instance_name


@mark.parametrize('policy', [
    'affinity',
    'anti-affinity'
])
def test_horizon_create_delete_server_group(server_groups_pg,
                                            policy):
    """
    Tests the server group creation and deletion functionality:

    Setups:
        - Login as Tenant
        - Go to Project > Compute > Server Groups page

    Teardown:
        - Go to instance page
        - Delete the created instance
        - Go to server group page
        - Delete the created group server
        - Logout

    Test Steps:
        - Create a new server group
        - Verify the group appears in server groups table
        - Launch instance with new created server group
        - Verify the instance status is active
    """
    server_groups_pg, group_name, instance_name = server_groups_pg

    # is_best_effort = True if best_effort == 'best_effort' else False
    LOG.tc_step('Create a new server group')
    server_groups_pg.create_server_group(name=group_name,
                                         policy='string:' + policy)
    assert not server_groups_pg.find_message_and_dismiss(messages.ERROR), \
        '{} creation error'.format(group_name)

    LOG.tc_step('Verify the group appears in server groups table')
    assert server_groups_pg.is_server_group_present(group_name)

    LOG.tc_step('Launch instance with new created server group')
    mgmt_net_name = '-'.join([Tenant.get_primary()['tenant'], 'mgmt', 'net'])
    flavor_name = nova_helper.get_basic_flavor(rtn_id=False)
    guest_img = GuestImages.DEFAULT_GUEST
    instances_pg = instancespage.InstancesPage(server_groups_pg.driver, port=server_groups_pg.port)
    instances_pg.go_to_target_page()
    instances_pg.create_instance(instance_name,
                                 source_name=guest_img,
                                 flavor_name=flavor_name,
                                 network_names=[mgmt_net_name],
                                 server_group_name=group_name)
    assert not instances_pg.find_message_and_dismiss(messages.ERROR), \
        'instance: {} creation error'.format(instance_name)

    LOG.tc_step('Verify the instance status is active')
    assert instances_pg.is_instance_active(instance_name), \
        'instance: {} status is not active'.format(instance_name)

    horizon.test_result = True
