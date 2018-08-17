import re
import time
from pytest import fixture, mark, skip

from utils import cli
from utils import table_parser
from utils.tis_log import LOG

from consts.auth import Tenant
from consts.cgcs import FlavorSpec, VMStatus, DevClassID
from keywords import vm_helper, nova_helper, network_helper, host_helper, common
from testfixtures.fixture_resources import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


@fixture(scope='module', params=['pci-passthrough', 'pci-sriov'])
def vif_model_check(request):
    vif_model = request.param

    LOG.fixture_step("Get a network that supports {} to boot vm".format(vif_model))
    primary_tenant = Tenant.get_primary()
    primary_tenant_name = common.get_tenant_name(primary_tenant)
    other_tenant = Tenant.get_secondary()

    tenant_net = "{}-net"
    extra_pcipt_net = extra_pcipt_net_name = None
    pci_net = network_helper.get_pci_vm_network(pci_type=vif_model)
    if not pci_net:
        skip("{} interface not found".format(vif_model))

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
    vm_helper.wait_for_vm_pingable_from_natbox(base_vm)
    vm_helper.ping_vms_from_vm(base_vm, base_vm, net_types=['mgmt', net_type], vlan_zero_only=True)

    if vif_model == 'pci-passthrough':

        LOG.fixture_step("Get seg_id for {} to prepare for vlan tagging on pci-passthough device later".format(pci_net))
        seg_id = network_helper.get_net_info(net_id=pci_net_id, field='segmentation_id', strict=False,
                                             auto_info=Tenant.get('admin'))
        assert seg_id, 'Segmentation id of pci net {} is not found'.format(pci_net)

    else:
        seg_id = None

    nics_to_test = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
                   {'net-id': pci_net_id, 'vif-model': vif_model}]
    if extra_pcipt_net:
        nics_to_test.append({'net-id': extra_pcipt_net, 'vif-model': vif_model})
        extra_pcipt_seg_id = network_helper.get_net_info(net_id=extra_pcipt_net, field='segmentation_id', strict=False,
                                                         auto_info=Tenant.get('admin'))
        seg_id = {pci_net: seg_id,
                  extra_pcipt_net_name: extra_pcipt_seg_id}

    return vif_model, base_vm, flavor_id, nics_to_test, seg_id, net_type, pnet_id, extra_pcipt_net_name, extra_pcipt_net


@mark.p2
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

    # Remove the following ssh VM to sync code once CGTS-9279 is fixed
    LOG.tc_step("Login in to VM & do sync command")
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        vm_ssh.exec_sudo_cmd('sync')

    LOG.tc_step("Reboot vm host {}".format(host))
    vm_helper.evacuate_vms(host=host, vms_to_check=vm_id, ping_vms=True, wait_for_host_up=False)

    if 'pci-passthrough' == vif_model:
        LOG.tc_step("Add vlan to pci-passthrough interface for VM again after evacuation due to interface change.")
        vm_helper.add_vlan_for_vm_pcipt_interfaces(vm_id=vm_id, net_seg_id=seg_id)

    LOG.tc_step("Check vm still pingable over mgmt, and {} nets after evacuation".format(net_type))
    vm_helper.ping_vms_from_vm(from_vm=base_vm, to_vms=vm_id, net_types=['mgmt', net_type], vlan_zero_only=True)


