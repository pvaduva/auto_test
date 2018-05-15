from pytest import fixture, skip
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, heat_helper, network_helper
from consts.filepaths import HeatTemplate
from consts.auth import Tenant
from consts.cgcs import GuestImages, HeatStackStatus, HEAT_CUSTOM_TEMPLATES
from consts.proj_vars import ProjVar


@fixture(scope='module', autouse=True)
def adjust_quota():
    """
    This is to adjust the quota
    return: code 0/1
    """
    network_helper.update_quotas(network=100)
    vm_helper.ensure_vms_quotas(cores_num=100, vols_num=100, vms_num=100)


@fixture(scope='module')
def get_large_heat():
    """
    copy the heat templates to TiS server.

    Args:
        cli_client (SSHClient):

    Returns (str): TiS file path of the heat template

    """
    file_name = HeatTemplate.LARGE_HEAT
    file_path = heat_helper.get_custom_heat_files(file_name=file_name)
    return file_path


def launch_heat_stack():
    """
    Launch the upgrade heat stacks on TiS server.
    It will get the heat template tp TiS
    check if the heat stack is already there if not it will create the heat stacks

    Args:

    Returns (code): 0/1 pass/fail

    """

    # check if the heat stack is already launched
    stack_id = heat_helper.get_stacks(name=HeatTemplate.LARGE_HEAT_NAME)

    if stack_id:
        LOG.tc_step("Stack is already there")
        return 0

    # make sure heat templates are there in Tis
    get_large_heat()

    file_dir = ProjVar.get_var('USER_FILE_DIR')
    file_name = HeatTemplate.LARGE_HEAT
    heat_template_file = '{}/{}/{}'.format(file_dir, HEAT_CUSTOM_TEMPLATES, file_name)

    LOG.tc_step("Get the heat file name to use")

    LOG.tc_step("Creating pre-request heat stack to create images and flavors")
    default_guest_img = GuestImages.IMAGE_FILES[GuestImages.DEFAULT_GUEST][2]
    file_path = "file://{}/images/{}".format(file_dir, default_guest_img)
    template_path = '{}/pre_req.yaml'.format(heat_template_file)
    stack_name = "pre_req"
    params_string = '-f {} -P LOCATION={} {}'.format(template_path, file_path, stack_name)
    LOG.info("Creating heat stack for pre-req, images and flavors")
    code, msg = heat_helper.create_stack(stack_name=stack_name, params_string=params_string,
                                         auth_info=Tenant.ADMIN, cleanup=None)
    assert code == 0, "Failed to create heat stack"

    LOG.tc_step("Creating Tenant key via heat stack")

    heat_template = 'Tenant1_Keypair.yaml'
    heat_stack_name = 'Tenant1_Keypair'
    heat_template = '{}/{}'.format(heat_template_file, heat_template)
    params_string = '-f {} {}'.format(heat_template, heat_stack_name)
    LOG.tc_step("Creating heat stack for Tenant key")
    heat_helper.create_stack(stack_name=heat_stack_name, params_string=params_string, cleanup=None)

    # Now create the large-stack
    stack_template = heat_template_file + "rnc_heat.yaml"
    env_file = heat_template_file + "rnc_heat.env"
    params_string = '-e {} -f {} {}'.format(env_file, stack_template, HeatTemplate.LARGE_HEAT_NAME)
    LOG.tc_step("Creating heat stack to launch networks, ports, volumes, and vms")
    heat_helper.create_stack(stack_name=HeatTemplate.LARGE_HEAT_NAME, params_string=params_string, cleanup=None)

    return 0


def check_vm_hosts(vms, policy='affinity', best_effort=False):
    vm_hosts = []
    for vm in vms:
        LOG.info("Vm is {}".format(vm))
        vm_host = nova_helper.get_vm_host(vm_id=vm)
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


def test_heat_stack_update(con_ssh=None):
    """
    Update heat stack that was already launched.
    It checks if the heat stack is already launched if not it will launch  the heat stack.
    It will check the status of the heat stack to be in good state (create complete/update complete)
    It will update the heat stack

    Args:
        con_ssh (SSHClient):

    Returns (code): 0/1

    """
    file_dir = ProjVar.get_var('USER_FILE_DIR')
    file_name = HeatTemplate.LARGE_HEAT
    large_heat_dir = '{}/{}/{}'.format(file_dir, HEAT_CUSTOM_TEMPLATES, file_name)
    file_path = '{}/update_env.sh'.format(large_heat_dir)

    res = launch_heat_stack()
    assert res == 0, "Failed to create heat stack"

    heat_status = [HeatStackStatus.CREATE_COMPLETE, HeatStackStatus.UPDATE_COMPLETE]
    current_status = heat_helper.get_stack_status(stack_name=HeatTemplate.LARGE_HEAT_NAME)[0]

    if current_status not in heat_status:
        skip("Heat stack Status is not in create_complete or update_complete")

    # TODO remote_cli
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    LOG.info("Check if file already exists on TiS")
    if con_ssh.file_exists(file_path=file_path):
        cmd1 = 'chmod 755 ' + file_path
        con_ssh.exec_cmd(cmd1)
        con_ssh.exec_cmd(file_path, fail_ok=False)

    stack_template = '{}/rnc_heat.yaml'.format(large_heat_dir)
    env_file = '{}/rnc_heat.env'.format(large_heat_dir)
    params_string = '-e {} -f {} {}'.format(env_file, stack_template, HeatTemplate.LARGE_HEAT_NAME)
    LOG.tc_step("Updating heat stack")
    code, msg = heat_helper.update_stack(stack_name=HeatTemplate.LARGE_HEAT_NAME, params_string=params_string)

    assert code == 0, "Failed to update heat stack"

    return 1


def test_migrate_anti_affinity_vms():
    """
    cold-migrate and live-migrate vms from anti-affinity group
    It will check if the heat stack is launched already if not it will launche the stack
    find the vms in anti-affinity group and will do cold and live migration
    TO_DO: you can make it work for best_effort by checking the server-group meta-data, now we only care about
     best-effort false.

    Returns (code): 0/1

    """
    # First make sure heat stack is there:
    result = launch_heat_stack()
    assert result == 0, "Failed to update heat stack"

    storage_backing, hosts = nova_helper.get_storage_backing_with_max_hosts()

    if len(hosts) < 3:
        skip("Not enough compute hosts to support anti-affinity")

    server_group_ids = nova_helper.get_server_groups()
    if not server_group_ids:
        skip("There are no server groups configured in the system")

    members = []
    for server_grp_id in server_group_ids:
        policy = nova_helper.get_server_group_info(group_id=server_grp_id, header='Policies')
        LOG.info("Policy is {}".format(policy))
        if str(policy).find('anti-affinity'):
            members.extend(nova_helper.get_server_group_info(group_id=server_grp_id, header='Members'))
            if members is not None:
                break

    if not members:
        skip("There are no vms in the server group")

    check_vm_hosts(vms=members, policy='anti_affinity')

    for vm_id in members:
        vm_helper.wait_for_vm_status(vm_id=vm_id, check_interval=10)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)
        vm_helper.live_migrate_vm(vm_id=vm_id)
        vm_helper.cold_migrate_vm(vm_id=vm_id)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)

    return 0
