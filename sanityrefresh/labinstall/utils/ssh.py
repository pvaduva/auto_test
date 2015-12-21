#!/usr/bin/env python3.4

"""
ssh.py - SSH utilities that use pxssh and pexpect.

Copyright (c) 2015 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.
"""

import pdb
from constants import *
from .common import remove_markers
from .log import getLogger
import pexpect
#import wr_pexpect
from pexpect import pxssh
#from wr_pexpect import pxssh
import sys
import re

log = getLogger(__name__)

class SSHClient(pxssh.pxssh):
    """Initiate pexpect pxssh session.

    Inherits from pxssh, which is an extension on pxpect.
    """

    def __init__(self, tmout=SSH_EXPECT_TIMEOUT, log_path=None, echo_flag=SSH_EXPECT_ECHO, encode='utf-8'):
        """Initialize connection class.

           Only expects attributes that can be passed to the parent constructor.
           Parent constructor:
           /usr/local/lib/python3.4/dist-packages/pexpect/pxssh.py
           The parent constructor in return calls the constructor of the
           spawn class:
           /usr/local/lib/python3.4/dist-packages/pexpect/pty_spawn.py
        """

        if log_path:
            logf = open(log_path, 'a')
        else:
            logf = None

        # Chain to parent constructor
        pxssh.pxssh.__init__(self, timeout=tmout, logfile=logf, echo=echo_flag, encoding=encode)

    def connect(self, hostname, username, password, prompt=PROMPT):
        """Establish ssh connection to host."""
        try:
            log.info("Open SSH connection to {}@{}".format(username, hostname))

            self.SSH_OPTS = " -o 'StrictHostKeyChecking=no'" + \
                            " -o 'UserKnownHostsFile=/dev/null'"
            self.PROMPT = prompt
            self.force_password = True
            self.username = username
            self.hostname = hostname
            self.login(hostname, username, password, auto_prompt_reset=False, quiet=False)

        except (pxssh.ExceptionPxssh, pexpect.EOF):
            log.error("Failed to login to SSH session: {}@{}".format(username, hostname))
            self.close()

    def find_prompt(self, timeout=SSH_EXPECT_TIMEOUT):
        matched = self.prompt(timeout)
        if not matched:
            log.error("Timeout occurred: Failed to find prompt")
            sys.exit(1)

    def get_after(self):
        output = None
        after = self.after
        if after is pexpect.TIMEOUT:
            log.exception("Timeout occurred: Failed to find text after executing command")
            sys.exit(1)

        lines = after.splitlines()
        if len(lines) >= 2:
            # Remove date-timestamp and prompt
            if re.search(DATE_TIMESTAMP_REGEX, lines[-2]):
                output = "\n".join(lines[:-2])
        if output is None:
            # Remove prompt
            output = "\n".join(lines[:-1])

        return output

    def exec_cmd(self, cmd, timeout=SSH_EXPECT_TIMEOUT, expect_pattern=None, show_output=True):
        output = None
        log.info(cmd)
        self.sendline(cmd)
        if expect_pattern:
            try:
                self.expect(expect_pattern, timeout)
            except pexpect.EOF:
                log.exception("Connection closed: Reached EOF in SSH session: {}@{}".format(self.username, self.hostname))
                sys.exit(1)
            except pexpect.TIMEOUT as ex:
                log.exception("Timeout occurred: Failed to find \"{}\" in output. Output:\n{}".format(expect_pattern, self.before))
                sys.exit(1)
            else:
                output = self.match.group().strip()
                log.info("Match: " + output)
                self.find_prompt(timeout)
                return output
        else:
            self.find_prompt(timeout)
            output = self.get_after()
            rc = self.get_rc()
            if output and show_output:
                log.info("Output:\n" + output)
            log.info("Return code: " + rc)
            return (int(rc), output)

    def get_rc(self):
        rc = self.exec_cmd(RETURN_CODE_CMD, expect_pattern=RETURN_CODE_REGEX)
        return remove_markers(rc)

    def rsync(self, source, dest_user, dest_server, dest, extra_opts=None):
        if extra_opts:
            extra_opts_str = " ".join(extra_opts) + " "
        else:
            extra_opts_str = ""

        ssh_opts = '"ssh {}" '.format(" ".join(RSYNC_SSH_OPTIONS))
        cmd = "rsync -ave {} {} {} ".format(ssh_opts, extra_opts_str, source)
        cmd += "{}@{}:{}".format(dest_user, dest_server, dest)
        if self.exec_cmd(cmd, RSYNC_TIMEOUT, show_output=False)[0] != 0:
            log.error("Rsync failed")
            sys.exit(1)