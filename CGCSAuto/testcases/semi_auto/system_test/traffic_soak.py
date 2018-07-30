import ipaddress
from utils import cli, table_parser
from utils.tis_log import LOG
from consts.auth import HostLinuxCreds, Tenant
from utils.clients.ssh import ControllerClient
from keywords import nova_helper, vm_helper, heat_helper,system_test_helper, ixia_helper
from contextlib import ExitStack
from consts.filepaths import TiSPath, IxiaPath


def traffic_with_preset_configs(ixncfg, ixia_session=None):
    with ExitStack() as stack:
        if ixia_session is None:
            LOG.info("ixia_session not supplied, creating")
            from keywords import ixia_helper
            ixia_session = ixia_helper.IxiaSession()
            ixia_session.connect()
            stack.callback(ixia_session.disconnect)

        ixia_session.load_config(ixncfg)

        subnet_table = table_parser.table(cli.neutron('subnet-list', auth_info=Tenant.ADMIN))
        cidrs = list(map(ipaddress.ip_network, table_parser.get_column(subnet_table, 'cidr')))
        for vport in ixia_session.getList(ixia_session.getRoot(), 'vport'):
            for interface in ixia_session.getList(vport, 'interface'):
                if ixia_session.testAttributes(interface, enabled='true'):
                    ipv4_interface = ixia_session.getList(interface, 'ipv4')[0]
                    gw = ipaddress.ip_address(ixia_session.getAttribute(ipv4_interface, 'gateway'))
                    vlan_interface = ixia_session.getList(interface, 'vlan')[0]
                    for cidr in cidrs:
                        if gw in cidr:
                            subnet_id = table_parser.get_values(subnet_table, 'id', cidr=cidr)[0]
                            table = table_parser.table(cli.neutron('subnet-show', subnet_id, auth_info=Tenant.ADMIN))
                            seg_id = table_parser.get_value_two_col_table(table, "wrs-provider:segmentation_id")
                            ixia_session.configure(vlan_interface, vlanEnable=True, vlanId=str(seg_id))
                            LOG.info("vport {} interface {} gw {} vlan updated to {}".format(vport, interface, gw,
                                                                                             seg_id))


def test_launch_vms_for_traffic():
    stack1 = "/home/wrsroot/lab_setup-tenant1-resources.yaml"
    stack1_name = "lab_setup-tenant1-resources"
    stack2 = "/home/wrsroot/lab_setup-tenant2-resources.yaml"
    stack2_name = "lab_setup-tenant2-resources"
    script_name = "/home/wrsroot/create_resource_stacks.sh"

    con_ssh = ControllerClient.get_active_controller()
    if con_ssh.file_exists(file_path=script_name):
        cmd1 = 'chmod 755 ' + script_name
        con_ssh.exec_cmd(cmd1)
        con_ssh.exec_cmd(script_name, fail_ok=False)
    # may be better to delete all tenant stacks if any
    stack_params = '-f {} {}'.format(stack1, stack1_name)
    heat_helper.create_stack(stack_name=stack1_name, params_string=stack_params, auth_info=Tenant.TENANT1, timeout=1000,
                             cleanup=None)
    stack_params = '-f {} {}'.format(stack2, stack2_name)
    heat_helper.create_stack(stack_name=stack2_name, params_string=stack_params, auth_info=Tenant.TENANT2,timeout=1000,
                             cleanup=None)
    LOG.info("Checking all VMs are in active state")
    vms= system_test_helper.get_all_vms()
    vm_helper.wait_for_vms_values(vms=vms, fail_ok=False)

    ixia_session = ixia_helper.IxiaSession()
    ixia_session.connect()

    traffic_with_preset_configs(IxiaPath.WCP35_60_Traffic, ixia_session=ixia_session)