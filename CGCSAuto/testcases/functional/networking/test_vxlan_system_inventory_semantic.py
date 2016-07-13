import random
from pytest import fixture, mark, skip
from utils import cli
from utils import table_parser
from utils.tis_log import LOG
from consts.auth import Tenant
from keywords import host_helper, system_helper
from testfixtures.recover_hosts import HostsToRecover


@fixture(scope='module')
def get_interface_(request):

    provider_, new_interface_ = 'neutron_provider_net_vxlan', 'test0if'

    compute_ = random.choice(host_helper.get_nova_hosts())

    # (a) create providernet
    LOG.info("Create provider networks {}".format(provider_))
    args = provider_ + ' --type=vxlan'
    code, output = cli.neutron('providernet-create', args, auth_info=Tenant.ADMIN, fail_ok=True, rtn_list=True)

    if code > 0 and "already exists" not in output:
        skip("Create provider network failed")

    # now lock the computer
    host_helper.lock_host(compute_)
    HostsToRecover.add(compute_, scope='module')

    # (b)create interface
    table_ = system_helper.get_interfaces(compute_, con_ssh=None)
    list_interfaces = table_parser.get_values(table_, 'name', **{'type': 'ethernet', 'network type': 'None'})
    if not list_interfaces:
        skip("Can not find data interface ")
    interface = random.choice(list_interfaces)

    LOG.info("Create interface associated with the provider-net")
    the_mtu = 1600
    args = compute_ + ' ' + new_interface_ + ' ae ' + provider_ + ' ' + interface + ' -nt data -m {}'.format(the_mtu)
    code, err_info = cli.system('host-if-add', args, fail_ok=True, rtn_list=True)
    if code > 0 and "Name must be unique" not in err_info:
        skip("can not create interface {}".format(err_info))

    def fin():
        # clean up
        LOG.info("Clean the interface and provider network")
        cli.system('host-if-delete', '{} {}'.format(compute_, new_interface_))
        cli.neutron('providernet-delete', provider_, auth_info=Tenant.ADMIN)
    request.addfinalizer(fin)

    return compute_, provider_, new_interface_


@fixture(scope='module')
def set_interface_ip_(get_interface_):
    compute, provider, new_interface_ = get_interface_

    LOG.info("change the ip mode to static ")
    args_mode = '-nt data -p {} {} {} --ipv4-mode=static'.format(provider, compute, new_interface_)
    code, err_info = cli.system('host-if-modify', args_mode, fail_ok=True, rtn_list=True)

    if code > 0:
        LOG.info("modify interface failed")

    ip = "192.168.3.3"
    LOG.info("add ip: {}/24".format(ip))
    args_ip = '{} {} {} 24'.format(compute, new_interface_, ip)
    code, err_info = cli.system('host-addr-add', args_ip, fail_ok=True, rtn_list=True)
    if code > 0 and "already exists" not in err_info:
        skip("can not create ip address: |{}|".format(err_info))

    return compute, provider, new_interface_


def test_1_if_no_addr(get_interface_):

    """
    1) vxLan provider network requires an IP address on interface before assignment
        (a) create providernet with type=vxlan
        (b) create interface associate with providernet
        (c) unlock the compute will fail:

    Args:
        get_interface_:

    Returns:

    """

    nova_host, provider, new_interface_ = get_interface_

    code, err_info = host_helper.unlock_host(nova_host, fail_ok=True)
    if code > 0:
        LOG.info("Expected error: {}".format(err_info))
        assert "requires an IP address" in err_info
    else:
        assert 1 == code, "There is no ip address add in interface yet, so the host can not be unlock"


