from pytest import mark, fixture, skip

from utils import cli, table_parser
from utils.tis_log import LOG
from consts.cli_errs import CpuAssignment, NumaErr   # Do not remove this. Used in eval()
from consts.cgcs import FlavorSpec
from keywords import host_helper, system_helper, vm_helper, nova_helper, check_helper
from testfixtures.fixture_resources import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


def compare_cores_to_configure(host, function, p0, p1):
    """
    Compare current cores for given host/function and return whether to configure and numbers to configure

    Args:
        host (str):
        function (str):
        p0 (int):
        p1 (int):

    Returns (tuple): (bool, int, int)
        (<is_match>, <p0_to_config>, <p1_to_config>)

    """
    proc_core_dict = host_helper.get_host_cpu_cores_for_function(host, function=function, core_type='log_core')
    current_p0_num = len(proc_core_dict[0])
    current_p1_num = len(proc_core_dict[1])

    p0_to_config = None if p0 == current_p0_num else p0
    p1_to_config = None if p1 == current_p1_num else p1

    return p0_to_config is None and p1_to_config is None, p0_to_config, p1_to_config


@fixture(scope='module', autouse=True)
def host_to_config(request, add_admin_role_module, add_cgcsauto_zone):
    LOG.info("Looking for a host to reconfigure.")
    nova_hosts = host_helper.get_nova_hosts()
    if len(nova_hosts) < 1:
        skip("No nova compute host available in the system, no host to lock and reconfigure.")

    storage_backing, hosts = nova_helper.get_storage_backing_with_max_hosts()
    host = hosts[0]
    host_other = hosts[1] if len(hosts) > 1 else None

    if not host:
        skip("No nova host available to reconfigure in the system.")

    vswitch_proc_core_dict = host_helper.get_host_cpu_cores_for_function(host, function='vSwitch', core_type='log_core')
    pform_proc_core_dict = host_helper.get_host_cpu_cores_for_function(host, function='platform', core_type='log_core')

    vswitch_original_num_p0 = len(vswitch_proc_core_dict[0])
    vswitch_original_num_p1 = len(vswitch_proc_core_dict[1])
    platform_ogigin_num_p0 = len(pform_proc_core_dict[0])
    platform_original_num_p1 = len(pform_proc_core_dict[1])

    def revert():
        post_vswitch_dict = host_helper.get_host_cpu_cores_for_function(host, function='vSwitch', core_type='log_core')
        post_pform_dict = host_helper.get_host_cpu_cores_for_function(host, function='platform', core_type='log_core')
        HostsToRecover.add(host, scope='module')

        LOG.fixture_step('(module) Revert host vswitch/platform cores if more than 2 cores per proc are assigned')
        if (vswitch_proc_core_dict != post_vswitch_dict or pform_proc_core_dict != post_pform_dict) and \
                (len(post_vswitch_dict[0]) > 2 or len(post_vswitch_dict[1]) > 2
                 or len(post_pform_dict[0]) > 2 or len(post_pform_dict[1]) > 2):
            host_helper.lock_host(host, swact=True)
            host_helper.modify_host_cpu(host, 'vswitch', p0=vswitch_original_num_p0, p1=vswitch_original_num_p1)
            host_helper.modify_host_cpu(host, 'platform', p0=platform_ogigin_num_p0, p1=platform_original_num_p1)
            host_helper.unlock_host(host, check_hypervisor_up=True)
    request.addfinalizer(revert)

    ht_enabled = system_helper.is_hyperthreading_enabled(host)
    is_small_system = system_helper.is_small_footprint()

    LOG.info("{} is selected. Hyper-threading is {}enabled".format(host, "not " if ht_enabled else ""))
    return host, ht_enabled, is_small_system, host_other, storage_backing


def id_params_cores(val):
    if isinstance(val, tuple):
        return '_'.join([str(i) for i in val])


