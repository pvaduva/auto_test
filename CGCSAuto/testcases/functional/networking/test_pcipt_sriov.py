import re
from pytest import fixture, mark, skip

from utils import cli
from utils import table_parser
from utils.tis_log import LOG

from consts.auth import Tenant
from consts.cgcs import FlavorSpec, VMStatus
from keywords import vm_helper, nova_helper, network_helper, host_helper, common, system_helper, check_helper
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

    LOG.fixture_step("Get a PCI network to boot vm from pci providernet info from lab_setup.conf")
    # pci_nets = network_helper.get_pci_nets(vif=interface, rtn_val='name')
    primary_tenant = Tenant.get_primary()
    primary_tenant_name = common.get_tenant_name(primary_tenant)
    other_tenant = Tenant.TENANT2 if primary_tenant_name == 'tenant1' else Tenant.TENANT1

    tenant_net = "{}-net"

    host_num = 1
    pci_net = None
    pci_nets_with_min_two_hosts = network_helper.get_pci_nets_with_min_hosts(min_hosts=2, pci_type=vif_model)

    # todo: for now skip any net that has only 1 vlan_id/segmentation_id as a workaround
    # for the issue that booting VM on that kind of net will fail
    if not pci_nets_with_min_two_hosts or len(pci_nets_with_min_two_hosts) < 1:
        skip('Not enough PCI networks of type: {} on this lab'.format(vif_model))

    if pci_nets_with_min_two_hosts:
        pci_net = pci_nets_with_min_two_hosts[0]
        if 'mgmt' not in pci_net:
            host_num = 2  # or > 2

    if host_num == 1:
        pci_nets_with_one_host = network_helper.get_pci_nets_with_min_hosts(min_hosts=1, pci_type=vif_model)
        if not pci_nets_with_one_host:
            skip("Even though some host(s) configured with {} interface, but none is up".format(vif_model))
        pci_net = pci_nets_with_one_host[0]
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

    LOG.fixture_step("PCI network selected to boot vm: {}".format(pci_net))

    LOG.fixture_step("Create a flavor with dedicated cpu policy")
    flavor_id = nova_helper.create_flavor(name='dedicated')[1]
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

    return vif_model, base_vm, flavor_id, nics_to_test, seg_id, net_type, pnet_id


    @mark.p2
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
        vif_model, base_vm, flavor_id, nics_to_test, seg_id, net_type, pnet_id = vif_model_check

        LOG.tc_step("Boot a vm with {} vif model on {} net".format(vif_model, net_type))
        res, vm_id, err, vol_id = vm_helper.boot_vm(name=vif_model, flavor=flavor_id, nics=nics_to_test)
        if vm_id:
            ResourceCleanup.add('vm', vm_id, del_vm_vols=False)
            pass
        if vol_id:
            ResourceCleanup.add('volume', vol_id)
            pass
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


@mark.p3
def test_pci_resource_usage(vif_model_check):
    """
    Create a vm under test with specified vifs for tenant network
    Args:
        request: pytest param
        net_setups_ (tuple): base vm, flavor, management net, tenant net, interal net to use

    Returns (str): id of vm under test

    """
    vif_model, base_vm, flavor_id, nics_to_test, seg_id, net_type, pnet_id = vif_model_check

    if 'sriov' in vif_model:
        vm_type = 'sriov'
        resource_param = 'pci_vfs_used'
    else:
        vm_type = 'pcipt'
        resource_param = 'pci_pfs_used'

    LOG.tc_step("Get resource usage for {} interface before booting VM(s)".format(vif_model))
    LOG.info("provider net id for {} interface: {}".format(vif_model, pnet_id))

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
            pass
        if vol_id:
            ResourceCleanup.add('volume', vol_id)
            pass
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


def get_vm_details_from_nova(vm_id, con_ssh=None, auth_info=None):
    table_ = table_parser.table(cli.nova('show', vm_id, ssh_client=con_ssh, auth_info=auth_info))

    details = {str(k).strip(): v for k, v in table_['values']}

    return details


def check_vm_boot(obj):
    if obj.pci_numa_affinity is not None:
        nic = obj.get_pci_nic()
        assert nic is not None and len(nic) > 0, \
            'Error, PCI device for {} is not created'.format(obj.net_type)

    assert obj.check_numa_affinity(msg_prefx='boot'), \
        'Error, VM CPU/Mem numa: {} is different from PCI device:{}'.format(obj.numa, obj.pci_numa)


def check_vm_pause_unpause(obj):
    obj.check_numa_affinity(msg_prefx='pause_unpause')


def check_vm_suspend_resume(obj):
    obj.check_numa_affinity(msg_prefx='suspend_resume')