def test_3_provider_net_requires_ip(get_interface_):
    """
    TC3) data interface address mode must be set to “static” before allowing any IP address

    Args:
        get_interface_:

    Returns:

    """

    compute, provider, new_interface_ = get_interface_

    LOG.tc_step("TC3: create ip addr when the mode is not static")
    args_ip = '{} {} 111.11.11.11 24'.format(compute, new_interface_)
    code, err_info = cli.system('host-addr-add', args_ip, fail_ok=True, rtn_list=True)
    if code > 0:
        LOG.info("Expect fail: set the ip mode to static before assign a address |{}|".format(err_info))
        assert "interface address mode must be 'static'" in err_info
    else:
        assert 1 == code, "Should not be here."


def test_4_provider_net_requires_ip(get_interface_):
    """
    TC4: setting data interface address mode to anything but “static” should not be allowed if addresses
    still exist on interface
    however, set to Disabled is ok

    Args:
        get_interface_:

    Returns:

    """
    compute, provider, new_interface_ = get_interface_

    args_mode = '-nt data -p {} {} {} --ipv4-mode=static'.format(provider, compute, new_interface_)
    code, err_info = cli.system('host-if-modify', args_mode, fail_ok=True, rtn_list=True)
    if code > 0:
        LOG.info("modify interface failed")

    # now create the ip again after mode set to static
    args = '{} {} 111.11.11.11 24'.format(compute, new_interface_)
    code, err_info = cli.system('host-addr-add', args, fail_ok=True, rtn_list=True)
    if not code:
        LOG.info("Success set the ip")

    LOG.tc_step("TC4: set the mode to 'pool' when the ip still exist")
    args = '-nt data -p {} {} {} --ipv4-mode="pool" --ipv4-pool=management'.format(provider, compute, new_interface_)
    code, err_info = cli.system('host-if-modify', args, fail_ok=True, rtn_list=True)
    if code > 0:
        LOG.info("modify interface failed")
        assert 'addresses still exist on interfac' in err_info
    else:
        assert 1 == code, 'should not be here'

    LOG.tc_step("TC4: clean the ip just created")
    table_ = table_parser.table(cli.system('host-addr-list', compute))
    cli.system('host-addr-delete', table_parser.get_values(table_, 'uuid', **{'ifname': new_interface_}))


def test_5_provider_net_requires_ip(get_interface_):
    """
    TC5: IP address must not be zero

    Args:
        get_interface_:

    Returns:

    """

    compute, provider, new_interface_ = get_interface_

    LOG.tc_step("TC5: create ip addr with all zero")
    args_ip = '{} {} 0.0.0.0 24'.format(compute, new_interface_)
    code, err_info = cli.system('host-addr-add', args_ip, fail_ok=True, rtn_list=True)
    if code > 0:
        LOG.info("Expect fail: {}".format(err_info))
        assert 'Address must not be null' == err_info
    else:
        assert 1 == code, 'should not be here'


def test_6_provider_net_requires_ip(get_interface_):
    """
    TC6: IP address network portion must not be zero

    Args:
        get_interface_:

    Returns:

    """

    compute, provider, new_interface_ = get_interface_

    LOG.tc_step("TC6: create ip addr with network partion zero")
    args_ip = '{} {} 0.0.0.33 24'.format(compute, new_interface_)
    code, err_info = cli.system('host-addr-add', args_ip, fail_ok=True, rtn_list=True)
    if code > 0:
        LOG.info("Expect fail: |{}|".format(err_info))
        assert 'Network must not be null' == err_info
    else:
        assert 1 == code, 'should not be here'


# TC7: 7) IP address host portion must not be zero
def test_7_provider_net_requires_ip(get_interface_):
    """
    TC7: 7) IP address host portion must not be zero

    Args:
        get_interface_:

    Returns:

    """

    compute, provider, new_interface_ = get_interface_

    LOG.tc_step("TC7: create ip addr with host partion zero")
    args_ip = '{} {} 192.168.0.0 16'.format(compute, new_interface_)
    code, err_info = cli.system('host-addr-add', args_ip, fail_ok=True, rtn_list=True)
    if code > 0:
        LOG.info("Expect fail: |{}|".format(err_info))
        assert 'Host bits must not be zero' == err_info
    else:
        assert 1 == code, 'should not be here'


