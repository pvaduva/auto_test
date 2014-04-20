#!/bin/bash


BUILDSERVER=128.224.145.95
#BUILDSERVER=128.224.145.117
#BUILDSDIR=/localdisk/loadbuild/jenkins/CGCS_1.0_Unified_Daily_Build
BUILDSDIR=/localdisk/loadbuild/jenkins/CGCS_1.0_Guest_Daily_Build/


ssh -q -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no cwinnick@$BUILDSERVER ls -l $BUILDSDIR/*|grep latest_build | awk '{print $11}'

IMAGEPATH=$LATEST/export/cgcs-guest.img

#ssh -q -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no cwinnick@$BUILDSERVER ls -rtd $BUILDSDIR/*/ | tail -n1
