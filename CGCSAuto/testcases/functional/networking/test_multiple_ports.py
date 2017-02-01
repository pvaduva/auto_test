from pytest import fixture, mark, skip

from utils.tis_log import LOG

from consts.cgcs import FlavorSpec, VMStatus
from consts.reasons import SkipReason
from consts.auth import Tenant
from keywords import vm_helper, nova_helper, network_helper, host_helper, check_helper, common
from testfixtures.resource_mgmt import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


def id_params(val):
    if not isinstance(val, str):
        new_val = []
        for val_1 in val:
            if not isinstance(val_1, str):
                val_1 = '_'.join([str(val_2).lower() for val_2 in val_1])
            new_val.append(val_1)
    else:
        new_val = val

    return '_'.join(new_val)


def _append_nics_for_net(vifs, net_id, nics):
    for vif in vifs:
        vif_, pci_addr = vif

        vif_ = vif_.split(sep='_x')
        vif_model = vif_[0]
        iter_ = int(vif_[1]) if len(vif_) > 1 else 1
        for i in range(iter_):
            nic = {'net-id': net_id, 'vif-model': vif_model}
            if pci_addr is not None:
                pci_prefix, pci_append = pci_addr.split(':')
                pci_append_incre = format(int(pci_append, 16) + i, '02x')
                nic['vif-pci-address'] = ':'.join(['0000', pci_prefix, pci_append_incre]) + '.0'
            nics.append(nic)

    return nics


def _boot_multiports_vm(flavor, mgmt_net_id, vifs, net_id, net_type, base_vm, pcipt_seg_id=None):
    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'}]

    nics = _append_nics_for_net(vifs, net_id=net_id, nics=nics)

    LOG.tc_step("Boot a test_vm with following nics on same networks as base_vm: {}".format(nics))
    vm_under_test = vm_helper.boot_vm(name='multiports', nics=nics, flavor=flavor, reuse_vol=False)[1]
    ResourceCleanup.add('vm', vm_under_test)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test, fail_ok=False)

    LOG.tc_step("Check vm PCI address is as configured")
    check_helper.check_vm_pci_addr(vm_under_test, nics)

    if pcipt_seg_id:
        LOG.tc_step("Add vlan to pci-passthrough interface for VM.")
        vm_helper.add_vlan_for_vm_pcipt_interfaces(vm_id=vm_under_test, net_seg_id=pcipt_seg_id)

    LOG.tc_step("Ping test_vm's own {} network ips".format(net_type))
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=vm_under_test, net_types=net_type)

    LOG.tc_step("Ping test_vm from base_vm to verify management and data networks connection")
    vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', net_type])

    return vm_under_test, nics


