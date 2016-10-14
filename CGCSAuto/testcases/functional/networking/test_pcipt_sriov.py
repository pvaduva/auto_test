from pytest import fixture, mark, skip

from utils.tis_log import LOG

from consts.auth import Tenant
from consts.cgcs import FlavorSpec, VMStatus
from keywords import vm_helper, nova_helper, network_helper, host_helper, common
from testfixtures.resource_mgmt import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


@fixture(scope='module', params=['pci-passthrough', 'pci-sriov'])
def vif_model_check(request):
    vif_model = request.param
    LOG.fixture_step("Check if lab is configured with {} interface".format(vif_model))

    interface = 'sriov' if 'sriov' in vif_model else 'pthru'
    pci_info = network_helper.get_pci_interface_info(interface=interface)
    if not pci_info:
        skip("{} interface not found in lab_setup.conf".format(vif_model))

    LOG.fixture_step("Get a PCI network too boot vm from pci providernet info from lab_setup.conf")
    pci_nets = network_helper.get_pci_nets(vif=interface, rtn_val='name')
    primary_tenant = Tenant.get_primary()
    primary_tenant_name = common.get_tenant_name(primary_tenant)
    other_tenant = Tenant.TENANT_2 if primary_tenant_name == 'tenant1' else Tenant.TENANT_1

    for net in pci_nets:
        if 'internal' in net:
            pci_net = net
            net_type = 'internal'
            break
        elif primary_tenant_name in net:
            pci_net = net
            net_type = 'data'
            break
    else:
        for net in pci_nets:
            if other_tenant['tenant'] in net:
                Tenant.set_primary(other_tenant)
                pci_net = net
                net_type = 'data'

                def _revert_tenant():
                    Tenant.set_primary(primary_tenant)
                request.addfinalizer(_revert_tenant)
                break

        else:
            skip("No tenant or internal networks have {} configured.".format(vif_model))
            return

    LOG.fixture_step("PCI network selected to boot vm: {}".format(pci_net))

    LOG.fixture_step("Create a flavor with dedicated cpu policy")
    flavor_id = nova_helper.create_flavor(name='dedicated')[1]
    ResourceCleanup.add('flavor', flavor_id, scope='module')

    extra_specs = {FlavorSpec.CPU_POLICY: 'dedicated'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    LOG.fixture_step("Boot a base vm with above flavor and virtio nics")

    mgmt_net_id = network_helper.get_mgmt_net_id()
    pci_net_id = network_helper._get_net_ids(net_name=pci_net)[0]

    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': pci_net_id, 'vif-model': 'virtio'}]

    base_vm = vm_helper.boot_vm(flavor=flavor_id, nics=nics)[1]
    ResourceCleanup.add('vm', base_vm, scope='module')
    vm_helper.wait_for_vm_pingable_from_natbox(base_vm)
    vm_helper.ping_vms_from_vm(base_vm, base_vm, net_types=['mgmt', net_type], vlan_zero_only=True)

    if vif_model == 'pci-passthrough':

        LOG.fixture_step("Get seg_id for {} to prepare for vlan tagging on pci-passthough device later".format(pci_net))
        seg_id = network_helper.get_net_info(net_id=pci_net_id, field='segmentation_id', strict=False,
                                             auto_info=Tenant.ADMIN)
        assert seg_id, 'Segmentation id of pci net {} is not found'.format(pci_net)

    else:
        seg_id = None

    nics_to_test = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
                    {'net-id': pci_net_id, 'vif-model': vif_model}]

    return vif_model, base_vm, flavor_id, nics_to_test, seg_id, net_type


