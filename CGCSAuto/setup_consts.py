from pytest import mark

from consts.lab import Labs, NatBoxes
from consts.auth import Tenant


#########################################
# Start of Test session params          #
#########################################

# Possible values for LAB: Labs.IP_1_4, Labs.HP380, Labs.PV0, Labs.WCP_7_12, WCP_13, etc
# Please revert to LAB = Labs.NO_LAB after test completed.
LAB = Labs.NO_LAB

PRIMARY_TENANT = Tenant.TENANT2
NATBOX = NatBoxes.NAT_BOX_HW
BOOT_VMS = False
COLLECT_ALL = False
REPORT_ALL = False
DOMAIN = 'Storage'
USERSTORY = ''

#########################################
# End of Test Session Params            #
#########################################

# Test priority marker
P1 = mark.p1
P2 = mark.p2
P3 = mark.p3
