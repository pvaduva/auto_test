# -*- coding: utf-8 -*-
#
# ip1-4 192.168.204.3 00:1e:67:54:aa:39
# pv0   192.168.204.3 90:e2:ba:a3:a0:c8
#
#
#
#
#-----------------------------------------------------------------------------#
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import NoAlertPresentException
import os
import unittest, time, re
import paramiko

# define constants
#PV-0
NODE_OAM_ADDRESS_1='128.224.150.141'
CONTROLLER_0_ADDRESS='192.168.204.3'
CONTROLLER_0_MAC='c8:1f:66:e0:ff:01'

# IP1-4
NODE_OAM_ADDRESS_2='128.224.151.212'
CONTROLLER_0_ADDRESS='192.168.204.3'
CONTROLLER_0_MAC='c8:1f:66:e0:ff:01'

# VBOX
NODE_OAM_ADDRESS_3='10.10.10.2'
CONTROLLER_0_ADDRESS='192.168.204.3'
CONTROLLER_0_MAC='c8:1f:66:e0:ff:01'

class BmcQuantaConfig(unittest.TestCase):

    def setUp(self):
        self.driver = webdriver.Firefox()
        self.driver.implicitly_wait(30)
        self.base_url = "http://%s/" % NODE_OAM_ADDRESS_3
        self.verificationErrors = []
        self.accept_next_alert = True
        self.alarms = ['a','b','c','d','e']
        self.nodes = ['controller-0',
                      'controller-1',
                      'compute-0',
                      'compute-1']

        # open a connection to the hosts
        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect("%s" % NODE_OAM_ADDRESS_3, username="wrsroot", password="li69nux")

        # transfer a password updating script to the host
        os.system ('expect ./sendfile.exp %s %s' % 
                        ("./set_root_password.exp", NODE_OAM_ADDRESS_3))

        # set the root password on the hosts
        print("Updating host root password")
        ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("expect ./set_root_password.exp")
         
        # configure the alarms   
        print("Configuring alarms...")
        ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("echo 'li69nux' | sudo -S cp -rf /usr/sbin/show_quanta /usr/sbin/show")


    def bmc_login(self):
        driver = self.driver
        driver.get(self.base_url + "/auth/login/")
        driver.find_element_by_id("id_username").clear()
        driver.find_element_by_id("id_username").send_keys("admin")
        driver.find_element_by_id("id_password").clear()
        driver.find_element_by_id("id_password").send_keys("admin")
        driver.find_element_by_id("loginBtn").click()

    def bmc_config(self, node):
        driver = self.driver
        driver.find_element_by_link_text("Inventory").click()
        driver.find_element_by_link_text("Hosts").click()
        #driver.find_element_by_id(node).click()
        links = driver.find_elements_by_partial_link_text('')
        for i in range(len(links)):
            board_mgmnt = links[i].get_attribute("text")
            #print("link: %s" % board_mgmnt)
            if (node in board_mgmnt):
                board_mgmnt_id = links[i+1].get_attribute("id")
                print("Board management id: %s" % board_mgmnt_id)
                driver.find_element_by_id(board_mgmnt_id).click()
                break
        try:
            driver.find_element_by_link_text("Board Management").click()
            Select(driver.find_element_by_id("id_bm_region_ilo")).select_by_visible_text("Quanta Integrated Lights Out External")
            driver.find_element_by_css_selector("option[value=\"external_quanta\"]").click()
            driver.find_element_by_id("id_bm_mac").clear()
            driver.find_element_by_id("id_bm_mac").send_keys("00:1e:67:54:aa:39")
            driver.find_element_by_id("id_bm_ip").clear()
            driver.find_element_by_id("id_bm_ip").send_keys("192.168.204.3")
            driver.find_element_by_id("id_bm_username").clear()
            driver.find_element_by_id("id_bm_username").send_keys("root")
            driver.find_element_by_id("id_bm_password").clear()
            driver.find_element_by_id("id_bm_password").send_keys("root")
            driver.find_element_by_id("id_bm_confirm_password").clear()
            driver.find_element_by_id("id_bm_confirm_password").send_keys("root")
            driver.find_element_by_xpath("//input[@value='Save']").click()
        except Exception as e:
            print("FAIL: Element not found: %s" % e)
            return False
        time.sleep(30)

    # Enable BMC on all nodes
    def test_bmc_autoprovision_quanta(self):
        self.bmc_login()
        for node in self.nodes:
           if not self.bmc_config(node):
               return False

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
    try:
        unittest.main()
    except Exception as e:
        print("Test Failed. Reason: %s" % e)
