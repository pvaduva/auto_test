from pytest import fixture, skip, mark

from utils.tis_log import LOG

from consts.auth import Tenant
from consts.cgcs import FlavorSpec
from keywords import vm_helper, nova_helper, network_helper, host_helper, common, system_helper
from testfixtures.fixture_resources import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover

"""
Userstory: us53856 & US58643 Robustness testcases
Test plan: /teststrategies/cgcs2.0/us53856_us58643_sriov_test_strategy.txt

Notes:
- PCIPT Tests are best to run in CX4 lab (2 pcipt nics for each vm) with 3+ computes (able to move vm to other host)
"""


def check_vm_pci_interface(vms, net_type, seg_id=None):
    for vm in vms:
        vm_helper.wait_for_vm_pingable_from_natbox(vm)

    LOG.tc_step("Check vms mgmt and {} interfaces reachable from other vm".format(net_type))
    if seg_id:
        for vm_id in vms:
            vm_helper.add_vlan_for_vm_pcipt_interfaces(vm_id=vm_id, net_seg_id=seg_id)

    # Ensure pci interface working well
    vm_helper.ping_vms_from_vm(vms, vms[0], net_types=['mgmt', net_type], vlan_zero_only=True)


def get_pci_net(request, vif_model, primary_tenant, primary_tenant_name, other_tenant):
    LOG.fixture_step("Get a PCI network to boot vm from pci providernet")
    # pci_nets = network_helper.get_pci_nets(vif=interface, rtn_val='name')
    tenant_net = "{}-net"
    other_pcipt_net_name = other_pcipt_net_id = None

    # This assumes pci hosts are configured with the same provider networks
    pci_net_name = network_helper.get_pci_vm_network(pci_type=vif_model)

    if isinstance(pci_net_name, list):
        pci_net_name, other_pcipt_net_name = pci_net_name
        other_pcipt_net_id = network_helper.get_net_id_from_name(other_pcipt_net_name)

    if not pci_net_name:
        skip('No {} net found on up host(s)'.format(vif_model))

    if 'mgmt' in pci_net_name:
        skip("Only management networks have {} interface.".format(vif_model))

    if 'internal' in pci_net_name:
        net_type = 'internal'
    else:
        net_type = 'data'
        if tenant_net.format(primary_tenant_name) not in pci_net_name:
            Tenant.set_primary(other_tenant)

            def revert_tenant():
                Tenant.set_primary(primary_tenant)

            request.addfinalizer(revert_tenant)

    pci_net_id = network_helper._get_net_ids(net_name=pci_net_name)[0]
    pnet_name = network_helper.get_net_info(net_id=pci_net_id, field='provider:physical_network')
    pnet_id = network_helper.get_providernets(name=pnet_name, rtn_val='id', strict=True)[0]

    LOG.info("PCI network selected to boot vm: {}".format(pci_net_name))
    if vif_model == 'pci-sriov':
        return net_type, pci_net_name, pci_net_id, pnet_id, pnet_name
    else:
        return net_type, pci_net_name, pci_net_id, pnet_id, pnet_name, other_pcipt_net_name, other_pcipt_net_id


def get_pci_vm_nics(vif_model, pci_net_id, other_pci_net_id=None):
    mgmt_net_id = network_helper.get_mgmt_net_id()
    nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
            {'net-id': pci_net_id, 'vif-model': vif_model}]
    if other_pci_net_id:
        nics.append({'net-id': other_pci_net_id, 'vif-model': vif_model})

    return nics


@fixture(scope='module')
def pci_prep():
    primary_tenant = Tenant.get_primary()
    primary_tenant_name = common.get_tenant_name(primary_tenant)
    other_tenant = Tenant.TENANT2 if primary_tenant_name == 'tenant1' else Tenant.TENANT1

    nova_helper.update_quotas(tenant='tenant1', cores=100)
    nova_helper.update_quotas(tenant='tenant2', cores=100)
    return primary_tenant, primary_tenant_name, other_tenant


