from pytest import fixture, mark, skip
import random
from utils import table_parser
from utils.tis_log import LOG
from utils import cli

from consts.timeout import SysInvTimeout
from consts.auth import Tenant
from keywords import system_helper, host_helper, network_helper


@fixture(scope='module')
def lock_unlock(request):

    compute = random.choice(host_helper.get_nova_hosts())
    # now lock the computer
    host_helper.lock_host(compute)

    def fin():
        host_helper.unlock_host(compute)
    request.addfinalizer(fin)

    return compute


@fixture(scope='module')
def get_provider_(request):
    # from "neutron providernet-list" get the provider's name if the type is vxlan
    provider = network_helper.get_provider_nets_by_type(type='vxlan', con_ssh=None)

    LOG.info("=*********=provider={}".format(provider))

    if not provider:
        skip(" ******* No vxlan set ")

    name = provider[0] + "-r2-1"

    return provider, name


# 2) Verify ability to provision VxLan VNI in maximum range (2^24)-100 --> (2^24)-1
@mark.parametrize(('r_min', 'r_max'), [
    (pow(2, 24)-100, pow(2, 24)),    # fail expected
    (pow(2, 24)-100, pow(2, 24)+1),  # fail expected
])
def test_vxlan_vnt_in_maximum_range(r_min, r_max, get_provider_):

    provider, name = get_provider_

    code, err_info = network_helper.create_vxlan_providernet_range(provider[0], name, range_min=r_min, range_max=r_max)

    expected_msg = "VXLAN id range {} to {} exceeds 16777215".format(r_min, r_max)
    if code > 0:
        LOG.info("Expect fail when range out of boun ({}, {})".format(r_min, r_max))
        assert err_info == expected_msg
    else:
        network_helper.delete_vxlan_providernet_range(name)
        assert 1 == code, "Should not pass when range out bourn"


#
# 3) The multicast group addresses are limited (224.0.0.0 to 239.255.255.255).
@mark.parametrize(('addr', 'r_min', 'r_max'), [
    ('223.0.0.0', pow(2, 24) - 100, pow(2, 24) - 1),  # fail expected
    ('240.0.0.0', pow(2, 24) - 100, pow(2, 24) - 1),  # fail expected
])
def test_vxlan_valid_multicast_addr(addr, r_min, r_max, get_provider_):
    provider, name = get_provider_

    code, err_info = network_helper.create_vxlan_providernet_range(provider[0], name, group=addr,
                                                                   range_min = r_min, range_max = r_max)

    expected_msg = "Invalid input for group. Reason: '{}' is not a valid multicast IP address.".format(addr)

    if code > 0:
        LOG.info("Expect fail when the multicast group addresses are not in (224.0.0.0 to 239.255.255.255).")
        assert err_info == expected_msg
    else:
        network_helper.delete_vxlan_providernet_range(name)
        assert 1 == code, "Should not pass when multicast addresses are out of range"


# 4) Verify that only a one of two valid ports (4789 or 8472) can be provisioned on vxLan provider network
# IANA port 4789
# Cisco port 8472
@mark.parametrize(('the_port', 'r_min', 'r_max'), [
    (8473, pow(2, 24) - 100, pow(2, 24) - 1),  # fail expected
    (4788, pow(2, 24) - 100, pow(2, 24) - 1)  # fail expected
])
def test_vxlan_valid_port(the_port, r_min, r_max, get_provider_):

    provider, name = get_provider_

    code, err_info = network_helper.create_vxlan_providernet_range(provider[0], name, port=the_port,
                                                                   range_min=r_min, range_max=r_max)

    expected_msg = "Invalid input for port. Reason: '{}' is not in [4789, 8472].".format(the_port)
    if code > 0:
        LOG.info("Expect fail when port is not 4789 or 8472")
        assert err_info == expected_msg
    else:
        network_helper.delete_vxlan_providernet_range(name)
        assert 1 == code, "Should not pass when port is not valid"


