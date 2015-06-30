#!/usr/bin/env python

'''

Sample script using Session Manager library (session_mgr.py)

Supports:
    Multiple sessions, via instanciation of session objects
    connect             connects a session
    send                sends string to remote host
    expect()            waits for prompt
    expect('value')     expects 'value'
    expect('value', show_exp=yes)        expects 'value' and prints value found
    expect(var)          expects python variable 
    expect('\w+::\w+')   expect short IPv6 address like 2001::0001
    close()              disconnects session
    reconnect()          reconnects to session

Script connects to hostname (defined in Main, default 10.10.10.3)

26 June 2015
'''

import getopt
import os
import traceback
import pexpect
import pxssh
import sys

#sys.path.append('./common/py/SessionMgr')
sys.path.append('./common/py')


from SessionMgr import sessionmgr

print('Version' + sessionmgr.VERSION)

def exit_with_usage(exit_code=2):
    # __doc_ prints the first comment at top of this script
    print(globals()['__doc__'])
    os._exit(exit_code)

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
    try:
        optlist, args = getopt.getopt(sys.argv[1:], 'h?l', ['help','h','?'])
    except Exception, e:
        print(str(e))
        exit_with_usage()

    command_line_options = dict(optlist)
    # There are a million ways to cry for help. These are but a few of them.
    if [elem for elem in command_line_options if elem in ['-h','--h','-?','--?','--help']]:
        exit_with_usage(0)


    # run the actual program
    main()
    print("\npau")

