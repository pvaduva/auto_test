
# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.
# 

import time
from pytest import fixture, mark
from utils import cli
from utils import table_parser
from utils.ssh import ControllerClient
from utils.tis_log import LOG
from consts.auth import Tenant
from keywords import nova_helper, host_helper

"""
Floating OAM Address: Verify configuration and use of both the fixed and
floating OAM addresses
"""

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

@mark.sanity
def test_417_floating_oam_address():
    """
    Floating OAM Address: Verify configuration and use of both the fixed
    and floating OAM addresses.

    Setup Notes:
    - Standard 4 blade config: 2 controllers + 2 compute
    - Lab booted and configure step complete

    Test Procedure:
    1. Get the floating and fixed OAM addresses of the active controller at:
       /opt/platform/config/$SW_VERSION/cgcs_config
    2. Swact the current active Controller
    3. Wait for swact to complete
    4. Verify that the second controller is active and that the floating
       OAM IP address switched over from the first controller
    5. Reboot the second controller
    6. Check that the first controller is now active and that the floating
       OAM IP address has switched over from the second controller
    7. Do a nova serivce-list to verify the first
       controller is running as expected
    """

    LOG.tc_step("Get the configured addresses of the active controller")
    with host_helper.ssh_to_host('controller-0') as con_ssh:
        cmd = 'host-show controller-0'
        exitcode, output = cli.system(cmd, ssh_client=con_ssh,
                                      auth_info=Tenant.ADMIN,
                                      rtn_list=True, fail_ok=False,
                                      timeout=90)

    LOG.tc_step("Get the ip address of the primary controller")
    compute_table = table_parser.table(output)
    ip_value = get_column_value(compute_table, 'mgmt_ip')
    LOG.info("Configured mgmt address of active: %s" % ip_value)
    time.sleep(10)

    LOG.tc_step("Extract the floating IP address as well as the static IP addresses")
    with host_helper.ssh_to_host('controller-0') as con_ssh:
        config_path = '/opt/platform/config/16.00'
        cmd = "cat %s/cgcs_config | grep EXTERNAL_OAM_FLOATING_ADDRESS" % \
              config_path
        LOG.info("Sending command %s" % cmd)
        exitcode, answer = con_ssh.exec_cmd(cmd)
    float_ip_0 = answer.split('=', 1)[1]
    LOG.info("Configured floating address: %s" % float_ip_0)

    LOG.tc_step("Get the ip address of the secondary controller")
    with host_helper.ssh_to_host('controller-0') as con_ssh:
        cmd = 'host-show controller-1'
        exitcode, output = cli.system(cmd, ssh_client=con_ssh,
                                      auth_info=Tenant.ADMIN,
                                      rtn_list=True, fail_ok=False,
                                      timeout=90)

    compute_table = table_parser.table(output)
    ip_value = get_column_value(compute_table, 'mgmt_ip')
    LOG.info('Configured mgmt address of standby: %s' % ip_value)
    time.sleep(3)

    LOG.tc_step("Swact primary controller and ensure the secondary controller is active")
    try:
        host_helper.swact_host(hostname="controller-0", swact_start_timeout=30, fail_ok=False)
        time.sleep(10)
        host_helper._wait_for_openstack_cli_enable()
        host_helper._wait_for_host_states('controller-0', timeout=900, fail_ok=False, task='')
        host_helper._wait_for_host_states('controller-1', timeout=900, fail_ok=False, task='')
    except Exception as e:
        LOG.info('Moving management_ip to controller-1 failed: %s'
                   % (e, ))

    LOG.tc_step("ssh to new primary controller")
    LOG.tc_step("Verify the floating IP got transfered over after the swact")
    con_ssh = ControllerClient.get_active_controller()
    config_path = '/opt/platform/config/16.00'
    cmd = "cat %s/cgcs_config | grep EXTERNAL_OAM_FLOATING_ADDRESS" % \
          config_path
    LOG.info("Sending command %s" % cmd)
    exitcode, answer = con_ssh.exec_cmd(cmd)

    float_ip_1 = answer.split('=', 1)[1]
    LOG.info("Floating address on new primary controller: %s" % float_ip_1)
    assert float_ip_1 == float_ip_0

    LOG.tc_step('Reboot controller-0')
    host_helper.reboot_hosts("controller-0")

    LOG.info("""Sleeping for 10 seconds to allow controller-0 to stabilize
             while it becomes ACTIVE""")
    time.sleep(30)
    #config_helpers.wait_until_services_com_available(self, timeout=30,
                                                     #check_interval=1)
    LOG.info("Wait for controller to change state to available")
    LOG.tc_step("Verify the floating IP is the same over a reboot")
    host_helper._wait_for_openstack_cli_enable()
    host_helper._wait_for_host_states('controller-0', timeout=900, fail_ok=False, task='')
    host_helper._wait_for_host_states('controller-1', timeout=900, fail_ok=False, task='')

    time.sleep(30)
    #ssh to new primary controller
    con_ssh = ControllerClient.get_active_controller()
    config_path = '/opt/platform/config/16.00'
    cmd = "cat %s/cgcs_config | grep EXTERNAL_OAM_FLOATING_ADDRESS" % \
          config_path
    LOG.info("Sending command %s" % cmd)
    exitcode, answer = con_ssh.exec_cmd(cmd)
    float_ip_0 = answer.split('=', 1)[1]
    LOG.info("Floating address after the reboot: %s" % float_ip_0)

    #verify the floating IP got transfered over after the swact
    assert float_ip_1 == float_ip_0

    #do a nova service-list
    #sched = ''
    #service_list = self.parser.table(self.clients.nova('service-list'))
    #for value in service_list['values']:
    #    if value[1] == 'nova-scheduler' and \
    #        value[2] == 'controller-0':
    #            sched = value[5]
    #make sure the nova scheduler is up on the primary controller
    #self.assertEqual(sched, 'up', 'Nova service list for controller not up')
