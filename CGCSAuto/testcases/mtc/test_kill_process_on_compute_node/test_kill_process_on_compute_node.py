# Copyright (c) 2013-2014 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.


import logging
import time
import re
import sys
from pytest import fixture, mark, skip, raises, fail
from utils.tis_log import LOG
from utils import cli, exceptions
from utils.ssh import ControllerClient
from keywords import vm_helper, nova_helper, system_helper, host_helper, cinder_helper, glance_helper

CONTROLLER_PROMPT = '.*controller\-[01].*\$ '
PROMPT = '.* '

def get_column_value_from_multiple_columns(table, match_header_key,
                                           match_col_value, search_header_key):


    """
    Function for getting column value from multiple columns

    """
    column_value = None
    col_index = None
    match_index = None
    for header_key in table["headers"]:
        if header_key == match_header_key:
            match_index = table["headers"].index(header_key)
    for header_key in table["headers"]:
        if header_key == search_header_key:
            col_index = table["headers"].index(header_key)

    if col_index is not None and match_index is not None:
        for col_value in table['values']:
            if match_col_value == col_value[match_index]:
                column_value = col_value[col_index]
    return column_value


def get_column_value(table, search_value):
    """
    Function for getting column value

    Get value from table with two column
    :table param: parse table with two colums (dictionary)
    :search_value param: value in column for checking
    """
    column_value = None
    for col_value in table['values']:
        if search_value == col_value[0]:
            column_value = col_value[1]
    return column_value


def table(output_lines):
    """Parse single table from cli output.

    Return dict with list of column names in 'headers' key and
    rows in 'values' key.
    """
    table_ = {'headers': [], 'values': []}
    columns = None

    delimiter_line = re.compile('^\+\-[\+\-]+\-\+$')

    def _table_columns(first_table_row):
        """Find column ranges in output line.

        Return list of tuples (start,end) for each column
        detected by plus (+) characters in delimiter line.
        """
        positions = []
        start = 1  # there is '+' at 0
        while start < len(first_table_row):
            end = first_table_row.find('+', start)
            if end == -1:
                break
            positions.append((start, end))
            start = end + 1
        return positions

    if not isinstance(output_lines, list):
        output_lines = output_lines.split('\n')

    if not output_lines[-1]:
        # skip last line if empty (just newline at the end)
        output_lines = output_lines[:-1]

    for line in output_lines:
        if delimiter_line.match(line):
            columns = _table_columns(line)
            continue
        if '|' not in line:
            print('skipping invalid table line: %s' % line)
            continue
        row = []
        for col in columns:
            row.append(line[col[0]:col[1]].strip())
        if table_['headers']:
            table_['values'].append(row)
        else:
            table_['headers'] = row

    return table_


def cmd_execute(action, param='', check_params=''):
    """
    Function to execute a command on a host machine
    """

    param_found = False

    controller_ssh = ControllerClient.get_active_controller()
    controller_ssh.set_prompt(CONTROLLER_PROMPT)
    exitcode, output = controller_ssh.exec_cmd('%s %s' % (action, param), expect_timeout=900)
    print("Output: %s" % output)
    if any (val in output for val in check_params):
        param_found = True

    return param_found, output

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
    search_value = "qemu*/" + instance_num
    print("Search parameter: %s" % search_value)
    kill_cmd = "kill -9 $(ps ax | grep %s | awk '{print $1}')" % search_value

    # Get the compute
    compute_ssh = host_helper.ssh_to_host("compute-1")
    exitcode, output = compute_ssh.exec_cmd(kill_cmd, expect_timeout=900)
    print("Output: %s" % output)

    cmd = 'source /etc/nova/openrc; /usr/bin/nova show %s' % instance_name
    res, out = cmd_execute(cmd)
    vm_table = table(out)

    table_param = 'OS-EXT-STS:task_state'
    task_state = get_column_value(vm_table, table_param)

    print("task_state: %s" % task_state)
    #cls.assertEqual(task_state, 'reboot_started_hard')

    #instance_helpers.wait_until_instance_state_is_changed(cls, instance_name,
    #                                                      'ACTIVE',
    #                                                      timeout=360)


def test_092_vm_instance_recovery_kill_process_on_compute_node():
    """
    Verification
    1. Boot ubuntu VM
    2. VM Instance Recovery: "kill -9" kvm process on compute node,
       ensure instance restarts automatically
    3. ping <private_ip> (from controller-0)
    4. ssh ubuntu@<mgmt_ip>
    5. kill -9 $(ps ax | grep qemu*/instance-00000001 | awk '{print $1}')
    6. ping <private_ip> (from controller-0)
    """


    vm_image = 'cgcs-guest'
    network_type = 'tenant2-mgmt-net'
    vol_size = 8

    # Get the image uuid from glance
    image_id = glance_helper.get_image_id_from_name(name=vm_image, strict=False)

    # Create volume containing the image
    vol_id = cinder_helper.create_volume(name='vol_' + vm_image, image_id=image_id, size=vol_size)[1]

    # Create ubuntu instances
    print("Create vm instances")
    vm_id = vm_helper.boot_vm(name=vm_image, source='volume', source_id=vol_id)[1]

    # Get the ip adress of the instance
    LOG.debug("Get private IP address of the vm instance")
    cmd = 'source /etc/nova/openrc; /usr/bin/nova show %s' % vm_id
    res, out = cmd_execute(cmd)
    stats_table = table(out)
    host_ip = get_column_value(stats_table,'%s network' % (network_type))
    private_ip = host_ip.split(',')[0]
    print("Host IP address for instance: %s" % private_ip[0])
    time.sleep(10)

    print("Check that VM responds on pings")
    ping_results, res_dict = vm_helper.ping_vms_from_natbox(vm_id)
    print("Ping result: %s" % res_dict)

    LOG.debug("Get search value")
    cmd = 'source /etc/nova/openrc; /usr/bin/nova show %s' % vm_id
    res, out = cmd_execute(cmd)
    vm_table = table(out)

    table_param = 'OS-EXT-SRV-ATTR:instance_name'
    instance_number = get_column_value(vm_table, table_param)
    print("Instance id: %s" % instance_number)

    LOG.debug("Kill qemu* process corresponding to the instance")
    LOG.debug("Check that instance restarts automatically")

    # Kill the process on the compute node
    kill_instance_process(instance_num=instance_number,
                          instance_name=vm_id)

    # Verify that the vm has been respawned
    print("Check that VM has been respawned and responds to pings")
    time.sleep(10)
    ping_results, res_dict = vm_helper.ping_vms_from_natbox(vm_id)
    print("Ping respawned VM result: %s" % res_dict)





