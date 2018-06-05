import os
import re
import socket
from telnetlib import Telnet

import pexpect

from consts.auth import HostLinuxCreds
from consts.cgcs import DATE_OUTPUT
from consts.proj_vars import ProjVar
from utils import exceptions
from utils.clients.ssh import PASSWORD_PROMPT, EXIT_CODE_CMD
from utils.tis_log import get_tis_logger, LOG


def telnet_logger(host):
    log_dir = ProjVar.get_var('LOG_DIR')
    if log_dir:
        log_dir = '{}/telnet'.format(log_dir)
        os.makedirs(log_dir, exist_ok=True)
        logpath = log_dir + '/telnet_' + host + ".log"
    else:
        logpath = None

    logger = get_tis_logger(logger_name='telnet_{}'.format(host), log_path=logpath)

    return logger

TELNET_REGEX = '(.*-[\d]+)[ login:|:~\$]'
TELNET_LOGIN_PROMPT = '[controller|compute|storage]-[\d]+ login:'
NEWPASSWORD_PROMPT = ''


class TelnetClient(Telnet):

    def __init__(self, host, prompt=None, port=0, timeout=30, hostname=None, user=HostLinuxCreds.get_user(),
                 password=HostLinuxCreds.get_password()):

        self.logger = LOG
        super(TelnetClient, self).__init__(host=host, port=port, timeout=timeout)
        # newlines for: login_prompt, port message
        if not prompt and not hostname:
            prompt = ':~\$ '
            self.send('\r\n\r\n')
            index = self.expect(TELNET_REGEX, fail_ok=True)
            if index == 0:
                hostname = re.search(TELNET_REGEX, self.cmd_output).group(1)
                prompt = '{}:~\$ '.format(hostname)

        elif not prompt:
            prompt = '{}:~\$ '.format(hostname)
        elif not hostname:
            hostname = re.search(TELNET_REGEX, prompt).group(0)

        self.flush()
        self.logger = telnet_logger(hostname) if hostname else telnet_logger(host)
        self.hostname = hostname
        self.prompt = prompt
        self.cmd_output = ''
        self.cmd_sent = ''
        self.user = user
        self.password = password
        self.logger.info('Telnet connection to {}:{} ({}) is established'.format(host, port, hostname))

    def connect(self, timeout=None, login=True, login_timeout=10, fail_ok=False):
        timeout_arg = {'timeout': timeout} if timeout else {}
        if self.eof:
            self.logger.info("Re-open telnet connection to {}:{}".format(self.host, self.port))
            self.open(host=self.host, port=self.port, **timeout_arg)

        if login:
            self.login(fail_ok=fail_ok, expect_prompt_timeout=login_timeout)
        return self.sock

    def login(self, expect_prompt_timeout=3, fail_ok=False):
        self.send()
        index = self.expect([TELNET_LOGIN_PROMPT, self.prompt], timeout=expect_prompt_timeout, fail_ok=fail_ok)
        self.flush()
        code = 0
        if index == 0:
            self.send(self.user)
            self.expect(PASSWORD_PROMPT)
            self.send(self.password)
            self.expect()
        elif index < 0:
            self.logger.warning("System is not in login page and default prompt is not found either")
            code = 1
        return code

    def initial_login(self, new_password, expect_prompt_timeout=3, fail_ok=False):
        self.send('\r\n\r\n')
        index = self.expect([TELNET_LOGIN_PROMPT, self.prompt], timeout=expect_prompt_timeout, fail_ok=fail_ok)
        self.flush()
        code = 0
        expect_index = 0
        if index == 0:
            self.send(self.user)
            self.expect(PASSWORD_PROMPT, fail_ok=fail_ok)
            self.send(self.password)
            self.expect(PASSWORD_PROMPT, fail_ok=fail_ok)
            self.send(new_password)
            self.expect(PASSWORD_PROMPT, fail_ok=fail_ok)
            self.send(new_password)
            expect_index = self.expect(fail_ok=fail_ok)
        elif index < 0:
            self.logger.warning("System is not in login page and default prompt is not found either")
            return 1

        if fail_ok and expect_index != 0:
            self.logger.warning("System did not login in successfully")
            return 1

        self.password = new_password

        return 0

    def send(self, cmd='', reconnect=False, reconnect_timeout=300, flush=False):
        if reconnect:
            self.connect(timeout=reconnect_timeout)
        if flush:
            self.flush()

        cmd_for_exitcode = (cmd == EXIT_CODE_CMD)
        is_read_only_cmd = (not cmd) or re.search('show|list|cat', cmd)
        if cmd_for_exitcode or is_read_only_cmd:
            self.logger.debug("Send: {}".format(cmd))
        else:
            self.logger.info("Send: {}".format(cmd))

        self.cmd_sent = cmd
        LOG.debug("cmd sent: {}".format(self.cmd_sent))
        if not cmd.endswith('\n'):
            cmd = '{}\n'.format(cmd)
        # self.set_debuglevel(2)
        self.write(cmd.encode())

    def send_control(self, char='c'):
        if char != 'c':
            raise NotImplemented("Only ctrl+c is supported")
        self.logger.info("Send: ctrl+{}".format(char))
        self.write(b'\x03')

    def _process_output(self, output, rm_date=False):
        if isinstance(output, bytes):
            output = output.decode(errors='ignore')
        if not self.cmd_sent == '':
            output_list = output.split('\r\n')
            output_list[0] = ''  # do not display the sent command

            if rm_date:  # remove date output if any
                if re.search(DATE_OUTPUT, output_list[-1]):
                    output_list = output_list[:-1]

            output = '\n'.join(output_list)
        self.cmd_sent = ''  # Make sure sent line is only removed once

        self.cmd_output = output
        return output

    def expect(self, blob_list=None, timeout=None, fail_ok=False, rm_date=False, searchwindowsize=None):
        if timeout is None:
            timeout = self.timeout
        if not blob_list:
            blob_list = self.prompt
        if isinstance(blob_list, (str, bytes)):
            blob_list = [blob_list]

        blobs = []
        for blob in blob_list:
            if isinstance(blob, str):
                blob = blob.encode()
            blobs.append(blob)

        try:
            index, re_obj, matched_text = Telnet.expect(self, list=blobs, timeout=timeout)
            # Reformat the output
            output = self._process_output(output=matched_text, rm_date=rm_date)
            if index >= 0:
                # Match found
                self.logger.debug("Found: {}".format(output))
                return index

            # Error handling
            self.logger.debug("No match found for: {}. Actual output: {}".format(blob_list, output))
            if self.eof:
                err_msg = 'EOF encountered before {} appear. '.format(blob_list)
                index = -1
            else:
                err_msg = "Timed out waiting for {} to appear. ".format(blob_list)
                index = -2

        except EOFError:
            err_msg = 'EOF encountered and before receiving anything. '
            index = -1

        if fail_ok:
            self.logger.warning(err_msg)
            return index

        if index == -1:
            raise exceptions.TelnetEOF(err_msg)
        elif index == -2:
            raise exceptions.TelnetTimeout(err_msg)
        else:
            raise exceptions.TelnetException("Unknown error! Please update telnet expect method")

    def flush(self):
        buffer = self.read_very_eager()
        if buffer:
            self.logger.debug("Flushed: \n{}".format(buffer.decode(errors='ignore')))
        return buffer

    def exec_cmd(self, cmd, expect_timeout=None, reconnect=False, reconnect_timeout=300, err_only=False, rm_date=False,
                 fail_ok=True, get_exit_code=True, blob=None, force_end=False, searchwindowsize=None):
        if blob is None:
            blob = self.prompt
        if expect_timeout is None:
            expect_timeout = self.timeout

        self.logger.debug("Executing command...")
        self.send(cmd, reconnect, reconnect_timeout)
        try:
            self.expect(blob_list=blob, timeout=expect_timeout, searchwindowsize=searchwindowsize)
        except pexpect.TIMEOUT as e:
            self.send_control()
            self.flush()
            if fail_ok:
                self.logger.warning(e)
            else:
                raise

        code, output = self._process_exec_result(cmd, rm_date, get_exit_code=get_exit_code)

        self.__force_end(force_end)

        if code > 0 and not fail_ok:
            raise exceptions.SSHExecCommandFailed("Non-zero return code for cmd: {}".format(cmd))

        return code, output

    def msg(self, msg, *args):
        return

    def _process_exec_result(self, cmd, rm_date=False, get_exit_code=True):
        LOG.debug("cmd output: {}".format(self.cmd_output))
        cmd_output_list = self.cmd_output.split('\n')[0:-1]  # exclude prompt
        LOG.debug("cmd output list: {}".format(cmd_output_list))
        # LOG.info("cmd output list: {}".format(cmd_output_list))
        # cmd_output_list[0] = ''                                       # exclude command, already done in expect

        if rm_date:  # remove date output if any
            if re.search(DATE_OUTPUT, cmd_output_list[-1]):
                cmd_output_list = cmd_output_list[:-1]

        cmd_output = '\n'.join(cmd_output_list)

        if get_exit_code:
            exit_code = self.get_exit_code()
            if exit_code != 0:
                self.logger.warning('Issue occurred when executing \'{}\'. Exit_code: {}. Output: {}'.
                                    format(cmd, exit_code, cmd_output))
        else:
            exit_code = -1
            self.logger.debug("Actual exit code for following cmd is unknown: {}".format(cmd))

        cmd_output = cmd_output.strip()
        return exit_code, cmd_output

    def get_exit_code(self):
        self.send(EXIT_CODE_CMD)
        self.expect(timeout=10)
        LOG.debug("echo output: {}".format(self.cmd_output))
        matches = re.findall("\n([-+]?[0-9]+)\n", self.cmd_output)
        LOG.debug("matches: {}".format(matches))
        return int(matches[-1])

    def __force_end(self, force):
        if force:
            self.flush()
            self.send_control('c')
            self.flush()

    def set_prompt(self, prompt):
        self.prompt = prompt

    def get_hostname(self):
        return self.exec_cmd('hostname')[1].splitlines()[0]

    def close(self):
        super().close()
        self.logger.info("Telnet connection closed")
