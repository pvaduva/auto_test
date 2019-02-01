import random

from pytest import fixture

from utils.tis_log import LOG
from keywords import network_helper, nova_helper, vm_helper, system_helper, common
from consts.auth import Tenant


@fixture(scope='module', autouse=True)
def setup_port_security():
    LOG.fixture_step("Ensure neutron port security is enabled")
    system_helper.enable_port_security_param()


def test_neutron_port_security():
    """
    test neutron port security

    Args:
        n/a

    Test Setups:
        System should be have ml2 driver capable
    Test Steps:
        - Enable Extension ml2 driver in system if its not already enabled
        - Enable Port Security in the network if its not already enabled
        - Boot base VM & VM to test
        - Verify IP Spoofing fails when port security is enabled
        - Delete existing base vm & VM to test
        - Disable Port security at network leve
        - Boot base VM & VM to test
        - Verify IP Spoofing works when port security is disabled
    Test Teardown:
        - Delete base vm & vm to test
        - Revert system service parameter if it is added
    """

    LOG.tc_step("Enable port_security for the system and update existing networks")
    port_security = network_helper.get_net_show_values('external-net0', 'port_security_enabled')[0]
    port_security = eval(port_security)
    if not port_security:
        networks = network_helper.get_networks(auth_info=Tenant.get('admin'))
        for net in networks:
            network_helper.set_network(net_id=net, enable_port_security=True)

    LOG.tc_step("Copy userdata file from test server to active controller")
    source = "/home/svc-cgcsauto/userdata/port_security/tenant1-userdata.txt"
    destination = "/home/wrsroot/userdata"
    common.scp_from_test_server_to_active_controller(source_path=source, dest_dir=destination)
    source = "/home/svc-cgcsauto/userdata/port_security/tenant2-userdata.txt"
    common.scp_from_test_server_to_active_controller(source_path=source, dest_dir=destination)

    internal_net_id = network_helper.get_internal_net_id()
    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()

    mgmt_nic = {'net-id': mgmt_net_id}
    internal_nic = {'net-id': internal_net_id}
    tenant_nic = {'net-id': tenant_net_id}
    nics = [mgmt_nic, tenant_nic, internal_nic]

    vm_ids = []

    LOG.tc_step("Boot Base VM")
    user_data1 = '/home/wrsroot/userdata/tenant1-userdata.txt'
    base_vm_id = vm_helper.boot_vm(name='base_vm', nics=nics, cleanup='function', user_data=user_data1)[1]

    vm_ids.append(base_vm_id)

    LOG.tc_step("Perform system service-parameter-list")
    port_security_enabled = network_helper.get_net_info(tenant_net_id, field='port_security_enabled')

    LOG.tc_step("Verify if Port Security Enabled in Network")
    LOG.info("Port security enabled: {}".format(port_security_enabled))
    assert port_security_enabled, "Port Security Not Enabled in Network"

    LOG.tc_step("Boot vm to test port security")
    user_data2 = '/home/wrsroot/userdata/tenant2-userdata.txt'
    vm_under_test = vm_helper.boot_vm(name='if_attach_tenant', nics=nics, cleanup='function', user_data=user_data2)[1]
    vm_ids.append(vm_under_test)

    ip_addr = '10.1.0.2'

    LOG.tc_step("Verify IP Spoofing fails, ping over internal networks should fails ")
    _ping_server(base_vm_id, vm_under_test, ip_addr, True)

    LOG.tc_step("Delete Base VM {} & VM under test {}".format(base_vm_id, vm_under_test))
    vm_helper.delete_vms(vm_ids, delete_volumes=True)

    LOG.tc_step("Disable port_security on existing Networks")
    networks = network_helper.get_networks(auth_info=Tenant.get('admin'))
    for net in networks:
        network_helper.set_network(net_id=net, enable_port_security=False)
    port_security_enabled = network_helper.get_net_info(tenant_net_id, field='port_security_enabled')
    LOG.tc_step("Verify if Port Security Disabled in Network")
    LOG.info("Port security enabled: {}".format(port_security_enabled))
    assert port_security_enabled, "Port Security Still Enabled in Network"

    LOG.tc_step("Boot Base VM & VM under test")
    base_vm_id = vm_helper.boot_vm(name='base_vm', nics=nics, cleanup='function', user_data=user_data1)[1]
    vm_under_test = vm_helper.boot_vm(name='if_attach_tenant', nics=nics, cleanup='function', user_data=user_data2)[1]

    LOG.tc_step("Verify IP Spoofing works, ping over internal networks should work ")
    _ping_server(base_vm_id, vm_under_test, ip_addr, False)

    LOG.tc_step("Generate new mac address")
    new_mac_addr = _gen_mac_addr()
    mac_addr = network_helper.get_ports(server=vm_under_test, network=internal_net_id, rtn_val='MAC Address')[0]
    eth_name = _find_eth_for_mac(vm_under_test, mac_addr)

    LOG.tc_step("Change mac addr to random {}".format(new_mac_addr))
    _change_mac_address(vm_under_test, new_mac_addr, eth_name)

    LOG.tc_step("Verify mac filtering works, ping over internal networks should work even after changing mac address ")
    _ping_server(base_vm_id, vm_under_test, ip_addr, False)

    LOG.tc_step("Revert change mac addr to orig {}".format(mac_addr))
    _change_mac_address(vm_under_test, mac_addr, eth_name)

    LOG.tc_step("Verify IP Spoofing works, ping over internal networks should work ")
    _ping_server(base_vm_id, vm_under_test, ip_addr, False)


def _find_eth_for_mac(vm_id, mac_addr):
    """
    ip link set <dev> up, and dhclient <dev> to bring up the interface of last nic for given VM
    Args:
        vm_id (str):
        mac_addr (str)
    """
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        eth_name = network_helper.get_eth_for_mac(mac_addr=mac_addr, ssh_client=vm_ssh)
        LOG.info("mac addr {}, eth_name {}".format(mac_addr, eth_name))
        assert eth_name, "Interface with mac {} is not listed in 'ip addr' in vm {}".format(mac_addr, vm_id)
    return eth_name


def _change_mac_address(vm_id, mac_addr, eth_name):
    """
    ip link set <dev> up, and dhclient <dev> to bring up the interface of last nic for given VM
    Args:
        vm_id (str):
    """
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        vm_ssh.exec_cmd('ip addr')
        vm_ssh.exec_sudo_cmd('ifconfig {} down'.format(eth_name))
        vm_ssh.exec_sudo_cmd('sudo ifconfig {} hw ether {}'.format(eth_name, mac_addr))
        vm_ssh.exec_sudo_cmd('ifconfig {} up'.format(eth_name))


def _gen_mac_addr():

    myhexdigits = []
    for x in range(6):
        # x will be set to the values 0 to 5
        a = random.randint(0, 255)
        # a will be some 8-bit quantity
        hex = '%02x' % a
        # hex will be 2 hexadecimal digits with a leading 0 if necessary
        # you need 2 hexadecimal digits to represent 8 bits
        myhexdigits.append(hex)
    new_mac_addr = ':'.join(myhexdigits)
    LOG.info("Generated new mac address {}".format(new_mac_addr))

    return new_mac_addr


def _ping_server(base_vm_id, vm_under_test, ip_addr, fail_ok):
    LOG.tc_step("Verify IP Spoofing fails, ping over internal networks should fails ")
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm_id, net_types=['mgmt'], retry=10)
    with vm_helper.ssh_to_vm_from_natbox(vm_id=base_vm_id) as vm_ssh:
        network_helper.ping_server(ip_addr, ssh_client=vm_ssh, fail_ok=fail_ok)