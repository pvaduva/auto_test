from common_utils import DriverUtils
import settings

__author__ = 'jbarber'


class FaultAlarms():

    @classmethod
    def check_alarms(cls):
        """
        Function for checking alarms in Fault Management
        """
        print "Fault Alarm Management Information----------------------------------------------------------------------"
        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        # Append to end of URL
        driver.get(DriverUtils.set_url(url + "/admin/fault_management/?tab=alarms_tabs__alarms"))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        # Call function to get fault names
        cls.get_fault_names()
        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)

    @classmethod
    def get_fault_names(cls):
        """
        Function for getting fault names in Fault Management
        """
        fault_count = 0
        fault_names = []
        # Get driver
        driver= DriverUtils.get_driver()

        fault_name = driver.find_element_by_xpath("//table[@id='alarms']")
        fault_name = fault_name.text
        fault_name = fault_name.split('\n')
        fault_name = fault_name[6:]
        fault_name = fault_name[1::2]
        for name in fault_name:
            fault_count += 1
            # Append all faults found in table to list
            fault_names.append(name)
            # Or check against constants for matching faults
            # cls.check_faults_found(name)
        # Call function to output faults to console
        cls.output_faults(fault_names, fault_count)

    @classmethod
    def output_faults(cls, fault_names, fault_count):
        """
        Function for outputting faults to console

        :param fault_names: list of fault names
        :param fault_count: number of total faults
        """
        print "There are currently " + str(fault_count) + " faults."
        print "Listing faults:"
        for fault_name in fault_names:
            print fault_name
