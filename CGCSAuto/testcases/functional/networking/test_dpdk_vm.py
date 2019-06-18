from pytest import mark, skip, fixture

from consts.stx import FlavorSpec
from consts.reasons import SkipHypervisor
from keywords import vm_helper, network_helper, nova_helper, glance_helper, cinder_helper, system_helper, host_helper
from testfixtures.fixture_resources import ResourceCleanup
from utils.tis_log import LOG


@fixture(scope='module', autouse=True)
def check_avs_pattern():
    if not system_helper.is_avs():
        skip('avp vif required by dpdk/vhost vm is unsupported by OVS')


def _get_dpdk_user_data(con_ssh=None):
    """
    copy the cloud-config userdata to TiS server.
    This userdata adds sysadmin/li69nux user to guest

    Args:
        con_ssh (SSHClient):

    Returns (str): TiS filepath of the userdata

    """
    return network_helper.get_dpdk_user_data(con_ssh=con_ssh)


def image_with_vif_multiq():
    img_id = glance_helper.create_image(name='vif_multq', cleanup='function')[1]
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

    LOG.tc_step("Boot a {} vm with {} vcpus on {}".format(vm_type, num_vcpu, host if host else "any host"))
    flavor_id = nova_helper.create_flavor(vcpus=num_vcpu, ram=1024, root_disk=2)[1]
    ResourceCleanup.add('flavor', flavor_id)
    extra_specs = {FlavorSpec.VCPU_MODEL: 'SandyBridge', FlavorSpec.CPU_POLICY: 'dedicated',
                   FlavorSpec.MEM_PAGE_SIZE: '2048'}
    nova_helper.set_flavor(flavor=flavor_id, **extra_specs)

    nic1 = {'net-id': network_helper.get_mgmt_net_id()}
    nic2 = {'net-id': network_helper.get_tenant_net_id()}
    nic3 = {'net-id': network_helper.get_internal_net_id()}
    if vif_model != 'virtio':
        nic2['vif-model'] = vif_model
        nic3['vif-model'] = vif_model

    vol = cinder_helper.create_volume(source_id=img_id, cleanup='function')[1]
    host_info = {'avail_zone': 'nova', 'vm_host': host} if host else {}
    vm_id = vm_helper.boot_vm(name='dpdk-vm', nics=[nic1, nic2, nic3], flavor=flavor_id,
                              user_data=_get_dpdk_user_data(),
                              source='volume', source_id=vol, cleanup='function', **host_info)[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)

    if host:
        vm_host = vm_helper.get_vm_host(vm_id)
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
    LOG.tc_step("Boot an observer VM")
    vms, nics = vm_helper.launch_vms(vm_type="dpdk")
    vm_observer = vms[0]
    vm_helper.setup_avr_routing(vm_observer)

    vm_id = launch_vm(vm_type=vm_type, num_vcpu=num_vcpu)
    vm_helper.setup_avr_routing(vm_id, vm_type=vm_type)

    for vm_actions in [['reboot'], ['pause', 'unpause'], ['suspend', 'resume'], ['live_migrate'], ['cold_migrate']]:

        LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm_id, vm_actions))
        for action in vm_actions:
            vm_helper.perform_action_on_vm(vm_id, action=action)

        LOG.tc_step("Ping vm")
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        vm_helper.ping_vms_from_vm(vm_id, vm_observer, net_types=['data', 'internal'], vshell=True)


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
    hosts = host_helper.get_up_hypervisors()
    if len(hosts) < 2:
        skip(SkipHypervisor.LESS_THAN_TWO_HYPERVISORS)

    LOG.tc_step("Boot an observer VM")
    vm_observer = launch_vm(vm_type='dpdk', num_vcpu=2, host=hosts[1])
    vm_helper.setup_avr_routing(vm_observer)

    LOG.tc_step("Launch dpdk and vhost vms")
    vms = []
    vm_host = hosts[0]
    for vm_info in (('dpdk', 3), ('vhost', 2), ('vhost', 3)):
        vm_type, num_vcpu = vm_info
        vm_id = launch_vm(vm_type=vm_type, num_vcpu=num_vcpu, host=vm_host)
        vm_helper.setup_avr_routing(vm_id, vm_type=vm_type)
        vms.append(vm_id)

    LOG.tc_step("Ensure dpdk and vhost vms interfaces are reachable before evacuate")
    vm_helper.ping_vms_from_vm(vms, vm_observer, net_types=['data', 'internal'], vshell=True)

    LOG.tc_step("Reboot VMs host {} and ensure vms are evacuated to other host".format(vm_host))
    vm_helper.evacuate_vms(host=vm_host, vms_to_check=vms, ping_vms=True)
    vm_helper.ping_vms_from_vm(vms, vm_observer, net_types=['data', 'internal'], vshell=True)
