from selenium.webdriver import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from common_utils import DriverUtils
import constants
import settings
import time

__author__ = 'jbarber'


class Hosts():

    @classmethod
    def hosts(cls):
        print "Check Hosts (Admin -> System -> Inventory)----------------------------------------------------------"
        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        # Append to end of URL
        driver.get(DriverUtils.set_url(url + "/admin/inventory/?tab=inventory__hosts"))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        # Call Functions below
        host_list = cls.get_hosts()
        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)
        return host_list

    @classmethod
    def get_hosts(cls):
        #print host_to_lock
        host_list = []
        row_number = -1
        driver = DriverUtils.get_driver()

        # Get link from partial text in table (Host Name column)
        links = driver.find_elements_by_partial_link_text('')
        for link in links:
            host_local = link.get_attribute("text")
            #print host_local
            # Match host_to_lock with link
            if("compute" in host_local):
                parse = link.get_attribute("href")
                # Parse number from link
                parse = parse.split("/")
                #print parse
                # Find the number in the list
                for num in parse:
                    if num.isdigit():
                        row_number = num
                temp_tuple = [host_local, row_number]
                host_list.append(temp_tuple)
        for item in host_list:
            host = item[0]
            row = item[1]
            # Call function to check Avail State
            print host
            return_value = cls.check_host_avail_state(row)
            if(return_value == 0):
                print "Host is online"
            if(return_value == 1):
                print "Host is in an invalide state"
        return host_list

    @classmethod
    def check_host_avail_state(cls, row_number):
        return_value = -1
        driver = DriverUtils.get_driver()
        host_label = constants.HOST_CHECK_AVAIL_STATE_FIST_HALF + str(row_number) + constants.HOST_CHECK_AVAIL_STATE_SECOND_HALF
        check = driver.find_element_by_css_selector(host_label)
        if("Online" in check.text):
            print "Host Status: Host is locked"
            return_value = 0
        else:
            return 1
        return return_value

    @classmethod
    def create_interface(cls, host_name, iface_name, network_type, iface_type, eth_mode, ports, mtu, *provider_networks):
        host_link = ""
        print host_name
        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL of compute passed to function
        # Get link from partial text in table (Host Name column)
        links = driver.find_elements_by_partial_link_text('')
        for link in links:
            host_local = link.get_attribute("text")
            # Match host_to_lock with link
            if(host_name in host_local):
                host_link = link.get_attribute("href")
        print host_link
        # Append to end of URL
        driver.get(DriverUtils.set_url(host_link + constants.HOST_INTERFACE_TAB))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        create_button = driver.find_element_by_id("interfaces__action_create")
        create_button.click()

        iface_name_input = driver.find_element_by_id("id_ifname")
        iface_name_input.click()
        iface_name_input.send_keys(iface_name)

        network_type_input = Select(driver.find_element_by_id("id_networktype_2"))
        network_type_input.select_by_visible_text(network_type)

        iface_type_input = Select(driver.find_element_by_id("id_iftype"))
        iface_type_input.select_by_visible_text(iface_type)

        # Ports
        ports_input = driver.find_element_by_id("id_ports_0")
        ports_input.click()

        # Provider Networks
        # For loop
        for item in provider_networks:
            provider_networks_input1 = driver.find_element_by_id("id_providernetworks_data_0")
            provider_networks_input1.click()
            provider_networks_input2 = driver.find_element_by_id("id_providernetworks_data_1")
            provider_networks_input2.click()
            provider_networks_input3 = driver.find_element_by_id("id_providernetworks_data_3")
            provider_networks_input3.click()

        mtu_input = driver.find_element_by_id("id_imtu")
        mtu_input.click()
        mtu_input.send_keys(mtu)
        mtu_input.submit()

        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)

    @classmethod
    def create_interface_profile(cls, host_name, if_profile_name):
        host_link = ""
        print host_name
        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        # Append to end of URL
        driver.get(DriverUtils.set_url(url + "/admin/inventory/?tab=inventory__hosts"))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        # Get URL of compute passed to function
        # Get link from partial text in table (Host Name column)
        links = driver.find_elements_by_partial_link_text('')
        for link in links:
            host_local = link.get_attribute("text")
            # Match host_to_lock with link
            if(host_name in host_local):
                host_link = link.get_attribute("href")
        print host_link
        # Append to end of URL
        driver.get(DriverUtils.set_url(host_link + constants.HOST_INTERFACE_TAB))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        create_button = driver.find_element_by_id("interfaces__action_createProfile")
        create_button.click()

        if_profile_name_input = driver.find_element_by_id("id_hostname")
        if_profile_name_input.click()
        if_profile_name_input.send_keys(if_profile_name)
        if_profile_name_input.submit()

        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)

    @classmethod
    def create_cpu_profile(cls, host_name, cpu_profile_name):
        host_link = ""
        print host_name
        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        # Append to end of URL
        driver.get(DriverUtils.set_url(url + "/admin/inventory/?tab=inventory__hosts"))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        # Get URL of compute passed to function
        # Get link from partial text in table (Host Name column)
        links = driver.find_elements_by_partial_link_text('')
        for link in links:
            host_local = link.get_attribute("text")
            # Match host_to_lock with link
            if(host_name in host_local):
                host_link = link.get_attribute("href")
        print host_link
        # Append to end of URL
        driver.get(DriverUtils.set_url(host_link + constants.HOST_PROCESSOR_TAB))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        create_button = driver.find_element_by_id("cpufunctions__action_createCpuProfile")
        create_button.click()

        cpu_profile_name_input = driver.find_element_by_id("id_hostname")
        cpu_profile_name_input.click()
        cpu_profile_name_input.send_keys(cpu_profile_name)
        cpu_profile_name_input.submit()

        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)

    @classmethod
    def create_mem_profile(cls, host_name, mem_profile_name):
        host_link = ""
        print host_name
        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        # Append to end of URL
        driver.get(DriverUtils.set_url(url + "/admin/inventory/?tab=inventory__hosts"))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        # Get URL of compute passed to function
        # Get link from partial text in table (Host Name column)
        links = driver.find_elements_by_partial_link_text('')
        for link in links:
            host_local = link.get_attribute("text")
            # Match host_to_lock with link
            if(host_name in host_local):
                host_link = link.get_attribute("href")
        # Append to end of URL
        driver.get(DriverUtils.set_url(host_link + constants.HOST_MEMORY_TAB))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        create_button = driver.find_element_by_id("memorys__action_createMemoryProfile")
        create_button.click()

        mem_profile_name_input = driver.find_element_by_id("id_hostname")
        mem_profile_name_input.click()
        mem_profile_name_input.send_keys(mem_profile_name)
        mem_profile_name_input.submit()

        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)









