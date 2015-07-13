#!/usr/bin/env python

'''

Session Manager using pexpect with ssh extension (pxssh)

Mostly copied from example
http://pexpect.readthedocs.org/en/latest/api/pxssh.html

26 June 2015
'''


import traceback
import sys
import os
import re

import pexpect
import pxssh

#setup color.format strings
colorred = "\033[1;31m{0}\033[00m"
colorgrn = "\033[1;32m{0}\033[00m"
colorblue = "\033[1;34m{0}\033[00m"
coloryel = "\033[1;34m{0}\033[00m"

DEBUG=False

VERSION = '0.9'

class Session():
    '''
        Class to extend pexpect.pxssh to manage sessions
        
        Supports:
            Multiple sessions, via instanciation of session objects
            connect             connects a session
            send                sends string to remote host
            expect()            waits for prompt
            expect('value')     expects 'value'
            expect('value', show_exp=yes)        expects 'value' and prints value found
            expect(var)         expects python variable 
            expect('\w+::\w+')  expect short IPv6 address like 2001::0001
            close()             disconnects session
            reconnect()         reconnects to session
    
    '''

    def __init__(self, *args, **kwargs):
        # initialize super class
        #super(Session, self).__init__(*args, **kwargs)
        self.session_name = 'session_name'
        self.prompt = '\$ '
        self.timeout = 3

    def connect(self, hostname='hostname', username='username', password='password', timeout=None):
        if timeout is None:
            timeout = self.timeout
        # preserve info for re-connect
        self.hostname = hostname
        self.username = username
        self.password = password
        try:
            self.session_name = pxssh.pxssh(timeout=5)
            
            # set to ignore ssh host fingerprinting
            self.session_name.SSH_OPTS = " '-o StrictHostKeyChecking=no'" + " '-o UserKnownHostsFile /dev/null' "            
            self.session_name.force_password = True
            
            # log into remote host
            self.session_name.login(hostname, username, password, auto_prompt_reset=False, quiet=False)
            
            self.session_name.PROMPT = self.prompt
            # echo session output to screen
            self.session_name.logfile = open('/dev/stdout', 'w+')

        #FIXME: look for specific exceptions
        except pexpect.EOF as e:
            print(e)
            traceback.print_exc()
            print self.session_name.SSH_OPTS 
            os._exit(1)
        
        except Exception as e:
            print(e)
            traceback.print_exc()
        
    
    def reconnect(self):
        self.connect(self.hostname,self.username,self.password,self.timeout)
        
    
    def send(self,cmd=None):
        if cmd is None:
            cmd = ''
        rtn = self.session_name.sendline(cmd)
        if rtn != 0:
            if DEBUG: print('>%s' % cmd)
        return rtn
    
    def expect(self,blob=None,timeout=None,show_exp=None):
        matchstr = ''
        if timeout is None:
            timeout = self.timeout
        if blob is None:
            blob = self.prompt
        try:
            rtn = self.session_name.expect(blob, timeout=timeout)
            # collect output for later
            #print("=<%s|%s" % (rtn,blob))
            if rtn == 0:
                m = self.session_name.match
                matchstr = m.group()
                self.cmd_output = self.session_name.before + matchstr

                if DEBUG: print("<%s" % (self.cmd_output))
                # look for expected string
                if str(blob) != self.prompt:
                    if show_exp is not None :
                        print(colorgrn.format("\nshow_exp>%s" % matchstr))
                
            
        #specific exception for timeout
        except pexpect.TIMEOUT as e:        
            sys.stderr.write(colorred.format("\nERROR: \"%s\" not found\n" % blob))
            return -1
        return 0
        
    def return_output(self):
        if self.cmd_output != "":
            return self.cmd_output
        
    def daisy_chain(self):
        pass
        
    def close(self):
        try:
            self.session_name.close()
        except:
            pass




def main():
    ''' 
    only used to test this library
    
    '''
    username = 'wrsroot'
    password = 'li69nux'
    hostname = '10.10.10.3'
    #hostname = 'yow-cgcs-ironpass-1.wrs.com'
    prompt = '.*\$ '

    CLI = Session()
    CLI.connect(hostname=hostname, username=username, password=password)
    CLI.send('echo "hello world"')
    CLI.expect()
    CLI.send('/sbin/ip route')
    CLI.expect('default', show_exp='yes')
    CLI.expect('eth1', show_exp='yes')
    CLI.send()
    CLI.expect()
    CLI.close()
    print("\n\nreconnecting...")
    CLI.reconnect()
    CLI.send('echo "hello \nworld2"')
    CLI.expect('hello', show_exp='yes')
    CLI.expect('world', show_exp='yes')
    CLI.close()
    


if __name__ == '__main__':
    try:
        main()
        print("\npau")
    except KeyboardInterrupt:
        print("Detected ^C")
        os._exit(1)



