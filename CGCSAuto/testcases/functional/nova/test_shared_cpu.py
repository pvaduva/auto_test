import re

from pytest import fixture, mark, skip

from consts.cgcs import FlavorSpec
from consts.cli_errs import SharedCPUErr, ResizeVMErr
from keywords import nova_helper, vm_helper, host_helper, keystone_helper, check_helper, system_helper
from testfixtures.fixture_resources import ResourceCleanup, GuestLogs
from utils import cli, table_parser
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG


@fixture(scope='module')
def target_hosts():
    storage_backing, hosts = nova_helper.get_storage_backing_with_max_hosts()
    return hosts


@fixture()
def origin_total_vcpus(target_hosts):
    return host_helper.get_vcpus_for_computes(hosts=target_hosts, rtn_val='vcpus_used')


def get_failed_live_migrate_action_id(vm_id):
    action_table = table_parser.table(cli.nova('instance-action-list {}'.format(vm_id)))
    req_id = table_parser.get_values(action_table, 'Request_ID', **{'Action': 'live-migration', 'Message': 'Error'})
    assert req_id, "request id for failed live migration not found"
    return req_id[0]


def check_shared_vcpu(vm, numa_node0, numa_nodes, vcpus, prev_total_vcpus, shared_vcpu=None,
                      expt_increase=None, min_vcpus=None):

    host = nova_helper.get_vm_host(vm_id=vm)
    if shared_vcpu is not None:
        host_shared_vcpu_dict = host_helper.get_host_cpu_cores_for_function(host, func='Shared', thread=None)
        LOG.info("dict: {}".format(host_shared_vcpu_dict))
        if numa_nodes is None:
            numa_nodes = 1

        if numa_nodes == 1:
            host_shared_vcpu = host_shared_vcpu_dict[numa_node0]
        else:
            host_shared_vcpu = host_shared_vcpu_dict[0] + host_shared_vcpu_dict[1]
        vm_shared_pcpu = vm_helper.get_instance_topology(vm)[0]['shared_pcpu'][0]
        assert vm_shared_pcpu in host_shared_vcpu

    if min_vcpus is None:
        min_vcpus = vcpus

    check_helper.check_topology_of_vm(vm, vcpus, prev_total_cpus=prev_total_vcpus[host], shared_vcpu=shared_vcpu,
                                      cpu_pol='dedicated', expt_increase=expt_increase,
                                      numa_num=numa_nodes, min_vcpus=min_vcpus)


def create_shared_flavor(vcpus=2, storage_backing='local_image', cpu_policy='dedicated',
                         numa_nodes=None, node0=None, node1=None, shared_vcpu=None):
    flavor_id = nova_helper.create_flavor(name='shared_core', vcpus=vcpus, storage_backing=storage_backing)[1]
    ResourceCleanup.add('flavor', flavor_id, scope='function')

    LOG.tc_step("Add specific cpu_policy, number_of_numa_nodes, numa_node0, and shared_vcpu to flavor extra specs")
    extra_specs = {FlavorSpec.CPU_POLICY: cpu_policy}
    if numa_nodes is not None:
        extra_specs[FlavorSpec.NUMA_NODES] = numa_nodes
    if node0 is not None:
        extra_specs[FlavorSpec.NUMA_0] = node0
    if node1 is not None:
        extra_specs[FlavorSpec.NUMA_1] = node1
    if shared_vcpu is not None:
        extra_specs[FlavorSpec.SHARED_VCPU] = shared_vcpu

    nova_helper.set_flavor_extra_specs(flavor_id, **extra_specs)
    return flavor_id


@mark.p3
@mark.parametrize('vcpu_id', [
    0,
    2,
    63
])
def test_set_shared_vcpu_spec(vcpu_id):
    flavor = nova_helper.create_flavor(name='shared_vcpus', vcpus=64, check_storage_backing=False)[1]
    ResourceCleanup.add('flavor', resource_id=flavor)
    nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.CPU_POLICY: 'dedicated', FlavorSpec.SHARED_VCPU: vcpu_id})


@mark.parametrize(('vcpus', 'cpu_policy', 'shared_vcpu'), [
    mark.p2((4, 'shared', 3)),
    mark.p3((4, 'dedicated', 5)),
    mark.p3((4, 'dedicated', -1)),
    mark.p3((64, 'dedicated', 64)),
])
def test_set_shared_vcpu_spec_reject(cpu_policy, vcpus, shared_vcpu):
    """
    Test set shared vcpu id to invalid value will be rejected.

    Args:
        cpu_policy (str): shared or dedicated
        vcpus (int): number of vcpus to set when creating flavor
        shared_vcpu (int): vcpu id to attempt to set to

    Test Steps:
        - Create flavor with given number of vcpus
        - Set cpu_policy extra spec to given value
        - Attempt to set shared vcpu id to specific value (invalid value)
        - Ensure cli is rejected

    Teardown:
        - Delete created flavor

    """
    LOG.tc_step("Create flavor with {} vcpus, and set cpu_policy to {}".format(vcpus, cpu_policy))

    flavor = nova_helper.create_flavor(vcpus=vcpus, check_storage_backing=False)[1]
    ResourceCleanup.add('flavor', flavor, scope='function')
    nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.CPU_POLICY: cpu_policy})

    LOG.tc_step("Attempt to set shared_vcpu spec to invalid value - {} and verify it's rejected.".format(shared_vcpu))
    code, output = nova_helper.set_flavor_extra_specs(flavor, fail_ok=True, **{FlavorSpec.SHARED_VCPU: shared_vcpu})

    error_msg = 'undefined'
    if cpu_policy == 'shared':
        error_msg = SharedCPUErr.DEDICATED_CPU_REQUIRED
    elif shared_vcpu < 0:
        error_msg = SharedCPUErr.INVALID_VCPU_ID
    elif shared_vcpu >= vcpus:
        error_msg = SharedCPUErr.MORE_THAN_FLAVOR.format(shared_vcpu, vcpus)

    assert code == 1, "Set vcpu id cli should be rejected."
    assert error_msg in output, "Error message mismatch. Actual: {}".format(output)


