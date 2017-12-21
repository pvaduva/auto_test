import time
from pytest import fixture, mark, skip

from utils import cli, table_parser
from utils.ssh import ControllerClient
from utils.tis_log import LOG
from consts.cgcs import FlavorSpec
from consts.cli_errs import SharedCPUErr, ResizeVMErr

from keywords import nova_helper, vm_helper, host_helper, keystone_helper
from testfixtures.fixture_resources import ResourceCleanup


def get_failed_live_migrate_action_id(vm_id):
    action_table = table_parser.table(cli.nova('instance-action-list {}'.format(vm_id)))
    req_id = table_parser.get_values(action_table, 'Request_ID', **{'Action': 'live-migration', 'Message': 'Error'})
    assert req_id, "request id for failed live migration not found"
    return req_id[0]


def check_shared_vcpu(vm, numa_node0, numa_nodes):
    host = nova_helper.get_vm_host(vm_id=vm)
    host_shared_vcpu_dict = host_helper.get_host_cpu_cores_for_function(host, function='Shared', thread=None)
    LOG.info("dict: {}".format(host_shared_vcpu_dict))
    if numa_nodes == 1:
        host_shared_vcpu = host_shared_vcpu_dict[numa_node0]
    else:
        host_shared_vcpu = host_shared_vcpu_dict[0] + host_shared_vcpu_dict[1]
    vm_shared_vcpu = vm_helper.get_instance_topology(vm)[0]['shared_pcpu'][0]
    assert vm_shared_vcpu in host_shared_vcpu


def check_disabled_shared_vcpu(vm):
    vm_shared_vcpu = vm_helper.get_instance_topology(vm)[0]['shared_pcpu']
    LOG.info("shared: {}".format(vm_shared_vcpu))
    assert not vm_shared_vcpu


def create_shared_flavor(vcpus=2, storage_backing='local_image', cpu_policy='dedicated',
                         numa_nodes=1, node0=None, node1=None, shared_vcpu=None):
    flavor_id = nova_helper.create_flavor(vcpus=vcpus, storage_backing=storage_backing)[1]
    ResourceCleanup.add('flavor', flavor_id, scope='function')

    LOG.tc_step("Add specific cpu_policy, number_of_numa_nodes, numa_node0, and shared_vcpu to flavor extra specs")
    extra_specs = {FlavorSpec.CPU_POLICY: cpu_policy, FlavorSpec.NUMA_NODES: numa_nodes}
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
            shared_cores_host = host_helper.get_host_cpu_cores_for_function(hostname=host, function='shared', thread=0)
            if shared_cores_host[0] or shared_cores_host[1]:
                hosts_unconfigured.append(host)

        if not hosts_unconfigured:
            return storage_backing, avail_zone

        hosts_configured = list(set(hosts) - set(hosts_unconfigured))
        hosts_to_configure = []
        if len(hosts_configured) < 2:
            hosts_to_configure = hosts_unconfigured[:(2-len(hosts_configured))]

        for host_to_config in hosts_to_configure:
            shared_cores = host_helper.get_host_cpu_cores_for_function(host_to_config, 'shared', thread=0)

            def _modify(host_):
                host_helper.modify_host_cpu(host_, 'shared', p0=0, p1=0)

            def _revert(host_):
                host_helper.modify_host_cpu(host_, 'shared', p0=len(shared_cores[0]), p1=len(shared_cores[1]))

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
        assert ResizeVMErr.SHARED_NOT_ENABLED.format('0') in msg

        LOG.tc_step("Ensure VM is still pingable after resize reject")
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)


