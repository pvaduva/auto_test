from pytest import fixture, mark, skip
import random
from utils import table_parser
from utils.tis_log import LOG
from utils import cli

from consts.auth import Tenant
from keywords import host_helper, network_helper, common, vm_helper, nova_helper
from testfixtures.recover_hosts import HostsToRecover
from consts.cli_errs import NetworkingErr


def get_vshell_stats(ssh_client, rtn_val='packets-unicast'):
    """
    Get the stats from vshell for vxlan-endpoint-stats-list
    Args:
        ssh_client (str): ssh con handle
        rtn_val (str): Filter to use to parse packets

        Returns:
            list

    """

    LOG.info("Getting vshell vxlan-endpoint-stats-list")
    table_ = table_parser.table(ssh_client.exec_cmd('vshell vxlan-endpoint-stats-list', fail_ok=False)[1])
    packets = table_parser.get_values(table_, 'rtn_val', regex=True)
    return packets


@mark.parametrize('version', [
    4
])
def _test_vxlan_multicast( version):
    """
        Vxlan feature test cases

        Test Steps:
            - Make sure Vxlan provider net is configured only on Internal net
            - Find out a internal network that matches the vxlan mode and IP version
            - Use the mgmt-net and the internal net to create vms for tenant-1 and tenant-2
            - Make sure the vms are occupied on separate hosts
            - ssh to the compute where the vm is hosted to check the vshell stats
            - from second ping or ssh over the internal net


        Test Teardown:
            - Delete vms, volumes created

    """
    vxlan_provider_name = 'group0-data0b'
    providernets = network_helper.get_providernets(rtn_val='name', strict=True, type='vxlan')
    if not providernets or (len(providernets) > 1) or (vxlan_provider_name not in providernets):
        skip("Vxlan provider-net not configured or Vxlan provider-net configured on more than one provider net\
         or not configurd on internal net")


    # get the id of the providr net
    vxlan_provider_net_id = network_helper.get_providernets(rtn_val='id', strict=True, type='vxlan')
    #mgmt_net_id = network_helper.get_mgmt_net_id()
    vms_id=[]

    # here I want to get the Internal net that is on IPV4

    internal_net_ids = network_helper.get_internal_net_ids_on_vxlan_v4_v6(vxlan_provider_net_id=vxlan_provider_net_id,\
                                                                          ip_version=version,)
    if not internal_net_ids:
        skip("No networks found for ip version {} on the vxlan provider net".format(version))

    LOG.tc_step("Got Internal net ids {}" . format(internal_net_ids))

    primary_tenant = Tenant.get_primary()
    primary_tenant_name = common.get_tenant_name(primary_tenant)
    other_tenant = Tenant.TENANT2 if primary_tenant_name == 'tenant1' else Tenant.TENANT1
    vm_hosts = ['compute-0', 'compute-1']

    for auth_info, vm_host in zip([primary_tenant, other_tenant], vm_hosts):
        mgmt_net_id = network_helper.get_mgmt_net_id(auth_info=auth_info)
        nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
                {'net-id': internal_net_ids[0], 'vif-model': 'avp'}]
        vm_name = common.get_unique_name(name_str='vxlan')
        vms_id.append(vm_helper.boot_vm(name=vm_name, vm_host=vm_host, nics=nics, auth_info=auth_info)[1])
        #vms_id.append(vm_helper.boot_vm(name=vm_name, vm_host=vm_host, nics=nics, auth_info=auth_info, cleanup='function')[1])

    # make sure VMS are not in the same compute:
    if nova_helper.get_vm_host(vm_id=vms_id[0]) == nova_helper.get_vm_host(vm_id=vms_id[1]):
        vm_helper.cold_migrate_vm(vm_id=vms_id[0])

    ## ssh to compute
        ssh_compute = host_helper.ssh_to_host(nova_helper.get_vm_host(vm_id=vms_id[0]))
