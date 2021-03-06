'''
constants.py - Handles constants for Horizon Automation

Copyright (c) 2015 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.


Contains constants for Horizon Automation.
'''

'''
modification history:
---------------------
26nov15,jbb  Initial file
'''

# CONSTANTS FOR HOSTS --------------------------------------------------------------------------------------------------

# CONSTANTS FOR LOCK HOST ###########################################################

# Lock label row # variables
# Each host has its own row number meaning its own 'lock host' id
CONST_LOCK_LABEL_FIRST_HALF = "#hosts__row_"
CONST_LOCK_LABEL_SECOND_HALF = "__action_lock"

# CONSTANTS FOR UNLOCK HOST ##########################################################
# Unlock label row # variables
# Each host has its own row number meaning its own 'unlock host' id
CONST_UNLOCK_LABEL_FIRST_HALF = "#hosts__row_"
CONST_UNLOCK_LABEL_SECOND_HALF = "__action_unlock"

# CONSTANTS FOR SWACT HOST ##########################################################
CONST_SWACT_LABEL_FIRST_HALF = "#hosts__row_"
CONST_SWACT_LABEL_SECOND_HALF = "__action_swact"

# These strings represent the unique values for the drop down button of each host
CONST_DROPDOWN_FIRST_HALF = "#hosts__row__"
CONST_DROPDOWN_SECOND_HALF = "> td:nth-child(8) > div:nth-child(1) > a:nth-child(2)"

# Check label personailty to determine if host is either active or standby
CONST_CHECK_PERSONALITY_FIRST_HALF = "#hosts__row__"
CONST_CHECK_PERSONALITY_SECOND_HALF = " > td:nth-child(2)"

# Check label Admin State to ensure host is either locked or unlocked
CONST_CHECK_ADMIN_STATE_FIRST_HALF = "#hosts__row__"
CONST_CHECK_ADMIN_STATE_SECOND_HALF = " > td:nth-child(3)"

HOST_CHECK_AVAIL_STATE_FIST_HALF = "#hosts__row__"
HOST_CHECK_AVAIL_STATE_SECOND_HALF = "> td:nth-child(5)"

HOST_CHECK_STATUS_FIRST_HALF = "#hosts__row__"
HOST_CHECK_STATUS_SECOND_HALF = "> td:nth-child(7)"

HOST_INTERFACE_TAB = "?tab=inventory_details__interfaces"
HOST_PROCESSOR_TAB = "?tab=inventory_details__cpufunctions"
HOST_MEMORY_TAB = "?tab=inventory_details__memorys"
HOST_STORAGE_TAB = "?tab=inventory_details__storages"
HOST_STORAGE_LOCAL_VOLUME_GROUP_PARAM_TAB = "?tab=lvg_details__lvg_params"

HOST_INTERFACE_EDIT_FIRST_HALF = "interfaces__row_"
HOST_INTERFACE_EDIT_SECOND_HALF = "__action_update"

# END CONSTANTS FOR HOSTS ----------------------------------------------------------------------------------------------


MOD_QUOTA_DROPDOWN_FIRST_HALF = "#tenants__row__"
MOD_QUOTA_DROPDOWN_SECOND_HALF = "> td:nth-child(6) > div:nth-child(1) > a:nth-child(2)"

MOD_QUOTA_MODIFY_FIRST_HALF = "tenants__row_"
MOD_QUOTA_MODIFY_SECOND_HALF = "__action_quotas"


FLAVOR_EXTRA_SPEC_TAB= "?tab=flavor_details__extra_specs"

FLAVOR_EXTRA_SPEC_TYPE_CPU_POLICY = "CPU Policy"
FLAVOR_EXTRA_SPEC_TYPE_CPU_POLICY_DEDICATED = "Dedicated"

FLAVOR_EXTRA_SPEC_TYPE_MEMORY_PAGE_SIZE = "Memory Page Size"
FLAVOR_EXTRA_SPEC_TYPE_MEMORY_PAGE_SIZE_2048 = "2048"

FLAVOR_EXTRA_SPEC_TYPE_VCPU_MODEL = "VCPU Model"
FLAVOR_EXTRA_SPEC_TYPE_VCPU_MODEL_INTEL_9XX = "Intel Core i7 9xx (Nehalem Class Core i7)"

ROUTER_INTERFACE_TAB = "?tab=router_details__interfaces"

ROUTER_EDIT_INTERFACE_DROPDOWN = "a.btn:nth-child(2)"
ROUTER_EDIT_INTERFACE_FIRST_HALF = "Routers__row_"
ROUTER_EDIT_INTERFACE_SECOND_HALF = "__action_update"
