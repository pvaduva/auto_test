import configparser
import yaml
import setups
from consts import lab
from consts.auth import HostLinuxCreds
from keywords import vlm_helper, host_helper
from utils.clients.ssh import SSHClient, CONTROLLER_PROMPT, ControllerClient, NATBoxClient, PASSWORD_PROMPT, \
    SSHFromSSH
from utils import table_parser
import os

def env_config_generate(floatingIP):
    con_ssh = ControllerClient.get_active_controller()
    con_ssh.connect()
    con_ssh.exec_cmd('source /etc/nova/openrc')
    projectID= con_ssh.exec_cmd('openstack project list')
    projectID=table_parser.table(projectID[1])
    projectID_admin=table_parser._get_values(projectID,'Name','admin','ID')
    projectID_admin=projectID_admin.pop(0)
    config = configparser.ConfigParser()
    config.optionxform = str
    config [None]= {'# Project-level authentication scope (name or ID), recommend admin project.':'',
                        'export OS_PROJECT_NAME': 'admin',
                        '# For identity v2, it uses OS_TENANT_NAME rather than OS_PROJECT_NAME.':'',
                        'export OS_TENANT_NAME' :'admin',
                        '# Authentication username, belongs to the project above, recommend admin user.':'',
                        'export OS_USERNAME':'admin',
                        '# Authentication password. Use your own password':'',
                        'export OS_PASSWORD':'Li69nux*',
                        '# Authentication URL, one of the endpoints of keystone service. If this is v3 version, \n# there need some extra variables as follows.' : '',
                        'export OS_AUTH_URL' : "'http://"+floatingIP+":5000/v3'",
                        '# Default is 2.0. If use keystone v3 API, this should be set as 3.': '',
                        'export OS_IDENTITY_API_VERSION':'3',
                        '# Domain name or ID containing the user above. \n# Command to check the domain: openstack user show <OS_USERNAME>':'',
                        'export OS_USER_DOMAIN_NAME' :'Default',
                        '# Domain name or ID containing the project aove.':'',
                        '# Command to check the domain: openstack project show <OS_PROJECT_NAME>':'',
                        'export OS_PROJECT_DOMAIN_NAME':'Default',
                        '# Special environment parameters for https. \n# If using https + cacert, the path of cacert file should be provided. \n# The cacert file should be put at $DOVETAIL_HOME/pre_config. \n#export OS_CACERT=/home/opnfv/dovetail/pre_config/cacert.pem \n\n# If using https + no cacert, should add OS_INSECURE environment parameter.':'',
                        'export OS_INSECURE':'True',
                        "export DOVETAIL_HOME":'/home/dovetail',
                        'export OS_PROJECT_ID': projectID_admin,
                        'export OS_REGION_NAME':'"RegionOne"'}

    with open('${DOVETAIL_HOME}/pre_config/env_config.sh', 'w') as configfile:
      config.write(configfile, space_around_delimiters=False)


def pod_generate_2plus2(n1ip, n2ip, n3ip, n4ip):
    sample = '''nodes:
-
    name: node1
    role: Controller
    ip: 128.224.151.192
    user: root
    password: Li69nux*
    # key_filename: /home/dovetail/pre_config/id_rsa
-
    name: node2
    role: Controller
    ip: 192.168.204.4
    user: root
    password: Li69nux*
    # key_filename: /home/dovetail/pre_config/id_rsa
-
    name: node3
    role: Compute
    ip: 192.168.204.175
    user: root
    password: Li69nux*
    # key_filename: /home/dovetail/pre_config/id_rsa
-
    name: node4
    role: Compute
    ip: 192.168.204.208
    user: root
    password: Li69nux*
    # key_filename: /home/dovetail/pre_config/id_rsa
'''
    yaml.load(sample)

    config = {'nodes': [{'name': 'node1', 'role': 'Controller', 'ip': n1ip, 'user': 'root', 'password': 'Li69nux*'},
                        {'name': 'node2', 'role': 'Controller', 'ip': n2ip, 'user': 'root', 'password': 'Li69nux*'},
                        {'name': 'node3', 'role': 'Compute', 'ip': n3ip, 'user': 'root', 'password': 'Li69nux*'},
                        {'name': 'node4', 'role': 'Compute', 'ip': n4ip, 'user': 'root', 'password': 'Li69nux*'}]}

    with open('${DOVETAIL_HOME}/pre_config/pod.yaml', 'w') as yaml_file:
        yaml_file.write(yaml.dump(config, default_flow_style=False))
    return config