def test_pci_resource_usage(vif_model_check):
    """
    Create a vm under test with specified vifs for tenant network
    Args:
        request: pytest param
        net_setups_ (tuple): base vm, flavor, management net, tenant net, interal net to use

    Returns (str): id of vm under test

    """
    vif_model, base_vm, flavor_id, nics_to_test, seg_id, net_type = vif_model_check

    if 'sriov' in vif_model:
        vm_type = 'sriov'
        resource_param = 'pci_vfs_used'
    else:
        vm_type = 'pcipt'
        resource_param = 'pci_pfs_used'

    LOG.tc_step("Get resource usage for {} interface before booting VM(s)".format(vif_model))
    pnet_id = network_helper.get_providernet_for_interface(interface=vm_type)
    LOG.info("provider net id {} for {}".format(pnet_id, vif_model))

    assert pnet_id, "provider network id for {} interface is not found".format(vif_model)

    pre_resource_value = nova_helper.get_provider_net_info(pnet_id, field=resource_param)
    LOG.info("Resource Usage {} for {}".format(pre_resource_value, vif_model))

    vm_limit = vm_helper.get_vm_apps_limit(vm_type=vm_type)
    LOG.info("limit {} for {}".format(vm_limit, vm_type))

    assert vm_limit > 0, "VM limit for {} should be at least 1".format(vif_model)

    vms_under_test = []
    for i in range(vm_limit):
        LOG.tc_step("Boot a vm with {} vif model on {} net".format(vif_model, net_type))
        res, vm_id, err, vol_id = vm_helper.boot_vm(name=vif_model, flavor=flavor_id, nics=nics_to_test, fail_ok=True)
        if vm_id:
            ResourceCleanup.add('vm', vm_id, del_vm_vols=False)
        if vol_id:
            ResourceCleanup.add('volume', vol_id)
        assert 0 == res, "VM is not booted successfully. Error: {}".format(err)

        vms_under_test.append(vm_id)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id, fail_ok=False)

        if vm_type == 'pcipt':
            LOG.tc_step("Add vlan to pci-passthrough interface for VM.")
            vm_helper.add_vlan_for_vm_pcipt_interfaces(vm_id=vm_id, net_seg_id=seg_id)

        LOG.tc_step("Ping vm over mgmt and {} nets from itself".format(net_type))
        vm_helper.ping_vms_from_vm(from_vm=vm_id, to_vms=vm_id, net_types=['mgmt', net_type])

        LOG.tc_step("Check resource usage for {} interface increased by 1".format(vif_model))
        resource_value = nova_helper.get_provider_net_info(pnet_id, field=resource_param)
        assert pre_resource_value + 1 == resource_value, "Resource usage for {} is not increased by 1".format(vif_model)
        pre_resource_value = resource_value

    for vm_to_del in vms_under_test:
        LOG.tc_step("Check resource usage for {} interface reduced by 1 after deleting a vm".format(vif_model))
        vm_helper.delete_vms(vm_to_del, check_first=False, stop_first=False)
        resource_val = common.wait_for_val_from_func(expt_val=pre_resource_value - 1, timeout=30, check_interval=3,
                                                     func=nova_helper.get_provider_net_info,
                                                     providernet_id=pnet_id, field=resource_param)[1]
        # resource_value = nova_helper.get_provider_net_info(pnet_id, field=resource_param)

        assert pre_resource_value - 1 == resource_val, "Resource usage for {} is not reduced by 1".format(vif_model)
        pre_resource_value = resource_val


def test_pci_vm_nova_actions(vif_model_check):
    """
    Test vm actions on vm with multiple ports with given vif models on the same tenant network

    Args:
        vifs (tuple): vif models to test. Used when booting vm with tenant network nics info
        net_setups_ (tuple): flavor, networks to use and base vm info

    Setups:
        - create a flavor with dedicated cpu policy (module)
        - choose one tenant network and one internal network to be used by test (module)
        - boot a base vm - vm1 with above flavor and networks, and ping it from NatBox (module)
        - Boot a vm under test - vm2 with above flavor and with multiple ports on same tenant network with base vm,
        and ping it from NatBox      (class)
        - Ping vm2's own data network ips        (class)
        - Ping vm2 from vm1 to verify management and data networks connection    (class)

    Test Steps:
        - Perform given actions on vm2 (migrate, start/stop, etc)
        - Verify ping from vm1 to vm2 over management and data networks still works

    Teardown:
        - Delete created vms and flavor
    """

    vif_model, base_vm, flavor_id, nics_to_test, seg_id, net_type = vif_model_check

    LOG.tc_step("Boot a vm with {} vif model on internal net".format(vif_model))
    res, vm_id, err, vol_id = vm_helper.boot_vm(name=vif_model, flavor=flavor_id, nics=nics_to_test)
    if vm_id:
        ResourceCleanup.add('vm', vm_id, del_vm_vols=False)
    if vol_id:
        ResourceCleanup.add('volume', vol_id)
    assert 0 == res, "VM is not booted successfully. Error: {}".format(err)

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id, fail_ok=False)

    if 'pci-passthrough' == vif_model:
        LOG.tc_step("Add vlan to pci-passthrough interface for VM.")
        vm_helper.add_vlan_for_vm_pcipt_interfaces(vm_id=vm_id, net_seg_id=seg_id)

    LOG.tc_step("Ping vm over mgmt and {} nets from base vm".format(net_type))
    vm_helper.ping_vms_from_vm(from_vm=vm_id, to_vms=vm_id, net_types=['mgmt', net_type], vlan_zero_only=True)
    vm_helper.ping_vms_from_vm(from_vm=base_vm, to_vms=vm_id, net_types=['mgmt', net_type], vlan_zero_only=True)

    LOG.tc_step('Pause/Unpause {} vm'.format(vif_model))
    vm_helper.pause_vm(vm_id)
    vm_helper.unpause_vm(vm_id)

    LOG.tc_step("Check vm still pingable over mgmt and {} nets after pause/unpause".format(net_type))
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    vm_helper.ping_vms_from_vm(from_vm=base_vm, to_vms=vm_id, net_types=['mgmt', net_type], vlan_zero_only=True)

    LOG.tc_step('Suspend/Resume {} vm'.format(vif_model))
    vm_helper.suspend_vm(vm_id)
    vm_helper.resume_vm(vm_id)

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    if 'pci-passthrough' == vif_model:
        LOG.tc_step("Add/Check vlan interface is added to pci-passthrough device for vm {}.".format(vm_id))
        vm_helper.add_vlan_for_vm_pcipt_interfaces(vm_id=vm_id, net_seg_id=seg_id)

    LOG.tc_step("Check vm still pingable over mgmt and {} nets after suspend/resume".format(net_type))
    vm_helper.ping_vms_from_vm(from_vm=base_vm, to_vms=vm_id, net_types=['mgmt', net_type], vlan_zero_only=True)

    LOG.tc_step('Cold migrate {} vm'.format(vif_model))
    vm_helper.cold_migrate_vm(vm_id)

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    if 'pci-passthrough' == vif_model:
        LOG.tc_step("Add/Check vlan interface is added to pci-passthrough device for vm {}.".format(vm_id))
        vm_helper.add_vlan_for_vm_pcipt_interfaces(vm_id=vm_id, net_seg_id=seg_id)

    LOG.tc_step("Check vm still pingable over mgmt and {} nets after cold migration".format(net_type))
    vm_helper.ping_vms_from_vm(from_vm=base_vm, to_vms=vm_id, net_types=['mgmt', net_type], vlan_zero_only=True)

    LOG.tc_step('Set vm to error and wait for it to be auto recovered')
    vm_helper.set_vm_state(vm_id=vm_id, error_state=True, fail_ok=False)
    vm_helper.wait_for_vm_values(vm_id=vm_id, status=VMStatus.ACTIVE, fail_ok=False, timeout=600)

    LOG.tc_step("Check vm still pingable over mgmt and {} nets after auto recovery".format(net_type))
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    vm_helper.ping_vms_from_vm(from_vm=base_vm, to_vms=vm_id, net_types=['mgmt', net_type], vlan_zero_only=True)


