import random

from pytest import fixture, mark, skip

from utils.tis_log import LOG

from consts.reasons import SkipReason
from consts.cgcs import FlavorSpec, VMStatus
from keywords import system_helper, vm_helper, nova_helper, network_helper, host_helper
from testfixtures.resource_mgmt import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


@fixture(scope='module')
def net_setups_():

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


class TestSriovPciptResourceUsage:
    vif_models = [('pci-passthrough', 'pcipt', 'pci_pfs_used'),
                  ('pci-sriov', 'sriov', 'pci_vfs_used')]

    @fixture(scope='class', params=vif_models)
    def vms_to_test(self, request, net_setups_):
        """
        Create a vm under test with specified vifs for tenant network
        Args:
            request: pytest param
            net_setups_ (tuple): base vm, flavor, management net, tenant net, interal net to use

        Returns (str): id of vm under test

        """
        LOG.error(request.param)
        vif_model, vm_type, resource_usage = request.param

        base_vm, flavor, mgmt_net_id, tenant_net_id, internal_net_id = net_setups_
        nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
                {'net-id': tenant_net_id, 'vif-model': 'avp'},
                {'net-id': internal_net_id, 'vif-model': vif_model}]

        pnet_id = network_helper.get_providernet_for_interface(interface=vm_type)
        LOG.info("provider net id {} for {}".format(pnet_id, vif_model))

        if not pnet_id:
            skip(SkipReason.PCI_IF_UNAVAIL)

        actual_resource_value = nova_helper.get_provider_net_info(pnet_id, field=resource_usage)
        LOG.info("Resource Usage {} for {}".format(actual_resource_value, vif_model))

        vm_limit = vm_helper.get_vm_apps_limit(vm_type=vm_type)
        LOG.info("limit {} for {}".format(vm_limit, vm_type))

        vms_under_test = []
        for i in range(vm_limit):
            LOG.info("Boot vm with vif_model {} for tenant-net".format(vif_model))
            vm_id = vm_helper.boot_vm(nics=nics)[1]
            ResourceCleanup.add('vm', vm_id, scope='class')
            vms_under_test.append(vm_id)

        resource_value = nova_helper.get_provider_net_info(pnet_id, field=resource_usage)
        LOG.info("Resource Usage {} for {}".format(resource_value, vif_model))
        increment_value = len(vms_under_test)
        vm_under_test = random.choice(vms_under_test)

        LOG.info("Ping VM {} from NatBox(external network)".format(vm_under_test))
        vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test, fail_ok=False)

        # LOG.info("Ping vm_under_test from base_vm to verify management, data & internal networks connection")
        # vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'internal'], vlan_zero_only=True)

        LOG.info("Tne resource usage {} is equal to expected value {}".format(resource_value, increment_value))
        assert resource_value == increment_value, "The resource usage is not equal to expected value"

        return base_vm, vm_under_test, pnet_id, resource_usage, increment_value, vif_model

    @mark.parametrize("vm_actions", [
        (['cold_migrate']),
        (['pause', 'unpause']),
        (['suspend', 'resume']),
        (['auto_recover']),
    ])
    def test_pcipt_sriov_vm_actions(self, vms_to_test, vm_actions):
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

        base_vm, vm_under_test, pnet_id, resource_usage, increment_value, vif_model = vms_to_test

        if vm_actions[0] == 'auto_recover':
            LOG.tc_step("Set vm to error state and wait for auto recovery complete, then verify ping from base vm over "
                        "management and data networks")
            vm_helper.set_vm_state(vm_id=vm_under_test, error_state=True, fail_ok=False)
            vm_helper.wait_for_vm_values(vm_id=vm_under_test, status=VMStatus.ACTIVE, fail_ok=True, timeout=600)
        else:
            LOG.tc_step("Perform following action(s) on vm {}: {}".format(vm_under_test, vm_actions))
            for action in vm_actions:
                vm_helper.perform_action_on_vm(vm_under_test, action=action)

        # LOG.tc_step("Verify ping from base_vm to vm_under_test over management and data networks still works after {}".
        #             format(vm_actions))
        # vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'internal'], vlan_zero_only=True)

        resource_value = nova_helper.get_provider_net_info(pnet_id, field=resource_usage)
        LOG.info("Resource Usage {} for {}".format(resource_value, vif_model))

        LOG.info("Tne resource usage {} is equal to expected value {}".format(resource_value, increment_value))
        assert resource_value == increment_value, "The resource usage is not equal to expected value"

    @mark.skipif(True, reason='Evacuation JIRA CGTS-4917')
    def test_pcipt_sriov_evacuate_vm(self, vms_to_test):
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
        base_vm, vm_under_test = vms_to_test[0]
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
        vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'internal'], vlan_zero_only=True)




