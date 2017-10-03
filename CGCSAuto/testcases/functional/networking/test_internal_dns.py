import time
import datetime
from copy import copy
from pytest import fixture, mark, skip
from keywords import nova_helper, host_helper, system_helper, network_helper, vm_helper, common
from utils import table_parser, cli
from utils.tis_log import LOG
from utils.ssh import ControllerClient
from consts.cgcs import EventLogID
from consts.proj_vars import ProjVar
from consts.auth import Tenant
from testfixtures.fixture_resources import ResourceCleanup

DEFAULT_DNS_SERVERS = ['147.11.57.133', '128.224.144.130', '147.11.57.128']


def apply_service_parameters(service):
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

    computes_list = list(system_helper.get_computes().keys())
    controller_list = system_helper.get_controllers()

    if not computes_list:
        node_list = controller_list
    else:
        node_list = computes_list

    LOG.tc_step("Applying service parameters")
    system_helper.apply_service_parameters(service, wait_for_config=False)

    LOG.tc_step("Check config out-of-date alarms are raised against the nodes")
    for node in node_list:
        assert system_helper.wait_for_alarm(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, entity_id="host={}".format(node))

    LOG.tc_step("Wait 60 seconds to ensure the service parameter is applied")
    time.sleep(60)

    LOG.tc_step("Lock and unlock all affected nodes")
    if not computes_list and len(controller_list) == 2:
        standby_controller = system_helper.get_standby_controller_name()
        host_helper.lock_host(standby_controller)
        host_helper.unlock_host(standby_controller)
        active_controller = system_helper.get_active_controller_name()
        host_helper.swact_host(active_controller)
        new_standby_controller = system_helper.get_standby_controller_name()
        host_helper.lock_host(new_standby_controller)
        host_helper.unlock_host(new_standby_controller)
    elif not computes_list and len(controller_list) == 1:
        host_helper.lock_host(node_list)
        host_helper.unlock_host(node_list)
    else:
        for node in node_list:
            host_helper.lock_host(node)
        host_helper.unlock_hosts(node_list)

    LOG.tc_step("Wait for the config out-of-date alarms to clear")
    for node in node_list:
        assert system_helper.wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, entity_id="host={}".format(node))


def provision_internal_dns():
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

    apply_service_parameters(service)


def deprovision_internal_dns():
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
    ml2driver = ("uuid", "network", "ml2", "extension_drivers")
    neutron_domain = ("uuid", "network", "default", "dns_domain")

    LOG.tc_step("Deleting internal dns resolution service parameters")
    ml2_uuid = system_helper.get_service_parameter_values(*ml2driver)
    neutron_uuid = system_helper.get_service_parameter_values(*neutron_domain)
    system_helper.delete_service_parameter(ml2_uuid)
    system_helper.delete_service_parameter(neutron_uuid)

    apply_service_parameters(service)


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


def set_dns_servers(net_name, subnet_list, dns_servers=[]):
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
            cli.neutron('subnet-update', args, auth_info=Tenant.ADMIN)
    else:
        LOG.tc_step("Setting DNS entries to: {}".format(dns_servers))
        for subnet in subnet_list:
            dns_string = " ".join(dns_servers)
            args = " {} --dns_nameservers list=true {}".format(subnet, dns_string)
            cli.neutron("subnet-update", args, auth_info=Tenant.ADMIN)


@fixture(scope="module", autouse=True)
def invoketeardown(request):
    def teardown():
        """
        If DNS servers are not set, set them.  Deprovision internal DNS.
        """
        global dns_servers
        global net_name

        current_dns_servers = get_dns_servers(net_name)
        LOG.info("DNS servers are set to: {}".format(dns_servers))
        if not dns_servers:
            LOG.info("Restoring DNS entries to: {}".format(dns_servers))
            subnet_list = get_subnets(net_name)
            set_dns_servers(net_name, subnet_list, dns_servers)
        vm_helper.delete_vms()

    request.addfinalizer(teardown)


@mark.p1
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

    global dns_servers
    global net_name

    dns_servers = []
    net_name = ""

    vm_helper.delete_vms()

    if ProjVar.get_var('PRIMARY_TENANT') == 'tenant1':
        net_name = "tenant1-mgmt-net"
    else:
        net_name = "tenant2-mgmt-net"

    LOG.tc_step("Store existing DNS entries so they can be restored later")
    dns_servers = get_dns_servers(net_name)

    if not dns_servers:
        LOG.tc_step("No DNS servers found.  Setting DNS servers to defaults")
        dns_servers = DEFAULT_DNS_SERVERS
        subnet_list = get_subnets(net_name)
        set_dns_servers(net_name, subnet_list, dns_servers)

    LOG.tc_step("Enabling internal dns resolution")
    provision_internal_dns()

    LOG.tc_step("Modify DNS entries for each subnet in the network")
    subnet_list = get_subnets(net_name)
    set_dns_servers(net_name, subnet_list)

    LOG.tc_step("Launch two VMs using the same network")
    mgmt_net_id = network_helper.get_mgmt_net_id()
    nics=[{"net-id": mgmt_net_id, "vif-model": "virtio"}]
    vm1_id = vm_helper.boot_vm(nics=nics)[1]
    vm2_id = vm_helper.boot_vm(nics=nics)[1]
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
    set_dns_servers(net_name, subnet_list, dns_servers)

    LOG.tc_step("Cleanup VMs")
    vm_helper.delete_vms()

    LOG.tc_step("Disabling internal dns resolution")
    deprovision_internal_dns()

    LOG.tc_step("Launch two VMs using the same network")
    mgmt_net_id = network_helper.get_mgmt_net_id()
    nics=[{"net-id": mgmt_net_id, "vif-model": "virtio"}]
    vm1_id = vm_helper.boot_vm(nics=nics)[1]
    vm2_id = vm_helper.boot_vm(nics=nics)[1]
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