def test_evacuate_pci_vm(vif_model_check):
    """
    Test evacuate vm with multiple ports on same network

    Args:
        vifs (tuple): vif models to test. Used when booting vm with tenant network nics info
        net_setups_ (tuple): flavor, networks to use and base vm info

    Setups:
        - create a flavor with dedicated cpu policy (module)
        - choose one tenant network and one internal network to be used by test (module)
        - boot a base vm - vm1 with above flavor and networks, and ping it from NatBox (module)
        - Boot a vm under test - vm2 with above flavor and with multiple ports on same tenant network with base vm,
        and ping it from NatBox     (class)
        - Ping vm2's own data network ips       (class)
        - Ping vm2 from vm1 to verify management and data networks connection   (class)

    Test Steps:
        - Reboot vm2 host
        - Wait for vm2 to be evacuated to other host
        - Wait for vm2 pingable from NatBox
        - Verify ping from vm1 to vm2 over management and data networks still works

    Teardown:
        - Delete created vms and flavor
    """
    vif_model, base_vm, flavor_id, nics_to_test, seg_id, net_type = vif_model_check

    LOG.tc_step("Boot a vm with {} vif model on {} net".format(vif_model, net_type))
    res, vm_id, err, vol_id = vm_helper.boot_vm(name=vif_model, flavor=flavor_id, nics=nics_to_test)
    if vm_id:
        ResourceCleanup.add('vm', vm_id, del_vm_vols=False)
    if vol_id:
        ResourceCleanup.add('volume', vol_id)
    assert 0 == res, "VM is not booted successfully. Error: {}".format(err)

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id, fail_ok=False)

    if 'pci-passthrough' == vif_model:
        LOG.tc_step("Add vlan to pci-passthrough interface for VM.")
        vm_helper.add_vlan_for_vm_pcipt_interfaces(vm_id=vm_id, net_seg_id=seg_id)

    LOG.tc_step("Ping vm over mgmt and {} nets from base vm".format(net_type))
    vm_helper.ping_vms_from_vm(from_vm=base_vm, to_vms=vm_id, net_types=['mgmt', net_type], vlan_zero_only=True)

    host = nova_helper.get_vm_host(vm_id)

    LOG.tc_step("Reboot vm host {}".format(host))
    host_helper.reboot_hosts(host, wait_for_reboot_finish=False)
    HostsToRecover.add(host, scope='function')

    LOG.tc_step("Wait for vm to reach ERROR or REBUILD state with best effort")
    vm_helper._wait_for_vms_values(vm_id, values=[VMStatus.ERROR, VMStatus.REBUILD], fail_ok=True, timeout=120)

    LOG.tc_step("Verify vm is evacuated to other host")
    vm_helper._wait_for_vm_status(vm_id, status=VMStatus.ACTIVE, timeout=300, fail_ok=False)
    post_evac_host = nova_helper.get_vm_host(vm_id)
    assert post_evac_host != host, "VM is on the same host after original host rebooted."


    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    if 'pci-passthrough' == vif_model:
        LOG.tc_step("Add vlan to pci-passthrough interface for VM again after evacuation due to interface change.")
        vm_helper.add_vlan_for_vm_pcipt_interfaces(vm_id=vm_id, net_seg_id=seg_id)

    LOG.tc_step("Check vm still pingable over mgmt, and {} nets after evacuation".format(net_type))
    vm_helper.ping_vms_from_vm(from_vm=base_vm, to_vms=vm_id, net_types=['mgmt', net_type], vlan_zero_only=True)
