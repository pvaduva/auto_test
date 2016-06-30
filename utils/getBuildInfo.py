#!/usr/bin/env python3

'''
getBuildInfo.py - helper utility to get the software running on a lab

Copyright (c) 2016 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.

'''

'''
modification history:
---------------------
30jun16,amf  Use server path if buildinfo on the lab is not present
11jun16,amf  Creation

'''

import os
import subprocess
import sys
import openSSHConnUtils as sshU
from optparse import OptionParser

def get_build_info(options):
    ''' Get build information from the lab that the test was executed on. 
    '''

    lab = options.sshIp
    serverPath = options.server_path
    serverName = options.server_name
    # establish SSH connection auth keys
    nodeSSH = sshU.SshConn(host=lab,
                           username='wrsroot',
                           password='li69nux',
                           port=22)


    # get the latest build available
    std_output, std_err, status = nodeSSH.executeCommand('cat /etc/build.info')

    # parse the build info from the output
    out = std_output.split('\n')
    for idx in out:
        if 'BUILD_ID' in idx:
            build = idx.split('=')[-1].strip('"')
            if "n/a" not in build:
                break
        # use the server path
        elif 'BUILD_DATE' in idx:
            cmd = "ssh -q -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no `whoami`@%s ls -l %s/*|grep 'latest_build '| awk '{print $11}' | awk -F / '{print $6}'" % (serverName, serverPath)
            build = subprocess.check_output(cmd, shell=True).decode('ascii')
            break
        else:
            build = ' '

    return build

            
#-----------------------------------------------------------------------------#
if __name__ == '__main__':


    parser = OptionParser()
    usage = "usage ex: %prog -i 10.10.10.10"
    parser = OptionParser(usage=usage)

    parser.add_option('--ip', '-i', dest='sshIp',
                      help='Provide ip address of lab')
    parser.add_option('--server', '-s', dest='server_path',
                      help='Provide path to build location on server')
    parser.add_option('--servername', '-n', dest='server_name',
                      help='Provide hostname of the build server')

    (options, args) = parser.parse_args()

    build = get_build_info(options)
    print (build)