def test_8_provider_net_requires_ip(get_interface_):
    """
    TC8: 8) IP address should be a unicast address (ie., not multicast and not broadcast)

    Args:
        get_interface_:

    Returns:

    """
    compute, provider, new_interface_ = get_interface_

    LOG.tc_step("TC8: try to set multicast ip addr: 224.0.0.0 to 239.225.225.225")
    args_ip = '{} {} 225.168.2.2 16'.format(compute, new_interface_)
    code, err_info = cli.system('host-addr-add', args_ip, fail_ok=True, rtn_list=True)
    if code > 0:
        LOG.info("Expect fail: |{}|".format(err_info))
        assert 'Address must be a unicast address' == err_info
    else:
        assert 1 == code, 'should not be here'

    LOG.tc_step("TC8: try to set broadcast ip addr")
    args_ip = '{} {} 255.255.255.255 24'.format(compute, new_interface_)
    code, err_info = cli.system('host-addr-add', args_ip, fail_ok=True, rtn_list=True)
    if code > 0:
        LOG.info("Expect fail: |{}|".format(err_info))
        assert 'Address cannot be the network broadcast address' == err_info
    else:
        assert 1 == code, 'should not be here'


def test_10_provider_net_requires_ip(get_interface_):
    """
    TC10 ) IP address should be unique across all compute nodes

    Args:
        get_interface_:

    Returns:

    """

    compute, provider, new_interface_ = get_interface_

    args_mode = '-nt data -p {} {} {} --ipv4-mode=static'.format(provider, compute, new_interface_)
    code, err_info = cli.system('host-if-modify', args_mode, fail_ok=True, rtn_list=True)
    if code > 0:
        LOG.info("modify interface failed")

    # randomly get a compute
    cmp = random.choice(host_helper.get_nova_hosts())

    table_ = table_parser.table(cli.system('host-addr-list', cmp))
    ip = random.choice(table_parser.get_values(table_, 'address'))
    prefix = table_parser.get_values(table_, 'prefix', **{'address': ip})

    LOG.tc_step("TC10: ip addr {}/{} used in {}".format(ip, prefix[0], cmp))
    args_ip = '{} {} {} {}'.format(compute, new_interface_, ip, prefix[0])
    code, err_info = cli.system('host-addr-add', args_ip, fail_ok=True, rtn_list=True)
    if code > 0:
        LOG.info("Expect fail: {}".format(err_info))
        assert 'already exists on this interface' in err_info
    else:
        assert 1 == code, 'should not be here'


@mark.parametrize(('prefix', 'status'), [
    (33, False),    # fail expected
    (345, False),    # fail expected
    (23, True),    # ok
    (24, True),    # ok
    (25, True),    # ok
])
def test_15_route_prefix_validation(set_interface_ip_, prefix, status):
    """
    15) IP route network prefix must be valid for family (i.e., 1-32 for IPv4, 1-128 for IP6)

    Args:
        set_interface_ip_:
        prefix:
        status:

    Returns:

    """
    compute, provider, new_interface_ = set_interface_ip_

    gateway = "192.168.3.0"

    LOG.tc_step("TC15: add route with prefix {}".format(prefix))

    nt = '192.168.102.0'
    metric = 16

    args = '{} {} {} {} {} {}'.format(compute, new_interface_, nt, prefix, gateway, metric)
    code, err_info = cli.system('host-route-add', args, fail_ok=True, rtn_list=True)
    if code > 0:
        if not status:
            LOG.info("Expect fail: {}".format(err_info))
            assert 'Invalid IP address and prefix' in err_info
        else:
            LOG.info("Error: {}".format(err_info))
            assert code, 'Should be failed'
    else:
        # delete router for next one
        # LOG.info("*******: {}".format(err_info))
        # table_ = table_parser.table(err_info)
        # uuid = table_parser.get_values(table_, 'Value', **{'Property': 'uuid'})
        # cli.system('host-route-delete', uuid)

        if not status:
            LOG.info("Error: {}".format(err_info))
            assert 0 == code, 'should not be here'
        else:
            LOG.info("Pass ok: {}".format(err_info))


