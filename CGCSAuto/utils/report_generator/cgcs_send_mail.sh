#!/bin/bash
# cgcs_send_mail.sh - script to send report email 
#
# Copyright (c) 2014-2015 Wind River Systems, Inc.
#
# The right to copy, distribute, modify or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.
#
# modification history
# --------------------
# 25mar15,amf  adding header 

#source "${WASSP_HOME}/wassp-nest/nightly/scripts/common_v2.cfg"

if [[ -z $1 ]] ; then
    CGCS_LAB="Ottawa_ironpass_1-4"
else
    CGCS_LAB=$1
fi

CGCS_LOAD=$2
EXECUTION_DATE=
PASSRATE=0
totalnum=1
passnum=0
REPORT_SERVER="report.wrs.com"
CORP="corp.ad.wrs.com"

if [[ -z $4 ]] ; then
    HOST_IP=$HOST
else
    HOST_IP=$4
fi

if [[ -z $5 ]] ; then
    REPORT_TITLE="TiS Automated Test Report"
else
    REPORT_TITLE=$5
fi

EMAILMESSAGE="/tmp/cgcs_emailmessage.html"

rm -f ${EMAILMESSAGE}

EMAIL_LIST="ENG-TiS@$CORP,Doina.Lepadatu@$CORP,Ed.Illidge@$CORP,Mark.Faig@$CORP"
PROJECT=CGCS+2.0
LOG_SUBFOLDER=cgcs_sanity
if [[ -z $6 ]] ; then
    MONGO_TAGS="sanity"
else
    MONGO_TAGS=$6
fi

if [[ -z $7 ]] ; then
    PLATFORM="IronPass"
else
    PLATFORM=$7
fi

#Get WASSP version
WASSP_VERSION_FILE=$WASSP_BASE/classes/versions.py
WASSP_VERSION_LINE=`cat $WASSP_VERSION_FILE | grep "MAIN_VERSION ="`
WASSP_VERSION=`echo ${WASSP_VERSION_LINE:16:8} |sed 's/,\ /./g'`
echo WASSP_VERSION=$WASSP_VERSION

TEMPMESSAGE="/tmp/emailmessage.tmp"
# remove ^M characters
#tr -d '\r' < $JSON_FILE > $TEMPMESSAGE && mv $TEMPMESSAGE $JSON_FILE

# Locate the Build name for this run
QUERY_DATE=`date +%Y-%m-%d`

#Get the total test runs from the MongoDB report database
wget "http://report.wrs.com/reportgenerator/rawresults/245faa5c-816d-11e4-a2ea-90b11c4fbb02/?main-TOTAL_FORMS=3&main-INITIAL_FORMS=3&main-MAX_NUM_FORMS=20&main-0-filter=test+date&main-0-dateStart=$QUERY_DATE&main-0-dateEnd=$QUERY_DATE&main-1-filter=project&main-1-options=CGCS+2.0&main-2-filter=tags&main-2-options=${MONGO_TAGS}&mainform-submit=Search&lastRunFilter=on" -O /tmp/report.html

