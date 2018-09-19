import re
import time

from pytest import fixture

from consts.proj_vars import ProjVar
from consts.filepaths import TiSPath, HeatTemplate, TestServerPath, WRSROOT_HOME
from keywords import vm_helper, nova_helper, common, heat_helper, network_helper, system_helper
from testfixtures.fixture_resources import ResourceCleanup
from utils import exceptions
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG


@fixture(scope='module', autouse=True)
def prefix_remote_cli(request):
    if ProjVar.get_var('REMOTE_CLI'):
        ProjVar.set_var(REMOTE_CLI=False)
        ProjVar.set_var(USER_FILE_DIR=WRSROOT_HOME)

        def revert():
            ProjVar.set_var(REMOTE_CLI=True)
            ProjVar.set_var(USER_FILE_DIR=ProjVar.get_var('TEMP_DIR'))
        request.addfinalizer(revert)


def _get_stress_ng_heat(con_ssh=None):
    """
    copy the cloud-config userdata to TiS server.
    This userdata adds wrsroot/li69nux user to guest

    Args:
        con_ssh (SSHClient):

    Returns (str): TiS filepath of the userdata

    """
    file_dir = TiSPath.CUSTOM_HEAT_TEMPLATES
    file_name = HeatTemplate.STRESS_NG
    file_path = file_dir + file_name

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    if not con_ssh.file_exists(file_path=file_path):
        LOG.debug('Create userdata directory if not already exists')
        cmd = 'mkdir -p {}'.format(file_dir)
        con_ssh.exec_cmd(cmd, fail_ok=False)

        source_file = TestServerPath.CUSTOM_HEAT_TEMPLATES + file_name

        dest_path = common.scp_from_test_server_to_active_controller(source_path=source_file, dest_dir=file_dir,
                                                                     dest_name=file_name, con_ssh=con_ssh)

        if dest_path is None:
            raise exceptions.CommonError("Heat template file {} does not exist after download".format(file_path))

    # tenant nets names were hardcoded in heat file. They need to be updated when systems don't have those networks.
    # Update heat file if less than 3 tenant-nets configured.
    tenant_nets = network_helper.get_tenant_net_ids(rtn_val='name')
    net_count = len(tenant_nets)
    if net_count <= 3:
        LOG.info("Less than 3 tenant networks configured. Update heat template.")
        con_ssh.exec_cmd("sed -i 's/tenant2-net3/tenant2-net{}/g' {}".format(net_count-1, file_path))
        if net_count <= 2:
            con_ssh.exec_cmd("sed -i 's/tenant2-net2/tenant2-net{}/g' {}".format(net_count-1, file_path))
            if net_count <= 1:
                con_ssh.exec_cmd("sed -i 's/tenant2-net1/tenant2-net{}/g' {}".format(net_count-1, file_path))

    # update heat file for multi-region system
    from consts.proj_vars import ProjVar
    from consts.cgcs import MULTI_REGION_MAP
    region = ProjVar.get_var("REGION")
    if region != 'RegionOne' and region in MULTI_REGION_MAP:
        region_str = MULTI_REGION_MAP.get(region)
        con_ssh.exec_cmd("sed -i 's/tenant2-net/tenant2{}-net/g' {}".format(region_str, file_path))
        con_ssh.exec_cmd("sed -i 's/tenant2-mgmt-net/tenant2{}-mgmt-net/g' {}".format(region_str, file_path))

    if not system_helper.is_avs():
        con_ssh.exec_cmd("sed -i 's/avp/virtio/g' {}".format(file_path))
        
    return file_path


def wait_for_stress_ng(ssh_client):
    """
    Get the IP addr for given eth on the ssh client provided
    Args:
        ssh_client (SSHClient): usually a vm_ssh

    Returns (str): The first matching ipv4 addr for given eth. such as "30.0.0.2"

    """
    proc_name = 'stress-ng'
    end_time = time.time() + 800
    while time.time() < end_time:
        if proc_name in ssh_client.exec_cmd('ps -aef | grep -v grep | grep -v yum | grep stress-ng')[1]:
            output = ssh_client.exec_cmd('ps -aef | grep stress-ng')[1]
            if re.search('stress-ng', output):
                return 0
            else:
                time.sleep(30)
    return 1


def test_migration_auto_converge(no_simplex):
    """
    Auto converge a VM with stress-ng running

    Test Steps:
        - Create flavor
        - Create a heat stack (launch a vm with stress-ng)
        - Perform live-migration and verify connectivity

    Test Teardown:
        - Delete stacks,vm, flavors created

    """

    LOG.tc_step("Create a flavor with 2 vcpus")
    flavor_id = nova_helper.create_flavor(vcpus=2, ram=1024, root_disk=3)[1]
    ResourceCleanup.add('flavor', flavor_id)

    LOG.tc_step("Get the heat file name to use")
    heat_template = _get_stress_ng_heat()

    stack_name = vm_name = 'stress_ng'
    cmd_list = ['-f %s' % heat_template,
                "-P flavor=%s" % flavor_id,
                "-P name=%s" % vm_name,
                stack_name]
    params_string = ' '.join(cmd_list)

    LOG.tc_step("Creating heat stack")
    code, msg = heat_helper.create_stack(stack_name=stack_name, params_string=params_string)
    # add the heat stack name for deletion in teardown
    ResourceCleanup.add(resource_type='heat_stack', resource_id=stack_name)
    assert code == 0, "Failed to create heat stack"

    LOG.info("Verifying server creation via heat")
    vm_id = nova_helper.get_vm_id_from_name(vm_name='stress_ng', strict=False)

    assert vm_id, "Error:vm was not created by stack"
    LOG.info("Found VM %s", vm_id)

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)

    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        LOG.tc_step("Check for Stress-ng inside vm")
        assert 0 == wait_for_stress_ng(vm_ssh), " Stress-ng is not running"

    for vm_actions in [['live_migrate']]:

        LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm_id, vm_actions))
        for action in vm_actions:
            vm_helper.perform_action_on_vm(vm_id, action=action)

        LOG.tc_step("Ping vm from natbox")
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
