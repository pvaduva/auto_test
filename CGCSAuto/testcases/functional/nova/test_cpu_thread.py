import math
from pytest import mark, fixture, skip

from utils.tis_log import LOG

from consts.cgcs import FlavorSpec
from consts.cli_errs import CPUThreadErr, SharedCPUErr

from keywords import nova_helper, system_helper, vm_helper, host_helper
from testfixtures.resource_mgmt import ResourceCleanup


@mark.parametrize(('cpu_policy', 'cpu_thread_policy', 'shared_vcpu', 'min_vcpus', 'expt_err'), [
    mark.p1((None, 'isolate', None, None, 'CPUThreadErr.DEDICATED_CPU_REQUIRED')),
    mark.p1((None, 'require', None, None, 'CPUThreadErr.DEDICATED_CPU_REQUIRED')),
    mark.p1(('shared', 'isolate', None, None, 'CPUThreadErr.DEDICATED_CPU_REQUIRED')),
    mark.p1(('shared', 'require', None, None, 'CPUThreadErr.DEDICATED_CPU_REQUIRED')),
    mark.p3(('dedicated', '', None, None, 'CPUThreadErr.INVALID_POLICY')),
    mark.p3(('dedicated', 'requi', None, None, 'CPUThreadErr.INVALID_POLICY')),
    mark.p3(('dedicated', '', None, None, 'CPUThreadErr.INVALID_POLICY')),
    mark.p3(('dedicated', 'REQUIRE', None, None, 'CPUThreadErr.INVALID_POLICY')),
    mark.p3(('dedicated', 'AOID', None, None, 'CPUThreadErr.INVALID_POLICY')),
    mark.p3(('dedicated', 'ISOLATE', None, None, 'CPUThreadErr.INVALID_POLICY')),
    mark.p3((None, None, '1', None, 'SharedCPUErr.DEDICATED_CPU_REQUIRED')),
    mark.p3(('shared', None, '0', None, 'SharedCPUErr.DEDICATED_CPU_REQUIRED')),
    mark.p2(('dedicated', 'isolate', '0', None, 'CPUThreadErr.UNSET_SHARED_VCPU')),
    mark.p2(('dedicated', 'require', '1', None, 'CPUThreadErr.UNSET_SHARED_VCPU')),
    mark.p2(('dedicated', 'require', None, '2', 'CPUThreadErr.UNSET_MIN_VCPUS')),     # Allowed with isolate

])
def test_cpu_thread_flavor_set_negative(cpu_policy, cpu_thread_policy, shared_vcpu, min_vcpus, expt_err):
    LOG.tc_step("Create a flavor with 2 vcpus")
    flavor_id = nova_helper.create_flavor(name='cpu_thread_neg1', check_storage_backing=False, vcpus=2)[1]
    ResourceCleanup.add('flavor', flavor_id)

    specs_dict = {FlavorSpec.CPU_POLICY: cpu_policy,
                  FlavorSpec.CPU_THREAD_POLICY: cpu_thread_policy,
                  FlavorSpec.SHARED_VCPU: shared_vcpu,
                  FlavorSpec.MIN_VCPUS: min_vcpus
                  }

    specs_to_set = {}
    for key, value in specs_dict.items():
        if value is not None:
            specs_to_set[key] = value

    LOG.tc_step("Attempt to set following flavor extra specs: {}".format(specs_to_set))
    code, output = nova_helper.set_flavor_extra_specs(flavor_id, fail_ok=True, **specs_to_set)

    LOG.tc_step("Verify cli rejected invalid extra specs setting with proper error message.")
    expt_err_eval = eval(expt_err)
    if expt_err in ['CPUThreadErr.INVALID_POLICY', 'CPUThreadErr.UNSET_SHARED_VCPU', 'CPUThreadErr.UNSET_MIN_VCPUS']:
        expt_err_eval = expt_err_eval.format(cpu_thread_policy)

    assert 1 == code, 'Set flavor extra spec is not rejected with invalid extra spec settings: {}.'.format(specs_to_set)
    assert expt_err_eval in output


