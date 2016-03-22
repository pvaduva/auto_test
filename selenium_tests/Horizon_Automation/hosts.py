'''
hosts.py - Handles all host functions

Copyright (c) 2015 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.


Contains functions: check host, create interface,
create profile (cpu, iface, mem), unlock, and lock.
'''

'''
modification history:
---------------------
26nov15,jbb  Initial file
30nov15,jbb  Add fail messages
8dec15,jbb   Add method create cinder device
8dec15,jbb   Add method add local storage
'''

from common_utils import DriverUtils
from selenium.webdriver.common.keys import Keys
import constants
import settings
import time


class Hosts():

    @classmethod
    def hosts(cls):
        """
        Function for initializing hosts class

        :return host_list: list of hosts in host table
        """

        print "Check Hosts (Admin -> System -> Inventory)--------------------------------------------------------------"
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
        time.sleep(settings.DEFAULT_SLEEP_TIME)
        return host_list

    @classmethod
    def get_hosts(cls):
        """
        Function for getting all hosts in table

        :return host_list: list of hosts in host table
        """

        host_list = []
        row_number = -1
        driver = DriverUtils.get_driver()
        # Get link from partial text in host table (Host Name column)
        links = driver.find_elements_by_partial_link_text('')
        for link in links:
            host_local = link.get_attribute("text")
            # Match host_local link name with compute
            if("compute" in host_local):
                parse = link.get_attribute("href")
                # Parse number from link
                parse = parse.split("/")
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
            return_value = cls.check_host_avail_state(row)
            if(return_value == 0):
                print "Host is online"
            if(return_value == 1):
                print "Host is in an invalid state"
                # Attempt to lock host
                LockHost.set_host_lock(row)
        return host_list

    @classmethod
    def check_host(cls, row_number):
        return_value = -1
        driver = DriverUtils.get_driver()
        host_label = constants.CONST_CHECK_ADMIN_STATE_FIRST_HALF + str(row_number) + constants.CONST_CHECK_ADMIN_STATE_SECOND_HALF
        check = driver.find_element_by_css_selector(host_label)
        if("Locked" in check.text):
            print "Host Status: Host is locked"
            return_value = 1
        elif("Unlocked" in check.text):
            print "Host Status: Host is unlocked"
            return_value = 2
        else:
            print "Test: FAIL - Check Host failed"
            return_value = 3
        return return_value

    @classmethod
    def check_host_avail_state(cls, row_number):
        """
        Function for checking column 'Available State' in host table

        :param row_number: row number of host [Row number is assigned by creation order not order in table]
        :return return_value: return value for valid or invalid host status [0 valid, 1 invalid]
        """

        return_value = -1
        driver = DriverUtils.get_driver()
        host_label = constants.HOST_CHECK_AVAIL_STATE_FIST_HALF + str(row_number) + \
                     constants.HOST_CHECK_AVAIL_STATE_SECOND_HALF
        check = driver.find_element_by_css_selector(host_label)
        if("Online" in check.text):
            print "Host Status: Host is locked"
            return_value = 0
        else:
            return 1
        return return_value

    @classmethod
    def modify_interface(cls, host_name, iface_name, network_type, port, mtu, provider_networks):
        """
        Function for creating an interface for specified host

        :param host_name: name of host in Hosts table
        :param iface_name: name of interface
        :param network_type: type of network [mgmt, oam, data, infra, pxeboot]
        :param iface_type: type of interface [aggregated or vlan]
        :param eth_mode: aggregated ethernet mode
        :param ports: network adapter?
        :param mtu: maximum transmit unit
        :param provider_networks: list of provider networks
        """

        print "Modify Interface (Admin -> System -> Inventory)---------------------------------------------------------"
        host_link = ""
        row_number = -1
        numbers = []
        print host_name
        print iface_name
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
        # Get link from partial text in table (Host Name column)
        links = driver.find_elements_by_partial_link_text('')
        for link in links:
            host_local = link.get_attribute("text")
            # Match host_name with link
            if(host_name in host_local):
                host_link = link.get_attribute("href")
        # Append to end of URL
        DriverUtils.set_url(host_link + constants.HOST_INTERFACE_TAB)
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        # Get link from partial text in host table (Host Name column)
        links = driver.find_elements_by_partial_link_text('')
        for link in links:
            host_interface = link.get_attribute("text")
            # Match host_local link name with compute
            if(port in host_interface):
                parse = link.get_attribute("href")
                # Parse number from link
                parse = parse.split("/")
                # Get row number in table
                row_number = parse[7]
            # TODO - Possible Enhancement: Add proper check for existing interfaces
            # Note: This a workaround because lab_cleanup.sh does not remove interface from con-1
            # Interface check for con-1 is currently hard-coded as 'oam0'
            if(host_interface == "oam0"):
                # Reset URL to home page in Horizon
                DriverUtils.set_url(settings.DEFAULT_URL)
                time.sleep(settings.DEFAULT_SLEEP_TIME)
                return
            else:
                continue



        # Get Edit Interface button
        edit_interface_button = constants.HOST_INTERFACE_EDIT_FIRST_HALF + str(row_number) + constants.HOST_INTERFACE_EDIT_SECOND_HALF
        edit_button = driver.find_element_by_id(edit_interface_button)
        edit_button.click()

        iface_name_input = driver.find_element_by_id("id_ifname")
        iface_name_input.send_keys(Keys.DELETE)
        iface_name_input.send_keys(Keys.DELETE)
        iface_name_input.send_keys(Keys.DELETE)
        iface_name_input.send_keys(Keys.DELETE)
        iface_name_input.send_keys(Keys.DELETE)
        iface_name_input.send_keys(iface_name)

        print network_type
        if(network_type == "data"):
            network_type_input = driver.find_element_by_id("id_networktype_5")
            network_type_input.click()
        if(network_type == "oam"):
            network_type_input = driver.find_element_by_id("id_networktype_2")
            network_type_input.click()

        time.sleep(2)

        # Provider Networks
        if(not provider_networks):
            pass
        else:
            if("group0-data0" in provider_networks):
                provider_networks_input1 = driver.find_element_by_id("id_providernetworks_data_1")
                provider_networks_input1.click()
            if("group0-data0b" in provider_networks):
                provider_networks_input2 = driver.find_element_by_id("id_providernetworks_data_2")
                provider_networks_input2.click()
            if("group0-ext0" in provider_networks):
                provider_networks_input3 = driver.find_element_by_id("id_providernetworks_data_0")
                provider_networks_input3.click()
            if("group0-data1" in provider_networks):
                provider_networks_input4 = driver.find_element_by_id("id_providernetworks_data_3")
                provider_networks_input4.click()


        mtu_input = driver.find_element_by_id("id_imtu")
        mtu_input.send_keys(Keys.BACKSPACE)
        mtu_input.send_keys(Keys.BACKSPACE)
        mtu_input.send_keys(Keys.BACKSPACE)
        mtu_input.send_keys(Keys.BACKSPACE)
        mtu_input.send_keys(Keys.BACKSPACE)
        mtu_input.send_keys(mtu)
        time.sleep(2)
        # Submit interface form
        mtu_input.submit()

        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)
        time.sleep(settings.DEFAULT_SLEEP_TIME)

    @classmethod
    def check_profile_exists(cls, profile_name, url_tab):
        """
        Function to check if profile exists
        :param profile_name: name of profile to check

        :return return_value
        """

        return_value = -1
        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        # Append to end of URL
        driver.get(DriverUtils.set_url(url + "/admin/inventory/" + url_tab))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        # Check if profile already exists
        words_on_page = driver.find_element_by_xpath("//*[contains(text()," + profile_name + ")]")
        if(profile_name in words_on_page.text):
            return 1
        else:
            return_value = 0
        return return_value

    @classmethod
    def create_interface_profile(cls, host_name, if_profile_name):
        """
        Function for creating an interface profile for specified host

        :param host_name: name of host in Hosts table
        :param if_profile_name: name of interface profile for specified host
        """

        # Check if profile already exists
        return_value = cls.check_profile_exists(if_profile_name, "?tab=inventory__interfaceprofiles")
        if(return_value == 1):
            # Reset URL to home page in Horizon
            DriverUtils.set_url(settings.DEFAULT_URL)
            time.sleep(settings.DEFAULT_SLEEP_TIME)
            return
        else:
            pass
        print "Create Interface Profile (Admin -> System -> Inventory)-------------------------------------------------"
        host_link = ""
        print host_name
        print if_profile_name
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
        if_profile_name_input.send_keys(if_profile_name)
        if_profile_name_input.submit()

        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)
        time.sleep(settings.DEFAULT_SLEEP_TIME)

    @classmethod
    def create_cpu_profile(cls, host_name, cpu_profile_name):
        """
        Function for creating a cpu profile for specified host

        :param host_name: name of host in Hosts table
        :param cpu_profile_name: name of cpu profile for specified host
        """

        # Check if profile already exists
        return_value = cls.check_profile_exists(cpu_profile_name, "?tab=inventory__cpuprofiles")
        if(return_value == 1):
            # Reset URL to home page in Horizon
            DriverUtils.set_url(settings.DEFAULT_URL)
            time.sleep(settings.DEFAULT_SLEEP_TIME)
            return
        else:
            pass
        print "Create Interface (Admin -> System -> Inventory)---------------------------------------------------------"
        host_link = ""
        print host_name
        print cpu_profile_name
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
        cpu_profile_name_input.send_keys(cpu_profile_name)
        cpu_profile_name_input.submit()

        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)
        time.sleep(settings.DEFAULT_SLEEP_TIME)

    @classmethod
    def create_mem_profile(cls, host_name, mem_profile_name):
        """
        Function for creating a memory profile for specified host

        :param host_name: name of host in Hosts table
        :param mem_profile_name: name of memory profile for specified host
        """

        # Check if profile already exists
        return_value = cls.check_profile_exists(mem_profile_name, "?tab=inventory__memoryprofiles")
        if(return_value == 1):
            # Reset URL to home page in Horizon
            DriverUtils.set_url(settings.DEFAULT_URL)
            time.sleep(settings.DEFAULT_SLEEP_TIME)
            return
        else:
            pass
        print "Create Memory Profile (Admin -> System -> Inventory)----------------------------------------------------"
        host_link = ""
        print host_name
        print mem_profile_name
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
        mem_profile_name_input.send_keys(mem_profile_name)
        mem_profile_name_input.submit()

        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)
        time.sleep(settings.DEFAULT_SLEEP_TIME)

    @classmethod
    def create_cinder_device(cls, host_name):
        """
        Function for creating a cinder device on a host

        :param host_name: name of host in Hosts table
        """

        print "Create Cinder Device (Admin -> System -> Inventory)-----------------------------------------------------"
        print host_name
        host_link = ""
        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        # Append to end of URL
        DriverUtils.set_url(url + "/admin/inventory/?tab=inventory__hosts")
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        # Get URL of compute passed to function
        time.sleep(settings.DEFAULT_SLEEP_TIME)
        # Get link from partial text in table (Host Name column)
        links = driver.find_elements_by_partial_link_text('')
        for link in links:
            host_local = link.get_attribute("text")
            # Match host_to_lock with link
            if(host_name in host_local):
                host_link = link.get_attribute("href")
        # If controller-1 does not exist skip
        if(host_link == ""):
            DriverUtils.set_url(settings.DEFAULT_URL)
            time.sleep(settings.DEFAULT_SLEEP_TIME)
            return
        # Append to end of URL
        driver.get(DriverUtils.set_url(host_link + constants.HOST_STORAGE_TAB))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)

        words_on_page = driver.find_element_by_xpath("//*[contains(text(),/dev/sdb)]")
        if("/dev/sdb" in words_on_page.text):
            # Reset URL to home page in Horizon
            DriverUtils.set_url(settings.DEFAULT_URL)
            time.sleep(settings.DEFAULT_SLEEP_TIME)
            return
        else:
            pass

        # TODO: Find create button
        create_button = driver.find_element_by_id()
        create_button.click()
        # TODO: Find element and submit form
        submit_element = driver.find_element_by_id()
        submit_element.submit()

        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)
        time.sleep(settings.DEFAULT_SLEEP_TIME)

    @classmethod
    def add_local_storage(cls, host_name, lvm_size):
        """
        Function for creating local storage on a host

        :param host_name: name of host in Hosts table
        :param lvm_size: local volume size
        """

        print "Add Local Storage (Admin -> System -> Inventory)--------------------------------------------------------"
        print host_name
        print lvm_size
        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        # Append to end of URL
        DriverUtils.set_url(url + "/admin/inventory/?tab=inventory__hosts")
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        # Get URL of compute passed to function
        # Get link from partial text in table (Host Name column)
        links = driver.find_elements_by_partial_link_text('')
        for link in links:
            host_local = link.get_attribute("text")
            # Match host_name with link
            if(host_name in host_local):
                host_link = link.get_attribute("href")
        # Append to end of URL
        DriverUtils.set_url(host_link + constants.HOST_STORAGE_TAB)
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        # Save current URL
        save_url = DriverUtils.get_url()
        # Find create button
        create_button = driver.find_element_by_id("localvolumegroups__action_addlocalvolumegroup")
        create_button.click()
        # Find element and submit form
        submit_element = driver.find_element_by_id("id_lvm_vg_name")
        submit_element.submit()

        time.sleep(settings.DEFAULT_SLEEP_TIME)

        DriverUtils.set_url(save_url)
        driver.get(DriverUtils.get_url())

        # Find create button
        add_pv_button = driver.find_element_by_id("physicalvolumes__action_addphysicalvolume")
        add_pv_button.click()
        # Find element and submit form
        submit_element_pv = driver.find_element_by_id("id_disks")
        submit_element_pv.submit()

        time.sleep(settings.DEFAULT_SLEEP_TIME)

        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        # Get URL of compute passed to function
        # Get link from partial text in table (Host Name column)
        links = driver.find_elements_by_partial_link_text('')
        for link in links:
            host_local = link.get_attribute("text")
            # Match nova-local with link
            if("nova-local" in host_local):
                host_link = link.get_attribute("href")
        # Append to end of URL
        driver.get(DriverUtils.set_url(host_link + constants.HOST_STORAGE_LOCAL_VOLUME_GROUP_PARAM_TAB))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)

        # TODO: Find edit size button
        edit_button = driver.find_element_by_id("params__row_instances_lv_size_mib__action_edit")
        edit_button.click()
        # TODO: Find size input
        lvm_size_input = driver.find_element_by_id("id_instances_lv_size_mib")
        lvm_size_input.send_keys(Keys.BACKSPACE)
        lvm_size_input.send_keys(Keys.BACKSPACE)
        lvm_size_input.send_keys(lvm_size)
        # TODO: Submit form
        lvm_size_input.submit()

        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)
        time.sleep(settings.DEFAULT_SLEEP_TIME)




