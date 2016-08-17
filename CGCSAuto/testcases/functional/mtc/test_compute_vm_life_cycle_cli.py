# Copyright (c) 2013-2014 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

import time
from pytest import fixture, mark, skip, raises, fail
from utils.tis_log import LOG
from utils import cli, exceptions
from utils.ssh import ControllerClient
from utils import table_parser
from consts.auth import Tenant
from keywords import vm_helper, nova_helper, system_helper, host_helper, cinder_helper
from testfixtures.resource_mgmt import ResourceCleanup

ubuntu_vm_login = 'ubuntu'
ubuntu_passwd = 'ubuntu'


@fixture(scope='function')
def check_computes_availability(request):
    """"""

    # action = 'lock'
    # hosts_table = table_parser.table(cli.system('host-list', ssh_client=None))
    # compute_list = get_active_computes(hosts_table)

    # Restore the host states
    def unlock_computes():

        # action = 'unlock'
        # status = 'available'
        # hosts_table = table_parser.table(cli.system('host-list', ssh_client=None))
        hosts = host_helper.get_hypervisors(state='down')
        host_helper.unlock_hosts(hosts)
        # for line in hosts_table['values']:
        #     if line[2] == 'compute' and line[3] != 'unlocked':
        #         comp_name = line[1]
        #         cli.system('host-{} {}'.format(action, comp_name), ssh_client=None)
        #         host_helper._wait_for_host_states(comp_name, timeout=600,
        #                                           availability=status,
        #                                           check_interval=10,
        #                                           con_ssh=None)

    request.addfinalizer(unlock_computes)


def get_active_computes(host_table):
    """
    Method for getting list of active computes

    :param host_table: system host-list table
    :return  list of active compute nodes names

    :example: host_list_table = self.parser.table(self.clients.sysinv('host-list'))
              compute_list = cli_helpers.get_active_computes(host_list_table)
    """
    computes_list = []
    for line in host_table['values']:
        if line[2] == 'compute' and line[3] == 'unlocked':
            if line[4] == 'enabled':
                if line[5] == 'available' or line[5] == 'degraded':
                    computes_list.append(line[1])
    return computes_list

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

def wait_until_instance_state_is_changed(instance_name, status,
                                         field='status', timeout=60, delay=0.3,
                                         master_host='controller-0'):
    """
    Function for waiting until instance status is changed
    """

    end_time = time.time() + timeout
    while True:
        if time.time() < end_time:
            if master_host == 'controller-0':
                instance_table = \
                    table_parser.table(cli.nova('show {}'.format(instance_name)))
            else:
                con_ssh = ControllerClient.get_active_controller()
                cmd = 'nova show %s' % instance_name
                exitcode, output = con_ssh.exec_cmd(cmd)
                instance_table = \
                table_parser.table(output)
            inst_status = get_column_value(instance_table, field)
            if inst_status == status:
                break
            elif inst_status == "ERROR":
                msg = "Server %s failed to build and is in ERROR status" % \
                    instance_name
                return False
            time.sleep(delay)
        else:
            message = "State wasn't changed to expected %s" % status
            return False

def _lock_unlock_computes_except_one(host_name, action='lock'):
    """"""
    # hosts_table = table_parser.table(cli.system('host-list', ssh_client=None))
    # compute_list = get_active_computes(hosts_table)
    compute_list = host_helper.get_hypervisors()
    print(compute_list)

    if action == 'unlock':
        host_helper.unlock_hosts(compute_list)
    elif action == 'lock':
        for comp_name in compute_list:
            if comp_name != host_name:
                host_helper.lock_host(comp_name)
            # cli.system('host-{} {}'.format(action, comp_name), ssh_client=None)

    # status = '%sed' % (action,)
    #
    # for comp_name in compute_list:
    #     if comp_name != host_name:
    #         host_helper._wait_for_host_states(comp_name, timeout=600,
    #                                           administrative=status,
    #                                           check_interval=10,
    #                                           con_ssh=None)

def launch_instance_on_compute(network_name=None,
                               flavor=None,
                               host_name=None,
                               image_name=None,
                               **instance_names):
    """
    Function for launching VM instance on specific compute node and
    check VM host value

    :network_name param: name of network (public or private)
    :flavor param:  flavour id
    :host_name param: name of required  host (compute-0 or compute-1)
    :image_name param: name launching image
    :instance_names param: names of instances that should be created

    instance_helpers.launch_instance_on_compute(self, network_name='private',
                flavor=1, host_name='compute-0', image_name='wrk5-avp',
                instance_name1='wrl5-test', instance_name2='wrl5-test-1')
    """


    if not Tenant.ADMIN:
        net_label_name = '-'.join([tenant.name, 'mgmt-net'])
    else:
        net_label_name = network_name + '-net0'

    LOG.tc_step('Locking unused computes')
    _lock_unlock_computes_except_one(host_name)

    LOG.tc_step('Booting instances on compute')
    vm_ids = []
    for name in instance_names:

        vm_id = vm_helper.boot_vm(name=instance_names[name])[1]
        ResourceCleanup.add('vm', vm_id)
        vm_ids.append(vm_id)
        wait_until_instance_state_is_changed(vm_id,'ACTIVE', timeout=120)

    LOG.tc_step('Verify instances are running')
    time.sleep(10)
    for vm_id in vm_ids:
        show_instance_table = table_parser.table(cli.nova('show {}'.format(vm_id),
                                                          ssh_client=None, auth_info=Tenant.ADMIN))

        search_name = table_parser.get_values(show_instance_table,
                                              'Value',
                                              Property='OS-EXT-SRV-ATTR:host')[0]
        assert host_name == search_name
        search_name = table_parser.get_values(show_instance_table,
                                              'Value',
                                              Property='OS-EXT-SRV-ATTR:hypervisor_hostname')[0]
        assert host_name == search_name

    LOG.tc_step('Unlocking all computes')
    _lock_unlock_computes_except_one(host_name, action='unlock')

    # LOG.tc_step('Deleting all instances')
    # for vm_id in vm_ids:
    #     vm_helper.delete_vms(vm_id, delete_volumes=True)

