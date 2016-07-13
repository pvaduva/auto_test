from pytest import fixture, mark, skip
import random
import time
from utils import table_parser
from utils.tis_log import LOG
from utils import cli

from consts.auth import Tenant
from keywords import host_helper, network_helper
from testfixtures.recover_hosts import HostsToRecover

@fixture(scope='module')
def locked_nova_host(request):

    nova_host = random.choice(host_helper.get_nova_hosts())
    nova_host = 'compute-2'
    host_helper.lock_host(nova_host)
    # HostsToRecover.add(nova_host, scope='module')

    return nova_host


@fixture(scope='module', autouse=True)
def providernet_():
    """

    step: from "neutron providernet-list" get the provider's name if the type is vxlan
    Returns: provider-nets if find it, also return segmentation range name
             will skip all test if no vxlan type of provider network is find
             or create one and continue

    """
    providernets = network_helper.get_provider_nets(strict=True, type='vxlan')
    if not providernets:
        skip(" ******* No vxlan provider-net configured.")

    range_name = 'neutron_check_vxlan'

    return providernets, range_name


@fixture(scope='module')
def prepare_segmentation_range(providernet_, request):
    """
    This fixture is for TC7 use

    Args:
        providernet_:
        request:
        steps:  create segmentation range

    Returns:  providers, range name, low and high range number

    """
    list_providers, name = providernet_
    low_rang = 6000
    high_rang = 6020
    code, err_info = network_helper.create_vxlan_providernet_range(list_providers[0], name, range_min=low_rang,
                                                                   range_max=high_rang)
    if code > 0:
        skip("The segmentation range exist and overlap with this one, delete it and try again")

    def fin():
        network_helper.delete_vxlan_providernet_range(name)
    request.addfinalizer(fin)

    return list_providers[0], name, low_rang, high_rang


@fixture(scope='module')
def prepare_multiple_provider_net_range_verify(locked_nova_host, request):
    """
    This is for TC8 use only
    Args:
        locked_nova_host:
        request:

    steps: create two provider networks
            find a free port/interface
            create an interface associate with the two provider networks
            create one segmentation range
    Returns:

    """


    providernet_names = ['provider_net_vxlan_1', 'provider_net_vxlan_2']

    # Create two provider networks
    for provider in providernet_names:
        args = provider + ' --type=vxlan'
        code, output = cli.neutron('providernet-create', args, auth_info=Tenant.ADMIN, fail_ok=True, rtn_list=True)
        # time.sleep(1)

        if code > 0 and "already exists" not in output:
            skip("Provider-net creation failed, can not test this case")


    # Create interface to associate with the two provider-nets

    # Find a free port from host-if-list -a
    args = '{} {}'.format(locked_nova_host, "-a")
    table_ = table_parser.table(cli.system('host-if-list', args, auth_info=Tenant.ADMIN))
    list_interfaces = table_parser.get_values(table_, 'name', **{'type': 'ethernet', 'network type': 'None'})
    if not list_interfaces:
        skip("Can not find a free port to create data interface ")

    port = random.choice(list_interfaces)

    # Create an interface associate with the two providers just create
    interface = 'test0if'
    args = locked_nova_host + ' ' + interface + ' ae '
    args += r'"{},{}" '.format(providernet_names[0], providernet_names[1])
    args += port + ' -nt data -m {}'.format(1600)
    code, err_info = cli.system('host-if-add', args, auth_info=Tenant.ADMIN, fail_ok=True, rtn_list=True)

    if code > 0:
        skip("can not create the data interface {}".format(err_info))

    # the name of the range is: providernet_names[0]_shared
    r_min = 6000
    r_max = 6050
    range_name = providernet_names[0] + '_shared'

    code, err_info = network_helper.create_vxlan_providernet_range(providernet_names[0], range_name, range_min=r_min,
                                                                   range_max=r_max)

    if code > 0:
        skip("create first provider network segmentation range {}-{} failed".format(r_min, r_max))

    def fin():
        # Clean up: remove the ranges and providers just created
        network_helper.delete_vxlan_providernet_range(range_name)

        args = '{} {}'.format(locked_nova_host, interface)
        cli.system('host-if-delete', args, auth_info=Tenant.ADMIN)

        for provider in providernet_names:
            cli.neutron('providernet-delete', provider, auth_info=Tenant.ADMIN)

    request.addfinalizer(fin)

    return providernet_names


