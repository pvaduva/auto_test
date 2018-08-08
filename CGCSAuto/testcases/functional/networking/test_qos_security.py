import time
import ipaddress
from collections import Counter
from contextlib import contextmanager, ExitStack
from pytest import fixture, mark, skip
from consts.auth import Tenant
from consts.filepaths import IxiaPath
from consts.proj_vars import ProjVar
from consts.cgcs import FlavorSpec
from utils import cli, table_parser
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG
from utils.guest_scripts.scripts import DPDKPktgen
from testfixtures.fixture_resources import ResourceCleanup
from keywords import network_helper, vm_helper, common, nova_helper, host_helper, ixia_helper, system_helper


@fixture(scope='module')
def update_network_quotas_primary(request):
    tenant = Tenant.get_primary()['tenant']

    LOG.fixture_step("Increasing network and subnet quotas by 10 for {}".format(tenant))
    nw_quota = network_helper.get_quota('network', tenant_name=tenant)
    sn_quota = network_helper.get_quota('subnet', tenant_name=tenant)
    network_helper.update_quotas(tenant_name=tenant, subnet=sn_quota+10, network=nw_quota+10)

    def teardown():
        LOG.fixture_step("Reverting network and subnet quotas for {}".format(tenant))
        network_helper.update_quotas(tenant_name=tenant, subnet=sn_quota, network=nw_quota)
    request.addfinalizer(teardown)


@fixture(scope='module')
def update_network_quotas_secondary(request):
    tenant = Tenant.get_secondary()['tenant']

    LOG.fixture_step("Increasing network and subnet quotas by 10 for {}".format(tenant))
    nw_quota = network_helper.get_quota('network', tenant_name=tenant)
    sn_quota = network_helper.get_quota('subnet', tenant_name=tenant)
    network_helper.update_quotas(tenant_name=tenant, subnet=sn_quota+10, network=nw_quota+10)

    def teardown():
        LOG.fixture_step("Reverting network and subnet quotas for {}".format(tenant))
        network_helper.update_quotas(tenant_name=tenant, subnet=sn_quota, network=nw_quota)
    request.addfinalizer(teardown)


@fixture(scope='module')
def update_network_quotas(request, update_network_quotas_primary, update_network_quotas_secondary):
    pass


@fixture(scope='function')
def skip_if_25G():
    if ProjVar.get_var("LAB")['name'] in ["yow-cgcs-wildcat-61_62", "yow-cgcs-wildcat-63_66"]:
        skip("25G labs are not supported for this testcase due to insufficient stress")


