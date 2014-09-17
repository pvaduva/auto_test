#!/bin/bash

###################################################################
# Workaround scrip for monitoring ceph health due to  WASSP defect
# with REPEATONFAIL command: http://jira.wrs.com/browse/WASSP-356
# 23jul14,ccw Initial version
###################################################################

# This scrip will block untill ceph health is HEALTH_WARN | HEALTH_OK
# Possible ceph healt states: HEALTH_ERR | HEALTH_WARN | HEALTH_OK

while [ 1 ]
do
    ceph -s --connect-timeout 5
    HEALTH=`ceph -s --connect-timeout 5 | grep health | awk '{print $2}'`
    echo "ceph expected state=HEALTH_WARN|HEALTH_OK|HEALTH_ERR  ::: actual state=$HEALTH"
    date
        if [  \( "$HEALTH"  ==  "HEALTH_WARN" \) -o \( "$HEALTH"  ==  "HEALTH_OK" \) -o \( "$HEALTH"  ==  "HEALTH_ERR" \) ]; then
            break
        fi
    sleep 5
done