@mark.p3
def test_pci_resource_usage(vif_model_check):
    """
    Create a vm under test with specified vifs for tenant network

    Returns (str): id of vm under test

    """
    vif_model, base_vm, flavor_id, nics_to_test, seg_id, net_type, pnet_id, extra_pcipt_net_name, extra_pcipt_net = \
        vif_model_check

    LOG.tc_step("Ensure core/vm quota is sufficient")

    if 'sriov' in vif_model:
        vm_type = 'sriov'
        resource_param = 'pci_vfs_used'
        max_resource = 'pci_vfs_configured'
    else:
        vm_type = 'pcipt'
        resource_param = 'pci_pfs_used'
        max_resource = 'pci_pfs_configured'

    LOG.tc_step("Get resource usage for {} interface before booting VM(s)".format(vif_model))
    LOG.info("provider net id for {} interface: {}".format(vif_model, pnet_id))

    assert pnet_id, "provider network id for {} interface is not found".format(vif_model)

    total_val, pre_resource_value = nova_helper.get_pci_interface_stats_for_providernet(
            pnet_id, fields=(max_resource, resource_param))
    LOG.info("Resource Usage {} for {}. Resource configured: {}".format(pre_resource_value, vif_model, total_val))

    expt_change = 2 if vif_model == 'pci-passthrough' and extra_pcipt_net else 1
    vm_limit = int((total_val - pre_resource_value) / expt_change) if vif_model == 'pci-passthrough' else 5
    inst_quota = nova_helper.get_quotas('instances')[0]
    if inst_quota < vm_limit + 5:
        nova_helper.update_quotas(instances=vm_limit + 5)
    vms_under_test = []
    for i in range(vm_limit):
        LOG.tc_step("Boot a vm with {} vif model on {} net".format(vif_model, net_type))
        vm_id = vm_helper.boot_vm(name=vif_model, flavor=flavor_id, cleanup='function', nics=nics_to_test)[1]
        vms_under_test.append(vm_id)

        vm_helper.wait_for_vm_pingable_from_natbox(vm_id, fail_ok=False)

        if vm_type == 'pcipt':
            LOG.tc_step("Add vlan to pci-passthrough interface for VM.")
            vm_helper.add_vlan_for_vm_pcipt_interfaces(vm_id=vm_id, net_seg_id=seg_id)

        LOG.tc_step("Ping vm over mgmt and {} nets from itself".format(net_type))
        vm_helper.ping_vms_from_vm(from_vm=vm_id, to_vms=vm_id, net_types=['mgmt', net_type])

        LOG.tc_step("Check resource usage for {} interface increased by 1".format(vif_model))
        resource_value = nova_helper.get_provider_net_info(pnet_id, field=resource_param)
        assert pre_resource_value + expt_change == resource_value, "Resource usage for {} is not increased by {}".\
            format(vif_model, expt_change)

        pre_resource_value = resource_value

    for vm_to_del in vms_under_test:
        LOG.tc_step("Check resource usage for {} interface reduced by 1 after deleting a vm".format(vif_model))
        vm_helper.delete_vms(vm_to_del, check_first=False, stop_first=False)
        resource_val = common.wait_for_val_from_func(expt_val=pre_resource_value - expt_change, timeout=30,
                                                     check_interval=3, func=nova_helper.get_provider_net_info,
                                                     providernet_id=pnet_id, field=resource_param)[1]

        assert pre_resource_value - expt_change == resource_val, "Resource usage for {} is not reduced by {}".\
            format(vif_model, expt_change)
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


def check_vm_hard_reboot(obj):
    obj.check_numa_affinity(msg_prefx='hard_reboot')


def _convert_irqmask_pcialias(irq_mask, pci_alias):
    if irq_mask is not None:
        irq_mask = irq_mask.split('irqmask_')[-1]
    if pci_alias is not None:
        pci_alias = pci_alias.split('pcialias_')[-1]

    return irq_mask, pci_alias


