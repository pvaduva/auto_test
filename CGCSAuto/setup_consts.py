from pytest import mark
from os.path import expanduser
from consts.lab import Labs, NatBox
from consts.auth import Tenant

#########################################
# Start of Test session params          #
#########################################

LAB = Labs.R720_3_7
#LAB = Labs.IP_1_4
PRIMARY_TENANT = Tenant.TENANT_2
NATBOX = NatBox.NAT_BOX_HW
BOOT_VMS = False

#########################################
# End of Test Session Params            #
#########################################

# Paths to save/create files per lab
LAB_NAME = LAB['short_name']
LOG_DIR = expanduser("~") + "/AUTOMATION_LOGS/" + LAB_NAME
TEMP_DIR = LOG_DIR + '/tmp_files'
KEYFILE_NAME = 'keyfile_{}.pem'.format(LAB_NAME)
KEYFILE_PATH = '/home/wrsroot/.ssh/' + KEYFILE_NAME

# Test priority marker
P1 = mark.p1
P2 = mark.p2
P3 = mark.p3