def test_16_route_prefix_validation(set_interface_ip_):
    """
    16) IP route gateway address must not be null (e.g., ::, 0.0.0.0)

    Args:
        set_interface_ip_:

    Returns:

    """
    compute, provider, new_interface_ = set_interface_ip_

    gateway = "0.0.0.0"
    prefix = 24

    LOG.tc_step("TC16: add route with bad gateway {}".format(prefix))

    nt = '192.168.102.0'
    metric = 16

    args = '{} {} {} {} {} {}'.format(compute, new_interface_, nt, prefix, gateway, metric)
    code, err_info = cli.system('host-route-add', args, fail_ok=True, rtn_list=True)
    if code > 0:
        LOG.info("Expected error: {}".format(err_info))
        assert 'Gateway address must not be null' == err_info
    else:
        assert 1 == code, 'should not be here'


def test_17_route_network_ip_validation(set_interface_ip_):
    """
    17) IP route network address must be valid

    Args:
        set_interface_ip_:

    Returns:

    """
    compute, provider, new_interface_ = set_interface_ip_

    gateway = "192.168.3.0"
    prefix = 24
    nt = '192.168.102.12'  # invalid one
    metric = 16

    LOG.tc_step("TC17: add route with bad network address {}".format(nt))

    args = '{} {} {} {} {} {}'.format(compute, new_interface_, nt, prefix, gateway, metric)
    code, err_info = cli.system('host-route-add', args, fail_ok=True, rtn_list=True)
    if code > 0:
        LOG.info("Expected error: {}".format(err_info))
        assert 'Invalid IP network' in err_info
    else:
        assert 1 == code, 'should not be here'


def test_18_route_gateway_ip_validation(set_interface_ip_):
    """
    18) IP route gateway address must be valid

    Args:
        set_interface_ip_:

    Returns:

    """
    compute, provider, new_interface_ = set_interface_ip_

    gateway = "192.168.33.1"  # invalid one
    prefix = 24
    nt = '192.168.102.0'
    metric = 16

    LOG.tc_step("TC18: add route with bad gateway address {}".format(gateway))

    args = '{} {} {} {} {} {}'.format(compute, new_interface_, nt, prefix, gateway, metric)
    code, err_info = cli.system('host-route-add', args, fail_ok=True, rtn_list=True)
    err_msg = "Route gateway {} is not reachable".format(gateway)
    if code > 0:
        LOG.info("Expected error: {}".format(err_info))
        assert err_msg in err_info
    else:
        assert 1 == code, 'should not be here'


@mark.parametrize(('gateway', 'nt', 'prefix'), [
    ('192.168.3.0', 'FE80::0202:B3FF:FE1E:0000', 24),    # fail expected
    ('FE80:0000:0000:0000:0202:B3FF:FE1E:0000', '192.168.102.0', 24),    # fail expected
    ('192.168.3.0', 'FE80::0202:B3FF:FE1E:0000', 64),    # fail expected
    ('FE80:0000:0000:0000:0202:B3FF:FE1E:0000', '192.168.102.0', 64),    # fail expected
])
def test_19_route_network_gateway_ip_in_same_families(set_interface_ip_, gateway, nt, prefix):
    """
    19) IP route network and gateway families must be the same (i.e., both IPv4 or both IPv6)

    Args:
        set_interface_ip_:
        gateway:
        nt:
        prefix:

    Returns:

    """

    compute, provider, new_interface_ = set_interface_ip_

    metric = 16

    LOG.tc_step("TC19: add route with bad gateway address {}".format(gateway))

    args = '{} {} {} {} {} {}'.format(compute, new_interface_, nt, prefix, gateway, metric)
    code, err_info = cli.system('host-route-add', args, fail_ok=True, rtn_list=True)
    if code > 0:
        LOG.info("Expected error: {}".format(err_info))
        assert 'Network and gateway IP versions must match' or 'Invalid IP network' in err_info
    else:
        assert 1 == code, 'should not be here'


