from selenium.webdriver import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from common_utils import DriverUtils
import constants
import settings
import time

__author__ = 'jbarber'


class ModifyQuotas():

    @classmethod
    def quotas(cls, user_name, meta_data, vcpus, instances, injected_files, injected_file_content, volumes, volume_snapshots,\
               size_of_volume_snapshots, ram, security_groups, security_groups_rules, floating_ips, networks,\
               ports, routers, subnets):
        print "Modify Quotas (Identity -> Projects)--------------------------------------------------------------------"
        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        # Append to end of URL
        driver.get(DriverUtils.set_url(url + "/identity/"))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        # Call Functions below
        project_id = cls.get_project_id(user_name)
        if(project_id == -1):
            print "Error finding project name"
            return
        cls.modify_quotas(project_id, meta_data, vcpus, instances, injected_files, injected_file_content, volumes, volume_snapshots,\
               size_of_volume_snapshots, ram, security_groups, security_groups_rules, floating_ips, networks,\
               ports, routers, subnets)
        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)

    @classmethod
    def get_project_id(cls, user_name):
        project_id = -1
        index = [4]
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
            if(user_name in host_local):
                parse = link.get_attribute("href")
                # Parse number from link
                parse = parse.split("/")
                print parse
                # Find the project ID in the list
                # TODO: Currently a WORKAROUND (Maybe?)
                # Find 4th item in list
                project_id_list = [parse[x] for x in index]
                for item in project_id_list:
                    project_id = item
        return project_id



    @classmethod
    def modify_quotas(cls, project_id, meta_data, vcpus, instances, injected_files, injected_file_content, volumes, volume_snapshots,\
               size_of_volume_snapshots, ram, security_groups, security_groups_rules, floating_ips, networks,\
               ports, routers, subnets):
        # TODO: Grab driver, read table, compare to user_name, navigate to modify quotas section!
        # Read table, match name with project ID, use constants like in 'lock_host.py'
        # tuple of Name and Project ID
        # Get driver
        driver = DriverUtils.get_driver()

        # Check ALL params if == None
        # Else TODO: find element and edit with value from param
        if(project_id == None):
            print "No username was given, failed modifying quotas"
            return
        else:
            # Navigate to correct location
            project_dropdown_element = constants.MOD_QUOTA_DROPDOWN_FIRST_HALF + str(project_id) + constants.MOD_QUOTA_DROPDOWN_SECOND_HALF
            drop_down_project = driver.find_element_by_css_selector(project_dropdown_element)
            drop_down_project.click()
            project_modify_element = constants.MOD_QUOTA_MODIFY_FIRST_HALF + str(project_id) + constants.MOD_QUOTA_MODIFY_SECOND_HALF
            project_modify_quotas = driver.find_element_by_id(project_modify_element)
            project_modify_quotas.click()
            # Grab any element on page to submit form
            submit_form = driver.find_element_by_id("id_network")

            if(meta_data == None):
                print "Meta=None"
            else:
                meta_data_input = driver.find_element_by_id("id_metadata_items")
                meta_data_input.click()
                meta_data_input.send_keys(Keys.BACKSPACE)
                meta_data_input.send_keys(Keys.BACKSPACE)
                meta_data_input.send_keys(Keys.BACKSPACE)
                meta_data_input.send_keys(Keys.BACKSPACE)
                meta_data_input.send_keys(meta_data)
            if(vcpus == None):
                print "vcpus=None"
            else:
                vcpus_input = driver.find_element_by_id("id_cores")
                vcpus_input.click()
                vcpus_input.send_keys(Keys.BACKSPACE)
                vcpus_input.send_keys(Keys.BACKSPACE)
                vcpus_input.send_keys(vcpus)
            if(instances == None):
                print "instances=None"
            else:
                instances_input = driver.find_element_by_id("id_instances")
                instances_input.click()
                instances_input.send_keys(Keys.BACKSPACE)
                instances_input.send_keys(Keys.BACKSPACE)
                instances_input.send_keys(instances)
            if(injected_files == None):
                print "injected_files=None"
            else:
                injected_files_input = driver.find_element_by_id("id_injected_files")
                injected_files_input.click()
                injected_files_input.send_keys(Keys.BACKSPACE)
                injected_files_input.send_keys(Keys.BACKSPACE)
                injected_files_input.send_keys(injected_files)
            if(injected_file_content == None):
                print "injected_file_content=None"
            else:
                injected_file_content_input = driver.find_element_by_id("id_injected_file_content_bytes")
                injected_file_content_input.click()
                injected_file_content_input.send_keys(Keys.BACKSPACE)
                injected_file_content_input.send_keys(Keys.BACKSPACE)
                injected_file_content_input.send_keys(Keys.BACKSPACE)
                injected_file_content_input.send_keys(Keys.BACKSPACE)
                injected_file_content_input.send_keys(Keys.BACKSPACE)
                injected_file_content_input.send_keys(injected_file_content)
            if(volumes == None):
                print "volumes=None"
            else:
                volumes_input = driver.find_element_by_id("id_volumes")
                volumes_input.click()
                volumes_input.send_keys(Keys.BACKSPACE)
                volumes_input.send_keys(Keys.BACKSPACE)
                volumes_input.send_keys(volumes)
            if(volume_snapshots == None):
                print "volume snapshots=None"
            else:
                volume_snapshots_input = driver.find_element_by_id("id_snapshots")
                volume_snapshots_input.click()
                volume_snapshots_input.send_keys(Keys.BACKSPACE)
                volume_snapshots_input.send_keys(Keys.BACKSPACE)
                volume_snapshots_input.send_keys(volume_snapshots)
            if(size_of_volume_snapshots == None):
                print "size of volume snapshots=None"
            else:
                size_of_volume_snapshots_input = driver.find_element_by_id("id_gigabytes")
                size_of_volume_snapshots_input.click()
                size_of_volume_snapshots_input.send_keys(Keys.BACKSPACE)
                size_of_volume_snapshots_input.send_keys(Keys.BACKSPACE)
                size_of_volume_snapshots_input.send_keys(size_of_volume_snapshots)
            if(ram == None):
                print "ram=None"
            else:
                ram_input = driver.find_element_by_id("id_ram")
                ram_input.click()
                ram_input.send_keys(Keys.BACKSPACE)
                ram_input.send_keys(Keys.BACKSPACE)
                ram_input.send_keys(Keys.BACKSPACE)
                ram_input.send_keys(Keys.BACKSPACE)
                ram_input.send_keys(Keys.BACKSPACE)
                ram_input.send_keys(ram)
            if(security_groups == None):
                print "security groups=None"
            else:
                security_groups_input = driver.find_element_by_id("id_security_group")
                security_groups_input.click()
                security_groups_input.send_keys(Keys.BACKSPACE)
                security_groups_input.send_keys(Keys.BACKSPACE)
                security_groups_input.send_keys(security_groups)
            if(security_groups_rules == None):
                print "security groups rules=None"
            else:
                security_groups_rules_input = driver.find_element_by_id("id_security_group_rule")
                security_groups_rules_input.click()
                security_groups_rules_input.send_keys(Keys.BACKSPACE)
                security_groups_rules_input.send_keys(Keys.BACKSPACE)
                security_groups_rules_input.send_keys(Keys.BACKSPACE)
                security_groups_rules_input.send_keys(security_groups_rules)
            if(floating_ips == None):
                print "floating ips=None"
            else:
                floating_ips_input = driver.find_element_by_id("id_floatingip")
                floating_ips_input.click()
                floating_ips_input.send_keys(Keys.BACKSPACE)
                floating_ips_input.send_keys(Keys.BACKSPACE)
                floating_ips_input.send_keys(floating_ips)
            if(networks == None):
                print "networks=None"
            else:
                network_input = driver.find_element_by_id("id_network")
                network_input.click()
                network_input.send_keys(Keys.BACKSPACE)
                network_input.send_keys(Keys.BACKSPACE)
                network_input.send_keys(networks)
            if(ports == None):
                print "ports=None"
            else:
                ports_input = driver.find_element_by_id("id_port")
                ports_input.click()
                ports_input.send_keys(Keys.BACKSPACE)
                ports_input.send_keys(Keys.BACKSPACE)
                ports_input.send_keys(ports)
            if(routers == None):
                print "routers=None"
            else:
                routers_input = driver.find_element_by_id("id_router")
                routers_input.click()
                routers_input.send_keys(Keys.BACKSPACE)
                routers_input.send_keys(Keys.BACKSPACE)
                routers_input.send_keys(routers)
            if(subnets == None):
                print "subnets=None"
            else:
                subnets_input = driver.find_element_by_id("id_subnet")
                subnets_input.click()
                subnets_input.send_keys(Keys.BACKSPACE)
                subnets_input.send_keys(Keys.BACKSPACE)
                subnets_input.send_keys(subnets)

            submit_form.submit()



