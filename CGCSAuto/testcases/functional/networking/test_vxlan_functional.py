from pytest import fixture, mark, skip

from utils import table_parser
from utils.tis_log import LOG
from consts.auth import Tenant
from keywords import host_helper, network_helper, common, vm_helper, nova_helper, keystone_helper, system_helper
from testfixtures.fixture_resources import ResourceCleanup


@fixture(scope='module', autouse=True)
def add_admin_role(request):

    if not system_helper.is_avs():
        skip("vshell commands unsupported by OVS")

    primary_tenant = Tenant.get_primary()
    other_tenant = Tenant.get_secondary()
    tenants = [primary_tenant, other_tenant]
    res = []
    for auth_info in tenants:
        code = keystone_helper.add_or_remove_role(add_=True, role='admin', user=auth_info.get('user'),
                                                  project=auth_info.get('tenant'))[0]
        res.append(code)

    def remove_admin_role():
        for i in range(len(res)):
            if res[i] != -1:
                auth_info_ = tenants[i]
                keystone_helper.add_or_remove_role(add_=False, role='admin', user=auth_info_.get('user'),
                                                   project=auth_info_.get('tenant'))

    request.addfinalizer(remove_admin_role)


def get_vxlan_endpoint_stats(compute, field='packets-unicast'):
    """
    Get the stats from vshell for vxlan-endpoint-stats-list
    Args:
        compute
        field (str): Filter to use to parse packets

        Returns:
            list

    """

    LOG.info("Getting vshell vxlan-endpoint-stats-list")
    with host_helper.ssh_to_host(compute) as host_ssh:
        table_ = table_parser.table(host_ssh.exec_cmd('vshell vxlan-endpoint-stats-list', fail_ok=False)[1])
        packets = table_parser.get_values(table_, field, regex=True)

    return packets


def clear_vxlan_endpoint_stats(compute):
    """
    Clear the vxlan-endpoint-stats
    Args:
        compute

        Returns:
            code

    """

    LOG.info("Clearing vshell vxlan-endpoint-stats-list")
    with host_helper.ssh_to_host(compute) as host_ssh:
        code = host_ssh.exec_cmd('vshell vxlan-endpoint-stats-clear', fail_ok=False)[0]

    return code


