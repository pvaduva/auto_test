from common_utils import DriverUtils
from selenium.webdriver.support.ui import Select
from fault_alarm_management import FaultAlarms

import settings
import constants
import time

__author__ = 'jbarber'


class LocateSensor():

    @classmethod
    def set_sensor_action(cls, host_name, action):

        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        cls.base_url = url
        # Append to end of URL
        driver.get(DriverUtils.set_url(url + "/admin/inventory/?tab=inventory__hosts"))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)

        # Call function to set action
        cls.set_host_alarms(host_name, action)
        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)

    @classmethod
    def get_sensor_name(cls, host_name):

        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        cls.base_url = url
        # Append to end of URL
        print url
        driver.get(url + "/admin/inventory/")
        driver.find_element_by_link_text("Inventory").click()
        driver.find_element_by_link_text("Hosts").click()
        driver.find_element_by_link_text("controller-0").click()
        #driver.find_element_by_link_text(host_name).click()
        driver.find_element_by_link_text("Sensors").click()

        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)

        # Confirm sensor present
        time.sleep(10)
        check_return_value = cls.check_sensor_exists()
        if(check_return_value == 1):
            print "Test Passed"
            pass
        else:
            print "Test Failed"
            return

    @classmethod
    def set_host_alarms(cls, host_to_alarm, action):

        host_list = []
        row_number = -1
        driver = DriverUtils.get_driver()

        # Get link from partial text in table (Host Name column)
        links = driver.find_elements_by_partial_link_text('')
        for link in links:
            host_local = link.get_attribute("text")
            # Match host_to_alarm with link
            if(host_to_alarm in host_local):
                print ('Setting sensor action for: %s' % host_local)
                host_link = link.get_attribute("href")
                # Parse number from link
                parse = host_link.split("/")
                # Find the number in the list
                for num in parse:
                    if num.isdigit():
                        row_number = num
                temp_tuple = [host_local, row_number]
                host_list.append(temp_tuple)

        for item in host_list:
            host = item[0]
            row = item[1]
            if(host_to_alarm == host):
                # Call function with row number
                print ('Horizon row entry: %s' % row)
                cls.set_alarm_action(host_link, action)
            else:
                print "Wrong Host found"

    @classmethod
    def set_alarm_action(cls, link, action='log'):

        #print("Link: %s" % link)
        driver = DriverUtils.get_driver()
        driver.get(link)

        driver.find_element_by_link_text("Sensors").click()

        links = driver.find_elements_by_partial_link_text('')
        for i in range(len(links)):
            sensor_name = links[i].get_attribute("text")
            #print("link: %s" % sensor_name)
            if ('server fans' in sensor_name):
                sensor_id = links[i+1].get_attribute("id")
                print("Sensor id: %s" % sensor_id)
                driver.find_element_by_id(sensor_id).click()
                break

        # set the audit interval to 10secs
        driver.find_element_by_id("id_audit_interval_group").clear()
        driver.find_element_by_id("id_audit_interval_group").send_keys("10")

        # set the action for the critical alarm levels
        Select(driver.find_element_by_id("id_actions_critical_group")).select_by_visible_text(action)
        driver.find_element_by_css_selector("option[value=\"%s\"]" % action.lower()).click()

        # set the action for the major alarm levels
        Select(driver.find_element_by_id("id_actions_major_group")).select_by_visible_text(action)
        driver.find_element_by_css_selector("option[value=\"%s\"]" % action.lower()).click()

        # save the entries
        driver.find_element_by_xpath("//input[@value='Save']").click()

        # Confirm alarm severity and action
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        time.sleep(10)
        check_return_value = cls.check_alarm('critical')
        if(check_return_value == 1):
            print "Test Passed"
            pass
        else:
            print "Test Failed"
            return

    @classmethod
    def check_alarm(cls, alarm_name):

        DriverUtils.set_url(cls.base_url)
        FaultAlarms.check_alarms()

        for name in FaultAlarms.fault_names:
            if(alarm_name in name):
                print ("%s alarm found" % alarm_name)
                return_value = 1
        return return_value


    @classmethod
    def check_sensor_exists(cls):
        """
        Function for getting sensor names in host
        """

        fault_count = 0
        cls.sensor_names = []
        # Get driver
        driver= DriverUtils.get_driver()

        sensor_name = driver.find_element_by_xpath("//table[@id='sensors']")
        print ('sensor_name: %s' % sensor_name.text)
        sensor_name = sensor_name.text
        sensor_name = sensor_name.split('\n')
        sensor_name = sensor_name[6:]
        sensor_name = sensor_name[1::2]
        for name in sensor_name:
            fault_count += 1
            # Append all faults found in table to list
            print('Name: %s' % name)
            cls.sensor_names.append(name)
            # Or check against constants for matching faults
            # cls.check_faults_found(name)
        # Call function to output faults to console

        for name in cls.sensor_names:
            if(alarm_name in name):
                print ("%s alarm found" % alarm_name)
                return_value = 1
        return return_value
