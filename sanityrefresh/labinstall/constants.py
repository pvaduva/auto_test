#!/usr/bin/env python3.4

# Directory and file paths/names
HOST_OS = ["centos", "wrlinux"]
DEFAULT_HOST_OS = "centos"
INSTALL_MODE = ["legacy", "uefi"]
DEFAULT_INSTALL_MODE = "legacy"
DEFAULT_REL = "latest_dev_stream"
DEFAULT_BLD = "latest_build"
DEFAULT_WKSPCE = "/localdisk/loadbuild/jenkins"
DEFAULT_GUEST = "cgcs-guest.img"
NODE_INFO_DIR = "node_info"
LAB_SETTINGS_DIR = "lab_settings"
LATEST_BUILD_DIR = "latest_build"
EXPORT_LAB_REL_PATH = "export/lab"
LAB_YOW_REL_PATH = EXPORT_LAB_REL_PATH + "/yow"
LAB_SCRIPTS_REL_PATH = EXPORT_LAB_REL_PATH + "/scripts"
CENTOS_LAB_REL_PATH = "std/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab"
HEAT_TEMPLATES_PATH = "std/repo/addons/wr-cgcs/layers/cgcs/openstack/recipes-base/python-heat/python-heat/templates"

SYSTEM_CFG_FILENAME = "system_config"
WRL_CFGFILE_LIST = ["system_config", "TiS_config.ini_wrl", "TiS_config.ini"]
CENTOS_CFGFILE_LIST = ["TiS_config.ini_centos", "TiS_config.ini"]
# TODO: Same todo as above, where the bulk add filename might be different
BULKCFG_LIST = ["hosts_bulk_add.xml", "hosts.xml"]
BULK_CFG_FILENAME = "hosts_bulk_add.xml"
LAB_SETUP_SCRIPT = "lab_setup.sh"
LAB_SETUP_CFG_FILENAME = "lab_setup.conf"
CUSTOM_LAB_SETTINGS_FILENAME = "settings.ini"
CENTOS_GUEST = DEFAULT_WKSPCE + "/CGCS_4.0_Centos_Guest_Build"

LIC_FILENAME = "license.lic"
LICENSE_FILEPATH = "-L /folk/cgts/lab/TiS17-full.lic"
SFP_LICENSE_FILEPATH = "-L /folk/cgts/lab/TiS17-CPE-full.lic"
WRSROOT_ETC_PROFILE = "/etc/profile.d/custom.sh"
WRSROOT_ETC_PROFILE_LEGACY = "/etc/profile"
TUXLAB_BARCODES_DIR = "/export/pxeboot/vlm-boards"
CENTOS_INSTALL_REL_PATH = "export/dist/isolinux/"
RPM_INSTALL_REL_PATH = "export/RPM_INSTALL"
WRSROOT_HOME_DIR = "/home/wrsroot/"
WRSROOT_PATCHES_DIR = WRSROOT_HOME_DIR + "/patches"
WRSROOT_IMAGES_DIR = WRSROOT_HOME_DIR + "/images"
WRSROOT_HEAT_DIR = WRSROOT_HOME_DIR + "/heat"
JIRA_LOGS_DIR = "/folk/cgts/logs"
CERTIFICATE_FILE_PATH = "/folk/cgts/lab/server-with-key-with-passwd.pem"
CERTIFICATE_FILE_NAME = "server-with-key.pem"
BANNER_DEST = '/opt/banner'
BANNER_SRC = WRSROOT_HOME_DIR + '/banner'

