import random
import time

from pytest import mark, fixture, skip, param

from utils.tis_log import LOG

from consts.reasons import SkipHypervisor, SkipHyperthreading
from consts.stx import FlavorSpec, ImageMetadata
# Do not remove used imports below as they are used in eval()
from consts.cli_errs import CPUThreadErr, SharedCPUErr, ColdMigErr, CPUPolicyErr, ScaleErr

from keywords import nova_helper, system_helper, vm_helper, host_helper, glance_helper, cinder_helper, check_helper
from testfixtures.fixture_resources import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


@fixture(scope='module', autouse=True)
def check_hypervisors():
    hypervisors = host_helper.get_up_hypervisors()
    if not hypervisors:
        skip("No hypervisor available")


def id_gen(val):
    if isinstance(val, list):
        return '-'.join(val)


# TODO: remove test for now due to flavor spec validation is unavailable upstream.
@mark.parametrize(('cpu_policy', 'cpu_thread_policy', 'shared_vcpu', 'min_vcpus', 'expt_err'), [
    param(None, 'isolate', None, None, 'CPUThreadErr.DEDICATED_CPU_REQUIRED_FLAVOR', marks=mark.p3),
    param(None, 'require', None, None, 'CPUThreadErr.DEDICATED_CPU_REQUIRED_FLAVOR', marks=mark.p3),
    param(None, 'prefer', None, None, 'CPUThreadErr.DEDICATED_CPU_REQUIRED_FLAVOR', marks=mark.p3),
    param('shared', 'isolate', None, None, 'CPUThreadErr.DEDICATED_CPU_REQUIRED_FLAVOR', marks=mark.p3),
    param('shared', 'require', None, None, 'CPUThreadErr.DEDICATED_CPU_REQUIRED_FLAVOR', marks=mark.p3),
    # should not be an error for this
    # param('shared', 'prefer', None, None, 'CPUThreadErr.DEDICATED_CPU_REQUIRED', marks=mark.p3),
    # should default to prefer policy
    param('dedicated', '', None, None, 'CPUThreadErr.INVALID_POLICY', marks=mark.p3),  # CGTS-5190
    param('dedicated', 'requi', None, None, 'CPUThreadErr.INVALID_POLICY', marks=mark.p3),  # CGTS-5190
    param('dedicated', 'REQUIRE', None, None, 'CPUThreadErr.INVALID_POLICY', marks=mark.p3),  # CGTS-5190
    param('dedicated', 'AOID', None, None, 'CPUThreadErr.INVALID_POLICY', marks=mark.p3),  # CGTS-5190
    param('dedicated', 'ISOLATE', None, None, 'CPUThreadErr.INVALID_POLICY', marks=mark.p3),  # CGTS-5190
    param('dedicated', 'PREFR', None, None, 'CPUThreadErr.INVALID_POLICY', marks=mark.p3),  # CGTS-5190
    param(None, None, '1', None, 'SharedCPUErr.DEDICATED_CPU_REQUIRED', marks=mark.p3),
    param('shared', None, '0', None, 'SharedCPUErr.DEDICATED_CPU_REQUIRED', marks=mark.p3),
    param('dedicated', 'isolate', '0', None, 'CPUThreadErr.UNSET_SHARED_VCPU', marks=mark.p3),
    param('dedicated', 'require', '1', None, 'CPUThreadErr.UNSET_SHARED_VCPU', marks=mark.p3),
    # param('dedicated', 'require', None, '2', 'CPUThreadErr.UNSET_MIN_VCPUS', marks=mark.p3),    # Deprecated. vcpu scale

])
def _test_cpu_thread_flavor_set_negative(cpu_policy, cpu_thread_policy, shared_vcpu, min_vcpus, expt_err):
    """
    Test cpu thread flavor spec cannot be set due to conflict with other flavor specs in same cli
    Args:
        cpu_policy (str): cpu policy to be set in flavor extra specs
        cpu_thread_policy (str): cpu thread policy to be set in flavor extra specs
        shared_vcpu (str): number of shared_vcpu to be set in flavor extra specs
        min_vcpus (str): min_vcpus to be set in flavor extra specs
        expt_err (str): Expected error string for if negative result is expected


    Test Steps:
        - Create a flavor with 2 vcpus
        - Attempt to set flavor extra specs as per test params
        - check extra spec required cannot be set and expected error is returned when setting extra specs

    Teardowns:
        - Delete created flavor if any

    """
    LOG.tc_step("Create a flavor with 2 vcpus")
    flavor_id = nova_helper.create_flavor(name='cpu_thread_neg1', vcpus=2)[1]
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
    code, output = nova_helper.set_flavor(flavor_id, fail_ok=True, **specs_to_set)

    LOG.tc_step("Verify cli rejected invalid extra specs setting with proper error message.")
    expt_err_eval = eval(expt_err)
    if expt_err in ['CPUThreadErr.INVALID_POLICY', 'CPUThreadErr.UNSET_SHARED_VCPU', 'CPUThreadErr.UNSET_MIN_VCPUS']:
        expt_err_eval = expt_err_eval.format(cpu_thread_policy)

    assert 1 == code, 'Set flavor extra spec is not rejected with invalid extra spec settings: {}.'.format(specs_to_set)
    assert expt_err_eval in output


# TODO: remove test for now due to flavor spec validation is unavailable upstream.
@mark.parametrize(('specs_preset', 'specs_to_set', 'expt_err'), [
    param({FlavorSpec.CPU_POLICY: 'dedicated', FlavorSpec.CPU_THREAD_POLICY: 'isolate'},
             {FlavorSpec.SHARED_VCPU: '1'}, 'CPUThreadErr.UNSET_SHARED_VCPU'),
    param({FlavorSpec.CPU_POLICY: 'dedicated', FlavorSpec.SHARED_VCPU: '0'},
             {FlavorSpec.CPU_THREAD_POLICY: 'require'}, 'CPUThreadErr.UNSET_SHARED_VCPU'),
])
def _test_cpu_thread_flavor_add_negative(specs_preset, specs_to_set, expt_err):
    """
    Test cpu thread flavor cannot be set due to conflict with existing flavor specs

    Args:
        specs_preset (dict): list of extra specs dictionary to preset
        specs_to_set (dict): thread policy extra spec to set
        expt_err (str): expected error message

    Test Steps:
        - Create a flavor with 2 vcpus
        - Set flavor with extra specs defined in specs_preset
        - Attempt to set given cpu thread policy extra spec
        - Check required cpu thread policy cannot be set and expected error is returned when setting extra specs

    Teardowns:
        - Delete created flavor if any

    """
    LOG.tc_step("Create a flavor with 2 vcpus")
    flavor_id = nova_helper.create_flavor(name='cpu_thread_neg1', vcpus=2)[1]
    ResourceCleanup.add('flavor', flavor_id)

    LOG.tc_step("Set following extra specs: {}".format(specs_preset))
    nova_helper.set_flavor(flavor_id, **specs_preset)

    LOG.tc_step("Attempt to set following flavor extra specs: {}".format(specs_to_set))
    code, output = nova_helper.set_flavor(flavor_id, fail_ok=True, **specs_to_set)

    LOG.tc_step("Verify cli rejected invalid extra specs setting with proper error message.")
    expt_err_eval = eval(expt_err)
    if expt_err == 'CPUThreadErr.UNSET_SHARED_VCPU':
        all_specs = specs_preset.copy()
        all_specs.update(specs_to_set)
        expt_err_eval = expt_err_eval.format(all_specs[FlavorSpec.CPU_THREAD_POLICY])

    assert 1 == code, 'Set flavor extra spec is not rejected. Existing specs: {}. Specs to set: {}'.format(
        specs_preset, specs_to_set)
    assert expt_err_eval in output


