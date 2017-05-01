import re
import time
from pytest import fixture, mark, skip

from utils import cli
from utils import table_parser
from utils.tis_log import LOG

from consts.auth import Tenant
from consts.cgcs import FlavorSpec, VMStatus
from keywords import vm_helper, nova_helper, network_helper, host_helper, common
from testfixtures.fixture_resources import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


@fixture(scope='module', params=['pci-passthrough', 'pci-sriov'])
def vif_model_check(request):
    vif_model = request.param
    LOG.fixture_step("Check if lab is configured with {} interface".format(vif_model))

    interface = 'sriov' if 'sriov' in vif_model else 'pthru'
    pci_info = network_helper.get_pci_interface_info(interface=interface)
    if not pci_info:
        skip("{} interface not found in lab_setup.conf".format(vif_model))

    LOG.fixture_step("Get a PCI network to boot vm from pci providernet info from lab_setup.conf")
    # pci_nets = network_helper.get_pci_nets(vif=interface, rtn_val='name')
    primary_tenant = Tenant.get_primary()
    primary_tenant_name = common.get_tenant_name(primary_tenant)
    other_tenant = Tenant.TENANT2 if primary_tenant_name == 'tenant1' else Tenant.TENANT1

    tenant_net = "{}-net"
    extra_pcipt_net = extra_pcipt_net_name = None
    pci_net = network_helper.get_pci_vm_network(pci_type=vif_model)
    if isinstance(pci_net, list):
        pci_net, extra_pcipt_net_name = pci_net
        extra_pcipt_net = network_helper.get_net_id_from_name(extra_pcipt_net_name)

    if not pci_net:
        skip('No {} net found on up host(s)'.format(vif_model))

    if 'mgmt' in pci_net:
        skip("Only management networks have {} interface.".format(vif_model))

    if 'internal' in pci_net:
        net_type = 'internal'
    else:
        net_type = 'data'
        if tenant_net.format(primary_tenant_name) not in pci_net:
            Tenant.set_primary(other_tenant)

            def revert_tenant():
                Tenant.set_primary(primary_tenant)
            request.addfinalizer(revert_tenant)

    LOG.info("PCI network selected to boot vm: {}".format(pci_net))

    LOG.fixture_step("Create a flavor with dedicated cpu policy")
    flavor_id = nova_helper.create_flavor(name='dedicated', ram=2048)[1]
    ResourceCleanup.add('flavor', flavor_id, scope='module')

    extra_specs = {FlavorSpec.CPU_POLICY: 'dedicated'}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    LOG.fixture_step("Boot a base vm with above flavor and virtio nics")

    mgmt_net_id = network_helper.get_mgmt_net_id()
    pci_net_id = network_helper._get_net_ids(net_name=pci_net)[0]
    pnet_name = network_helper.get_net_info(net_id=pci_net_id, field='provider:physical_network')
    pnet_id = network_helper.get_providernets(name=pnet_name, rtn_val='id', strict=True)[0]

    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': pci_net_id, 'vif-model': 'virtio'}]

    if extra_pcipt_net:
        nics.append({'net-id': extra_pcipt_net, 'vif-model': 'virtio'})

    base_vm = vm_helper.boot_vm(flavor=flavor_id, nics=nics, cleanup='module')[1]
    # ResourceCleanup.add('vm', base_vm, scope='module')
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
    if extra_pcipt_net:
        nics_to_test.append({'net-id': extra_pcipt_net, 'vif-model': vif_model})
        extra_pcipt_seg_id = network_helper.get_net_info(net_id=extra_pcipt_net, field='segmentation_id', strict=False,
                                                         auto_info=Tenant.ADMIN)
        seg_id = {pci_net: seg_id,
                  extra_pcipt_net_name: extra_pcipt_seg_id}

    return vif_model, base_vm, flavor_id, nics_to_test, seg_id, net_type, pnet_id, extra_pcipt_net_name, extra_pcipt_net


@mark.p1
def test_evacuate_pci_vm(vif_model_check):
    """
    Test evacuate vm with multiple ports on same network

    Args:

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
    vif_model, base_vm, flavor_id, nics_to_test, seg_id, net_type, pnet_id, extra_pcipt_net_name, extra_pcipt_net = \
        vif_model_check

    LOG.tc_step("Boot a vm with {} vif model on {} net".format(vif_model, net_type))
    res, vm_id, err, vol_id = vm_helper.boot_vm(name=vif_model, flavor=flavor_id, cleanup='function', nics=nics_to_test)
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

