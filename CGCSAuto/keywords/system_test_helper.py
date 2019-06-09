import time
import ipaddress
from contextlib import ExitStack

from pytest import skip

from utils import cli, table_parser
from utils.tis_log import LOG
from utils.multi_thread import MThread
from utils.clients.ssh import ControllerClient, NATBoxClient
from consts.auth import HostLinuxCreds, Tenant
from consts.cgcs import GuestImages
from consts.filepaths import TiSPath, HeatTemplate, TestServerPath
from consts.timeout import HostTimeout, VMTimeout
from keywords import vm_helper, heat_helper, host_helper, html_helper, system_helper, vlm_helper, network_helper


def get_all_vms():
    """

    :return:  list of all VMs in the system
    """
    # Getting the vms on each compute node
    vms_by_compute_dic = vm_helper.get_vms_per_host()
    vms_to_check = vms_by_compute_dic.values()
    # compute_to_lock = []
    # vms_to_check = []
    #
    # for k, v in vms_by_compute_dic.items():
    #     if len(v) >= 5:
    #         compute_to_lock.append(k)
    #         vms_to_check.append(v)

    # Making a merged list from list of lists
    vms = [y for x in vms_to_check for y in x]
    return vms


def check_for_diffs_in_vm_status(first_dict, second_dict):
    """

    Args:
        first_dict (dict):
        second_dict (dict):

    Returns:
        (0, {}), if dictionaries are identical.
        (1, {vm_id:info, vm_id:info, ...}), if vm status changed between the two dictionaries
        (2, info), if the number of vm_ids change or the same vm_id is not found in both dictionaries

    """
    first_dict_keys = sorted(first_dict.keys())
    second_dict_keys = sorted(second_dict.keys())
    if first_dict_keys != second_dict_keys:
        return 2, "Both arguments do not contain the same keys in the dictionaries. Details: First vm_ids:{}, " \
                  "Second vm_ids:{}.".format(first_dict_keys, second_dict_keys)

    unstable_vms = {}
    for vm_id in first_dict_keys:
        if first_dict[vm_id] != second_dict[vm_id]:
            unstable_vms[vm_id] = "Previous VM status: {}. Current VM status: {}.".format(first_dict[vm_id],
                                                                                          second_dict[vm_id])
    if unstable_vms:
        return 1, unstable_vms
    else:
        return 0, unstable_vms


def _get_large_heat(con_ssh=None, heat_template='system'):
    """
    copy the heat templates to TiS server.

    Args:
        con_ssh (SSHClient):

    Returns (str): TiS file path of the heat template

    """
    file_dir = TiSPath.CUSTOM_HEAT_TEMPLATES
    file_name = HeatTemplate.SYSTEM_TEST_HEAT

    if heat_template is 'patch':
        file_name = HeatTemplate.LARGE_HEAT

    file_path = file_dir + file_name
    source_file = TestServerPath.CUSTOM_HEAT_TEMPLATES + file_name

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    LOG.info('Check if file already exists on TiS')
    if con_ssh.file_exists(file_path=file_path):
        LOG.info('dest path {} already exists. Return existing path'.format(file_path))
        return file_path

    with host_helper.ssh_to_test_server() as ssh_to_server:
        ssh_to_server.rsync(source_file, html_helper.get_ip_addr(), file_dir, dest_user=HostLinuxCreds.get_user(),
                            dest_password=HostLinuxCreds.get_password(), timeout=1200)
    return file_path