class TestSharedCpuEnabled:
    @fixture(scope='class')
    def add_shared_cpu(self, config_host_class):
        storage_backing, hosts = nova_helper.get_storage_backing_with_max_hosts(rtn_down_hosts=False)

        LOG.fixture_step("Ensure at least two hypervisors has shared cpu cores on both p0 and p1")
        shared_cpu_hosts = []
        disabled_share_hosts = []

        for host_ in hosts:
            shared_cores_for_host = host_helper.get_host_cpu_cores_for_function(hostname=host_, function='shared')
            if shared_cores_for_host[0] and shared_cores_for_host[1]:
                shared_cpu_hosts.append(host_)
                if len(shared_cpu_hosts) == 2:
                    break
            else:
                disabled_share_hosts.append(host_)
        else:
            while len(shared_cpu_hosts) < 2:
                host_to_config = disabled_share_hosts.pop(0)

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
                    shared_cpu_hosts.append(host_to_config)

        return storage_backing

    # TC2920, TC2921
    @mark.parametrize(('vcpus', 'numa_nodes', 'numa_node0', 'shared_vcpu'), [
        mark.domain_sanity((2, 1, 1, 1)),
    ])
    def test_launch_vm_with_shared_cpu(self, vcpus, numa_nodes, numa_node0, shared_vcpu, add_shared_cpu):
        """
        Test boot vm cli returns error when system does not meet the shared cpu requirement(s) in given flavor

        Args:
            vcpus (int): number of vcpus to set when creating flavor
            numa_nodes (int): number of numa nodes to set in flavor extra specs
            numa_node0 (int): value for numa_node.0
            shared_vcpu (int):
            add_shared_cpu

        Setup:
            - Configure one compute to have shared cpus via 'system host-cpu-modify -f shared p0=1,p1=1 <hostname>'

        Test Steps:
            - Create flavor with given number of vcpus
            - Add specific cpu_policy, number of numa nodes, nume_node.0 , shared_vcpu values to flavor extra specs
            - Boot a vm with the flavor
            - Ensure vm is booted successfully
            - Validate the shared cpu
            - Live migrate the vm
            - Revalidate the shared cpu
            - Cold migrate the vm
            - Revalidate the shared cpu

        Teardown:
            - Delete created vm if any (function)
            - Delete created volume if any (module)
            - Set shared cpus to 0 (default setting) on the compute node under test (module)

        """
        LOG.tc_step("Create a flavor with given number of vcpus")

        flavor = create_shared_flavor(vcpus, storage_backing=add_shared_cpu, numa_nodes=numa_nodes, node0=numa_node0,
                                      shared_vcpu=shared_vcpu)

        LOG.tc_step("Boot a vm with above flavor, and ensure vm is booted successfully")
        code, vm_id, output, vol_id = vm_helper.boot_vm(name='shared_cpu', flavor=flavor, fail_ok=True,
                                                        cleanup='function')

        assert 0 == code, "Boot vm failed. Details: {}".format(output)

        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        check_shared_vcpu(vm=vm_id, numa_node0=numa_node0, numa_nodes=numa_nodes)

        # live migrate
        LOG.tc_step("Live migrate vm and then ping vm from NatBox")
        vm_helper.live_migrate_vm(vm_id)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=30)
        check_shared_vcpu(vm=vm_id, numa_node0=numa_node0, numa_nodes=numa_nodes)

        # cold migrate
        LOG.tc_step("Cold migrate vm and then ping vm from NatBox")
        vm_helper.cold_migrate_vm(vm_id)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=30)
        check_shared_vcpu(vm=vm_id, numa_node0=numa_node0, numa_nodes=numa_nodes)

    # TC2922
    def test_resize_vm_with_shared_cpu(self, add_shared_cpu):
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
        LOG.tc_step("Create a flavor with given number of vcpus")
        f1_vcpus = 2
        f1_numa_nodes = 1
        f1_node0 = 1
        f1_shared_vcpu = 1
        flavor = create_shared_flavor(vcpus=f1_vcpus, storage_backing=add_shared_cpu, numa_nodes=f1_numa_nodes,
                                      node0=f1_node0, shared_vcpu=f1_shared_vcpu)

        LOG.tc_step("Boot a vm with above flavor, and ensure vm is booted successfully")
        code, vm_id, output, vol_id = vm_helper.boot_vm(name='shared_cpu', flavor=flavor, fail_ok=True,
                                                        cleanup='function')

        assert 0 == code, "Boot vm failed. Details: {}".format(output)

        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        check_shared_vcpu(vm=vm_id, numa_node0=f1_node0, numa_nodes=f1_numa_nodes)

        f2_vcpus = 4
        f2_numa_nodes = 1
        f2_node0 = 1
        f2_shared_vcpu = 1
        new_shared_cpu_flavor = create_shared_flavor(vcpus=f2_vcpus, storage_backing=add_shared_cpu,
                                                     numa_nodes=f2_numa_nodes, node0=f2_node0,
                                                     shared_vcpu=f2_shared_vcpu)

        f3_vcpus = 4
        f3_numa_nodes = 1
        f3_node0 = 1
        non_shared_cpu_flavor = create_shared_flavor(vcpus=f3_vcpus, storage_backing=add_shared_cpu,
                                                     numa_nodes=f3_numa_nodes, node0=f3_node0)

        LOG.tc_step("Resize vm w/shared cpu flavor and validate shared vcpu")
        vm_helper.resize_vm(vm_id, new_shared_cpu_flavor)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        check_shared_vcpu(vm=vm_id, numa_node0=f2_node0, numa_nodes=f2_numa_nodes)

        LOG.tc_step("Resize vm w/non shared cpu flavor")
        vm_helper.resize_vm(vm_id, non_shared_cpu_flavor)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        check_disabled_shared_vcpu(vm_id)

        LOG.tc_step("Resize vm back to shared cpu flavor and validate shared vcpu")
        vm_helper.resize_vm(vm_id, new_shared_cpu_flavor)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        check_shared_vcpu(vm=vm_id, numa_node0=f3_node0, numa_nodes=f3_numa_nodes)

    # TC2923
    def test_evacuate_shared_cpu_vm(self, add_admin_role_func, add_shared_cpu):
        """
        Test that instance with shared vcpu can be evacuated and that the vm still has shared vcpu after evacuation

        Setup:
            - Configure at least two computes to have shared cpus via
                'system host-cpu-modify -f shared p0=1,p1=1 <hostname>' (module)

        Test Steps:
            - Create 3 flavors as follows:
                - flavor1 has 2 vcpus, dedicated cpu policy, 1 numa node, numa_0 is set to 0 and 1 shared vcpu
                - flavor2 has 2 vcpus, dedicated cpu policy, 1 numa node, numa_0 is set to 1 and 1 shared vcpu
                - flavor3 has 4 vcpus, dedicated cpu policy, 1 numa node, numa_0 is set to 1, numa1 is set to 0 and
                    1 shared vcpu
            - Boot a vm for each of the created flavors
            - Ensure all vms are booted successfully and validate the shared vcpus
            - Evacuate the vms
            - Ensure evacuation is successful and validate the shared vcpus

        Teardown:
            - Delete created vms and flavors
            - Set shared cpus to 0 (default setting) on the compute node under test (module)

        """
        flv1_args = {
            'numa_nodes': 1,
            'node0': 0,
        }
        flv2_args = {
            'numa_nodes': 1,
            'node0': 1,
        }
        flv3_args = {
            'vcpus': 4,
            'numa_nodes': 2,
            'node0': 1,
            'node1': 0
        }
        _flv_args = {'vcpus': 2, 'storage_backing': add_shared_cpu, 'shared_vcpu': 1}
        flv1_args.update(_flv_args)
        flv2_args.update(_flv_args)
        flv3_args.update(_flv_args)

        target_host = None
        vms = {}
        for flv_arg in (flv1_args, flv2_args, flv3_args):
            LOG.tc_step("Create a flavor with following specs and launch a vm with this flavor: {}".format(flv_arg))
            flv_id = create_shared_flavor(**flv_arg)
            vm_id = vm_helper.boot_vm(name='shared_cpu', flavor=flv_id, fail_ok=False, avail_zone='nova',
                                      vm_host=target_host, cleanup='function')[1]
            vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

            LOG.tc_step("Check vm {} numa node setting via vm-topology".format(vm_id))
            check_shared_vcpu(vm=vm_id, numa_node0=flv_arg['node0'], numa_nodes=flv_arg['numa_nodes'])
            vms[vm_id] = flv_arg
            if not target_host:
                target_host = nova_helper.get_vm_host(vm_id)

        LOG.tc_step("Evacuate vms")
        vm_helper.evacuate_vms(target_host, vms_to_check=list(vms.keys()), ping_vms=True)

        LOG.tc_step("Check shared vcpus and numa settings for vms after evacuation")
        for vm_, flv_arg_ in vms.items():
            check_shared_vcpu(vm=vm_, numa_node0=flv_arg_['node0'], numa_nodes=flv_arg_['numa_nodes'])


class TestMixSharedCpu:

    @fixture(scope='class')
    def config_host_cpus(self, config_host_class):
        storage_backing, hosts = nova_helper.get_storage_backing_with_max_hosts(rtn_down_hosts=False)

        if len(hosts) < 3:
            skip("Require at least three hosts with same storage backing")

        shared_cpu_hosts = []
        disabled_shared_cpu_hosts = []
        # Look through hosts to see if we already have the desired configuration with having to modify
        for host in hosts:
            shared_cores_host = host_helper.get_host_cpu_cores_for_function(hostname=host, function='shared', thread=0)
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