class TestVSwitchCPUReconfig:

    @fixture(scope='class')
    def flavor_(self, host_to_config):
        storage_backing = host_to_config[-1]
        flavor = nova_helper.create_flavor(name='flv_{}'.format(storage_backing), storage_backing=storage_backing,
                                           check_storage_backing=False)[1]
        ResourceCleanup.add('flavor', flavor, scope='class')

        return flavor

    @mark.p3
    @mark.parametrize(('platform', 'vswitch', 'ht_required', 'cpe_required'), [
        # (None, None, None, None),           # Test without reconfig
        ((1, 0), (1, 1), None, False),      # Standard lab only
        ((2, 0), (1, 1), None, True),       # CPE only
        ((1, 2), (3, 2), None, None),
        ((1, 2), (2, 2), None, None),
        ((1, 0), (1, 0), False, False),     # Standard lab only
        ((2, 0), (1, 0), False, True),      # CPE only
        # ((2, 0), (2, 0), None, True),       # CPE only    # remove - covered by other test
        ((1, 0), (2, 0), None, False),      # Standard lab only
    ], ids=id_params_cores)
    def test_vswitch_cpu_reconfig_positive(self, host_to_config, flavor_, platform, vswitch, ht_required, cpe_required):
        """
        Test valid vswitch cpu reconfigurations, and verify vm can still be hosted on the modified host

        Args:
            host_to_config: hostname of the host to reconfig
            platform: cpu cores to config for platform
            vswitch: cpu cores to config for vswitch
            ht_required: whether hyperthreading is required for the testcase. skip test if requirement is not met
            cpe_required: whether cpe lab is required for the testcase. skip test if requirement is not met.

        Setups (module):
            - Find a nova host with minimum number of vms (or standby controller if CPE) for testing    (module)
            - Record the cpu configs for vswitch and platform   (module)

        Test Steps:
            - Lock host
            - Reconfigure host platform and vswitch cpus to give numbers
            - Unlock host
            - Check ports and vswitch cores mapping in vswitch.ini are correct
            - Check host is still eligible to schedule instance via in nova host-list
            - Boot a vm
            - Live migrate to host if it's not originally booted on host

        Teardown:
            - Revert host platform and vswitch cpu configs      (module)

        """
        host, ht_enabled, is_cpe, host_other, storage_backing = host_to_config
        HostsToRecover.add(host, scope='class')

        if ht_required is not None and ht_required is not ht_enabled:
            skip("Hyper-threading for {} is not {}".format(host, ht_required))

        if cpe_required is not None and cpe_required is not is_cpe:
            skip("Small footprint is not {}".format(cpe_required))

        if platform is not None or vswitch is not None:
            LOG.tc_step("Reconfigure host cpus. Platform: {}, vSwitch: {}".format(platform, vswitch))
            platform_args = {}
            for i in range(len(platform)):
                if i is not None:
                    platform_args['p'+str(i)] = platform[i]

            vswitch_args = {}
            for j in range(len(vswitch)):
                if j is not None:
                    vswitch_args['p'+str(j)] = vswitch[j]

            LOG.tc_step("Lock and modify cpu for {}".format(host))
            host_helper.lock_host(host, swact=True)
            if platform is not None:
                host_helper.modify_host_cpu(host, 'platform', **platform_args)
            if vswitch is not None:
                host_helper.modify_host_cpu(host, 'vswitch', **vswitch_args)
            host_helper.unlock_host(host, check_hypervisor_up=True)

        LOG.tc_step("Check ports and vswitch cores mapping are correct.")
        check_helper.check_host_vswitch_port_engine_map(host)

        LOG.tc_step("Check {} is still a valid nova host.".format(host))
        host_helper.wait_for_hypervisors_up(host)
        host_helper.wait_for_hosts_in_nova_compute(host, timeout=60, fail_ok=False)

        LOG.tc_step("Check vm can be launched on or live migrated to {}.".format(host))
        vm_id = vm_helper.boot_vm(flavor=flavor_, avail_zone='nova', vm_host=host, cleanup='function')[1]
        # ResourceCleanup.add('vm', vm_id)

        assert host == nova_helper.get_vm_host(vm_id), "VM is not booted on configured host"

    @mark.parametrize(('platform', 'vswitch', 'ht_required', 'cpe_required', 'expt_err'), [
        mark.p1(((1, 1), (5, 5), False, None, "CpuAssignment.VSWITCH_TOO_MANY_CORES")),
        mark.p3(((7, 9), (2, 2), None, None, "CpuAssignment.TOTAL_TOO_MANY_CORES")),   # Assume total<=10 cores/per proc & thread
        mark.p3((('cores-2', 'cores-2'), (2, 2), None, None, "CpuAssignment.NO_VM_CORE")),
        mark.p3(((1, 1), (9, 8), None, None, "CpuAssignment.VSWITCH_TOO_MANY_CORES")),   # Assume total <= 10 cores/per proc & thread
        mark.p3(((5, 5), (5, 4), None, None, "CpuAssignment.VSWITCH_TOO_MANY_CORES")),
        mark.p1(((5, 5), (6, 5), None, None, "CpuAssignment.TOTAL_TOO_MANY_CORES")),  # Assume total<=10core/proc&thread
        mark.p3(((1, 1), (8, 10), None, None, "CpuAssignment.TOTAL_TOO_MANY_CORES")),  # Assume total <= 10 cores/per proc&thread
        mark.p3(((2, 0), (0, 0), None, None, "CpuAssignment.VSWITCH_INSUFFICIENT_CORES")),
    ], ids=id_params_cores)
    def test_vswitch_cpu_reconfig_negative(self, host_to_config, platform, vswitch, ht_required, cpe_required,
                                           expt_err):
        """
        Test negative cases for setting vSwitch cores.
        Args:
            host_to_config:
            platform:
            vswitch:
            ht_required:
            cpe_required:
            expt_err:

        Setups:
            - Find a nova host with minimum number of vms (or standby controller if CPE) for testing    (module)
            - Record the cpu configs for vswitch and platform   (module)
        Test Steps
            - Lock host
            - Modify host cpu platform cores as specified
            - Attempt to modify host cpu vSwitch cores as specified
            - Verify cli is rejected with proper error message
        Teardown:
            - Revert host platform and vswitch cpu configs      (module)

        """
        host, ht_enabled, is_cpe, host_other, storage_backing = host_to_config

        HostsToRecover.add(host, scope='class')

        if ht_required is not None and ht_required is not ht_enabled:
            skip("Hyper-threading for {} is not {}".format(host, ht_required))

        if cpe_required is not None and (cpe_required is not is_cpe):
            skip("Requires {} system.".format("non-CPE" if is_cpe else "CPE"))

        # FIXME
        # total_p0, total_p1 = host_helper.get_logcores_counts(host, proc_ids=(0, 1))
        total_p0, total_p1 = host_helper.get_logcores_counts(host, proc_ids=(0, 1),
                                                             functions=['VMs', 'vSwitch', 'Platform'])

        # convert test params if host to config has more than 10 cores per proc & threaad
        if 'NO_VM_CORE' in expt_err:
            # Unsure about expected behavior with Shared cores. FIXME
            # shared_p0, shared_p1 = host_helper.get_logcores_counts(host, proc_ids=(0, 1), functions='Shared')
            # if shared_p0 > 0 or shared_p1 > 0:
            #     skip("{} has shared core configured. Skip NO_VM_CORE semantic check".format(host))
            #
            platform = int(total_p0) - 2, int(total_p1) - 2
        elif 'TOTAL_TOO_MANY_CORES' in expt_err:
            diff = 0
            if total_p0 > 10 and platform[0] + vswitch[0] > 10:
                diff = total_p0 - 10
            elif total_p1 > 10 and platform[1] + vswitch[1] > 10:
                diff = total_p1 - 10
            platform = platform[0] + diff, platform[1] + diff
        elif 'VSWITCH_TOO_MANY_CORES' in expt_err:
            if total_p0 > 10 and vswitch[0] + vswitch[1] > 10:
                diff = total_p0 - 10
                vswitch = vswitch[0] + diff, vswitch[1] + diff

        platform_args = {}
        for i in range(len(platform)):
            if i is not None:
                platform_args['p' + str(i)] = platform[i]

        vswitch_args = {}
        for j in range(len(vswitch)):
            if j is not None:
                vswitch_args['p' + str(j)] = vswitch[j]

        # if is_cpe and system_helper.get_active_controller_name() == host:
        #     LOG.tc_step("{} is active controller, swact first".format(host))
        #     host_helper.swact_host(host)

        LOG.tc_step("Lock {}".format(host))
        host_helper.lock_host(host, swact=True)

        LOG.tc_step("Attempt to reconfigure host cpus. Platform: {}, vSwitch: {}".format(platform, vswitch))
        # host_helper.modify_host_cpu(host, 'vswitch', **{'p0': 1, 'p1': 0})
        host_helper.modify_host_cpu(host, 'platform', **platform_args)
        code, output = host_helper.modify_host_cpu(host, 'vswitch', fail_ok=True, **vswitch_args)

        LOG.tc_step("Verify modify host cpu vSwitch core request is rejected with expected error message.")
        assert 1 == code, "Modify host cpu request is not rejected."

        if "TOTAL_TOO_MANY_CORES" in expt_err:
            proc_id = 0 if platform[0] + vswitch[0] > total_p0 else 1
            expt_err = eval(expt_err).format(proc_id)
        elif "VSWITCH_INSUFFICIENT_CORES" in expt_err:
            min_core_num = 1        # 2 min platform cores for CPE
            expt_err = eval(expt_err).format(min_core_num)
        else:
            expt_err = eval(expt_err)

        assert expt_err in output, "Expected error string is not in output"


