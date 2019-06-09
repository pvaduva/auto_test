import time
import ipaddress
from contextlib import ExitStack

from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient
from utils import cli, table_parser
from consts.auth import Tenant
from consts.filepaths import IxiaPath
from keywords import vm_helper, heat_helper, system_test_helper, ixia_helper


def traffic_with_preset_configs(ixncfg, ixia_session=None):
    with ExitStack() as stack:
        if ixia_session is None:
            LOG.info("ixia_session not supplied, creating")
            from keywords import ixia_helper
            ixia_session = ixia_helper.IxiaSession()
            ixia_session.connect()
            stack.callback(ixia_session.disconnect)

        ixia_session.load_config(ixncfg)

        subnet_table = table_parser.table(cli.openstack('subnet list', auth_info=Tenant.get('admin'))[1])
        cidrs = list(map(ipaddress.ip_network, table_parser.get_column(subnet_table, 'Subnet')))
        for vport in ixia_session.getList(ixia_session.getRoot(), 'vport'):
            for interface in ixia_session.getList(vport, 'interface'):
                if ixia_session.testAttributes(interface, enabled='true'):
                    ipv4_interface = ixia_session.getList(interface, 'ipv4')[0]
                    gw = ipaddress.ip_address(ixia_session.getAttribute(ipv4_interface, 'gateway'))
                    vlan_interface = ixia_session.getList(interface, 'vlan')[0]
                    for cidr in cidrs:
                        if gw in cidr:
                            net_id = table_parser.get_values(subnet_table, 'Network', cidr=cidr)[0]
                            table = table_parser.table(
                                cli.openstack('network show', net_id, auth_info=Tenant.get('admin'))[1])
                            seg_id = table_parser.get_value_two_col_table(table, "provider:segmentation_id")
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
    heat_helper.create_stack(stack_name=stack1_name, template=stack1, auth_info=Tenant.TENANT1, timeout=1000,
                             cleanup=None)
    heat_helper.create_stack(stack_name=stack2_name, template=stack2, auth_info=Tenant.TENANT2, timeout=1000,
                             cleanup=None)
    LOG.info("Checking all VMs are in active state")
    vms = system_test_helper.get_all_vms()
    vm_helper.wait_for_vms_values(vms=vms, fail_ok=False)


def test_eight_hour_traffic_soak():
    system_test_helper.launch_lab_setup_tenants_vms()
    ixia_session = ixia_helper.IxiaSession()
    LOG.info("Connecting to Ixia")
    ixia_session.connect()
    #
    LOG.info("Loading ixia config file")
    system_test_helper.traffic_with_preset_configs(IxiaPath.WCP35_60_Traffic, ixia_session=ixia_session)
    LOG.info("Connecting to Ixia ports")
    ixia_session.connect_ports()
    ixia_session.traffic_regenerate()
    ixia_session.traffic_apply()
    LOG.info("Starting Ixia Traffic")
    ixia_session.traffic_start()
    time.sleep(120)
    LOG.info("Stopping Ixia Traffic")
    ixia_session.traffic_stop()
    frame_delta = ixia_session.get_frames_delta(stable=True)
    assert frame_delta == 0, "There is a frame delta detected during traffic soak"
    LOG.info("Frame delts is {}".format(frame_delta))
    ixia_session.disconnect(traffic_stop=True)
