from pytest import mark, fixture, skip

from utils.tis_log import LOG
from consts.cli_errs import CpuAssignment   # Do not remove this. Used in eval()
from consts.cgcs import FlavorSpec
from keywords import host_helper, system_helper, vm_helper, nova_helper
from testfixtures.resource_mgmt import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


@mark.tryfirst
@fixture(scope='module', autouse=True)
def host_to_config(request):
    LOG.info("Looking for a host to reconfigure.")
    nova_hosts = host_helper.get_nova_hosts()
    if len(nova_hosts) < 2:
        skip("Less than 2 nova hosts in the system, no host to lock and reconfigure.")

    is_small_system = system_helper.is_small_footprint()
    if is_small_system:
        host = system_helper.get_standby_controller_name()
    else:
        host = host_helper.get_nova_host_with_min_or_max_vms(rtn_max=False)

    if not host:
        skip("No nova host available to reconfigure in the system.")

    vswitch_proc_core_dict = host_helper.get_host_cpu_cores_for_function(host, function='vSwitch', core_type='log_core')
    pform_proc_core_dict = host_helper.get_host_cpu_cores_for_function(host, function='platform', core_type='log_core')

    vswitch_original_num_p0 = len(vswitch_proc_core_dict[0]) if 0 in vswitch_proc_core_dict.keys() else 0
    vswitch_original_num_p1 = len(vswitch_proc_core_dict[1]) if 1 in vswitch_proc_core_dict.keys() else 0
    platform_ogigin_num_p0 = len(pform_proc_core_dict[0])
    platform_original_num_p1 = len(pform_proc_core_dict[1]) if 1 in pform_proc_core_dict.keys() else 0

    def revert():
        post_vswitch_dict = host_helper.get_host_cpu_cores_for_function(host, function='vSwitch', core_type='log_core')
        post_pform_dict = host_helper.get_host_cpu_cores_for_function(host, function='platform', core_type='log_core')

        if vswitch_proc_core_dict != post_vswitch_dict or pform_proc_core_dict != post_pform_dict:
            host_helper.lock_host(host)
            host_helper.modify_host_cpu(host, 'vswitch', p0=vswitch_original_num_p0, p1=vswitch_original_num_p1)
            host_helper.modify_host_cpu(host, 'platform', p0=platform_ogigin_num_p0, p1=platform_original_num_p1)
            host_helper.unlock_host(host, check_hypervisor_up=True)
    request.addfinalizer(revert)

    ht_enabled = system_helper.is_hyperthreading_enabled(host)
    LOG.info("{} is selected. Hyper-threading is {}enabled".format(host, "not " if ht_enabled else ""))
    return host, ht_enabled, is_small_system


