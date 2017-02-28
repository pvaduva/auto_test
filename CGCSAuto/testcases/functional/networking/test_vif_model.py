
from pytest import fixture, mark

from utils.tis_log import LOG

from consts.cgcs import FlavorSpec
from keywords import vm_helper, nova_helper, network_helper

from testfixtures.fixture_resources import ResourceCleanup


@fixture(scope='module')
def base_setup():

    flavor_id = nova_helper.create_flavor(name='dedicated')[1]
    ResourceCleanup.add('flavor', flavor_id, scope='module')

    nova_helper.set_flavor_extra_specs(flavor_id, **{FlavorSpec.CPU_POLICY: 'dedicated'})

    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    internal_net_id = network_helper.get_internal_net_id()

    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': tenant_net_id, 'vif-model': 'virtio'},
            {'net-id': internal_net_id, 'vif-model': 'virtio'}
    ]
    base_vm = vm_helper.boot_vm(name='vif', flavor=flavor_id, nics=nics, cleanup='module', reuse_vol=False)[1]
    # ResourceCleanup.add('vm', base_vm, scope='module')

    return base_vm, mgmt_net_id, tenant_net_id, internal_net_id


# Remove following testcase as it has been covered in other tests
# @mark.sanity
@mark.parametrize('vif_model', [
    'avp',
    'e1000',
    'virtio'
])
def _test_vif_models(vif_model, base_setup):
    """
    boot avp,e100 and virtio instance
    KNI is same as avp

    Test Steps:
        - boot up a vm with given vif model
        - Ping VM from Natbox(external network)
        - Ping from VM to itself over data network
        - Live-migrate the VM and verify ping over management and data networks
        - Cold-migrate the VM and verify ping over management and data networks
        - Pause and un-pause the VM and verify ping over management and data networks
        - Suspend and resume the VM and verify ping over management and data networks
        - Stop and start the VM and verify ping over management and data networks
        - Reboot the VM and verify ping over management and data networks

    Test Teardown:
        - Delete vm created
        - Delete flavor created

    """
    base_vm, mgmt_net_id, tenant_net_id, internal_net_id = base_setup

    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': tenant_net_id, 'vif-model': vif_model},
            {'net-id': internal_net_id, 'vif-model': 'avp'}]

    LOG.tc_step("Boot vm with vif_model {} for tenant-net".format(vif_model))
    vm_under_test = vm_helper.boot_vm(name=vif_model, nics=nics, cleanup='function', reuse_vol=False)[1]
    # ResourceCleanup.add('vm', vm_under_test)

    LOG.tc_step("Ping VM {} from NatBox(external network)".format(vm_under_test))
    vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test, fail_ok=False)

    LOG.info("Ping vm under test from base vm over data network")
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=vm_under_test, net_types='data')

    # Following steps are moved to test_nova_actions.py

    # LOG.tc_step("Live-migrate the VM and verify ping over management and data networks")
    # vm_helper.live_migrate_vm(vm_under_test)
    # vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])
    #
    # LOG.tc_step("Cold-migrate the VM and verify ping over management and data networks")
    # vm_helper.cold_migrate_vm(vm_under_test)
    # vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])
    #
    # LOG.tc_step("Pause and un-pause the VM and verify ping over management and data networks")
    # vm_helper.pause_vm(vm_under_test)
    # vm_helper.unpause_vm(vm_under_test)
    # vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])
    #
    # LOG.tc_step("Suspend and resume the VM and verify ping over management and data networks")
    # vm_helper.suspend_vm(vm_under_test)
    # vm_helper.resume_vm(vm_under_test)
    # vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])
    #
    # LOG.tc_step("Stop and start the VM and verify ping over management and data networks")
    # vm_helper.stop_vms(vm_under_test)
    # vm_helper.start_vms(vm_under_test)
    # vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])
    #
    # LOG.tc_step("Reboot the VM and verify ping over management and data networks")
    # vm_helper.reboot_vm(vm_under_test)
    # vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])