def get_pci_hosts(vif_model, pnet_name):
    valid_pci_hosts = []
    hosts_and_pnets = host_helper.get_hosts_and_pnets_with_pci_devs(pci_type=vif_model, up_hosts_only=True)
    for key, val in hosts_and_pnets.items():
        if pnet_name in val:
            valid_pci_hosts.append(key)

    if len(valid_pci_hosts) < 2:
        skip("Less than 2 hosts configured with pci-sriov interface with same provider network")

    return valid_pci_hosts


def get_host_with_min_vm_cores_per_proc(candidate_hosts):
    # Get initial host with least vcpus
    min_cores_per_proc = 200
    min_core_host = None
    for host_ in candidate_hosts:
        proc0_cores, proc1_cores = host_helper.get_logcores_counts(host_, proc_ids=(0, 1), thread=['0', '1'],
                                                                   functions='VMs')
        min_cores = min(proc0_cores, proc1_cores)
        if min_cores < min_cores_per_proc:
            min_cores_per_proc = min_cores
            min_core_host = host_

    return min_core_host, min_cores_per_proc


class TestSriov:
    @fixture(scope='class')
    def sriov_prep(self, request, pci_prep, add_cgcsauto_zone):
        primary_tenant, primary_tenant_name, other_tenant = pci_prep
        vif_model = 'pci-sriov'

        net_type, pci_net, pci_net_id, pnet_id, pnet_name = get_pci_net(request, vif_model, primary_tenant,
                                                                        primary_tenant_name, other_tenant)

        LOG.fixture_step("Calculate number of vms and number of vcpus for each vm")
        pci_hosts = get_pci_hosts(vif_model, pnet_name)
        vfs_conf, vfs_use_init = nova_helper.get_pci_interface_stats_for_providernet(
                pnet_id, fields=('pci_vfs_configured', 'pci_vfs_used'))

        # TODO vfs configured per host is inaccurate when hosts are configured differently
        vfs_conf_per_host = vfs_conf/len(pci_hosts)
        if vfs_conf_per_host < 4:
            skip('Less than 4 {} interfaces configured on each host'.format(vif_model))
        pci_hosts = pci_hosts[:2]

        vm_num = min(4, int(vfs_conf_per_host / 4) * 2)

        initial_host, min_cores_per_proc = get_host_with_min_vm_cores_per_proc(pci_hosts)
        other_host = pci_hosts[0] if initial_host == pci_hosts[1] else pci_hosts[1]
        vm_vcpus = int(min_cores_per_proc / (vm_num/2))

        def remove_host_from_zone():
            LOG.fixture_step("Remove {} hosts from cgcsauto zone".format(vif_model))
            nova_helper.remove_hosts_from_aggregate(aggregate='cgcsauto', check_first=False)
        request.addfinalizer(remove_host_from_zone)

        LOG.fixture_step("Add {} hosts to cgcsauto zone: {}".format(vif_model, pci_hosts))
        nova_helper.add_hosts_to_aggregate(aggregate='cgcsauto', hosts=pci_hosts)

        nics = get_pci_vm_nics(vif_model, pci_net_id)

        return net_type, pci_net, pci_hosts, pnet_id, nics, initial_host, other_host, vfs_use_init, vm_num, vm_vcpus

    @mark.nics
    def test_sriov_robustness(self, sriov_prep, add_admin_role_func):
        """
        Exhaust all CPUs on one compute by spawning VMs with 2 SR-IOV interface

        Args:
            sriov_prep: test fixture to set up test environment and get proper pci nets/hosts

        Setups:
            - select two hosts configured with same pci-sriov providernet
            - add the two hosts to cgcsauto aggregate to limit the vms host to the selected hosts
            - Select one network under above providernet

        Test Steps:
            - Boot 2+ pci-sriov vms with pci-sriov vif over selected network onto same host
            - Verify resource usage for providernet is increased as expected
            - Lock vms host and ensure vms are all migrated to other host
            - Verify vms' pci-sriov interfaces reachable and resource usage for pnet unchanged
            - 'sudo reboot -f' new vms host, and ensure vms are evacuated to initial host
            - Verify vms' pci-sriov interfaces reachable and resource usage for pnet unchanged

        Teardown:
            - Delete vms, volumes, flavor created
            - Remove admin role to tenant
            - Recover hosts if applicable
            - Remove cgcsauto aggregate     - class

        """
        net_type, pci_net, pci_hosts, pnet_id, nics, initial_host, other_host, vfs_use_init, vm_num, vm_vcpus = \
            sriov_prep
        vif_model = 'pci-sriov'

        # proc0_vm, proc1_vm = host_helper.get_logcores_counts(initial_host, functions='VMs')
        # if system_helper.is_hyperthreading_enabled(initial_host):
        #     proc0_vm *= 2
        #     proc1_vm *= 2
        # vm_vcpus = int(min(proc1_vm, proc0_vm) / (vm_num/2))

        # Create flavor with calculated vcpu number
        LOG.tc_step("Create a flavor with dedicated cpu policy and {} vcpus".format(vm_vcpus))
        flavor_id = nova_helper.create_flavor(name='dedicated_{}vcpu'.format(vm_vcpus), ram=1024, vcpus=vm_vcpus)[1]
        ResourceCleanup.add('flavor', flavor_id, scope='module')
        extra_specs = {FlavorSpec.CPU_POLICY: 'dedicated', FlavorSpec.PCI_NUMA_AFFINITY: 'prefer'}
        nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

        # Boot vms with 2 {} vifs each, and wait for pingable
        LOG.tc_step("Boot {} vms with 2 {} vifs each".format(vm_num, vif_model))
        vms = []
        for i in range(vm_num):
            sriov_nics = nics.copy()
            sriov_nic2 = sriov_nics[-1].copy()
            sriov_nic2['port-id'] = network_helper.create_port(net_id=sriov_nic2.pop('net-id'), vnic_type='direct')[1]
            sriov_nics.append(sriov_nic2)
            LOG.info("Booting vm{}...".format(i + 1))
            vm_id = vm_helper.boot_vm(flavor=flavor_id, nics=sriov_nics, cleanup='function',
                                      vm_host=initial_host, avail_zone='cgcsauto')[1]
            vms.append(vm_id)
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

        check_vm_pci_interface(vms=vms, net_type=net_type)
        vfs_use_post_boot = nova_helper.get_provider_net_info(pnet_id, field='pci_vfs_used')
        assert vfs_use_post_boot - vfs_use_init == vm_num * 2, "Number of PCI vfs used is not as expected"

        HostsToRecover.add(pci_hosts)

        LOG.tc_step("Lock host of {} vms: {}".format(vif_model, initial_host))
        host_helper.lock_host(host=initial_host, check_first=False, swact=True)

        LOG.tc_step("Check vms are migrated to other host: {}".format(other_host))
        for vm in vms:
            vm_host = nova_helper.get_vm_host(vm_id=vm)
            assert other_host == vm_host, "VM did not move to {} after locking {}".format(other_host, initial_host)

        check_vm_pci_interface(vms, net_type=net_type)
        vfs_use_post_lock = nova_helper.get_provider_net_info(pnet_id, field='pci_vfs_used')
        assert vfs_use_post_boot == vfs_use_post_lock, "Number of PCI vfs used after locking host is not as expected"

        LOG.tc_step("Unlock {}".format(initial_host))
        host_helper.unlock_host(initial_host)

        LOG.tc_step("Reboot {} and ensure vms are evacuated to {}".format(other_host, initial_host))
        vm_helper.evacuate_vms(other_host, vms, post_host=initial_host, wait_for_host_up=True)
        check_vm_pci_interface(vms, net_type=net_type)
        vfs_use_post_evac = nova_helper.get_provider_net_info(pnet_id, field='pci_vfs_used')
        assert vfs_use_post_boot == vfs_use_post_evac, "Number of PCI vfs used after evacuation is not as expected"