def launch_heat_stack():
    """
    Launch the upgrade heat stacks on TiS server.
    It will get the heat template tp TiS
    check if the heat stack is already there if not it will create the heat stacks

    Args:
    Returns (code): 0/1 pass/fail

    """
    # TODO: Update this to use a different stack for labs with only 1 or 2 hypervisors.
    # check if the heat stack is already launched
    stack_id = heat_helper.get_stacks(name=HeatTemplate.SYSTEM_TEST_HEAT_NAME)

    if stack_id:
        LOG.tc_step("Stack is already there")
        return

    # make sure heat templates are there in Tis
    _get_large_heat()

    file_dir = TiSPath.CUSTOM_HEAT_TEMPLATES
    file_name = HeatTemplate.SYSTEM_TEST_HEAT + "/" + HeatTemplate.SYSTEM_TEST_HEAT_NAME
    heat_template_file = file_dir + file_name + "/"

    pre_req_stack_name = "pre_req"
    stack_id_pre_req = heat_helper.get_stacks(name=pre_req_stack_name, auth_info=Tenant.get('admin'))
    if not stack_id_pre_req:
        LOG.tc_step("Creating pre-request heat stack to create images and flavors")
        default_guest_img = GuestImages.IMAGE_FILES[GuestImages.DEFAULT['guest']][2]
        image_file_path = "file://{}/{}".format(GuestImages.DEFAULT['image_dir'], default_guest_img)
        pre_req_template_path = heat_template_file + "pre_req.yaml"

        LOG.info("Creating heat stack for pre-req, images and flavors")
        heat_helper.create_stack(stack_name=pre_req_stack_name, template=pre_req_template_path,
                                 parameters={'LOCATION': image_file_path},
                                 auth_info=Tenant.get('admin'), cleanup=None)

    keypair_stack_name = 'Tenant1_Keypair'
    stack_id_key_pair = heat_helper.get_stacks(name=keypair_stack_name)
    if not stack_id_key_pair:
        LOG.tc_step("Creating Tenant key via heat stack")
        keypair_template = 'Tenant1_Keypair.yaml'
        keypair_template = '{}/{}'.format(heat_template_file, keypair_template)
        heat_helper.create_stack(stack_name=keypair_stack_name, template=keypair_template, cleanup=None)

    # Now create the large-stack
    LOG.tc_step("Creating heat stack to launch networks, ports, volumes, and vms")
    large_heat_template = heat_template_file + "/templates/rnc/" + "rnc_heat.yaml"
    env_file = heat_template_file + "/templates/rnc/" + "rnc_heat.env"
    heat_helper.create_stack(stack_name=HeatTemplate.SYSTEM_TEST_HEAT_NAME, template=large_heat_template,
                             environments=env_file, timeout=1800, cleanup=None)


def sys_lock_unlock_hosts(number_of_hosts_to_lock):
    """
        This is to test the evacuation of vms due to compute lock/unlock
    :return:
    """
    # identify a host with atleast 5 vms
    vms_by_compute_dic = vm_helper.get_vms_per_host()
    compute_to_lock = []
    vms_to_check = []
    hosts_threads = []
    timeout = 1000

    for k, v in vms_by_compute_dic.items():
        if len(v) >= 5:
            compute_to_lock.append(k)
            vms_to_check.append(v)

    if compute_to_lock is None:
        skip("There are no compute with 5 or moer vms")

    if len(compute_to_lock) > number_of_hosts_to_lock:
        compute_to_lock = compute_to_lock[0:number_of_hosts_to_lock]
        vms_to_check = vms_to_check[0:number_of_hosts_to_lock]
    else:
        LOG.warning("There are only {} computes available with more than 5 vms ".format(len(compute_to_lock)))

    for host in compute_to_lock:
        new_thread = MThread(host_helper.lock_host, host)
        new_thread.start_thread(timeout=timeout+30)
        hosts_threads.append(new_thread)

    for host_thr in hosts_threads:
        host_thr.wait_for_thread_end()

    LOG.tc_step("Verify lock succeeded and vms still in good state")
    for vm_list in vms_to_check:
        vm_helper.wait_for_vms_values(vms=vm_list, fail_ok=False)

    for host, vms in zip(compute_to_lock, vms_to_check):
        for vm in vms:
            vm_host = vm_helper.get_vm_host(vm_id=vm)
            assert vm_host != host, "VM is still on {} after lock".format(host)
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm, timeout=VMTimeout.DHCP_RETRY)

    hosts_threads = []
    for host in compute_to_lock:
        new_thread = MThread(host_helper.unlock_host, host)
        new_thread.start_thread(timeout=timeout+30)
        hosts_threads.append(new_thread)

    for host_thr in hosts_threads:
        host_thr.wait_for_thread_end()


