# Set the variables we need
OAM_IP = $env.NODE.target.Boot.oamAddrA
CONT_USER = wrsroot
CONT_PASSWD = li69nux
CISCO_IP = 128.224.150.181
CISCO_USER = admin
CISCO_PASSWD = windriver

# Check we are unlocked-enabled-available at the start of test
Con1SSH TYPE system host-list\n
Con1SSH CONTINUEIF \| controller-0 \| controller(\s)*\| unlocked(\s)*\| enabled(\s)*\| available(\s)*\|
Con1SSH CONTINUEIF \| controller-1 \| controller(\s)*\| unlocked(\s)*\| enabled(\s)*\| available(\s)*\|
Con1SSH CONTINUEIF \| compute-0(\s)*\| compute(\s)*\| unlocked(\s)*\| enabled(\s)*\| available(\s)*\|
Con1SSH CONTINUEIF \| compute-1(\s)*\| compute(\s)*\| unlocked(\s)*\| enabled(\s)*\| available(\s)*\|
Con1SSH CONTINUEIF \| storage-0(\s)*\| storage(\s)*\| unlocked(\s)*\| enabled(\s)*\| available(\s)*\|
Con1SSH WAIT 5 SEC

# Check that we have the infra configuration on controller-0
Con1SSH TYPE system host-if-list controller-0\n
Con1SSH CONTINUEIF \| [a-z0-9-]{36} \| infra0(\s)*\| infra(\s)*\| ethernet \| \[u\'eth26\'\](\s)*\| [0-9]* \| None
Con1SSH WAIT 5 SEC

# Check that we have the infra configuration on controller-1
Con1SSH TYPE system host-if-list controller-1\n
Con1SSH CONTINUEIF \| [a-z0-9-]{36} \| infra0(\s)*\| infra(\s)*\| ethernet \| \[u\'eth26\'\](\s)*\| [0-9]* \| None
Con1SSH WAIT 5 SEC

# Check that we have the infra configuration on compute-0
Con1SSH TYPE system host-if-list compute-0\n
Con1SSH CONTINUEIF \| [a-z0-9-]{36} \| infra0(\s)*\| infra(\s)*\| ethernet \| \[u\'eth26\'\](\s)*\| [0-9]* \| None
Con1SSH WAIT 5 SEC

# Check that we have the infra configuration on compute-1
Con1SSH TYPE system host-if-list compute-1\n
Con1SSH CONTINUEIF \| [a-z0-9-]{36} \| infra0(\s)*\| infra(\s)*\| ethernet \| \[u\'eth26\'\](\s)*\| [0-9]* \| None
Con1SSH WAIT 5 SEC

# Check that we have the infra configuration on storage-0
Con1SSH TYPE system host-if-list storage-0\n
Con1SSH CONTINUEIF \| [a-z0-9-]{36} \| infra0(\s)*\| infra(\s)*\| ethernet \| \[u\'eth26\'\](\s)*\| [0-9]* \| None
Con1SSH WAIT 5 SEC

# Check that the infra network is configured
Con1SSH TYPE system infra-show\n
Con1SSH CONTINUEIF \| istate(\s)* \| applied(\s)*\|
Con1SSH WAIT 5 SEC

# Send a script to the controller that allows us to log an interface on the cisco router 
CALL python3 ${WASSP_TC_PATH}/../utils/sendFile.py -i $OAM_IP -u $CONT_USER -p $CONT_PASSWD -s ${WASSP_TC_PATH}/common/toggle.exp -d /home/wrsroot -P 22
