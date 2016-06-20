'''
The common WRIFT environment utilities library

Copyright (c) 2012-2013 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.

'''

'''
modification history:
---------------------
02d,23aug13,dr   Add envVarIsTrue utility function
02c,12dec12,dr   Add WriftEnv and CLI processing
02b,07dec12,ebh  Update routine name
02a,04dec12,ebh  Addition of the method to set up logs and workspace env vars
'''

import os
import copy

#-----------------------------------------------------------------------------#

def envVarIsTrue(varName, trueValues='ytYT'):
    ''' returns true if the first character of varName is in trueValues '''

    return os.environ.get(varName, 'F')[0] in trueValues

#-----------------------------------------------------------------------------#

def setTestCaseUserVars(logDir, workspaceDir):
    ''' Set the WRIFT_TC_xx_LOG and WRIFT_TC_xx_WORKSPACE
    environment variables
    '''

    userLogDir = os.path.join(logDir, "user")
    userWorkspaceDir = os.path.join(workspaceDir, "user")

    os.environ["WASSP_TC_RUN_LOG"] = logDir
    os.environ["WRIFT_TC_USER_LOG"] = userLogDir
    os.environ["WRIFT_TC_RUN_WORKSPACE"] = workspaceDir
    os.environ["WASSP_TC_USER_WORKSPACE"] = userWorkspaceDir
    try:
        if not os.path.exists(userLogDir):
            os.mkdir(userLogDir)
        if not os.path.exists(userWorkspaceDir):
            os.mkdir(userWorkspaceDir)
    except:
        return False

    # everything is set up now
    return True

#-----------------------------------------------------------------------------#

class WriftEnv():
    ''' Holds wrift environment and provides methods to
    write and read external environment files.
    '''

    envFile = 'envFile.txt'

    #-------------------------------------------------------------------------#

    class OpenFailedError(Exception):
        pass

    #-------------------------------------------------------------------------#

    def __init__(self, envFile=''):
        ''' initialize the object and overload the default environment file
        if one is provided.
        '''

        self._envFile = os.path.join(os.getenv('WASSP_TC_RUN_LOG', ''),
                                    envFile or WriftEnv.envFile)

    #-------------------------------------------------------------------------#

    def _openEnvFile(self, envFile, mode='r'):
        ''' open the environment file '''

        try:
            return open(envFile, mode)
        except:
            raise WriftEnv.OpenFailedError

    #-------------------------------------------------------------------------#

    def write(self, key, value, export=True):
        ''' Creates and sets a new environment variable '''

        setattr(self, key, value)
        if export:
            os.environ[key] = value

    #-------------------------------------------------------------------------#

    def read(self, key):
        ''' Retrieves an environment variable if it exists. Returns an
        empty string if it does not exist.
        '''

        if not hasattr(self, key):
            return ''
        return self.key

    #-------------------------------------------------------------------------#

    def writeEnvFile(self, append=True, **kwargs):
        ''' writes the provided environment key, value pairs into
        the environment file and the environment itself.
        '''

        try:
            #-- save it inside our environment
            mode = 'a' if append else 'w'
            f = self._openEnvFile(self._envFile, mode=mode)

            for key, value in kwargs.items():
                self.write(key, value)
                f.write('%s="%s"\n' % (key, value))

            f.close()
            return True

        except WriftEnv.OpenFailedError as e:
            return False

    #-------------------------------------------------------------------------#

    def readEnvFile(self):
        ''' read environment variables from an external file '''

        try:
            f = self._openEnvFile(self._envFile, mode='r')
            for line in f.readlines():
                line = line.replace('\n', '')
                key, value = line.split('=', 1)
                self.write(key, value.replace('"', ''))
            f.close()
        except WriftEnv.OpenFailedError:
            pass

        #-- copy the dict so we can remove items from it
        variables = copy.deepcopy(vars(self))

        for k, v in vars(self).items():
            if k.startswith('_'):
                variables.pop(k)

        return variables

#-----------------------------------------------------------------------------#

if __name__ == '__main__':

    import sys
    import os

    scriptName = os.path.basename(sys.argv[0])

    usage = '''usage:

        %s write [envfile] [var=value [var=value [..]]]
        %s read [envfile] [-b] [-c] [-s] [-r]

    Write the specified variables (var) and their values into the
    environment file. The environment file is optional. If omitted,
    this script uses the default.

    Read the environment file and display the information in
    one or many formats. The environment file is optional. If omitted,
    this script uses the default.

    When reading the environment file, only one output format can be used.
    If multiple output formats are specified, the highest priority will be
    the one used. The prioriy order is in decreasing order: -b, -s, -c, -r.

    Supported formats are:
        -b  -  selects an output format suitable to be used by the 'bash'
               shell in
               Linux. This is the default when no other option is selected.
        -c  -  selects an output format suitable to be used by the 'csh'
               shell in Linux.
        -r  -  select the raw output format which is equivalent to a Python
               dictionary of key and values.
        -s  -  selects an output format suitable to be used by the 'sh'
               shell in Linux. This is an alias to '-b'

        ''' % (scriptName, scriptName)


    #-- process options
    if '-h' in sys.argv:
        print(usage)
        sys.exit(2)

    bash = '-b' in sys.argv
    if bash:
        sys.argv.remove('-b')

    csh = '-c' in sys.argv
    if csh:
        sys.argv.remove('-c')

    sh = '-s' in sys.argv
    if sh:
        sys.argv.remove('-s')

    raw = '-r' in sys.argv
    if raw:
        sys.argv.remove('-r')

    #-- default to bash if nothing specified
    if not (bash or csh or sh or raw):
        bash = True

    #-- get the operation
    operation = sys.argv[1].lower()
    envFile = sys.argv[2] if len(sys.argv) > 2 else ''

    #-- ensure the envFile is not a key/value pair.
    if '=' in envFile:
        envFile = ''

    env = WriftEnv(envFile)

    if operation == 'write':
        if envFile:
            data = sys.argv[3:]
        else:
            data = sys.argv[2:]

        #-- convert the key=value pairs into a dict so we can pass them as
        #-- kwargs
        kvpairs = dict([tuple(stuff.split('=', 1)) for stuff in data])
        env.writeEnvFile(**kvpairs)

        #-- print what was processed
        print(vars(env))


    elif operation == 'read':
        #--  read the environment file
        data = env.readEnvFile()

        #-- output the data in the specified format(s)
        formatStr = ''
        if bash or sh:
            formatStr = 'export %s="%s"'
        elif csh:
            formatStr = 'setenv %s "%s"'
        elif raw:
            print(data)

        #-- print and set the environment
        for k, v in data.items():
            if formatStr:
                print(formatStr % (k, v))
            os.environ[k] = v

    else:
        print('Invalid operation specified. Must be "read" or "write".')
        print(usage)
        sys.exit(2)

    #-- all done
    sys.exit(0)
