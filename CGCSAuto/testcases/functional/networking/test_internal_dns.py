import time

from pytest import fixture, mark

from consts.stx import EventLogID
from keywords import host_helper, system_helper, network_helper, vm_helper
from utils.tis_log import LOG

DEFAULT_DNS_SERVERS = ['147.11.57.133', '128.224.144.130', '147.11.57.128']
UNRESTORED_DNS_SERVERS = []
NET_NAME = None
HOSTS_AFFECTED = []


def provision_internal_dns(hosts):
    """
    Verify that internal dns provisioning can be enabled using system
    service parameters.

    Args:
        - Nothing

    Setup:
        - Nothing

    Test Steps:
        - Set internal dns service parameters
        - Apply internal dns service parameters
        - Check that all computes report the 'Config out-of-date' alarm
        - Lock/unlock each compute
        - Ensure the 'Config out-of-date' alarms clear

    Returns:
        - Nothing

    """
    LOG.tc_step("Ensure ml2 extension driver for dns is enabled.")
    code = system_helper.add_ml2_extension_drivers(drivers='dns')[0]
    if code == -1:
        return

    # __clear_config_out_of_date_alarms(hosts=hosts)


def deprovision_internal_dns(hosts):
    """
    Verify that internal dns provisioning can be disabled using system
    service parameters.

    Args:
        - Nothing

    Setup:
        - Nothing

    Test Steps:
        - Delete internal dns service parameters
        - Apply internal dns service parameters
        - Check that all computes report the 'Config out-of-date' alarm
        - Lock/unlock each compute
        - Ensure the 'Config out-of-date' alarms clear

    Returns:
        - Nothing

    """

    LOG.tc_step("Ensure ml2 extension driver for dns is enabled.")
    code = system_helper.remove_ml2_extension_drivers(drivers='dns')[0]
    if code == -1:
        return

    # __clear_config_out_of_date_alarms(hosts=hosts)


def __clear_config_out_of_date_alarms(hosts):
    LOG.info("Check config out-of-date alarms are raised against the nodes and lock unlock them to clear alarms")
    for node in hosts:
        system_helper.wait_for_alarm(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, entity_id="host={}".format(node))

    LOG.info("Wait 60 seconds to ensure the service parameter is applied")
    time.sleep(60)

    host_helper.lock_unlock_hosts(hosts=hosts)
    for node in hosts:
        system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, entity_id="host={}".format(node))


def set_dns_servers(subnet_list, dns_servers=None, fail_ok=False):
    """
    Helper function to set dns servers on a list of subnets.

    Arguments:
    - net-name: tenant to be used
    - subnet_list: list of tenants to modify
    - dns_servers: a list of DNS Servers
    - fail_ok: bool

    """
    LOG.info("DNS servers are set to: {}".format(dns_servers))

    if not dns_servers:
        LOG.info("Clearing DNS entries")
        for subnet in subnet_list:
            network_helper.set_subnet(subnet, no_dns_servers=True)
    else:
        LOG.info("Setting DNS entries to: {}".format(dns_servers))
        for subnet in subnet_list:
            network_helper.set_subnet(subnet, dns_servers=dns_servers,
                                      fail_ok=fail_ok)


@fixture(scope='function')
def func_recover(request):
    vm_helper.delete_vms()
    mgmt_net_id = network_helper.get_mgmt_net_id()

    def teardown():
        """
        If DNS servers are not set, set them.  Deprovision internal DNS.
        """
        global UNRESTORED_DNS_SERVERS
        global HOSTS_AFFECTED

        if UNRESTORED_DNS_SERVERS:
            LOG.fixture_step("Restoring DNS entries to: {}".format(UNRESTORED_DNS_SERVERS))
            subnet_list = network_helper.get_subnets(network=mgmt_net_id)
            set_dns_servers(subnet_list, UNRESTORED_DNS_SERVERS, fail_ok=True)
            UNRESTORED_DNS_SERVERS = []

        if system_helper.get_alarms(alarm_id=EventLogID.CONFIG_OUT_OF_DATE):
            LOG.fixture_step("Config out-of-date alarm(s) present, check {} and lock/unlock if host config out-of-date".
                             format(HOSTS_AFFECTED))
            for host in HOSTS_AFFECTED:
                if system_helper.get_host_values(host, 'config_status')[0] == 'Config out-of-date':
                    LOG.info("Lock/unlock {} to clear config out-of-date status".format(host))
                    host_helper.lock_unlock_hosts(hosts=host)
                HOSTS_AFFECTED.remove(host)

    request.addfinalizer(teardown)

    return mgmt_net_id


