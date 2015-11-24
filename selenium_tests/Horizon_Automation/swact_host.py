from common_utils import DriverUtils
import settings
import constants
import time

__author__ = 'amcfarla'


class SwactHost():

    @classmethod
    def swact_host(cls, host_name):

        print "Swact Host Information------------------------------------------"
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
        # Call function to get list of all hosts
        cls.get_hosts(host_name)
        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)

    @classmethod
    def get_hosts(cls, host_to_lock):
        #print host_to_lock
        host_list = []
        row_number = -1
        driver = DriverUtils.get_driver()

        # Get link from partial text in table (Host Name column)
        links = driver.find_elements_by_partial_link_text('')
        for link in links:
            host_local = link.get_attribute("text")
            # Match host_to_lock with link
            if(host_to_lock in host_local):
                print host_local
                parse = link.get_attribute("href")
                # Parse number from link
                parse = parse.split("/")
                print parse
                # Find the number in the list
                for num in parse:
                    if num.isdigit():
                        row_number = num
                temp_tuple = [host_local, row_number]
                host_list.append(temp_tuple)
        for item in host_list:
            host = item[0]
            row = item[1]
            if(host_to_lock == host):
                print "Found Host"
                # Call function with row number
                cls.set_host_action(row)
            else:
                print "Wrong Host"

    @classmethod
    def set_host_action(cls, row_number):

        DROP_DOWN_LABEL_FIRST_HALF = constants.CONST_SWACT_LABEL_FIRST_HALF
        DROP_DOWN_LABEL_SECOND_HALF = constants.CONST_SWACT_LABEL_SECOND_HALF

        driver = DriverUtils.get_driver()

        # check that the host can be swacted
        check_return_value = cls.check_host_is_active(row_number)
        if(check_return_value == 1):
            pass
        elif(check_return_value == 2):
            return

        # swact host
        #host_drop_down_id = constants.CONST_DROPDOWN_FIRST_HALF + str(row_number) + constants.CONST_DROPDOWN_SECOND_HALF
        #drop_down_host = driver.find_element_by_css_selector(host_drop_down_id)
        #drop_down_host.click()

        #swact_host_id = DROP_DOWN_LABEL_FIRST_HALF + str(row_number) + DROP_DOWN_LABEL_SECOND_HALF
        #drop_down_swact = driver.find_element_by_css_selector(swact_host_id)
        #drop_down_swact.click()

        # Confirm swact host
        #confirm_swact = driver.find_element_by_css_selector(".btn-submit")
        #confirm_swact.click()

        check_return_value = cls.check_swact_in_progress(row_number)
        if(check_return_value == 1):
            pass
        elif(check_return_value == 2):
            print "Swact Failed"
            return

    @classmethod
    def check_host_is_active(cls, row_number):
        return_value = -1
        driver = DriverUtils.get_driver()
        host_label = constants.CONST_CHECK_PERSONALITY_FIRST_HALF + str(row_number) + constants.CONST_CHECK_PERSONALITY_SECOND_HALF
        check = driver.find_element_by_css_selector(host_label)
        if("Active" in check.text):
            print "Host Status: Host is active"
            return_value = 1
        elif("Standby" in check.text):
            print "Host Status: Host is standby - SWACT not allowed"
            return_value = 2
        else:
            print "An error has occurred"
            return_value = 3
        return return_value

    @classmethod
    def check_swact_in_progress(cls, row_number):
        return_value = -1
        driver = DriverUtils.get_driver()
        host_label = constants.HOST_CHECK_STATUS_FIRST_HALF + str(row_number) + constants.HOST_CHECK_STATUS_SECOND_HALF
        check = driver.find_element_by_css_selector(host_label)
        if("Swact" in check.text):
            print "SWACT is successful"
            return_value = 1
        else:
            print "An error has occurred"
            return_value = 2
        return return_value

