'''
routers.py - Handles the creation of routers and router interfaces

Copyright (c) 2015 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.


Contains function: create router, create router interface,
and router distribution
'''

'''
modification history:
---------------------
26nov15,jbb  Initial file
30nov15,jbb  Add fail messages
'''

from selenium.webdriver.support.ui import Select
from common_utils import DriverUtils
import constants
import settings
import time


class Routers():

    @classmethod
    def routers(cls, router_name, external_network_name):
        """
        Function for initializing routers class

        :param router_name: name of router
        :param external_network_name: name of external network
        :return router_full_link: link of router details for specified router
        """

        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        # Append to end of URL
        driver.get(DriverUtils.set_url(url + "/project/routers/"))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        # Call Functions below
        cls.create_router(router_name, external_network_name)
        time.sleep(settings.DEFAULT_SLEEP_TIME)
        router_full_link = cls.get_router_link(router_name)
        if(router_full_link == -1):
            print "Test: FAIL - Error finding flavor name"
            return
        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)
        time.sleep(settings.DEFAULT_SLEEP_TIME)
        return router_full_link

    @classmethod
    def create_router(cls, router_name, external_network_name):
        """
        Function for creating a router

        :param router_name: name of router
        :param external_network_name: name of external network
        """

        print "Create Router (Admin -> System -> Routers)--------------------------------------------------------------"
        print router_name
        # Get driver
        driver = DriverUtils.get_driver()

        create_button = driver.find_element_by_id("Routers__action_create")
        create_button.click()

        router_name_input = driver.find_element_by_id("id_name")
        router_name_input.send_keys(router_name)

        external_network_name_input = Select(driver.find_element_by_id("id_external_network"))
        external_network_name_input.select_by_visible_text(external_network_name)

        router_name_input.submit()

    @classmethod
    def get_router_link(cls, router_name):
        """
        Function for getting details page of specified router

        :param router_name: name of router
        :return router_full_link: link of router details for specified router
        """

        router_id_link = -1
        # Get driver
        driver = DriverUtils.get_driver()
        # Get link from partial text in table (Host Name column)
        links = driver.find_elements_by_partial_link_text('')
        for link in links:
            host_local = link.get_attribute("text")
            # Match host_to_lock with link
            if(router_name in host_local):
                router_id_link = link.get_attribute("href")
        # Append to end of URL
        driver.get(DriverUtils.set_url(router_id_link + constants.ROUTER_INTERFACE_TAB))
        return router_id_link

    @classmethod
    def create_router_interface(cls, router_link, subnet_name, subnet_ip):
        """
        Function for creating a router interface

        :param router_link: link of router details for specified router
        :param subnet_name: name of subnet
        :param subnet_ip: ip of subnet
        """

        print "Create Router Interface (Admin -> System -> Routers)----------------------------------------------------"
        print subnet_name
        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        # Append to end of URL
        driver.get(DriverUtils.set_url(router_link + constants.ROUTER_INTERFACE_TAB))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        create_button = driver.find_element_by_id("interfaces__action_create")
        create_button.click()

        subnet_name_input = Select(driver.find_element_by_id("id_subnet_id"))
        subnet_name_input.select_by_visible_text(subnet_name)

        subnet_ip_input = driver.find_element_by_id("id_ip_address")
        subnet_ip_input.send_keys(subnet_ip)

        subnet_ip_input.submit()
        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)
        time.sleep(settings.DEFAULT_SLEEP_TIME)

    @classmethod
    def router_distributed(cls, router_link, distributed):
        """
        Function for changing router distribution

        :param router_link: link of router details for specified router
        :param distributed: True or False
        """

        if(distributed == False):
            pass
        else:
            # Get driver
            driver = DriverUtils.get_driver()
            # Get URL text from class
            url = DriverUtils.get_url()
            # Append to end of URL
            driver.get(DriverUtils.set_url(router_link))
            # Navigate to newly appended URL
            driver.get(DriverUtils.get_url())
            # Wait for elements on page to load
            DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)

            # Parse router link
            parse = router_link.split("/")
            router_id = parse[5]

            # Edit router button

            edit_dropdown_button = driver.find_element_by_css_selector(constants.ROUTER_EDIT_INTERFACE_DROPDOWN)
            edit_dropdown_button.click()

            edit_button = constants.ROUTER_EDIT_INTERFACE_FIRST_HALF + router_id + constants.ROUTER_EDIT_INTERFACE_SECOND_HALF

            edit_button_input = driver.find_element_by_id(edit_button)
            edit_button_input.click()

            distributed_input = Select(driver.find_element_by_id("id_mode"))
            distributed_input.select_by_visible_text("Distributed")

            # Get name for form submission
            name_input = driver.find_element_by_id("id_name")
            name_input.submit()

            # Reset URL to home page in Horizon
            DriverUtils.set_url(settings.DEFAULT_URL)
            time.sleep(settings.DEFAULT_SLEEP_TIME)