def _get_vms_cores_nums(host, vswitch_cores_dict):
    """

    Args:
        host (str): vm hostname

    Returns (tuple): number of cores for VMs function on non-vSwitch numa node, and vSwitch numa node

    """
    #  vswitch and non-vswitch nodes should be one each when this is called

    vms_cores_dict = host_helper.get_host_cpu_cores_for_function(host, function='VMs')

    vswitch_procs = [proc for proc in vms_cores_dict if vswitch_cores_dict[proc]]
    nonvswitch_procs = [proc for proc in vms_cores_dict if not vswitch_cores_dict[proc]]

    vswitch_node_vm_cores = nonvswitch_node_vm_cores = 0
    if vswitch_procs:
        vswitch_node_vm_cores = len(vms_cores_dict[vswitch_procs[0]])
    if nonvswitch_procs:
        nonvswitch_node_vm_cores = len(vms_cores_dict[nonvswitch_procs[0]])

    return vswitch_node_vm_cores, nonvswitch_node_vm_cores


def _create_flavor(vcpus, storage_backing, vswitch_numa_affinity=None, numa_0=None, numa_nodes=None):
    LOG.tc_step("Create flavor with vcpus={}, vswitch_numa_affinity={}, numa_0={}, numa_nodes={}".
                format(vcpus, vswitch_numa_affinity, numa_0, numa_nodes))
    flv_id = nova_helper.create_flavor('numa_affinity', vcpus=vcpus, storage_backing=storage_backing)[1]
    ResourceCleanup.add('flavor', flv_id)

    specs = {FlavorSpec.CPU_POLICY: 'dedicated'}
    if numa_0 is not None:
        specs[FlavorSpec.NUMA_0] = numa_0
    if numa_nodes is not None:
        specs[FlavorSpec.NUMA_NODES] = numa_nodes
    if vswitch_numa_affinity is not None:
        specs[FlavorSpec.VSWITCH_NUMA_AFFINITY] = vswitch_numa_affinity
    nova_helper.set_flavor_extra_specs(flavor=flv_id, **specs)

    return flv_id


@fixture(scope='module')
def get_hosts(host_to_config):
    host0, ht_enabled, is_cpe, host1, storage_backing = host_to_config
    if not host1:
        storage_backing, hosts = nova_helper.get_storage_backing_with_max_hosts()
        if len(hosts) < 2:
            skip("Less than two up hypervisors support same storage backing")
        else:
            host0 = hosts[0]
            host1 = hosts[1]

    LOG.fixture_step("(module) Delete all vms and volumes on the system")
    vm_helper.delete_vms(stop_first=False)

    LOG.fixture_step("(module) Update cores and instances quota for tenant to ensure vms can boot")
    nova_helper.update_quotas(cores=200, instances=20)

    hosts_to_conf = [host0, host1]
    LOG.fixture_step("(module) Add hosts to cgcsauto aggregate: {}".format(hosts_to_conf))
    nova_helper.add_hosts_to_aggregate('cgcsauto', hosts_to_conf)

    return host0, host1, storage_backing, ht_enabled


