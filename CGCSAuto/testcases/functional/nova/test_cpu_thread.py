import random

from pytest import mark, fixture, skip

from utils.tis_log import LOG

from consts.cgcs import FlavorSpec, ImageMetadata
from consts.cli_errs import CPUThreadErr, SharedCPUErr, ColdMigrateErr, CPUPolicyErr

from keywords import nova_helper, system_helper, vm_helper, host_helper, glance_helper, cinder_helper, common
from testfixtures.resource_mgmt import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


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


@mark.parametrize(('flv_vcpus', 'flv_pol', 'img_pol', 'create_vol', 'expt_err'), [
    mark.p2((5, None, 'dedicated', True, None)),
    mark.p2((3, None, 'shared', False, None)),
    mark.p2((4, None, None, False, None)),
    mark.p3((4, 'dedicated', 'dedicated', True, None)),
    mark.p3((1, 'dedicated', None, False, None)),
    mark.p3((1, 'shared', 'shared', True, None)),
    mark.p3((2, 'shared', None, False, None)),
    mark.p1((3, 'dedicated', 'shared', True, None)),
    mark.p2((1, 'shared', 'dedicated', False, 'CPUPolicyErr.CONFLICT_FLV_IMG')),
])
def test_boot_vm_cpu_policy_image(flv_vcpus, flv_pol, img_pol, create_vol, expt_err):
    LOG.tc_step("Create flavor with {} vcpus".format(flv_vcpus))
    flavor_id = nova_helper.create_flavor(name='cpu_thread_image', vcpus=flv_vcpus)[1]
    ResourceCleanup.add('flavor', flavor_id)

    if flv_pol is not None:
        specs = {FlavorSpec.CPU_POLICY: flv_pol}

        LOG.tc_step("Set following extra specs: {}".format(specs))
        nova_helper.set_flavor_extra_specs(flavor_id, **specs)

    if img_pol is not None:
        image_meta = {ImageMetadata.CPU_POLICY: img_pol}
        LOG.tc_step("Create image with following metadata: {}".format(image_meta))
        image_id = glance_helper.create_image(name='cpu_thread_{}'.format(img_pol), **image_meta)[1]
        ResourceCleanup.add('image', image_id)
    else:
        image_id = glance_helper.get_image_id_from_name('cgcs-guest')

    if create_vol:
        LOG.tc_step("Create a volume from image")
        source_id = cinder_helper.create_volume(name='cpu_thr_img', image_id=image_id)[1]
        ResourceCleanup.add('volume', source_id)
        source = 'volume'
    else:
        source_id = image_id
        source = 'image'

    LOG.tc_step("Attempt to boot a vm with above flavor and {}".format(source))
    code, vm_id, msg, ignore = vm_helper.boot_vm(name='cpu_thread_image', flavor=flavor_id, source=source,
                                                 source_id=source_id, fail_ok=True)
    if vm_id:
        ResourceCleanup.add('vm', vm_id)

    # check for negative tests
    if expt_err is not None:
        LOG.tc_step("Check VM failed to boot due to conflict in flavor and image.")
        assert 4 == code, "Expect boot vm cli reject and no vm booted. Actual: {}".format(msg)
        assert eval(expt_err) in msg, "Expected error message is not found in cli return."
        return  # end the test for negative cases

    # Check for positive tests
    LOG.tc_step("Check vm is successfully booted on a HT enabled host.")
    assert 0 == code, "Expect vm boot successfully. Actual: {}".format(msg)

    # Calculate expected policy:
    expt_cpu_pol = 'ded' if 'dedicated' in [img_pol, flv_pol] else 'sha'

    # Check vm-topology
    LOG.tc_step("Check vm-topology servers table for following vm cpus info: cpu policy, topology, "
                "siblings, pcpus")
    instance_topology = vm_helper.get_instance_topology(vm_id)

    for topology_on_numa_node in instance_topology:  # Cannot be on two numa nodes for dedicated vm unless specified
        assert expt_cpu_pol == topology_on_numa_node['pol'], "CPU policy is not {} in vm-topology".format(expt_cpu_pol)

        actual_siblings = topology_on_numa_node['siblings']
        actual_topology = topology_on_numa_node['topology']
        actual_pcpus = topology_on_numa_node['pcpus']

        if expt_cpu_pol == 'ded':
            assert topology_on_numa_node['thr'] == 'no', "cpu thread policy is in vm topology"
            if flv_vcpus == 1:
                assert not actual_siblings, "siblings should not be included with only 1 vcpu"
            else:
                assert actual_siblings, "siblings should be included for dedicated vm"
            assert '1c,{}t'.format(flv_vcpus) in actual_topology, 'vm topology is not as expected.'
            assert flv_vcpus == len(actual_pcpus), "pcpus number for dedicated vm is not the same as setting in flavor"
        else:
            assert topology_on_numa_node['thr'] is None, "cpu thread policy is in vm topology"
            assert actual_siblings is None, 'siblings should not be included for floating vm'
            assert actual_topology is None, 'topology should not be included for floating vm'
            assert actual_pcpus is None, "pcpu should not be included in vm-topology for floating vm"

    # TODO: add check via from compute via taskset -apc 98456 for floating vm's actual vcpus.


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
    @mark.parametrize(('vcpus', 'cpu_thread_policy', 'min_vcpus'), [
        # mark.p1((2, 'isolate', None)),
        # mark.p1((2, 'require', None)),
        # mark.p1((2, 'isolate', '2')),
        mark.p1((5, 'isolate', None)),
        mark.p1((4, 'isolate', None)),
        mark.p1((4, 'require', None)),
        # None        # TODO this one needs updates
    ])
    def test_boot_vm_cpu_thread_positive(self, vcpus, cpu_thread_policy, min_vcpus, ht_hosts):
        LOG.tc_step("Create flavor with {} vcpus".format(vcpus))
        flavor_id = nova_helper.create_flavor(name='cpu_thread_{}'.format(cpu_thread_policy), vcpus=vcpus)[1]
        ResourceCleanup.add('flavor', flavor_id)

        specs = {FlavorSpec.CPU_POLICY: 'dedicated'}
        if cpu_thread_policy is not None:
            specs[FlavorSpec.CPU_THREAD_POLICY] = cpu_thread_policy

        if min_vcpus is not None:
            specs[FlavorSpec.MIN_VCPUS] = min_vcpus

        LOG.tc_step("Set following extra specs: {}".format(specs))
        nova_helper.set_flavor_extra_specs(flavor_id, **specs)

        LOG.tc_step("Get used cpus for all hosts before booting vm")
        pre_hosts_cpus = host_helper.get_vcpus_for_computes(hosts=ht_hosts, rtn_val='used_now')

        LOG.tc_step("Boot a vm with above flavor and ensure it's booted on a HT enabled host.")
        vm_id = vm_helper.boot_vm(name='cpu_thread_{}'.format(cpu_thread_policy), flavor=flavor_id)[1]
        ResourceCleanup.add('vm', vm_id)

        vm_host = nova_helper.get_vm_host(vm_id)
        assert vm_host in ht_hosts, "VM host {} is not hyper-threading enabled.".format(vm_host)

        # Check nova host-describe
        prev_cpus = pre_hosts_cpus[vm_host]

        LOG.tc_step('Check total used vcpus for vm host via nova host-describe')
        expt_increase = vcpus * 2 if cpu_thread_policy == 'isolate' else vcpus
        post_hosts_cpus = host_helper.get_vcpus_for_computes(hosts=vm_host, rtn_val='used_now')
        assert prev_cpus + expt_increase == post_hosts_cpus[vm_host]

        # Check vm-topology
        LOG.tc_step("Check vm-topology servers table for following vm cpus info: cpu policy, thread policy, topology, "
                    "siblings, pcpus")
        instance_topology = vm_helper.get_instance_topology(vm_id)
        log_cores_siblings = host_helper.get_logcore_siblings(host=vm_host)
        pcpus_total = []
        siblings_total = []
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

            actual_siblings = topology_on_numa_node['siblings']
            if cpu_thread_policy == 'isolate':
                assert not actual_siblings, "siblings should not be displayed for 'isolate'"
            else:
                assert actual_siblings, "sibling pairs should be included for 'require"

            if actual_siblings is not None:
                siblings_total += actual_siblings

            expt_topology = '{}c,1t'.format(vcpus) if cpu_thread_policy == 'isolate' else '{}c,2t'.format(int(vcpus/2))
            assert expt_topology in topology_on_numa_node['topology'], 'vm topology is not as expected'

            pcpus = topology_on_numa_node['pcpus']

            expt_core_len_in_pair = 1 if cpu_thread_policy == 'isolate' else 2
            for pair in log_cores_siblings:
                assert len(set(pair) & set(pcpus)) in [0, expt_core_len_in_pair]
            # if cpu_thread_policy == 'isolate':
            #     assert pcpus not in log_cores_siblings
            # else:
            #     assert pcpus in log_cores_siblings
            pcpus_total += pcpus

        # Check host side info such as nova-compute.log and virsh pcpupin
        instance_name = nova_helper.get_vm_instance_name(vm_id)
        with host_helper.ssh_to_host(vm_host) as host_ssh:
            LOG.tc_step("Check total allocated vcpus is increased by {} from nova-compute.log on host".format(
                    expt_increase))
            post_total_log = host_helper.wait_for_total_allocated_vcpus_update_in_log(host_ssh, prev_cpus=prev_cpus)
            assert prev_cpus + expt_increase == post_total_log, 'vcpus increase in nova-compute.log is not as expected'

            LOG.tc_step("Check vcpus for vm is the same via vm-topology and virsh vcpupin")
            vcpus_for_vm = host_helper.get_vcpus_for_instance_via_virsh(host_ssh, instance_name=instance_name)
            assert sorted(pcpus_total) == sorted(list(vcpus_for_vm.values())), \
                'pcpus from vm-topology is different than virsh vcpupin'

            LOG.tc_step("Check sibling pairs in vm-topology is same as virsh vcpupin")
            for sibling_pair_indexes in siblings_total:
                sibling_pcpus = []
                for index in sibling_pair_indexes:
                    sibling_pcpus.append(vcpus_for_vm[index])
                assert sorted(sibling_pcpus) in log_cores_siblings

        # Check from vm in /proc/cpuinfo and /sys/devices/.../cpu#/topology/core_siblings_list
        expt_sib_list = [{vcpu} for vcpu in range(vcpus)] if cpu_thread_policy == 'isolate' else siblings_total
        actual_sib_list = []
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
            LOG.tc_step("Check vm has {} cores from inside vm via /proc/cpuinfo.".format(vcpus))
            assert vcpus == vm_helper.get_proc_num_from_vm(vm_ssh)

            LOG.tc_step("Check vm /sys/devices/system/cpu/[cpu#]/topology/core_siblings_list")
            for cpu in ['cpu{}'.format(i) for i in range(vcpus)]:
                actual_sib_list_for_cpu = vm_ssh.exec_cmd('cat /sys/devices/system/cpu/{}/topology/core_siblings_list'.
                                                          format(cpu), fail_ok=False)[1]

                new_sib_pair = set([int(cpu) for cpu in actual_sib_list_for_cpu.split(sep='-')])
                if new_sib_pair not in actual_sib_list:
                    actual_sib_list.append(new_sib_pair)

        assert sorted(expt_sib_list) == sorted(actual_sib_list)

    @mark.parametrize(('flv_vcpus', 'flv_cpu_pol', 'flv_cpu_thr_pol', 'img_cpu_thr_pol', 'img_cpu_pol', 'create_vol', 'expt_err'), [
        mark.p2((3, None, None, 'isolate', 'dedicated', False, None)),
        mark.p2((4, None, None, 'require', 'dedicated', True, None)),
        mark.p2((2, 'dedicated', 'require', 'isolate', 'dedicated', True, 'CPUThreadErr.CONFLICT_FLV_IMG')),
        mark.p2((2, None, None, 'isolate', None, True, 'CPUThreadErr.DEDICATED_CPU_REQUIRED')),
        mark.p2((2, None, None, 'require', None, False, 'CPUThreadErr.DEDICATED_CPU_REQUIRED')),
    ])
    def test_boot_vm_cpu_thread_image(self, flv_vcpus, flv_cpu_pol, flv_cpu_thr_pol, img_cpu_thr_pol, img_cpu_pol,
                                      create_vol, expt_err, ht_hosts):
        LOG.tc_step("Create flavor with {} vcpus".format(flv_vcpus))
        flavor_id = nova_helper.create_flavor(name='cpu_thread_image', vcpus=flv_vcpus)[1]
        ResourceCleanup.add('flavor', flavor_id)

        if flv_cpu_pol is not None:
            specs = {FlavorSpec.CPU_POLICY: flv_cpu_pol}
            if flv_cpu_thr_pol is not None:
                specs[FlavorSpec.CPU_THREAD_POLICY] = flv_cpu_thr_pol

            LOG.tc_step("Set following extra specs: {}".format(specs))
            nova_helper.set_flavor_extra_specs(flavor_id, **specs)

        LOG.tc_step("Get used cpus for all hosts before booting vm")
        pre_hosts_cpus = host_helper.get_vcpus_for_computes(hosts=ht_hosts, rtn_val='used_now')

        image_meta = {ImageMetadata.CPU_POLICY: img_cpu_pol, ImageMetadata.CPU_THREAD_POLICY: img_cpu_thr_pol}
        LOG.tc_step("Create image with following metadata: {}".format(image_meta))
        image_id = glance_helper.create_image(name='cpu_thread_{}'.format(img_cpu_thr_pol), **image_meta)[1]
        ResourceCleanup.add('image', image_id)

        if create_vol:
            LOG.tc_step("Create a volume from above image")
            source_id = cinder_helper.create_volume(name='cpu_thr_img', image_id=image_id)[1]
            ResourceCleanup.add('volume', source_id)
            source = 'volume'
        else:
            source_id = image_id
            source = 'image'

        LOG.tc_step("Attempt to boot a vm with above flavor and {}".format(source))
        code, vm_id, msg, ignore = vm_helper.boot_vm(name='cpu_thread_image', flavor=flavor_id, source=source, source_id=source_id, fail_ok=True)
        if vm_id:
            ResourceCleanup.add('vm', vm_id)

        # check for negative tests
        if expt_err is not None:
            LOG.tc_step("Check VM failed to boot due to conflict in flavor and image.")
            assert 4 == code, "Expect boot vm cli reject and no vm booted. Actual: {}".format(msg)
            assert eval(expt_err) in msg, "Expected error message is not found in cli return."
            pass    # end the test for negative cases

        # Check for positive tests
        LOG.tc_step("Check vm is successfully booted on a HT enabled host.")
        assert 0 == code, "Expect vm boot successfully. Actual: {}".format(msg)

        vm_host = nova_helper.get_vm_host(vm_id)
        assert vm_host in ht_hosts, "VM host {} is not hyper-threading enabled.".format(vm_host)

        # Calculate expected policy:
        expt_thr_pol = img_cpu_thr_pol if flv_cpu_thr_pol is None else flv_cpu_thr_pol

        # Check nova host-describe
        prev_cpus = pre_hosts_cpus[vm_host]

        LOG.tc_step('Check total used vcpus for vm host via nova host-describe')
        expt_increase = flv_vcpus * 2 if expt_thr_pol == 'isolate' else flv_vcpus
        post_hosts_cpus = host_helper.get_vcpus_for_computes(hosts=vm_host, rtn_val='used_now')
        assert prev_cpus + expt_increase == post_hosts_cpus[vm_host]

        # Check vm-topology
        LOG.tc_step("Check vm-topology servers table for following vm cpus info: cpu policy, thread policy, topology, "
                    "siblings, pcpus")
        instance_topology = vm_helper.get_instance_topology(vm_id)
        log_cores_siblings = host_helper.get_logcore_siblings(host=vm_host)
        pcpus_total = []
        siblings_total = []
        for topology_on_numa_node in instance_topology:     # Cannot be on two numa nodes unless specified in flavor
            assert 'ded' == topology_on_numa_node['pol'], "CPU policy is not dedicated in vm-topology"

            actual_thread_policy = topology_on_numa_node['thr']
            assert actual_thread_policy in expt_thr_pol, \
                'cpu thread policy in vm topology is {} while flavor spec is {}'.\
                format(actual_thread_policy, expt_thr_pol)

            actual_siblings = topology_on_numa_node['siblings']
            if expt_thr_pol == 'isolate':
                assert not actual_siblings, "siblings should not be displayed for 'isolate'"
            else:
                assert actual_siblings, "sibling pairs should be included for 'require"

            if actual_siblings is not None:
                siblings_total += actual_siblings

            expt_topology = '{}c,1t'.format(flv_vcpus) if expt_thr_pol == 'isolate' else '{}c,2t'.format(int(flv_vcpus/2))
            assert expt_topology in topology_on_numa_node['topology'], 'vm topology is not as expected'

            pcpus = topology_on_numa_node['pcpus']
            expt_core_len_in_pair = 1 if expt_thr_pol == 'isolate' else 2
            for pair in log_cores_siblings:
                assert len(set(pair) & set(pcpus)) in [0, expt_core_len_in_pair]

            pcpus_total += pcpus

        # Check from vm in /proc/cpuinfo and /sys/devices/.../cpu#/topology/core_siblings_list
        expt_sib_list = [[vcpu] for vcpu in range(flv_vcpus)] if expt_thr_pol == 'isolate' else siblings_total
        actual_sib_list = []
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
            LOG.tc_step("Check vm has {} cores from inside vm via /proc/cpuinfo.".format(flv_vcpus))
            assert flv_vcpus == vm_helper.get_proc_num_from_vm(vm_ssh)

            LOG.tc_step("Check vm /sys/devices/system/cpu/[cpu#]/topology/core_siblings_list")
            for cpu in ['cpu{}'.format(i) for i in range(flv_vcpus)]:
                actual_sib_list_for_cpu = vm_ssh.exec_cmd('cat /sys/devices/system/cpu/{}/topology/core_siblings_list'.
                                                          format(cpu), fail_ok=False)[1]

                new_sibs = common._parse_cpus_list(actual_sib_list_for_cpu)
                if new_sibs not in actual_sib_list:
                    actual_sib_list.append(new_sibs)

        assert sorted(expt_sib_list) == sorted(actual_sib_list)

    @mark.p1
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

        with host_helper.ssh_to_host(ht_host) as host_ssh:
            host_vcpu_info = host_helper.get_vcpus_info_in_log(host_ssh, rtn_list=True)

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
                    assert 0, "pcpu {} is not found in core pairs {}".format(pcpu, log_cores_siblings)

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
    @mark.parametrize(('vcpus', 'cpu_thread_policy', 'min_vcpus', 'expt_err'), [
        (2, 'require', None, 'CPUThreadErr.HT_HOST_UNAVAIL'),
        (2, 'isolate', None, 'CPUThreadErr.HT_HOST_UNAVAIL'),
        (2, 'isolate', '2', 'CPUThreadErr.HT_HOST_UNAVAIL'),
    ])
    def test_boot_vm_cpu_thread_ht_disable_negative(self, vcpus, cpu_thread_policy, min_vcpus, expt_err):
        LOG.tc_step("Create flavor with {} vcpus".format(vcpus))
        flavor_id = nova_helper.create_flavor(name='cpu_thread_negative', vcpus=vcpus)[1]
        ResourceCleanup.add('flavor', flavor_id)

        specs = {FlavorSpec.CPU_THREAD_POLICY: cpu_thread_policy, FlavorSpec.CPU_POLICY: 'dedicated'}
        if min_vcpus is not None:
            specs[FlavorSpec.MIN_VCPUS] = min_vcpus

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


