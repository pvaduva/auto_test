#!/bin/bash

email=$1
test_list=$2
release_version=$3
build_id=$4
TODAY=`date +%d%b%Y`
START=`date +%Y-%m-%d_%H%M%S`
OUT=/tmp/refstack_result_$START.txt
SUB="Refstack test result for test list - $test_list"
echo -e "\nTest date: " $TODAY > $OUT
echo -e "\nRefstack test list: " $test_list >> $OUT
echo -e "\nSystem Software Version: " $release_version >> $OUT
echo -e "\nSystem Load: " $build_id >> $OUT

cd /sandbox/AUTOMATION_LOGS/refstack

export LAST_LOG=`ls -td -- * | head -n 1`

echo -e "\nTest Results Location: http://128.224.150.21/auto_logs/refstack/$LAST_LOG" >> $OUT

echo -e "\n\nTest Summary " >> $OUT

head -10 $LAST_LOG/summary.txt >> $OUT

mail -s "$SUB" "$email" < $OUT

exit 0

