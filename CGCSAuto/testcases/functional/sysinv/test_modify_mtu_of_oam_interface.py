###
# Testcase 20 of the 2016-04-04 sysinv_test_plan.pdf
###


from pytest import fixture, mark, skip
import ast
import time

from utils import cli
from utils.ssh import ControllerClient
from utils import table_parser
from consts.auth import Tenant
from consts.timeout import CLI_TIMEOUT
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, host_helper, system_helper


def modify_mtu_on_oam_interface(hostname, mtu):

    LOG.tc_step('This Test will take 10min+ to execute as it lock, modify and unlock a node. ')

    # get the ports for oam type interface only
    table_ = system_helper.get_interfaces(hostname, con_ssh=None)
    ports_list = table_parser.get_values(table_, 'ports', network_type='oam')

    # parse a ["[u'eth0']"]
    ports = ast.literal_eval(ports_list[0])[0]
    imtu = " --imtu "+mtu
    args = hostname + " " + ports + imtu
    # lock the node
    LOG.tc_step('lock the standby')
    host_helper.lock_host(hostname)

    # config the page number after lock the compute node
    LOG.tc_step('modify the mtu on locked controller')

    # system host-if-modify controller-1 eth6 --imtu <mtu_value>
    output = cli.system('host-if-modify', args, auth_info=Tenant.ADMIN, fail_ok=False)

    # unlock the node
    LOG.tc_step('unlock the standby')
    host_helper.unlock_host(hostname)


@mark.parametrize('mtu', ['1500',
                          '1700',
                          '1500'])
def test_mtu_modified(mtu):
    """
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
    modify_mtu_on_oam_interface(first_host, mtu)
    # swact active and standby controller
    host_helper.swact_host(fail_ok=False)
    # modify mtu on new standby controller
    second_host = system_helper.get_standby_controller_name()
    # modify mtu on new standby controller
    modify_mtu_on_oam_interface(second_host,mtu)

    # check mtu is updated
    table_ = system_helper.get_interfaces(first_host, con_ssh=None)
    mtu_list = table_parser.get_values(table_, 'attributes', network_type='oam')
    actual_mtu_one = mtu_list[0][4:]

    table_ = system_helper.get_interfaces(second_host, con_ssh=None)
    mtu_list = table_parser.get_values(table_, 'attributes', network_type='oam')
    actual_mtu_two = mtu_list[0][4:]

    assert mtu == actual_mtu_one == actual_mtu_two, "Expect MTU={} after modification. Actual active host MTU={}, " \
                                                    "Actual standby host " \
                                                    "MTU={}".format(mtu, actual_mtu_one, actual_mtu_two)