# Cumulus TiS on TiS setup
#CUMULUS_SERVER_IP="128.224.151.50"
CUMULUS_SERVER="cumulus.wrs.com"
BOOT_IMAGE_ISO = "bootimage.iso"
TIS_IMAGE = "tis.img"
BOOT_IMAGE_ISO_SIZE = 5
BOOT_IMAGE_ISO_PATH = "export/" + BOOT_IMAGE_ISO
BLD_TIS_IMAGE_PATH = "export/" + TIS_IMAGE
BOOT_IMAGE_ISO_TMP_PATH = "/tmp/" + BOOT_IMAGE_ISO
CUMULUS_CLEANUP_SCRIPT = "cumulus_cleanup.sh"
CUMULUS_SETUP_SCRIPT = "cumulus_setup.sh"
CUMULUS_SETUP_CFG_FILENAME = "cumulus_setup.conf"
CUMULUS_TMP_TIS_IMAGE_PATH = "/localdisk/designer"

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
INSTALL_TIMEOUTS = [2400, 2400, 2400]  # Some labs take longer that 2100 seconds to install; increased to 2400.
SERIAL_KICKSTART_CONTROLLER_INSTALL = "Serial Kickstart Controller Install"
MAX_BOOT_MENU_LINES = 15

NIC_INTERFACE = "eth0"
NIC_INTERFACE_CENTOS = "enp10s0f0"
HOST_ROUTING_PREFIX = "/23"
HOST_GATEWAY="128.224.150.1"

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
BLD_SERVERS = ["yow-cgts1-lx", "yow-cgts2-lx", "yow-cgts3-lx", "yow-cgts4-lx"]
DEFAULT_BLD_SERVER = "yow-cgts4-lx"
TUXLAB_SERVERS = ["yow-tuxlab", "yow-tuxlab2"]
DEFAULT_TUXLAB_SERVER = "yow-tuxlab2"
DNS_SERVER ="8.8.8.8"
HOST_EXT = ".wrs.com"

# wrsroot user
WRSROOT_USERNAME = "wrsroot"
WRSROOT_DEFAULT_PASSWORD = WRSROOT_USERNAME
WRSROOT_PASSWORD = "Li69nux*"

#Telnet expect
TELNET_EXPECT_TIMEOUT = 3600
BOOT_MENU_TIMEOUT = 120
MAX_SEARCH_ATTEMPTS =35 
MAX_LOGIN_ATTEMPTS = 5

#Telnet Console login
TELNET_CONSOLE_USERNAME = "admin"
TELNET_CONSOLE_PASSWORD = "admin"

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
REBOOT_TIMEOUT = 7200
BIOS_TYPE_TIMEOUT = 1800
CONFIG_CONTROLLER_TIMEOUT = 1800
LAB_SETUP_TIMEOUT = 3600
WIPE_DISK_TIMEOUT = 30
PING_TIMEOUT = 60
TIMEOUT_BUFFER = 2

# Prompts
LOGIN_PROMPT = "ogin:"
PASSWORD_PROMPT = "assword:"
PROMPT = ".*\$ ?"

# Stacks
ADMIN_YAML = "lab_setup-admin-resources.yaml"
TENANT1_YAML = "lab_setup-tenant1-resources.yaml"
TENANT2_YAML = "lab_setup-tenant2-resources.yaml"
YAML = [ADMIN_YAML, TENANT1_YAML, TENANT2_YAML]
STACK_CREATE_SCRIPT = "create_resource_stacks.sh"
RESOURCE_STACKS_SCRIPT = "launch_resource_stacks.sh"
STACK_LAUNCH_SCRIPT = "launch_stacks.sh"
HEAT_RESOURCES = ".heat_resources"

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


# lab type
LAB_TYPES = ['regular_lab', 'storage_lab', 'cpe_lab', 'tis_on_tis', 'tis_on_tis_storage', 'simplex']

# tmp install vars path
INSTALL_VARS_TMP_PATH = "/tmp"
INSTALL_VARS_FILE_EXT = "_install_vars.ini"
INSTALL_EXECUTED_STEPS_FILE_EXT = "_executed_steps.txt"

# Resume install message
RESUME_INSTALL_MSG = 'Please correct error and re-run auto-install with ' \
                     '--lab=<lab name>  and ' \
                     '--continue options to continue install'
