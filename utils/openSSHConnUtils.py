'''
openSSHConnUtils.py - SSH command utility using OpenSSH

Copyright (c) 2012-2014 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.

Inputs for SSH key generation script are: ip port user pass customConfig
Return code indicates SSH connection success or failure.
If requested, output contains the path of the custom config file 
surrounded by the GENSSH_CONFIG_MARKER string
'''

'''
modification history
--------------------
10jan14,srr  Added more file transfer options
01i,15feb13,srr  Removed verbose flag and added bug fixes
01h,25jan13,srr  Split-out SingleCmdExec to cmdutils.py
01g,27nov12,srr  Clean-up and miscellaneous improvements
01f,24oct12,srr  Added command execution exceptions
01e,15oct12,srr  Added non-SSH command execution support
01d,11oct12,srr  Added timeout support for SSH connection and command execution time
01c,10oct12,srr  Removed dependency on shConnUtils; using subprocess directly
01b,09oct12,srr  Single SSH command support.
01a,08oct12,srr  Created.
'''


import os
import sys
import time
import shlex
import logging
import subprocess
from threading import Thread

# prepend current folder to PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

import cmdutils

# import name change for backwards compatibility with MILS scripts
SingleCmdExec = cmdutils.CmdExec

log = logging.getLogger(__name__)

# default SSH key generation script
GENSSHKEYS_SCRIPT_DEFAULT = "genSSHKeys.sh"

# SSH key generation script string marker for config file path
GENSSH_CONFIG_MARKER = '%@%'

# SSH timeout detection settings
SSH_SETTINGS_TIMEOUT_DEFAULT = '-o ServerAliveInterval=15 -o ServerAliveCountMax=6 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no'

# set standard command timeout return codes
TIMEOUT_RETCODE_SSH = 255
TIMEOUT_RETCODE_SCP = 1

# set a default command timeout
TIMEOUT_CMD_SEC_DEFAULT = 300

# set default number of command retries
CMD_RETRIES_DEFAULT = 5

