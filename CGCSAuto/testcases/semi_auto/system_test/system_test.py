from pytest import fixture, mark, skip
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, heat_helper, host_helper, cinder_helper, network_helper, system_test_helper
from consts.filepaths import TiSPath, HeatTemplate, TestServerPath
from utils.clients.ssh import ControllerClient
from consts.auth import HostLinuxCreds, Tenant
from consts.cgcs import GuestImages, HeatStackStatus
from consts.proj_vars import ProjVar
from utils.multi_thread import MThread, Events
from testfixtures.vlm_fixtures import reserve_unreserve_all_hosts_module, unreserve_hosts_module


@fixture(scope='function')
def check_alarms():
    pass


@fixture(scope='module', autouse=True)
def pre_check(request):
    """
    This is to adjust the quota and to launch the heat stack
    return: code 0/1
    """
    hypervisors = host_helper.get_up_hypervisors()
    if len(hypervisors) < 3:
        skip('System trest heat tests require 3+ hypervisors')

    # disable remote cli for these testcases
    remote_cli = ProjVar.get_var('REMOTE_CLI')
    if remote_cli:
        ProjVar.set_var(REMOTE_CLI=False)

        def revert():
            ProjVar.set_var(REMOTE_CLI=remote_cli)
        request.addfinalizer(revert)
    network_helper.update_quotas(network=600)
    nova_helper.update_quotas(cores=1000, instances=1000, ram=7168000, server_groups=100, server_group_members=1000)
    cinder_helper.update_quotas(volumes=1000)
    network_helper.update_quotas(port=1000)
    #system_test_helper.launch_heat_stack()

    def list_status():
        LOG.fixture_step("Listing heat resources and nova migrations")
        stacks = heat_helper.get_stacks(auth_info=Tenant.ADMIN)
        for stack in stacks:
            heat_helper.get_stack_resources(stack=stack, auth_info=Tenant.ADMIN)

        stack_id = heat_helper.get_stacks(name=HeatTemplate.SYSTEM_TEST_HEAT_NAME)

        if stack_id:
            code, msg = heat_helper.delete_stack(stack_name=HeatTemplate.SYSTEM_TEST_HEAT_NAME)

        nova_helper.get_migration_list_table()
    request.addfinalizer(list_status)


def check_server_group_vms_hosts(server_grp_id):
    """
    This
    :param server_grp_id:
    :return:
    """
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


def _test_heat_stack_update():
    """
    Update heat stack that was already launched.
    It checks if the heat stack is already launched if not it will launch  the heat stack.
    It will check the status of the heat stack to be in good state (create complete/update complete)
    It will update the heat stack
    """

    # compile the file names and paths
    file_dir = TiSPath.CUSTOM_HEAT_TEMPLATES
    file_name = HeatTemplate.SYSTEM_TEST_HEAT + "/" + HeatTemplate.SYSTEM_TEST_HEAT_NAME
    heat_template_file = file_dir + file_name + "/"
    file_path = heat_template_file + "templates/update_env.sh"

    LOG.tc_step("Verify if the heat stack is already launch")
    system_test_helper.launch_heat_stack()

    heat_status = [HeatStackStatus.CREATE_COMPLETE, HeatStackStatus.UPDATE_COMPLETE]
    # get the current state of the heat stack
    current_status = heat_helper.get_stack_status(stack_name=HeatTemplate.SYSTEM_TEST_HEAT_NAME)[0]

    if current_status not in heat_status:
        skip("Heat stack Status is not in create_complete or update_complete")

    con_ssh = ControllerClient.get_active_controller()

    LOG.info("Check if file already exists on TiS")
    if con_ssh.file_exists(file_path=file_path):
        cmd1 = 'chmod 755 ' + file_path
        con_ssh.exec_cmd(cmd1)
        con_ssh.exec_cmd(file_path, fail_ok=False)

    stack_template = heat_template_file + "/templates/rnc/" + "rnc_heat.yaml"
    env_file = heat_template_file + "/templates/rnc/" + "rnc_heat.env"
    params_string = '-e {} -f {} {}'.format(env_file, stack_template, HeatTemplate.SYSTEM_TEST_HEAT_NAME)
    LOG.tc_step("Updating heat stack")
    heat_helper.update_stack(stack_name=HeatTemplate.SYSTEM_TEST_HEAT_NAME, params_string=params_string, timeout=1000,
                             fail_ok=False)


def _test_migrate_anti_affinity_vms_in_parallel():
    """
    cold-migrate and live-migrate vms from anti-affinity group
    It will check if the heat stack is launched already if not it will launch the stack
    find the vms in anti-affinity group and will do cold and live migration

    """
    # First make sure heat stack is there:
    system_test_helper.launch_heat_stack()

    srv_grps_info = nova_helper.get_server_groups_info(headers=('Policies', 'Metadata', 'Members'))
    vms = []
    for group in srv_grps_info:
        policies, metadata, members = srv_grps_info[group]
        if members and 'anti-affinity' in policies and metadata['wrs-sg:best_effort'] == 'false':
            if len(members) >= 10:
                vms= members[range(0,9)]
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


def _test_parallel_migration():
    """
    This is to test the parallel migration of the servers
    :return:
    """

@mark.p1
@mark.parametrize('number_of_hosts_to_lock', [
    1,
    3,
])
def test_sys_lock_unlock_hosts(number_of_hosts_to_lock):
    """
        This is to test the evacuation of vms due to compute lock/unlock
    :return:
    """
    # identify a host with atleast 5 vms

    system_test_helper.sys_lock_unlock_hosts(number_of_hosts_to_lock=number_of_hosts_to_lock)


@mark.p1
@mark.parametrize('number_of_hosts_to_evac', [
    1,
    3,
    5,
])
def _test_sys_evacuate_from_hosts(number_of_hosts_to_evac):
    """
        This is to test the evacuation of vms due to compute lock/unlock
    :return:
    """
    system_test_helper.sys_evacuate_from_hosts(number_of_hosts_to_evac=number_of_hosts_to_evac)


def _test_sys_storage_reboot(number_of_hosts_to_evac):
    """

    :param number_of_hosts_to_evac:
    :return:
    """
    system_test_helper.sys_reboot_storage()