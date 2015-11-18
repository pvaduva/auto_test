# -*- coding: utf-8 -*-
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import NoAlertPresentException
import unittest, time, re
import paramiko

class BmcQuantaConfig(unittest.TestCase):

    def setUp(self):
        self.driver = webdriver.Firefox()
        self.driver.implicitly_wait(30)
        self.base_url = "http://128.224.150.141/"
        self.verificationErrors = []
        self.accept_next_alert = True
        self.alarms = ['a','b','c','d','e']
        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect("128.224.150.141", username="wrsroot", password="li69nux")
        ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("echo 'li69nux' | sudo -S cp -rf /usr/sbin/show_quanta /usr/sbin/show")
        ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("echo root:li69nux > passwd.txt")
        ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("sudo -S chpasswd < 'passwd.txt'")
    
    def bmc_login(self):
        return
        driver = self.driver
        driver.get(self.base_url + "/auth/login/")
        driver.find_element_by_id("id_username").clear()
        driver.find_element_by_id("id_username").send_keys("admin")
        driver.find_element_by_id("id_password").clear()
        driver.find_element_by_id("id_password").send_keys("admin")
        driver.find_element_by_id("loginBtn").click()
        driver.find_element_by_link_text("Inventory").click()
        driver.find_element_by_link_text("Hosts").click()

    def bmc_config(self):
        driver = self.driver
        driver.find_element_by_id("hosts__row_1__action_update").click()
        driver.find_element_by_link_text("Board Management").click()
        Select(driver.find_element_by_id("id_bm_region_ilo")).select_by_visible_text("Quanta Integrated Lights Out External")
        driver.find_element_by_css_selector("option[value=\"external_quanta\"]").click()
        driver.find_element_by_id("id_bm_mac").clear()
        driver.find_element_by_id("id_bm_mac").send_keys("c8:1f:66:e0:ff:01")
        driver.find_element_by_id("id_bm_ip").clear()
        driver.find_element_by_id("id_bm_ip").send_keys("192.168.204.3")
        driver.find_element_by_id("id_bm_username").clear()
        driver.find_element_by_id("id_bm_username").send_keys("root")
        driver.find_element_by_id("id_bm_password").clear()
        driver.find_element_by_id("id_bm_password").send_keys("root")
        #driver.find_element_by_id("id_bm_confirm_password").clear()
        driver.find_element_by_id("id_bm_confirm_password").send_keys("root")
        driver.find_element_by_xpath("//input[@value='Save']").click()
        #driver.find_element_by_link_text("Sign Out").click()
        self.suppress_alarm_group()

    def test_bmc_quanta_suppress_group1(self):
        self.bmc_login()
        #self.bmc_config()
        #self.find_alarm_group()
        #self.suppress_alarm_group()
        #self.unsuppress_alarm_group()

    def find_alarm_group(self):
        driver = self.driver
        driver.get(self.base_url + "/admin/fault_management/")
        driver.find_element_by_link_text("Inventory").click()
        driver.find_element_by_link_text("controller-0").click()
        driver.find_element_by_link_text("Sensors").click()

    def suppress_alarm_group(self):
        try:
            driver = self.driver
            for idx in self.alarms:
                print("idx: %s" % idx)
                driver.find_element_by_xpath("//*[contains(@id, 'sensorgroups__row__')]/td[7]/div/a[2]").click()
                #driver.find_element_by_xpath("//tr[starts-with(@id, 'sensorgroups__row__')]/td[7]/div/a[2]").click()
                driver.find_element_by_xpath("//*[starts_with(@id, 'sensorgroups__row_')]" and "//*[contains (@id, '__action_suppress')]").click()
                #driver.find_element_by_id("sensorgroups__row_11667d2b-345e-43db-abf2-47c79c2f7c48__action_suppress").click()
                driver.find_element_by_link_text("Suppress SensorGroup").click()
        except:
            pass

    def unsuppress_alarm_group(self):
        driver = self.driver
        # int totalCheckboxes = driver.getXpathCount("//*[contains(@id, 'sensorgroups__row__')]/td[7]/div/a[2]").intValue();
        for idx in self.alarms:
            try:
                print("idx: %s" % idx)
                driver.find_element_by_xpath("//*[contains(@id, 'sensorgroups__row__')]/td[7]/div/a[2]").click()
                #driver.find_element_by_xpath("//tr[starts-with(@id, 'sensorgroups__row__')]/td[7]/div/a[2]").click()
                driver.find_element_by_xpath("//*[starts_with(@id, 'sensorgroups__row')]" and "//*[contains (@id, 'action_unsuppress')]").click()
                #driver.find_element_by_id("sensorgroups__row_11667d2b-345e-43db-abf2-47c79c2f7c48__action_suppress").click()
                driver.find_element_by_link_text("UnSuppress SensorGroup").click()
            except Exception as e:
                pass
    
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
        #self.driver.quit()
        self.assertEqual([], self.verificationErrors)

if __name__ == "__main__":
    unittest.main()