class TestNovaSchedulerAVS:

    @fixture(scope='class')
    def hosts_configured(self, get_hosts, config_host_class):
        host0, host1, storage_backing, ht_enabled = get_hosts

        function = 'vSwitch'
        LOG.fixture_step("(class) Configure hosts to have 0 vSwitch cores on p0 and 2 vSwitch cores on p1: {}".
                         format((host0, host1)))

        def _mod_host(host_, p0, p1):
            host_helper.modify_host_cpu(host_, function, p0=p0, p1=p1)

        hosts_to_config = {}

        h0p0_is_match, h0p0_p0_to_conf, h0p0_p1_to_conf = compare_cores_to_configure(host0, function, p0=2, p1=0)
        if h0p0_is_match:
            p0_host = host0  # No config for host0
            p1_host = host1
            h1p1_is_match, h1p1_p0_to_conf, h1p1_p1_to_conf = compare_cores_to_configure(host1, function, p0=0, p1=2)
            if not h1p1_is_match:   # config host1
                hosts_to_config[p1_host] = {'p0': h1p1_p0_to_conf, 'p1': h1p1_p1_to_conf}

        else:
            h1p0_is_match, h1p0_p0_to_conf, h1p0_p1_to_conf = compare_cores_to_configure(host1, function, p0=2, p1=0)
            if h1p0_is_match:
                p0_host = host1
                p1_host = host0
                h0p1_is_match, h0p1_p0_to_conf, h0p1_p1_to_conf = compare_cores_to_configure(host0, function, p0=0,
                                                                                             p1=2)
                if not h0p1_is_match:
                    hosts_to_config[p1_host] = {'p0': h0p1_p0_to_conf, 'p1': h0p1_p1_to_conf}
            else:
                h1p1_is_match, h1p1_p0_to_conf, h1p1_p1_to_conf = compare_cores_to_configure(host1, function, p0=0,
                                                                                             p1=2)
                if h1p1_is_match:
                    p1_host = host1
                    p0_host = host0
                    hosts_to_config[p0_host] = {'p0': h0p0_p0_to_conf, 'p1': h0p0_p1_to_conf}
                    # hosts_to_config[p1_host] = {'p0': h1p1_p0_to_conf, 'p1': h1p1_p1_to_conf}
                else:
                    # no match for (2,0) for both hosts, and host1 don't match (0,2) either - configure host1 to (2,0)
                    p0_host = host1
                    hosts_to_config[p0_host] = {'p0': h1p0_p0_to_conf, 'p1': h1p0_p1_to_conf}
                    p1_host = host0
                    h0p1_is_match, h0p1_p0_to_conf, h0p1_p1_to_conf = compare_cores_to_configure(host0, function, p0=0,
                                                                                                 p1=2)
                    if not h0p1_is_match:
                        hosts_to_config[p1_host] = {'p0': h0p1_p0_to_conf, 'p1': h0p1_p1_to_conf}

        assert p1_host and p0_host, "Check automation code. Init host should have been assigned"

        for host_, configs in hosts_to_config.items():
            config_host_class(host_, _mod_host, **configs)

        is_match_p0 = compare_cores_to_configure(p0_host, function, p0=2, p1=0)[0]
        is_match_p1 = compare_cores_to_configure(p1_host, function, p0=0, p1=2)[0]
        assert is_match_p0, "{} does not match vswitch core (2, 0)".format(p0_host)
        assert is_match_p1, "{} does not match vswitch core (0, 2)".format(p1_host)

        final_hosts_configured = [p1_host, p0_host]
        return final_hosts_configured, storage_backing, ht_enabled

    @mark.parametrize(('vswitch_numa_affinity', 'numa_0', 'numa_nodes', 'expt_err'), [
        ('strict', 0, None, "NumaErr.NUMA_AFFINITY_MISMATCH"),  # This error message has inconsistent formatting
        ('prefer', 0, None, None),
        ('strict', None, 1, None),
        ('prefer', None, None, None),
        ('strict', None, 2, 'NumaErr.UNINITIALIZED')  # This error message is confusing
    ])
    def test_vswitch_numa_affinity_boot_vm(self, hosts_configured, vswitch_numa_affinity, numa_0, numa_nodes, expt_err):
        """

        Args:
            hosts_configured (tuple): fixture to configure two hosts
            vswitch_numa_affinity (str):
            numa_0 (int):
            numa_nodes (int):
            expt_err (str):

        Setups:
            - Add admin role to primary tenant
            - Create cgcsauto aggregate
            - Delete all vms on the system
            - Configure a host with vswitch = 0, 2, and antother with vswitch = 2, 0 and add them to cgcsauto zone

        Test Steps:
            - Create flavor with 2 dedicated vcpus, and specified vswitch numa affinity, numa_0 and numa_nodes
            - Boot vm with above flavor
                - Check vm is booted successfully on expected numa node and host
                - or failed with proper error message in nova show

        """
        hosts_configured, storage_backing, ht_enabled = hosts_configured
        expt_host = hosts_configured[0]
        expt_numa = 1 if numa_0 is None else numa_0

        flv_id = _create_flavor(2, storage_backing, vswitch_numa_affinity, numa_0, numa_nodes)

        LOG.tc_step("Boot vm from volume using above flavor")
        code, vm_id, err, vol = vm_helper.boot_vm('numa_affinity', flavor=flv_id, cleanup='function',
                                                  avail_zone='cgcsauto', vm_host=expt_host, fail_ok=True)
        # ResourceCleanup.add('vm', vm_id, del_vm_vols=False)
        # ResourceCleanup.add('volume', vol)

        if expt_err:
            LOG.tc_step("Check boot vm failed due to conflict in vswtich node affinity and numa nodes requirements")
            assert 1 == code, "Boot vm is not rejected with conflicting requirements"
            actual_err = nova_helper.get_vm_nova_show_value(vm_id, 'fault')
            if 'NUMA_AFFINITY_MISMATCH' in expt_err:
                expt_err = eval(expt_err).format(0)
            else:
                expt_err = eval(expt_err)
            assert expt_err in actual_err, "Expected fault message is not found from nova show"
        else:
            LOG.tc_step("Check vm is booted successfully on numa node {}".format(expt_numa))
            assert 0 == code, "Boot vm is not successful. Details: {}".format(err)
            vm_host, vm_numa = vm_helper.get_vm_host_and_numa_nodes(vm_id)
            assert expt_host == vm_host, "VM {} is not booted on expected host".format(vm_id)
            assert expt_numa == vm_numa[0], "VM {} is booted on numa{} instead of numa{}".format(vm_id, vm_numa[0],
                                                                                                 expt_numa)

    @fixture(scope='class')
    def cal_vm_cores_two_hosts(self, hosts_configured):
        hosts_configured, storage_backing, ht_enabled = hosts_configured

        LOG.fixture_step("(class) Calculate the vcpus for flavor when two hosts available to schedule vms")
        total_vswitch_vm_cores = 0
        hosts_vswitch_vm_cores = []
        min_vm_cores = 200
        final_host = None
        hosts_vswitch_proc = {
            hosts_configured[0]: 1,
            hosts_configured[1]: 0,
        }
        for host in hosts_configured:
            vms_cores_dict = host_helper.get_host_cpu_cores_for_function(host, function='VMs')
            vswitch_vm_cores = len(vms_cores_dict[hosts_vswitch_proc[host]])
            if system_helper.is_hyperthreading_enabled(host):
                vswitch_vm_cores *= 2
            hosts_vswitch_vm_cores.append(vswitch_vm_cores)
            total_vswitch_vm_cores += vswitch_vm_cores

            if vswitch_vm_cores < min_vm_cores:
                min_vm_cores = vswitch_vm_cores
                final_host = host

        list(hosts_configured).remove(final_host)
        other_host = hosts_configured[0]
        flavor_vcpu_num = int(total_vswitch_vm_cores / 7) + 1

        vms_num = 0
        for vm_cores in hosts_vswitch_vm_cores:
            vms_num += int(vm_cores / flavor_vcpu_num)

        return final_host, other_host, hosts_vswitch_proc, flavor_vcpu_num, vms_num, storage_backing

    @mark.parametrize('vswitch_numa_affinity', [
        'strict',
        'prefer',
        None,
    ])
    def test_vswitch_numa_affinity_sched_vms_two_hosts_avail(self, cal_vm_cores_two_hosts, vswitch_numa_affinity):
        """

        Args:
            cal_vm_cores_two_hosts (tuple): fixture to calculate flavor vcpu number
            vswitch_numa_affinity (str):

        Setups:
            - Add admin role to primary tenant
            - Create cgcsauto aggregate
            - Delete all vms on the system
            - Select a host with vswitch = 0, 2, and antother with vswitch = 2, 0 and add them to cgcsauto zone
            - Select the host with less vm cores on vswitch node as target_host
            - Calculate favor vcpu number so that max 6 vms can be booted vswitch nodes

        Test Steps;
            - Create a flavor with calculated vcpu number and specified vswitch numa affinity
            - Boot vms with above flavor until vswitch nodes on both computes are full
            - Check above vms are booted on vswitch nodes of selected hosts
            - Attempt to boot one more vm
                - Check it failed if vswitch numa affinity = strict
                - Check it booted on non-vswitch node if vswitch numa affinity = prefer
            - Delete all vms on host_other
            - Cold migrate vms away from target_host and ensure they are moved to vswitch node of host_other
            - Live migrate vms from other host, and ensure they are moved to vswitch ndoe of target host
            - Reboot vms host and ensure vms are evacuated to host_other

        Teardown:
            - Delete created vms, flavors, volumes
            - Remove hosts from cgcsauto aggregate
            - Delete cgcsauto aggregate
            - Remove admin role from tenanat

        """
        final_host, other_host, hosts_vswitch_numa, flavor_vcpu_num, vms_num, storage_backing = cal_vm_cores_two_hosts
        expt_hosts = [final_host, other_host]

        flv_id = _create_flavor(flavor_vcpu_num, storage_backing, vswitch_numa_affinity)

        LOG.tc_step("Boot {} VMs and ensure they are booted on vswitch numa node".format(vms_num))
        final_host_vms = []
        total_cpus = {final_host: 0, other_host: 0}
        for i in range(vms_num):
            code, vm_id, err, vol = vm_helper.boot_vm('vswitch_numa', flavor=flv_id, cleanup='function',
                                                      avail_zone='cgcsauto', fail_ok=True)
            # ResourceCleanup.add('vm', vm_id, del_vm_vols=False)
            # ResourceCleanup.add('volume', vol)

            assert 0 == code, "VM is not booted successfully. Details: {}".format(err)
            vm_host, vm_numa = vm_helper.get_vm_host_and_numa_nodes(vm_id)
            vm_numa = vm_numa[0]
            assert vm_host in expt_hosts, "VM is not booted on cgcsauto hosts"

            expt_numa = hosts_vswitch_numa[vm_host]

            # CGTS-6389: vswitch engine availability is not considered in host selection for prefer
            if vswitch_numa_affinity != 'strict':
                if expt_numa != vm_numa:
                    LOG.warning("VM{} - {} is not booted on expected host. Applying workaround.".format(i, vm_id))
                    vm_helper.live_migrate_vm(vm_id)
                    vm_host, vm_numa = vm_helper.get_vm_host_and_numa_nodes(vm_id)
                    vm_numa = vm_numa[0]
                    expt_numa = hosts_vswitch_numa[vm_host]

            assert expt_numa == vm_numa, "VM {} is not booted on vSwitch node of {}".format(vm_id, vm_host)

            if vm_host == final_host:
                final_host_vms.append(vm_id)

            total_cpus[vm_host] += flavor_vcpu_num
            expt_total = total_cpus[vm_host]
            LOG.tc_step("Check total allocated vcpus is {} from nova-compute.log on {}".format(expt_total, other_host))
            with host_helper.ssh_to_host(vm_host) as host_ssh:
                host_helper.wait_for_total_allocated_vcpus_update_in_log(host_ssh, expt_cpus=expt_total, fail_ok=False)

        # Now vswitch nodes on both hosts are full. Attempt to boot another VM
        extra_str = 'rejected' if vswitch_numa_affinity == 'strict' else ' booted on non-vSwitch node - proc_0'
        LOG.tc_step("vSwitch nodes are full. Attempt to boot one more vm and ensure it's {}".format(extra_str))
        code, vm_id, err, vol = vm_helper.boot_vm('vswitch_numa', flavor=flv_id, cleanup='function',
                                                  avail_zone='cgcsauto', vm_host=final_host, fail_ok=True)
        # ResourceCleanup.add('vm', vm_id, del_vm_vols=False)
        # ResourceCleanup.add('volume', vol)

        if vswitch_numa_affinity == 'strict':
            assert 1 == code, "VM boot is not rejected even though vSwitch node is full. Details: {}".format(err)
        else:
            assert 0 == code, "VM is not booted successfully on another node. Details: {}".format(err)
            vm_host, vm_numa = vm_helper.get_vm_host_and_numa_nodes(vm_id)
            vm_numa = vm_numa[0]
            assert vm_host in expt_hosts, "VM is not booted on cgcsauto hosts"
            assert hosts_vswitch_numa[vm_host] != vm_numa, "VM is not booted on non-vSwitch node"

            if vm_host != final_host:
                vm_helper.live_migrate_vm(vm_id, final_host)

            # Add the vm to the first so we can verify a prefer vm that was on non-vSwitch node will be migrated to
            # vSwitch ndoe when sufficient vm cores available on other host
            final_host_vms.insert(0, vm_id)

        if vswitch_numa_affinity is not None:
            # Test vm actions for prefer and strict. None should be the same as prefer, so skip it for None.
            LOG.tc_step("Delete all vms on {}".format(other_host))
            vms_to_del = nova_helper.get_vms_on_hypervisor(other_host)
            vm_helper.delete_vms(vms_to_del)
            LOG.tc_step("Check total allocated vcpus is 0 from nova-compute.log on {}".format(other_host))
            with host_helper.ssh_to_host(other_host) as host_ssh:
                host_helper.wait_for_total_allocated_vcpus_update_in_log(host_ssh, expt_cpus=0, fail_ok=False)

            vswitch_vm_num = len(final_host_vms) if vswitch_numa_affinity == 'strict' else (len(final_host_vms) - 1)

            for action in ('cold_migrate', 'live_migrate'):
                LOG.tc_step("{} {} VMs and ensure they are migrated to vswitch node of other host".
                            format(action, vswitch_vm_num))
                for i in range(vswitch_vm_num):
                    vm_ = final_host_vms[i]
                    code, output = vm_helper.perform_action_on_vm(vm_, action=action, fail_ok=True)
                    assert 0 == code, "{}    vm{} unsuccessful. Details: {}".format(action, i, output)
                    vm_host, vm_numa = vm_helper.get_vm_host_and_numa_nodes(vm_)
                    vm_numa = vm_numa[0]
                    assert hosts_vswitch_numa[vm_host] == vm_numa, "VM{} is not {}d to vswitch node".format(i, action)

                if vswitch_numa_affinity != 'strict':
                    last_vm = final_host_vms[-1]
                    LOG.tc_step("{} last vm to other host and ensure it succeeded".format(action))
                    code, output = vm_helper.perform_action_on_vm(last_vm, action=action)
                    assert 0 == code, "{} vm unsuccessful. Details: {}".format(action, output)
                    vm_host, vm_numa = vm_helper.get_vm_host_and_numa_nodes(last_vm)
                    vm_numa = vm_numa[0]
                    if vm_host == other_host and vswitch_vm_num < vms_num / 2:
                        assert hosts_vswitch_numa[vm_host] == vm_numa, "Last VM is not {}d to vSwitch node of {}".\
                            format(action, vm_host)
                    else:
                        assert hosts_vswitch_numa[vm_host] != vm_numa, "Last VM is not {}d to non-vSwitch node of {}". \
                            format(action, vm_host)

            LOG.tc_step("Reboot {} and ensure vms are evacuated successfully".format(final_host))
            vm_helper.evacuate_vms(final_host, final_host_vms)

    @fixture(scope='class')
    def cal_vm_cores_one_host(self, hosts_configured):
        hosts_configured, storage_backing, ht_enabled = hosts_configured

        LOG.fixture_step("(class) Determine host to boot vms on and calculate the vcpus for flavor")

        initial_host, other_host = hosts_configured
        vms_cores_dict = host_helper.get_host_cpu_cores_for_function(initial_host, function='VMs')
        p1_vm_cores = len(vms_cores_dict[1])
        if system_helper.is_hyperthreading_enabled(initial_host):
            p1_vm_cores *= 2

        flavor_vcpu_num = int(p1_vm_cores / 4) + 1

        return initial_host, other_host, flavor_vcpu_num, storage_backing

    def test_vswitch_numa_affinity_sched_vms_one_host_avail(self, cal_vm_cores_one_host):
        """
        Test vswitch numa affinity strict when numa_0.0 = 1 which limits the vm host to only 1 host

        Args:
            cal_vm_cores_one_host (tuple): fixture to get host with vswitch node on proc1 and calculate flavor vcpu num

        Setups:
            - Add admin role to primary tenant
            - Create cgcsauto aggregate
            - Delete all vms on the system
            - Select a target host vswitch = 0, 2, and host_other vswitch = 2, 0 and add them to cgcsauto zone

        Test Steps;
            - Create a flavor with vswitch_numa_affinity=strict and vcpu_num = int(p1_vm_cores/4)+1 so that max 3
                vms can be booted on vswitch node
            - Boot vms with above flavor until vswitch node full
            - Check above vms are booted on expected host and numa node
            - Attempt to boot one more vm and ensure it failed
            - Attempt to live and cold migrate active vms, and ensure they are rejected
            - Reboot vm host and ensure vm stays on same host and return active after host is back up

        Teardown:
            - Delete created vms, flavors, volumes
            - Remove hosts from cgcsauto aggregate
            - Delete cgcsauto aggregate
            - Remove admin role from tenanat

        """
        expt_host, other_host, flavor_vcpu_num, storage_backing = cal_vm_cores_one_host

        flv_id = _create_flavor(flavor_vcpu_num, storage_backing, 'strict', 1)

        LOG.tc_step("Boot 3 VMs and ensure they are booted on vswitch numa node on {}".format(expt_host))
        vms = []
        for i in range(3):
            code, vm_id, err, vol = vm_helper.boot_vm('vswitch_numa_one_host', flavor=flv_id, cleanup='function',
                                                      avail_zone='cgcsauto', fail_ok=True)
            # ResourceCleanup.add('vm', vm_id, del_vm_vols=False)
            # ResourceCleanup.add('volume', vol)

            assert 0 == code, "VM is not booted successfully. Details: {}".format(err)
            vm_host, vm_numa = vm_helper.get_vm_host_and_numa_nodes(vm_id)
            vm_numa = vm_numa[0]
            assert expt_host == vm_host, "VM is booted on {} instead of {}".format(vm_host, expt_host)
            assert 1 == vm_numa, "VM is not booted on vSwitch node: proc_1"

            vms.append(vm_id)

        LOG.tc_step("Boot one more vm and ensure it's rejected")
        code, vm_id, err, vol = vm_helper.boot_vm('vswitch_numa', flavor=flv_id, cleanup='function',
                                                  avail_zone='cgcsauto', fail_ok=True)
        # ResourceCleanup.add('vm', vm_id, del_vm_vols=False)
        # ResourceCleanup.add('volume', vol)
        assert 1 == code, "VM boot is not rejected even though vSwitch node is full. Details: {}".format(err)

        LOG.tc_step("Attempt to live/cold migrate booted vms and ensure it's rejected")
        for vm_ in vms:
            for action in ('live_migrate', 'cold_migrate'):
                code, output = vm_helper.perform_action_on_vm(vm_, action=action, fail_ok=True)
                assert 2 == code, "{} is not rejected. Details: {}".format(action, output)

                vm_host, vm_numa = vm_helper.get_vm_host_and_numa_nodes(vm_)
                vm_numa = vm_numa[0]
                assert expt_host == vm_host
                assert 1 == vm_numa

        LOG.tc_step("Reboot vm host and ensure vms stayed on same host and become active after host comes back up")
        code, err_vms = vm_helper.evacuate_vms(expt_host, vms, wait_for_host_up=True, timeout=300, fail_ok=True)
        assert 2 == code, "Reboot host with vms are not as expected."
        assert sorted(err_vms) == sorted(vms), "Not all vms stayed on expected host"

    @fixture(scope='class')
    def get_target_host_and_flavors(self, hosts_configured, request):
        hosts, storage_backing, ht_enabled = hosts_configured
        other_host, target_host = hosts
        LOG.fixture_step("(class) Add {} to cgcsauto aggregate".format(target_host))
        nova_helper.add_hosts_to_aggregate('cgcsauto', target_host)

        def _add_other_host():
            LOG.fixture_step("(class) Add {} to cgcsauto aggregate".format(other_host))
            nova_helper.add_hosts_to_aggregate('cgcsauto', other_host)
        request.addfinalizer(_add_other_host)

        LOG.fixture_step("(class) Remove {} from cgcsauto aggregate".format(other_host))
        nova_helper.remove_hosts_from_aggregate('cgcsauto', other_host)

        LOG.fixture_step("(class) Check vswitch numa node on {} doesn't have the most vm cores.".format(target_host))
        vswitch_cores_dict = host_helper.get_host_cpu_cores_for_function(target_host, function='vSwitch')
        vswitch_vm_cores_num, nonvswitch_vm_cores_num = _get_vms_cores_nums(target_host, vswitch_cores_dict)
        assert nonvswitch_vm_cores_num > vswitch_vm_cores_num, "vSwitch numa node has the most vm cores."

        if ht_enabled:
            vswitch_vm_cores_num *= 2
            nonvswitch_vm_cores_num *= 2
        vswitch_proc = list(vswitch_cores_dict.keys())[0]

        LOG.fixture_step("(class) Create a origin flavor with 2 vcpus and boot a vm with this flavor.")
        pre_flavor = nova_helper.create_flavor(name='2_vcpus', vcpus=2)[1]
        ResourceCleanup.add('flavor', resource_id=pre_flavor, scope='class')
        nova_helper.set_flavor_extra_specs(pre_flavor, **{FlavorSpec.CPU_POLICY: 'dedicated'})

        LOG.fixture_step("(class) Create dest flavor with vcpu number larger than the available cores on current numa node")
        huge_flavor = nova_helper.create_flavor(name='many_vcpus', vcpus=vswitch_vm_cores_num + 1)[1]
        ResourceCleanup.add('flavor', huge_flavor, scope='class')
        nova_helper.set_flavor_extra_specs(huge_flavor, **{FlavorSpec.CPU_POLICY: 'dedicated'})

        return target_host, vswitch_proc, vswitch_vm_cores_num, nonvswitch_vm_cores_num, pre_flavor, huge_flavor

    @mark.parametrize(('vswitch_numa_affinity', 'resize_revert'), [
        mark.p2(('strict', 'confirm')),
        mark.p2(('prefer', 'confirm')),
        mark.p2(('prefer', 'revert'))
    ])
    def test_vswitch_affinity_resize_insufficient_cores_on_vswitch_node(self, get_target_host_and_flavors,
                                                                        vswitch_numa_affinity, resize_revert):
        """
        Test vswitch numa affinity when attempt to resize with insufficient cores on vswitch node
        Args:
            get_target_host_and_flavors (tuple): fixture to get target_host and flavor with large vcpu number
            vswitch_numa_affinity (str):
            resize_revert (str):

        Setups:
            - Add admin role to primary tenant
            - Create cgcsauto aggregate
            - Delete all vms on the system
            - Select target host with vswitch = 2, 0 and add it to cgcsauto aggregate
            - Create a flavor with 2 vcpus and vswitch affinity
            - Create another flavor with many vcpus = vswitch ndoe vm cores - 1

        Test Steps;
            - Boot a vm with dedicated 2 vcpu flavor in cgcsauto zone
            - Check vm is booted on cgcsauto host
            - Set vswitch numa affinity as specified on huge vcpu flavor
            - Attempt to resize to huge flavor
            - Check resize only succeeds if vswitch numa affinity = prefer

        Teardown:
            - Delete created vms, flavors, volumes
            - Remove hosts from cgcsauto aggregate
            - Delete cgcsauto aggregate
            - Remove admin role from tenanat

        """
        resize_revert = True if resize_revert == 'confirm' else False
        target_host, vswitch_proc, vswitch_vm_cores_num, nonvswitch_vm_cores_num, pre_flavor, huge_flavor = \
            get_target_host_and_flavors

        LOG.tc_step("Boot a vm with origin flavor with 2 vcpus")
        vm_id = vm_helper.boot_vm(flavor=pre_flavor, avail_zone='cgcsauto', cleanup='function')[1]
        # ResourceCleanup.add('vm', resource_id=vm_id)

        LOG.tc_step("Check vm is booted on same numa node with vSwitch of {} via vm-topology".format(target_host))
        pre_vm_host, pre_numa_nodes = vm_helper.get_vm_host_and_numa_nodes(vm_id)
        assert target_host == pre_vm_host, "VM host is not host under test"
        assert vswitch_proc == pre_numa_nodes[0], "VM {} is not booted on vswitch numa node {}".\
            format(vm_id, vswitch_proc)

        nova_helper.set_flavor_extra_specs(huge_flavor, **{FlavorSpec.VSWITCH_NUMA_AFFINITY: vswitch_numa_affinity})
        LOG.tc_step("Resize {}vm to above huge flavor with vswitch numa affinity {}".
                    format('and revert ' if resize_revert else '', vswitch_numa_affinity))

        code, output = vm_helper.resize_vm(vm_id, flavor_id=huge_flavor, revert=resize_revert, fail_ok=True)

        LOG.tc_step("Check vm is on same host")
        post_vm_host, post_numa_nodes = vm_helper.get_vm_host_and_numa_nodes(vm_id)
        assert target_host == post_vm_host, "VM is no longer on same host"

        if vswitch_numa_affinity == 'strict':
            LOG.tc_step("Check vm resize request is rejected with AVS strict due to insufficient cores on vSwitch node")
            assert 1 == code, "Resize with strict AVS policy is not rejected. Details: {}".format(output)
            assert vswitch_proc == post_numa_nodes[0], "VM is moved to non-vSwitch numa node even if resize is rejected"
        else:
            LOG.tc_step("Check resize succeeded with AVS perfer")
            assert 0 == code, "Resize with prefer AVS policy is not successful. Details: {}".format(output)
            if resize_revert:
                LOG.tc_step("Resize reverted - check vm remains on vswitch numa node on {}".format(target_host))
                assert vswitch_proc == post_numa_nodes[0], "VM is moved to non-vSwitch numa node after revert"
            else:
                LOG.tc_step("Resized to huge flavor - check vm is resized to non-vswitch numa node on same host")
                assert vswitch_proc != post_numa_nodes[0], "VM did not move to non-vSwitch numa node"


