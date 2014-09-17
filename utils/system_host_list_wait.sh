#!/bin/bash

usage="$(basename "$0") [-h] [-n node] [-s state] -- program to test expected availability state of a node.  This program exits when expected state is found.

where:
    -h  show this help text
    -n  sets the node under test
    -s  sets the expected state
    
    example:
    $(basename "$0" ) -n controller-1 -s available"

if [  "$#" -lt 2 ]; then
    echo "${usage}" >&2
    exit    
fi
    
while getopts 'h:n:s:' option; do
  case "$option" in
    h) echo "$usage"
       exit
       ;;
    s) state_expected=$OPTARG
       ;;
    :) printf "missing argument for -%s\n" "$OPTARG" >&2
       echo "$usage" >&2
       exit 1
       ;;
   n) node=$OPTARG
       ;;
   :) printf "missing argument for -%s\n" "$OPTARG" >&2
       echo "$usage" >&2
       exit 1
       ;;
   \?) printf "illegal option: -%s\n" "$OPTARG" >&2
       echo "$usage" >&2
       exit 1
       ;;
  esac
 # shift $((OPTIND - 1))
done

while [  "$state_actual"  !=  "$state_expected"  ]
do
    state_actual=`system host-list|grep $node |awk '{print $12}'`
    echo "$node expected state=$state_expected   :::   actual state=$state_actual"   
    date
    sleep 5
done

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
