# -*- coding: utf-8 -*-
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import NoAlertPresentException
import unittest, time, re

class BmcQuantaSuppressGroup(unittest.TestCase):
    def setUp(self):
        self.driver = webdriver.Firefox()
        self.driver.implicitly_wait(30)
        self.base_url = "http://128.224.150.73/"
        self.verificationErrors = []
        self.accept_next_alert = True
    
    def test_bmc_quanta_suppress_group(self):
        driver = self.driver
        driver.get(self.base_url + "/admin/fault_management/")
        driver.find_element_by_link_text("Inventory").click()
        driver.find_element_by_link_text("controller-0").click()
        driver.find_element_by_xpath("//tr[@id='sensorgroups__row__11667d2b-345e-43db-abf2-47c79c2f7c48']/td[7]/div/a[2]").click()
        driver.find_element_by_id("sensorgroups__row_11667d2b-345e-43db-abf2-47c79c2f7c48__action_suppress").click()
        driver.find_element_by_link_text("Suppress SensorGroup").click()
        driver.find_element_by_xpath("//tr[@id='sensorgroups__row__11667d2b-345e-43db-abf2-47c79c2f7c48']/td[7]/div/a[2]").click()
        driver.find_element_by_id("sensorgroups__row_11667d2b-345e-43db-abf2-47c79c2f7c48__action_unsuppress").click()
    
    def is_element_present(self, how, what):
        try: self.driver.find_element(by=how, value=what)
        except NoSuchElementException, e: return False
        return True
    
    def is_alert_present(self):
        try: self.driver.switch_to_alert()
        except NoAlertPresentException, e: return False
        return True
    
    def close_alert_and_get_its_text(self):
        try:
            alert = self.driver.switch_to_alert()
            alert_text = alert.text
            if self.accept_next_alert:
                alert.accept()
            else:
                alert.dismiss()
            return alert_text
        finally: self.accept_next_alert = True
    
    def tearDown(self):
        self.driver.quit()
        self.assertEqual([], self.verificationErrors)

if __name__ == "__main__":
    unittest.main()
