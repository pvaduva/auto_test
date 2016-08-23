from pytest import fixture, mark

from utils import table_parser, cli, exceptions
from utils.tis_log import LOG

from consts.auth import Tenant
from consts.cgcs import VMStatus, FlavorSpec, NetworkingVmMapping
from keywords import vm_helper, nova_helper, host_helper, network_helper, cinder_helper, common

from testfixtures.resource_mgmt import ResourceCleanup


@fixture(scope='module')
def base_vm_():

    LOG.fixture_step("Create a base vm with dedicated CPU policy and virtio nics")
    flavor_id = nova_helper.create_flavor(name='dedicated')[1]
    ResourceCleanup.add('flavor', flavor_id, scope='module')

    extra_specs = {FlavorSpec.CPU_POLICY: 'dedicated'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    internal_net_id = network_helper.get_internal_net_id()

    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': tenant_net_id, 'vif-model': 'virtio'},
            {'net-id': internal_net_id, 'vif-model': 'virtio'}
    ]
    base_vm = vm_helper.boot_vm(name='avs_base', flavor=flavor_id, nics=nics, reuse_vol=False)[1]
    ResourceCleanup.add('vm', base_vm, scope='module')

    return base_vm, mgmt_net_id, tenant_net_id, internal_net_id


@mark.parametrize(('spec_name', 'spec_val', 'vm_type', 'vif_model'), [
    (FlavorSpec.NIC_ISOLATION, 'true', 'avp', 'avp'),
    (FlavorSpec.NIC_ISOLATION, 'true', 'virtio', 'virtio'),
    (FlavorSpec.NIC_ISOLATION, 'true', 'vswitch', 'avp'),
])
def test_avp_vms_with_vm_actions(spec_name, spec_val, vm_type, vif_model, base_vm_):
    """
    <summary>

    Setups:
        - Boot a base vm with dedicated cpu policy in flavor        (module)
        - choose one tenant network and one internal network to be used by test     (module)
        - boot a base vm - vm1 with above flavor and networks, and ping it from NatBox  (module)

    Test Steps:
        - Create a flavor with given extra spec
        - Boot a vm under test - vm2 with above flavor and same networks with base vm,
        - Ping vm2 from NatBox
        - Ping vm2's own data network ips
        - Ping vm2 from vm1 to verify management and data networks connection
        - Live-migrate vm2 and verify ping over management and data networks
        - Cold-migrate vm2 and verify ping over management and data networks
        - Pause and un-pause vm2 and verify ping over management and data networks
        - Suspend and resume vm2 and verify ping over management and data networks
        - Stop and start vm2 and verify ping over management and data networks
        - Reboot vm2 and verify ping over management and data networks

    Test Teardown:
        - Delete vm2 and its flavor
        - Delete vm1 and its flavor     (module)

    """
    base_vm, mgmt_net_id, tenant_net_id, internal_net_id = base_vm_

    existing_flavor_name = eval("NetworkingVmMapping.{}".format(vm_type.upper()))['flavor']
    existing_flavor = nova_helper.get_flavor_id(name=existing_flavor_name)

    LOG.tc_step("Make a copy of flavor {}".format(existing_flavor_name))
    flavor_id = nova_helper.copy_flavor(from_flavor_id=existing_flavor, new_name='auto')
    ResourceCleanup.add('flavor', flavor_id)

    LOG.tc_step("Set new flavor extra spec {} to {}".format(spec_name, spec_val))
    extra_specs = {FlavorSpec.NIC_ISOLATION: 'true'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': tenant_net_id, 'vif-model': vif_model},
            {'net-id': internal_net_id, 'vif-model': 'avp'}]

    LOG.tc_step("Boot vm with flavor {} and vif_model {} for tenant-net".format(flavor_id, vif_model))
    volume = cinder_helper.create_volume(rtn_exist=False)[1]
    ResourceCleanup.add('volume', volume)
    vm_under_test = vm_helper.boot_vm(name='avs-vm', flavor=flavor_id, source='volume', source_id=volume, nics=nics)[1]
    ResourceCleanup.add('vm', vm_under_test)

    LOG.tc_step("Ping VM {} from NatBox".format(vm_under_test))
    vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test)

    LOG.tc_step("Ping vm's own data network ips")
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=vm_under_test, net_types='data')

    LOG.tc_step("Ping vm_under_test from base_vm to verify management and data networks connection")
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])

    LOG.tc_step("Live-migrate the VM and verify ping over management and data networks")
    vm_helper.live_migrate_vm(vm_under_test)
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])

    LOG.tc_step("Cold-migrate the VM and verify ping over management and data networks")
    vm_helper.cold_migrate_vm(vm_under_test)
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])

    LOG.tc_step("Pause and un-pause the VM and verify ping over management and data networks")
    vm_helper.pause_vm(vm_under_test)
    vm_helper.unpause_vm(vm_under_test)
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])

    LOG.tc_step("Suspend and resume the VM and verify ping over management and data networks")
    vm_helper.suspend_vm(vm_under_test)
    vm_helper.resume_vm(vm_under_test)
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])

    LOG.tc_step("Stop and start the VM and verify ping over management and data networks")
    vm_helper.stop_vms(vm_under_test)
    vm_helper.start_vms(vm_under_test)
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])

    LOG.tc_step("Reboot the VM and verify ping over management and data networks")
    vm_helper.reboot_vm(vm_under_test)
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])