class TestSharedCpuDisabled:

    @fixture(scope='class')
    def remove_shared_cpu(self, request, config_host_class):
        storage_backing, hosts = nova_helper.get_storage_backing_with_max_hosts()
        assert hosts, "No hypervisor in storage aggregate"

        avail_zone = None
        hosts_unconfigured = []
        for host in hosts:
            shared_cores_host = host_helper.get_host_cpu_cores_for_function(hostname=host, func='shared', thread=0)
            if shared_cores_host[0] or shared_cores_host.get(1, None):
                hosts_unconfigured.append(host)

        if not hosts_unconfigured:
            return storage_backing, avail_zone

        hosts_configured = list(set(hosts) - set(hosts_unconfigured))
        hosts_to_configure = []
        if len(hosts_configured) < 2:
            hosts_to_configure = hosts_unconfigured[:(2-len(hosts_configured))]

        for host_to_config in hosts_to_configure:
            shared_cores = host_helper.get_host_cpu_cores_for_function(host_to_config, 'shared', thread=0)
            p1_config = p1_revert = None
            if 1 in shared_cores:
                p1_config = 0
                p1_revert = len(shared_cores[1])

            def _modify(host_):
                host_helper.modify_host_cpu(host_, 'shared', p0=0, p1=p1_config)

            def _revert(host_):
                host_helper.modify_host_cpu(host_, 'shared', p0=len(shared_cores[0]), p1=p1_revert)

            config_host_class(host=host_to_config, modify_func=_modify, revert_func=_revert)
            host_helper.wait_for_hypervisors_up(host_to_config)
            hosts_configured.append(host_to_config)
            hosts_unconfigured.remove(host_to_config)

        if hosts_unconfigured:
            avail_zone = 'cgcsauto'

            def remove_admin():
                nova_helper.delete_aggregate(avail_zone, remove_hosts=True)
                if code != -1:
                    LOG.fixture_step("({}) Remove admin role and cgcsauto aggregate".format('class'))
                    keystone_helper.add_or_remove_role(add_=False, role='admin')
            request.addfinalizer(remove_admin)

            LOG.fixture_step("({}) Add admin role to user under primary tenant and add configured hosts {} to "
                             "cgcsauto aggregate".format('class', hosts_configured))
            code = keystone_helper.add_or_remove_role(add_=True, role='admin')[0]
            nova_helper.add_hosts_to_aggregate(aggregate=avail_zone, hosts=hosts_configured)

        return storage_backing, avail_zone

    @mark.parametrize(('vcpus', 'cpu_policy', 'numa_nodes', 'numa_node0', 'shared_vcpu'), [
        mark.p1((2, 'dedicated', 1, 1, 1)),
        mark.p2((2, 'dedicated', 2, None, 1)),
        mark.p1((3, 'dedicated', 1, 1, 0)),
        mark.p3((5, 'dedicated', 1, 1, 2)),
        # mark.p3((64, 'dedicated', 1, 1, 63)),   # No host supports this many vcpus atm
    ])
    def test_launch_vm_shared_cpu_setting_negative(self, vcpus, cpu_policy, numa_nodes, numa_node0, shared_vcpu,
                                                   remove_shared_cpu):
        """
        Test boot vm cli returns error when system does not meet the shared cpu requirement(s) in given flavor

        Args:
            vcpus (int): number of vcpus to set when creating flavor
            cpu_policy (str): 'dedicated' or 'shared' to set in flavor extra specs
            numa_nodes (int): number of numa nodes to set in flavor extra specs
            numa_node0 (int): value for numa_node.0
            shared_vcpu (int):
            remove_shared_cpu (tuple)

        Test Steps:
            - Create flavor with given number of vcpus
            - Add specific cpu_policy, number of numa nodes, nume_node.0 , shared_vcpu values to flavor extra specs
            - Attempt to boot a vm with the flavor
            - Ensure proper error is returned

        Teardown:
            - Delete created vm if any (function)
            - Delete created volume if any (module)

        """
        storage_backing, avail_zone = remove_shared_cpu
        LOG.tc_step("Create flavor with given numa configs")
        flavor = create_shared_flavor(vcpus=vcpus, cpu_policy=cpu_policy, storage_backing=storage_backing,
                                      numa_nodes=numa_nodes, node0=numa_node0, shared_vcpu=shared_vcpu)

        LOG.tc_step("Attempt to launch a vm with conflig numa node requirements")
        code, vm_id, output, vol_id = vm_helper.boot_vm(name='shared_cpu_negative', flavor=flavor, fail_ok=True,
                                                        cleanup='function', avail_zone=avail_zone)

        cores_quota = int(nova_helper.get_quotas('cores')[0])
        if vcpus >= cores_quota:
            assert 4 == code, 'Expect boot vm cli rejected and no vm is booted. Actual: {}'.format(output)
            expt_err = 'Quota exceeded for cores: '
            assert expt_err in output, "Expected error message is not included in cli output."
        else:
            assert 1 == code, 'Expect boot vm cli return error, although vm is booted anyway. Actual: {}'.format(output)
            LOG.tc_step("Ensure vm is in error state with expected fault message in nova show")
            vm_helper.wait_for_vm_values(vm_id, 10, status='ERROR', fail_ok=False)
            actual_fault = nova_helper.get_vm_nova_show_value(vm_id=vm_id, field='fault')
            expt_fault = 'Shared vCPU not enabled on host cell'

            assert expt_fault in actual_fault, "Expected fault message mismatch"

    @fixture(scope='class')
    def basic_vm(self, remove_shared_cpu):
        storage_backing, avail_zone = remove_shared_cpu
        vm_id = vm_helper.boot_vm(cleanup='class', avail_zone=avail_zone)[1]
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        return vm_id, storage_backing

    @mark.parametrize(('vcpus', 'cpu_policy', 'shared_vcpu'), [
        mark.p1((2, 'dedicated', 1)),
    ])
    def test_resize_vm_shared_cpu_negative(self, vcpus, cpu_policy, shared_vcpu, basic_vm):
        """
        Test resize request is rejected if system does not meet the shared_cpu requirement(s) in the flavor

        Args:
            vcpus (int): number of vcpus in flavor
            cpu_policy (str): cpu_policy in flavor extra specs
            shared_vcpu (int):
            basic_vm (str): id of a basic vm to attempt resize on

        Setup:
            - Boot a basic vm (module)

        Test Steps:
            - Create a flavor with given number of vcpus
            - Set extra specs for cpu_policy, shared_vcpu
            - Attempt to resize the basic vm with the flavor
            - Ensure cli is rejected and proper error returned

        Teardowns:
            - Delete created vm and volume (module)

        """
        vm_id, storage_backing = basic_vm
        LOG.tc_step("Create a flavor with {} vcpus. Set extra specs with: {} cpu_policy, {} shared_vcpu".format(
                vcpus, cpu_policy, shared_vcpu))
        flavor = nova_helper.create_flavor(name='shared_cpu', vcpus=vcpus, storage_backing=storage_backing)[1]
        ResourceCleanup.add('flavor', flavor, scope='module')
        nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.CPU_POLICY: cpu_policy})
        nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.SHARED_VCPU: shared_vcpu})

        LOG.tc_step("Attempt to resize vm with invalid flavor, and verify resize request is rejected.")
        code, msg = vm_helper.resize_vm(vm_id, flavor, fail_ok=True)
        assert code == 1, "Resize vm request is not rejected"
        assert re.search(ResizeVMErr.SHARED_NOT_ENABLED.format('0'), msg)

        LOG.tc_step("Ensure VM is still pingable after resize reject")
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)