@mark.parametrize(('specs_preset', 'specs_to_set', 'expt_err'), [
    mark.p2(({FlavorSpec.CPU_POLICY: 'dedicated', FlavorSpec.CPU_THREAD_POLICY: 'isolate'}, {FlavorSpec.SHARED_VCPU: '1'}, 'CPUThreadErr.UNSET_SHARED_VCPU')),
    mark.p2(({FlavorSpec.CPU_POLICY: 'dedicated', FlavorSpec.SHARED_VCPU: '0'}, {FlavorSpec.CPU_THREAD_POLICY: 'require'}, 'CPUThreadErr.UNSET_SHARED_VCPU')),
])
def test_cpu_thread_flavor_add_negative(specs_preset, specs_to_set, expt_err):
    LOG.tc_step("Create a flavor with 2 vcpus")
    flavor_id = nova_helper.create_flavor(name='cpu_thread_neg1', check_storage_backing=False, vcpus=2)[1]
    ResourceCleanup.add('flavor', flavor_id)

    LOG.tc_step("Set following extra specs: {}".format(specs_preset))
    nova_helper.set_flavor_extra_specs(flavor_id, **specs_preset)

    LOG.tc_step("Attempt to set following flavor extra specs: {}".format(specs_to_set))
    code, output = nova_helper.set_flavor_extra_specs(flavor_id, fail_ok=True, **specs_to_set)

    LOG.tc_step("Verify cli rejected invalid extra specs setting with proper error message.")
    expt_err_eval = eval(expt_err)
    if expt_err == 'CPUThreadErr.UNSET_SHARED_VCPU':
        all_specs = specs_preset.copy()
        all_specs.update(specs_to_set)
        expt_err_eval = expt_err_eval.format(all_specs[FlavorSpec.CPU_THREAD_POLICY])

    assert 1 == code, 'Set flavor extra spec is not rejected. Existing specs: {}. Specs to set: {}'.format(
            specs_preset, specs_to_set)
    assert expt_err_eval in output


@mark.p1
@mark.parametrize('cpu_thread_policy', [
    'isolate',
    'require',
])
def test_cpu_thread_flavor_delete_negative(cpu_thread_policy):
    LOG.tc_step("Create a flavor")
    flavor_id = nova_helper.create_flavor(name='cpu_thread_neg2', check_storage_backing=False)[1]
    ResourceCleanup.add('flavor', flavor_id)

    specs = {FlavorSpec.CPU_THREAD_POLICY: cpu_thread_policy, FlavorSpec.CPU_POLICY: 'dedicated'}
    LOG.tc_step("Set following extra specs: {}".format(specs))
    nova_helper.set_flavor_extra_specs(flavor_id, **specs)

    LOG.tc_step("Attempt to unset cpu policy while cpu thread policy is set to {}".format(cpu_thread_policy))
    code, output = nova_helper.unset_flavor_extra_specs(flavor_id, FlavorSpec.CPU_POLICY, check_first=False,
                                                        fail_ok=True)
    assert 1 == code, 'Unset cpu policy is not rejected when cpu thread policy is set.'
    assert CPUThreadErr.DEDICATED_CPU_REQUIRED in output


