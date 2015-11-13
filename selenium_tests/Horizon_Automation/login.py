from common_utils import DriverUtils

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
