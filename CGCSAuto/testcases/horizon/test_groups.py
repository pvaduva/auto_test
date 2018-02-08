from utils.horizon.regions import messages
from utils.horizon.pages.identity import groupspage
from selenium import webdriver
from utils.horizon.pages import loginpage
from time import sleep


class TestGroup:
    """Checks if the user is able to create/delete/edit groups"""

    GROUP_NAME = 'group_test'  # helpers.gen_random_resource_name("flavor")
    GROUP_DESCRIPTION = 'description_test'
    driver = webdriver.Firefox()
    login_pg = loginpage.LoginPage(driver)
    login_pg.go_to_login_page()
    home_pg = login_pg.login('admin', 'Li69nux*')
    groups_pg = groupspage.GroupsPage(home_pg.driver)
    groups_pg.go_to_groups_page()
    sleep(2)

    def _test_create_group(self):
        self.groups_pg.create_group(name=self.GROUP_NAME, description=self.GROUP_DESCRIPTION)
        assert self.groups_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not self.groups_pg.find_message_and_dismiss(messages.ERROR)
        sleep(5)  # the goups created cannot appear on time
        assert self.groups_pg.is_group_present(self.GROUP_NAME)

    def _test_delete_group(self,group_name):
        self.groups_pg.delete_group(name=group_name)
        assert self.groups_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not self.groups_pg.find_message_and_dismiss(messages.ERROR)
        assert not self.groups_pg.is_group_present(self.GROUP_NAME)

    def test_create_delete_group(self):
        """Tests ability to create and delete a group"""
        self._test_create_group()
        self._test_delete_group(self.GROUP_NAME)

    def test_edit_group(self):
        """Tests ability to edit group name and description"""
        self._test_create_group()
        new_group_name = 'edited-' + self.GROUP_NAME
        new_group_desc = 'edited-' + self.GROUP_DESCRIPTION
        self.groups_pg.edit_group(self.GROUP_NAME, new_group_name, new_group_desc)
        assert self.groups_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not self.groups_pg.find_message_and_dismiss(messages.ERROR)
        assert self.groups_pg.is_group_present(new_group_name)
        self._test_delete_group(new_group_name)
