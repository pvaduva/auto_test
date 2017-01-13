#!/bin/bash
# cgcs_save_load.sh - script to save the GREEN builds and clean up old ones
#
# Copyright (c) 2014-2015 Wind River Systems, Inc.
#
# The right to copy, distribute, modify or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.
#
# modification history
# --------------------
# 25jan16,amf  creation

CGCS_LOAD=$1
DIRECTORY=/folk/cgts/sanity-loads/${CGCS_LOAD}
BUILDSERVER=$3
EXECUTOR=${USER}

if [ -z "$1" ]; then
    echo "Description: This script is used to backup and save GREEN loads to the following folder:"
    echo "/folk/cgts/sanity-loads"
    echo "The following environment variables must be set:"
    echo "    export SANITY_STATUS=GREEN"
    echo "    export EXECUTOR=svc-cgcsauto"
    echo "    export BUILDSERVER=yow-cgts3-lx"
    echo "Usage: ./cgcs_save_loads.sh [BuildId]"
    echo "Example: ./cgcs_save_loads.sh 2016-01-22_22-04-35"
    exit 1
fi

if [ -z "$3" ]; then
    BUILDSERVER=yow-cgts3-lx
fi
# First check if the build has already been saved
if [ -d $DIRECTORY ] ; then
    echo 'Build already saved at:' $DIRECTORY
    echo 'Exiting!'
    exit
fi

# Check if this is a green build to be saved
SANITY_STATUS=`cat $2`
if (( ${SANITY_STATUS} == 'GREEN' )) ; then

    mkdir -p /folk/cgts/sanity-loads/${CGCS_LOAD}
    sshpass -p ")OKM0okm" rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' ${EXECUTOR}@$BUILDSERVER:/localdisk/loadbuild/jenkins/CGCS_3.0_Centos_Build/${CGCS_LOAD}/export/bootimage.iso /folk/cgts/sanity-loads/${CGCS_LOAD}/
    sshpass -p ")OKM0okm" rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' ${EXECUTOR}@$BUILDSERVER:/localdisk/loadbuild/jenkins/CGCS_3.0_Guest_Daily_Build/cgcs-guest.img /folk/cgts/sanity-loads/${CGCS_LOAD}/
    rm -rf /folk/cgts/sanity-loads/cgcs-guest.img
    ln -s /folk/cgts/sanity-loads/${CGCS_LOAD}/cgcs-guest.img /folk/cgts/sanity-loads/cgcs-guest.img
    rm -rf /folk/cgts/sanity-loads/latest_bootimage.iso
    ln -s /folk/cgts/sanity-loads/${CGCS_LOAD}/bootimage.iso /folk/cgts/sanity-loads/latest_bootimage.iso
else
    echo "Sanity was not GREEN. No builds saved."
fi

