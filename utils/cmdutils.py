'''
cmdutils.py - Simple command/process execution utilities

Copyright (c) 2013 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.

'''

'''
modification history
--------------------
20dec13,amf  Changing the name of the log monitoring variable to WATCH_LOGS
01l,23aug13,dr   Show command output in new window.
01k,02jun13,srr  Adding new functionality for killing processes
01j,30may13,srr  Fixing retries bug
01i,06may13,dr   Optionally prevent raising exceptions when commands fail.
01h,24feb13,srr  Added keyword argument to CmdRCError
01g,15feb13,srr  Modified to use getCmdEnv manager class and added bug fixes
01f,14feb13,srr  Added feature for maintaining the environment in CmdExec
01e,12feb13,srr  Added quitFlag
01d,11feb13,srr  Adding logFile for command output
01c,07feb13,dsk  revert change. No handler for this logger because it's a library
01b,06feb13,dsk  initialize logger
01a,25jan13,srr  Split out of openSSHConnUtils
'''

import os
import sys
import time
import signal
import subprocess
import platform
import logging
from threading import Thread, Event

# prepend current folder to PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from getCmdEnv import DataManager, PIPE_END_MNGR
from wriftenvutils import envVarIsTrue

log = logging.getLogger(__name__)

# set a default command return code and timeout in sec
TIMEOUT_CMD_SEC_DEFAULT = 300
TIMEOUT_RC_DEFAULT = -1

# set default number of command retries in case of timeout
CMD_RETRIES_DEFAULT = 1

# set default command sleep duration
SLEEP_SEC_BEFORE_CMD_KILL = 5
SLEEP_SEC_BEFORE_CMD_RPT = 10

# linux command to output the list of process IDs and parents IDs
CMD_LINUX_PARENT_PID = "ps hax -o pid,ppid"

def validateString(testIterable, OkStrList=[], notOkStrList=[]):
    ''' Verify if a list of strings contain a desired substring or a
    non-desired one.
    'testIterable', 'OkStrList' and 'notOkStrList' are lists of strings.
    'OkStrList' are not PASS conditions, just validity indicators.
    Can be used to check if result of a command is valid:
    Failure if:
        it doesn't include any 'OkStrList' OR it includes any 'notOkStrList'
        'notOkStrList' > 'OkStrList'
    returns bool True if the 'testIterable' is validated
    '''

    # if not a string, concatenate the testIterable into one
    # ie. (stdout, stderr, retcode)
    if not isinstance(testIterable, str):
        testString = ' '.join([str(element) for element in testIterable])
    else:
        testString = testIterable

    validString = False

    # ensure validation criteria inputs are lists
    if not isinstance(OkStrList, list):
        OkStrList = [OkStrList]
    if not isinstance(notOkStrList, list):
        notOkStrList = [notOkStrList]

    if testString != None:

        # if no validation strings have been provided and test string is
        # empty assume success
        if not OkStrList and not notOkStrList and testString == '':
            validString = True

        # otherwise perform test
        else:
            # check if output includes any success indicator strings
            for item in OkStrList:
                if item in testString:
                    validString = True
                    break

            # check if output includes any failure indicator strings
            for item in notOkStrList:
                if item in testString:
                    validString = False
                    log.warning('"%s" found in message string', item)
                    break

    # return output of command
    return testString, validString

#=============================================================================#