def check_host_cpu_and_memory(host, expt_shared_cpu, expt_1g_page):
    """
    Check host cpu and memory configs via sysinv cli
    Args:
        host:
        expt_shared_cpu (dict): {<proc>: <shared_core_count>, ...}
        expt_1g_page (dict): {<proc>: <page_count>, ...}

    Returns:

    """
    LOG.info("Check {} shared core config: {}".format(host, expt_shared_cpu))
    shared_cores_ = host_helper.get_host_cpu_cores_for_function(hostname=host, func='shared')
    for proc in expt_shared_cpu:
        assert len(shared_cores_[proc]) == expt_shared_cpu[proc], "Actual shared cpu count is different than expected"

    LOG.info("Check {} 1g page config: {}".format(host, expt_1g_page))
    mempages_1g = system_helper.get_host_mem_values(host, headers=('vm_hp_total_1G',))
    for proc in expt_1g_page:
        assert mempages_1g[proc][0] == expt_1g_page[proc], "Actual 1g page is differnt than expected"


class TestSharedCpuEnabled:

    @fixture(scope='class')
    def add_shared_cpu(self, no_simplex, config_host_class, request):
        """
        This fixture ensures at least two hypervisors are configured with shared cpu on proc0 and proc1
        It also reverts the configs at the end.

        Args:
            no_simplex:
            config_host_class:
            request:

        Returns:

        """
        storage_backing, hosts = nova_helper.get_storage_backing_with_max_hosts()
        if len(hosts) < 2:
            skip("Less than two hypervisors with same storage backend")

        LOG.fixture_step("Ensure at least two hypervisors has shared cpu cores on both p0 and p1")
        shared_cpu_hosts = []
        shared_disabled_hosts = {}
        modified_hosts = []

        for host_ in hosts:
            shared_cores_for_host = host_helper.get_host_cpu_cores_for_function(hostname=host_, func='shared')
            if 1 not in shared_cores_for_host:
                LOG.info("{} has only 1 processor. Ignore.".format(host_))
                continue

            if shared_cores_for_host[0] and shared_cores_for_host[1]:
                shared_cpu_hosts.append(host_)
                if len(shared_cpu_hosts) == 2:
                    break
            else:
                shared_disabled_hosts[host_] = shared_cores_for_host
        else:
            if len(shared_disabled_hosts) + len(shared_cpu_hosts) < 2:
                skip("Less than two up hypervisors with 2 processors")

            def _modify(host_to_modify):
                host_helper.modify_host_cpu(host_to_modify, 'shared', p0=1, p1=1)
                host_helper.modify_host_memory(host_to_modify, proc=0, gib_1g=4)

            for host_to_config in shared_disabled_hosts:
                config_host_class(host=host_to_config, modify_func=_modify)
                host_helper.wait_for_hypervisors_up(host_to_config)
                host_helper.wait_for_mempage_update(host_to_config)
                check_host_cpu_and_memory(host_to_config, expt_shared_cpu={0: 1, 1: 1}, expt_1g_page={0: 4})
                shared_cpu_hosts.append(host_to_config)
                modified_hosts.append(host_to_config)
                if len(shared_cpu_hosts) >= 2:
                    break

            def revert():
                for host_to_revert in modified_hosts:
                    check_host_cpu_and_memory(host_to_revert, expt_shared_cpu={0: 1, 1: 1}, expt_1g_page={0: 4})
                    p0_shared = len(shared_disabled_hosts[host_to_revert][0])
                    p1_shared = len(shared_disabled_hosts[host_to_revert][1])
                    try:
                        LOG.fixture_step("Revert {} shared cpu and memory setting".format(host_to_revert))
                        host_helper.lock_host(host_to_revert)
                        host_helper.modify_host_cpu(host_to_revert, 'shared', p0=p0_shared, p1=p1_shared)
                        host_helper.modify_host_memory(host_to_revert, proc=0, gib_1g=0)
                    finally:
                        host_helper.unlock_host(host_to_revert)
                        host_helper.wait_for_mempage_update(host_to_revert)

                    check_host_cpu_and_memory(host_to_revert,
                                              expt_shared_cpu={0: p0_shared, 1: p1_shared}, expt_1g_page={0: 0})
            request.addfinalizer(revert)

        max_vcpus_proc0 = 0
        max_vcpus_proc1 = 0
        host_max_proc0 = None
        host_max_proc1 = None

        LOG.fixture_step("Get VMs cores for each host")
        for host in shared_cpu_hosts:
            vm_cores_per_proc = host_helper.get_host_cpu_cores_for_function(host, func='VMs', thread=None)
            if len(vm_cores_per_proc[0]) > max_vcpus_proc0:
                max_vcpus_proc0 = len(vm_cores_per_proc[0])
                host_max_proc0 = host
            if len(vm_cores_per_proc.get(1, [])) > max_vcpus_proc1:
                max_vcpus_proc1 = len(vm_cores_per_proc.get(1, []))
                host_max_proc1 = host

        LOG.fixture_step("Increase quota of allotted cores")
        vm_helper.ensure_vms_quotas(cores_num=(max(max_vcpus_proc0, max_vcpus_proc1) + 1))

        return storage_backing, shared_cpu_hosts, [(max_vcpus_proc0, host_max_proc0), (max_vcpus_proc1, host_max_proc1)]

    # TC2920, TC2921
    @mark.parametrize(('vcpus', 'numa_nodes', 'numa_node0', 'shared_vcpu', 'error'), [
        mark.domain_sanity((3, 1, 1, 2, None)),
        # mark.domain_sanity((2, 1, 1, 1, None)),
        (2, 2, None, 1, 'error')
    ])
    def test_launch_vm_with_shared_cpu(self, vcpus, numa_nodes, numa_node0, shared_vcpu, error, add_shared_cpu,
                                       origin_total_vcpus):
        """
        Test boot vm cli returns error when system does not meet the shared cpu requirement(s) in given flavor

        Args:
            vcpus (int): number of vcpus to set when creating flavor
            numa_nodes (int): number of numa nodes to set in flavor extra specs
            numa_node0 (int): value for numa_node.0
            shared_vcpu (int):
            error
            add_shared_cpu
            origin_total_vcpus

        Setup:
            - Configure one compute to have shared cpus via 'system host-cpu-modify -f shared p0=1,p1=1 <hostname>'

        Test Steps:
            - Create flavor with given number of vcpus
            - Add specific cpu_policy, number of numa nodes, nume_node.0 , shared_vcpu values to flavor extra specs
            - Boot a vm with the flavor
            - Ensure vm is booted successfully
            - Validate the shared cpu
            - Live migrate the vm
            - Re-validate the shared cpu
            - Cold migrate the vm
            - Re-validate the shared cpu

        Teardown:
            - Delete created vm if any (function)
            - Delete created volume if any (module)
            - Set shared cpus to 0 (default setting) on the compute node under test (module)

        """
        storage_backing, shared_cpu_hosts, max_vcpus_per_proc = add_shared_cpu
        LOG.tc_step("Create a flavor with given number of vcpus")

        flavor = create_shared_flavor(vcpus, storage_backing=storage_backing, numa_nodes=numa_nodes, node0=numa_node0,
                                      shared_vcpu=shared_vcpu)

        LOG.tc_step("Boot a vm with above flavor")
        code, vm_id, output, vol_id = vm_helper.boot_vm(name='shared_cpu', flavor=flavor, fail_ok=True,
                                                        cleanup='function')

        if error:
            LOG.tc_step("Check vm boot fail")
            assert 1 == code, "Expect error vm. Actual result: {}".format(output)
            LOG.tc_step("Ensure vm is in error state with expected fault message in nova show")
            vm_helper.wait_for_vm_values(vm_id, 10, status='ERROR', fail_ok=False)
            actual_fault = nova_helper.get_vm_nova_show_value(vm_id=vm_id, field='fault')
            expt_fault = 'shared vcpu with 0 requested dedicated vcpus is not allowed'
            assert expt_fault in actual_fault, "Expected fault message mismatch"
            return

        LOG.tc_step("Check vm booted successfully and shared cpu indicated in vm-topology")
        assert 0 == code, "Boot vm failed. Details: {}".format(output)

        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        check_shared_vcpu(vm=vm_id, numa_node0=numa_node0, numa_nodes=numa_nodes,
                          shared_vcpu=shared_vcpu, vcpus=vcpus, prev_total_vcpus=origin_total_vcpus)

        # live migrate
        LOG.tc_step("Live migrate vm and then ping vm from NatBox")
        vm_helper.live_migrate_vm(vm_id)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        check_shared_vcpu(vm=vm_id, numa_node0=numa_node0, numa_nodes=numa_nodes,
                          shared_vcpu=shared_vcpu, vcpus=vcpus, prev_total_vcpus=origin_total_vcpus)

        # cold migrate
        LOG.tc_step("Cold migrate vm and then ping vm from NatBox")
        vm_helper.cold_migrate_vm(vm_id)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        check_shared_vcpu(vm=vm_id, numa_node0=numa_node0, numa_nodes=numa_nodes,
                          shared_vcpu=shared_vcpu, vcpus=vcpus, prev_total_vcpus=origin_total_vcpus)

    # TC2922
    def test_resize_vm_with_shared_cpu(self, add_shared_cpu, origin_total_vcpus):
        """
        Test that the vm created with shared vcpus can successfully be resized to a flavor with shared vcpus and to a
        flavor without shared vcpus (and back)

        Setup:
            - Configure two computes to have shared cpus via 'system host-cpu-modify -f shared p0=1,p1=1 <hostname>'

        Test Steps:
            - Create 3 flavors as follows:
                - flavor1 has 2 vcpus, dedicated cpu policy, 1 numa node, numa_0 is set to 1 and a shared vcpu
                - flavor2 has 4 vcpus, dedicated cpu policy, 1 numa node, numa_0 is set to 1 and a shared vcpu
                - flavor3 has 4 vcpus, dedicated cpu policy, 1 numa node, numa_0 is set to 1 and no shared vcpus
            - Add specific cpu_policy (dedicated), number of numa nodes(1), nume_node.0(1) , shared_vcpu values to
            flavor extra specs
            - Boot a vm with the flavor1
            - Ensure vm is booted successfully
            - Validate the shared cpu
            - Resize vm to flavor2 (enabled shared vcpu flavor)
            - Revalidate the shared cpu
            - Resize vm to flavor3 (disabled shared vcpu)
            - Revalidate the shared cpu by ensuring that it does not have a shared vcpu
            - Resize vm to back to flavor2
            - Revalidate the shared cpu by making sure it has a shared vcpu again

        Teardown:
            - Delete created vm if any (function)
            - Delete created volume if any (module)
            - Set shared cpus to 0 (default setting) on the compute node under test (module)
        """
        storage_backing, shared_cpu_hosts, max_vcpus_per_proc = add_shared_cpu

        LOG.tc_step("Create a flavor with given number of vcpus")
        f1_vcpus = 2
        f1_numa_nodes = 1
        f1_node0 = 1
        f1_shared_vcpu = 1
        flavor1 = create_shared_flavor(vcpus=f1_vcpus, storage_backing=storage_backing, numa_nodes=f1_numa_nodes,
                                       node0=f1_node0, shared_vcpu=f1_shared_vcpu)

        LOG.tc_step("Boot a vm with above flavor, and ensure vm is booted successfully")
        code, vm_id, output, vol_id = vm_helper.boot_vm(name='shared_cpu', flavor=flavor1, fail_ok=True,
                                                        cleanup='function')

        assert 0 == code, "Boot vm failed. Details: {}".format(output)

        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        check_shared_vcpu(vm=vm_id, numa_node0=f1_node0, numa_nodes=f1_numa_nodes, vcpus=f1_vcpus,
                          prev_total_vcpus=origin_total_vcpus, shared_vcpu=f1_shared_vcpu)

        f2_vcpus = 4
        f2_numa_nodes = 1
        f2_node0 = 1
        f2_shared_vcpu = 1
        f2_shared_cpu = create_shared_flavor(vcpus=f2_vcpus, storage_backing=storage_backing,
                                             numa_nodes=f2_numa_nodes, node0=f2_node0, shared_vcpu=f2_shared_vcpu)

        f3_vcpus = 4
        f3_numa_nodes = 1
        f3_node0 = 1
        f3_non_shared = create_shared_flavor(vcpus=f3_vcpus, storage_backing=storage_backing,
                                             numa_nodes=f3_numa_nodes, node0=f3_node0)

        LOG.tc_step("Resize vm w/shared cpu flavor and validate shared vcpu")
        vm_helper.resize_vm(vm_id, f2_shared_cpu)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        check_shared_vcpu(vm=vm_id, numa_node0=f2_node0, numa_nodes=f2_numa_nodes, shared_vcpu=f2_shared_vcpu,
                          vcpus=f2_vcpus, prev_total_vcpus=origin_total_vcpus)

        LOG.tc_step("Resize vm w/non shared cpu flavor")
        vm_helper.resize_vm(vm_id, f3_non_shared)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        check_shared_vcpu(vm=vm_id, numa_node0=f3_node0, numa_nodes=f3_numa_nodes, shared_vcpu=None,
                          vcpus=f3_vcpus, prev_total_vcpus=origin_total_vcpus)

        LOG.tc_step("Resize vm back to shared cpu flavor and validate shared vcpu")
        vm_helper.resize_vm(vm_id, f2_shared_cpu)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        check_shared_vcpu(vm=vm_id, numa_node0=f2_node0, numa_nodes=f2_numa_nodes, shared_vcpu=f2_shared_vcpu,
                          vcpus=f2_vcpus, prev_total_vcpus=origin_total_vcpus)

    # TC2923
    def test_evacuate_shared_cpu_vm(self, target_hosts, add_shared_cpu, add_admin_role_func):
        """
        Test that instance with shared vcpu can be evacuated and that the vm still has shared vcpu after evacuation

        Setup:
            - Configure at least two computes to have shared cpus via
                'system host-cpu-modify -f shared p0=1,p1=1 <hostname>' (module)

        Test Steps:
            - Create 2 flavors as follows:
                - flavor1 has 2 vcpus, dedicated cpu policy, 1 numa node, numa_0 is set to 0 and 1 shared vcpu
                - flavor2 has 2 vcpus, dedicated cpu policy, 1 numa node, numa_0 is set to 1 and 1 shared vcpu
            - Boot a vm for each of the created flavors
            - Ensure all vms are booted successfully and validate the shared vcpus
            - Evacuate the vms
            - Ensure evacuation is successful and validate the shared vcpus

        Teardown:
            - Delete created vms and flavors
            - Set shared cpus to 0 (default setting) on the compute node under test (module)

        """
        storage_backing, shared_cpu_hosts, max_vcpus_per_proc = add_shared_cpu
        vm_helper.delete_vms()
        prev_total_vcpus = host_helper.get_vcpus_for_computes()

        flv1_args = {
            'numa_nodes': 1,
            'node0': 0,
        }
        flv2_args = {
            'node0': 1,
        }

        shared_vcpu = 1
        vcpus = 2
        _flv_args = {'vcpus': vcpus, 'storage_backing': storage_backing, 'shared_vcpu': shared_vcpu}
        flv1_args.update(_flv_args)
        flv2_args.update(_flv_args)

        target_host = shared_cpu_hosts[0]
        vms = {}
        pcpus = vcpus - 1
        expt_increase = pcpus
        for flv_arg in (flv1_args, flv2_args):
            LOG.tc_step("Create a flavor with following specs and launch a vm with this flavor: {}".format(flv_arg))
            flv_id = create_shared_flavor(**flv_arg)
            vm_id = vm_helper.boot_vm(name='shared_cpu', flavor=flv_id, fail_ok=False, avail_zone='nova',
                                      vm_host=target_host, cleanup='function')[1]
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

            LOG.tc_step("Check vm {} numa node setting via vm-topology".format(vm_id))
            check_shared_vcpu(vm=vm_id, numa_node0=flv_arg.get('node0', None),
                              numa_nodes=flv_arg.get('numa_nodes', None),
                              shared_vcpu=shared_vcpu, vcpus=vcpus, prev_total_vcpus=prev_total_vcpus,
                              expt_increase=expt_increase)

            expt_increase += pcpus
            vms[vm_id] = flv_arg

        LOG.tc_step("Evacuate vms")
        vm_helper.evacuate_vms(target_host, vms_to_check=list(vms.keys()), ping_vms=True)

        vm_hosts = []
        LOG.tc_step("Check shared vcpus and numa settings for vms after evacuation")
        for vm_ in vms:
            vm_host = nova_helper.get_vm_host(vm_id=vm_)
            vm_hosts.append(vm_host)

        if len(list(set(vm_hosts))) == 1:
            post_evac_expt_increase = pcpus * 2
        else:
            post_evac_expt_increase = pcpus

        for vm_, flv_arg_ in vms.items():
            check_shared_vcpu(vm=vm_, numa_node0=flv_arg_.get('node0', None),
                              numa_nodes=flv_arg_.get('numa_nodes', None), expt_increase=post_evac_expt_increase,
                              prev_total_vcpus=prev_total_vcpus, shared_vcpu=shared_vcpu, vcpus=vcpus)

    @mark.parametrize(('vcpus', 'numa_nodes', 'numa_node0', 'shared_vcpu', 'min_vcpus'), [
            (3, 1, 1, 0, 1)
    ])
    def test_shared_vcpu_scaling(self, vcpus, numa_nodes, numa_node0, shared_vcpu, min_vcpus, add_shared_cpu):
        """
            Tests the following:
            - That the scaling of instance with shared vCPU behaves appropiately (TC5097)

            Test Setup:
                - Configure at least two computes to have shared cpus via
                    'system host-cpu-modify -f shared p0=1,p1=1 <hostname>' (module)

            Test Steps:
                - enable shared CPU on a compute node,
                - Create a scalable flavor with 4 cpus and shared CPU
                - Add min_vcpus related extra specs
                - Boot a vm with flavor
                - validate shared CPU
                - scale down instance once
                    -confirm offline vcpus pin to shared cpu
                - scale down to minimum vcpus and back to maximum
                    - confirm appropriate vcpu pinning.
            Teardown:
                - Delete created vms and flavors
        """

        storage_backing, shared_cpu_hosts, max_vcpus_per_proc = add_shared_cpu
        prev_total_vcpus = host_helper.get_vcpus_for_computes()
        if max_vcpus_per_proc[numa_node0][0] < vcpus/numa_nodes \
                or max_vcpus_per_proc[0 if numa_node0 == 1 else 1][0] < vcpus - (vcpus/numa_nodes):
            skip("Less than {} VMs cores on numa node0 of any hypervisor".format(vcpus/numa_nodes))
        # make vm (4 vcpus)
        LOG.tc_step("Make a flavor with {} vcpus and scaling enabled".format(vcpus))
        flavor_1 = create_shared_flavor(vcpus=vcpus, numa_nodes=numa_nodes, node0=numa_node0, shared_vcpu=shared_vcpu)
        ResourceCleanup.add('flavor', flavor_1)
        first_specs = {FlavorSpec.MIN_VCPUS: min_vcpus}
        nova_helper.set_flavor_extra_specs(flavor_1, **first_specs)
        LOG.tc_step("Boot a vm with above flavor")
        vm_1 = vm_helper.boot_vm(flavor=flavor_1, cleanup='function', fail_ok=False)[1]
        vm_helper.wait_for_vm_pingable_from_natbox(vm_1)
        GuestLogs.add(vm_1)
        LOG.tc_step("Validate Shared CPU")
        check_shared_vcpu(vm_1, numa_node0, numa_nodes, vcpus=vcpus, prev_total_vcpus=prev_total_vcpus,
                          min_vcpus=min_vcpus, shared_vcpu=shared_vcpu)

        # scale down once
        LOG.tc_step("Scale down the vm once")
        vm_helper.scale_vm(vm_1, direction='down', resource='cpu', fail_ok=False)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_1)
        check_helper.check_vm_vcpus_via_nova_show(vm_1, min_vcpus, (vcpus-1), vcpus)

        LOG.tc_step("Confirm offline vCPUs pin to shared CPU")
        host = nova_helper.get_vm_host(vm_1)
        check_helper.check_topology_of_vm(vm_1, vcpus=vcpus, prev_total_cpus=prev_total_vcpus[host],
                                          shared_vcpu=shared_vcpu, min_vcpus=min_vcpus, current_vcpus=vcpus-1,
                                          expt_increase=vcpus-2, cpu_pol='dedicated')

        # scale down to 1 (minimum)
        LOG.tc_step("Scale down to minimum vCPUs")
        for i in range(vcpus - 2):
            vm_helper.scale_vm(vm_1, direction='down', resource='cpu', fail_ok=False)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_1)

        LOG.tc_step("Confirm offline vCPUs pin to shared CPU")
        host = nova_helper.get_vm_host(vm_1)
        check_helper.check_topology_of_vm(vm_1, vcpus=vcpus, prev_total_cpus=prev_total_vcpus[host],
                                          shared_vcpu=shared_vcpu, min_vcpus=min_vcpus, current_vcpus=min_vcpus,
                                          expt_increase=min_vcpus-1, cpu_pol='dedicated')

        # scale up from 1 to vcpus (maximum)
        LOG.tc_step("Scale up to maximum vCPUs")
        for i in range(vcpus - 1):
            vm_helper.scale_vm(vm_1, direction='up', resource='cpu', fail_ok=False)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_1)
        host = nova_helper.get_vm_host(vm_1)
        check_helper.check_topology_of_vm(vm_1, vcpus=vcpus, prev_total_cpus=prev_total_vcpus[host],
                                          shared_vcpu=shared_vcpu, min_vcpus=min_vcpus, current_vcpus=vcpus,
                                          expt_increase=vcpus-1, cpu_pol='dedicated')
        GuestLogs.remove(vm_1)

    @mark.parametrize(('vcpus', 'numa_nodes', 'numa_node0', 'shared_vcpu'), [
            (3, 1, 1, 0)
    ])
    def test_shared_vcpu_pinning_constraints(self, vcpus, numa_nodes, numa_node0, shared_vcpu,
                                             add_shared_cpu, add_admin_role_func):
        """
        Tests the following:
        - That pinning constraints do not count on shared vCPU (TC5098)

        Test Setup:
            - Configure at least two computes to have shared cpus via
                'system host-cpu-modify -f shared p0=1,p1=1 <hostname>' (module)

        Test Steps:
            - enable shared CPU on a compute node
            - create flavor with shared vCPU
            - determine how many pcpus are available on a compute host
            - create a flavor with no shared vCPUs
                - has a number of vCPUs so that after booting it the number of available pcpus is:
                shared CPU flavor #vCPUs-1
            - boot instances using flavor without shared CPU.
            - boot instance with shared CPU flavor
            - confirm (via vm-topology and virsh vcpupin) that shared_vcpu of instance is pinned to the shared pcpu
                -and the remaining vcpus are pinned to the available physical cpus from the previous step.

        Teardown:
            - Delete created vms and flavors
        """

        storage_backing, shared_cpu_hosts, max_vcpus_per_proc = add_shared_cpu
        if max_vcpus_per_proc[numa_node0][0] < vcpus/numa_nodes \
                or max_vcpus_per_proc[0 if numa_node0 == 1 else 1][0] < vcpus - (vcpus/numa_nodes):
            skip("Less than {} VMs cores on numa node0 of any hypervisor with shared cpu".format(vcpus/numa_nodes))

        # make vm
        LOG.tc_step("Make a flavor with {} shared vcpus".format(vcpus))
        flavor_1 = create_shared_flavor(vcpus=vcpus, numa_nodes=numa_nodes, node0=numa_node0, shared_vcpu=shared_vcpu)
        ResourceCleanup.add('flavor', flavor_1)

        # select a compute node to use
        vm_host = max_vcpus_per_proc[numa_node0][1]

        # get the available vcpus on the selected numa node
        LOG.tc_step("Check how many vCPUs are available on the selected node")
        available_vcpus = int(host_helper.get_vcpus_for_computes(hosts=vm_host, rtn_val='vcpu_avail',
                                                                 numa_node=numa_node0)[vm_host])

        # create a flavor with no shared vcpu
        LOG.tc_step("Create a flavor with enough vcpus to fill the diff")
        no_share_flavor = nova_helper.create_flavor(vcpus=available_vcpus-(vcpus - 1))[1]
        ResourceCleanup.add('flavor', no_share_flavor)
        second_specs = {FlavorSpec.CPU_POLICY: 'dedicated', FlavorSpec.NUMA_NODES: numa_nodes,
                        FlavorSpec.NUMA_0: numa_node0}
        nova_helper.set_flavor_extra_specs(no_share_flavor, **second_specs)

        LOG.tc_step("boot vm with above flavor")
        vm_1 = vm_helper.boot_vm(flavor=no_share_flavor, cleanup='function', fail_ok=False, vm_host=vm_host)[1]
        vm_helper.wait_for_vm_pingable_from_natbox(vm_1)
        GuestLogs.add(vm_1)

        # get the available vcpus on the selected numa node
        LOG.tc_step("Check how many vCPUs are available on the selected node")
        available_vcpus = int(host_helper.get_vcpus_for_computes(hosts=vm_host, rtn_val='vcpu_avail',
                                                                 numa_node=numa_node0)[vm_host])
        assert available_vcpus == vcpus-1

        prev_total_vcpus = host_helper.get_vcpus_for_computes()

        LOG.tc_step("Boot a VM with the shared VCPU Flavor")
        vm_share = vm_helper.boot_vm(flavor=flavor_1, cleanup='function', fail_ok=False, vm_host=vm_host)[1]
        vm_helper.wait_for_vm_pingable_from_natbox(vm_share)
        GuestLogs.add(vm_share)

        check_shared_vcpu(vm=vm_share, vcpus=vcpus, prev_total_vcpus=prev_total_vcpus, shared_vcpu=shared_vcpu,
                          numa_nodes=numa_nodes, numa_node0=numa_node0)