class TestHTEnabled:

    @fixture(scope='class', autouse=True)
    def ht_hosts(self):
        LOG.fixture_step("Look for hyper-threading enabled hosts")
        nova_hosts = host_helper.get_nova_hosts()
        ht_hosts = []
        for host in nova_hosts:
            if system_helper.is_hyperthreading_enabled(host):
                ht_hosts.append(host)

        if not ht_hosts:
            skip("No up hypervisor found with Hyper-threading enabled.")

        LOG.info('Hyper-threading enabled hosts: {}'.format(ht_hosts))
        return ht_hosts

    @mark.p1
    @mark.parametrize('cpu_thread_policy', [
        'isolate',
        'require',
        None        # this one might need updates
    ])
    def test_boot_vm_cpu_thread_positive(self, cpu_thread_policy, ht_hosts):
        LOG.tc_step("Create flavor with 2 vcpus")
        flavor_id = nova_helper.create_flavor(name='cpu_thread_{}'.format(cpu_thread_policy), vcpus=2)[1]
        ResourceCleanup.add('flavor', flavor_id)

        specs = {FlavorSpec.CPU_POLICY: 'dedicated'}
        if cpu_thread_policy is not None:
            specs[FlavorSpec.CPU_THREAD_POLICY] = cpu_thread_policy

        LOG.tc_step("Set following extra specs: {}".format(specs))
        nova_helper.set_flavor_extra_specs(flavor_id, **specs)

        LOG.tc_step("Get used cpus for all hosts before booting vm")
        pre_hosts_cpus = host_helper.get_vcpus_for_computes(hosts=ht_hosts, rtn_val='used_now')

        LOG.tc_step("Boot a vm with above flavor and ensure it's booted on a HT enabled host.")
        vm_id = vm_helper.boot_vm(name='cpu_thread_{}'.format(cpu_thread_policy), flavor=flavor_id)[1]
        ResourceCleanup.add('vm', vm_id)

        vm_host = nova_helper.get_vm_host(vm_id)
        assert vm_host in ht_hosts, "VM host {} is not hyper-threading enabled.".format(vm_host)

        prev_cpus = pre_hosts_cpus[vm_host]

        LOG.tc_step('Check total used vcpus for vm host via nova host-describe')
        expt_increase = 4 if cpu_thread_policy == 'isolate' else 2
        post_hosts_cpus = host_helper.get_vcpus_for_computes(hosts=vm_host, rtn_val='used_now')
        assert prev_cpus + expt_increase == post_hosts_cpus[vm_host]

        LOG.tc_step(
            "Check total allocated vcpus increased by {} from nova-compute.log on vm host".format(expt_increase))
        post_total_log = host_helper.wait_for_total_allocated_vcpus_update_in_log(host=vm_host, prev_cpus=prev_cpus)
        assert prev_cpus + expt_increase == post_total_log

        LOG.tc_step("Check vm-topology servers table for following vm cpus info: cpu policy, thread policy, topology, "
                    "siblings, pcpus")
        instance_topology = vm_helper.get_instance_topology(vm_id)
        log_cores_siblings = host_helper.get_logcore_siblings(host=vm_host)
        for topology_on_numa_node in instance_topology:     # Cannot be on two numa nodes unless specified in flavor
            assert 'ded' == topology_on_numa_node['pol'], "CPU policy is not dedicated in vm-topology"

            actual_thread_policy = topology_on_numa_node['thr']
            if cpu_thread_policy:
                assert actual_thread_policy in cpu_thread_policy, \
                    'cpu thread policy in vm topology is {} while flavor spec is {}'.\
                    format(actual_thread_policy, cpu_thread_policy)
            else:
                assert actual_thread_policy == 'no', \
                    'cpu thread policy in vm topology is {} while flavor spec is {}'.\
                    format(actual_thread_policy, cpu_thread_policy)

            expt_siblings = None if cpu_thread_policy == 'isolate' else {0, 1}
            assert expt_siblings == topology_on_numa_node['siblings'], "siblings should be displayed for 'require' only"

            expt_topology = '2c,1t' if cpu_thread_policy == 'isolate' else '1c,2t'
            assert expt_topology in topology_on_numa_node['topology'], 'vm topology is not as expected'

            pcpus = topology_on_numa_node['pcpus']
            pcpus_reverse = pcpus.reverse()
            if cpu_thread_policy == 'isolate':
                assert pcpus not in log_cores_siblings and pcpus_reverse not  in log_cores_siblings
            else:
                assert pcpus in log_cores_siblings or pcpus_reverse in log_cores_siblings

        expt_core_sib_list = ['0', '1'] if cpu_thread_policy == 'isolate' else ['0-1']
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
            LOG.tc_step("Check vm has 2 cores from inside vm via /proc/cpuinfo.")
            assert 2 == vm_helper.get_proc_num_from_vm(vm_ssh)

            LOG.tc_step("Check vm /sys/devices/system/cpu/[cpu#]/topology/core_siblings_list")
            for cpu in 'cpu0', 'cpu1':
                actual_sib_list = vm_ssh.exec_cmd('cat /sys/devices/system/cpu/{}/topology/core_siblings_list'.
                                                  format(cpu), fail_ok=False)[1]
                assert actual_sib_list in expt_core_sib_list

    @mark.parametrize(('vcpus', 'cpu_thread_policy', 'expt_err'), [
        (1, 'require', 'CPUThreadErr.VCPU_NUM_UNDIVISIBLE'),
        (3, 'require', 'CPUThreadErr.VCPU_NUM_UNDIVISIBLE')
    ])
    def test_boot_vm_cpu_thread_negative(self, vcpus, cpu_thread_policy, expt_err):
        LOG.tc_step("Create flavor with {} vcpus".format(vcpus))
        flavor_id = nova_helper.create_flavor(name='cpu_thread_negative', vcpus=vcpus)[1]
        ResourceCleanup.add('flavor', flavor_id)

        specs = {FlavorSpec.CPU_THREAD_POLICY: cpu_thread_policy, FlavorSpec.CPU_POLICY: 'dedicated'}
        LOG.tc_step("Set following extra specs: {}".format(specs))
        nova_helper.set_flavor_extra_specs(flavor_id, **specs)

        LOG.tc_step("Boot a vm with above flavor and check it failed booted.")
        code, vm_id, msg, vol_id = vm_helper.boot_vm(name='cpu_thread_{}'.format(cpu_thread_policy),
                                                     flavor=flavor_id, fail_ok=True)
        ResourceCleanup.add('vm', vm_id, del_vm_vols=False)
        ResourceCleanup.add('volume', vol_id)

        assert 1 == code, "Boot vm cli is not rejected. Details: {}".format(msg)

        LOG.tc_step("Check expected fault message displayed in nova show")
        fault_msg = nova_helper.get_vm_nova_show_value(vm_id, 'fault')
        assert eval(expt_err).format(vcpus) in fault_msg

    @fixture(scope='class')
    def prepare_multi_vm_env(self, ht_hosts, request):
        if len(ht_hosts) > 1:
            # Only run test on lab with 1 ht host for sibling cores checking purpose.
            # IP14-17, IP1-4 can be used for this testcase
            skip("More than one host has hyper-threading enabled.")

        ht_host = ht_hosts[0]

        LOG.fixture_step("Create flavor with 4 vcpus")
        flavor_id = nova_helper.create_flavor(name='cpu_thread', vcpus=4)[1]
        ResourceCleanup.add('flavor', flavor_id)

        specs = {FlavorSpec.CPU_THREAD_POLICY: 'isolate', FlavorSpec.CPU_POLICY: 'dedicated'}
        LOG.fixture_step("Set following extra specs: {}".format(specs))
        nova_helper.set_flavor_extra_specs(flavor_id, **specs)

        LOG.fixture_step("Calculate max number of 4-core-isolate VMs can be booted on {}".format(ht_host))
        # pre_host_used_cpus = host_helper.get_vcpus_for_computes(hosts=ht_hosts, rtn_val='used_now')[ht_host]
        # pre_host_total_cpus = host_helper.get_vcpus_for_computes(hosts=ht_hosts, rtn_val='total')[ht_host]

        # ensure single numa node cores available is sufficient for booting last vm
        max_vm_num = 0
        left_over_unpinned_cpus = 0
        host_vcpu_info = host_helper.get_vcpus_info_in_log(ht_host, rtn_list=True)
        for info_for_node in host_vcpu_info:
            unpinned_cpus = info_for_node['unpinned']
            max_vm_num += int(unpinned_cpus / 8)
            left_over_unpinned_cpus = int(max(left_over_unpinned_cpus, unpinned_cpus % 8))

        assert max_vm_num > 0, "Less than 8 cores available on {}. Check system.".format(ht_host)

        # max_cores = math.floor(pre_host_total_cpus - pre_host_used_cpus)
        max_cores = max_vm_num * 8
        cores_quota = nova_helper.get_quotas('cores')[0]
        if cores_quota < max_cores:
            LOG.fixture_step("Update quota for cores to ensure VMs number is not limited by quota.")
            nova_helper.update_quotas(cores=max_cores + 8)

            def revert_quota():
                nova_helper.update_quotas(cores=cores_quota)
            request.addfinalizer(revert_quota)

        # # 8 cores because for isolate the sibling cores are always reserved. So it's 4*2.
        # max_vm_num = int(max_cores / 8)
        LOG.info("Maximum {} 4-core-isolate VMs can still be booted on {}".format(max_vm_num, ht_host))

        # left_over_isolate_cores = int((max_cores - max_vm_num * 8)/2)
        left_over_isolate_cores = left_over_unpinned_cpus / 2
        return ht_host, max_vm_num, flavor_id, left_over_isolate_cores

    @mark.p2
    def test_boot_multiple_vms_cpu_thread_isolate(self, prepare_multi_vm_env):
        ht_host, max_vm_num, flavor_id, left_over_isolate_cores = prepare_multi_vm_env
        log_cores_siblings = host_helper.get_logcore_siblings(host=ht_host)

        LOG.tc_step("Boot {} vms with isolate cpu thread policy and 4vcpus in flavor".format(max_vm_num))
        total_vms_core_pairs = []
        for i in range(max_vm_num):

            pre_boot_used_cpus = host_helper.get_vcpus_for_computes(hosts=ht_host, rtn_val='used_now')[ht_host]

            LOG.tc_step("Boot VM_{} with above flavor and ensure it's booted on the HT enabled host.".format(i+1))
            vm_id = vm_helper.boot_vm(name='cpu_thread_isolate', flavor=flavor_id)[1]
            ResourceCleanup.add('vm', vm_id)

            vm_host = nova_helper.get_vm_host(vm_id)
            assert ht_host == vm_host, "VM host {} is not hyper-threading enabled.".format(vm_host)

            LOG.tc_step('Check total used vcpus for vm host is increased by 8 via nova host-describe')
            post_boot_used_cpus = host_helper.get_vcpus_for_computes(hosts=vm_host, rtn_val='used_now')[ht_host]
            assert pre_boot_used_cpus + 8 == post_boot_used_cpus, "vcpus used on ht host {} is not increased by " \
                                                                  "8".format(ht_host)

            LOG.tc_step("Check topology, siblings, pcpus via vm-topology for vm {}".format(vm_id))
            instance_topology = vm_helper.get_instance_topology(vm_id)
            vm_pcpus = []
            for topology_on_numa_node in instance_topology:  # TODO is it possible to be on two numa nodes?

                assert topology_on_numa_node['siblings'] is None, "Siblings should not be displayed for 'isolate' vm"

                assert '4c,1t' in topology_on_numa_node['topology'], 'vm topology is not as expected'

                pcpus = topology_on_numa_node['pcpus']
                vm_pcpus += pcpus

            LOG.info("pcpus for vm {}: {}".format(vm_id, vm_pcpus))
            assert 4 == len(vm_pcpus), "VM {} does not have 4 pcpus listed in vm-topology".format(vm_id)
            vm_core_pairs = []
            for pcpu in vm_pcpus:
                for core_pair in log_cores_siblings:
                    if pcpu in core_pair:
                        vm_core_pairs.append(tuple(core_pair))
                        break
                else:
                    assert 0, "pcpu {} is not found core pairs {}".format(pcpu, log_cores_siblings)

            duplicated_pairs = [pair for pair in vm_core_pairs if vm_core_pairs.count(pair) > 1]
            assert not duplicated_pairs, 'Some vm cores are in pairs: {}. Duplicated pairs:{}'. \
                format(vm_pcpus, duplicated_pairs)

            total_vms_core_pairs += vm_core_pairs

        LOG.info("Total core pairs used by booted vms: {}".format(total_vms_core_pairs))
        LOG.tc_step("Ensure no duplicated core pairs used across all vms booted")
        duplicated_pairs = [pair for pair in total_vms_core_pairs if total_vms_core_pairs.count(pair) > 1]
        assert not duplicated_pairs, 'Some vms core pairs are duplicates: {}. Duplicated pairs:{}'. \
            format(total_vms_core_pairs, duplicated_pairs)

        LOG.tc_step("Boot one more vm, and ensure it's fail to boot due to insufficient cores on ht host.")
        code, vm_id, msg, vol_id = vm_helper.boot_vm(name='insufficient_cores_isolate', flavor=flavor_id, fail_ok=True)
        ResourceCleanup.add('vm', vm_id, del_vm_vols=False)
        ResourceCleanup.add('volume', vol_id)

        assert 1 == code, "Boot vm cli is not rejected. Details: {}".format(msg)

        LOG.tc_step("Check expected fault message displayed in nova show")
        fault_msg = nova_helper.get_vm_nova_show_value(vm_id, 'fault')
        assert "No valid host was found" in fault_msg
        assert CPUThreadErr.INSUFFICIENT_CORES_FOR_ISOLATE.format(ht_host, 4, left_over_isolate_cores) in fault_msg