TOTAL=`${WASSP_HOME}/wassp-nest/nightly/scripts/parse_key_value.py  -f /tmp/report.html -k Total:`
echo Total: ${TOTAL//[,]/}

#Get the PASSED test runs from the MongoDB report database
PASS_STRING=`${WASSP_HOME}/wassp-nest/nightly/scripts/parse_key_value.py  -f /tmp/report.html -k Passed:`
PASS=`echo ${PASS_STRING}|awk '{print $1}'`
PASSRATE=`echo ${PASS_STRING}|awk '{print $2}'`
echo "PASS: ${PASS}"
echo "PASSRATE: ${PASSRATE}"

#Get the FAILED test runs from the MongoDB report database
EXECFAIL=`${WASSP_HOME}/wassp-nest/nightly/scripts/parse_key_value.py  -f /tmp/report.html -k Failed:`
EXECFAIL=`echo ${EXECFAIL}|awk '{print $1}'`
echo Exec Fail: ${EXECFAIL}

#Calculate passrate
totalnum=$TOTAL
passnum=$PASS
if (( totalnum == 0 )) ; then
    echo "Database query failed"
    STATUS='Unknown'
    PASSRATE='<Unknown. Database query failed>'
else
    PASSRATE=$((100*${passnum}/${totalnum}))

    echo totalnum: $totalnum
    echo passnum: $passnum
    echo PASSRATE: $PASSRATE

    if (( $PASSRATE > 99 )) ; then
        STATUS='GREEN'
        export SANITY_STATUS="GREEN"
    elif (( $PASSRATE > 79 )) ; then
        STATUS='YELLOW'
    else
        STATUS='RED'
    fi
fi

#Generate email list
if [[ -z $3 ]] ; then
    echo "Send report to list of members."
elif [[ $3 = "sendall" ]] ; then
    echo "Send report to list of members."
elif [[ $3 = "nomail" ]] ; then
    echo "Avoid sending email, exit!"
    exit
else
    echo "only send to: $3"
    EMAIL_LIST="$3"
fi

# Construct the e-mail body

SUBJECT="$REPORT_TITLE [${CGCS_LOAD}] - ${STATUS}"
MONGODBLINK="<a href='http://report.wrs.com/reportgenerator/rawresults/245faa5c-816d-11e4-a2ea-90b11c4fbb02/?main-TOTAL_FORMS=5&main-INITIAL_FORMS=5&main-MAX_NUM_FORMS=20&main-0-filter=test+date&main-0-dateStart=$QUERY_DATE&main-0-dateEnd=$QUERY_DATE&main-1-filter=lab&main-1-options=${CGCS_LAB}&main-2-filter=project&main-2-options=CGCS+2.0&main-3-filter=tags&main-3-options=${MONGO_TAGS}&main-4-filter=platform&main-4-options=${PLATFORM}&mainform-submit=Search&lastRunFilter=on'>${CGCS_LAB}</a>"

# Create trend chart
TREND_CHART_FILE=$WASSP_LOGS_ROOT/cgcs/trend_chart.png
TREND_CHART_FILE=$WASSP_LOGS_ROOT/cgcs/trend_chart.png
TREND_CHART_LINK=http://$HOST_IP$WASSP_LOGS_ROOT/cgcs/trend_chart.png
echo -e $TREND_CHART_LINK
TODAY_DATE=`date +%Y-%m-%d`
SIX_DAYS_AGO=`date --date="7 days ago" +%Y-%m-%d`
echo '/usr/bin/wget "http://yow-ssp2-lx.wrs.com/smartTool/genTrendChart/genTrendChart.php?project=$PROJECT&tags=iot&startdate=$SEVEN_DAYS_AGO&enddate=$TODAY_DATE" -O $TREND_CHART_FILE'
echo '/usr/bin/wget "http://yow-ssp2-lx.wrs.com/smartTool/genTrendChart/genTrendChart.php?project=$PROJECT&tags=iot&startdate=$SEVEN_DAYS_AGO&enddate=$TODAY_DATE" -O $TREND_CHART_FILE'
/usr/bin/wget -4 "http://yow-ssp2-lx.wrs.com/smartTool/genTrendChart/genTrendChart.php?project=$PROJECT&tags=$MONGO_TAGS&startdate=$SIX_DAYS_AGO&enddate=$TODAY_DATE" -O $TREND_CHART_FILE
MONGODBLINK_TREND_CHART="<a href=http://$REPORT_SERVER/reportgenerator/trendData/aaaaaaaa-bbbb-cccc-eeee-ffffffffffff/?main-TOTAL_FORMS=3&main-INITIAL_FORMS=3&main-MAX_NUM_FORMS=20&main-0-filter=test+date&main-0-dateStart=$SIX_DAYS_AGO&main-0-dateEnd=$TODAY_DATE&main-1-filter=project&main-1-options=$PROJECT&main-2-filter=tags&main-2-options=$MONGO_TAGS&mainform-submit=Search><img src=cid:trend_chart.png></a><br>"

# Fill in the e-mail body
echo -e '<basefont face="arial" size="2">' > $EMAILMESSAGE
#echo -e '<head><style>body {background-image:url("http://$REPORT_SERVER/buildarea1/wassp-repos/wassp/host/tools/report/templates/wassp2.png");background-repeat:no-repeat;background-position:right top;}' >> $EMAILMESSAGE

echo -e "<ul>Lab: ${CGCS_LAB}<br>" >> $EMAILMESSAGE
echo -e "<b>Load:</b> ${CGCS_LOAD}<br>" >> $EMAILMESSAGE
echo -e "<b>Node Config:</b> 2 controllers + 2 computes<br>" >> $EMAILMESSAGE
echo -e "<b>Execution date:</b> ${QUERY_DATE}<br>" >> $EMAILMESSAGE
echo -e "<br>" >> $EMAILMESSAGE
echo -e "<b>Overall Status:</b> $STATUS<br>" >> $EMAILMESSAGE
echo -e "WASSP Link: $MONGODBLINK<br>" >> $EMAILMESSAGE
echo -e "<br>" >> $EMAILMESSAGE
echo -e "Automated Test Results Summary:<br>" >> $EMAILMESSAGE
echo -e "<br>" >> $EMAILMESSAGE
if (( totalnum == 0 )) ; then
    echo "Error. Database query timed out. Please check the link above. <br>" >> $EMAILMESSAGE
else
    echo -e "<b>Passed:</b> ${PASS//[,]/} (${PASSRATE}%) <br>" >> $EMAILMESSAGE
    echo -e "<b>Failed:</b> ${EXECFAIL//[,]/}<br>" >> $EMAILMESSAGE
    echo -e "<b>Total:</b> ${TOTAL//[,]/}<br>" >> $EMAILMESSAGE
fi

#export EMAIL_OPTIONS="-a "$TREND_CHART_FILE""
echo -e "<br>" >> $EMAILMESSAGE
echo -e "<br>" >> $EMAILMESSAGE
echo -e "<b>Trend Chart:</b><br>" >> $EMAILMESSAGE
echo -e "$MONGODBLINK_TREND_CHART" >> $EMAILMESSAGE
echo -e "</ul><br>" >> $EMAILMESSAGE


# remove ^M characters & send an e-mail
tr -d '\r' < $EMAILMESSAGE > $TEMPMESSAGE && mv $TEMPMESSAGE $EMAILMESSAGE

#/usr/bin/mutt -e "set from="svc-cgcsauto@windriver.com"" -e "set realname="svc-cgcsauto"" -e "set content_type=text/html" $EMAIL_OPTIONS -s "$SUBJECT" -- "$EMAIL_LIST" < "$EMAILMESSAGE"
/usr/bin/mutt -e "set from="svc-cgcsauto@windriver.com"" -e "set realname="svc-cgcsauto"" -e "set content_type=text/html"  -s "$SUBJECT" -- "$EMAIL_LIST" < "$EMAILMESSAGE"