class LockHost():

    @classmethod
    def set_host_lock(cls, row_number):
        """
        Function for setting host to locked state

        :param row_number: row number in the hosts table
        """

        driver = DriverUtils.get_driver()

        check_return_value = Hosts.check_host(row_number)
        if(check_return_value == 1):
            print "Host lock failed, host was already locked"
            return
        elif(check_return_value == 2):
            print "Host is attempting to lock"
            pass
        elif(check_return_value == 3):
            return

        host_drop_down_id = constants.CONST_DROPDOWN_FIRST_HALF + str(row_number) + constants.CONST_DROPDOWN_SECOND_HALF
        drop_down_host = driver.find_element_by_css_selector(host_drop_down_id)
        drop_down_host.click()
        lock_host_id = constants.CONST_LOCK_LABEL_FIRST_HALF + str(row_number) + constants.CONST_LOCK_LABEL_SECOND_HALF
        drop_down_lock = driver.find_element_by_css_selector(lock_host_id)
        drop_down_lock.click()
        # Confirm lock host
        confirm_lock = driver.find_element_by_css_selector(".btn-submit")
        confirm_lock.click()
        time.sleep(10)
        check_return_value = Hosts.check_host(row_number)
        if(check_return_value == 1):
            pass
        elif(check_return_value == 2):
            print "Lock Failed"
            return
        elif(check_return_value == 3):
            return


