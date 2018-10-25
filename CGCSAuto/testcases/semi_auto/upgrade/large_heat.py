from pytest import fixture, skip
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, heat_helper, host_helper, html_helper, network_helper
from consts.filepaths import TiSPath, HeatTemplate, TestServerPath
from utils.clients.ssh import ControllerClient
from consts.auth import HostLinuxCreds, Tenant
from consts.cgcs import GuestImages, HeatStackStatus
from consts.proj_vars import ProjVar


@fixture(scope='function')
def check_alarms():
    pass


@fixture(scope='module', autouse=True)
def pre_check(request):
    """
    This is to adjust the quota
    return: code 0/1
    """
    hypervisors = host_helper.get_up_hypervisors()
    if len(hypervisors) < 3:
        skip('Large heat tests require 3+ hypervisors')

    # disable remote cli for these testcases
    remote_cli = ProjVar.get_var('REMOTE_CLI')
    if remote_cli:
        ProjVar.set_var(REMOTE_CLI=False)

        def revert():
            ProjVar.set_var(REMOTE_CLI=remote_cli)
        request.addfinalizer(revert)

    network_helper.update_quotas(network=100)
    vm_helper.ensure_vms_quotas(cores_num=100, vols_num=100, vms_num=100)

    def list_status():
        LOG.fixture_step("Listing heat resources and nova migrations")
        stacks = heat_helper.get_stacks(auth_info=Tenant.get('admin'))
        for stack in stacks:
            heat_helper.get_stack_resources(stack=stack, auth_info=Tenant.get('admin'))

        nova_helper.get_migration_list_table()
    request.addfinalizer(list_status)


def _get_large_heat(con_ssh=None):
    """
    copy the heat templates to TiS server.

    Args:
        con_ssh (SSHClient):

    Returns (str): TiS file path of the heat template

    """
    file_dir = TiSPath.CUSTOM_HEAT_TEMPLATES
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
    stack_id = heat_helper.get_stacks(name=HeatTemplate.LARGE_HEAT_NAME)

    if stack_id:
        LOG.tc_step("Stack is already there")
        return

    # make sure heat templates are there in Tis
    _get_large_heat()

    file_dir = TiSPath.CUSTOM_HEAT_TEMPLATES
    file_name = HeatTemplate.LARGE_HEAT
    heat_template_file = file_dir + file_name + "/"

    LOG.tc_step("Creating pre-request heat stack to create images and flavors")
    default_guest_img = GuestImages.IMAGE_FILES[GuestImages.DEFAULT_GUEST][2]
    image_file_path = "file://{}/{}".format(GuestImages.IMAGE_DIR, default_guest_img)
    pre_req_template_path = heat_template_file + "pre_req.yaml"
    pre_req_stack_name = "pre_req"
    pre_req_params = '-f {} -P LOCATION={} {}'.format(pre_req_template_path, image_file_path, pre_req_stack_name)
    LOG.info("Creating heat stack for pre-req, images and flavors")
    heat_helper.create_stack(stack_name=pre_req_stack_name, params_string=pre_req_params,
                             auth_info=Tenant.get('admin'), cleanup=None)

    LOG.tc_step("Creating Tenant key via heat stack")
    keypair_template = 'Tenant1_Keypair.yaml'
    keypair_stack_name = 'Tenant1_Keypair'
    keypair_template = '{}/{}'.format(heat_template_file, keypair_template)
    keypair_params = '-f {} {}'.format(keypair_template, keypair_stack_name)
    heat_helper.create_stack(stack_name=keypair_stack_name, params_string=keypair_params, cleanup=None)

    # Now create the large-stack
    LOG.tc_step("Creating heat stack to launch networks, ports, volumes, and vms")
    large_heat_template = heat_template_file + "rnc_heat.yaml"
    env_file = heat_template_file + "rnc_heat.env"
    large_heat_params = '-e {} -f {} {}'.format(env_file, large_heat_template, HeatTemplate.LARGE_HEAT_NAME)
    heat_helper.create_stack(stack_name=HeatTemplate.LARGE_HEAT_NAME, params_string=large_heat_params, cleanup=None)


