#!/usr/bin/env python3.4

#TODO: This file should be under some directory like utils/ and not at
#      the same level as install_system.py

# Directory and file paths/names
NODE_INFO_DIR = "node_info"
LAB_SETTINGS_DIR = "lab_settings"
LATEST_BUILD_DIR = "latest_build"
EXPORT_LAB_REL_PATH = "export/lab"
LAB_YOW_REL_PATH = EXPORT_LAB_REL_PATH + "/yow"
LAB_SCRIPTS_REL_PATH = EXPORT_LAB_REL_PATH + "/scripts"


#TODO: Not all labs define their config_controller file as "system_config"
#      E.g. some refer to it as cgcs_config or TiS_config.ini
#      Need this filename to be ORed with other options or standardize naming
#      for config files in Stash
SYSTEM_CFG_FILENAME = "system_config"
CFGFILE_LIST = ["system_config", "TiS_config.ini"]
# TODO: Same todo as above, where the bulk add filename might be different
BULKCFG_LIST = ["hosts_bulk_add.xml", "hosts.xml"]
BULK_CFG_FILENAME = "hosts_bulk_add.xml"
LAB_SETUP_SCRIPT = "lab_setup.sh"
LAB_SETUP_CFG_FILENAME = "lab_setup.conf"
CUSTOM_LAB_SETTINGS_FILENAME = "settings.ini"
# TODO: Specifying full path to latest license instead of symlink as there
#       was a problem rsyncing the symlink "TiS15-GA-eval.lic". Fix this
LIC_FILENAME = "license.lic"
LICENSE_FILEPATH = "/folk/cgts/lab/TiS16-full-jun2016.lic"
SFP_LICENSE_FILEPATH = "/folk/cgts/lab/TiS16-CPE-full-jun2016.lic"
WRSROOT_ETC_PROFILE = "/etc/profile"
TUXLAB_BARCODES_DIR = "/export/pxeboot/vlm-boards"
RPM_INSTALL_REL_PATH = "export/RPM_INSTALL"
WRSROOT_HOME_DIR = "/home/wrsroot"
WRSROOT_PATCHES_DIR = WRSROOT_HOME_DIR + "/patches"
WRSROOT_IMAGES_DIR = WRSROOT_HOME_DIR + "/images"
JIRA_LOGS_DIR = "/folk/cgts/logs"
CERTIFICATE_FILE_PATH = "/folk/cgts/lab/server-with-key-with-passwd.pem"
CERTIFICATE_FILE_NAME = "server-with-key.pem"

# Cumulus TiS on TiS setup
CUMULUS_SERVER_IP="128.224.151.50"
BOOT_IMAGE_ISO = "bootimage.iso"
BOOT_IMAGE_ISO_SIZE = 5
BOOT_IMAGE_ISO_PATH = "export/" + BOOT_IMAGE_ISO
BOOT_IMAGE_ISO_TMP_PATH = "/tmp/" + BOOT_IMAGE_ISO
CUMULUS_CLEANUP_SCRIPT = "cumulus_cleanup.sh"
CUMULUS_SETUP_SCRIPT = "cumulus_setup.sh"
CUMULUS_SETUP_CFG_FILENAME = "cumulus_setup.conf"
CUMULUS_TMP_TIS_IMAGE_PATH = "/opt/backups/public"

# .ini section and option names
CFG_PROVISION_SECTION_NAME = "provision"
CFG_CMD_OPT_NAME = "commands"
CFG_BOOT_INTERFACES_NAME = "boot_interfaces"

# Node names
CONTROLLER = 'controller'
COMPUTE = 'compute'
STORAGE = 'storage'
CONTROLLER0 = 'controller-0'

ONLINE = "online"
OFFLINE = "offline"
AVAILABLE = "available"
ENABLED = "enabled"
DISABLED = "disabled"
UNLOCKED = "unlocked"
LOCKED = "locked"

ADMINISTRATIVE = "administrative"
OPERATIONAL = "operational"
AVAILABILITY = "availability"

STATE_TYPE_DICT = {ADMINISTRATIVE: [UNLOCKED, LOCKED],
                   OPERATIONAL: [ENABLED, DISABLED],
                   AVAILABILITY: [ONLINE, OFFLINE, AVAILABLE]}

PATCH_AVAILABLE_STATE = "Available"

# Installation
DEFAULT_BOOT_DEVICE_DICT = {'controller-0': '[ABC]00',
                        'compute': '[ABC]01',
                        'storage': '[ABC]01'}
BIOS_TYPES = [b"American Megatrends", b"Hewlett-Packard", b"Phoenix"]
BIOS_TYPE_FN_KEY_ESC_CODES = ['\x1b' + '[17~', '\x1b' + '@', '\x1b' + '[24~'] # F6, ESC + @, F12 Phoenix used for R720 nodes (i.e. Dell)
BIOS_TYPE_FN_HUMAN_READ = ['F6', 'ESC + @', 'F12']
INSTALL_TIMEOUTS = [2400, 2100, 2100]  # Some labs take longer that 2100 seconds to install; increased to 2400.
SERIAL_KICKSTART_CONTROLLER_INSTALL = "Serial Kickstart Controller Install"
MAX_BOOT_MENU_LINES = 15

