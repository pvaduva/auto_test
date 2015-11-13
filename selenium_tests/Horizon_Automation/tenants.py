from selenium.webdriver import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from common_utils import DriverUtils
import settings
import time

__author__ = 'jbarber'


class Tenants():

    @classmethod
    def tenants(cls, username, password, email, project_name):
        print "Create Users (Identity -> Users)------------------------------------------------------------------------"
        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        # Append to end of URL
        driver.get(DriverUtils.set_url(url + "/identity/users/"))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        # Call Functions below
        cls.create_tenant(username, password, email, project_name)
        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)

    @classmethod
    def create_tenant(cls, username, password, email, project_name):
        driver = DriverUtils.get_driver()
        # Locate create users button
        create_button = driver.find_element_by_id("users__action_create")
        create_button.click()
        # Locate password input field
        password_input_field = driver.find_element_by_id("id_password")
        password_input_field.send_keys(password)
        # Locate confirm password input field
        password_confirm_input_field = driver.find_element_by_id("id_confirm_password")
        password_confirm_input_field.send_keys(password)
        # Locate username input field
        username_input_field = driver.find_element_by_id("id_name")
        username_input_field.send_keys(username)
        # Locate email input field
        email_input_field = driver.find_element_by_id("id_email")
        email_input_field.send_keys(email)
        # Create project
        cls.create_project(project_name)
        time.sleep(1)
        # Select newly created project
        project = Select(driver.find_element_by_id("id_project"))
        project.select_by_visible_text(project_name)
        email_input_field.submit()


    @classmethod
    def create_project(cls, project_name):
        driver = DriverUtils.get_driver()
        # Locate create project button
        create_button = driver.find_element_by_css_selector(".ajax-add")
        create_button.click()
        time.sleep(2)
        # Locate name input field (WORK AROUND (Kinda))
        # (Name of username input field above conflicts with project name id)
        actions = ActionChains(driver)
        actions.send_keys(project_name)
        actions.perform()
        # Find element on web form to perform easy submit
        desc = driver.find_element_by_id("id_description")
        desc.submit()
