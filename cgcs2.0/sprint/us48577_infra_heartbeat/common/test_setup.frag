# This test case assumes that the infrastructure network has been created
# by the previous test

# Set the variables we need
SET OAM_IP       $env.NODE.target.Boot.oamAddrA
SET CONT_USER    $env.NODE.target.Connect.ssh_user 
SET CONT_PASSWD  $env.NODE.target.Connect.ssh_pass 
SET CISCO_IP     $env.NODE.target.Infra.ciscoIP
SET CISCO_USER   $env.NODE.target.Infra.ciscoUser 
SET CISCO_PASSWD $env.NODE.target.Infra.ciscoPasswd 

# Check we are unlocked-enabled-available at the start of test
Con1SSH TYPE system host-list\n
Con1SSH LOOKFOR \| controller-0 \| controller(\s)*\| unlocked(\s)*\| enabled(\s)*\| available(\s)*\|
Con1SSH LOOKFOR \| controller-1 \| controller(\s)*\| unlocked(\s)*\| enabled(\s)*\| available(\s)*\|
Con1SSH LOOKFOR \| compute-0(\s)*\| compute(\s)*\| unlocked(\s)*\| enabled(\s)*\| available(\s)*\|
Con1SSH LOOKFOR \| compute-1(\s)*\| compute(\s)*\| unlocked(\s)*\| enabled(\s)*\| available(\s)*\|
#Con1SSH CONTINUEIF \| storage-0(\s)*\| storage(\s)*\| unlocked(\s)*\| enabled(\s)*\| available(\s)*\|
Con1SSH WAIT 5 SEC
Con1SSH LOOKFOR

# Check that we have the infra configuration on controller-0
Con1SSH TYPE system host-if-list controller-0\n
Con1SSH CONTINUEIF \| [a-z0-9-]* \| [a-z0-9 ]*\| infra(\s)*\| ethernet \| \[u\'eth[0-9]*\'\](\s)*\| [0-9]*(\s)*\| None
Con1SSH WAIT 5 SEC
Con1SSH CONTINUEIF 

# Check that we have the infra configuration on controller-1
Con1SSH TYPE system host-if-list controller-1\n
Con1SSH CONTINUEIF \| [a-z0-9-]* \| [a-z0-9 ]*\| infra(\s)*\| ethernet \| \[u\'eth[0-9]*\'\](\s)*\| [0-9]*(\s)*\| None
Con1SSH WAIT 5 SEC
Con1SSH CONTINUEIF 

# Check that we have the infra configuration on compute-0
Con1SSH TYPE system host-if-list compute-0\n
Con1SSH CONTINUEIF \| [a-z0-9-]* \| [a-z0-9 ]*\| infra(\s)*\| ethernet \| \[u\'eth[0-9]*\'\](\s)*\| [0-9]*(\s)*\| None
Con1SSH WAIT 5 SEC
Con1SSH CONTINUEIF 

# Check that we have the infra configuration on compute-1
Con1SSH TYPE system host-if-list compute-1\n
Con1SSH CONTINUEIF \| [a-z0-9-]* \| [a-z0-9 ]*\| infra(\s)*\| ethernet \| \[u\'eth[0-9]*\'\](\s)*\| [0-9]*(\s)*\| None
Con1SSH WAIT 5 SEC
Con1SSH CONTINUEIF 

# Check that we have the infra configuration on storage-0
#Con1SSH TYPE system host-if-list storage-0\n
#Con1SSH CONTINUEIF \| [a-z0-9-]* \| infra0(\s)*\| infra(\s)*\| ethernet \| \[u\'eth[0-9]*\'\](\s)*\| [0-9]*(\s)*\| None
#Con1SSH WAIT 5 SEC
#Con1SSH CONTINUEIF

# Check that the infra network is configured
Con1SSH TYPE system infra-show\n
Con1SSH CONTINUEIF \| istate(\s)* \| applied(\s)*\|
Con1SSH WAIT 5 SEC
Con1SSH CONTINUEIF 

# Send a script to the controller that allows us to log an interface on the cisco router 
CALL python3 ${WASSP_TESTCASE_BASE}/utils/sendFile.py -i $OAM_IP -u $CONT_USER -p $CONT_PASSWD -s ${WASSP_TC_PATH}/../common/toggle.exp -d /home/wrsroot -P 22