@fixture(scope='module')
def prepare_mtu_verification(locked_nova_host, request):

    providernet_name = 'neutron_provider_net_vxlan'

    # Create provider networks
    args = providernet_name + ' --type=vxlan'
    code, output = cli.neutron('providernet-create', args, auth_info=Tenant.ADMIN, fail_ok=True, rtn_list=True)

    if code > 0 and "already exists" not in output:
        skip("Create provider network failed")

    args = '{} {}'.format(locked_nova_host, "-a")
    table_ = table_parser.table(cli.system('host-if-list', args, ssh_client=None, auth_info=Tenant.ADMIN))
    list_interfaces = table_parser.get_values(table_, 'name', **{'type': 'ethernet', 'network type': 'None'})
    if not list_interfaces:
        skip("Can not find data interface ")

    # Find a free interface
    interface = random.choice(list_interfaces)

    # Clean the provider network")
    def fin():
        cli.neutron('providernet-delete', providernet_name, auth_info=Tenant.ADMIN)

    request.addfinalizer(fin)

    return providernet_name, interface, locked_nova_host


@mark.parametrize(('r_min', 'r_max'), [
    (1, pow(2, 24)),
    (0, pow(2, 24)-1),
])
def test_2_vxlan_vnt_maximum_range(r_min, r_max, providernet_):
    """
    TC 2) Verify ability to provision VxLan VNI in maximum range (2^24)-100 --> (2^24)-1

    Args:
        providernet, - fixture for create the providernet
        r_min - low bound of Segmentation range
        r_man - high bound of Segmentation range

    Test Setups (module):
        - try to create segmentation ranges in given providernet

    Test Steps:
        - after providernet has been created and success
        - create segmentation ranges with the boundary value

    Test Teardown:
        since this is failure test, the segmentation creation should not success. Will be delete if success
    """

    provider, name = providernet_

    code, err_info = network_helper.create_vxlan_providernet_range(provider[0], name, range_min=r_min, range_max=r_max)

    expected_msg = "VXLAN id range {} to {} exceeds 16777215".format(r_min, r_max)
    if code > 0:
        LOG.info("Expect fail when range out of bound ({}, {})".format(r_min, r_max))
        assert expected_msg in err_info
    else:
        network_helper.delete_vxlan_providernet_range(name)
        assert 1 == code, "Should not pass when range out bourn"


@mark.parametrize('addr', [
    '223.255.255.255',
    '240.0.0.0',
])
def test_3_vxlan_valid_multicast_addr(addr, providernet_):
    """
    3) The multicast group addresses are limited (224.0.0.0 to 239.255.255.255).

    Args:
        addr:
        providernet_:  -- create a provider-net

    Returns:

    """

    r_max = pow(2, 24) - 1
    r_min = r_max - 100

    providernets, name = providernet_

    code, err_info = network_helper.create_vxlan_providernet_range(providernets[0], name, group=addr,
                                                                   range_min = r_min, range_max = r_max)

    expected_msg = "Invalid input for group. Reason: '{}' is not a valid multicast IP address.".format(addr)

    if code > 0:
        LOG.info("Expect fail when the multicast group addresses are not in (224.0.0.0 to 239.255.255.255).")
        assert err_info == expected_msg
    else:
        network_helper.delete_vxlan_providernet_range(name)
        assert 1 == code, "Should not pass when multicast addresses are out of range"


@mark.parametrize('the_port', [
    8473,
    4788,
])
def test_4_vxlan_valid_port(the_port, providernet_):
    """
    4) Verify that only a one of two valid ports (4789 or 8472) can be provisioned on vxLan provider network
    IANA port 4789
    Cisco port 8472

    Args:
        the_port:
        providernet_:

    Returns:

    """

    r_max = pow(2, 24) - 1
    r_min = r_max - 100

    provider, name = providernet_

    code, err_info = network_helper.create_vxlan_providernet_range(provider[0], name, port=the_port,
                                                                   range_min=r_min, range_max=r_max)

    expected_msg = "Invalid input for port. Reason: '{}' is not in [4789, 8472].".format(the_port)
    if code > 0:
        LOG.info("Expect fail when port is not 4789 or 8472")
        assert err_info == expected_msg
    else:
        network_helper.delete_vxlan_providernet_range(name)
        assert 1 == code, "Should not pass when port is not valid"


@mark.parametrize('the_ttl', [
    0,
    256,
])
def test_5_vxlan_valid_ttl(the_ttl, providernet_):
    """
    5) Verify that vxLan provider network TTL is configurable in range of 1-255

    Args:
        the_ttl:
        providernet_:

    Returns:

    """

    r_max = pow(2, 24) - 1
    r_min = r_max - 100

    providernets, name = providernet_

    code, err_info = network_helper.create_vxlan_providernet_range(providernets[0], name, ttl=the_ttl, range_min=r_min,
                                                                   range_max=r_max)

    expected_msg = "VXLAN time-to-live attributes missing".format(r_min, r_max)  # that's for ttl=0
    expected_msg2 = "is too large - must be no larger than '255'."               # that's for ttl>255
    if code > 0:
        LOG.info("Expect fail when TTL is not in range (1, 255)")
        assert err_info == expected_msg or expected_msg2 in err_info
    else:
        network_helper.delete_vxlan_providernet_range(name)
        assert 1 == code, "Should not pass when TTL is our of range 1 to 255"