class SshConn():
    ''' Use OpenSSH client utility to transfer files or execute remote commands.
    '''

    def __init__(self, host, username, password, port=22, sshCustomConf=True,
                 genSSHKeysScript=None, timeout=TIMEOUT_CMD_SEC_DEFAULT, 
                 retries=CMD_RETRIES_DEFAULT):
        ''' initialise the object.
        'host', 'port', 'username' and 'password' are the SSH destination and
        login details 
        'sshCustomConf' bool True will create a temporary SSH keys file
        'timeout' is the object default command timeout in seconds
        'retries' is the object default number of command retries
        '''

        self.isOpen = False
        self.host = host
        self.port = str(port)
        self.user = username
        self.password = password
        
        if genSSHKeysScript:
            self.genSSHKeysScript = genSSHKeysScript
        else:
            # find folder containing this script and assume it is the path to 
            # the genSSHkey script
            self.genSSHKeysScript = os.path.join(os.path.dirname(
                                                 os.path.realpath(__file__)), 
                                                 GENSSHKEYS_SCRIPT_DEFAULT)
        
        # temporary SSH custom configuration file (True/False)  
        # can be used to by-pass user personal keys(password protected) and 
        # hosts file
        self.sshCustomConf = sshCustomConf

        self.sshConfFileOption = SSH_SETTINGS_TIMEOUT_DEFAULT

        # create command execution object with default timeout and retries
        self.cmdExec = cmdutils.CmdExec(timeout=timeout, retries=retries)
        
        # generate SSH keys and test them
        try:
            self._connOpen()
        except Exception:
            log.exception('Failed to establish SSH connection to %s', host)
            raise

    #-------------------------------------------------------------------------#
    def _connOpen(self):
        ''' Try to open a SSH connection to the target.
        '''

        if self.isOpen:
            log.info('SSH connection already validated')
        
        else:
            log.info('Setting up SSH auth keys to: %s', self.host)
        
            # set up ssh keys for user
            cmd = [self.genSSHKeysScript, self.host, self.port, self.user, 
                   self.password, str(int(self.sshCustomConf))]

            # create the ssh keys
            out, err, rc = self.cmdExec.execute(cmd,
                                            repeatRetCode=[TIMEOUT_RETCODE_SSH])
            
            # check that the command execution return code does not indicate 
            # failure
            if rc:
                raise Exception("Did not generate keys succesfully")
    
            # extract the configuration file name if specified
            if self.sshCustomConf:
                
                # set the SSH configuration file option -F
                try:
                    self.sshConfFileOption += " -F {}".format(
                                   ''.join(out).split(GENSSH_CONFIG_MARKER)[1])
                except Exception:
                    # user already has access with his own configuration file
                    pass

            self.isOpen = True
            
    #-------------------------------------------------------------------------#
    def sendFile(self, srcLocalPath, dstRemotePath, timeout=True, rsync=False,
                 tar=False):
        ''' Copy file/folder from local computer to remote computer.
        'timeout' is in seconds; bool True indicates default should be used;
        None indicates no timeout.
        'rsync' bool True indicates that rsync should be used instead of scp
        'tar' bool True indicates that tar should be used
        '''

        # transfer the file
        if tar:
            cmd = 'sh -c "tar -cz -C {s} . | ssh {} -p {} {}@{} tar -xz -C {d}"'
        elif rsync:
            cmd = 'rsync -a -e "ssh {s} -p {}" {} {}@{}:{d}'
        else:
            cmd = 'scp -r {} -P {} {s} {}@{}:{d}'

        cmd = cmd.format(self.sshConfFileOption, self.port,self.user, self.host, 
                         s=srcLocalPath, d=self.escapeChar(dstRemotePath))

        return self.cmdExec.execute(shlex.split(cmd), timeout=timeout,
                                    repeatRetCode=[TIMEOUT_RETCODE_SCP])

    #-------------------------------------------------------------------------#
    def getFile(self, dstLocalPath, srcRemotePath, timeout=True, rsync=False):
        ''' Copy file/folder from remote computer to local computer.
        'timeout' is in seconds; bool True indicates default should be used;
        None indicates no timeout.
        'rsync' bool True indicates that rsync should be used instead of scp
        '''

        # transfer the file
        if tar:
            cmd = 'sh -c "ssh {} -p {} {}@{} tar -cz -C {s} | tar -xz -C {d}"'
        elif rsync:
            cmd = 'rsync -a -e "ssh {} -p {}" {}@{}:{s} {d}'
        else:
            cmd = 'scp -r {} -P {} {}@{}:{s} {d}'
            
        cmd = cmd.format(self.sshConfFileOption, self.port, self.user, self.host, 
                         s=self.escapeChar(srcRemotePath), d=dstLocalPath )
        
        return self.cmdExec.execute(shlex.split(cmd), timeout=timeout,
                                    repeatRetCode=[TIMEOUT_RETCODE_SCP])

    #-------------------------------------------------------------------------#
    def makeDirRemote(self, remotePath):
        ''' Create a folder tree on REMOTE system.
        remotePath is a folder tree string
        Assumption: remote system is UNIX because it runs a SSH server
        '''
        
        return self.executeCommand('mkdir {}'.format(remotePath))

    #-------------------------------------------------------------------------#
    def executeCommand(self, command, timeout=True, retries=None, 
                       outLineList=False, tty=False):
        ''' Execute a command through SSH and return its outputs when finished.
        'command' is a string
        'timeout' is in seconds; bool True indicates default should be used;
            None indicates no timeout.
        'retries' indicates how many times to re-attempt a command if timeout
        'repeatRetCode' is a list of command return codes for which
            execution will be re-attempted 'retries' times
        'tty' is a bool flag indicating if a TTY should be attached to the 
            remote session
        a CmdRCError exception is raised if command return code is non-zero
        returns tuple of (stdout, stderr and return code) if 'outLineList' is
            bool False otherwise the same data split into a list of lines
        '''
        
        return self.cmdExec.execute(self._stitchSSHCommand(command, tty=tty), 
                                    timeout=timeout,
                                    retries=retries, 
                                    outLineList=outLineList, 
                                    repeatRetCode=[TIMEOUT_RETCODE_SSH])

    #-------------------------------------------------------------------------#
    def executeCommandCheck(self, command, OkStrList=[], notOkStrList=[], 
                            timeout=True, retries=None, 
                            outLineList=False, tty=False):
        ''' Execute command through SSH and validate its outputs.
        Same functionality as executeCommand() with the addition of:
        A CmdCheckError exception is raised if command output is not validated.
        'OkStrList' and 'notOkStrList' are lists of strings to validate 
            the output.
        'OkStrList' are not PASS conditions, just validity indicators.
        Failure if:
            command output doesn't include any 'OkStrList' OR it includes 
            any 'notOkStrList'
            'notOkStrList' > 'OkStrList'
        '''

        return self.cmdExec.executeWithCheck(self._stitchSSHCommand(command, 
                                                                 tty=tty),
                                             OkStrList=OkStrList,
                                             notOkStrList=notOkStrList, 
                                             timeout=timeout,
                                             retries=retries, 
                                             outLineList=outLineList, 
                                             repeatRetCode=[TIMEOUT_RETCODE_SSH])
                                                     
    #-------------------------------------------------------------------------#
    def escapeChar(self, astring):
        ''' Escape special characters from string '''
        
        # escape backslash and quotes
        # only double quotes are allowed in command and contents will be 
        # INTERPRETED by bash
        return astring.replace("'", '"').replace("\\", "\\\\")\
                      .replace('"', '\\\"')
        
    #-------------------------------------------------------------------------#
    def _stitchSSHCommand(self, remoteCommand, shell=False, tty=False):
        ''' Escape special characters in remoteCommand and generate the full 
        SSH command for the subprocess.
        Assumption: remote system is UNIX because it runs a SSH server
        '''
        
        # set SSH options
        sshConfFileOption = self.sshConfFileOption
        
        # attach tty to SSH session
        if tty:
            sshConfFileOption += ' -t'

        # create the standard SSH command           
        sshCommand = 'ssh {} -p {} {}@{}'.format(sshConfFileOption, self.port, 
                                                 self.user, self.host)
        
        if shell:
            # single string
            cmd = "{} \'{}\'".format(sshCommand, self.escapeChar(remoteCommand))
        else:
            # separate arguments
            cmd = sshCommand.split()
            cmd.append(self.escapeChar(remoteCommand))
            
        return cmd

    #-------------------------------------------------------------------------#
    def waitProcEndRemote(self, pid, waitSec, period, retries=None, 
                          timeout=True):
        ''' Wait until a process on a REMOTE machine ends.
        'pid' is the process ID on the remote machine
        'waitSec' is in seconds and indicates the maximum amount of time to
            wait for remote process to finish
        'period' is in seconds and indicates how often to check the status of
            the remote process
        'retries' indicates how many times to re-attempt to check status in
            case the network connection for the check command times-out
        'timeout' is in seconds; bool True means default should be used;
            None indicates no timeout. It indicates the maximum time for a 
            single check command to finish
        returns bool True if process has finished within 'waitSec' time
        '''

        endTime = time.time() + waitSec
        
        # check PID until process ends or timeout is reached
        while time.time() < endTime:

            if not self.checkPID(pid=pid, timeout=timeout,
                                 retries=retries):
                log.info('Remote process has finished')
                return True

            log.info('Process %s is still running...', pid)
            time.sleep(period)

        # wait time has been reached, process is still alive
        return False

    #-------------------------------------------------------------------------#
    def checkPIDRemote(self, pid, timeout=True, retries=None):
        ''' Check if a process on a remote machine is alive.
        'timeout' is in seconds; bool True indicates default should be used;
        None indicates no timeout; maximum time for the check command to finish
        'retries' indicates how many times to re-attempt to check status in
            case the network connection for the check command times-out
        returns bool True if process is alive
        Assumption: remote system is UNIX because it runs a SSH server
        '''

        try:
            cmd = "ps -p {}".format(pid)
            
            # run command to check if PID exists
            # ReturnCode exception is raised if PID does NOT exist
            self.executeCommand(cmd, timeout=timeout, retries=retries)

            return True

        except cmdutils.CmdRCError:
            return False
