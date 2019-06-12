from pytest import fixture, mark

from utils.tis_log import LOG
from keywords import network_helper, vm_helper, system_helper, common
from consts.auth import Tenant
from consts.filepaths import TiSPath, TestServerPath


@fixture(scope='module')
def setup_port_security():

    LOG.fixture_step("Copy userdata files from test server to active controller")
    for i in (1, 2):
        source = "{}/port_security/vm{}-userdata.txt".format(TestServerPath.TEST_FILES, i)
        common.scp_from_test_server_to_active_controller(source_path=source, dest_dir=TiSPath.USERDATA)

    LOG.fixture_step("Enable port security ml2 extension driver on system")
    system_helper.add_ml2_extension_drivers(drivers='port_security')

    LOG.fixture_step("Select neutron networks to test")
    internal_net_id = network_helper.get_internal_net_id()
    nics = [{'net-id': network_helper.get_mgmt_net_id()},
            {'net-id': internal_net_id}]

    return internal_net_id, nics


@mark.parametrize('port_security', (
    'enabled',
    'disabled'
))
def test_neutron_port_security(setup_port_security, port_security):
    """
    Test neutron port security enabled/disabled with IP spoofing

    Args:
        n/a

    Pre-requisites:
        - System should be have ml2 driver capable
    Setups:
        - Enable Extension ml2 driver in system if its not already enabled
        - Enable Port Security in the network if its not already enabled
    Test Steps:
        - Set port_security on existing neutron networks
        - Boot 2 vms to test where userdata sets a static ip that is different than nova show
        - Verify IP Spoofing fails when port security is enabled, and vise versa
        - Delete spoofed vms
        - Boot another 2 vms without userdata
        - Verify ping between VMs work when without ip spoofing attach
        - Change vm2 mac address and verify IP spoofing fails only when port security is enabled
        - Revert vm2 mac address and verify ping between vms work again
    Teardown:
        - Delete created vms, volumes, etc

    """
    internal_net_id, nics = setup_port_security

    port_security_enabled = True if port_security == 'enabled' else False
    LOG.tc_step("Ensure port security is {} on neutron networks".format(port_security))
    internal_net_port_security = eval(network_helper.get_network_values(internal_net_id, 'port_security_enabled')[0])
    if internal_net_port_security is not port_security_enabled:
        LOG.info('Set port security to {} on existing neutron networks'.format(port_security))
        networks = network_helper.get_networks(auth_info=Tenant.get('admin'))
        for net in networks:
            network_helper.set_network(net_id=net, enable_port_security=port_security_enabled)

    # Test IP protection
    LOG.tc_step("Launch two VMs with port security {} with mismatch IP in userdata than neutron port".
                format(port_security))
    vms = []
    for i in (1, 2):
        user_data = '{}/vm{}-userdata.txt'.format(TiSPath.USERDATA, i)
        vm_name = 'vm{}_mismatch_ip_ps_{}'.format(i, port_security)
        vm = vm_helper.boot_vm(name=vm_name, nics=nics, cleanup='function', user_data=user_data)[1]
        vm_helper.wait_for_vm_pingable_from_natbox(vm)
        vms.append(vm)
    vm1, vm2 = vms
    vm_helper.ping_vms_from_vm(to_vms=vm2, from_vm=vm1, net_types=['mgmt'], retry=10)

    vm2_ip = '10.1.0.2'
    expt_res = 'fails' if port_security_enabled else 'succeeds'
    LOG.tc_step("With port security {}, verify ping over internal net {} with mismatch IPs".
                format(port_security, expt_res))
    packet_loss_rate = _ping_server(vm1, ip_addr=vm2_ip, fail_ok=port_security_enabled)
    if port_security_enabled:
        assert packet_loss_rate == 100, "IP spoofing succeeded when port security is enabled"

    LOG.info("Delete VMs with mismatch IPs")
    vm_helper.delete_vms(vms)

    # Test MAC protection
    LOG.tc_step("Launch two VMs without IP Spoofing and check ping between vms works")
    vms = []
    for i in (1, 2):
        vm = vm_helper.boot_vm(name='vm{}_ps_{}'.format(i, port_security), nics=nics, cleanup='function')[1]
        vm_helper.wait_for_vm_pingable_from_natbox(vm)
        vms.append(vm)
    vm1, vm2 = vms
    vm_helper.ping_vms_from_vm(vm2, from_vm=vm1, net_types=['mgmt', 'internal'])

    LOG.tc_step("With port security {}, change VM mac address and ensure ping over internal net {}".
                format(port_security, expt_res))
    origin_mac_addr = network_helper.get_ports(server=vm2, network=internal_net_id, field='MAC Address')[0]
    vm2_ip = network_helper.get_internal_ips_for_vms(vm2)[0]
    new_mac_addr = _change_mac_address(vm2, origin_mac_addr)
    packet_loss_rate = _ping_server(vm1, ip_addr=vm2_ip, fail_ok=port_security_enabled)
    if port_security_enabled:
        assert packet_loss_rate == 100, "IP spoofing succeeded when port security is enabled"

    LOG.tc_step("With port security {}, revert VM mac address and ensure ping over internal net succeeds".
                format(port_security))
    _change_mac_address(vm2, new_mac_addr, origin_mac_addr)
    _ping_server(vm1, ip_addr=vm2_ip, fail_ok=False)


def _change_mac_address(vm_id, prev_mac_addr, new_mac_addr=None):
    """
    ip link set <dev> up, and dhclient <dev> to bring up the interface of last nic for given VM
    Args:
        vm_id (str):
    """
    if not new_mac_addr:
        new_mac_addr = prev_mac_addr[:-1] + ('2' if prev_mac_addr.endswith('1') else '1')

    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        eth_name = network_helper.get_eth_for_mac(mac_addr=prev_mac_addr, ssh_client=vm_ssh)
        vm_ssh.exec_cmd('ip addr')
        vm_ssh.exec_sudo_cmd('ifconfig {} down'.format(eth_name), fail_ok=False)
        vm_ssh.exec_sudo_cmd('sudo ifconfig {} hw ether {}'.format(eth_name, new_mac_addr), fail_ok=False)
        vm_ssh.exec_sudo_cmd('ifconfig {} up'.format(eth_name), fail_ok=False)
        vm_ssh.exec_cmd('ip addr | grep --color=never -B 1 -A 1 {}'.format(new_mac_addr), fail_ok=False)

    return new_mac_addr


def _ping_server(vm_id, ip_addr, fail_ok):
    with vm_helper.ssh_to_vm_from_natbox(vm_id=vm_id) as vm_ssh:
        packet_loss_rate = network_helper.ping_server(ip_addr, ssh_client=vm_ssh, fail_ok=fail_ok, retry=10)[0]

    return packet_loss_rate
