# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

from pytest import fixture, mark, skip, raises, fail
from utils.tis_log import LOG
from utils.ssh import ControllerClient
from keywords import host_helper


CONTROLLER_PROMPT = '.*controller\-[01].*\$ '



def cmd_execute(action, param='', check_params=''):
    """
    Function to execute a command on a host machine
    """

    param_found = False

    controller_ssh = ControllerClient.get_active_controller()
    controller_ssh.set_prompt(CONTROLLER_PROMPT)
    exitcode, output = controller_ssh.exec_cmd('%s %s' % (action, param), expect_timeout=20, reconnect=True)
    print("Output: %s" % output)
    if any (val in output for val in check_params):
        param_found = True

    return param_found

def list_services():
    """
    Method to list services
    """

    result = False
    LOG.tc_step("List the available nova services")

    cmd = ("source /etc/nova/openrc; nova service-list")
    try:
        print ("Command sent: %s" % cmd)
        check_params = ["nova-scheduler", 
                        "nova-cert",
                        "nova-conductor",
                         "nova-consoleauth",
                         "nova-scheduler",
                         "nova-compute"]
        result = cmd_execute(cmd, param='', check_params = check_params)

    except Exception as e:
         print ("Test result: Failed")
         print("Exception: %s" % e)

    return result

def list_subfunctions(host):
    """
    Method to list a host subfunctions
    """

    result = False

    LOG.tc_step("List the available host subfunctions")
    cmd = ("source /etc/nova/openrc; system host-show %s | grep subfunctions" % host)
    print ("Command sent: %s" % cmd)
    check_params = ["controller", "compute"]
    result = cmd_execute(cmd, param='', check_params=check_params)
        
    return result

@mark.cpe_sanity
def test_tc4694_verify_services_and_functions():
    """Check the services on a controller node
    """

    host_list = ['controller-1', 'controller-0']
    test_result = True

    con_ssh = ControllerClient.get_active_controller()
    if not con_ssh.get_hostname() == 'controller-0':
        host_helper.swact_host()

    ret_1 = list_services()

    for item in host_list:
        ret_2 = list_subfunctions(item)
        if ret_2 == False:
            break  

    if (ret_1 == False) or (ret_2 == False):
        print ("Test result: Failed")
        assert 1==2
    else:
        print ("Test result: Passed")
