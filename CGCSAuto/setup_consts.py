from pytest import mark

from consts.lab import Labs, NatBoxes
from consts.auth import Tenant


#########################################
# Start of Test session params          #
#########################################

LAB = Labs.WCP_7_12
PRIMARY_TENANT = Tenant.TENANT_2
NATBOX = NatBoxes.NAT_BOX_HW
BOOT_VMS = False
COLLECT_ALL = False
REPORT_ALL = False
DOMAIN = 'UNKNOWN'
USERSTORY = ''

#########################################
# End of Test Session Params            #
#########################################

# Test priority marker
P1 = mark.p1
P2 = mark.p2
P3 = mark.p3
