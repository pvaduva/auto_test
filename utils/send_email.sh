#!/bin/bash

# CGCS build server
#CGCS_BUILD_SRV=128.224.145.95
# Ottawa yow-tuxlab.wrs.com
#PXE=128.224.148.9
# Downers Grover  splats.wrs.com
#PXE=128.224.60.28
USER=`whoami`


email=chris.winnicki@windriver.com
TODAY=`date +%d%b%Y`
START=`date +%Y-%m-%d_%H%M%S`
OUT=/tmp/tc_result_$START.txt
echo $TODAY > $OUT
echo "Executing from: `uname -a`" >>$OUT

LOGPATH=$1
TCNAME=$2

#TARGET=20519
sudo=""
ssh="ssh -t "

##################################################################
# 
##################################################################
CheckIfError() {
    if [ $1 -gt 0 ]; then
        echo "Error"
        echo -e "Errors, exits status of last command $1\n" >> $OUT
        mail -s "Houston we have a problem: $TODAY" $email < ./$OUT
        exit 1
    else
        echo -e "No Errors, exits status of last command $1\n" >> $OUT
    fi
    }

##################################################################
# 
##################################################################
AllGoodMail() {
    END=`date +%Y-%m-%d_%H%M%S`
    mail -s "Houston we are all clear.  Started:$START  Ended:$END" $email < ./$OUT
    }

SendMail() {
    TC=$1
    R=$2
    END=`date +%Y-%m-%d_%H%M%S`
    mail -s "Test $TC returned $R" $email < ./$OUT
    }


# WRIFT_TARGET_LOGS={'20519': ['/home/revo/repos/Logs/cgcs/IronPass/CGCS_1Cont_2Comp/cgcs/sanity/stressCompute2
# CONSOLE_LOG=/home/revo/repos/Logs/cgcs/consolelogs


ls -rt $LOGPATH/WRIFT_exec_*|tail -n 1 |  xargs grep -q "PASS : 1"
#RESULT=`echo $?`
#echo $RESULT
SendMail $TCNAME $?

#find ./repos/Logs/cgcs/consolelogs/WRIFT_exec* -iname "*" -mmin -1 -exec grep "PASS : 1" {} \;
#SendMail $TCNAME $?