@mark.parametrize('vm_type', [
    'virtio',
    'avp',
    'dpdk'
])
class TestPacketTypeSecurityRuleEnforcement(object):
    @fixture(scope='class')
    def security_groups(self):
        LOG.fixture_step("(class) Create two security groups")

        sg_primary = network_helper.create_security_group(
            "test_pkt_typ_sec_rul_enf", auth_info=Tenant.get_primary(), cleanup='class')
        sg_secondary = network_helper.create_security_group(
            "test_pkt_typ_sec_rul_enf", auth_info=Tenant.get_secondary(), cleanup='class')

        # required by ping_vms
        cli.openstack(
            "security group rule create",
            "--protocol icmp --remote-ip 0.0.0.0/0 --ingress {}".format(sg_primary), auth_info=Tenant.ADMIN)
        cli.openstack(
            "security group rule create",
            "--protocol icmp --remote-ip 0.0.0.0/0 --ingress {}".format(sg_secondary), auth_info=Tenant.ADMIN)

        # required by routing and ssh (TCP), could be restricted to ranges over internal-network and mgmt-network
        cli.openstack(
            "security group rule create",
            "--protocol tcp --remote-ip 0.0.0.0/0 --ingress {}".format(sg_primary), auth_info=Tenant.ADMIN)
        cli.openstack(
            "security group rule create",
            "--protocol tcp --remote-ip 0.0.0.0/0 --ingress {}".format(sg_secondary), auth_info=Tenant.ADMIN)

        yield sg_primary, sg_secondary

    def test_apply_group_at_launch(self, vm_type, ixia_supported, security_groups):
        """
        Apply security group to VMs at launch time, verify the rules are enforced

        Test Steps:
            - Create a VM pair of vm_type NICs with security group to disallow UDP traffic
            - Setup UDP traffic between vm_pair
            - Verify packets can not be received

        Test Teardown:
            - Stop traffic
            - Delete vms, volumes, flavor, security groups created
        """
        sg_primary, sg_secondary = security_groups

        vm_test, vm_observer = vm_helper.launch_vm_pair(
            vm_type,
            primary_kwargs=dict(sec_group_name=sg_primary),
            secondary_kwargs=dict(sec_group_name=sg_secondary))

        with vm_helper.traffic_between_vms([(vm_test, vm_observer)], ixncfg=IxiaPath.CFG_UDP) as session:
            LOG.tc_step("Verify UDP traffic is not allowed")
            succ, val = common.wait_for_val_from_func(0, 30, 5, session.get_frames_delta)
            assert not succ, "udp traffic successfully passed through"

    def test_apply_group_running_vm(self, vm_type, ixia_supported, security_groups):
        """
        Apply security group to VMs when the VMs are running, verify the rules are enforced

        Test Steps:
            - Create a VM pair of vm_type NICs
            - Apply security group to disallow UDP traffic
            - Setup UDP traffic between vm_pair
            - Verify packets can not be received

        Test Teardown:
            - Stop traffic
            - Delete vms, volumes, flavor, security groups created
        """
        sg_primary, sg_secondary = security_groups

        vm_test, vm_observer = vm_helper.launch_vm_pair(vm_type)

        LOG.tc_step("Add security groups to launched VMs")
        cli.nova('add-secgroup', "{} {}".format(vm_test, sg_primary), auth_info=Tenant.ADMIN)
        cli.nova('add-secgroup', "{} {}".format(vm_observer, sg_secondary), auth_info=Tenant.ADMIN)

        with vm_helper.traffic_between_vms([(vm_test, vm_observer)], ixncfg=IxiaPath.CFG_UDP) as session:
            LOG.tc_step("Verify UDP traffic is not allowed")
            succ, val = common.wait_for_val_from_func(0, 30, 5, session.get_frames_delta)
            assert not succ, "udp traffic successfully passed through"

    def test_modify_running_vm(self, vm_type, ixia_supported, security_groups):
        """
        Verify security_group related modifications are functioning as expected

        Test Steps:
            - Create a VM pair of vm_type NICs with security group to disallow UDP traffic
            - Verify security groups in use cannot be deleted
            - Setup UDP traffic between vm_pair
            - Verify packets can not be received
            - Add security group rules to allow UDP traffic
            - Verify packets can be received
            - Delete security group rules to disallow UDP traffic
            - Verify packets can not be received
            - Disassociate security group with VMs
            - Verify packets can be received

        Test Teardown:
            - Stop traffic
            - Delete vms, volumes, flavor, security groups created
        """
        sg_primary, sg_secondary = security_groups

        vm_test, vm_observer = vm_helper.launch_vm_pair(
            vm_type,
            primary_kwargs=dict(sec_group_name=sg_primary),
            secondary_kwargs=dict(sec_group_name=sg_secondary))

        LOG.info("Delete security group associated with running VM, verify it fails")
        code, output = network_helper.delete_security_group(sg_primary, fail_ok=True)
        LOG.info(output)
        assert code, "in-use security group {} deletion succeeded".format(sg_primary)
        code, output = network_helper.delete_security_group(sg_secondary, fail_ok=True)
        LOG.info(output)
        assert code, "in-use security group {} deletion succeeded".format(sg_secondary)

        with vm_helper.traffic_between_vms([(vm_test, vm_observer)], ixncfg=IxiaPath.CFG_UDP) as session:
            LOG.tc_step("Verify UDP traffic is not allowed")
            succ, val = common.wait_for_val_from_func(0, 30, 5, session.get_frames_delta)
            assert not succ, "udp traffic successfully passed through"

            LOG.tc_step("Allow UDP traffic on the fly and verify traffic comes back to normal")
            with udp_allow(*security_groups) as modified_groups:
                session.get_frames_delta(stable=True)   # raises if the delta is increasing (i.e., udp denied)

            LOG.tc_step("Verify UDP traffic is no longer allowed")
            succ, val = common.wait_for_val_from_func(0, 30, 5, session.get_frames_delta)
            assert not succ, "udp traffic successfully passed through"

            LOG.tc_step("Disassociate the security group, verify UDP traffic is allowed")
            cli.openstack("server remove security group {} {}".format(vm_test, sg_primary), auth_info=Tenant.ADMIN)
            cli.openstack("server remove security group {} {}".format(vm_observer, sg_secondary), auth_info=Tenant.ADMIN)
            session.get_frames_delta(stable=True)


