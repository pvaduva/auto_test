###
# Testcase 20 of the 2016-04-04 sysinv_test_plan.pdf
# Change the MTU value of the OAM interface using CLI
###


from pytest import fixture, mark, skip
import ast, random
from time import sleep

from utils import cli,exceptions
from utils.ssh import ControllerClient
from utils import table_parser
from consts.auth import Tenant
from consts.timeout import CLI_TIMEOUT
from utils.tis_log import LOG
from testfixtures.recover_hosts import HostsToRecover
from keywords import nova_helper, vm_helper, host_helper, system_helper, network_helper

HOSTS_IF_MODIFY_ARGS = []


def __get_mtu_to_mod(providernet_name, mtu_range='middle'):
    LOG.tc_step("Get a MTU value that is in mtu {} range".format(mtu_range))
    pnet_mtus = network_helper.get_providernets(name=providernet_name, rtn_val='mtu', strict=False)
    pnet_types = network_helper.get_providernets(name=providernet_name, rtn_val='type', strict=False)

    min_mtu = 1000
    max_mtu = 9216
    for pnet_type in pnet_types:
        if 'vxlan' in pnet_type:
            max_mtu = 9000
            break

    for pnet_mtu in pnet_mtus:
        pnet_mtu = int(pnet_mtu)
        if pnet_mtu > min_mtu:
            min_mtu = pnet_mtu

    if min_mtu == max_mtu:
        mtu = max_mtu
    else:
        if mtu_range == 'middle':
            mtu = random.choice(range(min_mtu + 1, max_mtu - 1))
        elif mtu_range == 'min':
            mtu = min_mtu
        else:
            mtu = max_mtu

    return mtu


@mark.p3
@mark.parametrize('mtu_range', [
    'middle'
])
def test_modify_mtu_oam_interface(mtu_range):
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
    mtu = __get_mtu_to_mod(providernet_name='-ext', mtu_range=mtu_range)

    first_host = system_helper.get_standby_controller_name()
    if not first_host:
        skip("Standby controller unavailable. Cannot lock controller.")

    second_host = system_helper.get_active_controller_name()
    HostsToRecover.add([first_host, second_host], scope='function')

    oam_attributes = system_helper.get_host_interfaces_info(host=first_host, rtn_val='attributes', net_type='oam')
    # sample attributes: [MTU=9216,AE_MODE=802.3ad]
    pre_oam_mtu = int(oam_attributes[0].split(',')[0].split('=')[1])

    LOG.tc_step("Modify {} oam interface MTU from {} to {}, and "
                "ensure it's applied successfully after unlock".format(first_host, pre_oam_mtu, mtu))
    code, res = host_helper.modify_mtu_on_interfaces(first_host, mtu_val=mtu, network_type='oam',
                                                     lock_unlock=True, fail_ok=True)

    LOG.tc_step("Revert OAM MTU to original value: {}".format(pre_oam_mtu))
    code_revert, res_revert = host_helper.modify_mtu_on_interfaces(first_host, mtu_val=pre_oam_mtu, network_type='oam',
                                                                   lock_unlock=True, fail_ok=True)
    assert 0 == code, "OAM MTU is not modified successfully. Result: {}".format(res)
    assert 0 == code_revert, "OAM MTU is not reverted successfully. Result: {}".format(res_revert)

    LOG.tc_step("Swact active controller")
    host_helper.swact_host(fail_ok=False)
    host_helper.wait_for_webservice_up(first_host)

    LOG.tc_step("Modify new standby controller {} oam interface MTU to: {}, and "
                "ensure it's applied successfully after unlock".format(second_host, mtu))

    code, res = host_helper.modify_mtu_on_interfaces(second_host, mtu_val=mtu, network_type='oam',
                                               lock_unlock=True, fail_ok=True)

    LOG.tc_step("Revert OAM MTU to original value: {}".format(pre_oam_mtu))
    code_revert, res_revert = host_helper.modify_mtu_on_interfaces(second_host, mtu_val=pre_oam_mtu, network_type='oam',
                                                                   lock_unlock=True, fail_ok=True)
    assert 0 == code, "OAM MTU is not modified successfully for second controller. Result: {}".format(res)
    assert 0 == code_revert, "OAM MTU is not reverted successfully. Result: {}".format(res_revert)


@mark.p3
@mark.parametrize('mtu_range', [
    'middle',
    ])
def test_modify_mtu_data_interface(mtu_range):
    """
    23) Change the MTU value of the data interface using CLI
    Verify that MTU on data interfaces on all compute node can be modified by cli
    The min mtu for data interface can be 1500,9000 or 9216, in which case MTU is unchangable. Need to confirm
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

    hypervisors = host_helper.get_hypervisors(state='up', status='enabled')
    if len(hypervisors) < 2:
        skip("Less than two hypervisors available.")

    if system_helper.is_small_footprint():
        standby = system_helper.get_standby_controller_name()
        if not standby:
            skip("Standby controller unavailable on CPE system. Unable to lock host")
        hypervisors = [standby]
    else:
        if len(hypervisors) > 4:
            hypervisors = random.sample(hypervisors, 4)

    # To remove
    # hypervisors = [host_helper.get_nova_host_with_min_or_max_vms(rtn_max=False)]

    LOG.tc_step("Delete vms to reduce lock time")
    vm_helper.delete_vms()

    mtu = __get_mtu_to_mod(providernet_name='-data', mtu_range=mtu_range)
    LOG.tc_step("Modify data MTU to {} for hosts: {}".format(mtu, hypervisors))
    for host in hypervisors:
        interfaces = system_helper.get_host_interfaces_info(host=host, rtn_val='name', net_type='data')
        for interface in interfaces:
            pre_mtu = int(system_helper.get_host_if_show_values(host, interface, 'imtu')[0])
            HOSTS_IF_MODIFY_ARGS.append("-m {} {} {}".format(pre_mtu, host, interface))

    HostsToRecover.add(hypervisors)
    code, res = host_helper.modify_mtu_on_interfaces(hypervisors, mtu_val=mtu, network_type='data',
                                                     lock_unlock=True, fail_ok=True)

    LOG.tc_step("Revert host data interface MTU to original settings: {}".format(HOSTS_IF_MODIFY_ARGS))
    for host in hypervisors:
        host_helper.lock_host(host)

    failed_args = []
    for args in HOSTS_IF_MODIFY_ARGS:
        code_revert, output = cli.system('host-if-modify', args, fail_ok=True, rtn_list=True)
        if not code_revert == 0:
            failed_args.append(args)

    # Let host recover fixture to unlock the hosts after revert modify to save run time

    assert 0 == code, "Failed to modify data MTU. Return code:{}; Details: {}".format(code, res)
    assert not failed_args, "Host if modify with below args failed: {}".format(failed_args)
