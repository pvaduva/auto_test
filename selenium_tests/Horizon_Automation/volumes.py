'''
volumes.py - Handles the creation of volumes for tenants

Copyright (c) 2015 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.


Contains function: create volume
'''

'''
modification history:
---------------------
26nov15,jbb  Initial file
'''

from selenium.webdriver.support.ui import Select
from common_utils import DriverUtils
import settings
import time


class Volumes():

    @classmethod
    def volumes(cls, volume_name, volume_source, image_source, availability_zone):
        """
        Function for initializing volumes class

        :param volume_name: name of volume
        :param volume_source: source of volume [image]
        :param image_source: image name
        :param availability_zone: [any or nova]
        """

        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        # Append to end of URL
        driver.get(DriverUtils.set_url(url + "/project/volumes/?tab=volumes_and_snapshots__volumes_tab"))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        # Call Functions below
        cls.create_volume(volume_name, volume_source, image_source, availability_zone)
        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)
        time.sleep(settings.DEFAULT_SLEEP_TIME)

    @classmethod
    def create_volume(cls, volume_name, volume_source, image_source, availability_zone):
        """
        Function for creating a volume

        :param volume_name: name of volume
        :param volume_source: source of volume [image]
        :param image_source: image name
        :param availability_zone: [any or nova]
        """

        print "Create Volumes (Project -> Compute -> Volumes)----------------------------------------------------------"
        print volume_name
        # Get driver
        driver = DriverUtils.get_driver()

        create_button = driver.find_element_by_id("volumes__action_create")
        create_button.click()

        volume_name_input = driver.find_element_by_id("id_name")
        volume_name_input.send_keys(volume_name)

        volume_source_input = Select(driver.find_element_by_id("id_volume_source_type"))
        volume_source_input.select_by_visible_text(volume_source)

        image_source_input = Select(driver.find_element_by_id("id_image_source"))
        image_source_input.select_by_index(1)
        for option in image_source_input.options:
            value = option.get_attribute('value')
            if(image_source == value):
                image_source_input.select_by_value(value)
                break

        availability_zone_input = Select(driver.find_element_by_id("id_availability_zone"))
        availability_zone_input.select_by_visible_text(availability_zone)

        volume_name_input.submit()






