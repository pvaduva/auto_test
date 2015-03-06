#!/bin/bash

node=${1}
state_expected=${2}

echo "starting lock/unlock test of host $node"
date

system host-lock $node
sleep 5
system host-unlock $node
begin=$(date +%s)

while [  "$state_actual"  !=  "$state_expected"  ]
do
    state_actual=`system host-list|grep $node |awk '{print $12}'`
    echo "$node expected state=$state_expected   :::   actual state=$state_actual"   
    date
    sleep 3
done

end=$(date +%s)

let out=$end-$begin+5

echo "total time to unlock $node is: $out"

