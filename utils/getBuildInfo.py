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
11jun16,amf  Creation

'''

import os
import sys
import openSSHConnUtils as sshU
from optparse import OptionParser

def get_build_info(lab):
    ''' Get build information from the lab that the test was executed on. 
    '''

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
        # use the build date
        elif 'BUILD_DATE' in idx:
            build = idx.split('=')[-1].strip('"')
            build = '%s_%s' % (build.split(' ')[0],'Centos') 
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

    (options, args) = parser.parse_args()

    build = get_build_info(options.sshIp)
    print (build)
