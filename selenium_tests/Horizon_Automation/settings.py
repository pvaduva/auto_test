'''
settings.py - Handles the default settings of Selenium

Copyright (c) 2015 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.

Settings defaults
'''

'''
modification history:
---------------------
26nov15,jbb  Initial file
'''

# Defaults
DEFAULT_BROWSER = "firefox"
DEFAULT_URL = "http://10.10.10.2"
SECURE_URL = "https://10.10.10.2"
DEFAULT_ELEMENT_LOAD_TIME = 30
DEFAULT_SLEEP_TIME = 4

SUPPORTED_BROWSERS = ["firefox", "chrome"]