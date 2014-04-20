#!/usr/bin/env python3

'''
sendFile.py - helper utilit to allow scp of files

Copyright (c) 2014 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.

'''

'''
modification history:
---------------------
26nov13,srr  Creation

'''

import os
import sys
import configparser
import logging
import openSSHConnUtils as sshU
from optparse import OptionParser

log = logging.getLogger(__name__)

            
#-----------------------------------------------------------------------------#
if __name__ == '__main__':

    logging.basicConfig(format='%(levelname)s: %(message)s',
                        level=logging.INFO)

    parser = OptionParser()
    usage = "usage ex: %prog -i 10.10.10.10 -u root -p root -s /tmp/file.txt -d .ssh/id_rsa"
    parser = OptionParser(usage=usage)

    parser.add_option('--ip', '-i', dest='sshIp',
                      help='Provide username')
    parser.add_option('--user', '-u', dest='sshUsername',
                      help='Provide username')
    parser.add_option('--password', '-p', dest='sshPassword',
                      help='Provide username')
    parser.add_option('--source', '-s', dest='srcPath',
                      help='Provide username')
    parser.add_option('--destination', '-d', dest='destPath',
                      help='Provide username')
    parser.add_option('--port', '-P', dest='sshPort', default='22')
    parser.add_option('--verbose', '-v', dest='verbose',
                      action='store_true', default=False, help='Verbose')

    (options, args) = parser.parse_args()

    #if not options.file or not options.nodeID:
        # print help and exit
        #parser.parse_args(['-h'])

    if options.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        
    # establish SSH connection auth keys
    nodeSSH = sshU.SshConn(host=options.sshIp, 
                           username=options.sshUsername,
                           password=options.sshPassword,
                           port=options.sshPort)

    try:
        nodeSSH.makeDirRemote(options.destPath)
    except Exception:
        pass

    nodeSSH.sendFile(options.srcPath, options.destPath)
