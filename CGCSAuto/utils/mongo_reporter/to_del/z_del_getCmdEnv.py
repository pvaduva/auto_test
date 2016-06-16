#! /usr/bin/env python3
'''
z_del_getCmdEnv.py - Utilities for obtaining the environment from a subprocess command

Copyright (c) 2013 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.

Use case:
Given a shell 'command' to be executed using the z_del_cmdutils.py, this script
will be executed immediately after and act as a transparent man-in-the-middle: 

After the 'command' finishes, this script will send the shell environment and 
current working directory to a network data manager and then exit with the 
same return code as the 'command'.
'''

'''
modification history
--------------------
01b,15jan13,srr  Converted manager to a class to allow for multiple instances
01a,14jan13,srr  Creation
'''

import os
import sys
import socket
import platform
from random import randint
from multiprocessing import Pipe
from multiprocessing.managers import BaseManager

# network manager information
IP_ADDRESS_DEFAULT = '127.0.0.1'
# auto-assign port number
PORT_DEFAULT = 0
# the key must be a bytearray
AUTHKEY_DEFAULT = b'WRIFT'

PLATFORM = platform.system()

# data pipe names
PIPE_END_MNGR = 'pipeEnvMngr'
PIPE_END_CLIENT = 'pipeEnvClient'

class CmdEnvManager(BaseManager):
    pass

#-----------------------------------------------------------------------------#
class DataManager():
    ''' A class for a network data manager
    '''
    
    def __init__(self, ipAddress=IP_ADDRESS_DEFAULT, port=PORT_DEFAULT, 
                 key=AUTHKEY_DEFAULT, python=''):
        '''
        'ipAddress' and 'port' are used to bind the network manager
        'key' is a password for the network manager
        '''
        self.ipAddress = ipAddress
        self.port = int(port)
        
        if isinstance(key, str):
            key = key.encode()
        self.key = key
        
        self.python = python
        
    def startManager(self):
        ''' Start a network data manager with a pipe
        '''
        
        # start a pipe
        PipeEndA, PipeEndB = Pipe()

        # register the pipe ends with the manager
        CmdEnvManager.register(PIPE_END_MNGR, callable=lambda: PipeEndA)
        CmdEnvManager.register(PIPE_END_CLIENT, callable=lambda: PipeEndB)

        # create and start the network manager
        self.manager = CmdEnvManager(address=(self.ipAddress, self.port),
                             authkey=self.key)
        self.manager.start()
        
        # get the port number that the manager was started on
        self.port = self.manager.address[1]
        
        return self.manager

    #-------------------------------------------------------------------------#
    def makeSubprocessCmd(self, command):
        ''' Chain a 'commmand' with the execution of the current script
        which will connect to the manager and send its environment
        '''

        # set commands chain separator
        if 'Windows' in PLATFORM:
            sep = '&'
        elif 'Linux' in PLATFORM:
            sep = ';'
        else:
            sep = ';'

        elements = {'c': command,
                    'x': sep,
                    'y': self.python,
                    's': os.path.realpath(__file__),
                    'e': getCmdReturnCode(),
                    'i': self.ipAddress,
                    'p': self.port,
                    'k': self.key.decode()}

        # return the chained command                  
        return '{c}{x}{y} {s} -e {e} -i {i} -p {p} -k {k}'.format(**elements)
        
#-----------------------------------------------------------------------------#
def getClient(ipAddress=IP_ADDRESS_DEFAULT, port=PORT_DEFAULT,
              key=AUTHKEY_DEFAULT):
    ''' Connect to a network data manager and get the client-end pipe
    '''

    CmdEnvManager.register(PIPE_END_CLIENT)
    
    client = CmdEnvManager(address=(ipAddress, int(port)), authkey=key)
    client.connect()

    return client

#-----------------------------------------------------------------------------#
def getCmdReturnCode():
    ''' Get the shell command that returns the previous command return code
    '''
    
    if 'Windows' in PLATFORM:
        return '%errorlevel%'
    elif 'Linux' in PLATFORM:
    # TODO: other shell types besides bash
        return '$?'
    else:
        return '$?'

#-----------------------------------------------------------------------------#
def main(ipAddress=IP_ADDRESS_DEFAULT, port=PORT_DEFAULT, key=AUTHKEY_DEFAULT,
         exitCode=0):
    ''' Send the current environment to the data manager
    '''
    
    if isinstance(key, str):
        key = key.encode()

    # connect to the manager and get the client pipe
    clientPipe = getattr(getClient(ipAddress, port, key), PIPE_END_CLIENT)()

    data = {'rc': exitCode,
            'env': os.environ.copy(),
            'cwd': os.path.realpath(os.getcwd())}

    # send the environment data
    clientPipe.send(data)

    # exit with the requested return code
    sys.exit(int(exitCode))
    

#-----------------------------------------------------------------------------#
if __name__ == '__main__':

    from optparse import OptionParser

    parser = OptionParser()

    parser.add_option('-e', '--exitcode', dest='exitcode', default=0, type=int,
                      help='Provide the desired exit code for this script')

    parser.add_option('-i', '--ip', dest='ip', default=IP_ADDRESS_DEFAULT,
                      help='Provide the data manager IP address')

    parser.add_option('-p', '--port', dest='port', default=PORT_DEFAULT,
                      help='Provide the data manager port number', type=int)
                      
    parser.add_option('-k', '--key', dest='key', default=AUTHKEY_DEFAULT,
                      help='Provide the data manager authentication key')

    (options, args) = parser.parse_args()
    
    main(options.ip, options.port, options.key, options.exitcode)
