__author__ = 'JBARBER'

import os.path
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait # available since 2.4.0
from selenium.webdriver.support import expected_conditions as EC # available since 2.26.0
import time

# This section defines all alarm names with descriptions (INCOMPLETE)
CONST_CPU_USAGE = "Platform CPU threshold exceeded; threshold"
CONST_VSWITCH_CPU_USAGE = "VSwitch CPU threshold exceeded; threshold"
CONST_MEMORY_USAGE = "Memory threshold exceeded; threshold"

CONST_FILE_SYSTEM_USAGE = "File System threshold exceeded; threshold"
CONST_PLATFORM_NOVA_INSTANCES = "No access to remote VM volumes."
CONST_OAM_PORT = "'OAM' Port failed."
CONST_OAM_INTERFACE1 = "'OAM' Interface degraded."
CONST_OAM_INTERFACE2 = "'OAM' Interface failed."
CONST_MGMT_PORT = "'MGMT' Port failed."
CONST_MGMT_INTERFACE1 = "'MGMT' Interface degraded."
CONST_MGMT_INTERFACE2 = "'MGMT' Interface failed."

CONST_LICENSE_EXPIRY1 = "License key has expired or is invalid; a valid license key is required for operation."
CONST_LICENSE_EXPIRY2 = "Evaluation license key will expire on"

CONST_COMMUNICATION_FAILURE = "Communication failure detected with peer over port"

CONST_SERVICE_GROUP_REDUNDANCY = "Service group loss of redundancy;"


# Create a new instance of the Firefox driver
driver = webdriver.Firefox()

# login() to Horizon (admin, admin)
# string user, string password
def login(user, password):
    # Go to Horizon login page
    driver.get("http://10.10.10.2")
    # Find element username (username input box)
    inputElement = driver.find_element_by_name("username")
    # Type in the input for username
    inputElement.send_keys(user)
    # Find element password (password input box)
    inputElement = driver.find_element_by_name("password")
    # Type in the input for password
    inputElement.send_keys(password)
    # submit the form (log user into Horizon)
    inputElement.submit()
    try:
        # we have to wait for the page to refresh, the last thing that seems to be updated is the title
        WebDriverWait(driver, 10)
    finally:
        pass

# navSystemFaultManagement() to navigate to Admin -> System -> Fault Management
def navSystemFaultManagement():
    driver.get("http://10.10.10.2/admin/fault_management/?tab=alarms_tabs__alarms")

# getFaultCount() gets the number of faults to determine that faults exist
# This function maybe not needed in the future
def getFaultCount():
    dataW = driver.find_element_by_css_selector("#alarms > tbody:nth-child(2)")
    data = dataW.text
    if(data == ""):
        print "No alarms have been triggered"
    else:
        data = [line.strip() for line in data.split('\n') if line.strip()]
        count = 0
        for a in data:
            count+=1
        count = (count / 2)
        return count
        #print data

# getFaultNames() gets names of all faults using XPath
# Loop calls notifyFaultsFound() for each fault alarm name
def getFaultNames():
    # Use XPath to go through all fault reason text
    name = driver.find_element_by_xpath("//table[@id='alarms']")
    print name.text
    name = name.text # Raw text of entire object
    name = name.split('\n') # Split object into list
    name = name[6:] # Remove first 6 items from list (titles)
    name = name[1::2] # Remove Alarm ID from list
    for item in name:
        #print item
        notifyFaultsFound(item)

# notifyFaultsFound() prints all faults on Horizon Fault Management page to console (todo file?)
def notifyFaultsFound(faultName):
    if(CONST_CPU_USAGE in faultName):
        print faultName
    else:
        pass
    if(CONST_VSWITCH_CPU_USAGE in faultName):
        print faultName
    else:
        pass
    if(CONST_SERVICE_GROUP_REDUNDANCY in faultName):
        print faultName
    else:
        pass
    if(CONST_COMMUNICATION_FAILURE in faultName):
        print faultName
    else:
        pass
    if(CONST_LICENSE_EXPIRY1 in faultName):
        print faultName
    else:
        pass
    if(CONST_LICENSE_EXPIRY2 in faultName):
        print faultName
    else:
        pass

# Main function calls functions in order
def main():
    login("admin", "admin") # user, password
    navSystemFaultManagement()
    countM = getFaultCount()
    if(countM == 0):
        "No Faults"
        return 0
    print "There are currently " + str(countM) + " faults."
    print "Listing faults:"
    getFaultNames()
    driver.quit()
    return 0

# Program Starts Here!
main()