class TestColdMigrate:

    @fixture(scope='class', autouse=True, params=['two_plus_ht', 'one_ht'])
    def ht_and_nonht_hosts(self, request):
        nova_hosts = host_helper.get_nova_hosts()
        if len(nova_hosts) < 2:
            skip("Less than two up hypervisors in system.")

        LOG.fixture_step('Check hyperthreading info for each up compute host')
        ht_hosts = []
        non_ht_hosts = []
        for host in nova_hosts:
            if system_helper.is_hyperthreading_enabled(host):
                ht_hosts.append(host)
            else:
                non_ht_hosts.append(host)

        if not ht_hosts:
            skip("System does not have up host with hyper-threading enabled")

        if request.param == 'two_plus_ht':
            if len(ht_hosts) < 2:
                skip("Less than two hyper-threading enabled up hosts in system")

        else:
            if not non_ht_hosts:
                skip("System does not have up host with hyper-threading disabled")

            if len(ht_hosts) > 1:
                if len(ht_hosts) > 4:
                    skip("More than 4 ht hosts available. Skip to reduce execution time.")

                LOG.fixture_step("Lock all hyper-threading enabled host except one")
                host_to_test = random.choice(ht_hosts)
                hosts_to_lock = list(ht_hosts)
                hosts_to_lock.remove(host_to_test)

                for host in hosts_to_lock:
                    HostsToRecover.add(host, scope='class')
                    host_helper.lock_host(host)
                # Now system only has one ht host
                ht_hosts = [host_to_test]

        LOG.info('Hyper-threading enabled hosts: {}'.format(ht_hosts))
        LOG.info('Hyper-threading disabled hosts: {}'.format(non_ht_hosts))
        return ht_hosts, non_ht_hosts

    @mark.p1
    @mark.parametrize(('cpu_thread_policy', 'min_vcpus'), [
        mark.p1(('isolate', None)),
        mark.p1(('require', None)),
        mark.p1(('isolate', '2'))
    ])
    def test_cold_migrate_vm_cpu_thread(self, cpu_thread_policy, min_vcpus, ht_and_nonht_hosts):
        ht_hosts, non_ht_hosts = ht_and_nonht_hosts

        LOG.tc_step("Create flavor with 2 vcpus")
        flavor_id = nova_helper.create_flavor(name='cpu_thread_{}'.format(cpu_thread_policy), vcpus=2)[1]
        ResourceCleanup.add('flavor', flavor_id)

        specs = {FlavorSpec.CPU_POLICY: 'dedicated'}
        if cpu_thread_policy is not None:
            specs[FlavorSpec.CPU_THREAD_POLICY] = cpu_thread_policy
        if min_vcpus is not None:
            specs[FlavorSpec.MIN_VCPUS] = min_vcpus

        LOG.tc_step("Set following extra specs: {}".format(specs))
        nova_helper.set_flavor_extra_specs(flavor_id, **specs)

        LOG.tc_step("Boot a vm with above flavor and ensure it's booted on a HT enabled host.")
        vm_id = vm_helper.boot_vm(name='cpu_thread_{}'.format(cpu_thread_policy), flavor=flavor_id)[1]
        ResourceCleanup.add('vm', vm_id)

        vm_host = nova_helper.get_vm_host(vm_id)
        assert vm_host in ht_hosts, "VM host {} is not one of the hyperthreading enabled host {}.".format(vm_host, ht_hosts)

        LOG.tc_step("Attempt to cold migrate VM")
        code, output = vm_helper.cold_migrate_vm(vm_id, fail_ok=True)

        if len(ht_hosts) == 1:
            LOG.tc_step("Check cold migration is rejected due to no other ht host available")
            assert 2 == code, "Cold migrate request is not rejected while no other ht host available."
            assert ColdMigrateErr.HT_HOST_REQUIRED.format(cpu_thread_policy) in output

            assert vm_host == nova_helper.get_vm_host(vm_id), "VM host changed even though cold migration rejected"
        else:
            LOG.tc_step("Check cold migration succeeded and vm is migrated to another HT host")
            assert 0 == code, "Cold migration failed unexpectedly. Details: {}".format(output)

            post_vm_host = nova_helper.get_vm_host(vm_id)
            assert post_vm_host in ht_hosts, "VM is migrated to a host that is not in ht_hosts list. non_ht_hosts " \
                                             "list: {}".format(non_ht_hosts)

        if len(ht_hosts) == 1:
            LOG.tc_step("Attempt to lock host and ensure lock is rejected due to no other HT host to migrate vm to")
            code, output = host_helper.lock_host(host=vm_host, check_first=False, fail_ok=True)
            HostsToRecover.add(vm_host)
            assert 5 == code, "Host lock result unexpected. Details: {}".format(output)

