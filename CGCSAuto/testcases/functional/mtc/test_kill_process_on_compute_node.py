# Copyright (c) 2013-2014 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

import time
import re
import sys
from pytest import fixture, mark, skip, raises, fail
from testfixtures.fixture_resources import ResourceCleanup
from utils.tis_log import LOG
from utils import cli, exceptions, table_parser
from utils.ssh import ControllerClient
from keywords import vm_helper, nova_helper, system_helper, host_helper, cinder_helper, glance_helper


def kill_instance_process(instance_num=None, instance_name=None):
    """
    Function for killing instance process

    :user param:  user name for ssh
    :ip_address param:  IP address value
    :passwd param:  password for ssh
    :instance_num param:  instance name id from the table (instance-00000092)
    :location param: instance location, host name
    :instance_name param: Name of created instance

    :example1: network_helpers.kill_instance_process(self, user="root",
                    ip_address=host_ip_value, passwd="root",
                    instance_num='instance-00000092', instance_name='wtl5-0')
    :example2: network_helpers.kill_instance_process(self, user="root",
                    location='compute-0', passwd="root",
                    instance_num='instance-00000092', instance_name='wrl5-0')
    """
    search_value = "qemu.*" + instance_num
    LOG.info("Search parameter: %s" % search_value)
    kill_cmd = "kill -9 $(ps ax | grep %s | grep -v grep | awk '{print $1}')" % search_value

    # Get the compute
    vm_host = nova_helper.get_vm_host(instance_name)
    with host_helper.ssh_to_host(vm_host) as host_ssh:
        exitcode, output = host_ssh.exec_sudo_cmd(kill_cmd, expect_timeout=900)
        LOG.info("Output: %s" % output)

    table_param = 'OS-EXT-STS:task_state'
    task_state = nova_helper.get_vm_nova_show_value(instance_name, field=table_param)

    LOG.info("task_state: %s" % task_state)


def test_092_vm_instance_recovery_kill_process_on_compute_node():
    """
    Verification
    1. Boot tis VM
    2. VM Instance Recovery: "kill -9" kvm process on compute node,
       ensure instance restarts automatically
    3. ping <private_ip> (from controller-0)
    4. ssh to vm
    5. kill -9 $(ps ax | grep qemu.*instance-00000001 | awk '{print $1}')
    6. ping <private_ip> (from controller-0)
    """

    # Create ubuntu instances
    LOG.tc_step("Create vm instances")
    vm_id = vm_helper.boot_vm(cleanup='function')[1]

    LOG.tc_step("Check that VM responds on pings")
    ping_results, res_dict = vm_helper.ping_vms_from_natbox(vm_id)

    table_param = 'OS-EXT-SRV-ATTR:instance_name'
    instance_number = nova_helper.get_vm_nova_show_value(vm_id, table_param)
    LOG.info("Instance id: %s" % instance_number)

    LOG.debug("Kill qemu* process corresponding to the instance")
    LOG.debug("Check that instance restarts automatically")

    # Kill the process on the compute node
    kill_instance_process(instance_num=instance_number,
                          instance_name=vm_id)

    # Verify that the vm has been respawned
    LOG.tc_step("Check that VM has been respawned and responds to pings")
    assert vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    LOG.info("Ping respawned VM result: %s" % res_dict)