def sys_evacuate_from_hosts(number_of_hosts_to_evac):
    """
        This is to test the evacuation of vms due to compute lock/unlock
    :return:
    """
    # identify a host with atleast 5 vms
    vms_by_compute_dic = vm_helper.get_vms_per_host()
    computes_to_reboot = []
    vms_to_check = []
    hosts_threads = []
    timeout = 1000

    for k, v in vms_by_compute_dic.items():
        if len(v) >= 5:
            computes_to_reboot.append(k)
            vms_to_check.append(v)

    if computes_to_reboot is None:
        skip("There are no compute with 5 or more vms")

    if len(computes_to_reboot) > number_of_hosts_to_evac:
        computes_to_reboot = computes_to_reboot[0:number_of_hosts_to_evac]
        vms_to_check = vms_to_check[0:number_of_hosts_to_evac]
    else:
        LOG.warning("There are only {} computes available with more than 5 vms ".format(len(computes_to_reboot)))

    for host, vms in zip(computes_to_reboot, vms_to_check):
        new_thread = MThread(vm_helper.evacuate_vms, host, vms, vlm=False)
        new_thread.start_thread(timeout=timeout+30)
        hosts_threads.append(new_thread)

    for host_thr in hosts_threads:
        host_thr.wait_for_thread_end()

    LOG.tc_step("Verify reboot succeeded and vms still in good state")
    for vm_list in vms_to_check:
        vm_helper.wait_for_vms_values(vms=vm_list, fail_ok=False)

    for host, vms in zip(computes_to_reboot, vms_to_check):
        for vm in vms:
            vm_host = vm_helper.get_vm_host(vm_id=vm)
            assert vm_host != host, "VM is still on {} after lock".format(host)
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm, timeout=VMTimeout.DHCP_RETRY)


def sys_reboot_storage():
    """
    This is to identify the storage nodes and turn them off and on via vlm
    :return:
    """
    controllers, computes, storages = system_helper.get_hosts_per_personality(rtn_tuple=True)

    LOG.info("Online or Available hosts before power-off: {}".format(storages))
    LOG.tc_step("Powering off hosts in multi-processes to simulate power outage: {}".format(storages))
    try:
        vlm_helper.power_off_hosts_simultaneously(storages)
    finally:
        LOG.tc_step("Wait for 60 seconds and power on hosts: {}".format(storages))
        time.sleep(60)
        LOG.info("Hosts to check after power-on: {}".format(storages))
        vlm_helper.power_on_hosts(storages, reserve=False, reconnect_timeout=HostTimeout.REBOOT + HostTimeout.REBOOT,
                                  hosts_to_check=storages)

    LOG.tc_step("Check vms status after storage nodes reboot")
    vms = get_all_vms()
    vm_helper.wait_for_vms_values(vms, fail_ok=False, timeout=600)

    for vm in vms:
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm)


def launch_lab_setup_tenants_vms():
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

    stack_id_t1 = heat_helper.get_stacks(name=stack1_name, auth_info=Tenant.TENANT1)
    # may be better to delete all tenant stacks if any
    if not stack_id_t1:
        heat_helper.create_stack(stack_name=stack1_name, template=stack1, auth_info=Tenant.TENANT1,
                                 timeout=1000, cleanup=None)
    stack_id_t2 = heat_helper.get_stacks(name=stack2_name, auth_info=Tenant.TENANT2)
    if not stack_id_t2:
        heat_helper.create_stack(stack_name=stack2_name, template=stack2, auth_info=Tenant.TENANT2,
                                 timeout=1000, cleanup=None)

    LOG.info("Checking all VMs are in active state")
    vms = get_all_vms()
    vm_helper.wait_for_vms_values(vms=vms, fail_ok=False)


def delete_lab_setup_tenants_vms():
    stack1_name = "lab_setup-tenant1-resources"
    stack2_name = "lab_setup-tenant2-resources"

    stack_id_t1 = heat_helper.get_stacks(name=stack1_name, auth_info=Tenant.TENANT1)
    # may be better to delete all tenant stacks if any
    if stack_id_t1:
        heat_helper.delete_stack(stack=stack1_name, auth_info=Tenant.TENANT1)

    stack_id_t2 = heat_helper.get_stacks(name=stack2_name, auth_info=Tenant.TENANT2)
    if stack_id_t2:
        heat_helper.delete_stack(stack=stack2_name, auth_info=Tenant.TENANT2)

    LOG.info("Checking all VMs are Deleted")
    vms = get_all_vms()
    assert len(vms) == 0, "Not all vms are deleted after heat stacks removal"


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
                                cli.openstack('network show', net_id, auth_info=Tenant.get('admin')))
                            seg_id = table_parser.get_value_two_col_table(table, "provider:segmentation_id")
                            ixia_session.configure(vlan_interface, vlanEnable=True, vlanId=str(seg_id))
                            LOG.info("vport {} interface {} gw {} vlan updated to {}".format(vport, interface, gw,
                                                                                             seg_id))


