from selenium.webdriver import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from common_utils import DriverUtils
import constants
import settings
import time

__author__ = 'jbarber'

class Flavors():

    @classmethod
    def flavors(cls, flavor_name, vcpus, ram, root_disk, ephemeral_disk, swap_disk):
        print "Create Flavors (Admin -> System -> Flavors)-------------------------------------------------------------"
        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        # Append to end of URL
        driver.get(DriverUtils.set_url(url + "/admin/flavors/"))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        # Call Functions below
        cls.create_flavor(flavor_name, vcpus, ram, root_disk, ephemeral_disk, swap_disk)
        time.sleep(5)
        flavor_full_link = cls.get_flavor_link(flavor_name)
        if(flavor_full_link == -1):
            print "Error finding flavor name"
            return
        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)
        return flavor_full_link

    @classmethod
    def create_flavor(cls, flavor_name, vcpus, ram, root_disk, ephemeral_disk, swap_disk):
        driver = DriverUtils.get_driver()

        create_button = driver.find_element_by_id("flavors__action_create")
        create_button.click()

        flavor_name_input = driver.find_element_by_id("id_name")
        flavor_name_input.click()
        flavor_name_input.send_keys(flavor_name)

        vcpus_input = driver.find_element_by_id("id_vcpus")
        vcpus_input.click()
        vcpus_input.send_keys(vcpus)

        ram_input = driver.find_element_by_id("id_memory_mb")
        ram_input.click()
        ram_input.send_keys(ram)

        root_disk_input = driver.find_element_by_id("id_disk_gb")
        root_disk_input.click()
        root_disk_input.send_keys(root_disk)

        ephemeral_disk_input = driver.find_element_by_id("id_eph_gb")
        ephemeral_disk_input.click()
        ephemeral_disk_input.send_keys(ephemeral_disk)

        swap_disk_input = driver.find_element_by_id("id_swap_mb")
        swap_disk_input.click()
        swap_disk_input.send_keys(swap_disk)

        swap_disk_input.submit()

    @classmethod
    def get_flavor_link(cls, flavor_name):
        flavor_id_link = -1
        index = [6]
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
            if(flavor_name in host_local):
                flavor_id_link = link.get_attribute("href")
        # Append to end of URL
        driver.get(DriverUtils.set_url(flavor_id_link + constants.FLAVOR_EXTRA_SPEC_TAB))
        print flavor_id_link
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        return flavor_id_link

    @classmethod
    def create_extra_spec(cls, flavor_full_link, first_input, second_input):
        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        # Append to end of URL
        driver.get(DriverUtils.set_url(flavor_full_link + constants.FLAVOR_EXTRA_SPEC_TAB))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        create_button = driver.find_element_by_id("extras__action_create")
        create_button.click()

        # Select extra spec
        extra_spec_first_input = Select(driver.find_element_by_id("id_type"))
        print first_input
        print second_input
        if(first_input in constants.FLAVOR_EXTRA_SPEC_TYPE_CPU_POLICY):
            extra_spec_first_input.select_by_visible_text(constants.FLAVOR_EXTRA_SPEC_TYPE_CPU_POLICY)
            if(second_input in constants.FLAVOR_EXTRA_SPEC_TYPE_CPU_POLICY_DEDICATED):
                extra_spec_second_input = Select(driver.find_element_by_id("id_cpu_policy"))
                extra_spec_second_input.select_by_visible_text(constants.FLAVOR_EXTRA_SPEC_TYPE_CPU_POLICY_DEDICATED)
        if(first_input in constants.FLAVOR_EXTRA_SPEC_TYPE_MEMORY_PAGE_SIZE):
            extra_spec_first_input.select_by_visible_text(constants.FLAVOR_EXTRA_SPEC_TYPE_MEMORY_PAGE_SIZE)
            if(second_input in constants.FLAVOR_EXTRA_SPEC_TYPE_MEMORY_PAGE_SIZE_2048):
                extra_spec_second_input = Select(driver.find_element_by_id("id_mem_page_size"))
                extra_spec_second_input.select_by_visible_text(constants.FLAVOR_EXTRA_SPEC_TYPE_MEMORY_PAGE_SIZE_2048)
        if(first_input in constants.FLAVOR_EXTRA_SPEC_TYPE_VCPU_MODEL):
            extra_spec_first_input.select_by_visible_text(constants.FLAVOR_EXTRA_SPEC_TYPE_VCPU_MODEL)
            if(second_input in constants.FLAVOR_EXTRA_SPEC_TYPE_VCPU_MODEL_INTEL_9XX):
                extra_spec_second_input = Select(driver.find_element_by_id("id_cpu_model"))
                extra_spec_second_input.select_by_visible_text(constants.FLAVOR_EXTRA_SPEC_TYPE_VCPU_MODEL_INTEL_9XX)
        submit_form = driver.find_element_by_id("id_type")
        submit_form.submit()
        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)






