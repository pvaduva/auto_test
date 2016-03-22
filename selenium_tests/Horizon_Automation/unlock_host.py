from common_utils import DriverUtils
import settings
import constants
import time

__author__ = 'jbarber'


class UnlockHost():

    @classmethod
    def unlock_host(cls, host_name):
        print "Unlock Host Information---------------------------------------------------------------------------------"
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
    def get_hosts(cls, host_to_unlock):
        host_list = []
        row_number = -1

        driver = DriverUtils.get_driver()
        # Get text from table (Host Name column)
        host_names = driver.find_element_by_xpath("//table[@id='hosts']")
        host_names = host_names.text # Raw text of entire object
        host_names = host_names.split('\n') # Split object into list
        #print host_names
        host_names = host_names[8:] # Remove first 8 items from list (titles)
        host_names = host_names[1::3] # Remove Alarm ID from list
        host_names = host_names[:-1] # Trim trailing information (Might break with more hosts)
        #print host_names
        # Get link from partial text in table (Host Name column)
        links = driver.find_elements_by_partial_link_text('')
        for link in links:
            host_local = link.get_attribute("text")
            # Match host_to_lock with link
            if(host_to_unlock in host_local):
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
            if(host_to_unlock == host):
                print "Found Host"
                # Call function with row number
                #print row
                cls.set_host_unlock(row)
            else:
                print "Wrong Host"

    @classmethod
    def set_host_unlock(cls, row_number):
        driver = DriverUtils.get_driver()

        check_return_value = cls.check_host(row_number)
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

        check_return_value = cls.check_host(row_number)
        if(check_return_value == 1):
            print "Unlock Failed"
            return
        elif(check_return_value == 2):
            pass
        elif(check_return_value == 3):
            return


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
            print "An error has occurred"
            return_value = 3
        return return_value