NIC_INTERFACE = "eth0"

# BIOS options
UP = '\x1b' + '[A'
DOWN = '\x1b' + '[B'
RIGHT = '\x1b' + '[C'
LEFT = '\x1b' + '[D'

# VLM commands and options
VLM = "/folk/vlm/commandline/vlmTool"
VLM_RESERVE = 'reserve'
VLM_UNRESERVE = 'unreserve'
VLM_TURNON = 'turnOn'
VLM_TURNOFF = 'turnOff'
VLM_REBOOT = 'reboot'
VLM_FINDMINE = 'findMine'
VLM_GETATTR = 'getAttr'

VLM_CMDS_REQ_RESERVE = [VLM_UNRESERVE, VLM_TURNON, VLM_TURNOFF, VLM_REBOOT]

INSTALLATION_RESERVE_NOTE = "AUTO: Lab installation"

# Servers
BLD_SERVERS = ["yow-cgts1-lx", "yow-cgts2-lx", "yow-cgts3-lx"]
DEFAULT_BLD_SERVER = "yow-cgts3-lx"
TUXLAB_SERVERS = ["yow-tuxlab", "yow-tuxlab2"]
DEFAULT_TUXLAB_SERVER = "yow-tuxlab2"
DNS_SERVER ="8.8.8.8"
HOST_EXT = ".wrs.com"

# wrsroot user
WRSROOT_USERNAME = "wrsroot"
WRSROOT_DEFAULT_PASSWORD = WRSROOT_USERNAME
WRSROOT_PASSWORD = "li69nux"

#Telnet expect
TELNET_EXPECT_TIMEOUT = 3600
MAX_SEARCH_ATTEMPTS = 20
MAX_LOGIN_ATTEMPTS = 5

# SSH expect
SSH_EXPECT_TIMEOUT = 3600
SSH_EXPECT_ECHO = False

# ssh
RSYNC_SSH_OPTIONS = ["-o StrictHostKeyChecking=no",
                     "-o UserKnownHostsFile=/dev/null",
                     "-o ConnectTimeout={}".format(SSH_EXPECT_TIMEOUT)]
SSH_DIR = "~/.ssh"
SSH_KEY_FPATH = SSH_DIR + "/id_rsa"
AUTHORIZED_KEYS_FPATH = SSH_DIR + "/authorized_keys"
GET_PUBLIC_SSH_KEY_CMD = "ssh-keygen -y -f {}"
CREATE_PUBLIC_SSH_KEY_CMD = "ssh-keygen -f {} -t rsa -N ''"
KNOWN_HOSTS_PATH = SSH_DIR + "/known_hosts"
REMOVE_HOSTS_SSH_KEY_CMD = "ssh-keygen -f {} -R {}"
#TODO: Remove this after verified that above command works
#CREATE_PUBLIC_SSH_KEY_CMD = GET_PUBLIC_SSH_KEY_CMD + ' -q -P ""'

# Command timeouts
COLLECT_TIMEOUT=300
RSYNC_TIMEOUT = 3600
REBOOT_TIMEOUT = 3600
BIOS_TYPE_TIMEOUT = 1800
CONFIG_CONTROLLER_TIMEOUT = 1200
LAB_SETUP_TIMEOUT = 1800
WIPE_DISK_TIMEOUT = 30
PING_TIMEOUT = 60
TIMEOUT_BUFFER = 2

# Prompts
LOGIN_PROMPT = "ogin:"
PASSWORD_PROMPT = "assword:"
PROMPT = ".*\$ "

# Other
LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

# Surrounding return code with special characters to ensure
# other numbers (i.e. date-timestamp prompt) in the output
# are not mistaken for it
OPEN_MARKER = '['
CLOSE_MARKER = ']'
RETURN_CODE_REGEX = r"\{}".format(OPEN_MARKER) + "\d+" + r"\{}".format(CLOSE_MARKER)
RETURN_CODE_CMD = "echo {}$?{}".format(OPEN_MARKER, CLOSE_MARKER)
# e.g. Tue Nov 24 15:52:39 UTC 2015
DATE_TIMESTAMP_REGEX = r"\w{3} \w{3} \d{2} \d{2}:\d{2}:\d{2} \w{3} \d{4}"
TIS_BLD_DIR_REGEX = r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}"

# Email notification constants
EMAIL_SERVER = 'prod-webmail.corp.ad.wrs.com'
EMAIL_FROM = 'no_reply_automated_labinstall@wrs.com'
EMAIL_SUBJECT = 'Automated Lab Install: '
EMAIL_ERROR_MSG = "Automated lab install has encountered problem." \
    "\nReason: "