# 5) Verify that vxLan provider network TTL is configurable in range of 1-255
@mark.parametrize(('the_ttl', 'r_min', 'r_max'), [
    (0, pow(2, 24) - 100, pow(2, 24) - 1),  # fail expected
    (256, pow(2, 24) - 100, pow(2, 24) - 1),  # fail expected
])
def test_vxlan_valid_ttl(the_ttl, r_min, r_max, get_provider_):

    provider, name = get_provider_

    code, err_info = network_helper.create_vxlan_providernet_range(provider[0], name, ttl=the_ttl, range_min=r_min,
                                                                   range_max=r_max)

    expected_msg = "VXLAN time-to-live attributes missing".format(r_min, r_max)
    expected_msg2 = "Invalid input for ttl. Reason: '{}' is too large - must be no larger than '255'.".format(the_ttl)
    if code > 0:
        LOG.info("Expect fail when TTL is not in range (1, 255)")
        assert err_info == expected_msg or err_info == expected_msg2
    else:
        network_helper.delete_vxlan_providernet_range(name)
        assert 1 == code, "Should not pass when TTL is our of range 1 to 255"


#
#
# 6) vxLan provider network fields must not be used with vlan (e.g., group, port, TTL)
# not necessary because create vlan don't need group, port, ttl
# e.g.  neutron providernet-range-create group0-data0 --name group0-data0-r1-1 --shared --range 111-116


# 7) two ranges on the same provider network cannot have overlapping segmentation ranges
# the same range create twice
# assume this range has not been created before
@mark.parametrize(('r_min', 'r_max'), [
    (pow(2, 24)-100, pow(2, 24)-1),  # fail expected
])
def test_vxlan_overlapping_segmentation(r_min, r_max, get_provider_):

    provider, name = get_provider_

    # first time create
    code, err_info = network_helper.create_vxlan_providernet_range(provider[0], name, range_min=r_min, range_max=r_max)
    if code > 0:
        skip("this range of provider should not be created before, delete it and try again")

    code, err_info = network_helper.create_vxlan_providernet_range(provider[0], name, range_min=r_min, range_max=r_max)
    expected_msg = "segmentation id range overlaps with"
    if code > 0:
        LOG.info("Expect fail when two ranges on the same provider network have overlapping segmentation ranges")
        assert expected_msg in err_info
    else:
        assert 1 == code, "Should not pass when the two ranges on the same provider nt have overlapping seg ranges"

    network_helper.delete_vxlan_providernet_range(name)


# 8) two ranges on different provider networks cannot have overlapping segmentation ranges if associated to the same
# data interface
@mark.parametrize(('range0', 'range1'), [
    ('100-110', '100-110'),   # failed
])
def test_vxlan_same_ranges_on_different_provider(lock_unlock, range0, range1, fail_ok=True):

    # neutron providernet-create group0-data11aa --type=vxlan
    # system host-if-modify

    # create two provider networks
    providers = ['data_pro_1', 'data_pro_2']

    LOG.tc_step("Create two provider networks {} and {}".format(providers[0], providers[1]))
    for provider in providers:
        args = provider + ' --type=vxlan'
        code, output = cli.neutron('providernet-create', args, ssh_client=None, auth_info=Tenant.ADMIN,
                                   fail_ok=fail_ok, rtn_list=True)

        if code > 0:
            LOG.info("create provider net failed")
            assert True

    # find a interface
    # compute = random.choice(host_helper.get_nova_hosts())
    compute = lock_unlock
    LOG.tc_step("find the working compute {}".format(compute))

    table_ = system_helper.get_interfaces(compute, con_ssh=None)
    network_type = 'data'
    list_names = table_parser.get_values(table_, 'name', **{'network type': network_type})

    if not list_names:
        skip("can not find free data interface ")

    interface = random.choice(list_names)
    LOG.tc_step("Find the working data interface {}".format(interface))

    # create two range on different providers
    LOG.tc_step("Create the first range")
    args = providers[0] + ' --name ' + providers[0] + '_shared --shared --range ' + range0
    args += ' --group 239.0.0.1 --port 8472 --ttl 1'
    code, output = cli.neutron('providernet-range-create', args, ssh_client=None, auth_info=Tenant.ADMIN,
                               fail_ok=fail_ok, rtn_list=True)
    if code > 0:
        LOG.info("create provider network range  failed")
        assert True

    LOG.tc_step("Create the second range")
    args = providers[1] + ' --name ' + providers[1] + '_shared --shared --range ' + range1
    args += ' --group 239.0.0.1 --port 8472 --ttl 1'
    code, output = cli.neutron('providernet-range-create', args, ssh_client=None, auth_info=Tenant.ADMIN,
                               fail_ok=fail_ok, rtn_list=True)

    if code > 0:
        LOG.info("create provider network range  failed")
        assert True

    # system host-if-modify compute-1 data0 --providernetworks=data_pro_2,data_pro_1
    LOG.tc_step("try to associate the provider networks with the same data interface")
    args = '-nt data -p "{},{}" {} {}'.format(providers[0], providers[1], compute, interface)
    code, err_info = cli.system('host-if-modify', args, ssh_client=None, auth_info=Tenant.ADMIN, fail_ok=fail_ok,
                                rtn_list=True, timeout=SysInvTimeout.RETENTION_PERIOD_MDOIFY)

    expected_msg = "overlaps with range"
    if code > 0:
        LOG.info("Expected fail when two range overlap and try to associate to same data if")
        assert expected_msg in err_info
    else:
        assert 1 == code, "Should not pass when two range overlap and try to associate to same data if"

    LOG.tc_step("Clean up: remove the providers just created and unlock the compute")
    for provider in providers:
        cli.neutron('providernet-delete', provider, ssh_client=None, auth_info=Tenant.ADMIN)


