import os
import re
import threading
import time
from contextlib import contextmanager

import pexpect
from pexpect import pxssh

from utils import exceptions, local_host
from utils.tis_log import LOG

from consts.auth import Guest, Host
from consts.cgcs import Prompt, DATE_OUTPUT
from consts.proj_vars import ProjVar
from consts.lab import Labs, NatBoxes

# setup color.format strings
colorred = "\033[1;31m{0}\033[00m"
colorgrn = "\033[1;32m{0}\033[00m"
colorblue = "\033[1;34m{0}\033[00m"
coloryel = "\033[1;34m{0}\033[00m"

CONTROLLER_PROMPT = '.*controller\-[01]\:~\$ '
ADMIN_PROMPT = Prompt.ADMIN_PROMPT
COMPUTE_PROMPT = Prompt.COMPUTE_PROMPT
PASSWORD_PROMPT = Prompt.PASSWORD_PROMPT
ROOT_PROMPT = Prompt.ROOT_PROMPT
CONNECTION_REFUSED = '.*Connection refused.*'
AUTHORIZED_KEYS_FPATH = "~/.ssh/authorized_keys"


_SSH_OPTS = (' -o RSAAuthentication=no' + ' -o PubkeyAuthentication=no' + ' -o StrictHostKeyChecking=no' +
             ' -o UserKnownHostsFile=/dev/null')

_SSH_OPTS_UBUNTU_VM = (' -o RSAAuthentication=no' + ' -o StrictHostKeyChecking=no' + ' -o UserKnownHostsFile=/dev/null')

EXIT_CODE_CMD = 'echo $?'
TIMEOUT_EXPECT = 10

RSYNC_SSH_OPTIONS = ['-o StrictHostKeyChecking=no', '-o UserKnownHostsFile=/dev/null']