class CmdExec():
    ''' Execute independent commands with timeout(seconds) and several retries.
    '''

    def __init__(self, retries=CMD_RETRIES_DEFAULT,
                 timeout=TIMEOUT_CMD_SEC_DEFAULT, quitFlag=None, keepEnv=False,
                 python='', stdOutErr=False, logFile=None,
                 retriesDelay=SLEEP_SEC_BEFORE_CMD_RPT,
                 killDelay=SLEEP_SEC_BEFORE_CMD_KILL):
        ''' 'quitflag' should be a thread.Event that when set will trigger
        a SystemExit exception in CmdExec
        'retries' is the object default number of command retries
        'retriesDelay' is the object delay before repeating a command
        'timeout' is the object default command timeout in seconds
        'stdOutErr' bool indicates if STDERR should be redirected to STDOUT
        'keepEnv' set to bool True keeps the environment between commands (str)
        'python' is optional and indicates the path to the local python3
        interpreter for use when 'keepEnv' is True
        'logFile' is the object default command output log file, None indicates
            no default logfile
        'killDelay' is the object delay before killing a timedout command
        '''

        # set a new default number of command retries
        self.retries = retries

        # set a new default command timeout
        self.timeout = timeout

        # set a quit flag
        self.quitFlag = quitFlag if quitFlag else Event()

        # set flag for maintaining the environment of commands
        self.keepEnv = keepEnv

        self.retriesDelay = retriesDelay

        self.killDelay = killDelay

        self.stdOutErr = stdOutErr

        self.logFile = logFile

        # start a data manager for transferring data from a subprocess
        if self.keepEnv is True:
            self.dataMngr = DataManager(python=python)

            self.dataMngr.startManager()

            # get the manager data pipe
            self.pipeEnv = getattr(self.dataMngr.manager, PIPE_END_MNGR)()

            # set previous command environment and cwd
            self._prevEnv = None
            self._prevCwd = None

    #-------------------------------------------------------------------------#
    def checkQuitFlag(self):
        ''' Check the quit event flag and exit if set
        '''

        if self.quitFlag.isSet():
            raise SystemExit

        return True

    #-------------------------------------------------------------------------#
    def executeBasic(self, command, timeout=True, shell=False, logFile=True,
                     cwd=None, retries=None, repeatRetCode=[], env=None,
                     stdOutErr=None):
        ''' Execute a command and return its outputs.
        'command' is a list of parameters as for the subprocess module
        'timeout' is in seconds. bool True uses object default;
            None indicates no timeout. If timeout occurs spawned process/shell
            will be terminated cleanly if possible or killed otherwise
        'shell' is a bool flag indicating if command should be executed in
            a subshell
        'logFile' is the command output log file, bool True uses object default,
            None indicates no logFile.
        'cwd' is the desired working directory in which to execute the command
        'env' is the desired environment for the command
        'stdOutErr' bool True indicates STDERR should be redirected to
            STDOUT, None indicates instance default will be used
        'retries' indicates how many times to re-attempt a command if timeout
        'repeatRetCode' is a list of command return codes for which
            execution will be re-attempted 'retries' times
        returns tuple of (stdout, stderr and return code)
        '''

        attempt = 0

        # use instance default timeout if caller did not specify it
        if timeout is True:
            timeout = self.timeout

        # convert timeout to float
        if timeout is not None:
            timeout = float(timeout)

        retries = self.retries if retries is None else retries

        if stdOutErr is None:
            stdOutErr = self.stdOutErr

        # use instance default log file if caller did not specify it
        if logFile is True:
            logFile = self.logFile

        # check if the environment of commands should be maintained
        if self.keepEnv is True:

            # modify the command to get the environment
            command = self.dataMngr.makeSubprocessCmd(command)

            # force shell True to maintain the environment
            shell = True

            # if caller has not specified a different cwd or env use prev.
            if cwd is None:
                cwd = self._prevCwd
            if env is None:
                env = self._prevEnv

        log.debug(command)

        # try to execute the command a few times
        while self.checkQuitFlag() and attempt <= retries:

            try:
                # increment the command attempt counter
                attempt += 1

                # delay before repeating a command
                if attempt > 1:
                    time.sleep(self.retriesDelay)

                log.debug('Command execution attempt: %s', attempt)

                # start running the command in a thread
                self.thread = commandThread(command=command, env=env,
                                            shell=shell, cwd=cwd,
                                            logFile=logFile,
                                            stdOutErr=stdOutErr)
                self.thread.start()

                # wait for thread to finish until timeout
                self.thread.join(timeout)

                # if thread is still alive then timeout has occured
                if self.thread.is_alive():
                    log.error("Command timeout after %s sec. "
                              "Terminating subprocess..", timeout)

                    # forcefully end the subprocess so thread will finish
                    try:
                        # get a list of all process children
                        children = findChildren(self.thread.process.pid)

                        # terminate the subprocess
                        self.thread.process.terminate()

                        # delay before killing the subprocess
                        time.sleep(self.killDelay)
                        self.thread.process.kill()

                        # kill any remaining process children
                        killProcess(children)
                    except Exception:
                        pass

                    # join the command execution thread
                    self.thread.join(self.killDelay)

                    # show output from timed-out thread
                    log.debug("%s\n%s\n%s", self.thread.cmdOutput,
                                            self.thread.cmdError,
                                            self.thread.cmdReturnCode)

                    # if program has terminated cleanly (return code of 0) set
                    # a return code in order to indicate timeout
                    if not self.thread.cmdReturnCode:
                        self.thread.cmdReturnCode = TIMEOUT_RC_DEFAULT
                else:
                    # check quit event flag
                    self.checkQuitFlag()

                    # show output from thread that did not timeout
                    log.debug("%s\n%s\n%s", self.thread.cmdOutput,
                                            self.thread.cmdError,
                                            self.thread.cmdReturnCode)

                    # store the environment and cwd of the previous command
                    # process must not have timed out (this else condition)
                    # in order to get any data in the output pipe
                    if self.keepEnv is True:

                        # check if there is any data
                        if self.pipeEnv.poll(self.retriesDelay):

                            # get the environment data
                            envData = self.pipeEnv.recv()
                            self._prevEnv = envData['env']
                            self._prevCwd = envData['cwd']

                    # stop repeating command based on return code
                    if self.thread.cmdReturnCode not in repeatRetCode:
                        break

            except Exception:
                log.exception("Command execution process failed")
                raise

        return (self.thread.cmdOutput, self.thread.cmdError,
                self.thread.cmdReturnCode)

    #-------------------------------------------------------------------------#
    def execute(self, command, timeout=True, shell=False, logFile=True,
                cwd=None, retries=None, outLineList=False, repeatRetCode=[],
                env=None, stdOutErr=None, raiseException=True):
        ''' Execute a command, check its return code and return its outputs.
        Same functionality as executeBasic() with the addition of:
        a CmdRCError exception is raised if command return code is non-zero
        returns tuple of (stdout, stderr and return code) if 'outLineList' is
            bool False otherwise the same data split into a list of lines
        '''

        # execute the command
        cmdOutput, cmdError, cmdReturnCode = self.executeBasic(
                                            command=command, timeout=timeout,
                                            shell=shell, logFile=logFile,
                                            cwd=cwd, retries=retries,
                                            repeatRetCode=repeatRetCode)

        if outLineList:
            # return the outputs as a single list of lines
            output = cmdOutput.splitlines() + cmdError.splitlines() \
                    + [str(cmdReturnCode)]
        else:
            output = (cmdOutput, cmdError, cmdReturnCode)

        # raise an exception if return code indicates failure
        # (timeout return code is usually negative)
        if cmdReturnCode and raiseException:
            log.error('%s\n%s\n%s', cmdOutput, cmdError, cmdReturnCode)
            raise CmdRCError("Command return code indicates failure",
                             output=output)

        return output

    #-------------------------------------------------------------------------#
    def executeWithCheck(self, command, OkStrList=[], notOkStrList=[],
                         timeout=True, shell=False, cwd=None, logFile=True,
                         retries=None, outLineList=False, env=None,
                         repeatRetCode=[], stdOutErr=None):
        ''' Execute a command, check return code and validate its output.
        Same functionality as execute() with the addition of:
        A CmdCheckError exception is raised if command output is not validated.
        'OkStrList' and 'notOkStrList' are lists of strings to validate
            the output.
        'OkStrList' are not PASS conditions, just validity indicators.
        Failure if:
            command output doesn't include any 'OkStrList' OR it includes
            any 'notOkStrList'
            'notOkStrList' > 'OkStrList'
        '''

        # execute the command
        result = self.execute(command=command, timeout=timeout, shell=shell,
                              logFile=logFile, cwd=cwd, retries=retries,
                              outLineList=outLineList,
                              repeatRetCode=repeatRetCode)

        # validate the output
        out, validFlag = validateString(result, OkStrList=OkStrList,
                                        notOkStrList=notOkStrList)

        if not validFlag:
            raise CmdCheckError("Command output was not validated:", result)

        # return command outputs
        return result

