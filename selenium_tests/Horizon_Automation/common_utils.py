import settings
import os
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from pyvirtualdisplay import Display

__author__ = 'jbarber'


class DriverUtils():

    driver = None
    profile = None
    url = settings.DEFAULT_URL

    @classmethod
    def open_driver(cls, browser):
        """ Determines the browser to be used and opens it """

        if(browser.lower() == "firefox"):
            """
            profile = webdriver.FirefoxProfile()
            path = "C:/Users/JBARBER/Downloads"
            profile.set_preference("browser.download.folderList", 2)
            profile.set_preference("browser.download.dir", path)
            profile.set_preference("browser.download.alertOnPEMOpen", False)
            profile.set_preference("browser.helperApps.neverAsksaveToDisk", "text/pem")
            profile.set_preference("browser.download.manager.showWhenStarting", False)
            profile.set_preference("browser.download.manager.focusWhenStarting", False)
            profile.set_preference("browser.helperApps.alwaysAsk.force", False)
            profile.set_preference("browser.download.manager.alertOnOpen", False)
            profile.set_preference("browser.download.manager.closeWhenDone", False)
            profile.set_preference("browser.download.manager.showAlertOnComplete", False)
            profile.set_preference("browser.download.manager.useWindow", False)
            profile.set_preference("browser.download.manager.showWhenStarting", False)
            profile.set_preference("services.sync.prefs.sync.browser.download.manager.showWhenStarting", False)
            profile.set_preference("pdfjs.disabled", True)
            """
            display = Display(visible=0, size=(1024, 768))
            display.start()
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
    def button_input(cls, common_element, selector_type):
        """
        Function for locating and clicking HTML button elements

        :param common_element: HTML element tag text
        :param selector_type: HTML element type [css or id]
        """

        # Get driver
        driver = DriverUtils.get_driver()
        if(selector_type == 'id'):
            create_button = driver.find_element_by_id(common_element)
            create_button.click()
        if(selector_type == 'css'):
            create_button = driver.find_element_by_css_selector(common_element)
            create_button.click()

    @classmethod
    def text_input(cls, key, value):
        """
        Function for locating, clicking and inputting text into HTML input elements

        :param key: HTML element tag id
        :param value: value to input into text field
        """

        # Get driver
        driver = DriverUtils.get_driver()
        common_input = driver.find_element_by_id(key)
        common_input.click()
        common_input.send_keys(Keys.BACKSPACE)
        common_input.send_keys(Keys.BACKSPACE)
        common_input.send_keys(Keys.BACKSPACE)
        common_input.send_keys(Keys.BACKSPACE)
        common_input.send_keys(Keys.BACKSPACE)
        common_input.send_keys(value)

    @classmethod
    def checkbox_input(cls, key, value):
        """
        Function for locating and clicking HTML checkbox elements

        :param key: HTML element tag id
        :param value: value of True or False
        """

        print "Checkbox Input"

    @classmethod
    def select_input(cls, key, value):
        """
        Function for locating and selecting in drop down HTML elements

        :param key: HTML element tag id
        :param value: value to locate and select
        """

        # Get driver
        driver = DriverUtils.get_driver()
        common_select = Select(driver.find_element_by_id(key))
        common_select.select_by_visible_text(value)

    @classmethod
    def submit(cls, element):
        """
        Function for submitting HTML form elements

        :param element: HTML element tag id
        """

        # Get driver
        driver = DriverUtils.get_driver()
        common_element = driver.find_element_by_id(element)
        common_element.submit()