class SSHClient:
    """
        Base SSH Class that uses pexpect and pexpect.pxssh

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
    """

    def __init__(self, host, user='wrsroot', password='Li69nux*', force_password=True, initial_prompt=CONTROLLER_PROMPT,
                 timeout=60, session=None):
        """
        Initiate an object for connecting to remote host
        Args:
            host: hostname or ip. such as "yow-cgcs-ironpass-1.wrs.com" or "128.224.151.212"
            user: linux username for login to host. such as "wrsroot"
            password: password for given user. such as "Li69nux*"

        Returns:

        """

        self.host = host
        self.user = user
        self.password = password
        self.initial_prompt = initial_prompt
        self.prompt = initial_prompt
        self._session = session
        # self.cmd_sent = ''
        # self.cmd_output = ''
        self.force_password = force_password
        self.timeout = timeout
        # self.logpath = None

    def __get_logpath(self):
        lab_list = [getattr(Labs, attr) for attr in dir(Labs) if not attr.startswith('__')]
        for lab in lab_list:
            if lab['floating ip'] == self.host:
                lab_name = lab['short_name']
                break
        else:
            lab_name = self.host

        log_dir = ProjVar.get_var('LOG_DIR')
        if log_dir:
            curr_thread = threading.current_thread()
            if not isinstance(curr_thread, threading._MainThread):
                log_dir += '/threads/'
            os.makedirs(log_dir, exist_ok=True)

            if isinstance(curr_thread, threading._MainThread):
                logpath = log_dir + '/ssh_' + lab_name + ".log"
            else:
                logpath = log_dir + curr_thread.name + '_ssh_' + lab_name + ".log"
        else:
            logpath = None

        return logpath

    def connect(self, retry=False, retry_interval=3, retry_timeout=300, prompt=None,
                use_current=True, timeout=None):

        # Do nothing if current session is connected and force_close is False:
        if self._is_alive() and use_current and self._is_connected():
            LOG.debug("Already connected to {}. Do nothing.".format(self.host))
            # LOG.debug("ID of the session: {}".format(id(self)))
            return

        # use original prompt instead of self.prompt when connecting in case of prompt change during a session
        if not prompt:
            prompt = self.initial_prompt
        if timeout is None:
            timeout = self.timeout

        # Connect to host
        end_time = time.time() + retry_timeout
        while time.time() < end_time:
            # LOG into remote host
            try:
                LOG.info("Attempt to connect to host - {}".format(self.host))
                self._session = pxssh.pxssh(encoding='utf-8')

                # set to ignore ssh host fingerprinting
                self._session.SSH_OPTS = _SSH_OPTS
                self._session.force_password = self.force_password
                self.logpath = self.__get_logpath()

                if self.logpath:
                    self._session.logfile = open(self.logpath, 'w+')

                # Login
                self._session.login(self.host, self.user, self.password, login_timeout=timeout,
                                    auto_prompt_reset=False, quiet=False)

                # Set prompt for matching
                self.set_prompt(prompt)

                # try to goto next line to ensure login really succeeded. pxssh login method has a bug where it
                # almost won't report any login failures.
                # Login successful if prompt matching is found
                if self._is_connected(fail_ok=False):
                    LOG.info("Login successful!")
                    # LOG.debug(self._session)
                    # next 5 lines change ssh window size and flush its buffer
                    self._session.setwinsize(150, 250)
                    self.send()

                    end_time = time.time() + 20
                    while time.time() < end_time:
                        index = self.expect(timeout=3, fail_ok=True)
                        if index != 0:
                            break
                    else:
                        LOG.warning("Still getting prompt from the buffer. Buffer might not be cleared yet.")

                    return

                # retry if this line is reached. it would've returned if login succeeded.
                LOG.debug("Login failed although no exception caught.")
                if not retry:
                    raise exceptions.SSHException("Unable to connect to host")

            # pxssh has a bug where the TIMEOUT exception during pxssh.login is completely eaten. i.e., it will still
            # pretend login passed even if timeout exception was thrown. So below exceptions are unlikely to be received
            # at all. But leave as is in case pxssh fix it in future releases.
            except (OSError, pexpect.TIMEOUT, pxssh.TIMEOUT, pexpect.EOF, pxssh.ExceptionPxssh) as e:
                # fail login if retry=False
                # LOG.debug("Reset session.after upon ssh error")
                # self._session.after = ''
                if not retry:
                    raise

                # don't retry if login credentials incorrect
                if "permission denied" in e.__str__():
                    LOG.error("Login credentials denied by {}. User: {} Password: {}".format(
                        self.host, self.user, self.password))
                    raise

                # print out error for more info before retrying
                LOG.info("Login failed due to error: {}".format(e))

            except:
                LOG.error("Login failed due to unknown exception!")
                raise

            self.close()
            LOG.debug("Retry in {} seconds".format(retry_interval))
            time.sleep(retry_interval)

        else:
            raise exceptions.SSHRetryTimeout("Host: {}, User: {}, Password: {}".
                                             format(self.host, self.user, self.password))

    def _is_alive(self):
        return self._session is not None and self._session.isalive()

    def _is_connected(self, fail_ok=True):
        # Connection is good if send and expect commands can be executed
        try:
            self.send()
        except OSError:    # TODO: add unit test
            return False
        return self.expect(timeout=3, fail_ok=fail_ok) == 0

    @staticmethod
    def _is_timed_out(start_time, timeout=TIMEOUT_EXPECT):
        return (time.time() - timeout) > start_time

    def send(self, cmd='', reconnect=False, reconnect_timeout=300, flush=False):
        """
        goto next line if no cmd is specified
        Args:
            cmd:
            reconnect:
            reconnect_timeout:
            flush: whether to flush out the expect buffer before sending a new command

        Returns:number of bytes sent

        """
        if flush:
            self.flush()
        cmd_for_exitcode = (cmd == EXIT_CODE_CMD)
        if cmd_for_exitcode:
            LOG.debug("Sending \'{}\'".format(cmd))
        else:
            LOG.debug("Sending command: \'{}\'".format(cmd))
        try:
            rtn = self._session.sendline(cmd)
        # TODO: use specific exception to catch unexpected disconnection with remote host such as swact
        except Exception:
            if not reconnect:
                raise
            else:
                LOG.exception("Failed to send line.")
                self.close()
                self.connect(retry_timeout=reconnect_timeout)
                rtn = self._session.sendline(cmd)

        LOG.debug("Command sent successfully")
        self.cmd_sent = cmd

        return str(rtn)

    def flush(self, timeout=3):
        """
        flush before sending the next command.
        Returns:

        """
        self.expect(fail_ok=True, timeout=timeout)

        LOG.debug("Buffer is flushed by reading out the rest of the output")

    def expect(self, blob_list=None, timeout=60, fail_ok=False, rm_date=False):
        """
        Look for match in the output. Stop if 1) match is found, 2) match is not found and prompt is reached, 3) match
        is not found and timeout is reached. For scenario 2 and 3, either throw timeout exception or return False based
        on the 'fail' argument.
        Args:
            blob_list: pattern(s) to find match for
            timeout: max timeout value to wait for pattern(s)
            fail_ok: True or False. When False: throws exception if match not found. When True: return -1 when match not
                found.
            rm_date (bool): Whether to remove the date output before expecting

        Returns: the index of the pattern matched in the output, assuming that blob can be a list.

        Examples:
            expect(): to wait for prompt
            expect('good'): to wait for a match starts with 'good'
            expect(['good', 'bad'], 10, False): to wait for a match start with 'good' or 'bad' with 10seconds timeout

        """
        if blob_list is None:
            blob_list = self.prompt

        if not isinstance(blob_list, list):
            blob_list = [blob_list]

        exit_cmd = (self.cmd_sent == EXIT_CODE_CMD)
        if not exit_cmd:
            LOG.debug("Expecting: \'{}\'...".format('\', \''.join(str(blob) for blob in blob_list)))
        else:
            LOG.debug("Expecting exit code...")

        try:
            index = self._session.expect(blob_list, timeout=timeout)
        except pexpect.EOF:
            # LOG.warning("No match found for {}!\npexpect exception caught: {}".format(blob_list, e.__str__()))
            # LOG.debug("Before: {}; After:{}".format(self._parse_output(self._session.before),
            #                                         self._parse_output(self._session.after)))
            if fail_ok:
                return -1
            else:
                LOG.warning("No match found for {}!\nEOF caught.".format(blob_list))
                raise
        except pexpect.TIMEOUT:
            if fail_ok:
                return -2
            else:
                LOG.warning("No match found for {}. \nexpect timeout.".format(blob_list))
                raise

        # Match found, reformat the outputs
        before_str = self._parse_output(self._session.before)
        after_str = self._parse_output(self._session.after)
        output = before_str + after_str
        if not self.cmd_sent == '':
            output_list = output.split('\r\n')
            output_list[0] = ''        # do not display the sent command

            if rm_date:     # remove date output if any
                if re.search(DATE_OUTPUT, output_list[-1]):
                    output_list = output_list[:-1]

            output = '\n'.join(output_list)
        self.cmd_sent = ''              # Make sure sent line is only removed once

        self.cmd_output = output
        extra_str = ''        # extra logging info
        if not exit_cmd and len(blob_list) > 1:
            extra_str = ' for \'{}\''.format(blob_list[index])

        LOG.debug("Found match{}: {}".format(extra_str, output))

        return index

    def exec_cmd(self, cmd, expect_timeout=10, reconnect=False, reconnect_timeout=300, err_only=False, rm_date=True,
                 fail_ok=True, get_exit_code=True):
        """

        Args:
            cmd:
            expect_timeout:
            reconnect:
            reconnect_timeout:
            err_only: if true, stdout will not be included in output
            rm_date (bool): weather to remove date output from cmd output before returning
            fail_ok (bool): whether to raise exception when non-zero exit-code is returned

        Returns (tuple): (exit code (int), command output (str))

        """
        LOG.debug("Executing command...")
        if err_only:
            cmd += ' 1> /dev/null'          # discard stdout
        self.send(cmd, reconnect, reconnect_timeout)
        try:
            self.expect(timeout=expect_timeout)
        except pexpect.TIMEOUT as e:
            self.send_control('c')
            self.flush(timeout=10)
            if fail_ok:
                LOG.warning(e)
            else:
                raise

        code, output = self.__process_exec_result(cmd, rm_date, get_exit_code=get_exit_code)

        if code != 0 and not fail_ok:
            raise exceptions.SSHExecCommandFailed("Non-zero return code for cmd: {}".format(cmd))

        return code, output

    def __process_exec_result(self, cmd, rm_date=True, get_exit_code=True):

        cmd_output_list = self.cmd_output.split('\n')[0:-1]  # exclude prompt
        # LOG.info("cmd output list: {}".format(cmd_output_list))
        # cmd_output_list[0] = ''                                       # exclude command, already done in expect

        if rm_date:  # remove date output if any
            if re.search(DATE_OUTPUT, cmd_output_list[-1]):
                cmd_output_list = cmd_output_list[:-1]

        cmd_output = '\n'.join(cmd_output_list)

        if get_exit_code:
            exit_code = self.get_exit_code()
            if exit_code != 0:
                LOG.warning('Issue occurred when executing \'{}\'. Exit_code: {}. Output: {}'.
                            format(cmd, exit_code, cmd_output))
        else:
            exit_code = -1
            LOG.info("Actual exit code for following cmd is unknown: {}".format(cmd))

        cmd_output = cmd_output.strip()
        return exit_code, cmd_output

    @staticmethod
    def _parse_output(output):
        if type(output) is bytes:
            output = output.decode("utf-8")
        return output

    def set_prompt(self, prompt=CONTROLLER_PROMPT):
        self.prompt = prompt

    def get_prompt(self):
        return self.prompt

    def get_exit_code(self):
        self.send(EXIT_CODE_CMD)
        self.expect(timeout=30)
        return int(self.cmd_output.splitlines()[1])

    def get_hostname(self):
        return self.exec_cmd('hostname')[1].splitlines()[0]

    def rsync(self, source, dest_server, dest, dest_user='wrsroot', extra_opts=None, pre_opts=None, timeout=60,
              fail_ok=False):
        if extra_opts:
            extra_opts_str = ' '.join(extra_opts) + ' '
        else:
            extra_opts_str = ''

        if not pre_opts:
            pre_opts = ''

        ssh_opts = 'ssh {}'.format(' '.join(RSYNC_SSH_OPTIONS))
        cmd = "{} rsync -avre \"{}\" {} {} ".format(pre_opts, ssh_opts, extra_opts_str, source)
        cmd += "{}@{}:{}".format(dest_user, dest_server, dest)
        self.send(cmd)
        index = self.expect([self.prompt, PASSWORD_PROMPT], timeout=timeout)
        if index == 1:
            self.send(self.password)
            self.expect(timeout=timeout)

        code, output = self.__process_exec_result(cmd, rm_date=True)
        if code != 0 and not fail_ok:
            raise exceptions.SSHExecCommandFailed("Non-zero return code for rsync cmd: {}".format(cmd))

        return code, output

    def scp_files_to_local_host(self, source_file, dest_password, dest_user=None, dest_folder_name=None, timeout=10):

        # Process destination info
        if dest_folder_name:
            dest_folder_name += '/'
        else:
            dest_folder_name = ''

        dest_path = ProjVar.get_var('TEMP_DIR') + dest_folder_name

        to_host = local_host.get_host_ip() + ':'
        to_user = (dest_user if dest_user is not None else local_host.get_user()) + '@'

        destination = to_user + to_host + dest_path
        scp_cmd = ' '.join(['scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -r', source_file,
                            destination]).strip()
        LOG.info("Copying files from ssh client to {}: {}".format(to_host, scp_cmd))
        self.send(scp_cmd)
        index = self.expect([self.prompt, PASSWORD_PROMPT, Prompt.ADD_HOST], timeout=timeout)
        if index == 2:
            self.send('yes')
            index = self.expect([self.prompt, PASSWORD_PROMPT], timeout=timeout)
        if index == 1:
            self.send(dest_password)
            index = self.expect()
        if not index == 0:
            raise exceptions.SSHException("Failed to scp files")

    def file_exists(self, file_path):
        return self.exec_cmd('stat ' + file_path)[0] == 0

    @contextmanager
    def login_as_root(self, timeout=10):
        self.send('sudo su -')
        index = self.expect([ROOT_PROMPT, PASSWORD_PROMPT], timeout=timeout)
        if index == 1:
            self.send(self.password)
            self.expect(ROOT_PROMPT)
        original_prompt = self.get_prompt()
        self.set_prompt(ROOT_PROMPT)
        self.set_session_timeout(timeout=0)
        try:
            yield self
        finally:
            if self.get_current_user() == 'root':
                self.set_prompt(original_prompt)
                self.send('exit')
                self.expect()

    def exec_sudo_cmd(self, cmd, expect_timeout=10, rm_date=True, fail_ok=True, get_exit_code=True):
        """
        Execute a command with sudo.

        Args:
            cmd (str): command to execute. such as 'ifconfig'
            expect_timeout (int): timeout waiting for command to return
            rm_date (bool): whether to remove date info at the end of the output
            fail_ok (bool): whether to raise exception when non-zero exit code is returned

        Returns (tuple): (exit code (int), command output (str))

        """
        cmd = 'sudo ' + cmd
        LOG.info("Executing sudo command: {}".format(cmd))
        self.send(cmd)
        index = self.expect([self.prompt, PASSWORD_PROMPT], timeout=expect_timeout)
        if index == 1:
            self.send(self.password)
            self.expect(timeout=expect_timeout)

        code, output = self.__process_exec_result(cmd, rm_date, get_exit_code=get_exit_code)
        if code != 0 and not fail_ok:
            raise exceptions.SSHExecCommandFailed("Non-zero return code for sudo cmd: {}".format(cmd))

        return code, output

    def send_control(self, char='c'):
        LOG.debug("Sending ctrl+{}".format(char))
        self._session.sendcontrol(char=char)

    def get_current_user(self):
        output = self.exec_cmd('whoami')[1]
        return output.splitlines()[0]

    def close(self):
        self._session.close(True)
        LOG.info("ssh session closed. host: {}, user: {}. Object ID: {}".format(self.host, self.user, id(self)))

    def set_session_timeout(self, timeout=0):
        self.send('TMOUT={}'.format(timeout))
        self.expect()

    def wait_for_cmd_output(self, cmd, content, timeout, strict=False, regex=False, expt_timeout=10,
                            check_interval=3, disappear=False, non_zero_rtn_ok=False):
        """
        Wait for given content to appear or disappear in cmd output.

        Args:
            cmd (str): cmd to run repeatedly until given content appears|disappears or timeout reaches
            content (str): string expected to appear|disappear in cmd output
            timeout (int): max seconds to wait for the expected content
            strict (bool): whether to perform strict search  (search is NOT case sensitive even if strict=True)
            regex (bool): whether given content is regex pattern
            expt_timeout (int): max time to wait for cmd to return
            check_interval (int): how long to wait to execute the cmd again in seconds.
            disappear (bool): whether to wait for content appear or disappear
            non_zero_rtn_ok (bool): whether it's okay for cmd to have none-zero return code. Raise exception if False.

        Returns (bool): True if content appears in cmd output within max wait time.

        """
        end_time = time.time() + timeout
        while time.time() < end_time:
            code, output = self.exec_cmd(cmd, expect_timeout=expt_timeout)
            if not non_zero_rtn_ok and code > 0:
                raise exceptions.SSHExecCommandFailed("Get non-zero return code for command: {}".format(cmd))

            content_exists = False
            if regex:
                if strict:
                    if re.match(content, output):
                        content_exists = True
                else:
                    if re.search(content, output):
                        content_exists = True
            else:
                if strict:
                    if content.lower() == output.lower():
                        content_exists = True
                else:
                    if content.lower() in output.lower():
                        content_exists = True

            if (content_exists and not disappear) or (not content_exists and disappear):
                return True

            time.sleep(check_interval)

        else:
            return False

    def wait_for_cmd_output_persists(self, cmd, content, timeout=60, time_to_stay=10, strict=False, regex=False,
                                     expt_timeout=10, check_interval=1, exclude=False, non_zero_rtn_ok=False):
        """
        Wait for given content to be included/excluded in cmd output for more than <time_to_stay> seconds.

        Args:
            cmd (str): cmd to run repeatedly until given content appears|disappears or timeout reaches
            content (str): string expected to appear|disappear in cmd output
            time_to_stay (int): how long the expected content be included/excluded from cmd output to return True
            timeout (int): max seconds to wait for content to consistently be included/excluded from cmd output
            strict (bool): whether to perform strict search  (search is NOT case sensitive even if strict=True)
            regex (bool): whether given content is regex pattern
            expt_timeout (int): max time to wait for cmd to return
            check_interval (int): how long to wait to execute the cmd again in seconds.
            exclude (bool): whether to wait for content be consistently included or excluded from cmd output
            non_zero_rtn_ok (bool): whether it's okay for cmd to have none-zero return code. Raise exception if False.

        Returns (bool): True if content appears in cmd output within max wait time.

        """
        end_time = time.time() + timeout
        while time.time() < end_time:

            stay_end_time = time.time() + time_to_stay
            while time.time() < stay_end_time:
                code, output = self.exec_cmd(cmd, expect_timeout=expt_timeout)
                if not non_zero_rtn_ok and code > 0:
                    raise exceptions.SSHExecCommandFailed("Get non-zero return code for command: {}".format(cmd))

                content_exists = False
                if regex:
                    if strict:
                        if re.match(content, output):
                            content_exists = True
                    else:
                        if re.search(content, output):
                            content_exists = True
                else:
                    if strict:
                        if content.lower() == output.lower():
                            content_exists = True
                    else:
                        if content.lower() in output.lower():
                            content_exists = True

                if (content_exists and not exclude) or (not content_exists and exclude):
                    time.sleep(check_interval)
                    continue
                else:
                    LOG.debug("Reset stay start time")
                    break
            else:
                # Did not break - meaning time to stay has reached
                return True

        else:
            return False

    def deploy_ssh_key(self, ssh_key=None):
        if ssh_key:
            self.exec_cmd("mkdir -p ~/.ssh/")
            cmd = 'grep -q "{}" {}'.format(ssh_key, AUTHORIZED_KEYS_FPATH)
            if self.exec_cmd(cmd) != 0:
                LOG.info("Adding public key to {}".format(AUTHORIZED_KEYS_FPATH))
                self.exec_cmd('echo -e "{}\n" >> {}'.format(ssh_key, AUTHORIZED_KEYS_FPATH))
                self.exec_cmd("chmod 700 ~/.ssh/ && chmod 644 {}".format(AUTHORIZED_KEYS_FPATH))