class TestMixSharedCpu:

    @fixture(scope='class')
    def config_host_cpus(self, no_simplex, config_host_class):
        storage_backing, hosts = nova_helper.get_storage_backing_with_max_hosts()

        if len(hosts) < 3:
            skip("Require at least three hosts with same storage backing")

        shared_cpu_hosts = []
        disabled_shared_cpu_hosts = []
        # Look through hosts to see if we already have the desired configuration with having to modify
        for host in hosts:
            shared_cores_host = host_helper.get_host_cpu_cores_for_function(hostname=host, func='shared', thread=0)
            if shared_cores_host[0] or shared_cores_host[1]:
                shared_cpu_hosts.append(host)
            else:
                disabled_shared_cpu_hosts.append(host)

        # If something is missing, then we'll have to config it ourselves
        LOG.fixture_step("Ensure at least one hypervisor has disabled shared cpu cores on both p0 and p1")
        if not disabled_shared_cpu_hosts:
            converted_host = shared_cpu_hosts.pop(0)
            shared_cores = host_helper.get_host_cpu_cores_for_function(converted_host, 'shared', thread=0)

            def _modify(hst):
                host_helper.modify_host_cpu(hst, 'shared', p0=0, p1=0)

            def _revert(hst):
                host_helper.modify_host_cpu(hst, 'shared', p0=len(shared_cores[0]), p1=len(shared_cores[1]))

            config_host_class(host=converted_host, modify_func=_modify, revert_func=_revert)
            host_helper.wait_for_hypervisors_up(converted_host)
            disabled_shared_cpu_hosts.append(converted_host)

        LOG.fixture_step("Ensure at least two hypervisors has shared cpu cores on p0")
        while len(shared_cpu_hosts) < 2:
            converted_host = disabled_shared_cpu_hosts.pop(0)

            def _modify(hst):
                host_helper.modify_host_cpu(hst, 'shared', p0=1)

            def _revert(hst):
                LOG.fixture_step("Revert {} shared cpu setting to original".format(host))
                host_helper.modify_host_cpu(hst, 'shared', p0=0)

            config_host_class(host=converted_host, modify_func=_modify, revert_func=_revert)
            host_helper.wait_for_hypervisors_up(converted_host)
            shared_cpu_hosts.append(converted_host)

        disable_shared_cpu_host = disabled_shared_cpu_hosts[0]

        return storage_backing, disable_shared_cpu_host, shared_cpu_hosts

    # TC6549
    def test_shared_cpu_migrate(self, config_host_cpus):
        """
        Test vm with shared cpus enabled can successful live migrate to a node with shared vcpus enabled and fails when
        it tries to migrate to a node with shared vcpus disabled

        Setup:
            - Skip if there are less than 3 hosts
            - Configure at least one compute to disable shared vcpus
            - Configure at least two computes to have shared cpus via
                'system host-cpu-modify -f shared p0=1,p1=1 <hostname>' (module)

        Test Steps:
            - Create flavor with given number of vcpus
            - Add specific cpu_policy, shared_vcpu values to flavor extra specs
            - Boot a vm with the flavor
            - Ensure vm is booted successfully
            - Perform a non-forced live migration on vm. Ensure that vm is on a shared cpu host.
            - Perform a non-forced cold migration on vm. Ensure that vm is on a shared cpu host.
            - Force live-migrate vm to host with shared vcpus enabled. The migration should succeed
                - Ensure that the vm is on a different host
            - Force live-migrate vm to the host with disabled shared vcpus. The migration should fail
                - Verify error by ensuring that vm is still on same host and grep nova-scheduler logs for
                'CANNOT SCHEDULE'

        Teardown:
            - Delete created vm if any (function)
            - Revert any hosts that were changed for this test

        """

        storage_backing, disable_shared_cpu_host, enabled_shared_hosts = config_host_cpus

        LOG.tc_step("Create a flavor with given number of vcpus")
        flavor = create_shared_flavor(vcpus=2, storage_backing=storage_backing, numa_nodes=1, shared_vcpu=1)
        nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.MEM_PAGE_SIZE: 2048})

        LOG.tc_step("Boot a vm with above flavor, and ensure vm is booted successfully")
        vm_id = vm_helper.boot_vm(name='shared_cpu', flavor=flavor, fail_ok=False, cleanup='function')[1]
        origin_host = nova_helper.get_vm_host(vm_id)
        assert origin_host in enabled_shared_hosts, "VM not booted on shared cpu host"

        LOG.tc_step("Perform a non-forced live migration onto an enabled shared cpu host, expect success")
        vm_helper.live_migrate_vm(vm_id)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        new_host = nova_helper.get_vm_host(vm_id)
        assert new_host in enabled_shared_hosts, "VM not migrated on shared cpu host"

        LOG.tc_step("Perform a non-forced cold migration onto an enabled shared cpu host, expect success")
        vm_helper.cold_migrate_vm(vm_id)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        new_host = nova_helper.get_vm_host(vm_id)
        assert new_host in enabled_shared_hosts, "VM not migrated on shared cpu host"

        if new_host != enabled_shared_hosts[0]:
            dest_host = enabled_shared_hosts[0]
        else:
            dest_host = enabled_shared_hosts[1]

        LOG.tc_step("Perform second live migration onto an enabled shared cpu host, expect success")
        vm_helper.live_migrate_vm(vm_id, destination_host=dest_host, force=True)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

        LOG.tc_step("Perform third live migration onto a disabled shared cpu host, expect failure")
        code = vm_helper.live_migrate_vm(vm_id, destination_host=disable_shared_cpu_host, force=True, fail_ok=True)[0]
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        assert code != 0, "Migrate not rejected as expected"
        assert nova_helper.get_vm_host(vm_id) == dest_host, "VM not on same compute node"

        LOG.tc_step("Verify second live migration failed via nova-scheduler.log")
        req_id = get_failed_live_migrate_action_id(vm_id)
        grepcmd = "grep 'CANNOT SCHEDULE' /var/log/nova/nova-scheduler.log | grep {}".format(req_id)
        control_ssh = ControllerClient.get_active_controller()
        control_ssh.exec_cmd(grepcmd, fail_ok=False)
