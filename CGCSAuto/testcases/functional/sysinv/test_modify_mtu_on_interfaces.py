###
# Testcase 20 of the 2016-04-04 sysinv_test_plan.pdf
# Change the MTU value of the OAM interface using CLI
###

import re

from pytest import mark, skip
import random

from utils import cli
from utils import table_parser
from utils.tis_log import LOG
from testfixtures.recover_hosts import HostsToRecover
from keywords import vm_helper, host_helper, system_helper, network_helper

HOSTS_IF_MODIFY_ARGS = []


def __get_mtu_to_mod(providernet_name, mtu_range='middle'):
    LOG.tc_step("Get a MTU value that is in mtu {} range".format(mtu_range))
    pnet_mtus = network_helper.get_providernets(name=providernet_name, rtn_val='mtu', strict=False)
    pnet_types = network_helper.get_providernets(name=providernet_name, rtn_val='type', strict=False)

    min_mtu = 1000
    max_mtu = 9216
    for pnet_mtu in pnet_mtus:
        pnet_mtu = int(pnet_mtu)
        if pnet_mtu > min_mtu:
            min_mtu = pnet_mtu

    for pnet_type in pnet_types:
        if 'vxlan' in pnet_type:
            min_mtu = min(min_mtu + 74, max_mtu)
            break

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


def get_if_info(host=None):
    if_info = {}

    try:
        if_table = system_helper.get_host_interfaces_table(host)

        index_name = if_table['headers'].index('name')

        index_type = if_table['headers'].index('type')

        index_uses_ifs = if_table['headers'].index('uses i/f')

        index_used_by_ifs = if_table['headers'].index('used by i/f')

        index_network_type = if_table['headers'].index('network type')

        index_attributes = if_table['headers'].index('attributes')

        for value in if_table['values']:

            name = value[index_name]

            if_type = value[index_type]

            uses_ifs = eval(value[index_uses_ifs])

            used_by_ifs = eval(value[index_used_by_ifs])

            network_type = value[index_network_type]

            attributes = value[index_attributes].split(',')

            if name in if_info:
                LOG.warn('NIC {} already appeard! Duplicate of NIC:"{}"'.format(name, if_info[name]))
            else:
                if_info[name] = {
                    'mtu': int(re.split('MTU=', attributes[0])[1]),
                    'uses_ifs': uses_ifs,
                    'used_by_ifs': used_by_ifs,
                    'type': if_type,
                    'network_type': network_type
                }

    except IndexError as e:
        LOG.error('Failed to get oam-interface name/type, error message:{}'.format(e))
        assert False, 'Failed to get oam-interface name/type, error message:{}'.format(e)
    except Exception as e:
        LOG.error('Failed to get oam-interface name/type, error message:{}'.format(e))
        assert False, 'Failed to get oam-interface name/type, error message:{}'.format(e)

    assert if_info, 'Cannot get interface information'

    return if_info


