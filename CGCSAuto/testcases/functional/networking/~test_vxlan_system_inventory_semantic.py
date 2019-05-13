# import random
# import re
#
# from pytest import fixture, mark, skip
#
# from utils import cli
# from utils import table_parser
# from utils.tis_log import LOG
# from consts.auth import Tenant
# from keywords import host_helper, system_helper, common
# from testfixtures.recover_hosts import HostsToRecover
# from consts.cli_errs import NetworkingErr
# from consts.cgcs import Networks
#
# pro_net_name = 'provider_vxlan'
#
#
# @fixture(scope='function')
# def check_alarms():
#     pass
#
#
# @fixture(scope='module')
# def get_interface_(request):
#
#     provider_ = common.get_unique_name(pro_net_name, resource_type='other')
#     new_interface_ = 'test0if'
#
#     # (a) create providernet
#     args = provider_ + ' --type=vxlan'
#     table_ = table_parser.table(cli.neutron('providernet-list', auth_info=Tenant.get('admin')))
#     if not table_parser.get_values(table_, 'id', **{'name': provider_}):
#         cli.neutron('providernet-create', args, auth_info=Tenant.get('admin'), rtn_code=True)
#
#     nova_hosts = host_helper.get_hypervisors(state='up')
#
#     if not nova_hosts:
#         skip("Can not continue without computer host node")
#
#     # find a free interface
#     computer_host = interface = None
#     for nova_host in nova_hosts:
#         table_ = table_parser.table(cli.system('host-if-list', positional_args='{} -a --nowrap'.format(nova_host),
#                                                auth_info=Tenant.get('admin')))
#         list_interfaces = table_parser.get_values(table_, 'name', **{'type': 'ethernet', 'class': 'None',
#                                                                      'used by i/f': '[]'})
#         if list_interfaces:
#             computer_host = nova_host
#             interface = random.choice(list_interfaces)
#             break
#     else:
#         skip("Can not find a free data interface")
#
#     # now lock the computer
#     host_helper.lock_host(computer_host, swact=True)
#     HostsToRecover.add(computer_host, scope='module')
#
#     host_helper.add_host_interface(computer_host, new_interface_, if_type='ae', pnet=provider_, ports_or_ifs=interface,
#                                    if_class='data', mtu=1600, lock_unlock=False)
#
#     def fin():
#         # clean up
#         cli.system('host-if-delete', '{} {}'.format(computer_host, new_interface_))
#         cli.neutron('providernet-delete', provider_, auth_info=Tenant.get('admin'))
#     request.addfinalizer(fin)
#
#     return computer_host, provider_, new_interface_
#
#
# @fixture(scope='module')
# def set_interface_ip_(get_interface_):
#     compute, provider, new_interface_ = get_interface_
#     host_helper.modify_host_interface(compute, new_interface_, pnet=provider, ipv4_mode='static',
#                                       ipv6_mode='static', if_class='data', lock_unlock=False)
#     ip_v4 = "192.168.3.3"
#
#     # check if the ip address already exist
#     table_ = table_parser.table(cli.system('host-addr-list', compute))
#     if not table_parser.get_values(table_, 'uuid', **{'address': ip_v4}):
#         args_ip = '{} {} {} 24'.format(compute, new_interface_, ip_v4)
#         cli.system('host-addr-add', args_ip, rtn_code=True)
#
#     ip_v6 = "2001:470:27:37e::2"
#     if not table_parser.get_values(table_, 'uuid', **{'address': ip_v6}):
#         args_ip = '{} {} {} 64'.format(compute, new_interface_, ip_v6)
#         cli.system('host-addr-add', args_ip, rtn_code=True)
#
#     return compute, provider, new_interface_
#
#
# @mark.p3
# def test_providernet_requires_ip_on_interface_before_assignment(get_interface_):
#
#     """
#     1) vxLan provider network requires an IP address on interface before assignment
#
#     Args:
#         get_interface_:
#
#     Test Setups:
#         (a) create providernet with type=vxlan
#         (b) lock the host
#         (c) create interface associate with providernet without create IP address
#
#     Test Steps:
#         unlock the compute fail:
#
#     Returns:
#
#     """
#
#     nova_host, provider, new_interface_ = get_interface_
#
#     LOG.tc_step("Unlock the host {}".format(nova_host))
#     code, err_info = host_helper.unlock_host(nova_host, fail_ok=True)
#
#     LOG.tc_step("Verify the host unlock statue, should be failed")
#     if code > 0:
#         LOG.info("Expected error: {}".format(err_info))
#         assert NetworkingErr.VXLAN_MISSING_IP_ON_INTERFACE in err_info
#
#     else:
#         assert 1 == code, "There is no ip address add in interface yet, so the host can not be unlock"
#
#
# @mark.p3
# def test_wrong_ip_addressing_mode(get_interface_):
#     """
#     TC3) data interface address mode must be set to “static” before allowing any IP address
#
#     Args:
#         get_interface_:
#
#     Test Setups:
#         (a) create providernet with type=vxlan
#         (b) lock the host
#         (c) create interface associate with providernet set the ip addressing mode as default, not static
#
#     Test Steps:
#         create ip addr for the interface
#
#     Returns:
#
#     """
#
#     compute, provider, new_interface_ = get_interface_
#
#     LOG.tc_step("Create ip address when the mode is not static")
#     args_ip = '{} {} 111.11.11.11 24'.format(compute, new_interface_)
#     code, err_info = cli.system('host-addr-add', args_ip, fail_ok=True, rtn_code=True)
#
#     LOG.tc_step("Verify the ip address creation should be failed")
#     if code > 0:
#         LOG.info("Expect fail: set the ip mode to static before assign a address |{}|".format(err_info))
#         assert NetworkingErr.WRONG_IF_ADDR_MODE in err_info
#     else:
#         assert 1 == code, "Should not be here."
#
#
# @mark.p3
# def test_set_data_if_ip_address_mode_to_none_static_when_ip_exist(get_interface_):
#     """
#     TC4: setting data interface address mode to anything but “static” should not be allowed if addresses
#     still exist on interface
#     however, set to Disabled is ok
#
#     Args:
#         get_interface_:
#
#     Test Setups:
#         (a) create providernet with type=vxlan
#         (b) lock the host
#         (c) create interface associate with providernet set the ip addressing mode as default, not static
#
#     Test Steps:
#         set ip addressing mode to static
#         create ip addr for the interface
#         set the ip addressing mode to pool should be fail
#
#     Test Teardown:
#         delete ip address just created
#
#     Returns:
#
#     """
#     auth_url = Tenant.get('admin')['auth_url']
#     if not re.search(Networks.IPV4_IP, auth_url):
#         skip("This test can only run on IPv4 system")
#
#     compute, provider, new_interface_ = get_interface_
#
#     LOG.tc_step("TC4: set the mode to 'static' ")
#     host_helper.modify_host_interface(compute, new_interface_, pnet=provider, if_class='data',
#                                       ipv4_mode='static', lock_unlock=False)
#
#     LOG.tc_step("create the ip again after mode set to static")
#     args = '{} {} 111.11.11.11 24'.format(compute, new_interface_)
#     cli.system('host-addr-add', args)
#
#     LOG.tc_step("TC4: set the mode to 'pool' when the ip still exist")
#     code, err_info = host_helper.modify_host_interface(compute, new_interface_, pnet=provider, if_class='data',
#                                                        ipv4_mode='pool', ipv4_pool='management',
#                                                        lock_unlock=False, fail_ok=True)
#
#     if code > 0:
#         LOG.info("modify interface failed")
#         assert NetworkingErr.SET_IF_ADDR_MODE_WHEN_IP_EXIST in err_info
#     else:
#         assert 1 == code, 'should not be here'
#
#     LOG.tc_step("TC4: clean the ip just created")
#     table_ = table_parser.table(cli.system('host-addr-list', compute))
#     cli.system('host-addr-delete', table_parser.get_values(table_, 'uuid', **{'ifname': new_interface_}))
#
#
# @mark.p3
# def test_create_null_ip_addr(get_interface_):
#     """
#     TC5: IP address must not be zero
#
#     Args:
#         get_interface_:
#
#     Test Setups:
#         (a) create providernet with type=vxlan
#         (b) lock the host
#         (c) create interface associate with providernet set the ip addressing mode as default, not static
#
#     Test Steps:
#         set ip addressing mode to static
#         create ip addr for the interface
#
#     Returns:
#
#     """
#
#     compute, provider, new_interface_ = get_interface_
#
#     LOG.tc_step("TC5: set the mode to 'static' ")
#     host_helper.modify_host_interface(compute, new_interface_, pnet=provider, if_class='data',
#                                       ipv4_mode='static', lock_unlock=False)
#
#     LOG.tc_step("TC5: create ip addr with all zero")
#     args_ip = '{} {} 0.0.0.0 24'.format(compute, new_interface_)
#     code, err_info = cli.system('host-addr-add', args_ip, fail_ok=True, rtn_code=True)
#     if code > 0:
#         LOG.info("Expect fail: {}".format(err_info))
#         assert NetworkingErr.NULL_IP_ADDR in err_info
#     else:
#         assert 1 == code, 'should not be here'
#
#
# @mark.p3
# def test_null_ip_network_partion(get_interface_):
#     """
#     TC6: IP address network portion must not be zero
#
#     Args:
#         get_interface_:
#
#     Test Setups:
#         (a) create providernet with type=vxlan
#         (b) lock the host
#         (c) create interface associate with providernet set the ip addressing mode as default, not static
#
#     Test Steps:
#         set ip addressing mode to static
#         create ip addr for the interface
#
#     Returns:
#
#     """
#
#     compute, provider, new_interface_ = get_interface_
#
#     LOG.tc_step("TC6: set the mode to 'static' ")
#     host_helper.modify_host_interface(compute, new_interface_, pnet=provider, if_class='data', ipv4_mode='static',
#                                       lock_unlock=False)
#
#     LOG.tc_step("TC6: create ip addr with network partion zero")
#     args_ip = '{} {} 0.0.0.33 24'.format(compute, new_interface_)
#     code, err_info = cli.system('host-addr-add', args_ip, fail_ok=True, rtn_code=True)
#     if code > 0:
#         LOG.info("Expect fail: |{}|".format(err_info))
#         assert NetworkingErr.NULL_NETWORK_ADDR == err_info
#     else:
#         assert 1 == code, 'should not be here'
#
#
# @mark.p3
# def test_null_ip_host_portion(get_interface_):
#     """
#     TC7: 7) IP address host portion must not be zero
#
#     Args:
#         get_interface_:
#
#
#     Test Setups:
#         (a) create providernet with type=vxlan
#         (b) lock the host
#         (c) create interface associate with providernet set the ip addressing mode as default, not static
#
#     Test Steps:
#         set ip addressing mode to static
#         create ip addr for the interface
#
#     Returns:
#
#     """
#
#     compute, provider, new_interface_ = get_interface_
#
#     LOG.tc_step("TC7: set the mode to 'static' ")
#     host_helper.modify_host_interface(compute, new_interface_, pnet=provider, if_class='data', ipv4_mode='static',
#                                       lock_unlock=False)
#
#     LOG.tc_step("TC7: create ip addr with host partion zero")
#     args_ip = '{} {} 192.168.0.0 16'.format(compute, new_interface_)
#     code, err_info = cli.system('host-addr-add', args_ip, fail_ok=True, rtn_code=True)
#     if code > 0:
#         LOG.info("Expect fail: |{}|".format(err_info))
#         assert NetworkingErr.NULL_HOST_PARTION_ADDR in err_info
#     else:
#         assert 1 == code, 'should not be here'
#
#
# @mark.p3
# def test_ip_should_be_unicast_address(get_interface_):
#     """
#     TC8: 8) IP address should be a unicast address (ie., not multicast and not broadcast)
#
#     Args:
#         get_interface_:
#
#     Test Setups:
#         (a) create providernet with type=vxlan
#         (b) lock the host
#         (c) create interface associate with providernet set the ip addressing mode as default, not static
#
#     Test Steps:
#         set ip addressing mode to static
#         create ip addr for the interface using multicast ip should be failed
#         create ip addr for the interface using broadcast ip should be failed
#
#     Returns:
#
#     """
#     compute, provider, new_interface_ = get_interface_
#
#     LOG.tc_step("TC8: set the mode to 'static' ")
#     host_helper.modify_host_interface(compute, new_interface_, pnet=provider, if_class='data', ipv4_mode='static',
#                                       lock_unlock=False)
#
#     LOG.tc_step("TC8: set multicast ip addr: 224.0.0.0 to 239.225.225.225")
#     args_ip = '{} {} 225.168.2.2 16'.format(compute, new_interface_)
#     code, err_info = cli.system('host-addr-add', args_ip, fail_ok=True, rtn_code=True)
#     if code > 0:
#         LOG.info("Expect fail: {}".format(err_info))
#         assert NetworkingErr.NOT_UNICAST_ADDR in err_info
#     else:
#         assert 1 == code, 'should not be here'
#
#     LOG.tc_step("TC8: set broadcast ip addr")
#     args_ip = '{} {} 255.255.255.255 24'.format(compute, new_interface_)
#     code, err_info = cli.system('host-addr-add', args_ip, fail_ok=True, rtn_code=True)
#     if code > 0:
#         LOG.info("Expect fail: |{}|".format(err_info))
#         assert NetworkingErr.NOT_BROADCAST_ADDR in err_info
#     else:
#         assert 1 == code, 'should not be here'
#
#
# @mark.p3
# def test_ip_unique_across_all_compute_nodes(get_interface_):
#     """
#     TC10 ) IP address should be unique across all compute nodes
#
#     Args:
#         get_interface_:
#
#     Test Setups:
#         (a) create providernet with type=vxlan
#         (b) lock the host
#         (c) create interface associate with providernet set the ip addressing mode as default, not static
#
#     Test Steps:
#         set ip addressing mode to static
#         random choise another compute node and get a ip address and their prefix
#         using this ip to create ip addr for the interface
#         verify the ip address creation statue
#
#     Returns:
#
#     """
#
#     compute, provider, new_interface_ = get_interface_
#
#     LOG.tc_step("Change the ip addressing mode to static")
#     host_helper.modify_host_interface(compute, new_interface_, pnet=provider, if_class='data', ipv4_mode='static',
#                                       ipv6_mode='static', lock_unlock=False)
#
#     LOG.tc_step("random get a ip from any compute node")
#     # randomly get a compute
#     cmp = random.choice(host_helper.get_hypervisors(state='up'))
#
#     table_ = table_parser.table(cli.system('host-addr-list', cmp))
#     ip = random.choice(table_parser.get_values(table_, 'address'))
#     prefix = table_parser.get_values(table_, 'prefix', **{'address': ip})
#
#     LOG.tc_step("TC10: ip addr {}/{} used in {}".format(ip, prefix[0], cmp))
#     args_ip = '{} {} {} {}'.format(compute, new_interface_, ip, prefix[0])
#     code, err_info = cli.system('host-addr-add', args_ip, fail_ok=True, rtn_code=True)
#     if code > 0:
#         LOG.info("Expect fail: {}".format(err_info))
#         assert NetworkingErr.DUPLICATE_IP_ADDR in err_info
#     else:
#         assert 1 == code, 'should not be here'
#
#
# @mark.p3
# @mark.parametrize(('prefix', 'status', 'ipv'), [
#     (33, False, 4),    # fail expected
#     (345, False, 4),    # fail expected
#     (23, True, 4),    # ok
#     (129, False, 6),    # ok
#     (124, True, 6),    # ok
# ])
# def test_route_prefix_validation(set_interface_ip_, prefix, status, ipv):
#     """
#     15) IP route network prefix must be valid for family (i.e., 1-32 for IPv4, 1-128 for IP6)
#
#     Args:
#         set_interface_ip_:
#         prefix:
#         status:
#         ipv   ipv4 or ipv6
#
#
#     Test Setups:
#         (a) create providernet with type=vxlan
#         (b) lock the host
#         (c) create interface associate with providernet set the ip addressing mode to static for both ipv4 and ipv6
#         (d) create ip addr for the interface
#
#     Test Steps:
#         add route with the given prefix
#         verify the route adding status
#
#     Returns:
#
#     """
#     compute, provider, new_interface_ = set_interface_ip_
#     metric = 16
#
#     LOG.tc_step("TC15: add route with prefix {}".format(prefix))
#     if ipv == 4:
#         gateway = "192.168.3.0"
#         nt = '192.168.102.0'
#
#         args = '{} {} {} {} {} {}'.format(compute, new_interface_, nt, prefix, gateway, metric)
#         code, err_info = cli.system('host-route-add', args, fail_ok=True, rtn_code=True)
#     else: # ipv = 6
#         gateway = "2001:470:27:37e::1"
#         nt = "2001:470:27:37::"
#
#         args = '{} {} {} {} {} {}'.format(compute, new_interface_, nt, prefix, gateway, metric)
#         code, err_info = cli.system('host-route-add', args, fail_ok=True, rtn_code=True)
#
#     LOG.tc_step("TC15: verify the route adding status")
#     if code > 0:
#         if not status:
#             LOG.info("Expect fail: {}".format(err_info))
#             assert NetworkingErr.INVALID_IP_OR_PREFIX in err_info
#         else:
#             LOG.info("Error: {}".format(err_info))
#             assert code, 'Should be failed'
#     else:
#         if not status:
#             LOG.info("Error: {}".format(err_info))
#             assert 0 == code, 'Test should fail, but it passed'
#
#
# @mark.p3
# def test_route_gateway_validation(set_interface_ip_):
#     """
#     16) IP route gateway address must not be null (e.g., ::, 0.0.0.0)
#
#     Args:
#         set_interface_ip_:
#
#     Test Setups:
#         (a) create providernet with type=vxlan
#         (b) lock the host
#         (c) create interface associate with providernet set the ip addressing mode to static for ipv4
#         (d) create ip addr for the interface
#
#     Test Steps:
#         add route with the given gateway
#         verify the route adding status
#     Returns:
#
#     """
#     compute, provider, new_interface_ = set_interface_ip_
#
#     gateway = "0.0.0.0"
#     prefix = 24
#
#     LOG.tc_step("TC16: add route with bad gateway {}".format(prefix))
#
#     nt = '192.168.102.0'
#     metric = 16
#
#     args = '{} {} {} {} {} {}'.format(compute, new_interface_, nt, prefix, gateway, metric)
#     code, err_info = cli.system('host-route-add', args, fail_ok=True, rtn_code=True)
#     if code > 0:
#         LOG.info("Expected error: {}".format(err_info))
#         assert NetworkingErr.NULL_GATEWAY_ADDR in err_info
#     else:
#         assert 1 == code, 'should not be here'
#
#
# @mark.p3
# def test_route_network_ip_validation(set_interface_ip_):
#     """
#     17) IP route network address must be valid
#
#     Args:
#         set_interface_ip_:
#
#     Test Setups:
#         (a) create providernet with type=vxlan
#         (b) lock the host
#         (c) create interface associate with providernet set the ip addressing mode to static for both ipv4 and ipv6
#         (d) create ip addr for the interface
#
#     Test Steps:
#         add route with the given invalid network ip
#         verify the route adding status
#     Returns:
#
#     """
#     compute, provider, new_interface_ = set_interface_ip_
#
#     gateway = "192.168.3.0"
#     prefix = 24
#     nt = '192.168.102.12'  # invalid one
#     metric = 16
#
#     LOG.tc_step("TC17: add route with bad network address {}".format(nt))
#
#     args = '{} {} {} {} {} {}'.format(compute, new_interface_, nt, prefix, gateway, metric)
#     code, err_info = cli.system('host-route-add', args, fail_ok=True, rtn_code=True)
#     if code > 0:
#         LOG.info("Expected error: {}".format(err_info))
#         assert NetworkingErr.INVALID_IP_NETWORK in err_info
#     else:
#         assert 1 == code, 'should not be here'
#
#
# @mark.p3
# def test_route_gateway_ip_validation(set_interface_ip_):
#     """
#     18) IP route gateway address must be valid
#
#     Args:
#         set_interface_ip_:
#
#     Test Setups:
#         (a) create providernet with type=vxlan
#         (b) lock the host
#         (c) create interface associate with providernet set the ip addressing mode to static for both ipv4 and ipv6
#         (d) create ip addr for the interface
#
#     Test Steps:
#         add route with the given invalide gateway
#         verify the route adding status
#     Returns:
#
#     """
#     compute, provider, new_interface_ = set_interface_ip_
#
#     gateway = "192.168.33.1"  # invalid one
#     prefix = 24
#     nt = '192.168.102.0'
#     metric = 16
#
#     LOG.tc_step("TC18: add route with bad gateway address {}".format(gateway))
#
#     args = '{} {} {} {} {} {}'.format(compute, new_interface_, nt, prefix, gateway, metric)
#     code, err_info = cli.system('host-route-add', args, fail_ok=True, rtn_code=True)
#
#     if code > 0:
#         LOG.info("Expected error: {}".format(err_info))
#         assert NetworkingErr.ROUTE_GATEWAY_UNREACHABLE in err_info
#     else:
#         assert 1 == code, 'should not be here'
#
#
# @mark.p3
# @mark.parametrize(('gateway', 'nt', 'prefix'), [
#     ('192.168.102.0', 'FE80:_', 64),    # fail expected
#     ('FE80:0000:0000:0000:0202:B3FF:FE1E:0000', '192.168.102.0', 24),    # fail expected
# ])
# def test_route_network_gateway_ip_in_same_families(set_interface_ip_, gateway, nt, prefix):
#     """
#     19) IP route network and gateway families must be the same (i.e., both IPv4 or both IPv6)
#
#     Args:
#         set_interface_ip_:
#         gateway:
#         nt:
#         prefix:
#
#     Test Setups:
#         (a) create providernet with type=vxlan
#         (b) lock the host
#         (c) create interface associate with providernet set the ip addressing mode to static for both ipv4 and ipv6
#         (d) create ip addr for the interface
#
#     Test Steps:
#         add route with the given network and gateway which are not in same families
#         verify the route adding status
#     Returns:
#
#     """
#     nt = nt.replace(':_', '::')
#     compute, provider, new_interface_ = set_interface_ip_
#
#     metric = 16
#
#     LOG.tc_step("TC19: add route with bad gateway address {}".format(gateway))
#
#     args = '{} {} {} {} {} {}'.format(compute, new_interface_, nt, prefix, gateway, metric)
#     code, err_info = cli.system('host-route-add', args, fail_ok=True, rtn_code=True)
#     if code > 0:
#         LOG.info("Expected error: {}".format(err_info))
#         assert NetworkingErr.IP_VERSION_NOT_MATCH in err_info
#     else:
#         assert 1 == code, 'should not be here'
#
#
# @mark.p3
# @mark.parametrize('gateway', [
#     ("192.168.3.11"),   #  gateway should be 172.16.102.1
#     ("192.168.3.3"),    #  local address  TC26
#     ("192.168.3.0"),    #  network addr  for test case 21
#     ("192.168.3.255"),  #  brodcast addr
#     ("192.168.2.1"),    #  other network gateway addr
# ])
# def test_route_gateway_addr_validation(set_interface_ip_, gateway):
#     """
#     20) IP route gateway address must not be part of the destination subnet
#     21) IP route gateway must be a unicast address
#     25) IP route gateway address must be a member of a subnet that corresponds to a local IP address on the same interface
#     26) IP route gateway address must not be a currently configured local address
#
#     Args:
#         set_interface_ip_:
#         gateway:
#
#     Test Setups:
#         (a) create providernet with type=vxlan
#         (b) lock the host
#         (c) create interface associate with providernet set the ip addressing mode to static for ipv4
#         (d) create ip addr for the interface
#
#     Test Steps:
#         add route with the given gateway
#         verify the route adding status
#     Returns:
#
#     """
#     compute, provider, new_interface_ = set_interface_ip_
#
#     prefix = 24
#     nt = '192.168.3.0'
#     metric = 16
#
#     LOG.tc_step("TC20: add route with bad gateway address {}".format(gateway))
#
#     args = '{} {} {} {} {} {}'.format(compute, new_interface_, nt, prefix, gateway, metric)
#     code, err_info = cli.system('host-route-add', args, fail_ok=True, rtn_code=True)
#     err_msg_tc20 = NetworkingErr.GATEWAY_IP_IN_SUBNET
#     err_msg_tc21 = NetworkingErr.NETWORK_IP_EQUAL_TO_GATEWAY
#     err_msg_tc25 = NetworkingErr.ROUTE_GATEWAY_UNREACHABLE
#     if code > 0:
#         LOG.info("Expected error: {}".format(err_info))
#         assert err_msg_tc20 or err_msg_tc21 or err_msg_tc25 in err_info
#     else:
#         assert 1 == code, 'should not be here'
#
#
# @mark.p3
# @mark.parametrize('nt', [
#     ('192.168.3.1'),    # try gateway addr
#     ('192.168.3.2'),    # try DHCP addr
#     ('192.168.3.255'),  # try broadcase addr
# ])
# def test_route_network_addr_must_be_unicast(set_interface_ip_, nt):
#     """
#     22) IP route network must be a unicast address
#
#     Args:
#         set_interface_ip_:
#         nt:
#
#     Test Setups:
#         (a) create providernet with type=vxlan
#         (b) lock the host
#         (c) create interface associate with providernet set the ip addressing mode to static for both ipv4 and ipv6
#         (d) create ip addr for the interface
#
#     Test Steps:
#         add route with the given network ip
#         verify the route adding status
#
#     Returns:
#
#     """
#     compute, provider, new_interface_ = set_interface_ip_
#
#     prefix = 24
#     gateway = '192.168.3.1'
#     metric = 16
#
#     LOG.tc_step("TC22: add route with bad network address {}".format(nt))
#
#     args = '{} {} {} {} {} {}'.format(compute, new_interface_, nt, prefix, gateway, metric)
#     code, err_info = cli.system('host-route-add', args, fail_ok=True, rtn_code=True)
#     if code > 0:
#         LOG.info("Expected error: {}".format(err_info))
#         assert NetworkingErr.INVALID_IP_NETWORK in err_info
#     else:
#         assert 1 == code, 'should not be here'
#
#
# @mark.p3
# def test_route_unique(set_interface_ip_):
#     """
#     27) IP route must be unique (network + prefix + gateway)
#
#     Args:
#         set_interface_ip_:
#
#     Test Setups:
#         (a) create providernet with type=vxlan
#         (b) lock the host
#         (c) create interface associate with providernet set the ip addressing mode to static for both ipv4 and ipv6
#         (d) create ip addr for the interface
#
#     Test Steps:
#         add route with the network, prefix and gateway twice
#         verify the second time route adding status
#     Returns:
#
#     """
#     compute, provider, new_interface_ = set_interface_ip_
#
#     prefix = 24
#     gateway = '192.168.3.1'
#     metric = 16
#
#     nt = '200.10.0.0'
#     LOG.tc_step("TC27: add first route address {}".format(nt))
#     args = '{} {} {} {} {} {}'.format(compute, new_interface_, nt, prefix, gateway, metric)
#     cli.system('host-route-add', args, rtn_code=True)
#
#     LOG.tc_step("TC27: add second route with same ip will fail")
#     code, err_info = cli.system('host-route-add', args, fail_ok=True, rtn_code=True)
#     err_msg = NetworkingErr.DUPLICATE_IP_ADDR
#     if code > 0:
#         LOG.info("Expected error: {}".format(err_info))
#         assert err_msg in err_info
#     else:
#         assert 1 == code, 'should not be here'