class TestMutiPortsBasic:
    @fixture(scope='class')
    def base_setup(self):

        flavor_id = nova_helper.create_flavor(name='dedicated')[1]
        ResourceCleanup.add('flavor', flavor_id, scope='class')

        extra_specs = {FlavorSpec.CPU_POLICY: 'dedicated'}
        nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

        mgmt_net_id = network_helper.get_mgmt_net_id()
        tenant_net_id = network_helper.get_tenant_net_id()
        internal_net_id = network_helper.get_internal_net_id()

        nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
                {'net-id': tenant_net_id, 'vif-model': 'e1000'},
                {'net-id': internal_net_id, 'vif-model': 'virtio'}]

        LOG.fixture_step("(class) Boot a base vm with following nics: {}".format(nics))
        base_vm = vm_helper.boot_vm(name='multiports_base', flavor=flavor_id, nics=nics, reuse_vol=False)[1]
        ResourceCleanup.add('vm', base_vm, scope='class')

        vm_helper.wait_for_vm_pingable_from_natbox(base_vm)
        vm_helper.ping_vms_from_vm(base_vm, base_vm, net_types='data')
        
        return base_vm, flavor_id, mgmt_net_id, tenant_net_id, internal_net_id

    @mark.p2
    @mark.parametrize('vifs', [
        (('avp', '00:02'), ('avp', '00:1f')),
        (('virtio', '01:01'), ('virtio', None)),
        (('e1000', '04:09'), ('virtio', '08:1f')),
        (('avp', None), ('virtio', None)),
    ], ids=id_params)
    def test_multiports_on_same_network_vm_actions(self, vifs, base_setup):
        """
        Test vm actions on vm with multiple ports with given vif models on the same tenant network

        Args:
            vifs (tuple): each item in the tuple is 1 nic to be added to vm with specified (vif_mode, pci_address)
            base_setup (list): test fixture to boot base vm

        Setups:
            - create a flavor with dedicated cpu policy (class)
            - choose one tenant network and one internal network to be used by test (class)
            - boot a base vm - vm1 with above flavor and networks, and ping it from NatBox (class)
            - Boot a vm under test - vm2 with above flavor and with multiple ports on same tenant network with base vm,
            and ping it from NatBox      (class)
            - Ping vm2's own data network ips        (class)
            - Ping vm2 from vm1 to verify management and data networks connection    (class)

        Test Steps:
            - Perform given actions on vm2 (migrate, start/stop, etc)
            - Verify pci_address preserves
            - Verify ping from vm1 to vm2 over management and data networks still works

        Teardown:
            - Delete created vms and flavor
        """
        base_vm, flavor, mgmt_net_id, tenant_net_id, internal_net_id = base_setup

        vm_under_test, nics = _boot_multiports_vm(flavor=flavor, mgmt_net_id=mgmt_net_id, vifs=vifs,
                                                  net_id=tenant_net_id, net_type='data', base_vm=base_vm)

        for vm_actions in [['auto_recover'], ['cold_migrate'], ['pause', 'unpause'], ['suspend', 'resume']]:
            if vm_actions[0] == 'auto_recover':
                LOG.tc_step("Set vm to error state and wait for auto recovery complete, then verify ping from "
                            "base vm over management and data networks")
                vm_helper.set_vm_state(vm_id=vm_under_test, error_state=True, fail_ok=False)
                vm_helper.wait_for_vm_values(vm_id=vm_under_test, status=VMStatus.ACTIVE, fail_ok=True, timeout=600)
            else:
                LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm_under_test, vm_actions))
                for action in vm_actions:
                    vm_helper.perform_action_on_vm(vm_under_test, action=action)

            vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test)

            LOG.tc_step("Verify vm pci address preserved after {}".format(vm_actions))
            check_helper.check_vm_pci_addr(vm_under_test, nics)

            LOG.tc_step("Verify ping from base_vm to vm_under_test over management and data networks still works "
                        "after {}".format(vm_actions))
            vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])

    # @mark.skipif(True, reason='Evacuation JIRA CGTS-4917')
    @mark.p2
    @mark.parametrize('vifs', [
        (('avp', '00:05'), ('e1000', '08:01'), ('virtio', '01:1f'), ('virtio', None)),
    ], ids=id_params)
    def test_multiports_on_same_network_evacuate_vm(self, vifs, base_setup):
        """
        Test evacuate vm with multiple ports on same network

        Args:
            vifs (tuple): each item in the tuple is 1 nic to be added to vm with specified (vif_mode, pci_address)
            base_setup (tuple): test fixture to boot base vm

        Setups:
            - create a flavor with dedicated cpu policy (class)
            - choose one tenant network and one internal network to be used by test (class)
            - boot a base vm - vm1 with above flavor and networks, and ping it from NatBox (class)
            - Boot a vm under test - vm2 with above flavor and with multiple ports on same tenant network with base vm,
            and ping it from NatBox     (class)
            - Ping vm2's own data network ips       (class)
            - Ping vm2 from vm1 to verify management and data networks connection   (class)

        Test Steps:
            - Reboot vm2 host
            - Wait for vm2 to be evacuated to other host
            - Wait for vm2 pingable from NatBox
            - Verify pci_address preserves
            - Verify ping from vm1 to vm2 over management and data networks still works

        Teardown:
            - Delete created vms and flavor
        """

        base_vm, flavor, mgmt_net_id, tenant_net_id, internal_net_id = base_setup
        vm_under_test, nics = _boot_multiports_vm(flavor=flavor, mgmt_net_id=mgmt_net_id, vifs=vifs,
                                                  net_id=tenant_net_id, net_type='data', base_vm=base_vm)

        host = nova_helper.get_vm_host(vm_under_test)

        LOG.tc_step("Reboot vm host {}".format(host))
        host_helper.reboot_hosts(host, wait_for_reboot_finish=False)
        HostsToRecover.add(host, scope='function')

        LOG.tc_step("Wait for vms to reach ERROR or REBUILD state with best effort")
        vm_helper._wait_for_vms_values(vm_under_test, values=[VMStatus.ERROR, VMStatus.REBUILD], fail_ok=True,
                                       timeout=120)

        LOG.tc_step("Verify vm is evacuated to other host")
        vm_helper._wait_for_vm_status(vm_under_test, status=VMStatus.ACTIVE, timeout=300, fail_ok=False)
        post_evac_host = nova_helper.get_vm_host(vm_under_test)
        assert post_evac_host != host, "VM is on the same host after original host rebooted."

        LOG.tc_step("Wait for vm pingable from NatBox after evacuation.")
        vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test)

        LOG.tc_step("Verify vm pci address preserved after evacuated from {} to {}".format(host, post_evac_host))
        check_helper.check_vm_pci_addr(vm_under_test, nics)

        LOG.tc_step("Verify ping from base_vm to vm_under_test over management and data networks still works after "
                    "evacuation.")
        vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])