class TestVSwitchCPUReconfig:

    @mark.parametrize(('platform', 'vswitch', 'ht_required', 'cpe_required'), [
        # (None, None, None, None),           # Test without reconfig
        ((1, 0), (1, 1), None, False),      # Standard lab only
        ((2, 0), (1, 1), None, True),       # CPE only
        ((1, 2), (3, 2), None, None),
        ((1, 2), (2, 2), None, None),
        ((1, 0), (1, 0), False, False),     # Standard lab only
        ((2, 0), (1, 0), False, True),      # CPE only
        ((2, 0), (2, 0), None, True),       # CPE only
        ((1, 0), (2, 0), None, False),      # Standard lab only
    ])
    def test_vswitch_cpu_reconfig(self, host_to_config, platform, vswitch, ht_required, cpe_required):
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
        host, ht_enabled, is_cpe = host_to_config
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

            host_helper.lock_host(host)
            if platform is not None:
                host_helper.modify_host_cpu(host, 'platform', **platform_args)
            if vswitch is not None:
                host_helper.modify_host_cpu(host, 'vswitch', **vswitch_args)
            host_helper.unlock_host(host, check_hypervisor_up=True)

        LOG.tc_step("Check ports and vswitch cores mapping are correct.")
        with host_helper.ssh_to_host(host) as host_ssh:
            expt_vswitch_map = host_helper.get_expected_vswitch_port_engine_map(host_ssh)
            actual_vswitch_map = host_helper.get_vswitch_port_engine_map(host_ssh)
            assert expt_vswitch_map == actual_vswitch_map

        LOG.tc_step("Check {} is still a valid nova host.".format(host))
        host_helper.wait_for_hypervisors_up(host)
        host_helper.wait_for_hosts_in_nova_compute(host, timeout=60, fail_ok=False)

        LOG.tc_step("Check vm can be launched on or live migrated to {}.".format(host))
        vm_id = vm_helper.boot_vm()[1]
        ResourceCleanup.add('vm', vm_id)

        if not nova_helper.get_vm_host(vm_id) == host:
            vm_helper.live_migrate_vm(vm_id, host)


    @mark.parametrize(('platform', 'vswitch', 'ht_required', 'cpe_required', 'expt_err'), [
        mark.p1(((1, 1), (5, 5), False, None, "CpuAssignment.VSWITCH_TOO_MANY_CORES")),
        ((7, 9), (2, 2), None, None, "CpuAssignment.TOTAL_TOO_MANY_CORES"),   # Assume total<=10 cores/per proc & thread
        mark.p1((('cores-2', 'cores-2'), (2, 2), None, None, "CpuAssignment.NO_VM_CORE")),
        ((1, 1), (9, 8), None, None, "CpuAssignment.VSWITCH_TOO_MANY_CORES"),   # Assume total <= 10 cores/per proc & thread
        ((5, 5), (5, 4), None, None, "CpuAssignment.VSWITCH_TOO_MANY_CORES"),
        mark.p1(((5, 5), (6, 5), None, None, "CpuAssignment.TOTAL_TOO_MANY_CORES")),  # Assume total<=10core/proc&thread
        ((1, 1), (8, 10), None, None, "CpuAssignment.TOTAL_TOO_MANY_CORES"),  # Assume total <= 10 cores/per proc&thread
        mark.p3(((2, 0), (0, 0), None, None, "CpuAssignment.VSWITCH_INSUFFICIENT_CORES")),
    ])
    def test_vswitch_cpu_reconfig_negative(host_to_config, platform, vswitch, ht_required, cpe_required, expt_err):
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
        host, ht_enabled, is_cpe = host_to_config
        if ht_required is not None and ht_required is not ht_enabled:
            skip("Hyper-threading for {} is not {}".format(host, ht_required))

        if cpe_required is not None and (cpe_required is not is_cpe):
            skip("Requires {} system.".format("non-CPE" if is_cpe else "CPE"))

        if platform[0] == 'cores-2':
            p0, p1 = host_helper.get_logcores_counts(host, proc_ids=(0, 1))
            platform = int(p0) - 2, int(p1) - 2

        platform_args = {}
        for i in range(len(platform)):
            if i is not None:
                platform_args['p' + str(i)] = platform[i]

        vswitch_args = {}
        for j in range(len(vswitch)):
            if j is not None:
                vswitch_args['p' + str(j)] = vswitch[j]

        LOG.tc_step("Lock {}".format(host))
        host_helper.lock_host(host)

        LOG.tc_step("Attempt to reconfigure host cpus. Platform: {}, vSwitch: {}".format(platform, vswitch))
        # host_helper.modify_host_cpu(host, 'vswitch', **{'p0': 1, 'p1': 0})
        host_helper.modify_host_cpu(host, 'platform', **platform_args)
        code, output = host_helper.modify_host_cpu(host, 'vswitch', fail_ok=True, **vswitch_args)

        LOG.tc_step("Verify modify host cpu vSwitch core request is rejected with expected error message.")
        assert 1 == code, "Modify host cpu request is not rejected."

        if "TOTAL_TOO_MANY_CORES" in expt_err:
            proc_id = 0 if platform[0] + vswitch[0] > 10 else 1
            expt_err = eval(expt_err).format(proc_id)
        elif "VSWITCH_INSUFFICIENT_CORES" in expt_err:
            min_core_num = 2 if is_cpe else 1
            expt_err = eval(expt_err).format(min_core_num)
        else:
            expt_err = eval(expt_err)

        assert expt_err in output, "Expected error string is not in output"