@mark.p1
# Exclude for now until we improve robustness for test teardown. The impact is big if teardown is interrupted.
def test_ping_between_vms_using_hostnames(func_recover):
    """
    This test includes a positive test and a negative test.

    Positive Test:
    Verify that VMs can interact using hostnames after internal dns is setup.

    Negative Test:
    Verify VMS can no longer interact with each other using hostnames after
    disabling internal dns.

    Args:
        - Nothing

    Setup:
        - Nothing

    Test Steps:
        - Delete existing VMs and volumes
        - Provision internal dns name resolution
        - Query DNS entries for subnet and store
        - If DNS entries are not present, set them to a default value
        - Delete dns servers for desired subnet
        - Launch two VMs in the same network
        - Log into the guests and ping the other VM
        - Restore DNS entries for subnet
        - Delete VMs and volumes created during test
        - Disable internal dns name resolution
        - Launch two new VMs in the same network
        - Log into the guest and ping the other VM (should fail)
        - Delete VMS and volumes created during test

    Returns:
        - Nothing

    Teardown:
        - Check the DNS Server entries
        - If not set, restore to original values

    """

    mgmt_net_id = func_recover
    subnet_list = network_helper.get_subnets(network=mgmt_net_id)

    LOG.tc_step("Store existing DNS entries so they can be restored later")
    dns_servers = network_helper.get_subnet_values(
        subnet_list[0], fields='dns_nameservers')[0].split(', ')
    if not dns_servers:
        LOG.tc_step("No DNS servers found. Setting DNS servers to defaults")
        dns_servers = DEFAULT_DNS_SERVERS
        set_dns_servers(subnet_list, dns_servers)

    global UNRESTORED_DNS_SERVERS
    UNRESTORED_DNS_SERVERS = dns_servers
    global HOSTS_AFFECTED
    hosts = host_helper.get_hypervisors()
    HOSTS_AFFECTED = hosts

    LOG.tc_step("Enabling internal dns resolution")
    provision_internal_dns(hosts=hosts)
    HOSTS_AFFECTED = []

    LOG.tc_step("Modify DNS entries for each subnet in the network")
    subnet_list = network_helper.get_subnets(network=mgmt_net_id)
    set_dns_servers(subnet_list)

    LOG.tc_step("Launch two VMs using the same network")
    nics = [{"net-id": mgmt_net_id}]
    vm1_id = vm_helper.boot_vm(nics=nics, cleanup='function')[1]
    vm2_id = vm_helper.boot_vm(nics=nics, cleanup='function')[1]
    vm1_name = vm_helper.get_vm_name_from_id(vm1_id)
    vm2_name = vm_helper.get_vm_name_from_id(vm2_id)

    LOG.tc_step("Log into each VM and ping the other VM using the hostname")
    cmd = "ping -c 3 {}".format(vm2_name)
    with vm_helper.ssh_to_vm_from_natbox(vm1_id) as vm_ssh:
        vm_ssh.exec_cmd(cmd, fail_ok=False)
    cmd = "ping -c 3 {}".format(vm1_name)
    with vm_helper.ssh_to_vm_from_natbox(vm2_id) as vm_ssh:
        vm_ssh.exec_cmd(cmd, fail_ok=False)

    LOG.tc_step("Restore DNS entries for each subnet in the network")
    set_dns_servers(subnet_list, dns_servers)
    UNRESTORED_DNS_SERVERS = []

    LOG.tc_step("Cleanup VMs")
    vm_helper.delete_vms()

    LOG.tc_step("Disabling internal dns resolution")
    HOSTS_AFFECTED = hosts
    deprovision_internal_dns(hosts=hosts)
    HOSTS_AFFECTED = []

    LOG.tc_step("Launch two VMs using the same network")
    vm1_id = vm_helper.boot_vm(nics=nics, cleanup='function')[1]
    vm2_id = vm_helper.boot_vm(nics=nics, cleanup='function')[1]
    vm1_name = vm_helper.get_vm_name_from_id(vm1_id)
    vm2_name = vm_helper.get_vm_name_from_id(vm2_id)

    LOG.tc_step("Log into each VM and ping the other VM using the hostname")
    cmd = "ping -c 3 {}".format(vm2_name)
    with vm_helper.ssh_to_vm_from_natbox(vm1_id) as vm_ssh:
        rc, out = vm_ssh.exec_cmd(cmd, fail_ok=True)
        assert rc == 2, out
    cmd = "ping -c 3 {}".format(vm1_name)
    with vm_helper.ssh_to_vm_from_natbox(vm2_id) as vm_ssh:
        rc, out = vm_ssh.exec_cmd(cmd, fail_ok=True)
        assert rc == 2, out

    LOG.tc_step("Cleanup VMs")
    vm_helper.delete_vms()
