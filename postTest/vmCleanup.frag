SINK 5 SEC
PROMPT (.*:~#\s)|(.*\]:\s)|(.*\)\]#\s)|(.*\]#\s)
Con1 PROMPT (.*:~#\s)|(.*\]:\s)|(.*\)\]#\s)|(.*\]#\s)
Con2 PROMPT (.*:~#\s)|(.*\]:\s)|(.*\)\]#\s)|(.*\]#\s)
Com1 PROMPT (.*:~#\s)|(.*\]:\s)|(.*\)\]#\s)|(.*\]#\s)
Com2 PROMPT (.*:~#\s)|(.*\]:\s)|(.*\)\]#\s)|(.*\]#\s)

SET dollar $

TYPE \n\n\n
WAIT 8 SEC {ignoreTimeout:True} login:

TYPE root\n
WAIT 1 SEC {ignoreTimeout:True} Password:

TYPE root\n
WAIT 1 SEC {ignoreTimeout:True} .*\s

TYPE source /etc/nova/openrc
TYPE \n
WAIT 1 SEC {ignoreTimeout:True}



Con2 TYPE \n\n\n
Con2 WAIT 8 SEC {ignoreTimeout:True} login:

Con2 TYPE root\n
Con2 WAIT 1 SEC {ignoreTimeout:True} Password:

Con2 TYPE root\n
Con2 WAIT 1 SEC {ignoreTimeout:True} .*\s

Con2 TYPE source /etc/nova/openrc
Con2 TYPE \n
Con2 WAIT 1 SEC {ignoreTimeout:True}



################################################################################
### VM cleanup block
################################################################################
SINK 2 SEC
LOOKFOR
TYPE nova list \n
WAIT 30 SEC
SAVEOUTPUT ${WASSP_TC_RUN_LOG}/nova-list.log
CALL cat ${WASSP_TC_RUN_LOG}/nova-list.log

CALLPARSER python3 ${WASSP_TC_PATH}/../utils/parse_uuid.py -f ${WASSP_TC_RUN_LOG}/nova-list.log
FOREACH ${X}
    TYPE nova delete $ITEM_uuid \n
    WAIT 30 SEC {ignoreTimeout:True}
    DELAY 3 SEC
ENDFOREACH



### Colect the logs




LOOKFOR
SINK 2 SEC
TYPE system host-list \n
WAIT 30 SEC
SAVEOUTPUT ${WASSP_TC_RUN_LOG}/system-host-list.log
DELAY 3 SEC
CALL cat ${WASSP_TC_RUN_LOG}/system-host-list.log
LOOKFOR

CALLPARSER python3 ${WASSP_TC_PATH}/../utils/parse_system_host_list.py -v HOST --wassp_dict_id node -l ${WASSP_TC_RUN_LOG}/system-host-list.log
DELAY 3 SEC




FOREACH ${HOST}
TYPE ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no  ${ITEM_node} zip -r  /root/${ITEM_node}.var.log.zip /var/log/ \n
    WAIT 100 SEC {ignoreTimeout:True} (.*\)\]#\s)|(password:)
    TYPE root\n
    WAIT 100 SEC {ignoreTimeout:True} (.*\)\]#\s)|(password:)
    SINK 3 SEC    
ENDFOREACH

FOREACH ${HOST}
TYPE scp  -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no  ${ITEM_node}:/root/${ITEM_node}.var.log.zip /root/ \n
    WAIT 100 SEC {ignoreTimeout:True} (.*\)\]#\s)|(password:)
    TYPE root\n
    WAIT 100 SEC {ignoreTimeout:True} (.*\)\]#\s)|(password:)
    SINK 3 SEC
LOOKFOR
ENDFOREACH

CALL rsync -r -e 'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ' root@$env.NODE.target.Boot.oamAddrA:/root/*.zip ${WASSP_TC_RUN_LOG}/

TYPE date > /tmp/date.txt\n
WAIT 3 SEC {ignoreTimeout:True}
TYPE zip --grow  /root/tempest.log.zip /tmp/date.txt\n
WAIT 3 SEC {ignoreTimeout:True}

TYPE zip --grow  /root/tempest.log.zip /usr/lib64/python2.7/site-packages/tempest.log \n
WAIT 100 SEC
CALL rsync -r -e 'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ' root@$env.NODE.target.Boot.oamAddrA:/root/*.zip ${WASSP_TC_RUN_LOG}/


Con2 TYPE \n
Con2 WAIT 7 SEC {ignoreTimeout:True}

SINK 1 SEC
CALL ${WASSP_TESTCASE_BASE}/utils/send_email.sh ${CONSOLE_LOG} ${WASSP_TC_NAME}

