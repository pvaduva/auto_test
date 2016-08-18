from selenium import webdriver
from selenium.webdriver.common.keys import Keys

IP = "128.224.64.178"
USERNAME = "root"
PASSWORD = "root"

addr = "http://" + IP
driver = webdriver.Firefox()
driver.get(addr)

username = driver.find_element_by_id("login_username")
username.send_keys(USERNAME)
password = driver.find_element_by_id("login_password")
password.send_keys(PASSWORD)
login = driver.find_element_by_name("Login").click()

driver.implicitly_wait(5)

driver.switch_to.frame("HEADER")
remote_control = driver.find_element_by_id("STR_TOPNAV_REMOTE_CONTROL").click()

driver.implicitly_wait(5)

console_addr = addr + "/page/launch_redirection.html"
driver.get(console_addr)
launch_console = driver.find_element_by_id("_launchJava").click()

driver.close()

