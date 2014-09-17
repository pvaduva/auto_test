#!/bin/bash

###################################################################
# Workaround scrip for adding OSDs to storage nodes due to a WASSP defect that
# splits variable with  dashes  in  name 
# 23jul14,ccw Initial version
###################################################################

export node="storage-0"
node=$1

DISKS=`system host-disk-list $node |  grep -E "[0-9a-z]{8}-.*sd[b-z]" | awk '{ print $2; }'`

for d in $DISKS
do
    echo "Adding drive $d as OSD to node $node"
    system host-stor-add $node $d
done

exit