@mark.parametrize('tenant', [
    'tenant1',
    'tenant2',
])
def test_max_reached_creation_fail(tenant):
    """
    Verify security group and security group rule quotas are respected

    Test Steps:
        - Retrieve security group and security group rule quota
        - Retrieve # of security groups in use
        - Create enough security groups to reach the quota
        - Verify creation fails
        - Retrieve $ of security group rules in use
        - Create enough security group rules to reach the quota
        - Verify creation fails

    Test Teardown:
        - Delete security groups created
    """
    if tenant == 'tenant1':
        auth_info = Tenant.TENANT1
    elif tenant == 'tenant2':
        auth_info = Tenant.TENANT2

    # nova_helper.get_quotas uses nova quota-show, which does not include secgroup* fields
    LOG.tc_step("Retrive quota and usage information")
    quota_table = table_parser.table(cli.openstack('quota show', auth_info=auth_info))
    max_secgroups = int(table_parser.get_value_two_col_table(quota_table, 'secgroups'))
    max_rules = int(table_parser.get_value_two_col_table(quota_table, 'secgroup-rules'))
    LOG.info("Tenant Quota Retrieved: secgroups={} secgroup-rules={}".format(max_secgroups, max_rules))

    LOG.tc_step("Retrieve usage for security groups")
    groups_list = table_parser.table(cli.openstack('security group list', auth_info=auth_info))
    in_use_secgroups = len(table_parser.get_all_rows(groups_list))
    LOG.info("Tenant InUse Retrieved: secgroups={}".format(in_use_secgroups))

    LOG.tc_step("Create enough groups to reach the quota")
    for i in range(max_secgroups - in_use_secgroups):
        # take the last security group for rules creation
        sec_group = network_helper.create_security_group('test_max_reached_creation_fail', auth_info=auth_info)

    LOG.tc_step("Verify security group creation fail as quota is reached")
    code, msg = network_helper.create_security_group(
        'test_max_reached_creation_fail', auth_info=auth_info, fail_ok=True)
    assert code, "creation after max quota reached succeeded"

    LOG.tc_step("Retrieve usage for security group rules")
    # note: each new security group creates 2 default rules for egress
    # therefore this usage must be retrieved after security group operations are completed
    rules_list = table_parser.table(cli.openstack('security group rule list', auth_info=auth_info))
    in_use_rules = len(table_parser.get_all_rows(rules_list))
    LOG.info("Tenant InUse Retrieved: secgroups-rules={}".format(in_use_rules))

    LOG.tc_step("Create enough rules to reach the quota")
    dummy_ip = ipaddress.ip_address("0.0.0.0")
    for i in range(max_rules - in_use_rules):
        dummy_ip += 1   # duplicate security group rule creation will fail
        cli.openstack(
            "security group rule create", "--protocol udp --remote-ip {}/32 --ingress {}".format(
                dummy_ip, sec_group),
            auth_info=auth_info)
    LOG.tc_step("Verify security rule creation fail as quota is reached")
    code, msg = cli.openstack(
        "security group rule create", "--protocol udp --remote-ip 255.255.255.254/32 --ingress {}".format(
            sec_group),
        auth_info=auth_info, fail_ok=True)
    assert code, "creation after max quota reached succeeded"


@contextmanager
def udp_allow(sg_primary, sg_secondary):
    LOG.info("Creating rules to allow UDP ingress for {} and {}".format(sg_primary, sg_secondary))
    table = table_parser.table(
        cli.openstack(
            "security group rule create", "--protocol udp --remote-ip 0.0.0.0/0 --ingress {}".format(sg_primary),
            auth_info=Tenant.ADMIN))
    udp_primary = table_parser.get_value_two_col_table(table, 'id')

    table = table_parser.table(
        cli.openstack(
            "security group rule create", "--protocol udp --remote-ip 0.0.0.0/0 --ingress {}".format(sg_secondary),
            auth_info=Tenant.ADMIN))
    udp_secondary = table_parser.get_value_two_col_table(table, 'id')

    yield sg_primary, sg_secondary

    LOG.info("Deleting UDP ingress rules for {} and {}".format(sg_primary, sg_secondary))
    cli.openstack("security group rule delete", udp_primary, auth_info=Tenant.ADMIN)
    cli.openstack("security group rule delete", udp_secondary, auth_info=Tenant.ADMIN)


