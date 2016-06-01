from pytest import fixture, mark

from utils import table_parser, cli
from utils.tis_log import LOG

from consts.auth import Tenant
from consts.cgcs import VMStatus, FlavorSpec
from keywords import vm_helper, nova_helper, host_helper, network_helper, cinder_helper, common

from testfixtures.resource_mgmt import ResourceCleanup

@fixture(scope='module', autouse=True)
def create_flavor(request):
    LOG.info("Create a flavor and set nic_isolation to true")
    flavor_id = nova_helper.create_flavor(name='nic_isolation')[1]
    ResourceCleanup.add('flavor', flavor_id)

    extra_specs = {FlavorSpec.NIC_ISOLATION: 'true'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)


@fixture(scope='module', autouse=True )
def vms_():
    possible_vifs = {'DPDKAPPS': "vswitch",
                     'AVPAPPS': 'avp',
                     'VIRTIOAPPS': 'virtio'}

    vms = {}
    for vif in possible_vifs:
        with host_helper.ssh_to_host('controller-0') as host_ssh:
            vm_limit = host_ssh.exec_cmd("grep -r {} lab_setup.conf | cut -d = -f2".format(vif))[1]

        tenant_net_ips = {'tenant1': "172.16.0.1", 'tenant2': "172.18.0.1"}
        # tenant1_internal_ip = "10.0.0.1"    # next: 10.1.1.1
        # tenant1_internal_ip = "10.0.0.2"
        vif_model = possible_vifs[vif]
        if vm_limit == '':
            break
        vms[vif_model] = []
        for auth_info in [Tenant.TENANT_1, Tenant.TENANT_2]:
            mgmt_id = network_helper.get_mgmt_net_id(auth_info=auth_info)
            for i in range(int(vm_limit)):
                #cinder create needs to be done here
                #needs to be in loop
                tenant_name = common.get_tenant_name(auth_info)
                vol_id = cinder_helper.create_volume(name='vol-{}-{}{}'.format(tenant_name, vif_model, i+1))[1]
                # I need to pass the variable in loop
                tenantnet_ip = tenant_net_ips[tenant_name]
                tenantnet_ip_list = tenantnet_ip.split(sep='.')
                cidr = '.'.join(tenantnet_ip_list[0:3])
                table_ = table_parser.table(cli.neutron('net-list', auth_info=auth_info))
                tenantnet_id = table_parser.get_values(table_, 'id', strict=False, subnets=cidr, merge_lines=True)[0]
                tenant_net_nic = {'net-id': tenantnet_id, 'v4-fixed-ip': tenantnet_ip, 'vif-model': vif_model}
                nics = [{'net-id': mgmt_id, 'vif-model': 'virtio'}, tenant_net_nic]
                # calculate ip for next vm
                tenantnet_ip_third_num = int(tenantnet_ip_list[2])
                tenantnet_ip_list[2] = str(tenantnet_ip_third_num + 1)
                tenant_net_ips[tenant_name] = '.'.join(tenantnet_ip_list)

                userdata = '/home/wrsroot/userdata/{}-{}{}_userdata.txt'.format(tenant_name, vif_model, i+1)
                vm_id = vm_helper.boot_vm(source='volume', source_id=vol_id, nics=nics, user_data=userdata)[1]
                #how to pass required variable
                ResourceCleanup.add('vm', vm_id, scope='module')
                # Ensure vm can be reached from outside before proceeding with the test cases
                vms[vif_model].append(vm_id)
    return vms

def test_avp_vms_with_vm_actions(vms_):
    """
    Test VM external access over VM launch, live-migration, cold-migration, pause/unpause, etc

    Args:
        vms_ (str): vm created by module level test fixture

    Test Setups:
        - boot a vm from volume and ping vm from NatBox     (module)

    Test Steps:
        - Ping from VM to 8.8.8.8
        - Live-migrate the VM and verify ping from VM
        - Cold-migrate the VM and verify ping from VM
        - Pause and un-pause the VM and verify ping from VM
        - Suspend and resume the VM and verify ping from VM
        - Stop and start the VM and verify ping from VM
        - Reboot the VM and verify ping from VM

    Test Teardown:
        - Delete the created vm     (module)

    """
    for vm in vms_:
        LOG.tc_step("Ping from VM {} to 8.8.8.8".format(vm))
        vm_helper.ping_ext_from_vm(vm)

        LOG.tc_step("Live-migrate the VM and verify ping from VM")
        vm_helper.live_migrate_vm(vm)
        vm_helper.ping_ext_from_vm(vm)

        LOG.tc_step("Cold-migrate the VM and verify ping from VM")
        vm_helper.cold_migrate_vm(vm)
        vm_helper.ping_ext_from_vm(vm)

        LOG.tc_step("Pause and un-pause the VM and verify ping from VM")
        vm_helper.pause_vm(vm)
        vm_helper.unpause_vm(vm)
        vm_helper.ping_ext_from_vm(vm)

        LOG.tc_step("Suspend and resume the VM and verify ping from VM")
        vm_helper.suspend_vm(vm)
        vm_helper.resume_vm(vm)
        vm_helper.ping_ext_from_vm(vm)

        LOG.tc_step("Stop and start the VM and verify ping from VM")
        vm_helper.stop_vms(vm)
        vm_helper.start_vms(vm)
        vm_helper.ping_ext_from_vm(vm)

        LOG.tc_step("Reboot the VM and verify ping from VM")
        vm_helper.reboot_vm(vm)
        vm_helper.ping_ext_from_vm(vm)