def tempest_conf_generate_2plus2():
    sample = '''compute:
  # The minimum number of compute nodes expected.

  #   # This should be no less than 2 and no larger than the compute nodes the SUT actually has.
  min_compute_nodes: 2
  #
  # Expected device name when a volume is attached to an instance.
  volume_device_name: vdb
'''
    sample=yaml.load(sample)
    with open('${DOVETAIL_HOME}/pre_config/tempest_conf.yaml', 'w') as yaml_file:
        yaml_file.write(yaml.dump(sample, default_flow_style=False))



def fix_sshd_file(con_ssh):

    con_ssh.exec_sudo_cmd("sed -ie 's/PermitRootLogin no/PermitRootLogin yes/g' /etc/ssh/sshd_config")
    con_ssh.exec_sudo_cmd("sed -ie 's/Match User root/#Match User root/g' /etc/ssh/sshd_config")
    con_ssh.exec_sudo_cmd("sed -ie 's/ PasswordAuthentication no/ #PasswordAuthentication no/g' /etc/ssh/sshd_config")
    con_ssh.exec_sudo_cmd("sed -ie 's/Match Address/#Match Address/g' /etc/ssh/sshd_config")
    con_ssh.exec_sudo_cmd("sed -ie 's/PermitRootLogin without-password/#PermitRootLogin without-password/g' /etc/ssh/sshd_config")


