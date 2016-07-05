from pytest import fixture, mark, skip

from utils.tis_log import LOG

from consts.cgcs import FlavorSpec, VMStatus
from consts.reasons import SkipReason
from keywords import vm_helper, nova_helper, network_helper, host_helper
from testfixtures.resource_mgmt import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


def id_params(val):
    return '_'.join(val)


class TestMutiPortsBasic:
    @fixture(scope='class')
    def base_setup(self):

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
        base_vm = vm_helper.boot_vm(flavor=flavor_id, nics=nics)[1]
        ResourceCleanup.add('vm', base_vm, scope='module')

        return base_vm, flavor_id, mgmt_net_id, tenant_net_id, internal_net_id

    vifs_to_test = [('avp', 'avp'),
                    ('virtio', 'virtio'),
                    ('e1000', 'virtio'),
                    ('avp', 'virtio'), ]

    @fixture(scope='class', params=vifs_to_test, ids=id_params)
    def vms_to_test(self, request, base_setup):
        """
        Create a vm under test with specified vifs for tenant network
        Args:
            request: pytest param
            base_setup (tuple): base vm, flavor, management net, tenant net, internal net to use

        Returns (str): id of vm under test

        """
        vifs = request.param
        base_vm, flavor, mgmt_net_id, tenant_net_id, internal_net_id = base_setup

        nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'}]
        for vif in vifs:
            nics.append({'net-id': tenant_net_id, 'vif-model': vif})

        # add interface for internal net
        nics.append({'net-id': internal_net_id, 'vif-model': 'avp'})

        LOG.info("Boot a vm with following nics: {}".format(nics))
        vm_under_test = vm_helper.boot_vm(nics=nics, flavor=flavor)[1]
        ResourceCleanup.add('vm', vm_under_test, scope='class')
        vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test, fail_ok=False)

        LOG.info("Ping vm's own data network ips")
        vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=vm_under_test, net_types='data')

        LOG.info("Ping vm_under_test from base_vm to verify management and data networks connection")
        vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])

        return base_vm, vm_under_test

    @mark.parametrize("vm_actions", [
        (['live_migrate']),
        (['cold_migrate']),
        (['pause', 'unpause']),
        (['suspend', 'resume']),
        (['auto_recover']),
    ], ids=id_params)
    def test_multiports_on_same_network_vm_actions(self, vms_to_test, vm_actions):
        """
        Test vm actions on vm with multiple ports with given vif models on the same tenant network

        Args:
            vms_to_test (tuple): id of base vm and vm under test
            vm_actions (list): actions to perform on vm under test

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

        base_vm, vm_under_test = vms_to_test

        if vm_actions[0] == 'auto_recover':
            LOG.tc_step("Set vm to error state and wait for auto recovery complete, then verify ping from base vm over "
                        "management and data networks")
            vm_helper.set_vm_state(vm_id=vm_under_test, error_state=True, fail_ok=False)
            vm_helper.wait_for_vm_values(vm_id=vm_under_test, status=VMStatus.ACTIVE, fail_ok=True, timeout=600)
        else:
            LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm_under_test, vm_actions))
            for action in vm_actions:
                vm_helper.perform_action_on_vm(vm_under_test, action=action)

        LOG.tc_step("Verify ping from base_vm to vm_under_test over management and data networks still works after {}".
                    format(vm_actions))
        vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])

    @mark.skipif(True, reason='Evacuation JIRA CGTS-4264')
    def test_multiports_on_same_network_evacuate_vm(self, vms_to_test):
        """
        Test evacuate vm with multiple ports on same network

        Args:
            vms_to_test (tuple): id of base vm and vm under test

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
        base_vm, vm_under_test = vms_to_test
        host = nova_helper.get_vm_host(vm_under_test)

        LOG.tc_step("Reboot vm host {}".format(host))
        host_helper.reboot_hosts(host, wait_for_reboot_finish=False)
        HostsToRecover.add(host, scope='function')

        LOG.tc_step("Verify vm is evacuated to other host")
        vm_helper._wait_for_vm_status(vm_under_test, status=VMStatus.ACTIVE, timeout=120, fail_ok=False)
        post_evac_host = nova_helper.get_vm_host(vm_under_test)
        assert post_evac_host != host, "VM is on the same host after original host rebooted."

        LOG.tc_step("Wait for vm pingable from NatBox after evacuation.")
        vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test)

        LOG.tc_step("Verify ping from base_vm to vm_under_test over management and data networks still works after "
                    "evacuation.")
        vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])