class TestMutiPortsPCI:

    @fixture(scope='class')
    def base_setup_pci(self):
        LOG.fixture_step("(class) Check pci-passthrough and pci-sriov support")
        sriov_info = network_helper.get_pci_interface_info(interface='sriov')
        pcipt_info = network_helper.get_pci_interface_info(interface='pthru')
        if not sriov_info:
            skip(SkipReason.SRIOV_IF_UNAVAIL)
        if not pcipt_info:
            skip(SkipReason.PCIPT_IF_UNAVAIL)

        LOG.fixture_step("(class) Get a PCI network to boot vm from pci providernet info from lab_setup.conf")
        pci_sriov_nets = network_helper.get_pci_nets(vif='sriov', rtn_val='name')
        pci_pthru_nets = network_helper.get_pci_nets(vif='pthru', rtn_val='name')
        avail_nets = list(set(pci_pthru_nets) & set(pci_sriov_nets))
        if 'internal0-net1' not in avail_nets:
            skip("'internal-net1' does not have pci-sriov and/or pci-passthrough interfaces")

        LOG.fixture_step("(class) Create a flavor with dedicated cpu policy.")
        flavor_id = nova_helper.create_flavor(name='dedicated')[1]
        ResourceCleanup.add('flavor', flavor_id, scope='class')

        extra_specs = {FlavorSpec.CPU_POLICY: 'dedicated'}
        nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

        mgmt_net_id = network_helper.get_mgmt_net_id()
        tenant_net_id = network_helper.get_tenant_net_id()
        internal_net_id = network_helper.get_internal_net_id(net_name='internal0-net1', strict=True)

        nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
                {'net-id': tenant_net_id, 'vif-model': 'virtio'},
                {'net-id': internal_net_id, 'vif-model': 'virtio'},
                {'net-id': internal_net_id, 'vif-model': 'pci-sriov'},
                {'net-id': internal_net_id, 'vif-model': 'avp'}, ]

        LOG.fixture_step("(class) Boot a base pci vm with following nics: {}".format(nics))
        base_vm_pci = vm_helper.boot_vm(name='multiports_pci_base', flavor=flavor_id, nics=nics, reuse_vol=False)[1]
        ResourceCleanup.add('vm', base_vm_pci, scope='class')

        LOG.fixture_step("(class) Ping base PCI vm from NatBox over management network.")
        vm_helper.wait_for_vm_pingable_from_natbox(base_vm_pci, fail_ok=False)

        LOG.fixture_step("(class) Ping base PCI vm from itself over data, and internal (vlan 0 only) networks")
        vm_helper.ping_vms_from_vm(to_vms=base_vm_pci, from_vm=base_vm_pci, net_types=['data', 'internal'],
                                   vlan_zero_only=True)

        LOG.fixture_step("(class) Get seg_id for internal0-net1 to prepare for vlan tagging on pci-passthough "
                         "device later.")
        seg_id = network_helper.get_net_info(net_id=internal_net_id, field='segmentation_id', strict=False,
                                             auto_info=Tenant.ADMIN)
        assert seg_id, 'Segmentation id of internal0-net1 is not found'

        return base_vm_pci, flavor_id, mgmt_net_id, tenant_net_id, internal_net_id, seg_id, pcipt_info

    @mark.parametrize('vifs', [
        mark.p2(['virtio_x7', 'avp_x5', 'pci-passthrough']),
        mark.p2(['virtio_x7', 'avp_x5', 'pci-sriov']),
        mark.p3((['pci-sriov', 'pci-passthrough'])),
        mark.domain_sanity((['avp', 'virtio', 'e1000', 'pci-passthrough', 'pci-sriov'])),
        mark.p3((['avp', 'pci-sriov', 'pci-passthrough', 'pci-sriov', 'pci-sriov'])),
    ], ids=id_params)
    def test_multiports_on_same_network_pci_vm_actions(self, base_setup_pci, vifs):
        """
        Test vm actions on vm with multiple ports with given vif models on the same tenant network

        Args:
            base_setup_pci (tuple): base_vm_pci, flavor, mgmt_net_id, tenant_net_id, internal_net_id, seg_id
            vifs (list): list of vifs to add to same internal net

        Setups:
            - Create a flavor with dedicated cpu policy (class)
            - Choose management net, one tenant net, and internal0-net1 to be used by test (class)
            - Boot a base pci-sriov vm - vm1 with above flavor and networks, ping it from NatBox (class)
            - Ping vm1 from itself over data, and internal (vlan 0 only) networks

        Test Steps:
            - Boot a vm under test - vm2 with above flavor and with multiple ports on same tenant network with vm1,
                and ping it from NatBox
            - Ping vm2's own data and internal (vlan 0 only) network ips
            - Ping vm2 from vm1 to verify management and data networks connection
            - Perform one of the following actions on vm2
                - set to error/ wait for auto recovery
                - suspend/resume
                - cold migration
                - pause/unpause
            - Update vlan interface to proper eth if pci-passthrough device moves to different eth
            - Verify ping from vm1 to vm2 over management and data networks still works
            - Repeat last 3 steps with different vm actions

        Teardown:
            - Delete created vms and flavor
        """

        base_vm_pci, flavor, mgmt_net_id, tenant_net_id, internal_net_id, seg_id, pcipt_info = base_setup_pci

        pcipt_included = False
        for vif in vifs:
            if 'pci-passthrough' in vif:
                pcipt_included = True
                break

        if pcipt_included and not pcipt_info:
            skip(SkipReason.PCIPT_IF_UNAVAIL)

        nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
                {'net-id': tenant_net_id, 'vif-model': 'avp'}]
        for vif in vifs:
            vif_ = vif.split(sep='_x')
            vif_type = vif_[0]
            iter_ = int(vif_[1]) if len(vif_) > 1 else 1
            for i in range(iter_):
                nics.append({'net-id': internal_net_id, 'vif-model': vif_type})

        LOG.tc_step("Boot a vm with following vifs on same network internal0-net1: {}".format(vifs))
        vm_under_test = vm_helper.boot_vm(name='multiports_pci', nics=nics, flavor=flavor, reuse_vol=False)[1]
        ResourceCleanup.add('vm', vm_under_test, scope='function')
        vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test, fail_ok=False)

        if pcipt_included:
            LOG.tc_step("Add vlan to pci-passthrough interface for VM.")
            vm_helper.add_vlan_for_vm_pcipt_interfaces(vm_id=vm_under_test, net_seg_id=seg_id)

        LOG.tc_step("Ping vm's own data and internal (vlan 0 only) network ips")
        vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=vm_under_test, net_types=['data', 'internal'])

        LOG.tc_step("Ping vm_under_test from base_vm over management, data, and internal (vlan 0 only) networks")
        vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm_pci, net_types=['mgmt', 'data', 'internal'])

        for vm_actions in [['auto_recover'], ['cold_migrate'], ['pause', 'unpause'], ['suspend', 'resume']]:

            if 'auto_recover' in vm_actions:
                LOG.tc_step("Set vm to error state and wait for auto recovery complete, "
                            "then verify ping from base vm over management and internal networks")
                vm_helper.set_vm_state(vm_id=vm_under_test, error_state=True, fail_ok=False)
                vm_helper.wait_for_vm_values(vm_id=vm_under_test, status=VMStatus.ACTIVE, fail_ok=False, timeout=600)

            else:
                LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm_under_test, vm_actions))
                for action in vm_actions:
                    vm_helper.perform_action_on_vm(vm_under_test, action=action)

            vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_under_test)

            LOG.tc_step("Add/Check vlan interface is added to pci-passthrough device for vm {}.".format(vm_under_test))
            vm_helper.add_vlan_for_vm_pcipt_interfaces(vm_id=vm_under_test, net_seg_id=seg_id)

            LOG.tc_step("Verify ping from base_vm to vm_under_test over management and internal networks still works "
                        "after {}".format(vm_actions))
            vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm_pci, net_types=['mgmt', 'internal'],
                                       vlan_zero_only=True)

    # @mark.skipif(True, reason='Evacuation JIRA CGTS-4917')
    @mark.parametrize('vifs', [
        # (['pci-sriov', 'pci-passthrough']),
        mark.domain_sanity((['avp', 'virtio', 'e1000', 'pci-passthrough', 'pci-sriov'])),
        # (['avp', 'pci-sriov', 'pci-passthrough', 'pci-sriov', 'pci-sriov']),
    ], ids=id_params)
    def test_multiports_on_same_network_pci_evacuate_vm(self, base_setup_pci, vifs):
        """
        Test evacuate vm with multiple ports on same network

        Args:
            base_setup_pci (tuple): base vm id, vm under test id, segment id for internal0-net1
            vifs (list): list of vifs to add to same internal net

        Setups:
            - create a flavor with dedicated cpu policy (module)
            - choose one tenant network and one internal network to be used by test (module)
            - boot a base vm - vm1 with above flavor and networks, and ping it from NatBox (module)
            - Boot a vm under test - vm2 with above flavor and with multiple ports on same tenant network with base vm,
            and ping it from NatBox     (class)
            - Ping vm2's own data network ips       (class)
            - Ping vm2 from vm1 to verify management and internal networks connection   (class)

        Test Steps:
            - Reboot vm2 host
            - Wait for vm2 to be evacuated to other host
            - Wait for vm2 pingable from NatBox
            - Verify ping from vm1 to vm2 over management and internal networks still works

        Teardown:
            - Delete created vms and flavor
        """
        base_vm_pci, flavor, mgmt_net_id, tenant_net_id, internal_net_id, seg_id, pcipt_info = base_setup_pci

        nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
                {'net-id': tenant_net_id, 'vif-model': 'avp'}]
        for vif in vifs:
            nics.append({'net-id': internal_net_id, 'vif-model': vif})

        LOG.tc_step("Boot a vm with following vifs on same network internal0-net1: {}".format(vifs))
        vm_under_test = vm_helper.boot_vm(name='multiports_pci_chris', nics=nics, flavor=flavor, reuse_vol=False)[1]
        ResourceCleanup.add('vm', vm_under_test, scope='function')
        vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test, fail_ok=False)

        LOG.tc_step("Add vlan to pci-passthrough interface.")
        vm_helper.add_vlan_for_vm_pcipt_interfaces(vm_id=vm_under_test, net_seg_id=seg_id)

        LOG.tc_step("Ping vm's own data and internal (vlan 0 only) network ips")
        vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=vm_under_test, net_types=['data', 'internal'])

        LOG.tc_step("Ping vm_under_test from base_vm over management, data, and internal (vlan 0 only) networks")
        vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm_pci, net_types=['mgmt', 'data', 'internal'])

        host = nova_helper.get_vm_host(vm_under_test)

        LOG.tc_step("Reboot vm host {}".format(host))
        host_helper.reboot_hosts(host, wait_for_reboot_finish=False)
        HostsToRecover.add(host, scope='function')

        LOG.tc_step("Wait for vm to reach ERROR or REBUILD state with best effort")
        vm_helper._wait_for_vms_values(vm_under_test, values=[VMStatus.ERROR, VMStatus.REBUILD], fail_ok=True,
                                       timeout=120)

        LOG.tc_step("Verify vm is evacuated to other host")
        vm_helper._wait_for_vm_status(vm_under_test, status=VMStatus.ACTIVE, timeout=120, fail_ok=False)
        post_evac_host = nova_helper.get_vm_host(vm_under_test)
        assert post_evac_host != host, "VM is on the same host after original host rebooted."

        LOG.tc_step("Wait for vm pingable from NatBox after evacuation.")
        vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test)

        LOG.tc_step("Add/Check vlan interface is added to pci-passthrough device for vm {}.".format(vm_under_test))
        vm_helper.add_vlan_for_vm_pcipt_interfaces(vm_id=vm_under_test, net_seg_id=seg_id)

        LOG.tc_step("Verify ping from base_vm to vm_under_test over management and internal networks still works after "
                    "evacuation.")
        vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm_pci, net_types=['mgmt', 'internal'])
