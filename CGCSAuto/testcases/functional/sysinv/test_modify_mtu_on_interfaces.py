###
# Testcase 20 of the 2016-04-04 sysinv_test_plan.pdf
# Change the MTU value of the OAM interface using CLI
###

import re
import random

from pytest import mark, skip, fixture

from utils import cli
from utils import table_parser
from utils.tis_log import LOG
from testfixtures.recover_hosts import HostsToRecover
from consts.cgcs import PLATFORM_NET_TYPES
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


def get_if_info(host):
    if_info = {}

    try:
        if_table = system_helper.get_host_interfaces_table(host)
        index_name = if_table['headers'].index('name')
        index_type = if_table['headers'].index('type')
        index_uses_ifs = if_table['headers'].index('uses i/f')
        index_used_by_ifs = if_table['headers'].index('used by i/f')
        index_class = if_table['headers'].index('class')
        index_attributes = if_table['headers'].index('attributes')

        for value in if_table['values']:
            name = value[index_name]
            if_type = value[index_type]
            uses_ifs = eval(value[index_uses_ifs])
            used_by_ifs = eval(value[index_used_by_ifs])
            if_class = value[index_class]
            network_types = [if_class]
            if if_class == 'platform':
                net_type_str = system_helper.get_host_if_show_values(host=host, interface=name, fields='networks')[0]
                network_types = [net_type.strip() for net_type in net_type_str.split(sep=',')]
            attributes = value[index_attributes].split(',')

            if name in if_info:
                LOG.warn('NIC {} already appeard! Duplicate of NIC:"{}"'.format(name, if_info[name]))
            else:
                if_info[name] = {
                    'mtu': int(re.split('MTU=', attributes[0])[1]),
                    'uses_ifs': uses_ifs,
                    'used_by_ifs': used_by_ifs,
                    'type': if_type,
                    'network_type': network_types
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

    if_names = [name for name in if_info if network_type in if_info[name]['network_type']]
    if not if_names:
        assert 0, 'Cannot find {} interface on host {}. Interface info: {}'.format(network_type, host, if_info)

    if not if_name:
        if len(if_names) > 1:
            LOG.warn('Multiple NICs found for network_type: "{}" on host:{}, {}'.format(
                network_type, host, if_names))

        if_name = if_names[0]

        LOG.warn('Will chose the first NIC:{} found for network_type: "{}" on host:{}'.format(
            if_name, network_type, host))
    else:
        assert if_name in if_names, 'Specified if_name {} not exist for {}'.format(if_name, host)

    min_mtu = 0

    uses_ifs = if_info[if_name]['uses_ifs']

    if uses_ifs:
        min_mtu = min([if_info[nic]['mtu'] for nic in uses_ifs])

    # check for mtu type
    # if it's not vlan set not restriction till mtu 9216 CGTS-8184
    uses_ifs_type = if_info[if_name]['type']
    if uses_ifs_type != 'vlan':
        min_mtu = 9216

    return min_mtu, if_info[if_name]['mtu'], if_name


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
    first_host = system_helper.get_standby_controller_name()
    if not first_host:
        skip("Standby controller unavailable. Cannot lock controller.")

    second_host = system_helper.get_active_controller_name()

    mtu = __get_mtu_to_mod(providernet_name='-ext', mtu_range=mtu_range)

    HostsToRecover.add([first_host, second_host], scope='function')

    max_mtu, cur_mtu, nic_name = get_max_allowed_mtus(host=first_host, network_type='oam')
    LOG.info('OK, the max MTU for {} is {}'.format(nic_name, max_mtu))

    expecting_pass = not max_mtu or mtu <= max_mtu
    if not expecting_pass:
        LOG.warn('Expecting to fail in changing MTU: changing to:{}, max-mtu:{}'.format(mtu, max_mtu))

    oam_attributes = system_helper.get_host_interfaces(host=first_host, rtn_val='attributes', net_type='oam')

    # sample attributes: [MTU=9216,AE_MODE=802.3ad]
    pre_oam_mtu = int(oam_attributes[0].split(',')[0].split('=')[1])

    LOG.tc_step("Modify {} oam interface MTU from {} to {}, and "
                "ensure it's applied successfully after unlock".format(first_host, pre_oam_mtu, mtu))
    if mtu == cur_mtu:
        LOG.info('Setting to same MTU: from:{} to:{}'.format(mtu, cur_mtu))

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

    if second_host == first_host:
        LOG.tc_step("Active-controller and Standby-controller are the same, likely a SIMPLEX lab," +
                    "hence, done with the testing")
    else:
        LOG.tc_step("Make sure current standby_controller is in available status in order to swact to")
        host_helper.wait_for_hosts_states(second_host, availability=['available'])

        LOG.tc_step("Swact active controller")
        host_helper.swact_host(fail_ok=False)
        host_helper.wait_for_webservice_up(first_host)

        LOG.tc_step("Modify new standby controller {} oam interface MTU to: {}, and "
                    "ensure it's applied successfully after unlock".format(second_host, mtu))

        code, res = host_helper.modify_mtu_on_interfaces(second_host,
                                                         mtu_val=mtu, network_type='oam', lock_unlock=True,
                                                         fail_ok=True)

        LOG.tc_step("Revert OAM MTU to original value: {}".format(pre_oam_mtu))
        code_revert, res_revert = host_helper.modify_mtu_on_interfaces(second_host, mtu_val=pre_oam_mtu,
                                                                       network_type='oam',
                                                                       lock_unlock=True, fail_ok=True)
        if 0 == code:
            assert expecting_pass, "OAM MTU is not modified successfully. Result: {}".format(res)
        else:
            assert not expecting_pass, "OAM MTU WAS modified unexpectedly. Result: {}".format(res)

        assert 0 == code_revert, "OAM MTU is not reverted successfully. Result: {}".format(res_revert)


@fixture()
def revert_data_mtu(request):
    def revert():
        LOG.fixture_step('Restore the MTUs of the data IFs on hosts if modified')
        global HOSTS_IF_MODIFY_ARGS
        items_to_revert = HOSTS_IF_MODIFY_ARGS.copy()
        for item in items_to_revert:
            host, pre_mtu, mtu, max_mtu, interface, net_type = item
            host_helper.lock_host(host, swact=True)

            LOG.info('Restore DATA MTU of IF:{} on host:{} to:{}, current MTU:{}'.format(interface, host, pre_mtu, mtu))
            host_helper.modify_mtu_on_interface(host, interface, pre_mtu, network_type=net_type, lock_unlock=False)
            LOG.info('OK, Data MTUs of IF:{} on host:{} are restored, from: {} to:{}'.format(
                interface, host, mtu, pre_mtu))

            host_helper.unlock_host(host)
            HOSTS_IF_MODIFY_ARGS.remove(item)
        LOG.info('OK, all changed MTUs of DATA IFs are restored')

    request.addfinalizer(revert)


@mark.p3
@mark.parametrize('mtu_range', [
    'middle',
    ])
def test_modify_mtu_data_interface(mtu_range, revert_data_mtu):
    """
    23) Change the MTU value of the data interface using CLI
    Verify that MTU on data interfaces on all compute node can be modified by cli
    The min mtu for data interface can be 1500,9000 or 9216, in which case MTU is unchangable. Need to confirm
    Args:
        mtu_range (str): A string that contain the mtu want to be tested
        revert_data_mtu: A fixture to restore changed mtus if any to their original values

    Setup:
        - Nothing

    Test Steps:
        - lock standby controller
        - modify the imtu value of the compute node
        - unlock the controller
        - check the compute node have expected mtu

    Teardown:
        - Revert data mtu

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
        if len(hypervisors) > 2:
            hypervisors = random.sample(hypervisors, 2)

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
            max_mtu, cur_mtu, nic_name = get_max_allowed_mtus(host=host, network_type=net_type, if_name=interface)

            LOG.info('Checking the max MTU for the IF:{}, max MTU: {}, host:{}'.format(
                interface, max_mtu or 'NOT SET', host))

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
                if mtu != cur_mtu:
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


def get_ifs_to_mod(host, network_type, mtu_val):
    table_ = table_parser.table(cli.system('host-if-list', '{} --nowrap'.format(host)))

    if_class = network_type
    network = ''
    if network_type in PLATFORM_NET_TYPES:
        if_class = 'platform'

    table_ = table_parser.filter_table(table_, **{'class': if_class})
    # exclude unmatched platform interfaces from the table.
    if 'platform' == if_class:
        platform_ifs = table_parser.get_values(table_, target_header='name', **{'class': 'platform'})
        for pform_if in platform_ifs:
            if_nets = system_helper.get_host_if_show_values(host=host, interface=pform_if, fields='networks')[0]
            if_nets = [if_net.strip() for if_net in if_nets.split(sep=',')]
            if network not in if_nets:
                table_ = table_parser.filter_table(table_, strict=True, exclude=True, name=pform_if)

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