class SSHFromSSH(SSHClient):
    """
    Base class for ssh to another node from an existing ssh session
    """
    def __init__(self, ssh_client, host, user, password, force_password=True, initial_prompt=COMPUTE_PROMPT,
                 timeout=10):
        """

        Args:
            ssh_client: SSH Client object that's currently connected
            host: host to connect to from the existing ssh session
            user: username
            password: password for given user

        Returns:

        """
        super(SSHFromSSH, self).__init__(host=host, user=user, password=password, force_password=force_password,
                                         initial_prompt=initial_prompt, timeout=timeout, session=ssh_client._session)
        self.parent = ssh_client
        self.ssh_cmd = '/usr/bin/ssh{} {}@{}'.format(_SSH_OPTS, self.user, self.host)
        self.timeout = timeout
        # self._session = self.parent._session
        # self.logpath = self.parent.logpath
        # self._session.logfile = self.parent._session.logfile

    def connect(self, retry=False, retry_interval=3, retry_timeout=300, prompt=None,
                use_current=True, use_password=True, timeout=None):
        """

        Args:
            retry:
            retry_interval:
            retry_timeout:
            timeout:
            prompt:
            use_current:
            use_password

        Returns:
            return the ssh client

        """
        self.logpath = self.parent.logpath
        self._session.logfile = self.parent._session.logfile

        if timeout is None:
            timeout = self.timeout
        if prompt is None:
            prompt = self.initial_prompt

        if use_current and self._is_connected():
            LOG.info("Already connected to {} from {}. Do nothing.".format(self.host, self.parent.host))
            return

        LOG.info("Attempt to connect to {} from {}...".format(self.host, self.parent.host))
        start_time = time.time()
        end_time = start_time + retry_timeout
        while time.time() < end_time:
            self.send(self.ssh_cmd)
            try:
                if use_password:
                    res_index = self.expect([PASSWORD_PROMPT, Prompt.ADD_HOST, self.parent.get_prompt()],
                                            timeout=timeout, fail_ok=False)
                    if res_index == 2:
                        raise exceptions.SSHException("Unable to login to {}".format(self.host))
                    if res_index == 1:
                        self.send('yes')
                        self.expect(PASSWORD_PROMPT)

                    self.send(self.password)
                    self.expect(prompt, timeout=timeout)
                else:
                    res_index = self.expect([Prompt.ADD_HOST, prompt, self.parent.get_prompt()], timeout=timeout,
                                            fail_ok=False)
                    if res_index == 2:
                        raise exceptions.SSHException("Unable to login to {}".format(self.host))

                    if res_index == 0:
                        self.send('yes')
                        self.expect(prompt, timeout=timeout)
                # Set prompt for matching
                self.set_prompt(prompt)
                LOG.info("Successfully connected to {} from {}!".format(self.host, self.parent.host))
                return

            except (OSError, pxssh.TIMEOUT, pexpect.EOF, pxssh.ExceptionPxssh) as e:
                LOG.info("Exception caught when attempt to ssh to {}: {}".format(self.host, e))
                if isinstance(e, pexpect.TIMEOUT):
                    # LOG.debug("Reset _session.after for {} session".format(self.host))
                    # self._session.after = ''
                    self.parent.send_control('c')
                    self.parent.flush(timeout=3)
                # fail login if retry=False
                if not retry:
                    raise
                # don't retry if login credentials incorrect
                if "permission denied" in e.__str__().lower():
                    LOG.error("Login credentials denied by {}. User: {} Password: {}".format(
                        self.host, self.user, self.password))
                    raise

            LOG.info("Retry in {} seconds".format(retry_interval))
            time.sleep(retry_interval)
        else:
            try:
                self.parent.flush()
            except:
                pass
            raise exceptions.SSHRetryTimeout("Host: {}, User: {}, Password: {}".
                                             format(self.host, self.user, self.password))

    # def expect(self, blob_list=None, timeout=10, fail_ok=False, rm_date=False):
    #     """
    #     Look for match in the output. Stop if 1) match is found, 2) match is not found and prompt is reached, 3) match
    #     is not found and timeout is reached. For scenario 2 and 3, either throw timeout exception or return False based
    #     on the 'fail' argument.
    #     Args:
    #         blob_list(list|str): pattern(s) to expect
    #         timeout: max timeout value to wait for pattern
    #         fail_ok: True or False. When False: throws exception if match not found. When True: return -1 when match not
    #             found.
    #         rm_date (bool): Weather to remove the date output before expecting
    #
    #     Returns: the index of the pattern matched in the output, assuming that blob can be a list.
    #
    #     Examples:
    #         expect(): to wait for prompt
    #         expect('good'): to wait for a match starts with 'good'
    #         expect(['good', 'bad'], 10, False): to wait for a match start with 'good' or 'bad' with 10seconds timeout
    #
    #     """
    #     if not blob_list:
    #         blob_list = self.prompt
    #
    #     response = self.parent.expect(blob_list, timeout, fail_ok, rm_date=rm_date)
    #     self.cmd_output = self.parent.cmd_output
    #     return response

    # def send(self, cmd='', reconnect=False, reconnect_timeout=300, flush=False):
    #     if flush:
    #         self.flush()
    #     self.parent.send(cmd, reconnect, reconnect_timeout)
    #     self.cmd_sent = self.parent.cmd_sent

    def close(self, force=False):
        if force or self._is_connected():
            self.send('exit')
            self.parent.expect()
            LOG.info("ssh session to {} is closed and returned to parent session {}".
                     format(self.host, self.parent.host))
        else:
            LOG.info("ssh session to {} is not open. Flushing the buffer for parent session.".format(self.host))
            self.parent.flush()

    def _is_connected(self, fail_ok=True):
        # Connection is good if send and expect commands can be executed
        try:
            self.send()
        except OSError:    # TODO: add unit test
            return False

        index = self.expect(blob_list=[self.prompt, self.parent.get_prompt()], timeout=3, fail_ok=fail_ok)
        return 0 == index


