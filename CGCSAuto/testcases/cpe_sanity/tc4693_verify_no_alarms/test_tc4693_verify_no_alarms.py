# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

from pytest import fixture, mark, skip, raises, fail

import copy
import datetime
import time
import paramiko
import re
import sys
import logging

from utils.tis_log import LOG
from utils import cli, exceptions


class VerifyNoAlarms():
    """Classs to verify no alarms are present after lab install
    """
    proc_list = []

    def __init__(self, host_ip):

        self.commands = []
        self.commandLns = []
        self.cmdAttrs = {}
        self.host_ip = host_ip
        self.ssh = paramiko.SSHClient()
        self.ssh.load_system_host_keys()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect("%s" % self.host_ip, username="wrsroot", password="li69nux")

    def cmd_execute(self, action, param=''):
        """
        Function to execute a command on a host machine
        """

        data = ''
        alarms_found = False

        ssh_stdin, ssh_stdout, ssh_stderr = self.ssh.exec_command("%s %s" % (action, param))
        while True:
            line = ssh_stdout.readline()
            if (line != ''):
                print(line)
                LOG.info(line)
                if (('warning' in line) or 
                    ('minor' in line) or 
                    ('major' in line) or 
                    ('critical' in line)):
                    alarms_found = True
            else:
                break

        return alarms_found

    def _list_alarms(self):
        """Method to list alarms
        """

        # list the alarms
        cmd = ("source /etc/nova/openrc; system alarm-list")
        print ("Command sent: %s" % cmd)
        result = self.cmd_execute(cmd)
        assert not result

    def list_alarms_for_host(self):
        """Check the alarms on a controller node
        """

        self._list_alarms()

@mark.parametrize('host_ip', [
                  '128.224.150.141',
                  '10.10.10.2',
                  '128.224.151.212'])
def test_tc4693_verify_no_alarms(host_ip):
    verify_no_alarms = VerifyNoAlarms(host_ip)
    verify_no_alarms.list_alarms_for_host()
