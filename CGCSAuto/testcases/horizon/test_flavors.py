import random

from utils.horizon.regions import messages
from utils.horizon.pages.admin.system import flavorspage
from selenium import webdriver
from utils.horizon.pages import loginpage
from time import sleep


class TestFlavors:
    
    FLAVOR_NAME = 'flavor_test'  # helpers.gen_random_resource_name("flavor")

    driver = webdriver.Firefox()
    login_pg = loginpage.LoginPage(driver)
    login_pg.go_to_login_page()
    home_pg = login_pg.login('admin', 'Li69nux*')
    flavors_pg = flavorspage.FlavorsPage(home_pg.driver)
    flavors_pg.go_to_flavors_page()
    sleep(2)

    def _create_flavor(self, flavor_name):
        self.flavors_pg.create_flavor(
            name=flavor_name,
            vcpus=1,
            ram=1024,
            root_disk=20,
            ephemeral_disk=0,
            swap_disk=0
        )
        assert self.flavors_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not self.flavors_pg.find_message_and_dismiss(messages.ERROR)
        assert self.flavors_pg.is_flavor_present(self.FLAVOR_NAME)

    def _delete_flavor(self, flavor_name):
        self.flavors_pg.delete_flavor_by_row(flavor_name)
        assert self.flavors_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not self.flavors_pg.find_message_and_dismiss(messages.ERROR)
        assert not self.flavors_pg.is_flavor_present(self.FLAVOR_NAME)

    def test_flavor_header(self):
        header_text = self.driver.find_element_by_xpath("//div[@class = 'page-header']/h1").text
        assert header_text == 'Flavors'

    def test_flavor_create(self):
        """tests the flavor creation and deletion functionalities:

        * creates a new flavor
        * verifies the flavor appears in the flavors table
        * deletes the newly created flavor
        * verifies the flavor does not appear in the table after deletion
        """
        self._create_flavor(self.FLAVOR_NAME)
        self._delete_flavor(self.FLAVOR_NAME)

    def test_flavor_update_info(self):
        """Tests the flavor Edit row action functionality"""

        self._create_flavor(self.FLAVOR_NAME)

        add_up = random.randint(1, 10)
        old_vcpus = self.flavors_pg.get_flavor_vcpus(self.FLAVOR_NAME)
        old_disk = self.flavors_pg.get_flavor_disk(self.FLAVOR_NAME)

        self.flavors_pg.update_flavor_info(self.FLAVOR_NAME, add_up)

        assert self.flavors_pg.find_message_and_dismiss(messages.SUCCESS)
        assert not self.flavors_pg.find_message_and_dismiss(messages.ERROR)
        assert self.flavors_pg.is_flavor_present("edited-" + self.FLAVOR_NAME)

        new_vcpus = self.flavors_pg.get_flavor_vcpus(
            "edited-" + self.FLAVOR_NAME)
        new_disk = self.flavors_pg.get_flavor_disk(
            "edited-" + self.FLAVOR_NAME)

        assert not old_disk == new_disk
        assert not old_vcpus == new_vcpus

        self._delete_flavor("edited-" + self.FLAVOR_NAME)

    # HOME_PROJECT = 'admin'

    '''def test_flavor_update_access(self):
        self._create_flavor(self.FLAVOR_NAME)

        self.flavors_pg.update_flavor_access(self.FLAVOR_NAME,
                                               self.HOME_PROJECT)

        assert not self.flavors_pg.is_flavor_public(self.FLAVOR_NAME)

        self.flavors_pg.update_flavor_access(self.FLAVOR_NAME,
                                               self.HOME_PROJECT,
                                               allocate=False)

        assert self.flavors_pg.is_flavor_public(self.FLAVOR_NAME)

        self._delete_flavor(self.FLAVOR_NAME)'''

    '''def test_flavor_module_exists(self):    # skipped first matt
        js_cmd = "$('html').append('<div id=\"testonly\">'"\
            " + angular.module('horizon.app.core.flavors').name"\
            " + '</div>');"
        self.driver.execute_script(js_cmd)
        value = self.driver.find_element_by_id('testonly').text
        assert value == 'horizon.app.core.flavors'''''