def qos_apply(net_id, qos_id, request):
    old_qos = network_helper.get_net_info(net_id=net_id, field='wrs-tm:qos')
    network_helper.update_net_qos(net_id, qos_id)

    def teardown():
        if old_qos:
            network_helper.update_net_qos(net_id, old_qos)

    request.addfinalizer(teardown)
    return old_qos


def ensure_vms_on_host(vms, host, *args, **kwargs):
    results = dict()
    for vm in vms:
        vm_host = nova_helper.get_vm_host(vm)
        if host != vm_host:
            results[vm] = vm_helper.live_migrate_vm(vm, host, *args, **kwargs)

    return results


def ensure_vms_on_same_host(vms, *args, **kwargs):
    """
    Ensure all VMs provided will sit on the same host
    selects the current host for most VMs in the list
    if multiple choices available, the target host is arbitrary

    Args:
        vms (list):
            list of VMs to ensure
        args (list):
            additional arguments for live_migrate_vm
        kwargs (dict):
            additional keyword arguments for live_migrate_vm

    Returns (str|None):
        the target compute host
        or None if vms is empty
    """
    if len(vms) == 0:
        return None
    if len(vms) == 1:
        return nova_helper.get_vm_host(vms[0])

    LOG.info("Ensuring the following VMs are on the same compute host: {}".format(vms))
    host_map = dict()
    for vm in vms:
        host_map[vm] = nova_helper.get_vm_host(vm)

    most_common, num_most_common = Counter(list(host_map.values())).most_common(1)[0]
    if num_most_common == len(vms):
        LOG.info("All VMs in the list sit on {}, skipping".format(most_common))
    else:
        LOG.info(
            "Most VMs ({}) in the list sit on {}, migrating the other instances".format(num_most_common, most_common))
        ensure_vms_on_host(vms, most_common)
    return most_common


