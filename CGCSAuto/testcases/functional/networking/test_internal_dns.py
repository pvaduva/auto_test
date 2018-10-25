import time

from pytest import fixture, mark

from consts.auth import Tenant
from consts.cgcs import EventLogID
from keywords import nova_helper, host_helper, system_helper, network_helper, vm_helper
from utils import table_parser, cli
from utils.tis_log import LOG

DEFAULT_DNS_SERVERS = ['147.11.57.133', '128.224.144.130', '147.11.57.128']
UNRESTORED_DNS_SERVERS = []
NET_NAME = None
HOSTS_AFFECTED = []


def apply_service_parameters(service, hosts):
    """
    This applies service parameters.

    Args:
        - service: service parameter to apply

    Setup:
        - Assume that there are parameters that need to be applied

    Test Steps:
        - Apply service parameters
        - Wait for nodes to report 'Config out-of-date' alarm(s)
        - Lock/unlock each affected node
        - Ensure 'Config out-of-date' alarm(s) clear

    Returns:
        - Nothing
    """
    LOG.tc_step("Applying service parameters")
    system_helper.apply_service_parameters(service, wait_for_config=False)

    LOG.tc_step("Check config out-of-date alarms are raised against the nodes")
    for node in hosts:
        system_helper.wait_for_alarm(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, entity_id="host={}".format(node))

    LOG.info("Wait 60 seconds to ensure the service parameter is applied")
    time.sleep(60)

    LOG.tc_step("Lock and unlock all affected nodes: {}".format(hosts))
    host_helper.lock_unlock_hosts(hosts=hosts)

    LOG.tc_step("Wait for the config out-of-date alarms to clear")
    for node in hosts:
        system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, entity_id="host={}".format(node))


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

    # service, section, name, value
    service = 'network'
    ml2driver = ('network', 'ml2', 'extension_drivers', 'dns')
    neutron_domain = ('network', 'default', 'dns_domain', 'example.ca')

    LOG.tc_step("Setting internal dns resolution service parameters")
    system_helper.create_service_parameter(*ml2driver)
    system_helper.create_service_parameter(*neutron_domain)

    apply_service_parameters(service, hosts=hosts)


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

    service = "network"
    ml2driver = ("network", "ml2", "extension_drivers")
    neutron_domain = ("network", "default", "dns_domain")

    LOG.tc_step("Deleting internal dns resolution service parameters")
    ml2_uuid = system_helper.get_service_parameter_values(*ml2driver, rtn_value='uuid')
    neutron_uuid = system_helper.get_service_parameter_values(*neutron_domain, rtn_value='uuid')
    system_helper.delete_service_parameter(ml2_uuid)
    system_helper.delete_service_parameter(neutron_uuid)

    apply_service_parameters(service, hosts)


def get_subnets(net_name):
    """
    Helper function to return list of subnets.

    Arguments:
    - net-name: tenant to be used
    """
    LOG.info("Query subnets")
    cmd = "net-show {}".format(net_name)
    net_show_table_ = table_parser.table(cli.neutron(cmd))
    subnet_list = table_parser.get_value_two_col_table(net_show_table_, "subnets")
    LOG.info("Subnets are: {}".format(subnet_list))

    if isinstance(subnet_list, str):
        subnet_list = [subnet_list]

    return subnet_list


def get_dns_servers(net_name):
    """
    Helper function to return list of dns servers.

    Arguments:
    - net-name: tenant to be used
    """

    LOG.info("Query DNS Servers")
    subnet_list = get_subnets(net_name)
    cmd = "subnet-show {}".format(subnet_list[0])
    subnet_show_table_ = table_parser.table(cli.neutron(cmd))
    dns_servers = table_parser.get_value_two_col_table(subnet_show_table_, "dns_nameservers")
    LOG.info("DNS servers are: {}".format(dns_servers))

    return dns_servers


def set_dns_servers(subnet_list, dns_servers=None):
    """
    Helper function to set dns servers on a list of subnets.

    Arguments:
    - net-name: tenant to be used
    - subnet_list: list of tenants to modify
    - dns_servers: a list of DNS Servers

    """
    LOG.info("DNS servers are set to: {}".format(dns_servers))

    if not dns_servers:
        LOG.info("Clearing DNS entries")
        for subnet in subnet_list:
            args = " {} --dns_nameservers action=clear".format(subnet)
            cli.neutron('subnet-update', args, auth_info=Tenant.get('admin'))
    else:
        LOG.info("Setting DNS entries to: {}".format(dns_servers))
        for subnet in subnet_list:
            dns_string = " ".join(dns_servers)
            args = " {} --dns_nameservers list=true {}".format(subnet, dns_string)
            cli.neutron("subnet-update", args, auth_info=Tenant.get('admin'))


@fixture(scope='function', autouse=True)
def func_recover(request):
    def teardown():
        """
        If DNS servers are not set, set them.  Deprovision internal DNS.
        """
        global UNRESTORED_DNS_SERVERS
        global NET_NAME
        global HOSTS_AFFECTED

        if UNRESTORED_DNS_SERVERS:
            LOG.fixture_step("Restoring DNS entries to: {}".format(UNRESTORED_DNS_SERVERS))
            subnet_list = get_subnets(NET_NAME)
            set_dns_servers(subnet_list, UNRESTORED_DNS_SERVERS)
            UNRESTORED_DNS_SERVERS = []

        if system_helper.get_alarms(alarm_id=EventLogID.CONFIG_OUT_OF_DATE):
            LOG.fixture_step("Config out-of-date alarm(s) present, check {} and lock/unlock if host config out-of-date".
                             format(HOSTS_AFFECTED))
            for host in HOSTS_AFFECTED:
                if host_helper.get_hostshow_value(host, 'config_status') == 'Config out-of-date':
                    LOG.info("Lock/unlock {} to clear config out-of-date status".format(host))
                    host_helper.lock_unlock_hosts(hosts=host)
            HOSTS_AFFECTED = []

    request.addfinalizer(teardown)


@mark.p1
# Exclude for now until we improve robustness for test teardown. The impact is big if teardown is interrupted.
def test_ping_between_vms_using_hostnames():
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

    vm_helper.delete_vms()

    mgmt_net_id = network_helper.get_mgmt_net_id()
    net_name = network_helper.get_net_name_from_id(net_id=mgmt_net_id)

    global NET_NAME
    NET_NAME = net_name
    subnet_list = get_subnets(NET_NAME)

    LOG.tc_step("Store existing DNS entries so they can be restored later")
    dns_servers = get_dns_servers(NET_NAME)

    if not dns_servers:
        LOG.tc_step("No DNS servers found.  Setting DNS servers to defaults")
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
    subnet_list = get_subnets(net_name)
    set_dns_servers(subnet_list)

    LOG.tc_step("Launch two VMs using the same network")
    nics = [{"net-id": mgmt_net_id, "vif-model": "virtio"}]
    vm1_id = vm_helper.boot_vm(nics=nics, cleanup='function')[1]
    vm2_id = vm_helper.boot_vm(nics=nics, cleanup='function')[1]
    vm1_name = nova_helper.get_vm_name_from_id(vm1_id)
    vm2_name = nova_helper.get_vm_name_from_id(vm2_id)

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
    vm1_name = nova_helper.get_vm_name_from_id(vm1_id)
    vm2_name = nova_helper.get_vm_name_from_id(vm2_id)

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
