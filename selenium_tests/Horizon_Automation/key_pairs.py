'''
key_pairs.py - Handles the creation of key pairs for tenants

Copyright (c) 2015 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.


Contains function: create key par
'''

'''
modification history:
---------------------
26nov15,jbb  Initial file
'''

from common_utils import DriverUtils
import settings
import time


class KeyPairs():

    @classmethod
    def key_pairs(cls, key_pair_name):
        """
        Function for initializing key pairs class

        :param key_pair_name: name of key pair
        """

        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        # Append to end of URL
        driver.get(DriverUtils.set_url(url + "/project/access_and_security/?tab=access_security_tabs__keypairs_tab"))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        # Call Functions below
        return_value = cls.check_key_pair(key_pair_name)
        if(return_value == 1):
            # Reset URL to home page in Horizon
            DriverUtils.set_url(settings.DEFAULT_URL)
            time.sleep(settings.DEFAULT_SLEEP_TIME)
            return
        else:
            pass
        cls.create_key_pair(key_pair_name)
        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)
        time.sleep(settings.DEFAULT_SLEEP_TIME)

    @classmethod
    def check_key_pair(cls, key_pair_name):
        """
        Function to key pair in list
        Note: This a workaround because lab_cleanup.sh does not remove key pairs from tenants
        :param key_pair_name: name of key pair

        :return return_value: 1 key pair found, 0 key pair not found
        """

        return_value = -1
        driver = DriverUtils.get_driver()
        # Get link from partial text in host table (Host Name column)
        links = driver.find_elements_by_partial_link_text('')
        for link in links:
            key_pair_local = link.get_attribute("text")
            # Match host_local link name with compute
            if(key_pair_name in key_pair_local):
                return 1
            else:
                return_value = 0
        return return_value

    @classmethod
    def create_key_pair(cls, key_pair_name):
        """
        Function for creating a key pair

        :param key_pair_name: name of key pair
        """

        print "Create Key-Pair (Project -> Compute -> Access & Security)-----------------------------------------------"
        print key_pair_name
        # Get driver
        driver = DriverUtils.get_driver()

        create_button = driver.find_element_by_id("keypairs__action_create")
        create_button.click()

        key_pair_input = driver.find_element_by_id("id_name")
        key_pair_input.send_keys(key_pair_name)
        key_pair_input.submit()

        time.sleep(settings.DEFAULT_SLEEP_TIME)