class TestSpanNumaNodes:
    @fixture(scope='class')
    def span_numa_hosts(self, get_hosts, config_host_class):
        host0, host1, storage_backing, ht_enabled = get_hosts

        function = 'vSwitch'
        LOG.fixture_step("(class) Configure hosts to have 0 vSwitch cores on p0 and 2 vSwitch cores on p1: {}")

        def _mod_host(host_, p0, p1):
            kwargs = {}
            if p0 is not None:
                kwargs['p0'] = p0
            if p1 is not None:
                kwargs['p1'] = p1

            host_helper.modify_host_cpu(host_, function, **kwargs)

        is_match, p0_to_conf, p1_to_conf = compare_cores_to_configure(host0, function, p0=2, p1=0)
        if is_match:
            host_span = host1
            host_other = host0
        else:
            host_span = host0
            host_other = host1
            is_match_other, p0_to_conf_other, p1_to_conf_other = compare_cores_to_configure(host1, function, p0=2, p1=0)
            if not is_match_other:
                LOG.fixture_step("Config {} vswitch cores to 2,0".format(host_other))
                config_host_class(host_span, _mod_host, **{'p0': p0_to_conf_other, 'p1': p1_to_conf_other})

        is_match_span, p0_to_conf_span, p1_to_conf_span = compare_cores_to_configure(host_span, function, p0=2, p1=2)
        if not is_match_span:
            LOG.fixture_step("Config {} vswitch cores to 2,2".format(host_span))
            config_host_class(host_span, _mod_host, **{'p0': p0_to_conf_span, 'p1': p1_to_conf_span})

        ht_enabled = system_helper.is_hyperthreading_enabled(host_span)
        return host_span, host_other, storage_backing, ht_enabled

    @staticmethod
    def create_flavor_span_numa(vcpus, vswitch_affinity, storage_backing, numa0, numa0_cpus, numa0_mem, numa1, numa1_cpus, numa1_mem):

        LOG.tc_step("Create a 1024ram flavor with specified vcpus")
        name = 'vswitch_affinity_{}_1G_{}cpu'.format(vswitch_affinity, vcpus)
        flv_id = nova_helper.create_flavor(name=name, vcpus=vcpus, ram=1024, storage_backing=storage_backing,
                                           check_storage_backing=False)[1]
        ResourceCleanup.add('flavor', flv_id)

        specs = {FlavorSpec.CPU_POLICY: 'dedicated', FlavorSpec.NUMA_NODES: 2,
                 FlavorSpec.VSWITCH_NUMA_AFFINITY: vswitch_affinity}
        tmp_dict = {FlavorSpec.NUMA_0: numa0,
                    FlavorSpec.NUMA0_CPUS: numa0_cpus,
                    FlavorSpec.NUMA0_MEM: numa0_mem,
                    FlavorSpec.NUMA_1: numa1,
                    FlavorSpec.NUMA1_CPUS: numa1_cpus,
                    FlavorSpec.NUMA1_MEM: numa1_mem}

        for key, val in tmp_dict.items():
            if val is not None:
                specs[key] = val

        LOG.tc_step("Add following extra spec to flavor {}: {}".format(flv_id, specs))
        nova_helper.set_flavor_extra_specs(flv_id, **specs)

        return flv_id

    @fixture(scope='class')
    def base_flavor_span_numa(self, span_numa_hosts):
        host_span, host_other, storage_backing, ht_enabled = span_numa_hosts
        LOG.fixture_step("(class) Create a 1024ram flavor with specified vcpus")
        flv_id = nova_helper.create_flavor(name='vswitch_affinity_strict_2vcpu', vcpus=4, ram=1024,
                                           storage_backing=storage_backing, check_storage_backing=False)[1]
        ResourceCleanup.add('flavor', flv_id, scope='class')

        specs = {FlavorSpec.CPU_POLICY: 'dedicated', FlavorSpec.NUMA_NODES: 2,
                 FlavorSpec.VSWITCH_NUMA_AFFINITY: 'strict',
                 FlavorSpec.NUMA_0: 1,
                 FlavorSpec.NUMA_1: 0
                 }

        LOG.fixture_step("(class) Add following extra spec to flavor {}: {}".format(flv_id, specs))
        nova_helper.set_flavor_extra_specs(flv_id, **specs)

        return flv_id

    @staticmethod
    def expt_vcpu_num_on_numa(vcpus, numa0_cpus, numa1_cpus):
        tmp_dict = {
            0: numa0_cpus,
            1: numa1_cpus
        }
        default_num = int(vcpus / 2)
        vcpu_on_numa = {}
        for key, val in tmp_dict.items():
            if val is None:
                num = default_num
            else:
                num = len(str(val).split(','))
            vcpu_on_numa[key] = num

        return vcpu_on_numa

    @mark.parametrize(('vcpus', 'vswitch_affinity', 'numa0', 'numa0_cpus', 'numa0_mem', 'numa1', 'numa1_cpus', 'numa1_mem'),[
        (3, 'strict', 0, 0, 512, 1, '1,2', 512),
        (2, 'strict', None, 0, 512, None, 1, 512),
        (2, 'prefer', None, None, None, None, None, None),
        # (3, 'prefer', 0, None, None, 1, None, None, 'NumaErr.UNDEVISIBLE')
    ])
    def test_vm_actions_vswitch_span_numa_nodes(self, span_numa_hosts, vcpus, vswitch_affinity, numa0, numa0_cpus,
                                                numa0_mem, numa1, numa1_cpus, numa1_mem, base_flavor_span_numa):
        """
        Test nova actions on 2 numa nodes vm with vswitch numa affinity set

        Args:
            span_numa_hosts(tuple): fixture to config hosts
            vcpus (int):
            vswitch_affinity (str):
            numa0 (int):
            numa0_cpus (int|str):
            numa0_mem (int):
            numa1 (int):
            numa1_cpus (int|str):
            numa1_mem (int):
            base_flavor_span_numa (str): fixture returns 4 vcpu 2 numa nodes flavor to resize to

        Setups:
            - Add admin role to primary tenant
            - Create cgcsauto aggregate
            - Select two hypervisors with same storage backing and add them to cgcsauto aggregate
            - Delete all vms on the system
            - Config host so that 1 host_other vswitch = 2, 0 and host_span vswitch = 2, 2

        Test Steps;
            - Create flavor with 2 numa nodes and given test func parameters
            - Boot vm using above flavor in cgcsauto zone
            - Check vm is booted on host_span and span on both numa nodes
            - Check vm topology is as specified
            - Attempt to live and cold migrate vm and ensure it's rejected
            - Resize revert to 4vcpu and 2numa nodes flavor
            - Check vm stays on same host and topology stays the same
            - Resize confirm to 4vcpu and 2numa nodes flavor
            - Check vm stays on same host and topology updated

        Teardown:
            - Delete created vms, flavors, volumes
            - Remove hosts from cgcsauto aggregate
            - Delete cgcsauto aggregate
            - Remove admin role from tenanat

        """
        host_span, host_other, storage_backing, ht_enabled = span_numa_hosts

        flavor = self.create_flavor_span_numa(vcpus, vswitch_affinity, storage_backing, numa0, numa0_cpus, numa0_mem,
                                              numa1, numa1_cpus, numa1_mem)

        LOG.tc_step("Boot a vm with above flavor")
        code, vm_id, err, vol = vm_helper.boot_vm('span_numa_{}'.format(vswitch_affinity), cleanup='function',
                                                  flavor=flavor, fail_ok=True, avail_zone='cgcsauto')
        # ResourceCleanup.add('vm', vm_id, del_vm_vols=False)
        # ResourceCleanup.add('volume', vol)

        expt_numa0 = numa0 if numa0 is not None else 0
        expt_numa1 = numa1 if numa1 is not None else 1
        expt_numas = [expt_numa0, expt_numa1]

        LOG.tc_step("Check vm is booted successfully and span on both numa node")
        assert 0 == code, "Boot vm is not successful. Details: {}".format(err)
        vm_host, vm_numa = vm_helper.get_vm_host_and_numa_nodes(vm_id)
        assert host_span == vm_host, "VM {} is not booted on expected host".format(vm_id)
        assert expt_numas == vm_numa, "VM {} is booted on numa-{} instead of [0,1]".format(vm_id, vm_numa)

        LOG.tc_step("Check vm topology after vm boot")
        expt_vcpu_on_numa = self.expt_vcpu_num_on_numa(vcpus=vcpus, numa0_cpus=numa0_cpus, numa1_cpus=numa1_cpus)
        check_helper._check_vm_topology_via_vm_topology(vm_id, vcpus, 'dedicated', cpu_thr_pol=None, numa_num=2,
                                                        vm_host=vm_host, is_ht=ht_enabled,
                                                        vcpus_on_numa=expt_vcpu_on_numa)

        for action in ('live_migrate', 'cold_migrate'):
            code, output = vm_helper.perform_action_on_vm(vm_id, action=action, fail_ok=True)
            vm_host, vm_numa = vm_helper.get_vm_host_and_numa_nodes(vm_id)

            if vswitch_affinity == 'strict':
                assert 2 == code, "{} is not rejected. Details: {}".format(action, output)
                assert host_span == vm_host
            else:
                assert 0 == code, "VM is not {}d successfully even though vswitch affinity is prefer".format(action)

            assert expt_numas == vm_numa

        assert host_span == vm_host

        LOG.tc_step("Check vm topology did not change after migration reject")
        check_helper._check_vm_topology_via_vm_topology(vm_id, vcpus, 'dedicated', cpu_thr_pol=None, numa_num=2,
                                                        vm_host=vm_host, is_ht=ht_enabled,
                                                        vcpus_on_numa=expt_vcpu_on_numa)

        for revert in (True, False):
            extra_str = 'revert' if revert else 'confirm'
            expt_vcpu = vcpus if revert else 4
            expt_numa0_cpus = numa0_cpus if revert else None
            expt_numa1_cpus = numa1_cpus if revert else None
            expt_vm_numa = expt_numas if revert else [1, 0]

            LOG.tc_step("Resize {} to a 2-numa 4-vcpu flavor - ensure vm stays on same host and "
                        "span on two numa nodes".format(extra_str))
            vm_helper.resize_vm(vm_id, flavor_id=base_flavor_span_numa, revert=revert)
            vm_host, vm_numa = vm_helper.get_vm_host_and_numa_nodes(vm_id)
            assert host_span == vm_host, "VM host changed after resize {}".format(extra_str)
            assert expt_vm_numa == vm_numa, "Unexpected VM numa nodes after resize {}".format(extra_str)

            LOG.tc_step("Check vm topology after resize {}".format(extra_str))
            post_vcpu_on_numa = self.expt_vcpu_num_on_numa(vcpus=expt_vcpu, numa0_cpus=expt_numa0_cpus,
                                                           numa1_cpus=expt_numa1_cpus)
            check_helper._check_vm_topology_via_vm_topology(vm_id, expt_vcpu, 'dedicated', cpu_thr_pol=None, numa_num=2,
                                                            vm_host=vm_host, is_ht=ht_enabled,
                                                            vcpus_on_numa=post_vcpu_on_numa)
