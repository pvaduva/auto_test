#!/usr/bin/env python

# build servers, i.e. yow-cgts1-lx, yow-cgts2-lx, yow-cgts3-lx
BUILD_SERVERS = ["128.224.145.95", "128.224.145.117", "128.224.145.134"]

# flag whether to use new CLI commands or deprecated ones
# e.g. /usr/bin/keystone tenant-list vs. openstack project list
USE_NEWCMDS=True

# Test server
TEST_HOSTNAME = "128.224.150.21"
TEST_USERNAME = "svc-cgcsauto"
TEST_PASSWORD = ")OKM0okm"

# VLM
VLM = "/folk/vlm/commandline/vlmTool"

# scp user
SCP_USERNAME = "svc-cgcsauto"
SCP_PASSWORD = ")OKM0okm"
LOG_LOCATION = "/folk/cgts/logs"

# pxssh connection arguments
HOSTNAME = "10.10.10.3"
USERNAME = "wrsroot"
PASSWORD = "li69nux"

# BIOS options
F10 = "^[[21~"
F6 = "^[[17~"
F2 = "^[[12~"
UP = "^[[A"
DOWN = "^[[B"
RIGHT = "^[[C"
LEFT = "^[[D"

# NAT box credentials
NAT_HOSTNAME = "128.224.150.11"
NAT_USERNAME = "cgcs"
NAT_PASSWORD = "li69nux"

# pxssh connection timeout
TIMEOUT = 6

# pxssh search window size
SEARCHWINSIZE = 50

# pxssh echo commands
ECHO=False

# pxssh shell prompt
INITIAL_PROMPT="\$ "
PROMPT=".*\$ "

# pxssh default location for log file
LOGFILE_BASE = "/tmp/"
LOGFILE = "temp.txt"

# timeout for the sudo collect all command
COLLECT_TIMEOUT = 300

# max time to wait for swact to complete
SWACT_MAXTIME = 85 

# response to match to detect when the CLI returns errors
# it will report the error message as well
ERROR = "(ERROR.*)\n"

# host availability states
STATE = ["available", "online", "offline", "failed", "intest"]

# match an arbitary hostname, e.g. controller-1, compute-0, storage-12
HOSTNAME_MATCH = "(\w+-\d+)"

# match a hostname, only from a table
# | 1  | controller-0 | controller  | unlocked       | enabled     | available  
# e.g. returns controller-0
HOSTNAME_MATCH_TBL = "(?<=\|\s)\w+-\d+"

# extract a controller hostname only from a table
# | 1  | controller-0 | controller  | unlocked       | enabled     | available  
# e.g. returns controller-0
CONT_HOSTNAME_MATCH_TBL = "(?<=\|\s)controller-\d+"

# extract a compute hostname only from a table
# | 1  | compute-0 | compute | unlocked       | enabled     | available  
# e.g. returns compute-0
COMP_HOSTNAME_MATCH_TBL = "(?<=\|\s)compute-\d+"

# extract a storage hostname only from a table 
# | 1  | storage-0 | storage | unlocked       | enabled     | available  
# e.g. returns storage-0
STOR_HOSTNAME_MATCH_TBL = "(?<=\|\s)storage-\d+"

# inactive controller response to source /etc/nova/openrc
# -sh: /opt/platform/.keyring/.CREDENTIAL: No such file or directory
INACTIVE_CONT_RESP = "No such file or directory"

# response returned when we try to execute a command but we're not active 
# You must provide a username via either --os-username or via env[OS_USERNAME]
INACTIVE_CONT_RESP_CMD = "You must provide a username"

# checks for empty table 
EMPTY_TABLE = "\+\r\n\+"

# checks for non-empty table
# this one doesn't seem to work
NON_EMPTY_TABLE = "\+\r\n.*\r\n\+.*\r\n\|"

