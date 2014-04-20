PROMPT (.*:~#\s)|(.*\]:\s)|(.*\)\]#\s)|(.*\]#\s)
Con1 PROMPT (.*:~#\s)|(.*\]:\s)|(.*\)\]#\s)|(.*\]#\s)
Con2 PROMPT (.*:~#\s)|(.*\]:\s)|(.*\)\]#\s)|(.*\]#\s)
Com1 PROMPT (.*:~#\s)|(.*\]:\s)|(.*\)\]#\s)|(.*\]#\s)
Com2 PROMPT (.*:~#\s)|(.*\]:\s)|(.*\)\]#\s)|(.*\]#\s)

TYPE \n
WAIT 1 SEC  {ignoreTimeout:True} login:
TYPE root\n
WAIT 1 SEC {ignoreTimeout:True} assword: 
TYPE root\n
WAIT 1 SEC {ignoreTimeout:True} .*\s 
TYPE source /etc/nova/openrc\n
WAIT 1 SEC {ignoreTimeout:True} .*\s 


Con2 TYPE \n\n\n
Con2 WAIT 3 SEC {ignoreTimeout:True} login:
Con2 TYPE root\n
Con2 WAIT 1 SEC {ignoreTimeout:True} assword:
Con2 TYPE root\n
Con2 WAIT 1 SEC {ignoreTimeout:True} .*\s
Con2 TYPE source /etc/nova/openrc\n
Con2 WAIT 1 SEC {ignoreTimeout:True} .*\s



Com1 TYPE \n\n\n
Com1 WAIT 3 SEC {ignoreTimeout:True} login:
Com1 TYPE root\n
Com1 WAIT 1 SEC {ignoreTimeout:True} assword:
Com1 TYPE root\n
Com1 WAIT 1 SEC {ignoreTimeout:True} .*\s
Com1 TYPE source /etc/nova/openrc\n
Com1 WAIT 1 SEC {ignoreTimeout:True} .*\s



Com2 TYPE \n\n\n
Com2 WAIT 3 SEC {ignoreTimeout:True} login:
Com2 TYPE root\n
Com2 WAIT 1 SEC {ignoreTimeout:True} assword:
Com2 TYPE root\n
Com2 WAIT 1 SEC {ignoreTimeout:True} .*\s
Com2 TYPE source /etc/nova/openrc\n
Com2 WAIT 1 SEC {ignoreTimeout:True} .*\s















PASS