def test_qos_weight_enforced(request, skip_if_25G):
    """
    Verify QoS weights are impacting networks
    DPDK-only test case (kpktgen does not supply enough Tx rate)

    Test Steps:
        - Create two QoS policies, with different weights
        - Assign policies to different tenant networks for the primary tenant
        - Launch two pairs of DPDK VMs attached to differently weighted networks
        - Move VMs so that 1 HIGH and 1 LOW VM sits on each side
        - Start pktgen, forward flow at 100%, backward flow at 1% to ensure vSwitch learns destination MACs
        - Reset compute's vshell statistics counter
        - Wait
        - Collect from vshell for distribution
        - Verify QoS weights are impacting drop rates of two tenant networks under stress-ed host (Rx(H) > Rx(L))

    Test Teardown:
        - Delete qoses, vms, volumes, flavors
    """
    if not system_helper.is_avs():
        skip("vshell not available on ovs systems")

    vm_type = 'dpdk'
    vif_model = 'avp'

    tenant_nets = network_helper.get_tenant_net_ids()
    if len(tenant_nets) < 2:
        skip("less than two tenant-nets under the primary tenant")
    tenant_high = tenant_nets[0]
    tenant_low = tenant_nets[1]
    mgmt_net = network_helper.get_mgmt_net_id(auth_info=Tenant.get_primary())

    LOG.tc_step("Create QoS policies with different weights")
    weight_high, weight_low = 100, 10
    qos_high = network_helper.create_qos(scheduler={'weight': weight_high}, tenant_name=Tenant.get_primary()['tenant'])[1]
    qos_low = network_helper.create_qos(scheduler={'weight': weight_low}, tenant_name=Tenant.get_primary()['tenant'])[1]

    LOG.tc_step("Assign network QoS policies")
    qos_apply(tenant_high, qos_high, request)
    qos_apply(tenant_low, qos_low, request)
    qos_apply(mgmt_net, qos_high, request)

    LOG.tc_step("Launch 4 VMs")
    flavor = nova_helper.create_flavor(name=vm_type, vcpus=3, ram=2048)[1]
    ResourceCleanup.add('flavor', flavor, scope='function')
    extra_specs = {FlavorSpec.CPU_POLICY: 'dedicated'}
    extra_specs.update({FlavorSpec.VCPU_MODEL: 'SandyBridge', FlavorSpec.MEM_PAGE_SIZE: '2048'})
    nova_helper.set_flavor_extra_specs(flavor=flavor, **extra_specs)

    nics = [{'net-id': mgmt_net, 'vif-model': 'virtio'},
            {'net-id': tenant_high, 'vif-model': vif_model}]
    vms_high, nics = vm_helper.launch_vms(vm_type, nics=nics, count=2, flavor=flavor)

    nics = [{'net-id': mgmt_net, 'vif-model': 'virtio'},
            {'net-id': tenant_low, 'vif-model': vif_model}]
    vms_low, nics = vm_helper.launch_vms(vm_type, nics=nics, count=2, flavor=flavor)

    # one LOW and one HIGH sit on each side(/compute)
    vm_pairs = list(zip(vms_high, vms_low))
    pair1 = vm_pairs[0]
    pair2 = vm_pairs[1]

    LOG.tc_step("Ensure VM locations")
    compute_A = ensure_vms_on_same_host(pair1)
    for vm in pair2:
        if nova_helper.get_vm_host(vm) == compute_A:
            vm_helper.live_migrate_vm(vm)
    compute_B = ensure_vms_on_same_host(pair2)

    LOG.tc_step("Start dpdk_pktgen")
    for vm in vms_high + vms_low:    # scp is rather slow
        vm_helper.scp_to_vm(vm, DPDKPktgen.src(), DPDKPktgen.dst())

    # high[0]->high[1] 100%;    high[1]<-high[0] 1%
    #  low[0]-> low[1] 100%;     low[1]<- low[0] 1%
    for vms in [vms_high, vms_low]:
        for (vm1, vm2), rate in zip([vms, reversed(list(vms))], [100, 1]):

            # resolve destination MACs here instead of using ARPs
            # due to unsynchronized starting time, ARP packets could get lost when the vswitch is flooded
            dst_ip = network_helper.get_data_ips_for_vms(vm2)[0]
            dst_mac = None
            for vm_id, info in vm_helper.get_vms_ports_info([vm2], rtn_subnet_id=True).items():
                for ip, subnet_id, mac in info:
                    if ip == dst_ip:
                        dst_mac = mac
                        break
            assert dst_mac is not None, "mac not resolved for {}".format(dst_ip)

            with vm_helper.ssh_to_vm_from_natbox(vm1) as vm_ssh:
                DPDKPktgen.configure(
                    vm_ssh,
                    "set 0 dst ip {}".format(dst_ip),
                    "set 0 src ip {}".format(network_helper.get_data_ips_for_vms(vm1)[0] + '/24'),
                    "set 0 dst mac {}".format(dst_mac),
                    # "enable mac_from_arp",
                    "enable 0 process",
                    "set 0 size 128",
                    "set 0 rate {}".format(rate),
                    # "start 0 arp request",
                    "start 0")
                # 60s delay, as once started, the network becomes extremely unstable -> SSH Failure
                DPDKPktgen.start(vm_ssh)

    time.sleep(60)   # wait for all DPDKPktgen to start
    con_ssh = ControllerClient.get_active_controller()
    LOG.tc_step("Reset vswitch statistics")
    # synchornized reference point
    for host in [compute_A, compute_B]:
        con_ssh.exec_cmd("vshell -H {} engine-stats-clear".format(host), fail_ok=False)
        con_ssh.exec_cmd("vshell -H {} port-stats-clear".format(host), fail_ok=False)
        con_ssh.exec_cmd("vshell -H {} interface-stats-clear".format(host), fail_ok=False)
        con_ssh.exec_cmd("vshell -H {} network-stats-clear".format(host), fail_ok=False)

    wait = 60
    LOG.tc_step("Wait for {} seconds".format(wait))
    time.sleep(wait)

    # check vshell rx-es for vports;
    LOG.tc_step("Verify QoS weights are impacting drop rates of two tenant networks under stress-ed host")

    # for post mortem analysis
    con_ssh.exec_cmd("vshell -H {} engine-stats-list".format(compute_A), fail_ok=False)
    con_ssh.exec_cmd("vshell -H {} port-stats-list".format(compute_A), fail_ok=False)
    con_ssh.exec_cmd("vshell -H {} interface-stats-list".format(compute_A), fail_ok=False)
    con_ssh.exec_cmd("vshell -H {} network-stats-list".format(compute_A), fail_ok=False)

    # analyze Rx side stats
    con_ssh.exec_cmd("vshell -H {} engine-stats-list".format(compute_B), fail_ok=False)
    succ, ifaces = con_ssh.exec_cmd("vshell -H {} interface-list".format(compute_B), fail_ok=False)
    succ, port_stats = con_ssh.exec_cmd("vshell -H {} port-stats-list".format(compute_B), fail_ok=False)
    succ, iface_stats = con_ssh.exec_cmd("vshell -H {} interface-stats-list".format(compute_B), fail_ok=False)
    succ, nw_stats = con_ssh.exec_cmd("vshell -H {} network-stats-list".format(compute_B), fail_ok=False)

    rx_high_id = network_helper.get_ports(ip_addr=network_helper.get_data_ips_for_vms(vms_high[1])[0])[0]
    rx_low_id = network_helper.get_ports(ip_addr=network_helper.get_data_ips_for_vms(vms_low[1])[0])[0]
    port_stats_table = table_parser.table(port_stats)
    iface_stats_table = table_parser.table(iface_stats)
    nw_stats_table = table_parser.table(nw_stats)

    # usually IP/MAC destination incorrect, verify manually (/root/dpdk_pktgen.[config/sh])
    for flood in table_parser.get_values(nw_stats_table, 'packets-flood'):
        assert int(flood) < 100000, "vswitch flooeded, setup is incorrect"

    # tx-packets, the amount host vswitch sent to the guest vnic
    rx_high_bytes = int(table_parser.get_values(iface_stats_table, 'tx-bytes', uuid=rx_high_id)[0])
    rx_low_bytes = int(table_parser.get_values(iface_stats_table, 'tx-bytes', uuid=rx_low_id)[0])

    LOG.info("high rx-bytes: {:>10}".format(rx_high_bytes))
    LOG.info("high rx-Gbps : {:>10.2f}".format(rx_high_bytes/125000000/wait))
    LOG.info(" low rx-bytes: {:>10}".format(rx_low_bytes))
    LOG.info(" low rx-Gbps : {:>10.2f}".format(rx_low_bytes/125000000/wait))

    assert abs(rx_high_bytes/rx_low_bytes - weight_high/weight_low) < 0.3*weight_high/weight_low,   \
        "weight policy deviated by more than 30%"


