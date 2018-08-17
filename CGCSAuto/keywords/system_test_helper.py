import time
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, heat_helper, host_helper, html_helper, system_helper, vlm_helper
from consts.filepaths import TiSPath, HeatTemplate, TestServerPath
from utils.clients.ssh import ControllerClient
from consts.auth import HostLinuxCreds, Tenant
from consts.cgcs import GuestImages
from utils.multi_thread import MThread
from pytest import skip
from consts.timeout import HostTimeout


def get_all_vms():
    vms_by_compute_dic = nova_helper.get_vms_by_hypervisors()
    compute_to_lock = []
    vms_to_check = []

    for k, v in vms_by_compute_dic.items():
        if len(v) >= 5:
            compute_to_lock.append(k)
            vms_to_check.append(v)

    vms = [y for x in vms_to_check for y in x]
    return vms


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
        default_guest_img = GuestImages.IMAGE_FILES[GuestImages.DEFAULT_GUEST][2]
        image_file_path = "file://{}/{}".format(GuestImages.IMAGE_DIR, default_guest_img)
        pre_req_template_path = heat_template_file + "pre_req.yaml"

        pre_req_params = '-f {} -P LOCATION={} {}'.format(pre_req_template_path, image_file_path, pre_req_stack_name)
        LOG.info("Creating heat stack for pre-req, images and flavors")
        heat_helper.create_stack(stack_name=pre_req_stack_name, params_string=pre_req_params,
                             auth_info=Tenant.get('admin'), cleanup=None)

    keypair_stack_name = 'Tenant1_Keypair'
    stack_id_key_pair = heat_helper.get_stacks(name=keypair_stack_name)
    if not stack_id_key_pair:
        LOG.tc_step("Creating Tenant key via heat stack")
        keypair_template = 'Tenant1_Keypair.yaml'
        keypair_template = '{}/{}'.format(heat_template_file, keypair_template)
        keypair_params = '-f {} {}'.format(keypair_template, keypair_stack_name)
        heat_helper.create_stack(stack_name=keypair_stack_name, params_string=keypair_params, cleanup=None)

    # Now create the large-stack
    LOG.tc_step("Creating heat stack to launch networks, ports, volumes, and vms")
    large_heat_template = heat_template_file + "/templates/rnc/" + "rnc_heat.yaml"
    env_file = heat_template_file + "/templates/rnc/" + "rnc_heat.env"
    large_heat_params = '-e {} -f {} {}'.format(env_file, large_heat_template, HeatTemplate.SYSTEM_TEST_HEAT_NAME)
    heat_helper.create_stack(stack_name=HeatTemplate.SYSTEM_TEST_HEAT_NAME, params_string=large_heat_params,
                             timeout=1000, cleanup=None)


def sys_lock_unlock_hosts(number_of_hosts_to_lock):
    """
        This is to test the evacuation of vms due to compute lock/unlock
    :return:
    """
    # identify a host with atleast 5 vms
    vms_by_compute_dic = nova_helper.get_vms_by_hypervisors()
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

    for host,vms in zip(compute_to_lock , vms_to_check):
        for vm in vms:
            vm_host = nova_helper.get_vm_host(vm_id=vm)
            assert vm_host != host, "VM is still on {} after lock".format(host)
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm)

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
    vms_by_compute_dic = nova_helper.get_vms_by_hypervisors()
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
        new_thread = MThread(vm_helper.evacuate_vms,host, vms, vlm=False)
        new_thread.start_thread(timeout=timeout+30)
        hosts_threads.append(new_thread)

    for host_thr in hosts_threads:
        host_thr.wait_for_thread_end()

    LOG.tc_step("Verify reboot succeeded and vms still in good state")
    for vm_list in vms_to_check:
        vm_helper.wait_for_vms_values(vms=vm_list, fail_ok=False)

    for host,vms in zip(computes_to_reboot , vms_to_check):
        for vm in vms:
            vm_host = nova_helper.get_vm_host(vm_id=vm)
            assert vm_host != host, "VM is still on {} after lock".format(host)
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm)


def sys_reboot_storage():
    """
    This is to identify the storage nodes and turn them off and on via vlm
    :return:
    """
    controllers, computes, storages = system_helper.get_hosts_by_personality()
    #hosts_to_check = system_helper.get_hostnames(availability=['available', 'online'])

    LOG.info("Online or Available hosts before power-off: {}".format(storages))
    LOG.tc_step("Powering off hosts in multi-processes to simulate power outage: {}".format(storages))
    try:
        vlm_helper.power_off_hosts_simultaneously(storages)
    except:
        raise
    finally:
        LOG.tc_step("Wait for 60 seconds and power on hosts: {}".format(storages))
        time.sleep(60)
        LOG.info("Hosts to check after power-on: {}".format(storages))
        vlm_helper.power_on_hosts(storages, reserve=False, reconnect_timeout=HostTimeout.REBOOT + HostTimeout.REBOOT,
                                  hosts_to_check=storages)

    LOG.tc_step("Check vms are recovered after dead office recovery")
    vms = get_all_vms()
    vm_helper.wait_for_vms_values(vms, fail_ok=False, timeout=600)

    for vm in vms:
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm)