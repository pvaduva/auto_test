from pytest import fixture, mark, skip

from utils.tis_log import LOG
from consts.cgcs import FlavorSpec
from consts.cli_errs import SharedCPUErr, ResizeVMErr

from keywords import nova_helper, vm_helper, host_helper, system_helper
from testfixtures.fixture_resources import ResourceCleanup


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
    def remove_shared_cpu(self, config_host_class):
        storage_backing, hosts = nova_helper.get_storage_backing_with_max_hosts()

        hosts_to_config = []
        for host in hosts:
            shared_cores_host = host_helper.get_host_cpu_cores_for_function(hostname=host, function='shared', thread=0)
            if shared_cores_host[0] or shared_cores_host[1]:
                hosts_to_config.append(host)

        if not hosts_to_config:
            return storage_backing

        for host_to_config in hosts_to_config:
            shared_cores = host_helper.get_host_cpu_cores_for_function(host_to_config, 'shared', thread=0)

            def _modify(host):
                host_helper.modify_host_cpu(host, 'shared', p0=0, p1=0)

            def _revert(host):
                host_helper.modify_host_cpu(host, 'shared', p0=len(shared_cores[0]), p1=len(shared_cores[1]))

            config_host_class(host=host_to_config, modify_func=_modify, revert_func=_revert)
            host_helper.wait_for_hypervisors_up(host_to_config)

        return storage_backing

    @mark.parametrize(('vcpus', 'cpu_policy', 'numa_nodes', 'numa_node0', 'shared_vcpu'), [
        mark.p1((2, 'dedicated', 1, 1, 1)),
        mark.p2((2, 'dedicated', 2, None, 1)),
        mark.p1((3, 'dedicated', 1, 1, 0)),
        mark.p3((64, 'dedicated', 1, 1, 2)),
        mark.p3((64, 'dedicated', 1, 1, 63)),   # Assuming quota for cores for tenant under test is less than 63
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
            remove_shared_cpu (str)

        Test Steps:
            - Create flavor with given number of vcpus
            - Add specific cpu_policy, number of numa nodes, nume_node.0 , shared_vcpu values to flavor extra specs
            - Attempt to boot a vm with the flavor
            - Ensure proper error is returned

        Teardown:
            - Delete created vm if any (function)
            - Delete created volume if any (module)

        """
        flavor = nova_helper.create_flavor(vcpus=vcpus, storage_backing=remove_shared_cpu)[1]
        ResourceCleanup.add('flavor', flavor, scope='function')
        nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.CPU_POLICY: cpu_policy})
        numa_nodes_flv = {FlavorSpec.NUMA_NODES: numa_nodes}
        if numa_node0 is not None:
            numa_nodes_flv[FlavorSpec.NUMA_0] = numa_node0
        nova_helper.set_flavor_extra_specs(flavor, **numa_nodes_flv)
        nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.SHARED_VCPU: shared_vcpu})

        code, vm_id, output, vol_id = vm_helper.boot_vm(name='shared_cpu_negative', flavor=flavor, fail_ok=True,
                                                        cleanup='function')

        cores_quota = int(nova_helper.get_quotas('cores')[0])
        if vcpus >= cores_quota:
            assert 4 == code, 'Expect boot vm cli rejected and no vm is booted. Actual: {}'.format(output)
            expt_err = 'Quota exceeded for cores: '
            assert expt_err in output, "Expected error message is not included in cli output."
        else:
            assert 1 == code, 'Expect boot vm cli return error, although vm is booted anyway. Actual: {}'.format(output)

            fault_pattern = ".*Shared not enabled for cell .*"
            res_bool, vals = vm_helper.wait_for_vm_values(vm_id, 10, regex=True, strict=False, status='ERROR',
                                                          fault=fault_pattern)
            assert res_bool, "VM did not reach expected error state. Actual: {}".format(vals)

    @fixture(scope='class')
    def basic_vm(self):
        vm_id = vm_helper.boot_vm(cleanup='class')[1]
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        return vm_id

    @mark.parametrize(('vcpus', 'cpu_policy', 'shared_vcpu'), [
        mark.p1((2, 'dedicated', 1)),
    ])
    def test_resize_vm_shared_cpu_negative(self, vcpus, cpu_policy, shared_vcpu, basic_vm, remove_shared_cpu):
        """
        Test resize request is rejected if system does not meet the shared_cpu requirement(s) in the flavor

        Args:
            vcpus (int): number of vcpus in flavor
            cpu_policy (str): cpu_policy in flavor extra specs
            shared_vcpu (int):
            basic_vm (str): id of a basic vm to attempt resize on
            remove_shared_cpu (str)

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
        LOG.tc_step("Create a flavor with {} vcpus. Set extra specs with: {} cpu_policy, {} shared_vcpu".format(
                vcpus, cpu_policy, shared_vcpu))
        flavor = nova_helper.create_flavor(name='shared_cpu', vcpus=vcpus, storage_backing=remove_shared_cpu)[1]
        ResourceCleanup.add('flavor', flavor, scope='module')
        nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.CPU_POLICY: cpu_policy})
        nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.SHARED_VCPU: shared_vcpu})

        LOG.tc_step("Attempt to resize vm with invalid flavor, and verify resize request is rejected.")
        code, msg = vm_helper.resize_vm(basic_vm, flavor, fail_ok=True)
        assert code == 1, "Resize vm request is not rejected"
        assert ResizeVMErr.SHARED_NOT_ENABLED.format('0') in msg

        LOG.tc_step("Ensure VM is still pingable after resize reject")
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id=basic_vm)


class TestSharedCpuEnabled:
    @fixture(scope='class')
    def add_shared_cpu(self, config_host_class):
        storage_backing, hosts = nova_helper.get_storage_backing_with_max_hosts(rtn_down_hosts=False)

        LOG.fixture_step("Ensure at least one hypervisor has Shared cpu cores on both p0 and p1")
        for host_ in hosts:
            shared_cores_for_host = host_helper.get_host_cpu_cores_for_function(hostname=host_, function='shared')
            if shared_cores_for_host[0] and shared_cores_for_host[1]:
                break
        else:
            if system_helper.is_two_node_cpe():
                host_to_config = system_helper.get_standby_controller_name()
            else:
                host_to_config = host_helper.get_nova_host_with_min_or_max_vms(rtn_max=False, hosts=hosts)

            if not host_to_config:
                skip("No up hypervisor found to reconfigure")

            shared_cores = host_helper.get_host_cpu_cores_for_function(host_to_config, 'shared')
            mod = False
            if len(shared_cores[0]) != 1 or len(shared_cores[1]) != 1:
                mod = True

            if mod:
                def _modify(host):
                    host_helper.modify_host_cpu(host, 'shared', p0=1, p1=1)

                def _revert(host):
                    LOG.fixture_step("Revert {} shared cpu setting to original".format(host))
                    host_helper.modify_host_cpu(host, 'shared', p0=len(shared_cores[0]), p1=len(shared_cores[1]))

                config_host_class(host=host_to_config, modify_func=_modify, revert_func=_revert)
                host_helper.wait_for_hypervisors_up(host_to_config)

        return storage_backing

    @mark.parametrize(('vcpus', 'cpu_policy', 'numa_nodes', 'numa_node0', 'shared_vcpu'), [
        mark.domain_sanity((2, 'dedicated', 1, 1, 1)),
    ])
    def test_launch_vm_with_shared_cpu(self, vcpus, cpu_policy, numa_nodes, numa_node0, shared_vcpu, add_shared_cpu):
        """
        Test boot vm cli returns error when system does not meet the shared cpu requirement(s) in given flavor

        Args:
            vcpus (int): number of vcpus to set when creating flavor
            cpu_policy (str): 'dedicated' or 'shared' to set in flavor extra specs
            numa_nodes (int): number of numa nodes to set in flavor extra specs
            numa_node0 (int): value for numa_node.0
            shared_vcpu (int):

        Setup:
            - Configure one compute to have shared cpus via 'system host-cpu-modify -f shared p0=1,p1=1 <hostname>' (module)

        Test Steps:
            - Create flavor with given number of vcpus
            - Add specific cpu_policy, number of numa nodes, nume_node.0 , shared_vcpu values to flavor extra specs
            - Boot a vm with the flavor
            - Ensure vm is booted successfully

        Teardown:
            - Delete created vm if any (function)
            - Delete created volume if any (module)
            - Set shared cpus to 0 (default setting) on the compute node under test (module)

        """
        LOG.tc_step("Create a flavor with given number of vcpus")
        flavor = nova_helper.create_flavor(vcpus=vcpus, storage_backing=add_shared_cpu)[1]
        ResourceCleanup.add('flavor', flavor, scope='function')

        LOG.tc_step("Add specific cpu_policy, number_of_numa_nodes, numa_node0, and shared_vcpu to flavor extra specs")
        nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.CPU_POLICY: cpu_policy})
        nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.NUMA_NODES: numa_nodes, FlavorSpec.NUMA_0: numa_node0})
        nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.SHARED_VCPU: shared_vcpu})

        LOG.tc_step("Boot a vm with above flavor, and ensure vm is booted successfully")
        code, vm_id, output, vol_id = vm_helper.boot_vm(name='shared_cpu', flavor=flavor, fail_ok=True,
                                                        cleanup='function')

        assert 0 == code, "Boot vm failed. Details: {}".format(output)

        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
