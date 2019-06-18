import time
import re

from pytest import fixture, mark, param

from utils.tis_log import LOG
from keywords import vm_helper, network_helper, glance_helper
from consts.stx import PING_LOSS_RATE


@fixture(scope='module', autouse=True)
def update_net_quota(request):
    network_quota = vm_helper.get_quotas('networks')[0]
    vm_helper.set_quotas(networks=network_quota + 2)

    def _revert_quota():
        vm_helper.set_quotas(networks=network_quota)
    request.addfinalizer(_revert_quota)


def _bring_up_interface(vm_id):
    """
    Set up the network scripts to auto assign the interface Ipv6 addr
    Args:
        vm_id (str): VM to configure the vlan interface

    """
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    cmds_to_exe = ["ls /etc/sysconfig/network-scripts/",
                   "sed -i -- 's/IPV6INIT=no/IPV6INIT=yes/g' /etc/sysconfig/network-scripts/ifcfg-eth1",
                   "sed -i '1 i\DHCPV6C=yes' /etc/sysconfig/network-scripts/ifcfg-eth1",
                   "sed -i '1 a NETWORKING_IPV6=yes' /etc/sysconfig/network", "systemctl restart network"]
    time.sleep(10)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        for cmd in cmds_to_exe:
            vm_ssh.exec_sudo_cmd('{}'.format(cmd))

        vm_ssh.exec_sudo_cmd('ip addr')
    return 0


def _get_ipv6_for_eth(ssh_client, eth_name):
    """
    Get the IP addr for given eth on the ssh client provided
    Args:
        ssh_client (SSHClient): usually a vm_ssh
        eth_name (str): such as "eth1, eth1.1"

    Returns (str): The first matching ipv6 addr for given eth.

    """
    cmd = "/sbin/ifconfig "
    cmd += '{}'.format(eth_name) + " | grep -i \"inet6\" | grep \"fd00\" | awk {'print $2'}"

    if eth_name in ssh_client.exec_cmd('ip addr'.format(eth_name))[1]:
        output = ssh_client.exec_cmd('{}'.format(cmd), fail_ok=False)[1]
        return output
    else:
        LOG.warning("Cannot find ipv6 addr for eth1")
        return ''


__PING_LOSS_MATCH = re.compile(PING_LOSS_RATE)


def _ping6_vms(ssh_client, ipv6_addr, num_pings=5, timeout=60, fail_ok=False,):
    """
    ping b/w 2 vms
    Args:
        ssh_client (SSHClient): usually a vm_ssh
        ipv6_addr: address to ping
        num_pings: ping count
        timeout: time out to use
        fail_ok:

    Returns (code):

    """
    cmd = 'ping6 -c {} {}'.format(num_pings, ipv6_addr)

    code, output = ssh_client.exec_cmd(cmd=cmd, expect_timeout=timeout, fail_ok=fail_ok)
    if code != 0:
        return 1
    else:
        packet_loss_rate = __PING_LOSS_MATCH.findall(output)[-1]
        packet_loss_rate = int(packet_loss_rate)
        if packet_loss_rate < 100:
            if packet_loss_rate > 0:
                LOG.warning("Some packets dropped when ping from {} ssh session to {}. Packet loss rate: {}%".
                            format(ssh_client.host, ipv6_addr, packet_loss_rate))
                return 1
            else:
                LOG.info("All packets received by {}".format(ipv6_addr))
                return 0


@mark.parametrize('vif_model', [
    param('avp', marks=mark.p1),
    param('virtio', marks=mark.p2),
    param('e1000', marks=mark.p3)
])
def test_ipv6_subnet(vif_model, check_avs_pattern):
    """
    Ipv6 Subnet feature test cases

    Test Steps:
        - Create networks
        - Create Ipv6 enabled subnet
        - Boot the first vm with the ipv6 subnet
        - Boot the second vm with ipv6 subnet
        - Configure interfaces to get ipv6 addr
        - Verify connectivity ipv6 interfaces
        - Ping default router

    Test Teardown:
        - Delete vms, subnets, and networks created

    """
    network_names = ['network11']
    net_ids = []
    sub_nets = ["fd00:0:0:21::/64"]
    gateway_ipv6 = "fd00:0:0:21::1"
    subnet_ids = []

    dns_server = "2001:4860:4860::8888"

    LOG.tc_step("Create Networks to setup IPV6 subnet")
    for net in network_names:
        net_ids.append(network_helper.create_network(name=net, cleanup='function')[1])

    LOG.tc_step("Create IPV6 Subnet on the Network Created")
    for sub, network in zip(sub_nets, net_ids):
        subnet_ids.append(network_helper.create_subnet(network=network, ip_version=6, dns_servers=dns_server,
                                                       subnet_range=sub, gateway='none', cleanup='function')[1])

    LOG.tc_step("Boot a VM with mgmt net and Network with IPV6 subnet")
    mgmt_net_id = network_helper.get_mgmt_net_id()
    nics = [{'net-id': mgmt_net_id},
            {'net-id': net_ids[0], 'vif-model': vif_model}]

    image = None
    if vif_model == 'e1000':
        image = glance_helper.create_image(name=vif_model, hw_vif_model=vif_model, cleanup='function')[1]

    LOG.tc_step("Boot a vm with created nets")
    vm_id = vm_helper.boot_vm(name='vm-with-ipv6-nic', nics=nics, image_id=image, cleanup='function')[1]
    LOG.tc_step("Setup interface script inside guest and restart network")
    _bring_up_interface(vm_id)

    LOG.tc_step("Boot a second vm with created nets")
    vm_id2 = vm_helper.boot_vm(name='vm2-with-ipv6-nic', nics=nics, cleanup='function')[1]
    LOG.tc_step("Setup interface script inside guest and restart network")
    _bring_up_interface(vm_id2)

    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        ip_addr = _get_ipv6_for_eth(eth_name='eth1', ssh_client=vm_ssh)

        if ip_addr is '':
            LOG.info('Ip addr is not assigned')
            assert ip_addr != '', "Failed to assign ip"
        else:
            LOG.info("Got Ipv6 address:{}".format(ip_addr))

    with vm_helper.ssh_to_vm_from_natbox(vm_id2) as vm_ssh:
        LOG.tc_step("ping b/w vms on the ipv6 net")
        ping = _ping6_vms(ssh_client=vm_ssh, ipv6_addr=ip_addr)
        assert ping == 0, "Ping between VMs failed"
        LOG.tc_step("ping Default Gateway from vms on the ipv6 net")
        ping = _ping6_vms(ssh_client=vm_ssh, ipv6_addr=gateway_ipv6)
        assert ping == 0, "Ping to default router failed"
