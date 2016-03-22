'''
tenants.py - Handles the creation of tenants (users and projects)

Copyright (c) 2015 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.


Contains function: create tenant, create project, get project id
'''

'''
modification history:
---------------------
26nov15,jbb  Initial file
3dec15,jbb   Add check if tenant exists
'''

from selenium.webdriver import ActionChains
from selenium.webdriver.support.ui import Select
from common_utils import DriverUtils
import settings
import time


class Tenants():

    @classmethod
    def tenants(cls, username, password, email, project_name):
        """
        Function for initializing tenants class

        :param username: username of tenant
        :param password: password of tenant
        :param email: email of tenant
        :param project_name: name of project
        """

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
        return_value = cls.check_tenants(username)
        if(return_value == 1):
            # Reset URL to home page in Horizon
            DriverUtils.set_url(settings.DEFAULT_URL)
            time.sleep(settings.DEFAULT_SLEEP_TIME)
            return
        else:
            pass
        cls.create_tenant(username, password, email, project_name)
        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)
        time.sleep(settings.DEFAULT_SLEEP_TIME)

    @classmethod
    def check_tenants(cls, username):
        """
        Function to check tenants list
        Note: This a workaround because lab_cleanup.sh does not tenants (users or projects)
        :param username: username of tenant

        :return return_value: 1 tenant found, 0 tenant not found
        """

        return_value = -1
        driver = DriverUtils.get_driver()
        # Get link from partial text in host table (Host Name column)
        links = driver.find_elements_by_partial_link_text('')
        for link in links:
            tenant_local = link.get_attribute("text")
            # Match host_local link name with compute
            if(username in tenant_local):
                return 1
            else:
                return_value = 0
        return return_value

    @classmethod
    def create_tenant(cls, username, password, email, project_name):
        """
        Function for creating a tenant user

        :param username: username of tenant
        :param password: password of tenant
        :param email: email of tenant
        :param project_name: name of project
        """

        print "Create User (Identity -> Users)-------------------------------------------------------------------------"
        print username
        # Get driver
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
        time.sleep(settings.DEFAULT_SLEEP_TIME)
        # Select newly created project
        project = Select(driver.find_element_by_id("id_project"))
        project.select_by_visible_text(project_name)
        email_input_field.submit()

    @classmethod
    def create_project(cls, project_name):
        """
        Function for creating a tenant project

        :param project_name: name of project
        """

        print "Create Project (Identity -> Projects)-------------------------------------------------------------------"
        print project_name
        # Get driver
        driver = DriverUtils.get_driver()
        # Locate create project button
        create_button = driver.find_element_by_css_selector(".ajax-add")
        create_button.click()
        time.sleep(settings.DEFAULT_SLEEP_TIME)
        # Locate name input field (WORK AROUND (Kinda))
        # (Name of username input field above conflicts with project name id)
        actions = ActionChains(driver)
        actions.send_keys(project_name)
        actions.perform()
        # Find element on web form to perform easy submit
        desc = driver.find_element_by_id("id_description")
        desc.submit()