def get_max_allowed_mtus(host='controller-0', network_type='oam', if_name='', if_info=None):
    if not if_info:
        if_info = get_if_info(host=host)

    if_names = [name for name in if_info if if_info[name]['network_type'] == network_type]
    if not if_names:
        LOG.warn('Cannot find NIC of network_type: "{}" on host: "{}"'.format(network_type, host))
        return 0, ''

    if not if_name:
        if len(if_names) > 1:
            LOG.warn('Multiple NICs found for network_type: "{}" on host:{}, {}'.format(
                network_type, host, if_names))

        if_name = if_names[0]

        LOG.warn('Will chose the first NIC:{} found for network_type: "{}" on host:{}'.format(
            if_name, network_type, host))
    else:
        if if_name not in if_names:
            LOG.error('Cannot find NIC with name:{} of network_type: "{}" on host: "{}"'.format(
                if_name, network_type, host))

            return 0, None

    min_mtu = 0

    uses_ifs = if_info[if_name]['uses_ifs']
    if uses_ifs:
        min_mtu = min([if_info[nic]['mtu'] for nic in uses_ifs])

    return min_mtu, if_name


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
        mtu_range (str): A string that contain the mtu want to be tested

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

    max_mtu, nic_name = get_max_allowed_mtus(host=first_host, network_type='oam')
    LOG.info('OK, the max MTU for {} is {}'.format(nic_name, max_mtu))

    expecting_pass = not max_mtu or mtu <= max_mtu
    if not expecting_pass:
        LOG.warn('Expecting to fail in changing MTU: changing to:{}, max-mtu:{}'.format(mtu, max_mtu))

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
    if 0 == code:
        assert expecting_pass, "OAM MTU is not modified successfully. Result: {}".format(res)
    else:
        assert not expecting_pass, "OAM MTU WAS modified unexpectedly. Result: {}".format(res)

    assert 0 == code_revert, "OAM MTU is not reverted successfully. Result: {}".format(res_revert)

    LOG.tc_step("Swact active controller")
    host_helper.swact_host(fail_ok=False)
    host_helper.wait_for_webservice_up(first_host)

    LOG.tc_step("Modify new standby controller {} oam interface MTU to: {}, and "
                "ensure it's applied successfully after unlock".format(second_host, mtu))

    code, res = host_helper.modify_mtu_on_interfaces(second_host,
                                                     mtu_val=mtu, network_type='oam', lock_unlock=True, fail_ok=True)

    LOG.tc_step("Revert OAM MTU to original value: {}".format(pre_oam_mtu))
    code_revert, res_revert = host_helper.modify_mtu_on_interfaces(second_host, mtu_val=pre_oam_mtu, network_type='oam',
                                                                   lock_unlock=True, fail_ok=True)
    if 0 == code:
        assert expecting_pass, "OAM MTU is not modified successfully. Result: {}".format(res)
    else:
        assert not expecting_pass, "OAM MTU WAS modified unexpectedly. Result: {}".format(res)

    assert 0 == code_revert, "OAM MTU is not reverted successfully. Result: {}".format(res_revert)


@mark.p3
@mark.parametrize('mtu_range', [
    'middle',
    'larger'
    ])