class VMSSHClient(SSHFromSSH):

    def __init__(self, vm_ip, vm_name, vm_img_name='cgcs-guest', user=None, password=None, natbox_client=None,
                 prompt=None, timeout=20, retry=True, retry_timeout=120):
        """

        Args:
            vm_ip:
            vm_img_name:
            user:
            password:
            natbox_client:
            prompt:

        Returns:

        """
        LOG.debug("vm_image_name: {}".format(vm_img_name))
        if vm_img_name is None:
            vm_img_name = ''

        vm_img_name = vm_img_name.strip().lower()

        if not natbox_client:
            natbox_client = NATBoxClient.get_natbox_client()

        if user:
            if not password:
                password = None
        else:
            for image_name in Guest.CREDS:
                if image_name.lower() in vm_img_name.lower() or image_name.lower() in vm_name.lower():
                    vm_creds = Guest.CREDS[image_name]
                    user = vm_creds['user']
                    password = vm_creds['password']
                    break
            else:
                user = 'root'
                password = 'root'
                known_guests = list(Guest.CREDS.keys())

                LOG.warning("User/password are not provided, and VM image type is not in the list: {}. "
                            "Use root/root to login.".format(known_guests))

        if prompt is None:
            # prompt = r'.*{}\@{}.*\~.*[$#]'.format(user, str(vm_name).replace('_', '-'))
            prompt = r'.*{}\@.*\~.*[$#]'.format(user)
        super(VMSSHClient, self).__init__(ssh_client=natbox_client, host=vm_ip, user=user, password=password,
                                          initial_prompt=prompt, timeout=timeout)

        # This needs to be modified in centos case.
        if not password:
            ssh_options = " -i {}{}".format(ProjVar.get_var('KEYFILE_PATH'), _SSH_OPTS_UBUNTU_VM)
        else:
            ssh_options = _SSH_OPTS
        self.ssh_cmd = 'ssh {} {}@{}'.format(ssh_options, self.user, self.host)
        self.connect(use_password=password, retry=retry, retry_timeout=retry_timeout)
        self.exec_cmd("TMOUT=0")


