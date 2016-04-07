# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

import copy
import datetime
import time
import paramiko
import re
from pytest import fixture, mark, skip, raises, fail
from utils.tis_log import LOG
from utils import cli, exceptions


class VerifyServices():
    """Class to test services and functions
    """

    def __init__(self, host_ip):
        self.host_ip = host_ip
        self.ssh = paramiko.SSHClient()
        self.ssh.load_system_host_keys()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect("%s" % self.host_ip, username="wrsroot", password="li69nux")


    def cmd_execute(self, action, param='', check_params=''):
        """
        Function to execute a command on a host machine
        """

        data = ''
        param_found = False

        ssh_stdin, ssh_stdout, ssh_stderr = self.ssh.exec_command("%s %s" % (action, param))
        while True:
            line = ssh_stdout.readline()
            if (line != ''):
                print (line)
                if any (val in line for val in check_params):
                    param_found = True
            else:
                break

        return param_found

    def _list_services(self):
        """Method to list services
        """

        result = False
        cmd = ("source /etc/nova/openrc; nova service-list")
        try:
            print ("Command sent: %s" % cmd)
            check_params = ["nova-scheduler", 
                             "nova-cert",
                             "nova-conductor",
                             "nova-consoleauth",
                             "nova-scheduler",
                             "nova-compute"]
            result = self.cmd_execute(cmd, param='', check_params = check_params)

        except Exception as e:
             print ("Test result: Failed")
             print("Exception: %s" % e)

        return result

    def _list_subfunctions(self, host):
        """Method to list a host subfunctions
        """

        result = False

        cmd = ("source /etc/nova/openrc; system host-show %s | grep subfunctions" % host)
        print ("Command sent: %s" % cmd)
        check_params = ["controller", "compute"]
        result = self.cmd_execute(cmd, param='', check_params=check_params)
        
        return result


    def test_check_services_on_a_node(self):
        """Check the alarms on a controller node
        """

        host_list = ['controller-1', 'controller-0']

        ret_1 = self._list_services()

        for item in host_list:
            ret_2 = self._list_subfunctions(item)
            if ret_2 == False:
                break  

        if (ret_1 == False) or (ret_2 == False):
            print ("Test result: Failed")
            assert 1==2
        else:
            print ("Test result: Passed")


@mark.parametrize('host_ip', [
                  '128.224.150.141',
                  '10.10.10.2',
                  '128.224.151.212'])
def test_tc4694_verify_services_and_functions(host_ip):
    verify_services = VerifyServices(host_ip)
    verify_services.test_check_services_on_a_node()
