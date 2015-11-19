from selenium.webdriver import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from common_utils import DriverUtils
import constants
from common_utils import InputFields
import settings
import time

__author__ = 'jbarber'


class ModifyQuotas():

    @classmethod
    def quotas(cls, project_name, quota_dict):
        """
        Function for initializing modify quotas class

        :param project_name: name of project in Horizon
        :param quota_dict: dictionary of all quotas to modify [example (input_id_name: value)]
        """

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
        project_id = cls.get_project_id(project_name)
        if(project_id == -1):
            print "Error finding project name"
            return
        cls.modify_quotas(project_id, quota_dict)
        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)
        time.sleep(settings.DEFAULT_SLEEP_TIME)

    @classmethod
    def get_project_id(cls, project_name):
        """
        Function for getting project id

        :param project_name: name of project in Horizon
        :return project_id: id of project taken from project_name link
        """

        project_id = -1
        index = [4]
        # Get driver
        driver = DriverUtils.get_driver()
        # Get link from partial text in table (Host Name column)
        links = driver.find_elements_by_partial_link_text('')
        for link in links:
            host_local = link.get_attribute("text")
            # Match host_to_lock with link
            if(project_name in host_local):
                parse = link.get_attribute("href")
                # Parse number from link
                parse = parse.split("/")
                # Find the project ID in the list
                # Find 4th item in list
                project_id_list = [parse[x] for x in index]
                for item in project_id_list:
                    project_id = item
        return project_id

    @classmethod
    def modify_quotas(cls, project_id, quota_dict):
        """
        Function for getting project id

        :param project_id: id of project in Horizon
        :param quota_dict: dictionary of all quotas to modify [example (input_id_name: value)]
        """

        if(project_id == None):
            print "No username was given, failed modifying quotas"
            return
        else:
            print "Modify Quotas (Identity -> Projects)--------------------------------------------------------------------"
            print project_id
            project_dropdown_element = constants.MOD_QUOTA_DROPDOWN_FIRST_HALF + str(project_id) + constants.MOD_QUOTA_DROPDOWN_SECOND_HALF
            project_modify_element = constants.MOD_QUOTA_MODIFY_FIRST_HALF + str(project_id) + constants.MOD_QUOTA_MODIFY_SECOND_HALF
            InputFields.button_input(project_dropdown_element, 'css')
            InputFields.button_input(project_modify_element, 'id')
            for key, value in quota_dict.items():
                if quota_dict[key]:
                    name = value[0]
                    input_type = value[1]
                    if(input_type == 'text'):
                        InputFields.text_input(key, name)
                    if(input_type == 'checkbox'):
                        InputFields.checkbox_input(key, name)
                    if(input_type == 'select'):
                        InputFields.select_input(key, name)

            InputFields.submit(key)