class TestVmPCIOperations:
    @fixture(scope='class')
    def pci_dev_numa_nodes(self, vif_model_check):
        vif_model = vif_model_check[0]
        hosts = host_helper.get_up_hypervisors()
        hosts_pci_numa = network_helper.get_pci_device_numa_nodes(hosts)
        hosts_pciif_procs = network_helper.get_pci_procs(hosts, net_type=vif_model)

        # Get number of hosts that has pcipt/sriov interface on same numa node as pci device
        numa_match = 0
        for host_ in hosts:
            LOG.info('\n\nPCI_NUMA_{}: {}; PCIIF_PROCS_{}: {}'.format(host_, hosts_pci_numa[host_], host_, hosts_pciif_procs[host_]))
            if set(hosts_pci_numa[host_]).intersection(set(hosts_pciif_procs[host_])):
                numa_match += 1
                if numa_match == 2:
                    break

        return numa_match

    NIC_PCI_TYPES = ['pci-passthrough', 'pci-sriov']
    PCI_NUMA_AFFINITY_VALUES = ['strict', 'prefer']

    CHECKERS = {'boot': check_vm_boot,
                'pause/unpause': check_vm_pause_unpause,
                'suspend/resume': check_vm_suspend_resume,
                'cold-migrate': check_vm_cold_migrate,
                'set-error-state-recover': check_vm_set_error_recover,
                'hard-reboot': check_vm_hard_reboot,
                }

    def get_pci_nic(self):
        nics = self.vm_details_from_nova['wrs-if:nics']

        self.pci_nic = None
        for nic in nics:
            nic_details = list(eval(nic).values())[0]
            if 'vif_model' in nic_details and nic_details['vif_model'] == self.vif_model and \
                            nic_details['network'] != self.extra_pcipt_net_name:
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

    def check_numa_affinity(self, msg_prefx='', retries=3, retry_interval=20):

        LOG.tc_step('Check PCIPT/SRIOV numa/irq-cpu-affinity/alias on VM afer {}'.format(msg_prefx))

        numa_affinity = getattr(self, 'pci_numa_affinity', 'strict')

        if numa_affinity is None:
            # defaults to 'strict' for pci numa affinity
            numa_affinity = 'strict'

        assert numa_affinity in self.PCI_NUMA_AFFINITY_VALUES, \
            'Invalid value for PCI Numa Affinity: {}, \n\tValid values:{}'.format(
                numa_affinity, self.PCI_NUMA_AFFINITY_VALUES)

        vm_pci_infos, vm_topology = vm_helper.get_vm_pcis_irqs_from_hypervisor(self.vm_id)

        assert len(vm_pci_infos) > 0, "No pci_devices info found"

        # pci_addr_list = vm_pci_infos.pop('pci_addr_list')
        # LOG.debug('after {}: pci addr list for VM:\nVM ID={}\nPCI-ADDR-LIST:{}\n'.format(
        #     msg_prefx, self.vm_id, pci_addr_list))

        # pci_numa_affinity pci_irq_affinity_mask', 'pci_alias'
        if self.pci_numa_affinity == 'strict' and \
                (self.pci_irq_affinity_mask is not None or self.pci_alias is not None):

            numa_nodes_for_pcis = sorted(list(set([v['node'] for v in vm_pci_infos.values()])))
            vm_numa_nodes = sorted([top_for_numa['node'] for top_for_numa in vm_topology])
            if len(numa_nodes_for_pcis) > 1:
                LOG.warn('after {}: PCIs on multiple Numa Nodes:'.format(numa_nodes_for_pcis))

            assert set(numa_nodes_for_pcis) <= set(vm_numa_nodes),\
                'after {}: 1st Numa Nodes for PCIs differ from those of CPU, PCIs:{}, CPUs:{}'.format(
                    msg_prefx, numa_nodes_for_pcis, vm_numa_nodes)

            LOG.debug('OK, after {}: numa node for PCI is the same as numa node for CPU'.format(msg_prefx))

        # 'pci-passthrough', 'pci-sriov'
        if self.vif_model == 'pci-passthrough':
            assert 'PF' in [v['type'] for v in vm_pci_infos.values()], \
                '{}: No PF/PCI-passthrough device found while having NIC of type:{}'.format(msg_prefx, self.vif_model)
            LOG.debug('OK, after {}: PCI of type:{} is created'.format(msg_prefx, self.vif_model))

        if self.vif_model == 'pci-sriov':
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
            count = 0
            cpus_matched = False

            while not cpus_matched and count < retries:
                count += 1

                indices_to_pcpus = vm_helper.parse_cpu_list(self.pci_irq_affinity_mask)

                vm_pcpus = []
                for top_per_numa in vm_topology:
                    vm_pcpus += top_per_numa['pcpus']

                expected_pcpus_for_irqs = sorted([vm_pcpus[i] for i in indices_to_pcpus])

                cpus_matched = True
                for pci_info in vm_pci_infos.values():
                    if 'cpulist' in pci_info and expected_pcpus_for_irqs != sorted(pci_info['cpulist']):
                        LOG.warn(
                            'Mismatched CPU list after {}: expected/affin-mask cpu list:{}, actual:{}, '
                            'pci_info:{}'.format(msg_prefx, expected_pcpus_for_irqs, pci_info['cpulist'], pci_info))

                        LOG.warn('retries:{}'.format(count))
                        cpus_matched = False
                        break
                vm_pci_infos.clear()
                vm_topology.clear()

                time.sleep(retry_interval)
                vm_pci_infos, vm_topology = vm_helper.get_vm_pcis_irqs_from_hypervisor(self.vm_id)
                # vm_pci_infos.pop('pci_addr_list')

            assert cpus_matched, \
                '{}: CPU list is not matching expected mask after tried {} times'.format(msg_prefx, count)

            LOG.info('after {}: pci_irq_affinity_mask checking passed after retries:{}\n'.format(msg_prefx, count))

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

    def create_flavor_for_pci(self, vcpus=4, ram=1024):
        self.vcpus = vcpus
        self.ram = ram
        self.extra_specs = {}
        self.flavor_id = None

        flavor_id = nova_helper.create_flavor(name='dedicated_pci_extras',  vcpus=self.vcpus, ram=self.ram)[1]

        if flavor_id:
            ResourceCleanup.add('flavor', flavor_id)

            pci_alias_spec = '{}:{}'.format(self.pci_alias_names[0], self.pci_alias) if self.pci_alias else None
            LOG.tc_step('Set extra-specs to the flavor {}'.format(flavor_id))
            extra_specs = {
                FlavorSpec.CPU_POLICY: 'dedicated',
                FlavorSpec.PCI_NUMA_AFFINITY: self.pci_numa_affinity,
                FlavorSpec.PCI_PASSTHROUGH_ALIAS: pci_alias_spec,
                FlavorSpec.PCI_IRQ_AFFINITY_MASK: self.pci_irq_affinity_mask}
            extra_specs = {k: str(v) for k, v in extra_specs.items() if v is not None}

            if extra_specs:
                nova_helper.set_flavor_extra_specs(flavor_id, **extra_specs)
                self.extra_specs = extra_specs

            self.flavor_id = flavor_id

    def is_pci_device_supported(self, pci_alias, nova_pci_devices=None):
        if nova_pci_devices is None:
            # qat-vf devices only
            nova_pci_devices = network_helper.get_pci_devices_info(class_id=DevClassID.QAT_VF)

        # self.nova_pci_devices = nova_pci_devices
        if not nova_pci_devices:
            skip('No PCI devices existing! Note, currently "Coleto Creek PCIe Co-processor(0443/8086) is supported"')
        requested_vfs = int(pci_alias)

        free_vfs_num = {}
        for dev, dev_dict in nova_pci_devices.items():
            for host, dev_info in dev_dict.items():
                avail_vfs_on_host = int(dev_info['pci_vfs_configured']) - int(dev_info['pci_vfs_used'])
                free_vfs_num[host] = free_vfs_num.pop(host, 0) + avail_vfs_on_host

        min_vfs = min(list(free_vfs_num.values()))

        if min_vfs < requested_vfs:
            skip('Not enough PCI alias devices exit, only {} supported'.format(min_vfs))

        self.pci_alias_names = list(nova_pci_devices.keys())


    @mark.nics
    @mark.parametrize(('pci_numa_affinity', 'pci_irq_affinity_mask', 'pci_alias'), [
        mark.p1((None, None, None)),
        mark.p1(('strict', None, None)),
        mark.nightly(('strict', 'irqmask_1,3', None)),
        mark.p1(('strict', None, 'pcialias_3')),
        mark.p2(('strict', 'irqmask_1,3', 'pcialias_3')),
        # mark.p3(('prefer', '1,3', '3')),  # TODO: expt behavior on msi_irq > cpulist mapping unknown
        # mark.p3(('prefer', None, None)),  # TODO same as above
    ])
    def test_pci_vm_nova_actions(self, pci_numa_affinity, pci_irq_affinity_mask, pci_alias, vif_model_check,
                                 pci_dev_numa_nodes):
        """
        Test vm actions on vm with multiple ports with given vif models on the same tenant network

        Args:

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
        pci_irq_affinity_mask, pci_alias = _convert_irqmask_pcialias(pci_irq_affinity_mask, pci_alias)
        boot_forbidden = False
        migrate_forbidden = False
        if pci_numa_affinity == 'strict' and pci_alias is not None:
            host_count = pci_dev_numa_nodes
            if host_count == 0:
                boot_forbidden = True
            elif host_count == 1:
                migrate_forbidden = True
        LOG.tc_step("Expected result - Disallow boot: {}; Disallow migrate: {}".format(boot_forbidden,
                                                                                       migrate_forbidden))

        self.pci_numa_affinity = pci_numa_affinity
        self.pci_alias = pci_alias
        self.pci_irq_affinity_mask = pci_irq_affinity_mask

        if pci_alias is not None:
            LOG.info('Check if PCI-Alias devices existing')
            self.is_pci_device_supported(pci_alias)

        self.vif_model, self.base_vm, self.base_flavor_id, self.nics_to_test, self.seg_id, self.net_type, \
            self.pnet_id, self.extra_pcipt_net_name, self.extra_pcipt_net = vif_model_check

        LOG.tc_step("Create a flavor with specified extra-specs and dedicated cpu policy")
        self.create_flavor_for_pci()

        LOG.tc_step("Boot a vm with {} vif model on internal net".format(self.vif_model))
        resource_param = 'pci_vfs_used' if 'sriov' in self.vif_model else 'pci_pfs_used'

        LOG.tc_step("Get resource usage for {} interface before booting VM(s)".format(self.vif_model))
        pre_resource_value = nova_helper.get_provider_net_info(self.pnet_id, field=resource_param)

        res, vm_id, err, vol_id = vm_helper.boot_vm(name=self.vif_model, flavor=self.flavor_id, cleanup='function',
                                                    nics=self.nics_to_test, fail_ok=boot_forbidden)
        if boot_forbidden:
            assert res > 0, "VM booted successfully while it numa node for pcipt/sriov and pci alias mismatch"
            return

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

        self.wait_check_vm_states(step='boot')

        LOG.tc_step("Check {} usage is incremented by 1".format(resource_param))
        post_resource_value = nova_helper.get_provider_net_info(self.pnet_id, field=resource_param)
        expt_change = 2 if self.vif_model == 'pci-passthrough' and self.extra_pcipt_net else 1
        assert pre_resource_value + expt_change == post_resource_value, "{} usage is not incremented by {} as " \
                                                                        "expected".format(resource_param, expt_change)

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
        code, msg = vm_helper.cold_migrate_vm(self.vm_id, fail_ok=migrate_forbidden)
        if migrate_forbidden:
            assert code > 0, "Expect migrate fail due to no other host has pcipt/sriov and pci-alias on same numa. " \
                             "Actual: {}".format(msg)

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

        LOG.tc_step("Hard reboot {} vm".format(self.vif_model))
        vm_helper.reboot_vm(self.vm_id, hard=True)
        LOG.tc_step("Check vm still pingable over mgmt and {} nets after nova reboot hard".format(self.net_type))
        self.wait_check_vm_states(step='hard-reboot')
        vm_helper.ping_vms_from_vm(
                from_vm=self.base_vm, to_vms=self.vm_id, net_types=['mgmt', self.net_type], vlan_zero_only=True)

        LOG.fixture_step("Create a flavor with dedicated cpu policy")
        resize_flavor = nova_helper.create_flavor(name='dedicated', ram=2048)[1]
        ResourceCleanup.add('flavor', resize_flavor, scope='module')

        extra_specs = {FlavorSpec.CPU_POLICY: 'dedicated'}
        nova_helper.set_flavor_extra_specs(flavor=resize_flavor, **extra_specs)

        origin_host = nova_helper.get_vm_host(vm_id=vm_id)
        LOG.info("Orignal host where VM {} hosted is {}".format(vm_id, origin_host))
        LOG.tc_step("Resize the vm and verify if it becomes Active")
        vm_helper.resize_vm(self.vm_id, resize_flavor)
        new_host = nova_helper.get_vm_host(self.vm_id)
        LOG.info("New host where VM {} resized {}".format(vm_id, new_host))
        vm_helper.ping_vms_from_vm(
                from_vm=self.base_vm, to_vms=self.vm_id, net_types=['mgmt', self.net_type], vlan_zero_only=True)
