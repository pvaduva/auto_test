from selenium.webdriver import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from common_utils import DriverUtils
import constants
import settings
import time
# import paramiko

__author__ = 'jbarber'


class Images():

    @classmethod
    def images(cls, image_name, image_location, format, copy_data, timeout, downtime, public, instance_auto_recovery):
        print "Create Images (Admin -> System -> Images)---------------------------------------------------------------"
        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        # Append to end of URL
        driver.get(DriverUtils.set_url(url + "/admin/images/"))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        # Call Functions below
        cls.create_images(image_name, image_location, format, copy_data, timeout, downtime, public,
                          instance_auto_recovery)
        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)

    @classmethod
    def create_images(cls, image_name, image_location, format, copy_data, timeout, downtime, public,
                      instance_auto_recovery):
        # Get driver
        driver = DriverUtils.get_driver()

        create_button = driver.find_element_by_id("images__action_create")
        create_button.click()

        image_name_input = driver.find_element_by_id("id_name")
        image_name_input.click()
        image_name_input.send_keys(image_name)

        image_location_input = driver.find_element_by_id("id_image_url")
        image_location_input.click()
        image_location_input.send_keys(image_location)

        format_input = Select(driver.find_element_by_id("id_disk_format"))
        format_input.select_by_visible_text(format)

        if(copy_data == False):
            copy_data_input = driver.find_element_by_id("id_is_copying")
            copy_data_input.click()
        else:
            pass

        if(timeout == None):
            timeout_input = driver.find_element_by_id("id_hw_wrs_live_migration_timeout")
            timeout_input.click()
            timeout_input.send_keys(Keys.BACKSPACE)
            timeout_input.send_keys(Keys.BACKSPACE)
            timeout_input.send_keys(Keys.BACKSPACE)
            timeout_input.send_keys(Keys.BACKSPACE)
        else:
            timeout_input = driver.find_element_by_id("id_hw_wrs_live_migration_timeout")
            timeout_input.click()
            timeout_input.send_keys(timeout)

        if(downtime == None):
            downtime_input = driver.find_element_by_id("id_hw_wrs_live_migration_max_downtime")
            downtime_input.click()
            downtime_input.send_keys(Keys.BACKSPACE)
            downtime_input.send_keys(Keys.BACKSPACE)
            downtime_input.send_keys(Keys.BACKSPACE)
            downtime_input.send_keys(Keys.BACKSPACE)
        else:
            downtime_input = driver.find_element_by_id("id_hw_wrs_live_migration_timeout")
            downtime_input.click()
            downtime_input.send_keys(downtime)

        if(public == True):
            public_input = driver.find_element_by_id("id_is_public")
            public_input.click()
        else:
            pass

        if(instance_auto_recovery == False):
            instance_auto_recovery_input = driver.find_element_by_id("id_sw_wrs_auto_recovery")
            instance_auto_recovery_input.click()
        else:
            pass

        image_name_input.submit()
    """
    @classmethod
    def get_guest_image(cls):
        print "Hi"
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.WarningPolicy())
        client.connect('128.224.145.121', '22', 'jbarber', '3jbarber')
        stdin, stdout, stderr = client.exec_command("cd /buildarea3/users/jbarber/")
        return_value = stdout.channel.recv_exit_status()
        print return_value
        if(return_value == 0):
            pass
        else:
            print "CD Failed"
            return 1
        time.sleep(1)
        stdin, stdout, stderr = client.exec_command("scp jbarber@128.224.145.134:"
                            "/localdisk/loadbuild/jenkins/CGCS_2.0_Guest_Daily_Build/cgcs-guest.img ./cgcs-guest.img")
        return_value2 =  stdout.channel.recv_exit_status()
        print return_value2
        if(return_value2 == 0):
            pass
        else:
            print "SCP Failed"
            return 2
        time.sleep(1)
        """
