def check_vm_cold_migrate(obj):
    obj.check_numa_affinity(msg_prefx='cold-migrate')


def check_vm_set_error_recover(obj):
    obj.check_numa_affinity('set_error_recover')


class TestVmPCIOperations:

    NIC_PCI_TYPES = ['pci-passthrough', 'pci-sriov']
    PCI_NUMA_AFFINITY_VALUES = ['strict', 'prefer']

    CHECKERS = {'boot': check_vm_boot,
                'pause/unpause': check_vm_pause_unpause,
                'suspend/resume': check_vm_suspend_resume,
                'cold-migrate': check_vm_cold_migrate,
                'set-error-state-recover': check_vm_set_error_recover
                }

    def get_pci_nic(self):
        nics = self.vm_details_from_nova['wrs-if:nics']

        self.pci_nic = None
        for nic in nics:
            nic_details = list(eval(nic).values())[0]
            if 'vif_model' in nic_details and nic_details['vif_model'] == self.vif_model:
                self.pci_nic = nic_details
                LOG.info('pci_nic:{}'.format(self.pci_nic))
                return self.pci_nic

        return None

    def get_numa_node(self):
        topology = self.vm_details_from_nova['wrs-res:topology']
        found = re.match(r'\s*node:(\d+)\s*', topology)
        assert found, \
            'Error, no numa node info from nova show for VM:{}, nova show:{}'.format(self.vm_id, self.vm_details_from_nova)

        self.numa_node = int(found.group(1))

        return self.numa_node

    def check_numa_affinity(self, msg_prefx=''):

        LOG.tc_step('Check PCI numa on VM afer {}'.format(msg_prefx))

        numa_affinity = getattr(self, 'pci_numa_affinity', 'strict')

        if numa_affinity is None:
            # defaults to 'strict' for pci numa affinity
            numa_affinity = 'strict'

        assert numa_affinity in self.PCI_NUMA_AFFINITY_VALUES, \
            'Invalid value for PCI Numa Affinity: {}, \n\tValid values:{}'.format(
                numa_affinity, self.PCI_NUMA_AFFINITY_VALUES)

        vm_pci_infos, vm_topology = vm_helper.get_vm_pcis_irqs_from_hypervisor(self.vm_id)

        assert len(vm_pci_infos) > 0 and len(vm_topology), \
            'Empty output from nova-pci-interrupts'

        pci_addr_list = vm_pci_infos.pop('pci_addr_list')
        LOG.debug('after {}: pci addr list for VM:\nVM ID={}\nPCI-ADDR-LIST:{}\n'.format(
            msg_prefx, self.vm_id, pci_addr_list))

        # pci_numa_affinity pci_irq_affinity_mask', 'pci_alias'
        if self.pci_numa_affinity == 'strict' \
            or self.pci_irq_affinity_mask is not None or self.pci_alias is not None:

            numa_nodes_for_pcis = sorted(list(set([v['numa_node'] for v in vm_pci_infos.values()])))
            if len(numa_nodes_for_pcis) > 1:
                LOG.warn('after {}: PCIs on multiple Numa Nodes:'.format(numa_nodes_for_pcis))

            assert numa_nodes_for_pcis[0] == vm_topology['numa_node'],\
                'after {}: 1st Numa Nodes for PCIs differ from those of CPU, PCIs:{}, CPUs:{}'.format(
                    msg_prefx, numa_nodes_for_pcis[0], vm_topology['numa_node'])

            LOG.debug('OK, after {}: numa node for PCI is the same as numa node for CPU'.format(msg_prefx))

        # 'pci-passthrough', 'pci-sriov'
        if self.vif_model =='pci-passthrough':
            assert 'PF' in [v['type'] for v in vm_pci_infos.values()], \
                '{}: No PF/PCI-passthrough device found while having NIC of type:{}'.format(msg_prefx, self.vif_model)
            LOG.debug('OK, after {}: PCI of type:{} is created'.format(msg_prefx, self.vif_model))

        if self.vif_model =='pci-sriov':
            assert 'VF' in [v['type'] for v in vm_pci_infos.values()], \
                '{}: No VF/PCI-sriov device found while having NIC of type:{}'.format(msg_prefx, self.vif_model)
            LOG.debug('OK, after {}: PCI of type:{} is created'.format(msg_prefx, self.vif_model))

        expected_num_pci_alias = 0
        if self.pci_alias is not None:
            expected_num_pci_alias += int(self.pci_alias)
            if expected_num_pci_alias < 1:
                LOG.error('{}: zero or less number of PCI Alias specified in extra-specs:{}'.format(
                    msg_prefx, expected_num_pci_alias))

        expected_num_pci_alias += 1 if self.vif_model in ['pci-sriov'] else 0

        if expected_num_pci_alias > 0:
            cnt_vf = len([v['type'] for v in vm_pci_infos.values() if v['type'] == 'VF'])
            assert cnt_vf == expected_num_pci_alias, \
                '{}: Missmatched Number of PCI Alias, expected:{}, actual:{}'.format(
                    msg_prefx, expected_num_pci_alias, cnt_vf)
            LOG.debug('OK, after {}: correct number of PCI alias/devices are created'.format(msg_prefx, cnt_vf))

        if self.pci_irq_affinity_mask is not None:
            indices_to_pcpus = vm_helper.parse_cpu_list(self.pci_irq_affinity_mask)
            vm_pcpus = vm_topology['pcpus']

            expected_pcpus_for_irqs = sorted([vm_pcpus[i] for i in indices_to_pcpus])

            for pci_info in vm_pci_infos.values():
                assert expected_pcpus_for_irqs == sorted(pci_info['cpulist']), \
                    '{}: CPU list of IRQ:{} is not matching expected mask:{}'.format(
                        msg_prefx, pci_info['irq'], expected_pcpus_for_irqs)

        LOG.debug('OK, after {}: CPU list for all IRQ are consistent'.format(msg_prefx))

        LOG.info('OK, after {}: check_numa_affinity passed'.format(msg_prefx))

        return True

    def wait_check_vm_states(self, step='boot'):
        LOG.info('Check VM states after {}'.format(step))

        vm_helper.wait_for_vm_pingable_from_natbox(self.vm_id, fail_ok=False)

        self.vm_details_save = getattr(self, 'vm_details_from_nova', None)
        self.vm_details_from_nova = get_vm_details_from_nova(self.vm_id)
        # LOG.info('details from nova show:{}'.format(self.vm_details_from_nova))

        assert step in self.CHECKERS, 'Unknown step {} found in wait_check_vm_states()'.format(step)

        self.CHECKERS[step](self)

    def create_vm_with_pci_nic(self):
        res, vm_id, err, vol_id = vm_helper.boot_vm(name=self.vif_model, flavor=self.flavor_id, nics=self.nics_to_test)
        if vm_id:
            ResourceCleanup.add('vm', vm_id, del_vm_vols=False)
            pass
        if vol_id:
            ResourceCleanup.add('volume', vol_id)
            pass

        assert 0 == res, "VM is not booted successfully. Error: {}".format(err)

        self.vm_id = vm_id
        self.vol_id = vol_id

        if 'pci-passthrough' == self.vif_model:
            LOG.tc_step("Add vlan to pci-passthrough interface for VM.")
            vm_helper.add_vlan_for_vm_pcipt_interfaces(vm_id=vm_id, net_seg_id=self.seg_id)

        LOG.tc_step("Ping vm over mgmt and {} nets from base vm".format(self.net_type))
        vm_helper.ping_vms_from_vm(
            from_vm=self.vm_id, to_vms=self.vm_id, net_types=['mgmt', self.net_type], vlan_zero_only=True)
        vm_helper.ping_vms_from_vm(
            from_vm=self.base_vm, to_vms=self.vm_id, net_types=['mgmt', self.net_type], vlan_zero_only=True)

    def create_flavor_for_pci(self, vcpus=4, ram=1024):
        self.vcpus = vcpus
        self.ram = ram
        self.extra_specs = {}
        self.flavor_id = None

        flavor_id = nova_helper.create_flavor(name='dedicated_pci_extras',  vcpus=self.vcpus, ram=self.ram)[1]

        if flavor_id:
            ResourceCleanup.add('flavor', flavor_id)

            LOG.tc_step('Set extra-specs to the flavor {}'.format(flavor_id))
            extra_specs = {
                FlavorSpec.CPU_POLICY: 'dedicated',
                FlavorSpec.PCI_NUMA_AFFINITY: self.pci_numa_affinity,
                FlavorSpec.PCI_PASSTHROUGH_ALIAS: 'qat-vf:{}'.format(self.pci_alias) if self.pci_alias else None,
                FlavorSpec.PCI_IRQ_AFFINITY_MASK: self.pci_irq_affinity_mask}
            extra_specs = {k: str(v) for k, v in extra_specs.items() if v is not None}

            if extra_specs:
                nova_helper.set_flavor_extra_specs(flavor_id, **extra_specs)
                self.extra_specs = extra_specs

            self.flavor_id = flavor_id

    def is_pci_device_supported(self, pci_alias, nova_pci_devices=None):
        if nova_pci_devices is None:
            nova_pci_deivces = network_helper.get_pci_devices_info()

        self.nova_pci_deivces = nova_pci_deivces
        if not self.nova_pci_deivces:
            skip('No PCI devices existing! Note, currently "Coleto Creek PCIe Co-processor(0443/8086) is supported"')
        requested_vfs = int(pci_alias)
        min_vfs = min([int(v['pci_vfs_configured']) - int(v['pci_vfs_used'])
                       for v in nova_pci_deivces.values()])
        if min_vfs < requested_vfs:
            skip('Not enough PCI alias devices exit, only {} supported'.format(min_vfs))

    @mark.parametrize(('pci_numa_affinity', 'pci_irq_affinity_mask', 'pci_alias'), [
        mark.p1((None, None, None)),
        mark.p1(('strict', None, None)),
        mark.p2(('strict', '1,3', None)),
        mark.p1(('strict', None, '3')),
        mark.p2(('strict', '1,3', '3')),
        mark.p4(('prefer', None, None)),
    ])
    def test_pci_vm_nova_actions(self, pci_numa_affinity, pci_irq_affinity_mask, pci_alias, vif_model_check):
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
            - Verify the correct number of PCI devices are created, in correct types,
                    the numa node of the PCI devices aligns with that of CPUs, and affined CPUs for PCI devices
                    are same as specified by 'pci_alias' (if applicable)

        Teardown:
            - Delete created vms and flavor
        """

        self.pci_numa_affinity = pci_numa_affinity
        self.pci_alias = pci_alias
        self.pci_irq_affinity_mask = pci_irq_affinity_mask

        if pci_alias is not None:
            LOG.info('Check if PCI-Alias devices existing')
            self.is_pci_device_supported(pci_alias)

        self.vif_model, self.base_vm, self.base_flavor_id, self.nics_to_test, self.seg_id, self.net_type, self.pnet_id \
            = vif_model_check

        LOG.tc_step("Create a flavor with specified extra-specs and dedicated cpu policy")
        self.create_flavor_for_pci()

        LOG.tc_step("Boot a vm with {} vif model on internal net".format(self.vif_model))
        self.create_vm_with_pci_nic()

        self.wait_check_vm_states(step='boot')

        LOG.tc_step('Pause/Unpause {} vm'.format(self.vif_model))
        vm_helper.pause_vm(self.vm_id)
        vm_helper.unpause_vm(self.vm_id)
        LOG.tc_step("Check vm still pingable over mgmt and {} nets after pause/unpause".format(self.net_type))

        self.wait_check_vm_states(step='pause/unpause')

        LOG.tc_step('Suspend/Resume {} vm'.format(self.vif_model))
        vm_helper.suspend_vm(self.vm_id)
        vm_helper.resume_vm(self.vm_id)
        self.wait_check_vm_states(step='suspend/resume')

        if 'pci-passthrough' == self.vif_model:
            LOG.tc_step("Add/Check vlan interface is added to pci-passthrough device for vm {}.".format(self.vm_id))
            vm_helper.add_vlan_for_vm_pcipt_interfaces(vm_id=self.vm_id, net_seg_id=self.seg_id)

        LOG.tc_step("Check vm still pingable over mgmt and {} nets after suspend/resume".format(self.net_type))
        vm_helper.ping_vms_from_vm(
            from_vm=self.base_vm, to_vms=self.vm_id, net_types=['mgmt', self.net_type], vlan_zero_only=True)

        LOG.tc_step('Cold migrate {} vm'.format(self.vif_model))
        vm_helper.cold_migrate_vm(self.vm_id)

        self.wait_check_vm_states(step='cold-migrate')

        if 'pci-passthrough' == self.vif_model:
            LOG.tc_step("Add/Check vlan interface is added to pci-passthrough device for vm {}.".format(self.vm_id))
            vm_helper.add_vlan_for_vm_pcipt_interfaces(vm_id=self.vm_id, net_seg_id=self.seg_id)

        LOG.tc_step("Check vm still pingable over mgmt and {} nets after cold migration".format(self.net_type))
        vm_helper.ping_vms_from_vm(
            from_vm=self.base_vm, to_vms=self.vm_id, net_types=['mgmt', self.net_type], vlan_zero_only=True)

        LOG.tc_step('Set vm to error and wait for it to be auto recovered')
        vm_helper.set_vm_state(vm_id=self.vm_id, error_state=True, fail_ok=False)
        vm_helper.wait_for_vm_values(vm_id=self.vm_id, status=VMStatus.ACTIVE, fail_ok=False, timeout=600)

        LOG.tc_step("Check vm still pingable over mgmt and {} nets after auto recovery".format(self.net_type))

        self.wait_check_vm_states(step='set-error-state-recover')
        vm_helper.ping_vms_from_vm(
            from_vm=self.base_vm, to_vms=self.vm_id, net_types=['mgmt', self.net_type], vlan_zero_only=True)
