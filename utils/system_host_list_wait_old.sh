#!/bin/bash

export node="controller-1"
export expected="online"
node=$1
# expected=$2
state=`system host-list|grep $node |awk '{print $12'}`


while [  "$state"  !=  "$expected"  ]
do
    state=`system host-list|grep $node |awk '{print $12'}`
    sleep 5
    echo "$node expected state=$expected   :::   actual state=$state"   
    date
done

sleep 10

exit

while [ "$a" -le "$LIMIT" ]
do
 a=$(($a+1))

 if [ "$a" -gt 2 ]
 then
   break  # Skip entire rest of loop.
 fi

 echo -n "$a "
done
