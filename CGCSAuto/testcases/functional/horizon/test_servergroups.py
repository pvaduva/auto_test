from pytest import fixture, mark

from utils.horizon.regions import messages
from utils.horizon.pages.project.compute import servergroupspage, instancespage
from utils.horizon import helper
from utils.tis_log import LOG
from consts import horizon
from consts.auth import Tenant
from keywords import network_helper
from testfixtures.horizon import tenant_home_pg, driver


class TestServerGroup:

    GROUP_NAME = None
    INSTANCE_NAME = None

    @fixture(scope='function')
    def server_groups_pg(self, tenant_home_pg, request):
        LOG.fixture_step('Go to Project > Compute > Server Groups')
        self.GROUP_NAME = helper.gen_resource_name('groups')
        self.INSTANCE_NAME = helper.gen_resource_name('instance_groups')
        instances_pg = instancespage.InstancesPage(tenant_home_pg.driver)
        groups_pg = servergroupspage.ServerGroupsPage(tenant_home_pg.driver)
        groups_pg.go_to_target_page()

        def teardown():
            instances_pg.go_to_target_page()
            if instances_pg.is_instance_present(self.INSTANCE_NAME):
                instances_pg.delete_instance_by_row(self.INSTANCE_NAME)
            groups_pg.go_to_target_page()
            if groups_pg.is_server_group_present(self.GROUP_NAME):
                groups_pg.delete_server_group(name=self.GROUP_NAME)

        request.addfinalizer(teardown)
        return groups_pg

    @mark.parametrize(('policy', 'is_best_effort', 'group_size', 'source_name', 'flavor_name'), [
        ('affinity', True, 10, 'tis-centos-guest', 'small'),
        ('anti-affinity', None, None, 'tis-centos-guest', 'small')
    ])
    def test_create_delete_server_group(self, server_groups_pg,
                                        policy,
                                        is_best_effort,
                                        group_size,
                                        source_name,
                                        flavor_name):
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
        LOG.tc_step('Create a new server group')
        server_groups_pg.create_server_group(name=self.GROUP_NAME,
                                             policy=policy,
                                             is_best_effort=is_best_effort,
                                             group_size=group_size)
        assert not server_groups_pg.find_message_and_dismiss(messages.ERROR), \
            '{} creation error'.format(self.GROUP_NAME)

        LOG.tc_step('Verify the group appears in server groups table')
        assert server_groups_pg.is_server_group_present(self.GROUP_NAME)

        LOG.tc_step('Launch instance with new created server group')
        mgmt_net_id = network_helper.get_mgmt_net_id(auth_info=Tenant.get('tenant1'))
        network_names = network_helper.get_net_name_from_id(net_id=mgmt_net_id, auth_info=Tenant.get('tenant1'))
        instances_pg = instancespage.InstancesPage(server_groups_pg.driver)
        instances_pg.go_to_target_page()
        instances_pg.create_instance(self.INSTANCE_NAME,
                                     source_name=source_name,
                                     flavor_name=flavor_name,
                                     network_names=[network_names],
                                     server_group_name=self.GROUP_NAME)
        assert not instances_pg.find_message_and_dismiss(messages.ERROR), \
            'instance: {} creation error'.format(self.INSTANCE_NAME)

        LOG.tc_step('Verify the instance status is active')
        assert instances_pg.is_instance_active(self.INSTANCE_NAME), \
            'instance: {} status is not active'.format(self.INSTANCE_NAME)

        horizon.test_result = True
