import random
from utils.horizon.regions import messages
from utils.horizon.pages.project.network import securitygroupspage
from pytest import fixture
from utils.horizon import helper
from utils.tis_log import LOG
from testfixtures.horizon import tenant_home_pg, driver
from consts import horizon


class TestSecurityGroup:
    SEC_GROUP_NAME = None
    RULE_PORT = str(random.randint(9000, 9999))

    @fixture(scope='function')
    def security_groups_pg(self, tenant_home_pg, request):
        LOG.fixture_step('Go to Project > Network > Security Groups')
        self.SEC_GROUP_NAME = helper.gen_resource_name('sec_group')
        security_groups_pg = securitygroupspage.SecuritygroupsPage(tenant_home_pg.driver)
        security_groups_pg.go_to_target_page()

        def teardown():
            LOG.fixture_step('Back to Security Groups page')
            security_groups_pg.go_to_target_page()

        request.addfinalizer(teardown)
        return security_groups_pg

    @fixture(scope='function')
    def security_groups_pg_action(self, security_groups_pg, request):
        LOG.fixture_step('Create new security group {}'.format(self.SEC_GROUP_NAME))
        security_groups_pg.create_securitygroup(self.SEC_GROUP_NAME)

        def teardown():
            LOG.fixture_step('Delete security group {}'.format(self.SEC_GROUP_NAME))
            security_groups_pg.delete_securitygroup(self.SEC_GROUP_NAME)

        request.addfinalizer(teardown)
        return security_groups_pg

    def test_securitygroup_create_delete(self, security_groups_pg):
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
        security_groups_pg.create_securitygroup(self.SEC_GROUP_NAME)
        assert security_groups_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not security_groups_pg.find_message_and_dismiss(messages.ERROR)
        assert security_groups_pg.is_securitygroup_present(self.SEC_GROUP_NAME)

        LOG.tc_step('Delete security group {} and Verify it does not appear in the table'
                    .format(self.SEC_GROUP_NAME))
        security_groups_pg.delete_securitygroup(self.SEC_GROUP_NAME)
        assert security_groups_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not security_groups_pg.find_message_and_dismiss(messages.ERROR)
        assert not security_groups_pg.is_securitygroup_present(self.SEC_GROUP_NAME)
        horizon.test_result = True

    def test_managerules_create_delete(self, security_groups_pg_action):
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
        managerulespage = security_groups_pg_action.go_to_manage_rules(self.SEC_GROUP_NAME)
        managerulespage.create_rule(self.RULE_PORT)
        assert managerulespage.find_message_and_dismiss(messages.SUCCESS)

        LOG.tc_step('Verify the rule appears in the rules table')
        assert managerulespage.is_rule_present(self.RULE_PORT)

        LOG.tc_step('Delete rule {}'.format(self.RULE_PORT))
        managerulespage.delete_rule(self.RULE_PORT)
        assert managerulespage.find_message_and_dismiss(messages.SUCCESS)
        assert not managerulespage.find_message_and_dismiss(messages.ERROR)

        LOG.tc_step('Verify the rule does not appear in the table after deletion')
        assert not managerulespage.is_rule_present(self.RULE_PORT)

        security_groups_pg_action.go_to_target_page()
        horizon.test_result = True

    def test_managerules_create_delete_by_table(self, security_groups_pg_action):
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
        managerulespage = security_groups_pg_action.go_to_manage_rules(self.SEC_GROUP_NAME)
        managerulespage.create_rule(self.RULE_PORT)
        assert managerulespage.find_message_and_dismiss(messages.SUCCESS)

        LOG.tc_step('Verify the rule appears in the rules table')
        assert managerulespage.is_rule_present(self.RULE_PORT)

        LOG.tc_step('Delete rule {}'.format(self.RULE_PORT))
        managerulespage.delete_rule(self.RULE_PORT)
        assert managerulespage.find_message_and_dismiss(messages.SUCCESS)
        assert not managerulespage.find_message_and_dismiss(messages.ERROR)

        LOG.tc_step('Verify the rule does not appear in the table after deletion')
        assert not managerulespage.is_rule_present(self.RULE_PORT)

        security_groups_pg_action.go_to_target_page()
        horizon.test_result = True