class TestHTDisabled:

    @fixture(scope='class', autouse=True)
    def ht_hosts(self):
        LOG.fixture_step("Check if all hosts have hyper-threading disabled.")
        nova_hosts = host_helper.get_nova_hosts()
        ht_hosts = []
        for host in nova_hosts:
            if system_helper.is_hyperthreading_enabled(host):
                ht_hosts.append(host)

        if ht_hosts:
            skip("Some nova host(s) has Hyper-threading enabled.")

        LOG.info('Hyper-threading enabled hosts: {}'.format(ht_hosts))
        return nova_hosts

    @mark.p1
    @mark.parametrize(('vcpus', 'cpu_thread_policy', 'expt_err'), [
        (2, 'require', 'CPUThreadErr.HT_HOST_UNAVAIL'),
        (2, 'isolate', 'CPUThreadErr.HT_HOST_UNAVAIL')
    ])
    def test_boot_vm_cpu_thread_ht_disable_negative(self, vcpus, cpu_thread_policy, expt_err):
        LOG.tc_step("Create flavor with {} vcpus".format(vcpus))
        flavor_id = nova_helper.create_flavor(name='cpu_thread_negative', vcpus=vcpus)[1]
        ResourceCleanup.add('flavor', flavor_id)

        specs = {FlavorSpec.CPU_THREAD_POLICY: cpu_thread_policy, FlavorSpec.CPU_POLICY: 'dedicated'}
        LOG.tc_step("Set following extra specs: {}".format(specs))
        nova_helper.set_flavor_extra_specs(flavor_id, **specs)

        LOG.tc_step("Boot a vm with above flavor and check it failed booted.")
        code, vm_id, msg, vol_id = vm_helper.boot_vm(name='cpu_thread_{}'.format(cpu_thread_policy),
                                                     flavor=flavor_id, fail_ok=True)
        ResourceCleanup.add('vm', vm_id, del_vm_vols=False)
        ResourceCleanup.add('volume', vol_id)

        assert 1 == code, "Boot vm cli is not rejected. Details: {}".format(msg)

        LOG.tc_step("Check expected fault message displayed in nova show")
        fault_msg = nova_helper.get_vm_nova_show_value(vm_id, 'fault')
        assert eval(expt_err).format(cpu_thread_policy) in fault_msg