@mark.slow
class TestVMSchedulingLockHosts:

    @fixture(scope='class', autouse=True)
    def lock_hosts(self, host_to_config):
        host_to_set = host_to_config[0]
        vm_helper.delete_vms(fail_ok=True, delete_volumes=False)
        nova_hosts = host_helper.get_nova_hosts()
        nova_hosts.remove(host_to_set)
        HostsToRecover.add(nova_hosts, scope='class')
        for host in nova_hosts:
            host_helper.lock_host(host)

    @staticmethod
    def __get_vms_cores_nums(host, vswitch_cores_dict):
        """

        Args:
            host (str): vm hostname

        Returns (tuple): max vms cores number across all cores, vms cores number on vSwitch cores

        """
        vms_cores_dict = host_helper.get_host_cpu_cores_for_function(host, function='VMs')

        vms_cores_nums = []
        for value in vms_cores_dict.values():
            vms_cores_nums.append(len(value))

        max_num = max(vms_cores_nums)
        vswitch_proc = list(vswitch_cores_dict.keys())[0]
        return max_num, len(vms_cores_dict[vswitch_proc])

    @mark.parametrize('resize_revert', [
        mark.p1(False),
        mark.p1(True)
    ])
    def test_resize_vm_vswitch_node_insufficient(self, host_to_config, resize_revert):
        """
        Test vm moves to non-vSwitch Numa node when resize to a flavor with more vcpus than current numa node

        Args:
            host_to_config:

        Setups:
            - Find a nova host with minimum number of vms (or standby controller if CPE) for testing    (module)
            - Record the cpu configs for vswitch and platform   (module)
            - Delete all the vms on the system      (class)
            - Lock all the nova hosts except the one under test     (class)

        Test Steps
            - Check vswitch numa node on host doesn't have the most vm cores. Modify host cpu otherwise.
            - Create a basic flavor with 2 vcpus and boot a vm with this flavor
            - Check vm is booted on vswitch numa node via vm-topology
            - Resize vm to a flavor with vcpus numbers more than current numa node
            - Confirm/Revert resize and verify vm is on different/same numa node on same host

        Teardown:
            - Delete created vm and flavors
            - Unlock hosts      (class)
            - Revert host platform and vswitch cpu configs      (module)

        """
        host, ht_enabled, is_cpe = host_to_config

        LOG.tc_step("Check vswitch numa node on {} doesn't have the most vm cores.".format(host))
        vswitch_cores_dict = host_helper.get_host_cpu_cores_for_function(host, function='vSwitch')
        max_vm_cores_num, vswitch_vm_cores_num = self.__get_vms_cores_nums(host, vswitch_cores_dict)

        if len(vswitch_cores_dict) > 1 or vswitch_vm_cores_num == max_vm_cores_num:
            LOG.tc_step("Modify host vSwitch cores to: 'p0': 2, 'p1': 0")
            host_helper.lock_host(host)
            host_helper.modify_host_cpu(host, 'vSwitch', **{'p0': 2, 'p1': 0})
            host_helper.unlock_host(host, check_hypervisor_up=True)
            host_helper.wait_for_hypervisors_up(host)
            host_helper.wait_for_hosts_in_nova_compute(host)
            vswitch_cores_dict = host_helper.get_host_cpu_cores_for_function(host, function='vSwitch')
            max_vm_cores_num, vswitch_vm_cores_num = self.__get_vms_cores_nums(host, vswitch_cores_dict)

        assert max_vm_cores_num > vswitch_vm_cores_num, "vSwitch numa node has the most vm cores."

        if ht_enabled:
            vswitch_vm_cores_num *= 2

        LOG.tc_step("Create a basic flavor with 2 vcpus and boot a vm with this flavor.")
        pre_flavor = nova_helper.create_flavor(name='2_vcpus', vcpus=2)[1]
        ResourceCleanup.add('flavor', resource_id=pre_flavor)
        nova_helper.set_flavor_extra_specs(pre_flavor, **{FlavorSpec.CPU_POLICY: 'dedicated'})
        vm_id = vm_helper.boot_vm(flavor=pre_flavor)[1]
        ResourceCleanup.add('vm', resource_id=vm_id)

        vswitch_proc = list(vswitch_cores_dict.keys())[0]
        LOG.tc_step("Check vm is booted on same numa node with vSwitch of {} via vm-topology".format(host))
        pre_vm_host, pre_numa_nodes = vm_helper.get_vm_host_and_numa_nodes(vm_id)
        assert host == pre_vm_host, "VM host is not host under test"
        assert vswitch_proc == pre_numa_nodes[0], "VM {} is not booted on vswitch numa node {}".\
            format(vm_id, vswitch_proc)

        LOG.tc_step("Resize {}vm to a flavor with vcpu number more than the available cores on current numa node".
                    format('and revert ' if resize_revert else ''))
        huge_flavor = nova_helper.create_flavor(name='many_vcpus', vcpus=vswitch_vm_cores_num + 1)[1]
        nova_helper.set_flavor_extra_specs(huge_flavor, **{FlavorSpec.CPU_POLICY: 'dedicated'})
        vm_helper.resize_vm(vm_id, flavor_id=huge_flavor, revert=resize_revert)

        LOG.tc_step("Check vm is on same host")
        post_vm_host, post_numa_nodes = vm_helper.get_vm_host_and_numa_nodes(vm_id)
        assert host == post_vm_host, "VM is no longer on same host"

        if resize_revert:
            LOG.tc_step("Check vm remains on same numa node on {}".format(host))
            assert vswitch_proc == post_numa_nodes[0]
        else:
            LOG.tc_step("Check vm is resized to use the other numa node on same host")
            assert vswitch_proc != post_numa_nodes[0], "VM did not move to other numa node"

    @mark.parametrize('vswitch', [
        mark.p3((0, 2)),
        mark.p1((2, 0)),
    ])
    def test_boot_vm_vswitch_node_full(self, host_to_config, vswitch):
        """
        Test vms are first scheduled on vSwitch numa node until full, then will be scheduled on different numa node
        Args:
            host_to_config:
            vswitch:

        Setups:
            - Find a nova host with minimum number of vms (or standby controller if CPE) for testing    (module)
            - Record the cpu configs for vswitch and platform   (module)
            - Delete all the vms on the system      (class)
            - Lock all the nova hosts except the one under test     (class)

        Test Steps
            - Modify vSwitch cpus on host to specified values
            - Create a flavor with vcpus set to (vSwitch node VMs cores / 3) +1
            - Boot a VM with sufficient cores on vSwitch numa node
            - Verify VM is booted on vSwitch numa node
            - Repeat above two steps
            - Boot one more VM (insufficient cores on vSwitch numa node)
            - Verify VM is booted on different numa node that doesn't have vSwitch

        Teardown:
            - Delete created vm and flavors
            - Unlock hosts      (class)
            - Revert host platform and vswitch cpu configs      (module)

        """
        host, ht_enabled, is_cpe = host_to_config
        LOG.tc_step("Modify vSwitch CPUs on {} to: {}".format(vswitch, host))

        vswitch_args = {}
        for j in range(len(vswitch)):
            if j is not None:
                vswitch_args['p' + str(j)] = vswitch[j]

        host_helper.lock_host(host),
        host_helper.modify_host_cpu(host, 'vswitch', **vswitch_args)
        host_helper.unlock_host(host, check_hypervisor_up=True)
        host_helper.wait_for_hypervisors_up(host)
        host_helper.wait_for_hosts_in_nova_compute(host)

        LOG.tc_step("Create a flavor with vcpus set to (vSwitch node VMs cores / 3) +1")
        proc_id = 1 if vswitch[0] == 0 else 0
        vms_cores_dict = host_helper.get_host_cpu_cores_for_function(host, function='VMs')
        vms_cores_num = len(vms_cores_dict[proc_id])
        if ht_enabled:
            vms_cores_num *= 2
        flavor_vcpu_num = int(vms_cores_num / 3) + 1

        flavor = nova_helper.create_flavor(name='vm-scheduling', vcpus=flavor_vcpu_num)[1]
        nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.CPU_POLICY: 'dedicated'})
        ResourceCleanup.add('flavor', flavor)

        for i in range(3-1):
            LOG.tc_step("Boot a VM with sufficient cores on numa node {}".format(proc_id))
            vm_id = vm_helper.boot_vm(flavor=flavor)[1]
            ResourceCleanup.add('vm', vm_id)

            LOG.tc_step("Check vm is booted on numa node {} of {} via vm-topology".format(proc_id, host))
            vm_host, numa_nodes = vm_helper.get_vm_host_and_numa_nodes(vm_id)
            assert host == vm_host, "VM host is not host under test"
            assert 1 == len(numa_nodes), "VM numa node number is not 1"
            assert proc_id == numa_nodes[0], "VM {} is not booted on vswitch numa node {}".format(vm_id, proc_id)

        LOG.tc_step("Boot one more VM with insufficient cores on numa node {}".format(proc_id))
        vm_id = vm_helper.boot_vm(flavor=flavor)[1]
        ResourceCleanup.add('vm', vm_id)

        other_proc = 0 if proc_id == 1 else 1
        LOG.tc_step("Check vm is booted on numa node {} of {} via vm-topology".format(other_proc, host))
        vm_host, numa_nodes = vm_helper.get_vm_host_and_numa_nodes(vm_id)
        assert host == vm_host, "VM host is not host under test"
        assert 1 == len(numa_nodes), "VM numa node number is not 1"
        assert other_proc == numa_nodes[0], "VM {} is not booted on other numa node {}".format(vm_id, other_proc)
