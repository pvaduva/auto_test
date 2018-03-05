from pytest import mark, skip

from utils.tis_log import LOG
from keywords import vm_helper, network_helper, nova_helper, common, host_helper, glance_helper, cinder_helper
from testfixtures.fixture_resources import ResourceCleanup
from consts.cgcs import FlavorSpec
from consts.reasons import SkipHypervisor
from consts.filepaths import TiSPath, UserData
from utils.ssh import ControllerClient
from consts.proj_vars import ProjVar


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

    tmp_file = ProjVar.get_var('TEMP_DIR') + file_name
    with open(tmp_file, mode='a') as f:
        f.write("#wrs-config\n")
        f.write("FUNCTIONS=hugepages,avr\n")

    common.scp_to_active_controller(source_path=tmp_file, dest_path=file_path, is_dir=False)

    return file_path


def image_with_vif_multiq():
    img_id = glance_helper.create_image(name='vif_multq')[1]
    ResourceCleanup.add('image', img_id)
    glance_helper.set_image(image=img_id, properties={'hw_vif_multiqueue_enabled': True})
    return img_id


def launch_vm(vm_type, num_vcpu, host=None):
    img_id = None
    if vm_type == 'vhost':
        vif_model = 'virtio'
        if num_vcpu > 2:
            img_id = image_with_vif_multiq()
    else:
        vif_model = 'avp'

    LOG.tc_step("Create a flavor with 2 vcpus and extra-spec for dpdk")
    flavor_id = nova_helper.create_flavor(vcpus=num_vcpu, ram=1024, root_disk=2)[1]
    ResourceCleanup.add('flavor', flavor_id)
    extra_specs = {FlavorSpec.VCPU_MODEL: 'SandyBridge', FlavorSpec.CPU_POLICY: 'dedicated',
                   FlavorSpec.MEM_PAGE_SIZE: '2048'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    LOG.tc_step("Boot a VM with mgmt net and tenant net")
    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'}, {'net-id': tenant_net_id, 'vif-model': vif_model}]
    vol = cinder_helper.create_volume(image_id=img_id, cleanup='function')[1]

    LOG.tc_step("Boot a vm with created ports")
    host_info = {'avail_zone': 'nova', 'vm_host': host} if host else {}
    vm_id = vm_helper.boot_vm(name='dpdk-vm', nics=nics, flavor=flavor_id, user_data=_get_dpdk_user_data(),
                              source='volume', source_id=vol, cleanup='function', **host_info)[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)

    if host:
        vm_host = nova_helper.get_vm_host(vm_id)
        assert vm_host == host, "VM is not launched on {} as specified".format(host)

    return vm_id


@mark.nics
@mark.parametrize(('vm_type', 'num_vcpu'), [
    ('dpdk', 2),
    ('vhost', 2),
    ('vhost', 3)
])
def test_dpdk_vm_nova_actions(vm_type, num_vcpu):
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

    vm_id = launch_vm(vm_type=vm_type, num_vcpu=num_vcpu)

    for vm_actions in [['reboot'], ['pause', 'unpause'], ['suspend', 'resume'], ['live_migrate'], ['cold_migrate']]:

        LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm_id, vm_actions))
        for action in vm_actions:
            vm_helper.perform_action_on_vm(vm_id, action=action)

        LOG.tc_step("Ping vm from natbox")
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)


@mark.nics
def test_evacuate_dpdk_and_vhost_vms(add_admin_role_func):
    """
    Skip:
        - Less than 2 up hypervisors with same storage config available on system
    Setups:
        - Add admin role to tenant user under test
    Test Steps:
        - Launch 3 vms on same host with following configs:
            - dpdk vm with 2 vcpus
            - vhost vm with 2 vcpus
            - vhost vm with 3 vcpus
        - sudo reboot -f on vm host
        - Check vms are moved to other host, in active state, and are pingable after evacuation
    Teardown:
        - Remove admin role from tenant user
        - Wait for failed host to recover
        - Delete created vms
    """
    storage, hosts = nova_helper.get_storage_backing_with_max_hosts()
    if len(hosts) < 2:
        skip(SkipHypervisor.LESS_THAN_TWO_HYPERVISORS)

    LOG.tc_step("Launch dpdk and vhost vms")
    vms = []
    vm_host = hosts[0]
    for vm_info in (('dpdk', 3), ('vhost', 2), ('vhost', 3)):
        vm_type, num_vcpu = vm_info
        vms.append(launch_vm(vm_type=vm_type, num_vcpu=num_vcpu, host=vm_host))

    LOG.tc_step("Reboot VMs host {} and ensure vms are evacuated to other host".format(vm_host))
    vm_helper.evacuate_vms(host=vm_host, vms_to_check=vms, ping_vms=True)
