import random
from utils.horizon.regions import messages
from utils.horizon.pages.project.network import securitygroupspage
from pytest import fixture
from utils.horizon import helper
from utils.tis_log import LOG


class TestSecuritygroup(helper.TenantTestCase):
    SEC_GROUP_NAME = None
    RULE_PORT = str(random.randint(9000, 9999))

    @fixture(scope='function')
    def securitygroups_pg(self, home_pg, request):
        LOG.fixture_step('Go to Project > Network > Security Groups')
        self.SEC_GROUP_NAME = helper.gen_resource_name('sec_group')
        securitygroups_pg = securitygroupspage.SecuritygroupsPage(home_pg.driver)
        securitygroups_pg.go_to_target_page()

        def teardown():
            LOG.fixture_step('Back to Security Groups page')
            securitygroups_pg.go_to_target_page()

        request.addfinalizer(teardown)
        return securitygroups_pg

    @fixture(scope='function')
    def securitygroups_pg_action(self, securitygroups_pg, request):
        LOG.fixture_step('Create new security group {}'.format(self.SEC_GROUP_NAME))
        self._create_securitygroup(securitygroups_pg)

        def teardown():
            LOG.fixture_step('Delete security group {}'.format(self.SEC_GROUP_NAME))
            self._delete_securitygroup(securitygroups_pg)

        request.addfinalizer(teardown)
        return securitygroups_pg


    def _create_securitygroup(self, securitygroupspage):
        securitygroupspage.create_securitygroup(self.SEC_GROUP_NAME)
        assert securitygroupspage.find_message_and_dismiss(messages.SUCCESS)
        assert not securitygroupspage.find_message_and_dismiss(messages.ERROR)
        assert securitygroupspage.is_securitygroup_present(self.SEC_GROUP_NAME)

    def _delete_securitygroup(self, securitygroupspage):
        securitygroupspage.delete_securitygroup(self.SEC_GROUP_NAME)
        assert securitygroupspage.find_message_and_dismiss(messages.SUCCESS)
        assert not securitygroupspage.find_message_and_dismiss(messages.ERROR)
        assert not securitygroupspage.is_securitygroup_present(self.SEC_GROUP_NAME)

    def test_securitygroup_create_delete(self, securitygroups_pg):
        """
        Test the security group creation and deletion functionality:

        Setups:
            - Login as Tenant
            - Go to Project > Network > Security Groups

        Teardown:
            - Back to Security Groups page
            - Logout

        Test Steps:
            - Create a new security group
            - Verify the security group appears in the security groups table
            - Delete the newly created security group
            - Verify the security group does not appear in the table after deletion
        """

        LOG.tc_step('Create new security group {} and Verify it appears in the security groups table'
                    .format(self.SEC_GROUP_NAME))
        self._create_securitygroup(securitygroups_pg)

        LOG.tc_step('Delete security group {} and Verify it does not appear in the table'
                    .format(self.SEC_GROUP_NAME))
        self._delete_securitygroup(securitygroups_pg)

    def test_managerules_create_delete(self, securitygroups_pg_action):
        """
        Test the manage rules creation and deletion functionality:

        Setups:
            - Login as Tenant
            - Go to Project > Network > Security Groups
            - Create a new security group
        Teardown:
            - Delete the newly created security group
            - Back to Security group page
            - Logout

        Test Steps:
            - Create a new rule
            - Verify the rule appears in the rules table
            - Delete the newly created rule
            - Verify the rule does not appear in the table after deletion
        """
        LOG.tc_step('Create new rule {}'.format(self.RULE_PORT))
        managerulespage = securitygroups_pg_action.go_to_manage_rules(self.SEC_GROUP_NAME)
        managerulespage.create_rule(self.RULE_PORT)
        assert managerulespage.find_message_and_dismiss(messages.SUCCESS)

        LOG.tc_step('Verify the rule appears in the rules table')
        assert managerulespage.is_port_present(self.RULE_PORT)

        LOG.tc_step('Delete rule {}'.format(self.RULE_PORT))
        managerulespage.delete_rule(self.RULE_PORT)
        assert managerulespage.find_message_and_dismiss(messages.SUCCESS)
        assert not managerulespage.find_message_and_dismiss(messages.ERROR)

        LOG.tc_step('Verify the rule does not appear in the table after deletion')
        assert not managerulespage.is_port_present(self.RULE_PORT)

        securitygroups_pg_action.go_to_target_page()

    def test_managerules_create_delete_by_table(self, securitygroups_pg_action):
        """
        Test the manage rules creation and deletion functionality:

        Setups:
            - Login as Tenant
            - Go to Project > Network > Security Groups
            - Create a new security group
        Teardown:
            - Delete the newly created security group
            - Back to Security group page
            - Logout

        Test Steps:
            - Create a new rule
            - Verify the rule appears in the rules table
            - Delete the newly created rule
            - Verify the rule does not appear in the table after deletion
        """

        LOG.tc_step('Create new rule {}'.format(self.RULE_PORT))
        managerulespage = securitygroups_pg_action.go_to_manage_rules(self.SEC_GROUP_NAME)
        managerulespage.create_rule(self.RULE_PORT)
        assert managerulespage.find_message_and_dismiss(messages.SUCCESS)

        LOG.tc_step('Verify the rule appears in the rules table')
        assert managerulespage.is_port_present(self.RULE_PORT)

        LOG.tc_step('Delete rule {}'.format(self.RULE_PORT))
        managerulespage.delete_rules(self.RULE_PORT)
        assert managerulespage.find_message_and_dismiss(messages.SUCCESS)
        assert not managerulespage.find_message_and_dismiss(messages.ERROR)

        LOG.tc_step('Verify the rule does not appear in the table after deletion')
        assert not managerulespage.is_port_present(self.RULE_PORT)

        securitygroups_pg_action.go_to_target_page()