def check_server_group_vms_hosts(server_grp_id):
    policies, metadata, members = nova_helper.get_server_group_info(group_id=server_grp_id,
                                                                    headers=('Policies', 'Metadata', 'Members'))
    vm_hosts = []
    if members:
        best_effort = str(metadata['wrs-sg:best_effort']).lower()
        best_effort = False if 'false' in best_effort else True
        vm_hosts = check_vm_hosts(vms=members, policy=policies[0], best_effort=best_effort)

    return vm_hosts


def check_vm_hosts(vms, policy='affinity', best_effort=False):
    LOG.tc_step("Check hosts for {} vms with best_effort={}".format(policy, best_effort))
    vm_hosts = []
    for vm in vms:
        vm_host = nova_helper.get_vm_host(vm_id=vm)
        LOG.info("Vm {} is hosted on: {}".format(vm, vm_host))
        vm_hosts.append(vm_host)

    vm_hosts = list(set(vm_hosts))
    if policy == 'affinity':
        if best_effort:
            return 1 == len(vm_hosts)
        assert 1 == len(vm_hosts), "VMs in affinity group are not on same host"

    else:
        if best_effort:
            return len(vms) == len(vm_hosts)
        assert len(vms) == len(vm_hosts), "VMs in anti_affinity group are not on different host"

    return vm_hosts


def test_heat_stack_update():
    """
    Update heat stack that was already launched.
    It checks if the heat stack is already launched if not it will launch  the heat stack.
    It will check the status of the heat stack to be in good state (create complete/update complete)
    It will update the heat stack
    """
    file_dir = TiSPath.CUSTOM_HEAT_TEMPLATES
    file_name = HeatTemplate.LARGE_HEAT
    file_path = file_dir + file_name + '/update_env.sh'

    launch_heat_stack()

    heat_status = [HeatStackStatus.CREATE_COMPLETE, HeatStackStatus.UPDATE_COMPLETE]
    current_status = heat_helper.get_stack_status(stack_name=HeatTemplate.LARGE_HEAT_NAME)[0]

    if current_status not in heat_status:
        skip("Heat stack Status is not in create_complete or update_complete")

    con_ssh = ControllerClient.get_active_controller()

    LOG.info("Check if file already exists on TiS")
    if con_ssh.file_exists(file_path=file_path):
        cmd1 = 'chmod 755 ' + file_path
        con_ssh.exec_cmd(cmd1)
        con_ssh.exec_cmd(file_path, fail_ok=False)

    stack_template = file_dir + file_name + '/rnc_heat.yaml'
    env_file = file_dir + file_name + '/rnc_heat.env'
    params_string = '-e {} -f {} {}'.format(env_file, stack_template, HeatTemplate.LARGE_HEAT_NAME)
    LOG.tc_step("Updating heat stack")
    heat_helper.update_stack(stack_name=HeatTemplate.LARGE_HEAT_NAME, params_string=params_string, fail_ok=False)


def test_migrate_anti_affinity_vms():
    """
    cold-migrate and live-migrate vms from anti-affinity group
    It will check if the heat stack is launched already if not it will launch the stack
    find the vms in anti-affinity group and will do cold and live migration

    """
    # First make sure heat stack is there:
    launch_heat_stack()

    srv_grps_info = nova_helper.get_server_groups_info(headers=('Policies', 'Metadata', 'Members'))
    vms = []
    for group in srv_grps_info:
        policies, metadata, members = srv_grps_info[group]
        if members and 'anti-affinity' in policies and metadata['wrs-sg:best_effort'] == 'false':
            vms = members
            break
    else:
        skip("There are no VMs in anti-affinity server group")

    check_vm_hosts(vms=vms, policy='anti_affinity')
    for vm_id in vms:
        vm_helper.wait_for_vm_status(vm_id=vm_id, check_interval=10)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)
        vm_helper.live_migrate_vm(vm_id=vm_id)
        vm_helper.cold_migrate_vm(vm_id=vm_id)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)

    check_vm_hosts(vms=vms, policy='anti_affinity')