class FloatingClient(SSHClient):
    def __init__(self, floating_ip, user='wrsroot', password='Li69nux*', initial_prompt=CONTROLLER_PROMPT):

        # get a list of floating ips for all known labs
        __lab_list = [getattr(Labs, attr) for attr in dir(Labs) if not attr.startswith(r'__')]
        ips = []
        for lab in __lab_list:
            ip = lab['floating ip']
            ips.append(ip)
        if not floating_ip.strip() in ips:
            raise ValueError("Invalid input. No matching floating ips found in lab.Labs class")
        super(FloatingClient, self).__init__(host=floating_ip, user=user, password=password,
                                             initial_prompt=initial_prompt)


class NATBoxClient:
    # a list of natbox dicts from lab.NatBox class
    __natbox_list = [getattr(NatBoxes, attr) for attr in dir(NatBoxes) if not attr.startswith('__')]

    # internal dict that holds the natbox client if set_natbox_client was called
    __natbox_ssh_map = {}

    _PROMPT = r'\@.*\:\~[$#]'  # use user+_PROMPT to differentiate before and after ssh to vm

    @classmethod
    def get_natbox_client(cls, natbox_ip=None):
        """

        Args:
            natbox_ip (str): natbox ip

        Returns (SSHClient): natbox ssh client

        """
        curr_thread = threading.current_thread()
        idx = 0 if isinstance(curr_thread, threading._MainThread) else int(curr_thread.name.split('-')[-1])
        if not natbox_ip:
            num_natbox = len(cls.__natbox_ssh_map)
            if num_natbox == 0:
                raise exceptions.NatBoxClientUnsetException

            if not NatBoxes.NAT_BOX_HW['ip'] in cls.__natbox_ssh_map:
                LOG.warning("More than one natbox client available, returning the first one found.")
                for ip in cls.__natbox_ssh_map:
                    if not len(cls.__natbox_ssh_map[ip]) < idx:
                        return cls.__natbox_ssh_map[ip][idx]
                raise exceptions.NatBoxClientUnsetException
            else:
                natbox_ip = NatBoxes.NAT_BOX_HW['ip']

        return cls.__natbox_ssh_map[natbox_ip][idx]   # KeyError will be thrown if not exist

    @classmethod
    def set_natbox_client(cls, natbox_ip=NatBoxes.NAT_BOX_HW['ip']):
        for natbox in cls.__natbox_list:
            ip = natbox['ip']
            if ip == natbox_ip.strip():
                curr_thread = threading.current_thread()
                idx = 0 if isinstance(curr_thread, threading._MainThread) else int(curr_thread.name.split('-')[-1])
                user = natbox['user']
                nat_ssh = SSHClient(ip, user, natbox['password'], initial_prompt=user + cls._PROMPT)
                nat_ssh.connect(use_current=False)
                nat_ssh.exec_cmd(cmd='TMOUT=0')

                if ip not in cls.__natbox_ssh_map:
                    cls.__natbox_ssh_map[ip] = []

                if len(cls.__natbox_ssh_map[ip]) == idx:
                    cls.__natbox_ssh_map[ip].append(nat_ssh)
                elif len(cls.__natbox_ssh_map[ip]) > idx:
                    cls.__natbox_ssh_map[ip][idx] = nat_ssh
                else:
                    new_ssh = SSHClient(ip, user, natbox['password'], initial_prompt=user + cls._PROMPT)
                    new_ssh.connect(use_current=False)
                    while len(cls.__natbox_ssh_map[ip]) < idx:
                        cls.__natbox_ssh_map[ip].append(new_ssh)
                    cls.__natbox_ssh_map[ip].append(nat_ssh)

                LOG.info("NatBox {} ssh client is set".format(ip))
                return nat_ssh

        raise ValueError(("No matching natbox ip found from natbox list. IP provided: {}\n"
                          "List of natbox(es) available: {}").format(natbox_ip, cls.__natbox_list))


