from common_utils import DriverUtils
import settings
import time


__author__ = 'jbarber'


class Login():

    @classmethod
    def login(cls, username, password):
        """
        Function for logging into Horizon

        :param username: username for Horizon login
        :param password: password for Horizon login
        """

        # Get driver
        driver = DriverUtils.get_driver()
        driver.get(DriverUtils.get_url())

        # Check username and password are NOT empty
        if(username != ""):
            if(password != ""):
                # Perform login
                # Find HTML element for username input field
                username_element = driver.find_element_by_name("username")
                # Type in the input for username
                username_element.send_keys(username)
                # Find HTML element for password input field
                password_element = driver.find_element_by_name("password")
                # Type in the input for password
                password_element.send_keys(password)
                # Submit HTML form
                password_element.submit()
                time.sleep(settings.DEFAULT_SLEEP_TIME)
        else:
            print "Username or Password is missing/invalid"
            print "Exiting..."
            exit(1)


class Logout():

    @classmethod
    def logout(cls):
        """
        Function for logging out of Horizon
        """

        # Get driver
        logout_link = ""
        driver = DriverUtils.get_driver()
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Get link from partial text in table (Host Name column)
        links = driver.find_elements_by_partial_link_text('')
        for link in links:
            host_local = link.get_attribute("text")
            # Match host_to_lock with link
            if("Sign Out" in host_local):
                logout_link = link.get_attribute("href")
        driver.get(DriverUtils.set_url(logout_link))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)
        time.sleep(settings.DEFAULT_SLEEP_TIME)