##############################
# main
##############################
def test():
    #test_host = input("What lab will you be running Dovetail on: ")

    os.system("export DOVETAIL_HOME=/home/dovetail")
    os.system('mkdir -p ${DOVETAIL_HOME}/pre_config')
    lab_info= vlm_helper.get_lab_dict()
    controller0_ip= lab_info.get('controller-0 ip', 'xyz')

    floatingIP = lab_info.get('floating ip', 'xyz')
    controller1_ip =lab_info.get('controller-1 ip', 'xyz')

    con_ssh = ControllerClient.get_active_controller()
    con_ssh.connect()
    compute0_ip= con_ssh.exec_cmd('nslookup compute-0')

    compute0_ip = compute0_ip[1]
    compute0_ip = compute0_ip.split('Address')
    compute0_ip=compute0_ip[-1]
    compute0_ip=compute0_ip[2:]

    compute1_ip = con_ssh.exec_cmd('nslookup compute-1')
    compute1_ip = compute1_ip[1]
    compute1_ip = compute1_ip.split('Address')
    compute1_ip = compute1_ip[-1]
    compute1_ip = compute1_ip[2:]

    valid = False
    pod_generate_2plus2('192.168.204.3','192.168.204.3',compute0_ip,compute1_ip)
    tempest_conf_generate_2plus2()
    env_config_generate(floatingIP)

    password = HostLinuxCreds.get_password()

    with host_helper.ssh_to_host('controller-0') as con_ssh:
        fix_sshd_file(con_ssh)
        con_ssh.exec_cmd('wall Fixed controller-0')
        con_ssh.exec_sudo_cmd("printf '" + password + "\n" + password + "\n" + password + "\n' | passwd root", )
        con_ssh.exec_sudo_cmd('systemctl restart sshd')
        # con_ssh.close()
        # input("press enter to continue")

    with host_helper.ssh_to_host('controller-1') as con_ssh:
        fix_sshd_file(con_ssh)
        con_ssh.exec_cmd('wall fixed controller-1')
        con_ssh.exec_sudo_cmd("printf '" + password + "\n" + password + "\n" + password + "\n' | passwd root", )
        con_ssh.exec_sudo_cmd('systemctl restart sshd')

        # con_ssh.close()
        # input("press enter to continue")

    with host_helper.ssh_to_host('compute-0') as con_ssh:
        fix_sshd_file(con_ssh)
        con_ssh.exec_cmd('wall fixed compute-0')
        con_ssh.exec_sudo_cmd("printf '" + password + "\n" + password + "\n" + password + "\n' | passwd root", )
        con_ssh.exec_sudo_cmd('systemctl restart sshd')

        # con_ssh.close()
        # input("press enter to continue")



    with host_helper.ssh_to_host('compute-1') as con_ssh:
        fix_sshd_file(con_ssh)
        con_ssh.exec_cmd('wall fixed compute-1')
        con_ssh.exec_sudo_cmd("printf '" + password + "\n" + password + "\n" + password + "\n' | passwd root", )
        con_ssh.exec_sudo_cmd('systemctl restart sshd')

        # con_ssh.close()
        # input("press enter to continue")


    con_ssh = ControllerClient.get_active_controller()
    con_ssh.connect()

    stdout=con_ssh.exec_cmd('ps -fC nova-api | grep -v UID | wc')
    stdout=stdout[1]
    stdout=stdout.split()
    stdout=stdout[0]
    filepath=os.system("printf 'kumuluz\n' | sudo find / -name monitor_process.py")

    monitor = '''##############################################################################
# Copyright (c) 2015 Huawei Technologies Co.,Ltd. and others
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Apache License, Version 2.0
# which accompanies this distribution, and is available at
# http://www.apache.org/licenses/LICENSE-2.0
##############################################################################
from __future__ import absolute_import
import logging
import yardstick.ssh as ssh

from yardstick.benchmark.scenarios.availability.monitor import basemonitor

LOG = logging.getLogger(__name__)


class MonitorProcess(basemonitor.BaseMonitor):
    """docstring for MonitorApi"""

    __monitor_type__ = "process"

    def setup(self):
        host = self._context[self._config["host"]]

        self.connection = ssh.SSH.from_node(host, defaults={"user": "root"})
        self.connection.wait(timeout=600)
        LOG.debug("ssh host success!")
        self.check_script = self.get_script_fullpath(
            "ha_tools/check_process_python.bash")
        self.process_name = self._config["process_name"]

    def monitor_func(self):
        with open(self.check_script, "r") as stdin_file:
            exit_status, stdout, stderr = self.connection.execute(
                "sudo /bin/sh -s {0}".format(self.process_name),
                stdin=stdin_file)

        # if not stdout or int(stdout) < self.monitor_data[self.process_name]:
            # LOG.info("the (%s) processes are in recovery, %d < %d !", self.process_name, int(stdout), self.monitor_data[self.process_name])
            # return False

        if self.process_name == "nova-api":
           if not stdout or int(stdout) < '''+stdout+''':
               LOG.info("the (%s) processes are in recovery, %d < %d !", self.process_name, int(stdout), '''+stdout+''')
               return False
        else:
           if not stdout or int(stdout) < self.monitor_data[self.process_name]:
               LOG.info("the (%s) processes are in recovery, %d < %d !", self.process_name, int(stdout), self.monitor_data[self.process_name])
               return False

        LOG.info("the (%s) processes have been fully recovered!",
                 self.process_name)
        return True

    def verify_SLA(self):
        LOG.debug("the _result:%s", self._result)
        outage_time = self._result.get('outage_time', None)
        max_outage_time = self._config["sla"]["max_recover_time"]
        if outage_time > max_outage_time:
            LOG.error("SLA failure: %f > %f", outage_time, max_outage_time)
            return False
        else:
            LOG.info("the sla is passed")
            return True


def _test():    # pragma: no cover
    host = {
        "ip": "10.20.0.5",
        "user": "root",
        "key_filename": "/root/.ssh/id_rsa"
    }
    context = {"node1": host}
    monitor_configs = []
    config = {
        'monitor_type': 'process',
        'process_name': 'nova-api',
        'host': "node1",
        'monitor_time': 1,
        'sla': {'max_recover_time': 5}
    }
    monitor_configs.append(config)

    p = basemonitor.MonitorMgr()
    p.init_monitors(monitor_configs, context)
    p.start_monitors()
    p.wait_monitors()
    p.verify_SLA()


if __name__ == '__main__':    # pragma: no cover
    _test()
'''

    file = open(filepath, 'w+')
    file.write(monitor)
    os.system('export DOVETAIL_HOME=/home/dovetail')
    os.system('source ${DOVETAIL_HOME}/pre_config/env_config.sh')
    os.system("printf 'kumuluz\n' | sudo docker run --privileged=true -it -e DOVETAIL_HOME=$DOVETAIL_HOME -v $DOVETAIL_HOME:$DOVETAIL_HOME -v /var/run/docker.sock:/var/run/docker.sock opnfv/dovetail:ovp.1.0.0 /bin/bash")
    os.system('dovetail run --testsuite ovp.1.0.0')