class TestMutiPortsPCI:

    @fixture(scope='class')
    def base_setup_pci(self):
        sriov_info = network_helper.get_pci_interface_info(interface='sriov')
        pcipt_info = network_helper.get_pci_interface_info(interface='pthru')
        if not sriov_info or not pcipt_info:
            skip(SkipReason.PCI_IF_UNAVAIL)

        flavor_id = nova_helper.create_flavor(name='dedicated')[1]
        ResourceCleanup.add('flavor', flavor_id, scope='module')

        extra_specs = {FlavorSpec.CPU_POLICY: 'dedicated'}
        nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

        mgmt_net_id = network_helper.get_mgmt_net_id()
        tenant_net_id = network_helper.get_tenant_net_id()
        internal_net_id = network_helper.get_internal_net_id(net_name='internal0-net1', strict=True)

        nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
                {'net-id': tenant_net_id, 'vif-model': 'virtio'},
                {'net-id': internal_net_id, 'vif-model': 'virtio'},
                {'net-id': internal_net_id, 'vif-model': 'pci-passthrough'},
                {'net-id': internal_net_id, 'vif-model': 'avp'}, ]

        base_vm_pci = vm_helper.boot_vm(name='auto-sriov', flavor=flavor_id, nics=nics)[1]
        ResourceCleanup.add('vm', base_vm_pci, scope='module')

        LOG.info("Ping base PCI vm from NatBox over management")
        vm_helper.wait_for_vm_pingable_from_natbox(base_vm_pci, fail_ok=False)
        LOG.info("Ping base PCI vm from itself over data, and internal (vlan 0 only) networks")
        vm_helper.ping_vms_from_vm(to_vms=base_vm_pci, from_vm=base_vm_pci, net_types=['data', 'internal'],
                                   vlan_zero_only=True)

        return base_vm_pci, flavor_id, mgmt_net_id, tenant_net_id, internal_net_id

    vifs_to_test = [('pci-sriov', 'pci-passthrough'),
                    ('avp', 'virtio', 'e1000', 'pci-passthrough', 'pci-sriov'),
                    ('avp', 'pci-sriov', 'pci-passthrough', 'pci-sriov', 'pci-sriov')]

    @fixture(scope='class', params=vifs_to_test, ids=id_params)
    def vms_to_test(self, request, base_setup_pci):
        """
        Create a vm under test with specified vifs for tenant network
        Args:
            request: pytest param
            base_setup_pci (tuple): base vm, flavor, management net, tenant net, interal net to use

        Returns (str): id of vm under test

        """
        vifs = request.param
        base_vm_pci, flavor, mgmt_net_id, tenant_net_id, internal_net_id = base_setup_pci

        nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
                {'net-id': tenant_net_id, 'vif-model': 'avp'}]
        for vif in vifs:
            nics.append({'net-id': internal_net_id, 'vif-model': vif})

        LOG.info("Boot a vm with following vifs on same internal net {}: {}".format(vifs, internal_net_id))
        vm_under_test = vm_helper.boot_vm(nics=nics, flavor=flavor)[1]
        ResourceCleanup.add('vm', vm_under_test, scope='class')
        vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test, fail_ok=False)

        LOG.info("Ping vm's own data and internal (vlan 0 only) network ips")
        vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=vm_under_test, net_types=['data', 'internal'])

        LOG.info("Ping vm_under_test from base_vm over management, data, and internal (vlan 0 only) networks")
        vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm_pci, net_types=['mgmt', 'data', 'internal'])

        return base_vm_pci, vm_under_test

    @mark.parametrize("vm_actions", [
        (['live_migrate']),
        (['cold_migrate']),
        (['pause', 'unpause']),
        (['suspend', 'resume']),
        (['auto_recover']),
    ], ids=id_params)
    def test_multiports_on_same_network_pci_vm_actions(self, vms_to_test, vm_actions):
        """
        Test vm actions on vm with multiple ports with given vif models on the same tenant network

        Args:
            vms_to_test (tuple): id of base vm and vm under test
            vm_actions (list): actions to perform on vm under test

        Setups:
            - Create a flavor with dedicated cpu policy (module)
            - Choose management net, one tenant net, and internal0-net1 to be used by test (class)
            - Boot a base pci-sriov vm - vm1 with above flavor and networks, ping it from NatBox (class)
            - Ping vm1 from itself over data, and internal (vlan 0 only) networks
            - Boot a vm under test - vm2 with above flavor and with multiple ports on same tenant network with vm1,
            and ping it from NatBox      (class)
            - Ping vm2's own data and internal (vlan 0 only) network ips        (class)
            - Ping vm2 from vm1 to verify management and data networks connection    (class)

        Test Steps:
            - Perform given actions on vm2 (migrate, start/stop, etc)
            - Verify ping from vm1 to vm2 over management and data networks still works

        Teardown:
            - Delete created vms and flavor
        """

        base_vm, vm_under_test = vms_to_test

        if vm_actions[0] == 'auto_recover':
            LOG.tc_step("Set vm to error state and wait for auto recovery complete, then verify ping from base vm over "
                        "management and data networks")
            vm_helper.set_vm_state(vm_id=vm_under_test, error_state=True, fail_ok=False)
            vm_helper.wait_for_vm_values(vm_id=vm_under_test, status=VMStatus.ACTIVE, fail_ok=True, timeout=600)
        else:
            LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm_under_test, vm_actions))
            for action in vm_actions:
                vm_helper.perform_action_on_vm(vm_under_test, action=action)

        LOG.tc_step("Verify ping from base_vm to vm_under_test over management and internal networks still works "
                    "after {}".format(vm_actions))
        vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'internal'],
                                   vlan_zero_only=True)

    @mark.skipif(True, reason='Evacuation JIRA CGTS-4264')
    def test_multiports_on_same_network_pci_evacuate_vm(self, vms_to_test):
        """
        Test evacuate vm with multiple ports on same network

        Args:
            vms_to_test (tuple): id of base vm and vm under test

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
        base_vm, vm_under_test = vms_to_test
        host = nova_helper.get_vm_host(vm_under_test)

        LOG.tc_step("Reboot vm host {}".format(host))
        host_helper.reboot_hosts(host, wait_for_reboot_finish=False)
        HostsToRecover.add(host, scope='function')

        LOG.tc_step("Verify vm is evacuated to other host")
        vm_helper._wait_for_vm_status(vm_under_test, status=VMStatus.ACTIVE, timeout=120, fail_ok=False)
        post_evac_host = nova_helper.get_vm_host(vm_under_test)
        assert post_evac_host != host, "VM is on the same host after original host rebooted."

        LOG.tc_step("Wait for vm pingable from NatBox after evacuation.")
        vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test)

        LOG.tc_step("Verify ping from base_vm to vm_under_test over management and data networks still works after "
                    "evacuation.")
        vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'internal'])