# TODO: remove test for now due to flavor spec validation is unavailable upstream.
@mark.p1
@mark.parametrize('cpu_thread_policy', [
    'isolate',
    'require',
    'prefer',
])
def _test_cpu_thread_flavor_delete_negative(cpu_thread_policy):
    """
    Test cpu policy spec cannot be deleted from flavor when cpu thread policy is also set

    Args:
        cpu_thread_policy (str): cpu thread policy to be included in flavor

    Test Steps:
        - Create a flavor with 2 vcpus
        - Set flavor cpu_polic=dedicated and given cpu thread policy
        - Attempt to delete cpu policy extra spec
        - Check cpu policy cannot be deleted when cpu thread policy is also set

    Teardowns:
        - Delete created flavor if any

    """
    LOG.tc_step("Create a flavor")
    flavor_id = nova_helper.create_flavor(name='cpu_thread_neg2')[1]
    ResourceCleanup.add('flavor', flavor_id)

    specs = {FlavorSpec.CPU_THREAD_POLICY: cpu_thread_policy, FlavorSpec.CPU_POLICY: 'dedicated'}
    LOG.tc_step("Set following extra specs: {}".format(specs))
    nova_helper.set_flavor(flavor_id, **specs)

    LOG.tc_step("Attempt to unset cpu policy while cpu thread policy is set to {}".format(cpu_thread_policy))
    code, output = nova_helper.unset_flavor(flavor_id, FlavorSpec.CPU_POLICY, check_first=False,
                                            fail_ok=True)
    assert 1 == code, 'Unset cpu policy is not rejected when cpu thread policy is set.'
    assert CPUThreadErr.DEDICATED_CPU_REQUIRED_FLAVOR in output


@fixture(scope='module')
def ht_and_nonht_hosts():
    LOG.fixture_step("(Module) Get hyper-threading enabled and disabled hypervisors")
    nova_hosts = host_helper.get_up_hypervisors()
    ht_hosts = []
    non_ht_hosts = []
    for host in nova_hosts:
        if host_helper.is_host_hyperthreaded(host):
            ht_hosts.append(host)
        else:
            non_ht_hosts.append(host)

    LOG.info('-- Hyper-threading enabled hosts: {}; Hyper-threading disabled hosts: {}'.format(ht_hosts, non_ht_hosts))
    return ht_hosts, non_ht_hosts