def sys_reboot_standby(number_of_times=1):
    """
    This is to identify the storage nodes and turn them off and on via vlm
    :return:
    """
    timeout = VMTimeout.DHCP_RETRY if system_helper.is_aio_system() else VMTimeout.PING_VM
    for i in range(0, number_of_times):
        active, standby = system_helper.get_active_standby_controllers()
        LOG.tc_step("Doing iteration of {} of total iteration {}".format(i, number_of_times))
        LOG.tc_step("'sudo reboot -f' from {}".format(standby))
        host_helper.reboot_hosts(hostnames=standby)

        LOG.tc_step("Check vms status after stanby controller reboot")
        vms = get_all_vms()
        vm_helper.wait_for_vms_values(vms, fail_ok=False, timeout=600)

        for vm in vms:
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm, timeout=timeout)


def sys_controlled_swact(number_of_times=1):
    """
    This is to identify the storage nodes and turn them off and on via vlm
    :return:
    """
    for i in range(0, number_of_times):
        active, standby = system_helper.get_active_standby_controllers()
        LOG.tc_step("Doing iteration of {} of total iteration {}".format(i, number_of_times))
        LOG.tc_step("'sudo reboot -f' from {}".format(standby))
        host_helper.swact_host(hostname=active)

        LOG.tc_step("Check vms status after controller swact")
        vms = get_all_vms()
        vm_helper.wait_for_vms_values(vms, fail_ok=False, timeout=600)

        for vm in vms:
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm)


def sys_uncontrolled_swact(number_of_times=1):
    """
    This is to identify the storage nodes and turn them off and on via vlm
    :return:
    """
    for i in range(0, number_of_times):
        active, standby = system_helper.get_active_standby_controllers()
        LOG.tc_step("Doing iteration of {} of total iteration {}".format(i, number_of_times))
        LOG.tc_step("'sudo reboot -f' from {}".format(standby))
        host_helper.reboot_hosts(hostnames=active)

        LOG.tc_step("Check vms status after controller swact")
        vms = get_all_vms()
        vm_helper.wait_for_vms_values(vms, fail_ok=False, timeout=600)

        for vm in vms:
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm)


def sys_lock_unlock_standby(number_of_times=1):
    """
    This is to identify the storage nodes and turn them off and on via vlm
    :return:
    """
    timeout = VMTimeout.DHCP_RETRY if system_helper.is_aio_system() else VMTimeout.PING_VM
    for i in range(0, number_of_times):
        active, standby = system_helper.get_active_standby_controllers()
        LOG.tc_step("Doing iteration of {} of total iteration {}".format(i, number_of_times))
        LOG.tc_step("'sudo reboot -f' from {}".format(standby))
        host_helper.lock_host(host=standby)

        LOG.tc_step("Check vms status after locking standby")
        vms = get_all_vms()
        vm_helper.wait_for_vms_values(vms, fail_ok=False, timeout=600)

        for vm in vms:
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm, timeout=timeout)

        host_helper.unlock_host(host=standby)
        vms = get_all_vms()
        vm_helper.wait_for_vms_values(vms, fail_ok=False, timeout=600)

        for vm in vms:
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm)


def ping_all_vms_from_nat_box():
    """

    :return:
    """
    natbox_client = NATBoxClient.get_natbox_client()
    vms = get_all_vms()
    ips_list = network_helper.get_mgmt_ips_for_vms(vms=vms)
    timeout = 1000
    vm_threads = []
    for vm in ips_list:
        new_thread = MThread(network_helper.ping_server(vm, natbox_client))
        new_thread.start_thread(timeout=timeout+30)
        vm_threads.append(new_thread)
        time.sleep(5)

    for vm_thr in vm_threads:
        vm_thr.wait_for_thread_end()

    # param = ','.join(map(str, ips_list))
    # cmd1 = "cd /home/cgcs/bin"
    # cmd2 =  "python monitor.py --addresses " + param
    # code1, output1 = natbox_client.send(cmd=cmd1)
    # code, output = natbox_client.send(cmd=cmd2)
    # output = natbox_client.cmd_output
    # pattern = str(len(ips_list))+ "/" + str(len(ips_list))
    # pattern_to_look = re.compile(pattern=pattern)
    # if not pattern_to_look.findall(output):
    #     return False

    return True
