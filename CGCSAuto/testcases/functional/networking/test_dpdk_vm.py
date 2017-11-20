from pytest import mark

from utils.tis_log import LOG
from keywords import vm_helper, network_helper, nova_helper, common, host_helper
from testfixtures.fixture_resources import ResourceCleanup
from consts.cgcs import FlavorSpec
from consts.filepaths import TiSPath, UserData, TestServerPath
from utils.ssh import ControllerClient
from consts.proj_vars import ProjVar
from testfixtures.recover_hosts import HostsToRecover
from consts.cgcs import VMStatus


def _get_dpdk_user_data(con_ssh=None):
    """
    copy the cloud-config userdata to TiS server.
    This userdata adds wrsroot/li69nux user to guest

    Args:
        con_ssh (SSHClient):

    Returns (str): TiS filepath of the userdata

    """
    file_dir = TiSPath.USERDATA
    file_name = UserData.DPDK_USER_DATA
    file_path = file_dir + file_name

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()
    if con_ssh.file_exists(file_path=file_path):
        LOG.info('userdata {} already exists. Return existing path'.format(file_path))
        return file_path

    LOG.debug('Create userdata directory if not already exists')
    cmd = 'mkdir -p {}'.format(file_dir)
    con_ssh.exec_cmd(cmd, fail_ok=False)

    source_file = TestServerPath.USER_DATA + file_name
    tmp_file = ProjVar.get_var('TEMP_DIR') + file_name
    with open(tmp_file, mode='a') as f:
        f.write("#wrs-config\n")
        f.write("FUNCTIONS=hugepages,avr\n")

    common.scp_to_active_controller(source_path=tmp_file, dest_path=file_path, is_dir=False)

    return file_path


@mark.parametrize('vm_type', [
    'dpdk',
    'vhost'
])
def test_dpdk_vm(vm_type):
    """
    DPDK VM with nova operations,  and evacuation test cases

    Test Steps:
        - Create flavor for dpdk
        - Create a dpdk vm
        - Perform nova actions and verify connectivity
        - Perform evacuation

    Test Teardown:
        - Delete vms, ports, subnets, and networks created

    """

    if vm_type == 'vhost':
        vif_model = 'virtio'
    else:
        vif_model = 'avp'

    LOG.tc_step("Create a flavor with 2 vcpus and extra-spec for dpdk")
    flavor_id = nova_helper.create_flavor(vcpus=2, ram=1024, root_disk=2)[1]
    ResourceCleanup.add('flavor', flavor_id)
    extra_specs = {FlavorSpec.VCPU_MODEL: 'SandyBridge', FlavorSpec.CPU_POLICY: 'dedicated',
                   FlavorSpec.MEM_PAGE_SIZE: '2048'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    LOG.tc_step("Boot a VM with mgmt net and tenant net")
    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'}, {'net-id': tenant_net_id, 'vif-model': vif_model}]

    LOG.tc_step("Boot a vm with created ports")
    vm_id = vm_helper.boot_vm(name='dpdk-vm', nics=nics, flavor= flavor_id, user_data=_get_dpdk_user_data(),
                              cleanup='function')[1]

    for vm_actions in [['reboot'], ['pause', 'unpause'], ['suspend', 'resume'], ['live_migrate'], ['cold_migrate']]:

        LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm_id, vm_actions))
        for action in vm_actions:
            vm_helper.perform_action_on_vm(vm_id, action=action)

        LOG.tc_step("Ping vm from natbox")
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    vm_host = nova_helper.get_vm_host(vm_id)
    LOG.tc_step("Reboot VM host {}".format(vm_host))
    HostsToRecover.add(vm_host, scope='function')
    host_helper.reboot_hosts(vm_host, wait_for_reboot_finish=False)

    LOG.tc_step("Wait for vms to reach ERROR or REBUILD state with best effort")
    vm_helper.wait_for_vm_values(vm_id, fail_ok=True, timeout=120, status=[VMStatus.ERROR, VMStatus.REBUILD])

    LOG.tc_step("Check vms are in Active state and moved to other host after host reboot")
    vm_helper.wait_for_vm_values(vm_id, timeout=300, fail_ok=False, status=[VMStatus.ACTIVE])

    post_vm_host = nova_helper.get_vm_host(vm_id)
    assert vm_host != post_vm_host, "VM host did not change upon host reboot even though VM is in Active state."

    LOG.tc_step("Check VM still pingable from Natbox after evacuated to other host")
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
