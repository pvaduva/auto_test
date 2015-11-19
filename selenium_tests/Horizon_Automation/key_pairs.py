from common_utils import DriverUtils
from selenium import webdriver
import settings
import time

__author__ = 'jbarber'


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
        cls.create_key_pair(key_pair_name)
        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)
        time.sleep(settings.DEFAULT_SLEEP_TIME)

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