def setup_busy_loop_net(host, vlan_a, vlan_b, request, mtu=1492, eth='eth0'):
    with host_helper.ssh_to_host(host) as host_ssh:
        succ, uuid_nw = host_ssh.exec_cmd("uuidgen -r", fail_ok=False)
        succ, uuid_va = host_ssh.exec_cmd("uuidgen -r", fail_ok=False)
        succ, uuid_vb = host_ssh.exec_cmd("uuidgen -r", fail_ok=False)
        with network_helper.vconsole(host_ssh) as v_exec:
            v_exec("network add busy_loop_net {}".format(uuid_nw))
            v_exec("vlan add {} {} {} {}".format(eth, vlan_a, uuid_va, mtu))
            v_exec("vlan add {} {} {} {}".format(eth, vlan_b, uuid_vb, mtu))
            v_exec("bridge attach {}.{} busy_loop_net".format(eth, vlan_a))
            v_exec("bridge attach {}.{} busy_loop_net".format(eth, vlan_b))

    def teardown():
        LOG.fixture_step("removing busy_loop_net from {}".format(host))
        with host_helper.ssh_to_host(host) as host_ssh:
            with network_helper.vconsole(host_ssh) as v_exec:
                v_exec("vlan delete {}.{}".format(eth, vlan_a), fail_ok=True)
                v_exec("vlan delete {}.{}".format(eth, vlan_b), fail_ok=True)
                v_exec("network delete busy_loop_net", fail_ok=True)
    request.addfinalizer(teardown)