#=============================================================================#

class CmdCheckError(Exception):
    ''' define an exception that indicates a command output validation error
    '''

    pass

#=============================================================================#

class CmdRCError(Exception):
    ''' define an exception that indicates a command return code error
    '''

    def __init__(self, *args, output=('', '', 1)):
        super().__init__(*args)

        # set the command output tuple
        self.output = output

        # set the command return code
        self.rc = output[2]

#=============================================================================#

class commandThread(Thread):
    ''' Execute a command using subprocess and wait for it to finish.
    '''

    def __init__(self, command, shell=False, cwd=None, logFile=None,
                 stdOutErr=False, env=None):

        Thread.__init__(self)
        self.command = command
        self.cmdOutput = ''
        self.cmdError = ''
        self.cmdReturnCode = 1
        self.shell = shell
        self.cwd = cwd
        self.env = env
        self.logFile = logFile
        self.stdOutErr = stdOutErr
        self.process = None
        self.pid = 0

    #-------------------------------------------------------------------------#
    def run(self):
        ''' Start a subprocess to execute a command.
        '''

        # open a log file for writting or create a pipe
        if self.logFile is not None:
            procOut = open(self.logFile, 'a')
        else:
            procOut = subprocess.PIPE

        #-- Only for Linux. Show command output in new window
        if (platform.system() == 'Linux'
            and envVarIsTrue('WATCH_LOGS')):
            termProcess = subprocess.Popen(['xterm',
                                            '-T',
                                            '"%s"' % ' '.join(self.command),
                                            '-e', 'tail',
                                            '-f', self.logFile],
                                            stdout=subprocess.PIPE,
                                            preexec_fn=os.setsid)

        # start the process
        self.process = subprocess.Popen(self.command,
                                        cwd=self.cwd,
                                        env=self.env,
                                        shell=self.shell,
                                        stdout=procOut,
                                        stderr=self.stdOutErr
                                               and subprocess.STDOUT
                                               or procOut)
        self.pid = self.process.pid

        # wait for process to finish (blocking this thread)
        (out, err) = self.process.communicate()

        # close the destination log file
        if self.logFile is not None:
            #os.killpg(termProcess.pid, signal.SIGTERM)
            procOut.close()

        # get the process outputs and return code
        self.cmdOutput = '' if out is None else out.decode()
        self.cmdError = '' if err is None else err.decode()
        self.cmdReturnCode = self.process.returncode

