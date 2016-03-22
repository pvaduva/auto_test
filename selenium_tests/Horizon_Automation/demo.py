'''
demo.py - An example program showing the basic functions of Selenium

Copyright (c) 2015 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.


This example runs through logging into Horizon and clicking
the drop down of host 'compute-0'
'''

'''
modification history:
---------------------
26nov15,jbb  Initial file
'''

from selenium import webdriver

# Constants
DROP_DOWN_UNIQUE_SELECTOR_FIRST_HALF = "#hosts__row__"
DROP_DOWN_UNIQUE_SELECTOR_SECOND_HALF = "> td:nth-child(8) > div:nth-child(1) > a:nth-child(2)"

# Global variables
username = "admin"
password = "admin"
host_id_link = ""
row_number = -1
host_name = 'compute-0'

# Create firefox instance
driver = webdriver.Firefox()

# Get Horizon web page
driver.get("http://10.10.10.2")

# Login
# Find HTML element for username input field by ID
username_element = driver.find_element_by_id("id_username")
# Type in the input for username
username_element.send_keys(username)
# Find HTML element for password input field by CSS
password_element = driver.find_element_by_css_selector("#id_password")
# Type in the input for password
password_element.send_keys(password)
# Find HTML element for Sign In button by XPath
button_element = driver.find_element_by_xpath("//button[@id='loginBtn']")
button_element.click()

# Get Inventory web page
driver.get("http://10.10.10.2/admin/inventory/?tab=inventory__hosts")

# Get link from partial text in table (Host Name column)
links = driver.find_elements_by_partial_link_text('')
# Loop through list of links
for link in links:
    # Get text of every link
    host_link = link.get_attribute("text")
    # Match host_name with link
    if(host_name in host_link):
        # This is the link containing the id that we are looking for
        host_id_link = link.get_attribute("href")

# Parse number from link
parse_list = host_id_link.split("/")
# Find the number in the list
for num in parse_list:
    if num.isdigit():
        row_number = num

# compute_0_drop_down_location is our id we look for now using the driver
compute_0_drop_down_location = DROP_DOWN_UNIQUE_SELECTOR_FIRST_HALF + str(row_number) + DROP_DOWN_UNIQUE_SELECTOR_SECOND_HALF

# Locate compute-0 drop down and click it
compute_0_drop_down = driver.find_element_by_css_selector(compute_0_drop_down_location)
compute_0_drop_down.click()
