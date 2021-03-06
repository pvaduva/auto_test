LOOKFOR
TYPE \n
SINK 1 SEC
PROMPT (.*:~#\s)(.*:~\$)|(.*\]:\s)|(.*\)\]#\s)|(.*\]#\s)|(.*\)\]\$\s)
Con1 PROMPT (.*:~#\s)(.*:~\$)|(.*\]:\s)|(.*\)\]#\s)|(.*\]#\s)|(.*\)\]\$\s)
Con2 PROMPT (.*:~#\s)(.*:~\$)|(.*\]:\s)|(.*\)\]#\s)|(.*\]#\s)|(.*\)\]\$\s)

SET CR }
SET CL {

#TYPE zip nosetests.xml.zip nosetests.xml\n
#WAIT 30 SEC {ignoreTimeout:True}

CALL rsync -r -e 'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -i ${WASSP_TESTCASE_BASE}/utils/id_rsa' wrsroot@$env.NODE.target.Boot.oamAddrA:tempest.log ${WASSP_TC_RUN_LOG}/
CALL rsync -r -e 'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -i ${WASSP_TESTCASE_BASE}/utils/id_rsa' wrsroot@$env.NODE.target.Boot.oamAddrA:nosetests.xml ${WASSP_TC_RUN_LOG}/
CALL  ${WASSP_TESTCASE_BASE}/utils/testResultsParser.py -f ${WASSP_TC_RUN_LOG}/nosetests.xml