@mark.parametrize(('r_min', 'r_max'), [
    (0, 0),  # the range will be:  low_rang+r_min to high_rang+r_max
    (-5, -5),
    (0, 5),
    (5, -5),
    (-5, 5),
])
def test_7_vxlan_same_providernet_overlapping_segmentation(r_min, r_max, prepare_segmentation_range):
    """
    7)  two ranges on the same provider network cannot have overlapping segmentation ranges
        the same range create twice
        assume this range has not been created before

    Args:
        r_min:
        r_max:
        prepare_segmentation_range:

    Returns:

    """

    provider, name, low_rang, high_rang = prepare_segmentation_range

    r_min = low_rang + r_min
    r_max = high_rang + r_max

    # second time create it should be fail because using same segmentation range
    code, err_info = network_helper.create_vxlan_providernet_range(provider, name, range_min=r_min, range_max=r_max)
    expected_msg = "segmentation id range overlaps with"
    if code > 0:
        LOG.info("Expect fail when two ranges on the same provider network have overlapping segmentation ranges")
        assert expected_msg in err_info
    else:
        assert 1 == code, "Should not pass when the two ranges on the same provider-nt have overlapping seg ranges"



@mark.parametrize(('r_min', 'r_max'), [
    (6000, 6050),
    (6010, 6040),
    (6010, 6040),
])
def test_8_vxlan_same_ranges_on_different_provider_negative(prepare_multiple_provider_net_range_verify, r_min, r_max,
                                                            fail_ok=True):
    """
    8) two ranges on different provider networks cannot have overlapping segmentation ranges if associated to the same
    data interface

    Args:
        prepare_multiple_provider_net_range_verify
        range1:
        fail_ok:

        the first segmentation range is 6050
    Returns:

    """
    # neutron providernet-create group0-data11aa --type=vxlan
    # system host-if-modify

    # create two provider networks
    providers = prepare_multiple_provider_net_range_verify

    LOG.tc_step("Create the second range, first been created in fixture")

    range_name = providers[1] + '_shared'
    code, output = network_helper.create_vxlan_providernet_range(providers[1], range_name, range_min=r_min,
                                                                   range_max=r_max)

    expected_msg = "Provider network segmentation id range overlaps with"

    if code > 0:
        LOG.info("Expect fail when create second provider network range  failed:{}".format(output))
        assert expected_msg in output
    else:
        range_name = providers[1] + '_shared'
        network_helper.delete_vxlan_providernet_range(range_name)
        assert 1 == code, "Should not pass when two range overlap and try to associate to same data if"


@mark.parametrize('the_mtu', [
    1573,
    1500,
    1400,
])
def test_9_vxlan_mtu_value(prepare_mtu_verification, the_mtu):

    """
    9) MTU value of a provider network must be less than that of its associated data interface.  For vxLan, the data
       interface MTU must be large enough to accommodate the largest possible tenant packet *and* the VXLAN overhead
       (see overview document)

    Args:
        prepare_mtu_verification:
        the_mtu:

     create provider network with mut=1500
     lock the compute
     add interface associate with the provider network with:
     neutron providernet-create group0-data11aa --type=vxlan
     system host-if-add compute-1 data11aa ae group0-data11aa  data1 -nt data -m 1600 --ipv4-mode=pool --ipv4-pool=management

    Returns:

    """

    providernet_name, interface, compute = prepare_mtu_verification

    LOG.tc_step("Try to create interface with MTU={} less then the one from provider MTU=1500+x".format(the_mtu))
    new_interface_ = 'testif9'
    args = compute + ' ' + new_interface_ + ' ae ' + providernet_name + ' ' + interface + ' -nt data -m {}'.format(the_mtu)
    code, err_info = cli.system('host-if-add', args, auth_info=Tenant.ADMIN, fail_ok=True, rtn_list=True)

    expected_msg = "requires an interface MTU value of at least"
    if code > 0:
        LOG.info("Expect fail: MTU value of a provider network must be less than that of its associated data interface")
        assert expected_msg in err_info
    else:
        args = '{} {}'.format(compute, new_interface_)
        cli.system('host-if-delete', args, auth_info=Tenant.ADMIN)
        assert 1 == code, "Should not pass when the MTU less than the one in provider"