class TestHTEnabled:

    @fixture(scope='class', autouse=True)
    def ht_hosts_(self, ht_and_nonht_hosts):
        ht_hosts, non_ht_hosts = ht_and_nonht_hosts

        if not ht_hosts:
            skip("No up hypervisor found with Hyper-threading enabled.")

        return ht_hosts, non_ht_hosts

    def test_isolate_vm_on_ht_host(self, ht_hosts_, add_admin_role_func):
        """
        Test isolate vms take the host log_core sibling pair for each vcpu when HT is enabled.
        Args:
            ht_hosts_:
            add_admin_role_func:

        Pre-conditions: At least on hypervisor has HT enabled

        Test Steps:
            - Launch VM with isolate thread policy and 4 vcpus, until all Application cores on thread-0 are taken
            - Attempt to launch another vm on same host, and ensure it fails

        """
        ht_hosts, non_ht_hosts = ht_hosts_
        vcpu_count = 4
        cpu_thread_policy = 'isolate'
        LOG.tc_step("Create flavor with {} vcpus and {} thread policy".format(vcpu_count, cpu_thread_policy))
        flavor_id = nova_helper.create_flavor(name='cpu_thread_{}'.format(cpu_thread_policy), vcpus=vcpu_count,
                                              cleanup='function')[1]
        specs = {FlavorSpec.CPU_POLICY: 'dedicated', FlavorSpec.CPU_THREAD_POLICY: cpu_thread_policy}
        nova_helper.set_flavor(flavor_id, **specs)

        LOG.tc_step("Get used vcpus for vm host before booting vm, and ensure sufficient instance and core quotas")
        host = ht_hosts[0]
        vms = vm_helper.get_vms_on_host(hostname=host)
        vm_helper.delete_vms(vms=vms)
        log_core_counts = host_helper.get_logcores_counts(host, thread='0', functions='Application')
        max_vm_count = int(log_core_counts[0] / vcpu_count) + int(log_core_counts[1] / vcpu_count)
        vm_helper.ensure_vms_quotas(vms_num=max_vm_count + 10, cores_num=4 * (max_vm_count + 2) + 10)

        LOG.tc_step("Boot {} isolate 4vcpu vms on a HT enabled host, and check topology of vm on host and vms".
                    format(max_vm_count))
        for i in range(max_vm_count):
            name = '4vcpu_isolate-{}'.format(i)
            LOG.info("Launch VM {} on {} and check it's topology".format(name, host))
            prev_cpus = host_helper.get_vcpus_for_computes(hosts=[host], field='used_now')[host]
            vm_id = vm_helper.boot_vm(name=name, flavor=flavor_id, vm_host=host,
                                      cleanup='function')[1]

            check_helper.check_topology_of_vm(vm_id, vcpus=vcpu_count, prev_total_cpus=prev_cpus, cpu_pol='dedicated',
                                              cpu_thr_pol=cpu_thread_policy, vm_host=host)

        LOG.tc_step("Attempt to boot another vm on {}, and ensure it fails due to no free sibling pairs".format(host))
        code = vm_helper.boot_vm(name='cpu_thread_{}'.format(cpu_thread_policy), flavor=flavor_id, vm_host=host,
                                 fail_ok=True, cleanup='function')[0]
        assert code > 0, "VM is still scheduled even though all sibling pairs should have been occupied"

    @mark.parametrize(('vcpus', 'cpu_thread_policy', 'min_vcpus'), [
        # param(5, 'isolate', 2),       # Deprecated. vcpu scale
        # param(4, 'isolate', None),    # Already covered by new test_isolate_vm_on_ht_host
        param(4, 'require', None),
        param(3, 'require', None),
        param(3, 'prefer', None),
        # param(2, 'prefer', 1),
        # param(3, None, 1),          # Deprecated. vcpu scale # should default to prefer policy behaviour
        # param(2, None, None),       # Already covered by many other test cases with default settings
    ])
    def test_boot_vm_cpu_thread_positive(self, vcpus, cpu_thread_policy, min_vcpus, ht_hosts_):
        """
        Test boot vm with specific cpu thread policy requirement

        Args:
            vcpus (int): number of vpus to set when creating flavor
            cpu_thread_policy (str): cpu thread policy to set in flavor
            min_vcpus (int): min_vcpus extra spec to set
            ht_hosts_ (tuple): (ht_hosts, non-ht_hosts)

        Skip condition:
            - no host is hyperthreading enabled on system

        Setups:
            - Find out HT hosts and non-HT_hosts on system   (module)

        Test Steps:
            - Create a flavor with given number of vcpus
            - Set cpu policy to dedicated and extra specs as per test params
            - Get the host vcpu usage before booting vm
            - Boot a vm with above flavor
            - Ensure vm is booted on HT host for 'require' vm
            - Check vm-topology, host side vcpu usage, topology from within the guest to ensure vm is properly booted

        Teardown:
            - Delete created vm, volume, flavor

        """
        ht_hosts, non_ht_hosts = ht_hosts_
        LOG.tc_step("Create flavor with {} vcpus".format(vcpus))
        flavor_id = nova_helper.create_flavor(name='cpu_thread_{}'.format(cpu_thread_policy), vcpus=vcpus)[1]
        ResourceCleanup.add('flavor', flavor_id)

        specs = {FlavorSpec.CPU_POLICY: 'dedicated'}
        if cpu_thread_policy is not None:
            specs[FlavorSpec.CPU_THREAD_POLICY] = cpu_thread_policy

        if min_vcpus is not None:
            specs[FlavorSpec.MIN_VCPUS] = min_vcpus

        LOG.tc_step("Set following extra specs: {}".format(specs))
        nova_helper.set_flavor(flavor_id, **specs)

        LOG.tc_step("Get used cpus for all hosts before booting vm")
        hosts_to_check = ht_hosts if cpu_thread_policy == 'require' else ht_hosts + non_ht_hosts
        pre_hosts_cpus = host_helper.get_vcpus_for_computes(hosts=hosts_to_check, field='used_now')

        LOG.tc_step("Boot a vm with above flavor and ensure it's booted on a HT enabled host.")
        vm_id = vm_helper.boot_vm(name='cpu_thread_{}'.format(cpu_thread_policy), flavor=flavor_id,
                                  cleanup='function')[1]

        vm_host = vm_helper.get_vm_host(vm_id)
        if cpu_thread_policy == 'require':
            assert vm_host in ht_hosts, "VM host {} is not hyper-threading enabled.".format(vm_host)

        LOG.tc_step("Check topology of the {}vcpu {} vm on hypervisor and on vm".format(vcpus, cpu_thread_policy))
        prev_cpus = pre_hosts_cpus[vm_host]
        check_helper.check_topology_of_vm(vm_id, vcpus=vcpus, prev_total_cpus=prev_cpus, cpu_pol='dedicated',
                                          cpu_thr_pol=cpu_thread_policy, min_vcpus=min_vcpus, vm_host=vm_host)

    @mark.parametrize(
        ('flv_vcpus', 'flv_cpu_pol', 'flv_cpu_thr_pol', 'img_cpu_thr_pol', 'img_cpu_pol', 'create_vol', 'expt_err'), [
            param(3, None, None, 'isolate', 'dedicated', False, None),
            param(4, None, None, 'require', 'dedicated', False, None),
            param(3, None, None, 'require', 'dedicated', True, None),
            param(3, None, None, 'prefer', 'dedicated', True, None),
            param(2, 'dedicated', None, 'isolate', None, False, None),
            param(2, 'dedicated', None, 'require', None, True, None),
            param(3, 'dedicated', None, 'require', None, False, None),
            param(3, 'dedicated', 'isolate', 'isolate', 'dedicated', True, None),
            param(2, 'dedicated', 'require', 'require', 'dedicated', True, None),
            param(2, 'dedicated', 'prefer', 'prefer', 'dedicated', True, None),
            param(3, 'dedicated', 'prefer', 'prefer', None, True, None),
            # Following two tests removed due to CGTS-6504. Upstream bug was opened.
            # param(3, 'dedicated', 'prefer', 'isolate', 'dedicated', False, None),
            # param(3, 'dedicated', 'prefer', 'require', 'dedicated', True, None),
            param(2, 'dedicated', 'isolate', 'require', 'dedicated', True, 'CPUThreadErr.CONFLICT_FLV_IMG'),
            param(2, 'dedicated', 'require', 'isolate', 'dedicated', True, 'CPUThreadErr.CONFLICT_FLV_IMG'),
            param(3, 'dedicated', 'require', 'isolate', 'dedicated', False, 'CPUThreadErr.CONFLICT_FLV_IMG'),
            param(2, 'dedicated', 'require', 'prefer', 'dedicated', False, 'CPUThreadErr.CONFLICT_FLV_IMG'),
            param(3, 'dedicated', 'isolate', 'prefer', 'dedicated', True, 'CPUThreadErr.CONFLICT_FLV_IMG'),
            param(2, None, None, 'isolate', None, True, 'CPUThreadErr.DEDICATED_CPU_REQUIRED_BOOT_VM'),
            param(2, None, None, 'require', None, False, 'CPUThreadErr.DEDICATED_CPU_REQUIRED_BOOT_VM'),
            param(2, None, None, 'prefer', None, False, 'CPUThreadErr.DEDICATED_CPU_REQUIRED_BOOT_VM'),
            # param(3, 'dedicated', None, 'require', None, True, 'CPUThreadErr.VCPU_NUM_UNDIVISIBLE'),
        ])
    def test_boot_vm_cpu_thread_image(self, flv_vcpus, flv_cpu_pol, flv_cpu_thr_pol, img_cpu_thr_pol, img_cpu_pol,
                                      create_vol, expt_err, ht_hosts_):

        """
        Test boot vm with specific cpu thread policy requirement

        Args:
            flv_vcpus (int): number of vpus to set when creating flavor
            flv_cpu_pol (str): cpu policy in flavor
            flv_cpu_thr_pol (str): cpu thread policy in flavor
            img_cpu_thr_pol: (str) cpu thread policy in image metadata
            img_cpu_pol (str): cpu policy in image metadata
            create_vol (bool): whether to boot from volume or image
            expt_err (str|None): expected error message when booting vm if any
            ht_hosts_ (tuple): (ht_hosts, non-ht_hosts)

        Skip condition:
            - no host is hyperthreading enabled on system

        Setups:
            - Find out HT hosts and non-HT_hosts on system   (module)

        Test Steps:
            - Create a flavor with given number of vcpus
            - Set cpu policy to dedicated and extra specs as per flavor related test params
            - Create an image from tis image
            - Set image metadata as per image related test params
            - Get the host vcpu usage before booting vm
            - Attempt to boot a vm with above flavor and image
                - if expt_err is None:
                    - Ensure vm is booted on HT host for 'require' vm
                    - Check vm-topology, host side vcpu usage, topology from within the guest to ensure vm
                        is properly booted
                - else, ensure expected error message is included in nova show

        Teardown:
            - Delete created vm, volume, flavor, image

        """
        ht_hosts, non_ht_hosts = ht_hosts_
        LOG.tc_step("Create flavor with {} vcpus".format(flv_vcpus))
        flavor_id = nova_helper.create_flavor(name='cpu_thread_image', vcpus=flv_vcpus)[1]
        ResourceCleanup.add('flavor', flavor_id)

        if flv_cpu_pol is not None:
            specs = {FlavorSpec.CPU_POLICY: flv_cpu_pol}
            if flv_cpu_thr_pol is not None:
                specs[FlavorSpec.CPU_THREAD_POLICY] = flv_cpu_thr_pol

            LOG.tc_step("Set following extra specs: {}".format(specs))
            nova_helper.set_flavor(flavor_id, **specs)

        LOG.tc_step("Get used cpus for all hosts before booting vm")
        hosts_to_check = ht_hosts if img_cpu_thr_pol == 'require' else ht_hosts + non_ht_hosts
        pre_hosts_cpus = host_helper.get_vcpus_for_computes(hosts=hosts_to_check, field='used_now')

        image_meta = {ImageMetadata.CPU_THREAD_POLICY: img_cpu_thr_pol}
        if img_cpu_pol:
            image_meta[ImageMetadata.CPU_POLICY] = img_cpu_pol

        LOG.tc_step("Create image with following metadata: {}".format(image_meta))
        image_id = glance_helper.create_image(name='cpu_thread_{}'.format(img_cpu_thr_pol), cleanup='function',
                                              **image_meta)[1]
        if create_vol:
            LOG.tc_step("Create a volume from above image")
            source_id = cinder_helper.create_volume(name='cpu_thr_img', source_id=image_id)[1]
            ResourceCleanup.add('volume', source_id)
            source = 'volume'
        else:
            source_id = image_id
            source = 'image'

        LOG.tc_step("Attempt to boot a vm with above flavor and {}".format(source))
        code, vm_id, msg = vm_helper.boot_vm(name='cpu_thread_image', flavor=flavor_id, source=source,
                                             source_id=source_id, fail_ok=True, cleanup='function')

        # check for negative tests
        if expt_err is not None:
            LOG.tc_step("Check VM failed to boot due to conflict in flavor and image.")
            assert 4 == code, "Expect boot vm cli reject and no vm booted. Actual: {}".format(msg)
            assert eval(expt_err) in msg, "Expected error message is not found in cli return."

            return  # end the test for negative cases

        # Check for positive tests
        LOG.tc_step("Check vm is successfully booted on a HT enabled host.")
        assert 0 == code, "Expect vm boot successfully. Actual: {}".format(msg)

        vm_host = vm_helper.get_vm_host(vm_id)
        if flv_cpu_thr_pol == 'require':
            assert vm_host in ht_hosts, "VM host {} is not hyper-threading enabled.".format(vm_host)

        # Calculate expected policy. Image overrides flavor.
        expt_thr_pol = img_cpu_thr_pol if img_cpu_thr_pol else flv_cpu_thr_pol
        expt_cpu_pol = flv_cpu_pol if flv_cpu_pol else img_cpu_pol

        # Check vm topology on controller, compute, vm
        prev_cpus = pre_hosts_cpus[vm_host]

        check_helper.check_topology_of_vm(vm_id, vcpus=flv_vcpus, prev_total_cpus=prev_cpus, vm_host=vm_host,
                                          cpu_pol=expt_cpu_pol, cpu_thr_pol=expt_thr_pol)

    @fixture(scope='function')
    def prepare_multi_vm_env(self, ht_hosts_, request):
        ht_hosts, non_ht_hosts = ht_hosts_
        if len(ht_hosts) > 1:
            # Only run test on lab with 1 ht host for sibling cores checking purpose.
            # IP14-17, IP1-4, IP33-36 can be used for this testcase
            skip("More than one host has hyper-threading enabled.")

        ht_host = ht_hosts[0]

        LOG.fixture_step("Create flavor with 4 vcpus")
        flavor_id = nova_helper.create_flavor(name='cpu_thread', vcpus=4)[1]
        ResourceCleanup.add('flavor', flavor_id)

        specs = {FlavorSpec.CPU_THREAD_POLICY: 'isolate', FlavorSpec.CPU_POLICY: 'dedicated'}
        LOG.fixture_step("Set following extra specs: {}".format(specs))
        nova_helper.set_flavor(flavor_id, **specs)

        LOG.fixture_step("Calculate max number of 4-core-isolate VMs with can be booted on {}".format(ht_host))
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
        vm_helper.ensure_vms_quotas(vms_num=max_vm_num + 10, cores_num=max_cores + 8)

        # # 8 cores because for isolate the sibling cores are always reserved. So it's 4*2.
        # max_vm_num = int(max_cores / 8)
        LOG.info("Maximum {} 4-core-isolate VMs can still be booted on {}".format(max_vm_num, ht_host))

        # left_over_isolate_cores = int((max_cores - max_vm_num * 8)/2)
        left_over_isolate_cores = left_over_unpinned_cpus / 2
        return ht_host, max_vm_num, flavor_id, left_over_isolate_cores, non_ht_hosts

    @mark.p2
    # TODO Use require instead
    def _test_boot_multiple_vms_cpu_thread_isolate(self, prepare_multi_vm_env):
        """
        Test isolate thread policy with multiple vms

        Args:
            prepare_multi_vm_env (tuple): Calculate max number of isolate vms can be booted on specified HT host

        Skip condition:
            - no host is hyperthreading enabled on system

        Setups:
            - Find out HT hosts and non-HT_hosts on system   (module)
            - Ensure system only has one HT host  (function)

        Test Steps:
            - Create a flavor with 4 vcpus
            - Set cpu policy to dedicated and cpu thread policy to isolate
            - Get the host vcpu usage before booting vm
            - Boot a vm with above flavor and image
            - Ensure vm is booted on target host
            - Check vm-topology, host side vcpu usage, topology from within the guest to ensure vm is properly booted
            - Repeat boot vm steps until pre-calculated maximum number of vms reached
            - Boot one more vm and ensure it's rejected

        Teardown:
            - Delete created vms, volumes, flavor

        """
        ht_host, max_vm_num, flavor_id, left_over_isolate_cores, non_ht_hosts = prepare_multi_vm_env
        log_cores_siblings = host_helper.get_logcore_siblings(host=ht_host)

        LOG.tc_step("Boot {} vms with isolate cpu thread policy and 4vcpus in flavor".format(max_vm_num))
        total_vms_core_pairs = []
        for i in range(max_vm_num):

            pre_boot_used_cpus = host_helper.get_vcpus_for_computes(hosts=ht_host, field='used_now')[ht_host]

            LOG.tc_step("Boot VM_{} with above flavor and ensure it's booted on the HT enabled host.".format(i + 1))
            vm_id = vm_helper.boot_vm(name='cpu_thread_isolate', flavor=flavor_id, cleanup='function')[1]

            vm_host = vm_helper.get_vm_host(vm_id)
            # TODO: Might need update if isolate vm has no priority to boot on ht host
            assert ht_host == vm_host, "VM host {} is not hyper-threading enabled.".format(vm_host)

            LOG.tc_step('Check total used vcpus for vm host is increased by 8 via nova host-describe')
            post_boot_used_cpus = host_helper.get_vcpus_for_computes(hosts=vm_host, field='used_now')[ht_host]
            assert pre_boot_used_cpus + 8 == post_boot_used_cpus, "vcpus used on ht host {} is not increased by " \
                                                                  "8".format(ht_host)

            LOG.tc_step("Check topology, siblings, pcpus via vm-topology for vm {}".format(vm_id))
            instance_topology = vm_helper.get_instance_topology(vm_id)
            vm_pcpus = []
            for topology_on_numa_node in instance_topology:  # TODO is it possible to be on two numa nodes?

                assert topology_on_numa_node['siblings'] is None, "Siblings should not be displayed for 'isolate' vm"

                # TODO assert '4c,1t' in topology_on_numa_node['topology'], 'vm topology is not as expected'

                pcpus = topology_on_numa_node['pcpus']
                if pcpus:
                    pcpus = sorted(pcpus)
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

        LOG.tc_step("Boot one more vm, and ensure it does not boot on HT host due to insufficient cores on HT host.")
        code, vm_id, msg = vm_helper.boot_vm(name='insufficient_cores_isolate', flavor=flavor_id, fail_ok=True,
                                             cleanup='function')

        # if non_ht_hosts:
        #     vm_host_ht_full = nova_helper.get_vm_host(vm_id)
        #     assert 0 == code, "VM is not successfully booted even though non HT host available"
        #     assert vm_host_ht_full in non_ht_hosts, "VM is not booted on non-HT host"
        # else:
        assert 1 == code, "Boot vm cli is not rejected. Details: {}".format(msg)

        LOG.tc_step("Check expected fault message displayed in nova show")
        fault_msg = vm_helper.get_vm_fault_message(vm_id)
        assert "No valid host was found" in fault_msg
        assert CPUThreadErr.INSUFFICIENT_CORES_FOR_ISOLATE.format(ht_host, 4) in fault_msg

    # Deprecated - numa pinning. Rest is covered by test_cpu_thread_vm_topology_nova_actions
    @mark.parametrize(
    ('vcpus', 'cpu_pol', 'cpu_thr_pol', 'min_vcpus', 'numa_0', 'vs_numa_affinity', 'boot_source', 'nova_actions', 'host_action'), [
        param(1, 'dedicated', 'isolate', None, None, None, 'volume', 'live_migrate', None, marks=mark.p3),
        param(2, 'dedicated', 'isolate', 1, None, None, 'image', 'live_migrate', None, marks=mark.p3),
        param(4, 'dedicated', 'require', None, None, 'strict', 'volume', 'live_migrate', None, marks=mark.domain_sanity),
        param(3, 'dedicated', 'prefer', 2, None, 'strict', 'volume', 'live_migrate', None, marks=mark.p3),
        param(6, 'dedicated', 'isolate', 4, 0, None, 'volume', 'cold_migrate', None, marks=mark.p3),
        param(4, 'dedicated', 'require', None, None, 'strict', 'volume', 'cold_migrate', None, marks=mark.domain_sanity),
        param(4, 'dedicated', 'prefer', 2, None, 'strict', 'volume', 'cold_migrate', None, marks=mark.p3),
        param(2, 'dedicated', 'require', None, None, None, 'volume', 'cold_mig_revert', None, marks=mark.p3),
        param(3, 'dedicated', 'isolate', None, None, 'strict', 'volume', 'cold_mig_revert', None, marks=mark.p3),
        param(2, 'dedicated', 'prefer', None, None, None, 'volume', 'cold_mig_revert', None, marks=mark.p3),
        param(4, 'dedicated', 'isolate', 2, None, None, 'volume', ['suspend', 'resume', 'rebuild'], None, marks=mark.p3),
        param(6, 'dedicated', 'require', None, None, 'strict', 'volume', ['suspend', 'resume', 'rebuild'], None, marks=mark.priorities('nightly', 'domain_sanity', 'sx_nightly')),
        param(5, 'dedicated', 'prefer', None, None, 'strict', 'volume', ['suspend', 'resume', 'rebuild'], None, marks=mark.p3),
        param(3, 'dedicated', 'isolate', None, None, 'strict', 'volume', ['cold_migrate', 'live_migrate'], 'evacuate', marks=mark.domain_sanity),
    ], ids=id_gen)
    def _test_cpu_thread_vm_topology_nova_actions(self, vcpus, cpu_pol, cpu_thr_pol, min_vcpus, numa_0,
                                                  vs_numa_affinity, boot_source, nova_actions, host_action, ht_hosts_):
        ht_hosts, non_ht_hosts = ht_hosts_

        if 'mig' in nova_actions or 'evacuate' == host_action:
            if len(ht_hosts) + len(non_ht_hosts) < 2:
                skip(SkipHypervisor.LESS_THAN_TWO_HYPERVISORS)
            if cpu_thr_pol in ['require', 'isolate'] and len(ht_hosts) < 2:
                skip(SkipHyperthreading.LESS_THAN_TWO_HT_HOSTS)

        # Boot vm with given requirements and check vm is booted with correct topology
        LOG.tc_step("Create flavor with {} vcpus".format(vcpus))
        flavor_id = nova_helper.create_flavor(name='cpu_thr_{}_{}'.format(cpu_thr_pol, vcpus), vcpus=vcpus)[1]
        ResourceCleanup.add('flavor', flavor_id)

        specs_dict = {
            FlavorSpec.CPU_POLICY: cpu_pol,
            FlavorSpec.CPU_THREAD_POLICY: cpu_thr_pol,
            FlavorSpec.MIN_VCPUS: min_vcpus,
            FlavorSpec.NUMA_0: numa_0,
            FlavorSpec.VSWITCH_NUMA_AFFINITY: vs_numa_affinity
        }
        specs = {}
        for key, value in specs_dict.items():
            if value is not None:
                specs[key] = value

        if specs:
            LOG.tc_step("Set following extra specs: {}".format(specs))
            nova_helper.set_flavor(flavor_id, **specs)

        LOG.tc_step("Get used cpus for all hosts before booting vm")
        hosts_to_check = ht_hosts if cpu_thr_pol == 'require' else ht_hosts + non_ht_hosts
        pre_hosts_cpus = host_helper.get_vcpus_for_computes(hosts=hosts_to_check, field='used_now')

        LOG.tc_step("Boot a vm with above flavor and ensure it's booted on a HT enabled host.")
        vm_name = 'cpu_thr_{}_{}'.format(cpu_thr_pol, vcpus)
        vm_id = vm_helper.boot_vm(name=vm_name, flavor=flavor_id, source=boot_source, cleanup='function')[1]

        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

        if vs_numa_affinity == 'strict':
            LOG.tc_step("Check VM is booted on vswitch numa nodes, when vswitch numa affinity set to strict")
            check_helper.check_vm_vswitch_affinity(vm_id, on_vswitch_nodes=True)

        vm_host = vm_helper.get_vm_host(vm_id)
        if cpu_thr_pol == 'require':
            assert vm_host in ht_hosts, "VM host {} is not hyper-threading enabled.".format(vm_host)

        prev_cpus = pre_hosts_cpus[vm_host]

        prev_siblings = check_helper.check_topology_of_vm(vm_id, vcpus=vcpus, prev_total_cpus=prev_cpus,
                                                          cpu_pol=cpu_pol, cpu_thr_pol=cpu_thr_pol,
                                                          min_vcpus=min_vcpus, vm_host=vm_host)[1]

        # Perform Nova action(s) and check vm topology
        LOG.tc_step("Perform following nova action(s) on vm {}: {}".format(vm_id, nova_actions))
        if isinstance(nova_actions, str):
            nova_actions = [nova_actions]

        for action in nova_actions:
            vm_helper.perform_action_on_vm(vm_id, action=action)
            time.sleep(10)

        post_vm_host = vm_helper.get_vm_host(vm_id)

        pre_action_cpus = pre_hosts_cpus[post_vm_host]
        if cpu_thr_pol == 'require':
            LOG.tc_step("Check vm is on HT host")
            assert post_vm_host in ht_hosts, "VM host {} is not hyper-threading enabled.".format(vm_host)
        elif cpu_thr_pol == 'prefer':
            prev_siblings = prev_siblings if nova_actions == ['live_migrate'] else None

        LOG.tc_step("Check VM topology is still correct after {}".format(nova_actions))
        check_helper.check_topology_of_vm(vm_id, vcpus=vcpus, prev_total_cpus=pre_action_cpus, cpu_pol=cpu_pol,
                                          cpu_thr_pol=cpu_thr_pol, min_vcpus=min_vcpus, vm_host=post_vm_host,
                                          prev_siblings=prev_siblings)

        if vs_numa_affinity == 'strict':
            LOG.tc_step("Check VM is still on vswitch numa nodes, when vswitch numa affinity set to strict")
            check_helper.check_vm_vswitch_affinity(vm_id, on_vswitch_nodes=True)

        LOG.tc_step("Check VM still pingable from NatBox after Nova action(s)")
        vm_helper.ping_vms_from_natbox(vm_id)

        # Perform host action and check vm topology
        if host_action == 'evacuate':
            target_host = post_vm_host
            LOG.tc_step("Reboot vm host {}".format(target_host))
            vm_helper.evacuate_vms(host=target_host, vms_to_check=vm_id, ping_vms=True)
            vm_host_post_evac = vm_helper.get_vm_host(vm_id=vm_id)

            LOG.tc_step("Check VM topology is still correct after host reboot")
            check_helper.check_topology_of_vm(vm_id, vcpus=vcpus, prev_total_cpus=prev_cpus, cpu_pol=cpu_pol,
                                              cpu_thr_pol=cpu_thr_pol, min_vcpus=min_vcpus, vm_host=vm_host_post_evac)

            if vs_numa_affinity == 'strict':
                LOG.tc_step("Check VM is still on vswitch numa nodes, when vswitch numa affinity set to strict")
                check_helper.check_vm_vswitch_affinity(vm_id, on_vswitch_nodes=True)

            LOG.tc_step("Check VMs are pingable from NatBox after evacuation")
            vm_helper.ping_vms_from_natbox(vm_id)

    @mark.parametrize(('vcpus', 'cpu_pol', 'cpu_thr_pol', 'flv_or_img', 'vs_numa_affinity', 'boot_source', 'nova_actions'), [
        param(2, 'dedicated', 'isolate', 'image', None, 'volume', 'live_migrate', marks=mark.priorities('domain_sanity', 'nightly')),
        # mark.domain_sanity((4, 'dedicated', 'require', 'image', 'strict', 'image', 'live_migrate'),
        param(3, 'dedicated', 'require', 'image', None, 'volume', 'live_migrate', marks=mark.domain_sanity),
        # param(4, 'dedicated', 'prefer', 'image', 'strict', 'image', 'live_migrate', marks=mark.p2),
        # param(1, 'dedicated', 'isolate', 'flavor', 'strict', 'volume', 'live_migrate', marks=mark.p2),
        param(3, 'dedicated', 'prefer', 'flavor', None, 'volume', 'live_migrate', marks=mark.p2),
        param(3, 'dedicated', 'require', 'flavor', None, 'volume', 'live_migrate', marks=mark.p2),
        param(3, 'dedicated', 'isolate', 'flavor', None, 'volume', 'cold_migrate', marks=mark.domain_sanity),
        param(2, 'dedicated', 'require', 'image', None, 'image', 'cold_migrate', marks=mark.domain_sanity),
        param(2, 'dedicated', 'require', 'flavor', None, 'volume', 'cold_mig_revert', marks=mark.p2),
        param(5, 'dedicated', 'prefer', 'image', None, 'volume', 'cold_mig_revert'),
        param(4, 'dedicated', 'isolate', 'image', None, 'volume', ['suspend', 'resume', 'rebuild'], marks=mark.p2),
        param(6, 'dedicated', 'require', 'image', None, 'image', ['suspend', 'resume', 'rebuild'], marks=mark.p2),
        # param(5, 'dedicated', 'prefer', 'image', 'strict', 'volume', ['suspend', 'resume', 'rebuild']),
        # mark.domain_sanity((3, 'dedicated', 'require', 'image', 'strict', 'volume', ['suspend', 'resume', 'rebuild']),
    ], ids=id_gen)
    def test_cpu_thread_vm_topology_nova_actions(self, vcpus, cpu_pol, cpu_thr_pol, flv_or_img, vs_numa_affinity,
                                                 boot_source, nova_actions, ht_hosts_):
        ht_hosts, non_ht_hosts = ht_hosts_
        if 'mig' in nova_actions:
            if len(ht_hosts) + len(non_ht_hosts) < 2:
                skip(SkipHypervisor.LESS_THAN_TWO_HYPERVISORS)
            if cpu_thr_pol in ['require', 'isolate'] and len(ht_hosts) < 2:
                skip(SkipHyperthreading.LESS_THAN_TWO_HT_HOSTS)

        name_str = 'cpu_thr_{}_in_img'.format(cpu_pol)

        LOG.tc_step("Create flavor with {} vcpus".format(vcpus))
        flavor_id = nova_helper.create_flavor(name='vcpus{}'.format(vcpus), vcpus=vcpus)[1]
        ResourceCleanup.add('flavor', flavor_id)

        specs = {}
        if vs_numa_affinity:
            specs[FlavorSpec.VSWITCH_NUMA_AFFINITY] = vs_numa_affinity

        if flv_or_img == 'flavor':
            specs[FlavorSpec.CPU_POLICY] = cpu_pol
            specs[FlavorSpec.CPU_THREAD_POLICY] = cpu_thr_pol

        if specs:
            LOG.tc_step("Set following extra specs: {}".format(specs))
            nova_helper.set_flavor(flavor_id, **specs)

        image_id = None
        if flv_or_img == 'image':
            image_meta = {ImageMetadata.CPU_POLICY: cpu_pol, ImageMetadata.CPU_THREAD_POLICY: cpu_thr_pol}
            LOG.tc_step("Create image with following metadata: {}".format(image_meta))
            image_id = glance_helper.create_image(name=name_str, cleanup='function', **image_meta)[1]

        LOG.tc_step("Get used cpus for all hosts before booting vm")
        hosts_to_check = ht_hosts if cpu_thr_pol == 'require' else ht_hosts + non_ht_hosts
        pre_hosts_cpus = host_helper.get_vcpus_for_computes(hosts=hosts_to_check, field='used_now')

        LOG.tc_step("Boot a vm from {} with above flavor".format(boot_source))
        vm_id = vm_helper.boot_vm(name=name_str, flavor=flavor_id, source=boot_source, image_id=image_id,
                                  cleanup='function')[1]

        vm_host = vm_helper.get_vm_host(vm_id)

        if cpu_thr_pol == 'require':
            LOG.tc_step("Check vm is booted on a HT host")
            assert vm_host in ht_hosts, "VM host {} is not hyper-threading enabled.".format(vm_host)

        # TODO: Remove vswitch numa affinity checking for now due to feature unavailable yet
        # if vs_numa_affinity == 'strict':
        #     LOG.tc_step("Check VM is booted on vswitch numa node, when vswitch numa affinity set to strict")
        #     check_helper.check_vm_vswitch_affinity(vm_id, on_vswitch_nodes=True)

        prev_cpus = pre_hosts_cpus[vm_host]
        prev_siblings = check_helper.check_topology_of_vm(vm_id, vcpus=vcpus, prev_total_cpus=prev_cpus,
                                                          cpu_pol=cpu_pol, cpu_thr_pol=cpu_thr_pol, vm_host=vm_host)[1]

        LOG.tc_step("Perform following nova action(s) on vm {}: {}".format(vm_id, nova_actions))
        if isinstance(nova_actions, str):
            nova_actions = [nova_actions]

        check_prev_siblings = False
        for action in nova_actions:
            kwargs = {}
            if action == 'rebuild':
                kwargs['image_id'] = image_id
            elif action == 'live_migrate':
                check_prev_siblings = True
            vm_helper.perform_action_on_vm(vm_id, action=action, **kwargs)

        post_vm_host = vm_helper.get_vm_host(vm_id)
        pre_action_cpus = pre_hosts_cpus[post_vm_host]

        if cpu_thr_pol == 'require':
            LOG.tc_step("Check vm is still on HT host")
            assert post_vm_host in ht_hosts, "VM host {} is not hyper-threading enabled.".format(vm_host)

        LOG.tc_step("Check VM topology is still correct after {}".format(nova_actions))
        if cpu_pol != 'dedicated' or not check_prev_siblings:
            # Allow prev_siblings in live migration case
            prev_siblings = None
        check_helper.check_topology_of_vm(vm_id, vcpus=vcpus, prev_total_cpus=pre_action_cpus, cpu_pol=cpu_pol,
                                          cpu_thr_pol=cpu_thr_pol, vm_host=post_vm_host, prev_siblings=prev_siblings)

        # TODO: Remove vswitch affinity checking for now
        # if vs_numa_affinity == 'strict':
        #     LOG.tc_step("Check VM is still on vswitch numa nodes, when vswitch numa affinity set to strict")
        #     check_helper.check_vm_vswitch_affinity(vm_id, on_vswitch_nodes=True)

    @fixture(scope='class')
    def _add_hosts_to_cgcsauto(self, request, ht_hosts_, add_cgcsauto_zone):
        ht_hosts, non_ht_hosts = ht_hosts_

        if not non_ht_hosts:
            skip("No non-HT host available")

        LOG.fixture_step("Add one HT host and nonHT hosts to cgcsauto zone")

        if len(ht_hosts) > 1:
            ht_hosts = [ht_hosts[0]]

        host_in_cgcsauto = ht_hosts + non_ht_hosts

        def _revert():
            nova_helper.remove_hosts_from_aggregate(aggregate='cgcsauto', hosts=host_in_cgcsauto)

        request.addfinalizer(_revert)

        nova_helper.add_hosts_to_aggregate('cgcsauto', ht_hosts + non_ht_hosts)

        LOG.info("cgcsauto zone: HT: {}; non-HT: {}".format(ht_hosts, non_ht_hosts))
        return ht_hosts, non_ht_hosts

    @mark.parametrize(('vcpus', 'cpu_pol', 'cpu_thr_pol', 'cpu_thr_source', 'vs_numa_affinity', 'boot_source'), [
        # (2, 'dedicated', 'isolate', 'flavor', 'strict', 'volume'),
        # (1, 'dedicated', 'isolate', 'flavor', None, 'image'),
        param(4, 'dedicated', 'require', 'flavor', None, 'volume', marks=mark.p3),
        # (3, 'dedicated', 'isolate', 'image', None, 'volume'),
        param(2, 'dedicated', 'require', 'image', None, 'volume', marks=mark.p3)
    ])
    def test_cpu_thr_live_mig_negative(self, vcpus, cpu_pol, cpu_thr_pol, cpu_thr_source, vs_numa_affinity,
                                       boot_source, _add_hosts_to_cgcsauto):
        """
        Test live migration is rejected for require VM when only one HT host available

        Args:
            vcpus:
            cpu_pol:
            cpu_thr_pol:
            cpu_thr_source:
            vs_numa_affinity:
            boot_source:

        Skip condition:
            - More than one HT host available
            - Less than two up hypervisors available

        Test Steps:
            - Ensure system has only one HT host
            - Create a flavor with given number of vcpus
            - Add vs_numa_affinity to flavor extra spec if specified
            - Based on the cpu_thr_source
                - If cpu_thr_source=flavor: Add cpu policy and cpu thread policy to flavor extra specs
                - If cpu_thr_source=image: Create image with cpu policy and thread policy metadata
            - Boot vm from specified boot source from above flavor and image
            - Check vm is booted with correct topology
            - Attempt to live migrate vm and ensure it's rejected

        Teardown:
            - Delete created vm, volume, flavor, image

        """
        ht_hosts, non_ht_hosts = _add_hosts_to_cgcsauto

        specs = {}
        if cpu_thr_source == 'flavor':
            flv_name = 'cpu_thr_{}_{}'.format(cpu_thr_pol, vcpus)
            specs_dict = {
                FlavorSpec.CPU_POLICY: cpu_pol,
                FlavorSpec.CPU_THREAD_POLICY: cpu_thr_pol,
                FlavorSpec.VSWITCH_NUMA_AFFINITY: vs_numa_affinity
            }
            for key, value in specs_dict.items():
                if value is not None:
                    specs[key] = value

            source_id = None
        else:
            name_str = 'cpu_thr_{}_in_img'.format(cpu_thr_pol)
            flv_name = 'vcpus{}'.format(vcpus)
            if vs_numa_affinity:
                specs[FlavorSpec.VSWITCH_NUMA_AFFINITY] = vs_numa_affinity

            image_meta = {ImageMetadata.CPU_POLICY: cpu_pol, ImageMetadata.CPU_THREAD_POLICY: cpu_thr_pol}
            LOG.tc_step("Create image with following metadata: {}".format(image_meta))
            image_id = glance_helper.create_image(name=name_str, cleanup='function', **image_meta)[1]

            if boot_source == 'volume':
                LOG.tc_step("Create a volume from above image")
                source_id = cinder_helper.create_volume(name=name_str, source_id=image_id)[1]
                ResourceCleanup.add('volume', source_id)
            else:
                source_id = image_id

        LOG.tc_step("Create flavor with {} vcpus".format(vcpus))
        flavor_id = nova_helper.create_flavor(name=flv_name, vcpus=vcpus)[1]
        ResourceCleanup.add('flavor', flavor_id)

        if specs:
            LOG.tc_step("Set following extra specs: {}".format(specs))
            nova_helper.set_flavor(flavor_id, **specs)

        LOG.tc_step("Get used cpus for all hosts before booting vm")
        hosts_to_check = ht_hosts if cpu_thr_pol == 'require' else ht_hosts + non_ht_hosts
        pre_hosts_cpus = host_helper.get_vcpus_for_computes(hosts=hosts_to_check, field='used_now')

        LOG.tc_step("Boot a vm from {} with above flavor and ensure it's booted on HT host.".format(boot_source))
        vm_name = 'cpu_thr_{}_{}_{}'.format(cpu_thr_pol, cpu_thr_source, vcpus)
        vm_id = vm_helper.boot_vm(name=vm_name, flavor=flavor_id, source=boot_source, source_id=source_id,
                                  avail_zone='cgcsauto', cleanup='function')[1]

        vm_host = vm_helper.get_vm_host(vm_id)
        assert vm_host in ht_hosts, "VM host {} is not hyper-threading enabled.".format(vm_host)

        # TODO: remove vswitch affinity checking for now
        # if vs_numa_affinity == 'strict':
        #     LOG.tc_step("Check VM is booted on vswitch numa nodes, when vswitch numa affinity set to strict")
        #     check_helper.check_vm_vswitch_affinity(vm_id, on_vswitch_nodes=True)

        prev_cpus = pre_hosts_cpus[vm_host]

        check_helper.check_topology_of_vm(vm_id, vcpus=vcpus, prev_total_cpus=prev_cpus, cpu_pol=cpu_pol,
                                          cpu_thr_pol=cpu_thr_pol, vm_host=vm_host)

        LOG.tc_step("Attempt to live migrate vm and ensure it's rejected due to no other HT host")
        code, output = vm_helper.live_migrate_vm(vm_id, fail_ok=True)
        assert 1 == code, "Expect live migration request to be rejected. Actual: {}".format(output)

        LOG.tc_step("Attempt to cold migrate vm and ensure it's rejected due to non other HT host")
        code, output = vm_helper.cold_migrate_vm(vm_id, fail_ok=True)
        assert 1 == code, "Expect cold migration request to be rejected. Actual: {}".format(output)

        expt_pol_str = "u'{}'".format(cpu_thr_pol)
        if cpu_thr_source == 'flavor':
            assert ColdMigErr.HT_HOST_REQUIRED.format(expt_pol_str, None) in output
        else:
            assert ColdMigErr.HT_HOST_REQUIRED.format(None, expt_pol_str) in output


