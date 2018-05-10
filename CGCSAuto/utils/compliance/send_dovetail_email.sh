#!/bin/bash

email=$1
test_parameter=$2
release_version=$3
build_id=$4
TODAY=`date +%d%b%Y`
START=`date +%Y-%m-%d_%H%M%S`
OUT=/tmp/dovetail_result_$START.txt
SUB="Dovetail test result for $test_parameter"
echo -e "\nTest date: " $TODAY > $OUT
echo -e "\nTest Parameter: " $test_parameter >> $OUT
echo -e "\nSystem Software Version: " $release_version >> $OUT
echo -e "\nSystem Load: " $build_id >> $OUT

cd /sandbox/AUTOMATION_LOGS/refstack

export LAST_LOG=`ls -td -- * | head -n 1`

echo -e "\nTest Results Location: http://128.224.150.21/auto_logs/dovetail/$LAST_LOG" >> $OUT

echo -e "\n\nTest Summary \n" >> $OUT

grep -A100000 "Dovetail Report" $LAST_LOG/test_run.log >> $OUT

mail -s "$SUB" "$email" < $OUT

exit 0