class UnlockHost():

    @classmethod
    def set_host_unlock(cls, row_number):
        """
        Function for setting host to unlocked state

        :param row_number: row number in the hosts table
        """

        driver = DriverUtils.get_driver()

        check_return_value = Hosts.check_host(row_number)
        if(check_return_value == 1):
            print "Host is attempting to unlock"
            pass
        elif(check_return_value == 2):
            print "Host unlock failed, host was already unlocked"
            return
        elif(check_return_value == 3):
            return

        host_drop_down_id = constants.CONST_DROPDOWN_FIRST_HALF + str(row_number) + constants.CONST_DROPDOWN_SECOND_HALF
        drop_down_host = driver.find_element_by_css_selector(host_drop_down_id)
        drop_down_host.click()
        unlock_host_id = constants.CONST_UNLOCK_LABEL_FIRST_HALF + str(row_number) + constants.CONST_UNLOCK_LABEL_SECOND_HALF
        drop_down_lock = driver.find_element_by_css_selector(unlock_host_id)
        drop_down_lock.click()
        time.sleep(10)
        check_return_value = Hosts.check_host(row_number)
        if(check_return_value == 1):
            print "Unlock Failed"
            return
        elif(check_return_value == 2):
            pass
        elif(check_return_value == 3):
            return









