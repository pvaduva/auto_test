#!/usr/bin/env python3.4

# Directory and file paths/names
NODE_INFO_DIR="node_info"
LAB_SETTINGS_DIR="lab_settings"
LATEST_BUILD_DIR="latest_build"
LAB_YOW_REL_PATH="layers/wr-cgcs/cgcs/extras.ND/lab/yow"
SYSTEM_CONFIG_FILENAME="system_config"
BULK_CONFIG_FILENAME="hosts_bulk_add.xml"
CUSTOM_LAB_SETTINGS_FILENAME="settings.ini"
LICENSE_FILEPATH = "/folk/cgts/lab/TiS15-GA-demo.lic"
ETC_PROFILE="/etc/profile"
TUXLAB_BARCODES_DIR = "/export/pxeboot/vlm-boards"
HOME_DIR = "/home/wrsroot"
PATCHES_DIR = HOME_DIR + "/patches"

# .ini section and option names
CFG_PROVISION_SECTION_NAME="provision"
CFG_CMD_OPT_NAME="commands"
CFG_BOOT_INTERFACES_NAME="boot_interfaces"

# Node names
CONTROLLER='controller'
COMPUTE='compute'
STORAGE='storage'
CONTROLLER0='controller-0'

# Installation
DEFAULT_BOOT_DEVICES = { 'controller-0' : 'A00',
                 'compute' : 'A01',
                 'storage' : 'A01'}
BIOS_TYPES = [b"American Megatrends", b"Hewlett-Packard", b"Phoenix"]
BIOS_TYPE_FN_KEY_ESC_CODES = ['\x1b' + '[17~', '\x1b' + '@', '\x1b' + '^[24~'] # F6, ESC + @, F12 Phoenix used for R720 nodes (i.e. Dell)
INSTALL_TIMEOUTS = [1000, 2200, 1000]
SERIAL_KICKSTART_CONTROLLER_INSTALL = "Serial Kickstart Controller Install"
MAX_BOOT_MENU_LINES = 10

# BIOS options
UP = "^[[A"
DOWN = "^[[B"
RIGHT = "^[[C"
LEFT = "^[[D"

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
DEFAULT_TUXLAB_SERVER = "yow-tuxlab"
HOST_EXT = ".wrs.com"

# SCP user
SCP_USERNAME = "svc-cgcsauto"
SCP_PASSWORD = ")OKM0okm"

# wrsroot user
WRSROOT_USERNAME = "wrsroot"
WRSROOT_DEFAULT_PASSWORD = WRSROOT_USERNAME
WRSROOT_PASSWORD = "li69nux"

#Telnet expect
TELNET_EXPECT_TIMEOUT = 20
MAX_SEARCH_ATTEMPTS = 10

# SSH expect
SSH_EXPECT_TIMEOUT = 20
SSH_EXPECT_ECHO = False

# ssh
RSYNC_SSH_OPTIONS = ["-o StrictHostKeyChecking=no",
                     "-o UserKnownHostsFile=/dev/null",
                     "-o ConnectTimeout={}".format(SSH_EXPECT_TIMEOUT)]
SSH_DIR = "~/.ssh"
SSH_KEY_FPATH = SSH_DIR + "/id_rsa.pub"
AUTHORIZED_KEYS_FPATH = SSH_DIR + "/authorized_keys"

# Rsync
RSYNC_TIMEOUT = 300

REBOOT_TIMEOUT = 600
BIOS_TYPE_TIMEOUT = 420
CONFIG_CONTROLLER_TIMEOUT = 1200

# Prompts
LOGIN_PROMPT = "ogin:"
PASSWORD_PROMPT = "assword:"
PROMPT=".*\$ "

# Other
LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

# Surrounding return code with special characters to ensure
# other numbers (i.e. date-timestamp prompt) in the output
# are not mistaken for it
OPEN_MARKER ='['
CLOSE_MARKER =']'

RETURN_CODE_PATTERN=r"\{}".format(OPEN_MARKER) + "\d" + r"\{}".format(CLOSE_MARKER)
RETURN_CODE_CMD="echo {}$?{}".format(OPEN_MARKER, CLOSE_MARKER)