class TestHTDisabled:

    @fixture(scope='class', autouse=True)
    def ensure_nonht(self, ht_and_nonht_hosts):
        ht_hosts, non_ht_hosts = ht_and_nonht_hosts
        if not non_ht_hosts:
            skip("No host with HT disabled")

        if ht_hosts:
            LOG.fixture_step("Locking HT hosts to ensure only non-HT hypervisors available")
            HostsToRecover.add(ht_hosts, scope='class')
            for host_ in ht_hosts:
                host_helper.lock_host(host_, swact=True)

    @mark.parametrize(('vcpus', 'cpu_thread_policy', 'min_vcpus', 'expt_err'), [
        param(2, 'require', None, 'CPUThreadErr.HT_HOST_UNAVAIL'),
        param(3, 'require', None, 'CPUThreadErr.HT_HOST_UNAVAIL'),
        # param(2, 'isolate', 2, None),     # Deprecated. vcpu scale
        param(3, 'isolate', None, None),
        # (3, 'isolate', None, 'CPUThreadErr.HT_HOST_UNAVAIL'),
        # (2, 'isolate', '2', 'CPUThreadErr.HT_HOST_UNAVAIL'),
        param(2, 'prefer', None, None),
        # param(3, 'prefer', 2, None),      # Deprecated. vcpu scale
    ])
    def test_boot_vm_cpu_thread_ht_disabled(self, vcpus, cpu_thread_policy, min_vcpus, expt_err):
        """
        Test boot vm with specified cpu thread policy when no HT host is available on system

        Args:
            vcpus (int): number of vcpus to set in flavor
            cpu_thread_policy (str): cpu thread policy in flavor extra spec
            min_vcpus (int): min_vpus in flavor extra spec
            expt_err (str|None): expected error message in nova show if any

        Skip condition:
            - All hosts are hyperthreading enabled on system

        Setups:
            - Find out HT hosts and non-HT_hosts on system   (module)
            - Enusre no HT hosts on system

        Test Steps:
            - Create a flavor with given number of vcpus
            - Set flavor extra specs as per test params
            - Get the host vcpu usage before booting vm
            - Attempt to boot a vm with above flavor
                - if expt_err is None:
                    - Ensure vm is booted on non-HT host for 'isolate'/'prefer' vm
                    - Check vm-topology, host side vcpu usage, topology from within the guest to ensure vm
                        is properly booted
                - else, ensure expected error message is included in nova show for 'require' vm

        Teardown:
            - Delete created vm, volume, flavor

        """

        LOG.tc_step("Create flavor with {} vcpus".format(vcpus))
        flavor_id = nova_helper.create_flavor(name='cpu_thread', vcpus=vcpus)[1]
        ResourceCleanup.add('flavor', flavor_id)

        specs = {FlavorSpec.CPU_THREAD_POLICY: cpu_thread_policy, FlavorSpec.CPU_POLICY: 'dedicated'}
        if min_vcpus is not None:
            specs[FlavorSpec.MIN_VCPUS] = min_vcpus

        LOG.tc_step("Set following extra specs: {}".format(specs))
        nova_helper.set_flavor(flavor_id, **specs)

        LOG.tc_step("Attempt to boot a vm with the above flavor.")
        code, vm_id, msg = vm_helper.boot_vm(name='cpu_thread_{}'.format(cpu_thread_policy),
                                             flavor=flavor_id, fail_ok=True, cleanup='function')

        if expt_err:
            assert 1 == code, "Boot vm cli is not rejected. Details: {}".format(msg)

            # TODO: Remove error message checking. Upstream error msg is very generic. i.e., No valid host was found
            # LOG.tc_step("Check expected fault message displayed in nova show")
            # fault_msg = nova_helper.get_vm_nova_show_value(vm_id, 'fault')
            # flavor_pol = "u'{}'".format(cpu_thread_policy) if cpu_thread_policy is not None else None
            # requested_thread_pols = '[{}, None]'.format(flavor_pol)
            # assert eval(expt_err).format(requested_thread_pols) in fault_msg
        else:
            assert 0 == code, "Boot vm with isolate policy was unsuccessful. Details: {}".format(msg)