class TestPcipt:
    @fixture(scope='class')
    def pcipt_prep(self, request, pci_prep):
        primary_tenant, primary_tenant_name, other_tenant = pci_prep
        vif_model = 'pci-passthrough'

        net_type, pci_net_name, pci_net_id, pnet_id, pnet_name, other_pcipt_net_name, other_pcipt_net_id = \
            get_pci_net(request, vif_model, primary_tenant, primary_tenant_name, other_tenant)
        pci_hosts = get_pci_hosts(vif_model, pnet_name)
        if len(pci_hosts) < 2:
            skip('Less than 2 hosts with {} interface configured'.format(vif_model))

        pfs_conf, pfs_use_init = nova_helper.get_pci_interface_stats_for_providernet(
                pnet_id, fields=('pci_pfs_configured', 'pci_pfs_used'))
        if pfs_conf < 2:
            skip('Less than 2 {} interfaces configured on system'.format(vif_model))

        # Get initial host with least vcpus
        LOG.fixture_step("Calculate number of vms and number of vcpus for each vm")
        vm_num = 2
        min_vcpu_host, min_cores_per_proc = get_host_with_min_vm_cores_per_proc(pci_hosts)
        vm_vcpus = int(min_cores_per_proc / (vm_num / 2))

        LOG.fixture_step("Get seg_id for {} for vlan tagging on pci-passthough device later".format(pci_net_id))
        seg_id = network_helper.get_net_info(net_id=pci_net_id, field='segmentation_id', strict=False,
                                             auto_info=Tenant.ADMIN)
        assert seg_id, 'Segmentation id of pci net {} is not found'.format(pci_net_id)

        if other_pcipt_net_name:
            extra_pcipt_seg_id = network_helper.get_net_info(net_id=other_pcipt_net_name, field='segmentation_id',
                                                             strict=False,
                                                             auto_info=Tenant.ADMIN)
            seg_id = {pci_net_name: seg_id,
                      other_pcipt_net_name: extra_pcipt_seg_id}

        nics = get_pci_vm_nics(vif_model, pci_net_id, other_pcipt_net_id)

        return net_type, pci_net_name, pci_hosts, pnet_id, nics, min_vcpu_host, seg_id, vm_num, vm_vcpus, pfs_use_init

    @mark.nics
    def test_pcipt_robustness(self, pcipt_prep):
        """
        TC3_robustness: PCI-passthrough by locking and rebooting pci_vm host

        Args:
            pcipt_prep: test fixture to set up test environment and get proper pci nets/hosts/seg_id

        Setups:
            - select a providernet with pcipt interfaces configured
            - get pci hosts configured with same above providernet
            - get one network under above providernet (or two for CX4 nic)

        Test Steps:
            - Boot 2 pcipt vms with pci-passthrough vif over selected network
            - Verify resource usage for providernet is increased as expected
            - Lock pci_vm host and ensure vm migrated to other host (or fail to lock if no other pcipt host available)
            - Repeat above step for another pcipt vm
            - Verify vms' pci-pt interfaces reachable and resource usage for pnet unchanged
            - 'sudo reboot -f' pci_vm host, and ensure vm evacuated or up on same host if no other pcipt host available
            - Repeat above step for another pcipt vm
            - Verify vms' pci-pt interfaces reachable and resource usage for pnet unchanged

        Teardown:
            - Delete vms, volumes, flavor created
            - Recover hosts if applicable
        
        """
        net_type, pci_net_name, pci_hosts, pnet_id, nics, min_vcpu_host, seg_id, vm_num, vm_vcpus, pfs_use_init = \
            pcipt_prep
        vif_model = 'pci-passthrough'

        # Create flavor with calculated vcpu number
        LOG.fixture_step("Create a flavor with dedicated cpu policy and {} vcpus".format(vm_vcpus))
        flavor_id = nova_helper.create_flavor(name='dedicated_{}vcpu'.format(vm_vcpus), ram=1024, vcpus=vm_vcpus)[1]
        ResourceCleanup.add('flavor', flavor_id, scope='module')
        extra_specs = {FlavorSpec.CPU_POLICY: 'dedicated', FlavorSpec.PCI_NUMA_AFFINITY: 'prefer'}
        nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

        # Boot vms with 2 {} vifs each, and wait for pingable
        LOG.tc_step("Boot {} vms with 2 {} vifs each".format(vm_num, vif_model))
        vms = []
        for i in range(vm_num):
            LOG.info("Booting pci-passthrough vm{}".format(i+1))
            vm_id = vm_helper.boot_vm(flavor=flavor_id, nics=nics, cleanup='function')[1]
            vms.append(vm_id)
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
            vm_helper.add_vlan_for_vm_pcipt_interfaces(vm_id, seg_id)

        pfs_use_post_boot = nova_helper.get_provider_net_info(pnet_id, field='pci_pfs_used')
        resource_change = 2 if isinstance(seg_id, dict) else 1
        assert pfs_use_post_boot - pfs_use_init == vm_num * resource_change, "Number of PCI pfs used is not as expected"

        check_vm_pci_interface(vms=vms, net_type=net_type)
        HostsToRecover.add(pci_hosts)

        pfs_use_pre_action = pfs_use_post_boot
        iter_count = 2 if len(pci_hosts) < 3 else 1
        for i in range(iter_count):
            if i == 1:
                LOG.tc_step("Delete a pcipt vm and test lock and reboot pcipt host again for success pass")
                vm_helper.delete_vms(vms=vms[1])
                vms.pop()
                pfs_use_pre_action -= resource_change
                common.wait_for_val_from_func(expt_val=pfs_use_pre_action, timeout=30, check_interval=3,
                                              func=nova_helper.get_provider_net_info,
                                              providernet_id=pnet_id, field='pci_pfs_used')

            LOG.tc_step("Test lock {} vms hosts started - iter{}".format(vif_model, i+1))
            for vm in vms:
                pre_lock_host = nova_helper.get_vm_host(vm)
                assert pre_lock_host in pci_hosts, "VM is not booted on pci_host"

                LOG.tc_step("Lock host of {} vms: {}".format(vif_model, pre_lock_host))
                code, output = host_helper.lock_host(host=pre_lock_host, check_first=False, swact=True, fail_ok=True)
                post_lock_host = nova_helper.get_vm_host(vm)
                assert post_lock_host in pci_hosts, "VM is not on pci host after migrating"

                if len(pci_hosts) < 3 and i == 0:
                    assert 5 == code, "Expect host-lock fail due to migration of vm failure. Actual: {}".format(output)
                    assert pre_lock_host == post_lock_host, "VM host should not change when no other host to migrate to"
                else:
                    assert 0 == code, "Expect host-lock successful. Actual: {}".format(output)
                    assert pre_lock_host != post_lock_host, "VM host did not change"
                    LOG.tc_step("Unlock {}".format(pre_lock_host))

                check_vm_pci_interface(vms, net_type=net_type)
                host_helper.unlock_host(pre_lock_host, available_only=True)

            pfs_use_post_lock = nova_helper.get_provider_net_info(pnet_id, field='pci_pfs_used')
            assert pfs_use_pre_action == pfs_use_post_lock, "Number of PCI pfs used after host-lock is not as expected"

            LOG.tc_step("Test evacuate {} vms started - iter{}".format(vif_model, i+1))
            for vm in vms:
                pre_evac_host = nova_helper.get_vm_host(vm)

                LOG.tc_step("Reboot {} and ensure {} vm are evacuated when applicable".format(pre_evac_host, vif_model))
                code, output = vm_helper.evacuate_vms(pre_evac_host, vm, fail_ok=True, wait_for_host_up=True)

                if len(pci_hosts) < 3 and i == 0:
                    assert 2 == code, "Expect vm stay on same host due to migration fail. Actual:{}".format(output)
                else:
                    assert 0 == code, "Expect vm evacuated to other host. Actual: {}".format(output)

                post_evac_host = nova_helper.get_vm_host(vm)
                assert post_evac_host in pci_hosts, "VM is not on pci host after evacuation"

                check_vm_pci_interface(vms, net_type=net_type)

            pfs_use_post_evac = nova_helper.get_provider_net_info(pnet_id, field='pci_pfs_used')
            assert pfs_use_pre_action == pfs_use_post_evac, "Number of PCI pfs used after evacuation is not as expected"
