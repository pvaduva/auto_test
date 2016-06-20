from pytest import fixture, mark

from utils import table_parser, cli, exceptions
from utils.tis_log import LOG

from consts.auth import Tenant
from consts.cgcs import VMStatus, FlavorSpec, NetworkingVmMapping
from keywords import vm_helper, nova_helper, host_helper, network_helper, cinder_helper, common

from testfixtures.resource_mgmt import ResourceCleanup
#
# @fixture(scope='module', autouse=True)
# def create_flavor(request):
#     LOG.info("Create a flavor and set nic_isolation to true")
#     flavor_id = nova_helper.create_flavor(name='nic_isolation')[1]
#     ResourceCleanup.add('flavor', flavor_id)
#
#     extra_specs = {FlavorSpec.NIC_ISOLATION: 'true'}
#     nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

#
# @fixture(scope='module', autouse=True )
# def vms_():
#     possible_vifs = ['DPDKAPPS', 'AVPAPPS', 'VIRTIOAPPS']
#
#     DPDKAPPS = {'vif_model': 'vswitch',
#                 'flavor': 'medium.dpdk',
#                 }
#
#     AVPAPPS = {'vif_model': 'avp',
#                'flavor': 'small',
#                }
#
#     VIRTIOAPPS = {'vif_model': 'vswitch',
#                   'flavor': 'small',
#                   }
#
#     vms = {}
#     for vif in possible_vifs:
#
#         with host_helper.ssh_to_host('controller-0') as host_ssh:
#             vm_limit = host_ssh.exec_cmd("grep --color='never' -r {} lab_setup.conf | cut -d = -f2".format(vif))[1]
#
#         vif = eval(vif)
#         tenant_net_ips = {'tenant1': "172.16.0.1", 'tenant2': "172.18.0.1"}
#         # tenant1_internal_ip = "10.0.0.1"    # next: 10.1.1.1
#         # tenant1_internal_ip = "10.0.0.2"
#         vif_model = vif['vif_model']
#         if vm_limit == '':
#             break
#         vms[vif_model] = []
#         for auth_info in [Tenant.TENANT_1, Tenant.TENANT_2]:
#             mgmt_id = network_helper.get_mgmt_net_id(auth_info=auth_info)
#             for i in range(int(vm_limit)):
#
#                 tenant_name = common.get_tenant_name(auth_info)
#                 vol_id = cinder_helper.create_volume(name='vol-{}-{}{}'.format(tenant_name, vif_model, i+1),
#                                                      auth_info=auth_info)[1]
#
#                 tenantnet_ip = tenant_net_ips[tenant_name]
#                 tenantnet_ip_list = tenantnet_ip.split(sep='.')
#                 cidr = '.'.join(tenantnet_ip_list[0:3])
#                 table_ = table_parser.table(cli.neutron('net-list', auth_info=auth_info))
#                 tenantnet_id = table_parser.get_values(table_, 'id', strict=False, subnets=cidr, merge_lines=True)[0]
#                 tenant_net_nic = {'net-id': tenantnet_id, 'v4-fixed-ip': tenantnet_ip, 'vif-model': vif_model}
#                 nics = [{'net-id': mgmt_id, 'vif-model': 'virtio'}, tenant_net_nic]
#
#                 # Get flavor id
#                 flavor_name = vif['flavor']
#                 flavor_id = nova_helper.get_flavor_id(name=flavor_name)
#                 if flavor_id == '':
#                     raise exceptions.NoMatchFoundError("Flavor {} does not exist on system.".format(flavor_name))
#
#                 # calculate ip for next vm
#                 tenantnet_ip_third_num = int(tenantnet_ip_list[2])
#                 tenantnet_ip_list[2] = str(tenantnet_ip_third_num + 1)
#                 tenant_net_ips[tenant_name] = '.'.join(tenantnet_ip_list)
#
#                 userdata = '/home/wrsroot/userdata/{}-{}{}_userdata.txt'.format(tenant_name, vif_model, i+1)
#
#                 vm_name = "{}{}_auto".format(vif_model, i+1)
#                 vm_id = vm_helper.boot_vm(name=vm_name, flavor=flavor_id, source='volume', source_id=vol_id, nics=nics,
#                                           user_data=userdata, auth_info=auth_info)[1]
#                 ResourceCleanup.add('vm', vm_id, scope='module')
#
#                 # Ensure vm can be reached from outside before proceeding with the test cases
#                 vms[vif_model].append(vm_id)
#     return vms


@mark.parametrize(('spec_name', 'spec_val', 'vm_type', 'vif_model'), [
    (FlavorSpec.NIC_ISOLATION, 'true', 'avp', 'avp'),
    (FlavorSpec.NIC_ISOLATION, 'true', 'virtio', 'virtio'),
    (FlavorSpec.NIC_ISOLATION, 'true', 'vswitch', 'avp'),
])
def test_avp_vms_with_vm_actions(spec_name, spec_val, vm_type, vif_model):
    """
    <summary>

    Test Steps:
        - Create a flavor with given extra spec
        - boot a vm via lab_setup script
        - resize the vm with the flavor created
        - Ping VM from Natbox(external network)
        - Ping from VM to 8.8.8.8
        - Live-migrate the VM and verify ping from VM
        - Cold-migrate the VM and verify ping from VM
        - Pause and un-pause the VM and verify ping from VM
        - Suspend and resume the VM and verify ping from VM
        - Stop and start the VM and verify ping from VM
        - Reboot the VM and verify ping from VM

    Test Teardown:
        - Delete vm created
        - Delete flavor created

    """

    existing_flavor_name = eval("NetworkingVmMapping.{}".format(vm_type.upper()))['flavor']
    existing_flavor = nova_helper.get_flavor_id(name=existing_flavor_name)

    LOG.tc_step("Make a copy of flavor {}")
    flavor_id = nova_helper.copy_flavor(from_flavor_id=existing_flavor, new_name='auto')
    ResourceCleanup.add('flavor', flavor_id)

    LOG.tc_step("Set new flavor extra spec {} to {}".format(spec_name, spec_val))
    extra_specs = {FlavorSpec.NIC_ISOLATION: 'true'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': tenant_net_id, 'vif-model': vif_model}]

    LOG.tc_step("Boot vm with flavor {} and vif_model {} for tenant-net".format(flavor_id, vif_model))
    volume = cinder_helper.create_volume(rtn_exist=False)[1]
    ResourceCleanup.add('volume', volume)
    vm = vm_helper.boot_vm(name='vm-avs', flavor=flavor_id, source='volume', source_id=volume, nics=nics)[1]
    ResourceCleanup.add('vm', vm)

    LOG.tc_step("Ping VM {} from NatBox".format(vm))
    vm_helper.wait_for_vm_pingable_from_natbox(vm)

    LOG.tc_step("Ping from VM to external ip 8.8.8.8")
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