class ControllerClient:

    # Each entry is a lab dictionary such as Labs.VBOX. For newly created dict entry, 'name' must be provided.
    __lab_attr_list = [attr for attr in dir(Labs) if not attr.startswith('__')]
    __lab_list = [getattr(Labs, attr) for attr in __lab_attr_list]
    __lab_ssh_map = {}     # item such as 'PV0': [con_ssh, ...]

    @classmethod
    def get_active_controller(cls, lab_name=None, fail_ok=False):
        """
        Attempt to match given lab or current lab, otherwise return first ssh
        Args:
            lab_name: The lab dictionary name in Labs class, such as 'PV0', 'HP380'
            fail_ok: when True: return None if no active controller was set

        Returns:

        """
        if not lab_name:
            lab_dict = ProjVar.get_var('lab')
            for lab_ in cls.__lab_list:
                if lab_dict['floating ip'] == lab_['floating ip']:
                    lab_name = lab_['short_name']
                    break
            else:
                lab_name = 'no_name'

        curr_thread = threading.current_thread()
        idx = 0 if isinstance(curr_thread, threading._MainThread) else int(curr_thread.name.split('-')[-1])
        for lab_ in cls.__lab_ssh_map:
            if lab_ == lab_name.lower():
                LOG.debug("Getting active controller client for {}".format(lab_))
                controller_ssh = cls.__lab_ssh_map[lab_][idx]
                if isinstance(controller_ssh, SSHClient):
                    return controller_ssh

        if not lab_name:
            LOG.debug("No lab ssh matched. Getting an active controller ssh client if one is set.")
            controllers = cls.get_active_controllers(fail_ok=fail_ok)
            if len(controllers) == 0:
                return None
            if len(controllers) > 1:
                LOG.warning("Multiple active controller sessions available. Returning the one for this thread.")
                LOG.debug("ssh client for {} returned".format(controllers[0].host))
                return controllers[0]

        if fail_ok:
            return None
        raise exceptions.ActiveControllerUnsetException(("The lab_name provided - {} does not have a corresponding "
                                                         "controller ssh session set").format(lab_name))

    @classmethod
    def get_active_controllers(cls, fail_ok=False):
        """ Get all the active controllers ssh sessions.

        Used when running tests in multiple labs in parallel. i.e.,get all the active controllers' ssh sessions, and
        execute cli commands on all these controllers

        Returns: list of active controllers ssh clients.

        """
        controllers = []
        for value in cls.__lab_ssh_map.values():
            if value is not None:
                controllers.append(value)

        if len(controllers) == 0 and not fail_ok:
            raise exceptions.ActiveControllerUnsetException

        return controllers

    @classmethod
    def set_active_controller(cls, ssh_client):
        """
        lab_name for new entry

        Args:
            ssh_client:

        Returns:

        """
        if not isinstance(ssh_client, SSHClient):
            raise TypeError("ssh_client has to be an instance of SSHClient!")

        for lab_ in cls.__lab_list:
            if ssh_client.host == lab_['floating ip']:
                lab_name_ = lab_['short_name']
                break
        else:
            lab_name_ = 'no_name'

        # new lab or ip address
        if lab_name_ not in cls.__lab_ssh_map:
            cls.__lab_ssh_map[lab_name_] = []

        curr_thread = threading.current_thread()
        idx = 0 if isinstance(curr_thread, threading._MainThread) else int(curr_thread.name.split('-')[-1])
        # set ssh for new lab
        if len(cls.__lab_ssh_map[lab_name_]) == idx:
            cls.__lab_ssh_map[lab_name_].append(ssh_client)
        # change existing ssh
        elif len(cls.__lab_ssh_map[lab_name_]) > idx:
            cls.__lab_ssh_map[lab_name_][idx] = ssh_client
        # fill with copy of new ssh session until list is correct length
        # (only when a different lab or ip address has also been added)
        else:
            new_ssh = SSHClient(ssh_client.host, ssh_client.user, ssh_client.password)
            new_ssh.connect(use_current=False)
            while len(cls.__lab_ssh_map[lab_name_]) < idx:
                cls.__lab_ssh_map[lab_name_].append(new_ssh)
            cls.__lab_ssh_map[lab_name_].append(ssh_client)

        LOG.info("Active controller client for {} is set. Host ip/name: {}".format(lab_name_.upper(), ssh_client.host))

    @classmethod
    def set_active_controllers(cls, *args):
        """
        Set active controller(s) for lab(s).

        Args:
            *args:ssh clients for lab(s)
                e.g.,ip_1-4_ssh , hp380_ssh

        """
        for lab_ssh in args:
            cls.set_active_controller(ssh_client=lab_ssh)


def ssh_to_controller0(ssh_client=None):
    if ssh_client is None:
        ssh_client = ControllerClient.get_active_controller()
    if ssh_client.get_hostname() == 'controller-0':
        LOG.info("Already on controller-0. Do nothing.")
        return ssh_client
    con_0_ssh = SSHFromSSH(ssh_client=ssh_client, host='controller-0', user=Host.USER, password=Host.PASSWORD,
                           initial_prompt=Prompt.CONTROLLER_0)
    con_0_ssh.connect()
    return con_0_ssh