#=============================================================================#

def findChildren(pid, recursive=True):
    ''' Find all children of a process
    'recursive' set to True returns the entire child process tree
    returns PID list
    '''

    def getChildren(pid, procTreeDict):
        ''' Get children of a process from a process tree dictionary
        '''

        if pid in procTreeDict:
            for child in procTreeDict[pid]:
                yield child
                if recursive:
                    for ch in getChildren(child, procTreeDict):
                        yield ch

    try:
        if platform.system() == 'Linux':

            cmdExecObj = CmdExec()
            out, err, rc = cmdExecObj.execute(CMD_LINUX_PARENT_PID.split(),
                                              raiseException=False)
            procTreeDict = {}

            # create the process tree dictionary
            for line in out.splitlines():
                child, parent = map(int, line.split())

                if procTreeDict.get(parent):
                    procTreeDict[parent].append(child)
                else:
                    procTreeDict[parent] = [child]

            return list(getChildren(pid, procTreeDict))
        else:
            # Windows
            # currently requires psutil to find child processes
            # pip install psutil
            import psutil

            parent = psutil.Process(int(pid))
            children = parent.get_children(recursive=recursive)

            return [child.pid for child in children]

    except Exception:
        log.exception('Unable to find process children')
        return None

#=============================================================================#

def killProcess(pid):
    ''' Kill a process using its ID
    'pid' can be a single PID or a list of PIDs
    '''

    if pid is None:
        return

    pidList = pid if isinstance(pid, list) else [pid]

    # set the kill signal
    try:
        sig = signal.SIGKILL
    except AttributeError:
        sig = signal.SIGTERM

    # attempt to kill each individual process
    for process in pidList:
        try:
            log.info('Trying to kill pid: %s', process)
            os.kill(int(process), sig)
        except Exception:
            pass

#=============================================================================#

def killTree(pid, killGroup=True):
    ''' Kill a process tree
    'killGroup' will also kill the parent
    '''

    try:
        if platform.system() == 'Linux':
            if killGroup:
                # kill the process group directly
                killProcess(-pid)
            else:
                # find and kill only the children
                killProcess(findChildren(pid, recursive=True))
        else:
            killProcess(findChildren(pid, recursive=True))
            if killGroup:
                killProcess(pid)
        return True

    except Exception:
        return False