# 9) MTU value of a provider network must be less than that of its associated data interface.  For vxLan, the data
#    interface MTU must be large enough to accommodate the largest possible tenant packet *and* the VXLAN overhead
#    (see overview document)
@mark.parametrize('the_mtu', [1500, 1400])
def test_vxlan_mtu_value(lock_unlock, the_mtu):
    # create provider network with mut=1500
    # lock the compute
    # add interface associate with the provider network with:
    #  neutron providernet-create group0-data11aa --type=vxlan
    #  system host-if-add compute-1 data11aa ae group0-data11aa  data1 -nt data -m 1600 --ipv4-mode=pool --ipv4-pool=management

    provider_ = 'data_pro_1'
    LOG.tc_step("Create provider networks {}".format(provider_))
    args = provider_ + ' --type=vxlan'
    code, output = cli.neutron('providernet-create', args, ssh_client=None, auth_info=Tenant.ADMIN,
                               fail_ok=True, rtn_list=True)

    if code > 0 and "already exists" not in output:
        skip("Create provider network failed")

    compute = lock_unlock

    args = '{} {}'.format(compute, "-a")
    table_ = table_parser.table(cli.system('host-if-list', args, ssh_client=None, auth_info=Tenant.ADMIN))
    list_interfaces = table_parser.get_values(table_, 'name', **{'type': 'ethernet', 'network type': 'None'})
    if not list_interfaces:
        skip("Can not find data interface ")
    interface = random.choice(list_interfaces)
    LOG.tc_step("Find a free port {}".format(interface))

    LOG.tc_step("try to create a interface with MTU less then the one from provider MTU=1500")
    new_interface_ = 'test0if'
    args = compute + ' ' + new_interface_ + ' ae ' + provider_ + ' ' + interface + ' -nt data -m {}'.format(the_mtu)
    code, err_info = cli.system('host-if-add', args, ssh_client=None, auth_info=Tenant.ADMIN, fail_ok=True,
                                rtn_list=True)

    expected_msg = "requires an interface MTU value of at least"
    if code > 0:
        LOG.info("Expect fail: MTU value of a provider network must be less than that of its associated data interface")
        assert expected_msg in err_info
    else:
        args = '{} {}'.format(compute, new_interface_)
        cli.system('host-if-delete', args, auth_info=Tenant.ADMIN)
        assert 1 == code, "Should not pass when the MTU less than the one in provider"

    LOG.tc_step("Clean the provider network")
    cli.neutron('providernet-delete', provider_, auth_info=Tenant.ADMIN)