@mark.parametrize('vm_type', [
    'virtio',
    'avp',
])
def test_qos_phb_enforced(vm_type, skip_if_25G, ixia_supported, request, update_network_quotas):
    """
    Verify QoS PHB policies are applied via traffic, driven by Ixia
    PHB precedence weights are hardcoded

    Test Steps:
        - Launch a vm_pair
        - Setup with different PHBs for traffic at the same rate
        - Start traffic and keep increasing framerate until vNIC capability reached
        - Wait for statistics
        - Verify PHB weights are properly distributed

    Test Teardown:
        - Delete vms, volumes, flavors, networks, subnets
    """
    if not system_helper.is_avs():
        skip("cannot properly setup guests without avs")

    vm_test = vm_helper.launch_vm_with_both_providernets(vm_type)
    nic_test = (network_helper.get_data_ips_for_vms(vm_test)[0], vm_test)
    nic_observer = (network_helper.get_data_ips_for_vms(vm_test)[1], vm_test)

    with vm_helper.traffic_between_vms(
            [(nic_test, nic_observer)] * 8,
            fps=2, fps_type="percentLineRate", bidirectional=True, start_traffic=False) as session:

        LOG.tc_step("Setup traffic items with PHBs and frameRates")
        for trafficItem in session.getList(session.getRoot()+'/traffic', 'trafficItem'):
            name = session.getAttribute(trafficItem, 'name')
            configElement = session.getList(trafficItem, 'configElement')[0]
            if 'vm_pairs' in name:
                index = int(name[name.index('[')+1: name.index(']')])
            else:
                continue

            if index == 0:  # ixia does not support CS0. since default is zero, skip it.
                continue

            mp = ['Precedence {}'.format(i) for i in range(8)]
            session.configure(
                configElement+'/stack:"ipv4-3"/field:"ipv4.header.priority.ds.phb.classSelectorPHB.classSelectorPHB-12"',
                activeFieldChoice=True, fieldValue=mp[index])
            trackBy = session.getAttribute(trafficItem+'/tracking', 'trackBy') + ["ipv4ClassSelectorPhb0"]
            session.configure(trafficItem+'/tracking', trackBy=trackBy)

        LOG.tc_step("Start traffic and keep increasing frameRate until vNIC starts dropping")
        session.traffic_start()

        # at 13% for 8 flowgroups, >100% line rate will be reached --> invalid flowgroups
        for frame_rate in range(1, 13):
            LOG.info("Adjusting frame rates to {}%".format(frame_rate))
            for trafficItem in session.getList(session.getRoot()+'/traffic', 'trafficItem'):
                name = session.getAttribute(trafficItem, 'name')
                if 'vm_pairs' not in name:
                    continue
                for hls in session.get_hls(trafficItem):
                    # rate = int(float(session.getAttribute(hls+'/frameRate', 'rate')))
                    session.configure(hls+'/frameRate', rate=frame_rate, type="percentLineRate")

            session.traffic_apply_live()
            time.sleep(10)

            stats = session.get_statistics('traffic item statistics', fail_ok=False)
            results = [0 for i in range(8)]
            for item in stats:
                name = item['Traffic Item']
                if 'vm_pairs' in name:
                    index = int(name[name.index('[')+1: name.index(']')])
                else:
                    continue

                results[index] = float(item[r'Rx Frame Rate'])

            LOG.info("Verifying Rx rate distribution with 1% tolerance")
            fail = False
            class_weights = [1, 1, 2, 2, 4, 8, 16, 32]
            total_framerates = sum(results)
            total_weights = sum(class_weights)
            for precedence in range(len(class_weights)):
                expected = class_weights[precedence] / total_weights * total_framerates
                LOG.info("PHB Precedence {}: Frame Rates: Expected: {:>10}; Actual: {:>10}".format(
                    precedence, int(expected), int(results[precedence])))

                # allow 1% deviation
                if expected - 0.01 * total_framerates <= results[precedence] <= expected + 0.01 * total_framerates:
                    pass
                else:
                    fail = True

            if not fail:
                break

        LOG.tc_step("Collecting vshell statistics over 60 seconds interval for post analytics")
        with host_helper.ssh_to_host(nova_helper.get_vm_host(vm_test)) as host_ssh:
            host_ssh.exec_cmd("vshell engine-stats-clear", fail_ok=False)
            host_ssh.exec_cmd("vshell port-stats-clear", fail_ok=False)
            host_ssh.exec_cmd("vshell interface-stats-clear", fail_ok=False)
            time.sleep(60)
            host_ssh.exec_cmd("vshell engine-stats-list", fail_ok=False)
            host_ssh.exec_cmd("vshell port-stats-list", fail_ok=False)
            host_ssh.exec_cmd("vshell interface-stats-list", fail_ok=False)

        LOG.tc_step("Verifying PHB policies enforced")
        assert not fail, "framerates are not properly distributed by PHB weights after max. framerate reached"