class TestVariousHT:

    @fixture(scope='class', params=['two_plus_ht', 'one_ht'])
    def ht_hosts_mix(self, request, ht_and_nonht_hosts):

        ht_hosts, non_ht_hosts = ht_and_nonht_hosts
        if len(host_helper.get_up_hypervisors()) < 2:
            skip("Less than two up hypervisors in system.")
        if not ht_hosts:
            skip("System does not have up host with hyper-threading enabled")

        if request.param == 'two_plus_ht':
            if len(ht_hosts) < 2:
                skip("Less than two hyper-threading enabled up hosts in system")

        else:
            # needs a mix of HT and non HT hosts
            if not non_ht_hosts:
                skip("System does not have up host with hyper-threading disabled")

            if len(ht_hosts) > 1:
                if len(ht_hosts) > 4:
                    skip("More than 4 ht hosts available. Skip to reduce execution time.")

                LOG.fixture_step("Lock all hyper-threading enabled host except one")
                host_to_test = random.choice(ht_hosts)
                if system_helper.is_aio_system():
                    host_to_test = system_helper.get_active_controller_name()
                hosts_to_lock = list(ht_hosts)
                hosts_to_lock.remove(host_to_test)

                for host in hosts_to_lock:
                    HostsToRecover.add(host, scope='class')
                    host_helper.lock_host(host, swact=True)
                # Now system only has one ht host
                ht_hosts = [host_to_test]

        LOG.info('Hyper-threading enabled hosts: {}'.format(ht_hosts))
        LOG.info('Hyper-threading disabled hosts: {}'.format(non_ht_hosts))
        return ht_hosts, non_ht_hosts

    @mark.parametrize(('vcpus', 'cpu_thread_policy', 'min_vcpus'), [
        param(2, 'isolate', None),
        param(2, 'require', None),
        # param(2, 'isolate', 2),   # Deprecated. vcpu scale
        param(3, 'prefer', None),
        param(3, 'require', None),
    ])
    def test_cold_migrate_vm_cpu_thread(self, vcpus, cpu_thread_policy, min_vcpus, ht_hosts_mix):
        """
        Test cold migrate VM with specified cpu thread policy and various ht hosts number (1 or 2+) on system
        Args:
            vcpus:
            cpu_thread_policy:
            min_vcpus:
            ht_hosts_mix:

        Skip conditions:
            - Less than two up hypervisors in system
            - System does not have up host with hyper-threading enabled

        Setups:
            - Ensure system has specified number of HT hosts as per fixture param, lock host(s) when needed   (class)

        Test Steps:
            - Create a flavor with specified vcpus, cpu thread policy and min_vcpus
            - Boot a vm with above flavor
            - Attempt to cold migrate vm
                - Ensure cold migrate is rejected for require vm with only 1 HT host
                    - Ensure lock vm host is also rejected due to no other HT host
                - Ensure cold migrate succeeded otherwise

        Teardown:
            - Delete created vm, volume, flavor
            - Unlock any locked hosts in setup      (class)

        """
        ht_hosts, non_ht_hosts = ht_hosts_mix

        LOG.tc_step("Create flavor with {} vcpus".format(vcpus))
        flavor_id = nova_helper.create_flavor(name='cpu_thread_{}'.format(cpu_thread_policy), vcpus=vcpus)[1]
        ResourceCleanup.add('flavor', flavor_id)

        specs = {FlavorSpec.CPU_POLICY: 'dedicated'}
        if cpu_thread_policy is not None:
            specs[FlavorSpec.CPU_THREAD_POLICY] = cpu_thread_policy

        if min_vcpus is not None:
            specs[FlavorSpec.MIN_VCPUS] = min_vcpus

        LOG.tc_step("Set following extra specs: {}".format(specs))
        nova_helper.set_flavor(flavor_id, **specs)

        LOG.tc_step("Boot a vm with above flavor and ensure it's booted on a HT enabled host.")
        vm_id = vm_helper.boot_vm(name='cpu_thread_{}'.format(cpu_thread_policy), flavor=flavor_id,
                                  cleanup='function')[1]

        vm_host = vm_helper.get_vm_host(vm_id)
        if cpu_thread_policy == 'require':
            assert vm_host in ht_hosts, "VM host {} is not one of the hyperthreading enabled host {}.". \
                format(vm_host, ht_hosts)

        LOG.tc_step("Attempt to cold migrate VM")
        code, output = vm_helper.cold_migrate_vm(vm_id, fail_ok=True)

        if cpu_thread_policy not in ['require'] or len(ht_hosts) > 1:
            LOG.tc_step("Check cold migration succeeded and vm migrated to other host")
            assert 0 == code, "Cold migration failed unexpectedly. Details: {}".format(output)

        else:
            LOG.tc_step("Check cold migration is rejected due to no other ht host available for require vm")
            assert 1 == code, "Cold migrate result unexpected. Details: {}".format(output)

            expt_flv_str = "u'{}'".format(cpu_thread_policy)
            expt_err = ColdMigErr.HT_HOST_REQUIRED.format(expt_flv_str, None)
            assert expt_err in output

            post_vm_host = vm_helper.get_vm_host(vm_id)
            assert vm_host == post_vm_host, "VM host changed even though cold migration rejected"

            # Check lock host rejected
            LOG.tc_step("Attempt to lock host and ensure it is rejected as no other HT host to migrate require vm to")
            code, output = host_helper.lock_host(host=vm_host, check_first=False, fail_ok=True)
            HostsToRecover.add(vm_host)
            assert 0 != code, "Host lock result unexpected. Details: {}".format(output)