@mark.parametrize('gateway', [
    ("192.168.3.11"),   #  gateway should be 172.16.102.1
    ("192.168.3.3"),    #  local address  TC26
    ("192.168.3.0"),    #  network addr  for test case 21
    ("192.168.3.255"),  #  brodcast addr
    ("192.168.2.1"),    #  other network gateway addr
])
def test_20(set_interface_ip_, gateway):
    """
    20) IP route gateway address must not be part of the destination subnet
    21) IP route gateway must be a unicast address
    25) IP route gateway address must be a member of a subnet that corresponds to a local IP address on the same interface
    26) IP route gateway address must not be a currently configured local address

    Args:
        set_interface_ip_:
        gateway:

    Returns:

    """
    compute, provider, new_interface_ = set_interface_ip_

    prefix = 24
    nt = '192.168.3.0'
    metric = 16

    LOG.tc_step("TC20: add route with bad gateway address {}".format(gateway))

    args = '{} {} {} {} {} {}'.format(compute, new_interface_, nt, prefix, gateway, metric)
    code, err_info = cli.system('host-route-add', args, fail_ok=True, rtn_list=True)
    err_msg_tc20 = "Gateway address must not be within destination subnet"
    err_msg_tc21 = "Network and gateway IP addresses must be different"
    err_msg_tc25 = "not reachable by any address"
    if code > 0:
        LOG.info("Expected error: {}".format(err_info))
        assert err_msg_tc20 or err_msg_tc21 or err_msg_tc25 in err_info
    else:
        assert 1 == code, 'should not be here'


@mark.parametrize('nt', [
    ('192.168.3.1'),    # try gateway addr
    ('192.168.3.2'),    # try DHCP addr
    ('192.168.3.255'),  # try broadcase addr
])
def test_22_network_addr_must_be_unicast_addr(set_interface_ip_, nt):
    """
    22) IP route network must be a unicast address

    Args:
        set_interface_ip_:
        nt:

    Returns:

    """
    compute, provider, new_interface_ = set_interface_ip_

    prefix = 24
    gateway = '192.168.3.1'
    metric = 16

    LOG.tc_step("TC22: add route with bad network address {}".format(nt))

    args = '{} {} {} {} {} {}'.format(compute, new_interface_, nt, prefix, gateway, metric)
    code, err_info = cli.system('host-route-add', args, fail_ok=True, rtn_list=True)
    err_msg = "Invalid IP network"
    if code > 0:
        LOG.info("Expected error: {}".format(err_info))
        assert err_msg in err_info
    else:
        assert 1 == code, 'should not be here'


def test_27_route_unique(set_interface_ip_):
    """
    27) IP route must be unique (network + prefix + gateway)

    Args:
        set_interface_ip_:

    Returns:

    """
    compute, provider, new_interface_ = set_interface_ip_

    prefix = 24
    gateway = '192.168.3.1'
    metric = 16

    nt = '200.10.0.0'
    LOG.tc_step("TC27: add first route address {}".format(nt))
    args = '{} {} {} {} {} {}'.format(compute, new_interface_, nt, prefix, gateway, metric)
    code, err_info = cli.system('host-route-add', args, fail_ok=True, rtn_list=True)
    if code > 0:
        skip('Can not add route')

    LOG.tc_step("TC27: add second route with same ip will fail")
    code, err_info = cli.system('host-route-add', args, fail_ok=True, rtn_list=True)
    err_msg = "already exists"
    if code > 0:
        LOG.info("Expected error: {}".format(err_info))
        assert err_msg in err_info
    else:
        assert 1 == code, 'should not be here'
