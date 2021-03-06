# import random
#
# from pytest import fixture, mark, skip
#
# from utils import table_parser
# from utils.tis_log import LOG
# from utils import cli
# from consts.auth import Tenant
# from consts.cli_errs import NetworkingErr
# from keywords import host_helper, network_helper, common, system_helper
# from testfixtures.recover_hosts import HostsToRecover
#
#
# pro_net_name = 'provider_vxlan'
#
#
# @fixture(scope='function')
# def check_alarms():
#     pass
#
#
# @fixture(scope='module', autouse=True)
# def providernet_(request):
#
#     providernets = system_helper.get_data_networks(network_type='vxlan')
#     if not providernets:
#         skip("No vxlan provider-net configured")
#
#     provider = common.get_unique_name(pro_net_name, resource_type='other')
#     args = provider + ' --type=vxlan'
#
#     table_ = table_parser.table(cli.neutron('providernet-list', auth_info=Tenant.get('admin')))
#     if not table_parser.get_values(table_, 'id', **{'name': provider}):
#         cli.neutron('providernet-create', args, auth_info=Tenant.get('admin'), rtn_code=True)
#
#     range_name = provider + '_range'
#
#     def fin():
#         cli.neutron('providernet-delete', provider, auth_info=Tenant.get('admin'))
#     request.addfinalizer(fin)
#
#     return provider, range_name
#
#
# @mark.p3
# @mark.parametrize(('r_min', 'r_max'), [
#     (1, pow(2, 24)),
#     (0, pow(2, 24)-1),
# ])
# def test_vxlan_vni_maximum_range_negative(r_min, r_max, providernet_):
#     """
#     TC 2) Verify ability to provision VxLan VNI in maximum range (2^24)-100 --> (2^24)-1
#
#     Args:
#         providernet, - fixture for create the providernet
#         r_min - low bound of Segmentation range
#         r_man - high bound of Segmentation range
#
#     Test Setups (module):
#         - Create segmentation ranges in given providernet
#
#     Test Steps:
#         - create segmentation ranges with the boundary value
#         - Verify the segmentation range can not be created
#         - The created segmentation range will be removed if success
#
#     Test Teardown:
#         since this is failure test, the segmentation creation should not success. Will be delete if success
#     """
#
#     provider, range_name = providernet_
#
#     LOG.tc_step("Create the segmentation range")
#     code, err_info = create_vxlan_providernet_range(provider, range_name=range_name, range_min=r_min, range_max=r_max)
#
#     LOG.tc_step("Verify the segmentation range creation should be failed")
#
#     if code > 0:
#         LOG.info("Expect fail when range out of bound ({}, {})".format(r_min, r_max))
#         assert NetworkingErr.INVALID_VXLAN_VNI_RANGE in err_info
#     else:
#         LOG.tc_step("The segmentation range should be removed if success")
#         network_helper.delete_providernet_range(range_name)
#         assert 1 == code, "Should not pass when range out bourn"
#
#
# @mark.p3
# @mark.parametrize('addr', [
#     '223.255.255.255',
#     '240.0.0.0',
# ])
# def test_vxlan_valid_multicast_addr_negative(addr, providernet_):
#     """
#     3) Verify the multicast group addresses are limited (224.0.0.0 to 239.255.255.255), any address out
#         of this range will cause error.
#
#     Args:
#         addr:
#         providernet_:  -- create a provider-net
#
#     Test Setup (module):
#         - Create segmentation ranges in given providernet
#
#     Test Steps:
#         create segmentation ranges with given multcast group address
#         verify the status of the range creation, it should be failed
#         the created range will be removed if success
#
#     Test Teardown
#         the segmenation range will be removed if successfully created
#     """
#
#     r_max = pow(2, 24) - 1
#     r_min = r_max - 100
#
#     provider, range_name = providernet_
#
#     LOG.tc_step("Create the segmentation range with given multcast group addr {}".format(addr))
#     code, err_info = create_vxlan_providernet_range(provider, range_name=range_name, group=addr, range_min=r_min,
#                                                     range_max=r_max)
#
#     LOG.tc_step("Verify the segmentation range creation should be failed")
#     if code > 0:
#         LOG.info("Expect fail when the multicast group addresses are not in (224.0.0.0 to 239.255.255.255).")
#         assert NetworkingErr.INVALID_MULTICAST_IP_ADDRESS in err_info
#     else:
#         network_helper.delete_providernet_range(range_name)
#         assert 1 == code, "Should not pass when multicast addresses are out of range"
#
#
# @mark.p3
# @mark.parametrize('the_port', [
#     8473,
#     4788,
# ])
# def test_vxlan_valid_port_negative(the_port, providernet_):
#     """
#     4) Verify that only a one of two valid ports (4789 or 8472) can be provisioned on vxLan provider network
#     IANA port 4789
#     Cisco port 8472
#
#     Args:
#         the_port:
#         providernet_:
#
#     Test Setup (module):
#         - Create segmentation ranges in given providernet
#
#     Test Steps:
#         create segmentation ranges with given port number
#         verify the status of the range creation with the invalid ports, it should be failed
#         the created range will be removed if success
#
#     Test Teardown
#         the segmenation range will be removed if successfully created
#
#     Returns:
#
#     """
#
#     r_max = pow(2, 24) - 1
#     r_min = r_max - 100
#
#     provider, range_name = providernet_
#
#     LOG.tc_step("Create the segmentation range with the port {}".format(the_port))
#     code, err_info = create_vxlan_providernet_range(provider, range_name=range_name, port=the_port,
#                                                     range_min=r_min, range_max=r_max)
#
#     LOG.tc_step("Verify the segmentation range creation should be failed")
#     if code > 0:
#         LOG.info("Expect fail when port is not 4789 or 8472")
#         assert NetworkingErr.INVALID_VXLAN_PROVISION_PORTS in err_info
#     else:
#         network_helper.delete_providernet_range(range_name)
#         assert 1 == code, "Should not pass when port is not valid"
#
#
# @mark.p3
# @mark.parametrize('the_ttl', [
#     0,
#     256,
# ])
# def test_vxlan_valid_ttl_negative(the_ttl, providernet_):
#     """
#     5) Verify that vxLan provider network TTL is configurable in range of 1-255
#
#     Args:
#         the_ttl:
#         providernet_:
#
#     Test Setup (module):
#         - Create segmentation ranges in given providernet
#
#     Test Steps:
#         create segmentation ranges with given ttl number
#         verify the status of the range creation with the invalid ttl numbers, it should be failed
#         the created range will be removed if success
#
#     Test Teardown
#         the segmenation range will be removed if successfully created
#     Returns:
#
#     """
#
#     r_max = pow(2, 24) - 1
#     r_min = r_max - 100
#
#     provider, range_name = providernet_
#
#     LOG.tc_step("Create the segmentation range with ttl {}".format(the_ttl))
#     code, err_info = create_vxlan_providernet_range(provider, range_name=range_name, ttl=the_ttl, range_min=r_min,
#                                                     range_max=r_max)
#
#     LOG.tc_step("Verify the segmentation range creation should be failed")
#     # the two error message one for ttl=0  and another one if for ttl>255
#     if code > 0:
#         LOG.info("Expect fail when TTL is not in range (1, 255)")
#         assert NetworkingErr.VXLAN_TTL_RANGE_MISSING in err_info or \
#             NetworkingErr.VXLAN_TTL_RANGE_TOO_LARGE in err_info or \
#             NetworkingErr.VXLAN_TTL_RANGE_TOO_SMALL in err_info
#     else:
#         network_helper.delete_providernet_range(range_name)
#         assert 1 == code, "Should not pass when TTL is our of range 1 to 255"
#
#
# @fixture(scope='module')
# def prepare_segmentation_range(request):
#     provider = common.get_unique_name(pro_net_name, resource_type='other')
#     min_rang = 7000
#     max_rang = 7020
#
#     args = provider + ' --type=vxlan'
#     code, output = cli.neutron('providernet-create', args, auth_info=Tenant.get('admin'), fail_ok=True, rtn_code=True)
#
#     if not code:
#         table_ = table_parser.table(output)
#         provider_id = table_parser.get_value_two_col_table(table_, 'id')
#     else:
#         provider_id = system_helper.get_data_networks(network_type='vxlan', name=provider)[0]
#
#     range_name = provider+"_range"
#     range_name = create_vxlan_providernet_range(provider_id, range_name=range_name, range_min=min_rang,
#                                                 range_max=max_rang)[1]
#
#     def fin():
#         network_helper.delete_providernet_range(range_name)
#         cli.neutron('providernet-delete', provider, auth_info=Tenant.get('admin'))
#     request.addfinalizer(fin)
#
#     return provider_id, range_name, min_rang, max_rang
#
#
# @mark.p3
# @mark.parametrize(('r_min', 'r_max'), [
#     (0, 0),  # the range will be:  low_rang+r_min to high_rang+r_max
#     (-5, -5),
#     (0, 5),
#     (5, -5),
#     (-5, 5),
# ])
# def test_vxlan_same_providernet_overlapping_segmentation_negative(r_min, r_max, prepare_segmentation_range):
#     """
#     7)  two ranges on the same provider network cannot have overlapping segmentation ranges
#         the same range create twice
#         assume this range has not been created before
#
#     Args:
#         r_min:
#         r_max:
#         prepare_segmentation_range:
#
#     Test Setups:
#         create one provider-net
#         create a segmentation range with given ranges
#
#     Test Steps:
#         create segmentation again with the given rangs which overlapping with the crated ranges
#         verify the range creation status, it should be failed
#
#     Test Teardown:
#         delete range if creation successfully,
#         delete the range had been created
#         delete the provider-net
#
#     Returns:
#
#     """
#
#     provider_id, range_name, low_rang, high_rang = prepare_segmentation_range
#
#     r_min = low_rang + r_min
#     r_max = high_rang + r_max
#
#     LOG.tc_step("Create the segmentation range with the range {}-{}".format(r_min, r_max))
#     # second time create it should be fail because using same segmentation range
#     code, err_info = create_vxlan_providernet_range(provider_id, range_name=range_name, range_min=r_min,
#                                                     range_max=r_max)
#
#     LOG.tc_step("Verify the segmentation range creation should be failed")
#     if code > 0:
#         LOG.info("Expect fail when two ranges on the same provider network have overlapping segmentation ranges")
#         assert NetworkingErr.OVERLAP_SEGMENTATION_RANGE in err_info
#     else:
#         assert False, "Should not pass when the two ranges on the same providernet have overlapping seg ranges"
#
#
# @fixture(scope='module')
# def multiple_provider_net_range(request):
#
#     providernet_names = [common.get_unique_name(pro_net_name, resource_type='other'),
#                          common.get_unique_name(pro_net_name, resource_type='other')]
#     r_min = 8000
#     r_max = 8050
#
#     # Create two provider networks
#     provider_ids = []
#     for provider in providernet_names:
#         args = provider + ' --type=vxlan'
#         code, out = cli.neutron('providernet-create', args, auth_info=Tenant.get('admin'), fail_ok=True, rtn_code=True)
#         if code == 0:
#             table_ = table_parser.table(out)
#             provider_ids.append(table_parser.get_value_two_col_table(table_, 'id'))
#         else:
#             provider_ids.append(system_helper.get_data_networks(network_type='vxlan', name=provider)[0])
#
#     # Create interface to associate with the two provider-nets
#     nova_hosts = host_helper.get_hypervisors(state='up')
#     if not nova_hosts:
#         skip("Can not continue without computer host node")
#
#     # find a free interface
#     computer_host = if_name = None
#     for nova_host in nova_hosts:
#         args = '{} {}'.format(nova_host, "-a --nowrap")
#         table_ = table_parser.table(cli.system('host-if-list', args, auth_info=Tenant.get('admin')))
#         list_interfaces = table_parser.get_values(table_, 'name', **{'type': 'ethernet', 'class': 'None',
#                                                                      'used by i/f': '[]'})
#
#         if list_interfaces:
#             computer_host = nova_host
#             if_name = random.choice(list_interfaces)
#             break
#     else:
#         skip("Can not find a free data interface")
#
#     host_helper.lock_host(computer_host, swact=True)
#     HostsToRecover.add(computer_host, scope='module')
#
#     # Create an interface associate with the two providers just create
#     interface = 'test0if'
#     host_helper.add_host_interface(computer_host, if_name=interface, if_type='ae', ports_or_ifs=if_name, mtu=1600,
#                                    pnet=','.join(providernet_names[:2]), if_class='data', ipv4_mode='static',
#                                    lock_unlock=False)
#
#     # the name of the range is: providernet_names[0]_range
#     range_name = providernet_names[0] + '_range'
#     code, range_name = create_vxlan_providernet_range(provider_ids[0], range_name=range_name, range_min=r_min,
#                                                       range_max=r_max)
#
#     def fin_teardown():
#         # Clean up: remove the ranges and providers just created
#         network_helper.delete_providernet_range(range_name)
#
#         for pnet in providernet_names:
#             cli.neutron('providernet-delete', pnet, auth_info=Tenant.get('admin'))
#     request.addfinalizer(fin_teardown)
#
#     if code > 0:
#         msg = "create first provider network segmentation range {}-{} failed".format(r_min, r_max)
#         assert False, msg
#
#     return providernet_names, r_min, r_max, computer_host, if_name, interface
#
#
# @mark.p3
# @mark.parametrize(('r_min', 'r_max'), [
#     (0, 0),
#     (-10, -10),
#     (0, 10),
#     (10, -10),
#     (-10, 10),
# ])
# def test_vxlan_same_ranges_on_different_provider_negative(multiple_provider_net_range, r_min, r_max):
#
#     """
#     8) two ranges on different provider networks cannot have overlapping segmentation ranges if associated to the same
#     data interface
#
#     Args:
#         multiple_provider_net_range
#         r_max
#         r_min
#
#     Test Setups (module):
#         - Create two provider net
#         - Create interface associate with the two provider-nets
#         - create segmentation ranges for first providernet
#
#     Test Steps:
#         - create segmentation ranges for second providernet
#         - Verify the segmentation range can not be created
#         - The created segmentation range will be removed if success
#
#     Test Teardown:
#         since this is failure test, the segmentation creation should not success. Will be delete if success
#
#     Returns:
#
#     """
#     # neutron providernet-create group0-data11aa --type=vxlan
#     # system host-if-modify
#
#     # create two provider networks
#     providers, low_rang, high_rang, x, y, z = multiple_provider_net_range
#
#     r_min = low_rang + r_min
#     r_max = high_rang + r_max
#
#     LOG.tc_step("Create the second range, first been created in fixture")
#     range_name = providers[1] + '_shared'
#     code, output = create_vxlan_providernet_range(providers[1], range_name=range_name, range_min=r_min, range_max=r_max)
#
#     LOG.tc_step("Verify the segmentation range creation should be failed")
#     if code > 0:
#         LOG.info("Expect fail when create second provider network range  failed:{}".format(output))
#         assert NetworkingErr.OVERLAP_SEGMENTATION_RANGE in output
#     else:
#         range_name = providers[1] + '_shared'
#         network_helper.delete_providernet_range(range_name)
#         assert 1 == code, "Should not pass when two range overlap and associate to same data if"
#
#
# @mark.p3
# @mark.parametrize('the_mtu', [
#     1573,
#     1500,
#     1400,
# ])
# def test_vxlan_mtu_value_negative(multiple_provider_net_range, the_mtu):
#
#     """
#     9) MTU value of a provider network must be less than that of its associated data interface.  For vxLan, the data
#        interface MTU must be large enough to accommodate the largest possible tenant packet *and* the VXLAN overhead
#        (see overview document)
#
#     Args:
#         multiple_provider_net_range
#         the_mtu:
#
#     Test Setups:
#         create provider network with mut=1500
#         lock the compute
#
#     Test Steps:
#         add interface associate with the provider network with given mtu:
#         verify the interface creation status. it should be failed
#         The created interface will be removed if success
#
#     Returns:
#
#     """
#
#     providernet_names, x, y, computer_host, if_name, new_interface = multiple_provider_net_range
#
#     args = computer_host
#     table_ = table_parser.table(cli.system('host-if-list', args, auth_info=Tenant.get('admin')))
#     if table_parser.get_values(table_, 'name', **{'name': new_interface}):
#         args = '{} {}'.format(computer_host, new_interface)
#         cli.system('host-if-delete', args, auth_info=Tenant.get('admin'))
#
#     LOG.tc_step("Create interface with MTU={} less then the one from provider MTU=1500+x".format(the_mtu))
#     code, err_info = host_helper.add_host_interface(computer_host, if_name=new_interface, if_type='ae',
#                                                     pnet=providernet_names[0], ports_or_ifs=if_name, mtu=the_mtu,
#                                                     if_class='data', lock_unlock=False, fail_ok=True)
#
#     LOG.tc_step("Verify the interface creation should be failed")
#     if code > 0:
#         LOG.info("Expect fail: MTU value of a provider network must be less than that of its associated data interface")
#         assert NetworkingErr.INVALID_MTU_VALUE in err_info
#     else:
#         args = '{} {}'.format(computer_host, new_interface)
#         cli.system('host-if-delete', args, auth_info=Tenant.get('admin'))
#         assert 1 == code, "Should not pass when the MTU less than the one in provider"
#
#
# def create_vxlan_providernet_range(provider_id, range_name, range_min, range_max, group='239.0.0.0', port=4789, ttl=1):
#
#     return network_helper.create_providernet_range(provider_id, range_name=range_name, range_min=range_min,
#                                                    range_max=range_max, group=group, port=port, ttl=ttl,
#                                                    auth_info=Tenant.get('admin'), con_ssh=None, fail_ok=True)
