import settings
import os
from selenium import webdriver
from selenium.webdriver.common.keys import Keys

__author__ = 'jbarber'


class DriverUtils():

    driver = None
    url = settings.DEFAULT_URL

    @classmethod
    def open_driver(cls, browser):
        """ Determines the browser to be used and opens it """

        if(browser.lower() == "firefox"):
            cls.driver = webdriver.Firefox()
        elif(browser.lower() == "chrome"):
            chromePath = os.path.realpath('drivers/chromedriver_linux64')

            cls.driver = webdriver.Chrome(
                executable_path=chromePath
            )
        else:
            print("Invalid browser specified. Using firefox by default")
            cls.driver = webdriver.Firefox()

    @classmethod
    def get_driver(cls):
        return cls.driver

    @classmethod
    def get_url(cls):
        return cls.url

    @classmethod
    def set_url(cls, u):
        cls.url = u

    @classmethod
    def close_driver(cls):
        cls.driver.close()

    @classmethod
    def dont_wait_for_elements(cls):
        """ Tells the driver to not wait for elements to load.
        If an element is not found right away, an exception is thrown
        Use when you expect an element to not be there and don't wish
        to wait for it to be loaded
        """

        cls.driver.implicitly_wait(0)

    @classmethod
    def wait_for_elements(cls, timeout):
        """ Tells the driver how much time in seconds to wait for
        elements to load. Driver will throw a NoSuchElementException
        if element is not loaded within given time frame
        """

        cls.driver.implicitly_wait(timeout)


class InputFields():

    @classmethod
    def button_input(cls, value):
        # Get driver
        driver = DriverUtils.get_driver()
        print "Button Input"
        create_button = driver.find_element_by_id("users__action_create")
        create_button.click()

    @classmethod
    def text_input(cls, **dict):
        # Get driver
        driver = DriverUtils.get_driver()
        print "Text Input"
        ram_input = driver.find_element_by_id("id_ram")
        ram_input.click()
        ram_input.send_keys(Keys.BACKSPACE)
        ram_input.send_keys(Keys.BACKSPACE)
        ram_input.send_keys(Keys.BACKSPACE)
        ram_input.send_keys(Keys.BACKSPACE)
        ram_input.send_keys(Keys.BACKSPACE)
        #ram_input.send_keys(ram)

    @classmethod
    def checkbox_input(cls):
        print "Checkbox Input"

    @classmethod
    def select_input(cls):
        print "Select Input"