def test_modify_mtu_data_interface(mtu_range):
    """
    23) Change the MTU value of the data interface using CLI
    Verify that MTU on data interfaces on all compute node can be modified by cli
    The min mtu for data interface can be 1500,9000 or 9216, in which case MTU is unchangable. Need to confirm
    Args:
        mtu_range (str): A string that contain the mtu want to be tested

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

    if system_helper.is_two_node_cpe():
        standby = system_helper.get_standby_controller_name()
        if not standby:
            skip("Standby controller unavailable on CPE system. Unable to lock host")
        hypervisors = [standby]
    else:
        if len(hypervisors) > 4:
            hypervisors = random.sample(hypervisors, 4)

    LOG.tc_step("Delete vms to reduce lock time")
    vm_helper.delete_vms()

    mtu = __get_mtu_to_mod(providernet_name='-data', mtu_range=mtu_range)

    LOG.tc_step("Modify data MTU to {} for hosts: {}".format(mtu, hypervisors))

    net_type = 'data'

    active_controller = system_helper.get_active_controller_name()
    hosts = hypervisors[:]
    if active_controller in hosts:
        hosts.remove(active_controller)
        hosts.append(active_controller)

    for host in hosts:
        interfaces = get_ifs_to_mod(host, net_type, mtu)
        revert_ifs = list(interfaces)
        if not revert_ifs:
            LOG.info('Skip host:{} because there is no interface to set MTU'.format(host))
            continue

        host_helper.lock_host(host, swact=True)

        revert_ifs.reverse()
        changed_ifs = []
        for interface in revert_ifs:
            LOG.tc_step('Checking the max MTU for the IF:{} on host:{}'.format(interface, host))
            max_mtu = get_max_allowed_mtus(host=host, network_type=net_type, if_name=interface)[0]

            LOG.info('Checking the max MTU for the IF is: {}'.format(max_mtu or 'NOT SET'))

            expecting_pass = not max_mtu or mtu <= max_mtu
            if not expecting_pass:
                LOG.warn('Expecting to fail in changing MTU: changing to:{}, max-mtu:{}'.format(mtu, max_mtu))

            pre_mtu = int(system_helper.get_host_if_show_values(host, interface, 'imtu')[0])

            LOG.tc_step('Modify MTU of IF:{} on host:{} to:{}, expeting: {}'.format(
                interface, host, mtu, 'PASS' if expecting_pass else 'FAIL'))

            code, res = host_helper.modify_mtu_on_interface(host, interface, mtu_val=mtu, network_type=net_type,
                                                            lock_unlock=False, fail_ok=True)
            msg_result = "PASS" if expecting_pass else "FAIL"
            msg = "Failed to modify data MTU, expecting to {}, \nnew MTU:{}, max MTU:{}, old MTU:{}, " \
                  "Return code:{}; Details: {}".format(msg_result, pre_mtu, max_mtu, pre_mtu, code, res)

            if 0 == code:
                changed_ifs.append(interface)
                HOSTS_IF_MODIFY_ARGS.append((host, pre_mtu, mtu, max_mtu, interface, net_type))
                assert expecting_pass, msg
            else:
                assert not expecting_pass, msg

            LOG.info('OK, modification of MTU of data interface {} as expected: {}'.format(msg_result, msg_result))

        host_helper.unlock_host(host)
        for interface in revert_ifs:
            if interface in changed_ifs:
                actual_mtu = int(system_helper.get_host_if_show_values(host,
                                                                       interface=interface, fields=['imtu'])[0])
                assert actual_mtu == mtu, \
                    'Actual MTU after modification did not match expected, expected:{}, actual:{}'.format(
                        mtu, actual_mtu)
        changed_ifs[:] = []

    if not HOSTS_IF_MODIFY_ARGS:
        skip('No data interface changed!')
        return

    HOSTS_IF_MODIFY_ARGS.reverse()

    LOG.tc_step('Restore the MTUs of the data IFs on hosts:{}'.format(hosts))

    prev_host = None
    for host, pre_mtu, mtu, max_mtu, interface, net_type in HOSTS_IF_MODIFY_ARGS:
        if not prev_host or prev_host != host:
            host_helper.lock_host(host, swact=True)

        LOG.info('Restore DATA MTU of IF:{} on host:{} to:{}, current MTU:{}'.format(interface, host, pre_mtu, mtu))
        host_helper.modify_mtu_on_interface(host, interface, pre_mtu, network_type=net_type, lock_unlock=True)

        LOG.info('OK, Data MTUs of IF:{} on host:{} are restored, from: {} to:{}'.format(
            interface, host, mtu, pre_mtu))

        if prev_host and prev_host != host:
            host_helper.unlock_host(host)

        prev_host = host

    LOG.info('OK, all changed MTUs of DATA IFs are restored')


def get_ifs_to_mod(host, network_type, mtu_val):
    table_ = table_parser.table(cli.system('host-if-list', '{} --nowrap'.format(host)))
    table_ = table_parser.filter_table(table_, **{'network type': network_type})
    uses_if_names = table_parser.get_values(table_, 'name', exclude=True, **{'uses i/f': '[]'})
    non_uses_if_names = table_parser.get_values(table_, 'name', exclude=False, **{'uses i/f': '[]'})
    uses_if_first = False
    if uses_if_names:
        current_mtu = int(system_helper.get_host_if_show_values(host, interface=uses_if_names[0], fields=['imtu'])[0])
        if current_mtu <= mtu_val:
            uses_if_first = True

    if uses_if_first:
        if_names = uses_if_names + non_uses_if_names
    else:
        if_names = non_uses_if_names + uses_if_names

    return if_names