@mark.parametrize(('version', 'mode'), [
    (4, "dynamic"),
    (6, "dynamic"),
    (4, 'static'),
    (6, 'static')
])
def test_dynamic_vxlan_functional(version, mode):
    """
        Vxlan feature test cases

        Test Steps:
            - Make sure Vxlan provider net is configured only on Internal net
            - Find out a internal network that matches the vxlan mode and IP version
            - Use the mgmt-net and the internal net to create vms for tenant-1 and tenant-2
            - Make sure the vms are occupied on separate hosts achieved with host-aggregates
            - ssh to the compute where the vm is hosted to check the vshell stats
            - Ping from the vm and check the stats for known-vtep on the compute
            - Ping from the vm to a unknown IP and check compute for stats


        Test Teardown:
            - Delete vms, volumes created

    """
    vxlan_provider_name = 'group0-data0b'
    vif_model = 'avp'
    providernets = system_helper.get_data_networks(field='name', network_type='vxlan')
    if not providernets or (len(providernets) > 1) or (vxlan_provider_name not in providernets):
        skip("Vxlan provider-net not configured or Vxlan provider-net configured on more than one provider net\
         or not configurd on internal net")

    # get the id of the providr net
    vxlan_provider_net_id = system_helper.get_data_networks(field='id', type='vxlan')
    vm_ids = []

    # get 2 computes so we can create the aggregate and force vm-ccupancy
    computes = host_helper.get_up_hypervisors()

    if len(computes) < 2:
        skip(" Need at least 2 computes to run the Vxlan test cases")

    aggregate_name = 'vxlan'
    vxlan_computes = computes[0:2]

    # create aggregate with 2 computes
    ret_val = nova_helper.create_aggregate(name=aggregate_name, avail_zone=aggregate_name)[1]
    assert ret_val == aggregate_name, "Aggregate is not create as expected."
    ResourceCleanup.add('aggregate', aggregate_name)

    nova_helper.add_hosts_to_aggregate(aggregate=aggregate_name, hosts=vxlan_computes)

    for compute in computes:
        assert 0 == clear_vxlan_endpoint_stats(compute), "clear stats failed"

    LOG.tc_step("Getting Internal net ids.")
    internal_net_ids = network_helper.get_internal_net_ids_on_vxlan(vxlan_provider_net_id=vxlan_provider_net_id,
                                                                    ip_version=version, mode=mode)
    if not internal_net_ids:
        skip("No networks found for ip version {} on the vxlan provider net".format(version))

    LOG.tc_step("Creating vms for both tenants.")
    primary_tenant = Tenant.get_primary()
    other_tenant = Tenant.get_secondary()

    for auth_info, vm_host in zip([primary_tenant, other_tenant], vxlan_computes):
        mgmt_net_id = network_helper.get_mgmt_net_id(auth_info=auth_info)
        nics = [{'net-id': mgmt_net_id},
                {'net-id': internal_net_ids[0], 'vif-model': vif_model}]
        vm_name = common.get_unique_name(name_str='vxlan')
        vm_ids.append(vm_helper.boot_vm(name=vm_name, vm_host=vm_host, nics=nics, avail_zone=aggregate_name,
                                        auth_info=auth_info, cleanup='function')[1])

    # make sure VMS are not in the same compute, I don;t need it but just in case (double checking):
    if vm_helper.get_vm_host(vm_id=vm_ids[0]) == vm_helper.get_vm_host(vm_id=vm_ids[1]):
        vm_helper.cold_migrate_vm(vm_id=vm_ids[0])

    filter_known_vtep = 'packets-unicast'
    filter_stat_at_boot = 'packets-multicast'
    filter_unknown_vtep = 'packets-multicast'

    if mode is 'static':
        filter_stat_at_boot = 'packets-unicast'
        filter_unknown_vtep = 'packets-unicast'

    LOG.tc_step("Checking stats on computes after vms are launched.")
    for compute in computes:
        stats_after_boot_vm = get_vxlan_endpoint_stats(compute, field=filter_stat_at_boot)
        if len(stats_after_boot_vm) is 3:
            stats = int(stats_after_boot_vm[1]) + int(stats_after_boot_vm[2])
            LOG.info("Got the stats for packets {} after vm launched is {}".format(filter_stat_at_boot, stats))
        elif len(stats_after_boot_vm) is 2:
            stats = int(stats_after_boot_vm[1])
            LOG.info("Got the stats for packets {} after vm launched is {}".format(filter_stat_at_boot, stats))
        else:
            assert 0, "Failed to get stats from compute"
        assert 0 < int(stats), "stats are not incremented as expected"

    # clear stats
    LOG.tc_step("Clearing vxlan-endpoint-stats on computes: {}".format(computes))
    for compute in computes:
        assert 0 == clear_vxlan_endpoint_stats(compute), "clear stats failed"

    # Ping b/w vm over Internal nets and check stats, ping from 2nd vm
    LOG.tc_step("Ping between two vms over internal network")
    vm_helper.ping_vms_from_vm(to_vms=vm_ids[0], from_vm=vm_ids[1], net_types=['internal'])

    stats_after_ping = get_vxlan_endpoint_stats(computes[0], field=filter_known_vtep)
    if not stats_after_ping:
        assert "Compute stats are empty"

    LOG.tc_step("Checking stats on computes after vm ping over the internal net.")
    if len(stats_after_ping) is 3:
        stats_known_vtep = int(stats_after_ping[1]) + int(stats_after_ping[2])
        LOG.info("Got the stats for packets {} after ping {}".format(filter_known_vtep, stats_known_vtep))
    elif len(stats_after_ping) is 2:
        stats_known_vtep = int(stats_after_ping[1])
        LOG.info("Got the stats for packets {} after ping {}".format(filter_known_vtep, stats_known_vtep))
    else:
        assert 0, "Failed to get stats from compute"
    assert 0 < int(stats_known_vtep), "stats are not incremented as expected"

    # clear stats
    LOG.tc_step("Clearing vxlan-endpoint-stats on computes: {}".format(computes))
    for compute in computes:
        assert 0 == clear_vxlan_endpoint_stats(compute), "clear stats failed"

    # ping unknown IP over the internal net and check stats
    LOG.tc_step("Ping to an unknown IP from vms over internal network")
    unknown_ip = '10.10.10.30'
    with vm_helper.ssh_to_vm_from_natbox(vm_ids[1]) as vm2_ssh:
        LOG.tc_step("Ping unknown ip from guest")
        cmd = 'ping -I eth1 -c 5 {}'.format(unknown_ip)
        code, output = vm2_ssh.exec_cmd(cmd=cmd, expect_timeout=60)
        assert int(code) > 0, "Expected to see 100% ping failure"

    LOG.tc_step("Checking stats on computes after vm ping on unknown IP.")
    stats_after_ping_unknown_vtep = get_vxlan_endpoint_stats(computes[1], field=filter_unknown_vtep)
    if not stats_after_ping_unknown_vtep:
        assert 0, "Compute stats are empty"

    if len(stats_after_ping_unknown_vtep) is 3:
        stats_unknown_vtep = int(stats_after_ping_unknown_vtep[1]) + int(stats_after_ping_unknown_vtep[2])
        LOG.info("Got the stats for packets {} after ping unknown vtep {}".format(filter_unknown_vtep,
                                                                                  stats_unknown_vtep))
    elif len(stats_after_ping_unknown_vtep) is 2:
        stats_unknown_vtep = int(stats_after_ping_unknown_vtep[1])
        LOG.info("Got the stats for packets {} after ping uknown vtep {}".format(filter_unknown_vtep,
                                                                                 stats_unknown_vtep))
    else:
        assert 0, "Failed to get stats from compute"
    assert 0 < int(stats_unknown_vtep), "stats are not incremented as expected"
