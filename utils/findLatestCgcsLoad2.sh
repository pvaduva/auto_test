#!/bin/bash


#BUILDSERVER=128.224.145.95
BUILDSERVER=128.224.145.117

BUILDSDIR=/localdisk/loadbuild/jenkins/CGCS_1.0_Unified_Daily_Build
#BUILDSDIR=/localdisk/loadbuild/jenkins/CGCS_GG_14.06_Host
#BUILDSDIR=/localdisk/loadbuild/jenkins/CGCS_GG_14.03_Host
#BUILDSDIR=/localdisk/loadbuild/jenkins/Titanium_Server_14.10_Host/
#/localdisk/loadbuild/jenkins/Titanium_Server_14.10_Guest/

if [ $1 ]; then
    BUILDSERVER=$1
else
BUILDSERVER=$BUILDSERVER
fi

if [ $2 ]; then
    BUILDSDIR=$2
else
BUILDSDIR=$BUILDSDIR
fi



ssh -q -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no `whoami`@$BUILDSERVER ls -l $BUILDSDIR/*|grep "latest_build "| awk '{print $11}'

#ssh -q -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no `whoami`@$BUILDSERVER ls -l $BUILDSDIR/*|grep latest_build | awk '{print $11}'
#ssh -q -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no `whoami`@$BUILDSERVER ls -rtd $BUILDSDIR/*/ | tail -n1
