###
# Testcase 20 of the 2016-04-04 sysinv_test_plan.pdf
# Change the MTU value of the OAM interface using CLI
###


from pytest import fixture, mark, skip
import ast
from time import sleep

from utils import cli,exceptions
from utils.ssh import ControllerClient
from utils import table_parser
from consts.auth import Tenant
from consts.timeout import CLI_TIMEOUT
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, host_helper, system_helper


def modify_mtu_on_interface(hostname, mtu, network_type):

    LOG.tc_step('This Test will take 10min+ to execute as it lock, modify and unlock a node. ')

    if not hostname:
        raise exceptions.HostError("Expected a valid hostname but got nothing instead")

    # get the port_uuid for network_type interface only
    table_ = system_helper.get_interfaces(hostname, con_ssh=None)
    port_uuid_list = table_parser.get_values(table_, 'uuid', **{'network type': network_type})
    imtu = " --imtu "+mtu

    # lock the node
    LOG.tc_step('lock the standby')
    host_helper.lock_host(hostname)

    # config the page number after lock the compute node
    LOG.tc_step('modify the mtu on locked controller')

    # change all MTUs on ports of the same network type
    for port_uuid in port_uuid_list:
        args = hostname + " " + port_uuid + imtu
        # system host-if-modify controller-1 <port_uuid>--imtu <mtu_value>
        output = cli.system('host-if-modify', args, auth_info=Tenant.ADMIN, fail_ok=False)

    # unlock the node
    LOG.tc_step('unlock the standby')
    host_helper.unlock_host(hostname)


@mark.parametrize('mtu', ['1400', '1500'])
def test_oam_intf_mtu_modified(mtu):
    """

    of the 2016-04-04 sysinv_test_plan.pdf
    20) Change the MTU value of the OAM interface using CLI

    Verify that MTU on oam interfaces on both standby and active controller can be modified by cli

    Args:
        mtu (str): A string that contain the mtu want to be tested

    Setup:
        - Nothing

    Test Steps:
        - lock standby controller
        - modify the imtu value of the controller
        - unlock the controller
        - swact the controller
        - lock the controller
        - modify the imtu value of the controller
        - unlock the controller
        - check the controllers have expected mtu

    Teardown:
        - Nothing

    """

    # retrieve standby controller
    first_host = system_helper.get_standby_controller_name()
    # modify mtu on standby controller
    modify_mtu_on_interface(first_host, mtu, 'oam')
    # swact active and standby controller

    host_helper.swact_host(fail_ok=False)
    # modify mtu on new standby controller
    second_host = system_helper.get_standby_controller_name()
    # modify mtu on new standby controller
    modify_mtu_on_interface(second_host, mtu, 'oam')

    # check mtu is updated
    table_ = system_helper.get_interfaces(first_host, con_ssh=None)
    mtu_list = table_parser.get_values(table_, 'attributes', **{'network type': 'oam'})
    # parse the string of MTU=xxxx
    actual_mtu_one = mtu_list[0][4:]

    table_ = system_helper.get_interfaces(second_host, con_ssh=None)
    mtu_list = table_parser.get_values(table_, 'attributes', **{'network type': 'oam'})
    actual_mtu_two = mtu_list[0][4:]

    assert mtu == actual_mtu_one == actual_mtu_two, "Expect MTU={} after modification. Actual active host MTU={}, " \
                                                    "Actual standby host " \
                                                    "MTU={}".format(mtu, actual_mtu_one, actual_mtu_two)


@mark.parametrize('mtu', ['1550', '1500'])
def test_data_intf_mtu_modified(mtu):
    """
    23) Change the MTU value of the data interface using CLI
    Verify that MTU on data interfaces on all compute node can be modified by cli

    Args:
        mtu (str): A string that contain the mtu want to be tested

    Setup:
        - Nothing

    Test Steps:
        - lock standby controller
        - modify the imtu value of the compute node
        - unlock the controller
        - check the compute node have expected mtu

    Teardown:
        - Nothing

    """
    # test all compute node that are up and enabled
    compute_list = host_helper.get_hypervisors(state='up', status='enabled')

    for host in compute_list:

        modify_mtu_on_interface(host, mtu, 'data')

        # check mtu is updated
        table_ = system_helper.get_interfaces(host, con_ssh=None)
        mtu_list = table_parser.get_values(table_, 'attributes', **{'network type': 'data'})
        # parse the string of MTU=xxxx

        for port_mtu in mtu_list:

            mtu_list = port_mtu.split(',')
            actual_mtu = mtu_list[0][4:]
            # verfiy each data ports on each hosts
            assert mtu == actual_mtu, "On {} ports Expect MTU={} after modification. " \
                                      "Actual active host MTU={} ".format(host,mtu, actual_mtu)