# checks for alarms in the alarms table
# this matches alarm UUIDs, e.g. 491462fe-a261-4af2-8669-606555df98ee
# can we do better than this??  position dependent the way it is written.
#ALARMS_MATCH = "(?<=\|\s)([a-zA-Z0-9-]*)(?= \|\s\d)"
#ALARMS_MATCH = "([0-9a-f-]{32,36})"
#UUID = "([0-9a-f-]{32,36})"
UUID = "(?<=\r\n\|\s)([0-9a-f-]{32,36})"
ID = "(?<=\r\n\|\s)([0-9a-f-]{32,36})"

# Match and extract a nova flavor ID from the nova flavor-list table. Flavor IDs 
# look like UUID, numeric value or alphabetic.  Has a flaw in that it retrieves
# ID from the # heading which is not a flavor ID so you must consume it first
FLAVOR_ID = "(?<=\r\n\|\s)([0-9a-zA-Z-]{1,36})"

# this extracts a project UUID from a table, e.g.
# | 690d4635663a46aba6d4c1e6a3a9efc7 | admin    |
USER_ID = "([0-9a-f]{32})"

# checks for flavors in the flavors table
FLAVOR_MATCH = "(?<=\|\s)([0-9a-f-]{1,36})"

# extract neutron providernet-list vxlan interface names only, e.g. group0-ext0
# can we do better than this??  position dependent the way it is written.
VXLAN_NAME = "(?<=\|\s)([\w-]+)(?=\s*\|\svxlan)" 

# extract neutron providernet-list vlan interfaces names only, e.g. group0-data1
# can we do better than this??  position dependent the way it is written.
VLAN_NAME = "(?<=\|\s)([\w-]+)(?=\s*\|\svlan)"

# extract neutron providernet-list flat interfaces names only, e.g. group0-data1
# can we do better than this??  position dependent the way it is written.
FLAT_NAME = "(?<=\|\s)([\w-]+)(?=\s*\|\sflat)"

# checks system host-list for available hosts and returns hostname
AVAIL = "(\w+-\d+)(?=.*available)"

# checks system host-list for available hosts and returns hostname
FAIL = "(\w+-\d+)(?=.*failed)"

# checks system host-list for available hosts and returns hostname
INTEST = "(\w+-\d+)(?=.*intest)"

# checks system host-list for available hosts and returns hostname
OFFLINE = "(\w+-\d+)(?=.*offline)"

# checks system host-list for available hosts and returns hostname
ONLINE = "(\w+-\d+)(?=.*offline)"

# matches the tarball name, e.g. ALL_NODES_20150731.160116.tar.tgz
# controller-0: Compressing Tarball ..: /scratch/ALL_NODES_20150731.160116.tar.tgz
TARBALL_NAME = "(?<=Compressing Tarball ..:\s)(.+)"

# extracts personality from system host-list
CONT_PERSONALITY = "personality\s*\|\s(controller)"
COMP_PERSONALITY = "personality\s*\|\s(compute)"
STOR_PERSONALITY = "personality\s*\|\s(storage)"

# extracts down services
# 3 groups: service name, node, state
DOWN_NOVASERVICE = "(nova-\w+)\s*\|\s(\w+-\d+).*(down).*\n" 

# get vm by name
# works on nova list
# input: | 55ac9f6d-192c-4b7b-83f9-f5c8408c2700 | tenant1-avp1     
# output: on the data above, it would extract tenant1-avp1
VM_NAME = "(?<=\r\n\|\s[0-9a-f-]{36}\s\|\s)([0-9a-zA-Z-]+)"

# get the host that the vm is on
# works on the nova show <vm_id> command
# input: | OS-EXT-SRV-ATTR:host                 | compute-0               
# output: compute-0
# must grab conn.match.group(1) with this regex 
VM_HOST = "(?<=host)\s*\|\s(\w+\-\d+)"

# get the state of the VM
# works on the nvoa show <vm_id> command
# input: | OS-EXT-STS:vm_state                  | active                   
# output: active
# must grab conn.match.group(1) with this regex
VM_STATE= "(?<=host)\s*\|\s(\w+)"

