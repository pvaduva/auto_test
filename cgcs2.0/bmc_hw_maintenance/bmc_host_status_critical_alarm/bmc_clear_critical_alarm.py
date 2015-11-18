# -*- coding: utf-8 -*-
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

# IP1-4
NODE_OAM_ADDRESS_3='10.10.10.2'
CONTROLLER_0_ADDRESS='192.168.204.3'
CONTROLLER_0_MAC='c8:1f:66:e0:ff:01'

class BmcQuantaConfig(unittest.TestCase):

    def print_out(self, stdoutput):
        for row in stdoutput:
            print ("%s" % row)

    def setUp(self):
        self.verificationErrors = []
        self.accept_next_alert = True

        # open a connection to the host
        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect("%s" % NODE_OAM_ADDRESS_3, username="wrsroot", password="li69nux")

        # ensure all alarms are cleared
        ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("echo 'li69nux' | sudo -S rm -rf /home/wrsroot/show_quanta")
        os.system("expect ./sendfile.exp %s %s" % ("../clear_alarms/show_quanta", NODE_OAM_ADDRESS_3))
        ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("echo 'li69nux' | sudo -S cp -rf /home/wrsroot/show_quanta /usr/sbin/show")
        print("Waiting 2mins for the alarms to be cleared....")
        time.sleep (120)
        ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("source /etc/nova/openrc; system host-sensor-list controller-0")
        self.print_out (ssh_stdout.readlines())


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

    def test_bmc_quanta_configured_cli(self):
        self.bmc_login()
        #self.bmc_config()

    
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