@mark.parametrize('vm_type', [
    'virtio',
    'avp',
    'dpdk',
])
def test_jumbo_frames(vm_type, ixia_supported, update_network_quotas):
    """
    Verify jumbo frames processed correctly

    Test Steps:
        - Launch a pair of test VMs
        - Setup routing with MTU fetched from VMs' tenant network
        - Configure traffic frameSize
        - Start traffic and verify loss

    Test Teardown:
        - Delete vms, volumes, flavors
    """
    for tenant in [Tenant.get_primary(), Tenant.get_secondary()]:
        tenant_net = network_helper.get_tenant_net_id(auth_info=tenant)
        if network_helper.get_net_info(tenant_net, field='provider:network_type') != 'vlan':
            skip("Tenant {}'s providernet is not on vlan".format(tenant['tenant']))

    LOG.tc_step("Launch a pair of test VMs")
    vms, nics = vm_helper.launch_vms(
        vm_type=vm_type, count=1, ping_vms=True, auth_info=Tenant.get_primary())
    vm_test = vms[0]
    tenant_net = nics[1]['net-id']
    providernet = network_helper.get_net_info(tenant_net, field='provider:physical_network')
    vm_test_mtu = int(network_helper.get_providernets(name=providernet, rtn_val='mtu')[0])

    vms, nics = vm_helper.launch_vms(
        vm_type=vm_type, count=1, ping_vms=True, auth_info=Tenant.get_secondary())
    vm_observer = vms[0]
    tenant_net = nics[1]['net-id']
    providernet = network_helper.get_net_info(tenant_net, field='provider:physical_network')
    vm_observer_mtu = int(network_helper.get_providernets(name=providernet, rtn_val='mtu')[0])

    if vm_test_mtu != vm_observer_mtu:
        LOG.warning("Mismatched MTUs for data network(s) launched for VMs, taking the smaller one")
    mtu = min(vm_test_mtu, vm_observer_mtu)

    LOG.tc_step("Configuring VMs with MTU={}".format(mtu))
    if vm_type == 'virtio' or vm_type == 'avp':
        vm_helper.setup_kernel_routing(vm_test)
        vm_helper.setup_kernel_routing(vm_observer)
    elif vm_type == 'dpdk' or vm_type == 'vhost' or vm_type == 'vswitch':
        vm_helper.setup_avr_routing(vm_test, vm_type=vm_type, mtu=mtu)
        vm_helper.setup_avr_routing(vm_observer, vm_type=vm_type, mtu=mtu)

    vm_helper.route_vm_pair(vm_test, vm_observer)

    for flow_mtu in [1500, 3000, 9216]:
        with vm_helper.traffic_between_vms(
                [(vm_test, vm_observer)],
                fps=1000, bidirectional=True, mtu=flow_mtu, start_traffic=False) as session:

            LOG.tc_step("Configure traffic frameSize to {}".format(flow_mtu))
            for trafficItem in session.getList(session.getRoot()+'/traffic', 'trafficItem'):
                configElement = session.getList(trafficItem, 'configElement')[0]
                session.configure(configElement+'/frameSize', fixedSize=flow_mtu, type='fixed')

            LOG.tc_step("Start traffic and verify loss")
            session.traffic_start()
            time.sleep(10)

            loss = int(float(session.get_statistics('traffic item statistics', fail_ok=False)[0]['Loss %']))
            LOG.info("Observed Loss %: {}".format(loss))

            if mtu < flow_mtu:
                assert loss >= 99, "expected loss when sending frame > provider_mtu"
            else:
                assert loss <= 1, "expected no loss when sending frame <= provider_mtu"