def check_process_exists(cmd_output=None, process_name=None,
                         existence='+'):
    count = 0
    lines = []
    for line in cmd_output.split('\n'):
        if process_name in line:
            count = count + 1
            lines.append(line)
    if existence == '+':
        LOG.info('Expected process: %s' % lines)
        if count == 0:
            LOG.info("Expected process doen't exist")
        assert count != 0
    else:
        LOG.info('Unexpected process: %s' % lines)


@mark.usefixtures('check_computes_availability')
def test_435_launching_guest_instances_on_first_compute():
    """
    Test launching Guest instances (ubuntu) on 1st Compute

    nova boot --key_name=controller-0 --flavor=1
              --availability-zone=nova-compute:compute-0
              --nic net-id=<private_net_id> --nic net-id=<internal_net_id>
              --image=ubuntu-precise-amd64 ubuntu-test
    nova boot --key_name=controller-0 --flavor=1
              --availability-zone=nova-compute:compute-0
              --nic net-id=<private_net_id> --nic net-id=<internal_net_id>
              --image=ubuntu-precise-amd64 ubuntu-test-1
    Verification Steps
    1. lock all computes except first one
    2. boot 2 ubuntu VMs
    """
    vm_name1 = 'ubuntu-test'
    vm_name2 = 'ubuntu-test-1'
    image_name = 'ubuntu-precise-amd64'
    compute_name = 'compute-0'

    LOG.info('Booting ubuntu image on first compute')
    launch_instance_on_compute(network_name='private',
                                flavor=2,
                                host_name=compute_name,
                                image_name=image_name,
                                instance_name1=vm_name1,
                                instance_name2=vm_name2)


@mark.usefixtures('check_computes_availability')
def test_437_launching_guest_instances_on_second_compute():
    """
    Test launching Guest ubuntu instances on 2nd Compute

    Verification
    1. Boot 2 VMS with
    nova boot --key_name=controller-0 --flavor=1
              --availability-zone=nova-compute:compute-1
              --nic net-id=<public_net_id> --nic net-id=<internal_net_id>
              --image=ubuntu-precise-amd64 ubuntu-test
    nova boot --key_name=controller-0 --flavor=1
              --availability-zone=nova-compute:compute-1
              --nic net-id=<public_net_id> --nic net-id=<internal_net_id>
              --image=ubuntu-precise-amd64 ubuntu-test-1
    2. Verify VMs successfully boot
    """
    vm_name1 = 'ubuntu-test'
    vm_name2 = 'ubuntu-test-1'
    image_name = 'ubuntu-precise-amd64'
    comp_name = "compute-1"
    LOG.info('Booting ubuntu VM on second compute')
    launch_instance_on_compute(network_name='private',
                                flavor=2,
                                host_name=comp_name,
                                image_name=image_name,
                                instance_name1=vm_name1,
                                instance_name2=vm_name2)


def test_438_launching_cgcs_guest_instances_on_second_compute():
    """
    Test launching Guest cgcs-guest instances on 2nd Compute

    Verification
    1. Boot 2 VMS with
    nova boot --key_name=controller-0 --flavor=1
              --availability-zone=nova-compute:compute-1
              --nic net-id=public_net_id --nic net-id=internal_net_id
              --image=wrl5-avp wrl5-avp-test
    nova boot --key_name=controller-0 --flavor=1
              --availability-zone=nova-compute:compute-1
              --nic net-id=public_net_id --nic net-id=internal_net_id
              --image=wrl5-avp wrl5-avp-test-1
    2. Verify VMs successfully boot
    """
    vm_name1 = 'wrl5-avp-test'
    vm_name2 = 'wrl5-avp-test1'
    comp_name = 'compute-1'
    LOG.debug('Booting cgcs_guest VM on second compute')
    launch_instance_on_compute(network_name='public',
                                flavor=101,
                                host_name=comp_name,
                                image_name='wrl5-avp',
                                instance_name1=vm_name1,
                                instance_name2=vm_name2)
