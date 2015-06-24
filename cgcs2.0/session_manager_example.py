#!/usr/bin/env python

'''

Sample script using Session Manager library (session_mgr.py)

Supports:
	Multiple sessions, via instanciation of session objects
	connect 



'''

import os
import traceback
import pexpect
import pxssh
import sys

#sys.path.append('./common/py/SessionMgr')
sys.path.append('./common/py')


from SessionMgr import sessionmgr

print('Version' + sessionmgr.VERSION)

def main():
	username = 'wrsroot'
	password = 'li69nux'
	hostname = '10.10.10.3'
	#hostname = 'yow-cgcs-ironpass-1.wrs.com'
	#prompt = '.*\$ '

	# first session
	CLI = sessionmgr.Session()
	# connect to remote host
	CLI.connect(hostname=hostname, username=username, password=password)
	# send a command
	CLI.send('echo "hello world"')
	# wait for prompt
	CLI.expect()
	# send another command
	CLI.send('/sbin/ip route')
	# verify output, and show expected match
	CLI.expect('default', show_exp='yes')
	# verify more output from route command
	CLI.expect('eth1', show_exp='yes')
	# send a CR
	CLI.send()
	# expect a prompt
	CLI.expect()
	# close the connection
	CLI.close()
	print("\n\nreconnecting...")
	# reconnect to same host, with same username and password
	CLI.reconnect()
	# issue more commands
	CLI.send('echo "hello \nworld2"')
	CLI.expect('hello', show_exp='yes')
	CLI.expect('world', show_exp='yes')
	# expect fail
	CLI.expect('five',timeout=1)
	CLI.close()



if __name__ == '__main__':
	main()
	print "pau"

