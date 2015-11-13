from selenium.webdriver import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from common_utils import DriverUtils
import constants
import settings
import time

__author__ = 'jbarber'


class Routers():

    @classmethod
    def routers(cls, router_name, external_network_name):
        print "Create Routers (Admin -> System -> Routers)-------------------------------------------------------------"
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
        time.sleep(5)
        router_full_link = cls.get_router_link(router_name)
        if(router_full_link == -1):
            print "Error finding flavor name"
            return
        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)
        return router_full_link

    @classmethod
    def create_router(cls, router_name, external_network_name):
        # Get driver
        driver = DriverUtils.get_driver()

        create_button = driver.find_element_by_id("Routers__action_create")
        create_button.click()

        router_name_input = driver.find_element_by_id("id_name")
        router_name_input.click()
        router_name_input.send_keys(router_name)

        external_network_name_input = Select(driver.find_element_by_id("id_external_network"))
        external_network_name_input.select_by_visible_text(external_network_name)

        router_name_input.submit()

    @classmethod
    def get_router_link(cls, router_name):
        router_id_link = -1
        # TODO: Grab driver, read table, compare to user_name, navigate to modify quotas section!
        # Read table, match name with project ID, use constants like in 'lock_host.py'
        # tuple of Name and Project ID
        # Get driver
        driver = DriverUtils.get_driver()

        # Get link from partial text in table (Host Name column)
        links = driver.find_elements_by_partial_link_text('')
        for link in links:
            host_local = link.get_attribute("text")
            #print host_local
            # Match host_to_lock with link
            if(router_name in host_local):
                router_id_link = link.get_attribute("href")
        # Append to end of URL
        driver.get(DriverUtils.set_url(router_id_link + constants.ROUTER_INTERFACE_TAB))
        print router_id_link
        return router_id_link

    @classmethod
    def create_router_interface(cls, router_link, subnet_name, subnet_ip):
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
        subnet_ip_input.click()
        subnet_ip_input.send_keys(subnet_ip)

        subnet_ip_input.submit()
        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)

