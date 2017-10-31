import time, re

from pytest import mark, fixture

from utils.tis_log import LOG
from utils import table_parser

from consts.cgcs import FlavorSpec
from consts.cli_errs import MinCPUErr       # Do not remove this import, used by eval()
from keywords import nova_helper, vm_helper, host_helper, check_helper, system_helper
from testfixtures.fixture_resources import ResourceCleanup


@mark.parametrize(('vcpu_num', 'cpu_policy', 'min_vcpus', 'expected_err'), [
    mark.p2((1, 'dedicated', 2, "MinCPUErr.VAL_LARGER_THAN_VCPUS")),
    mark.p3((1, 'dedicated', [0, -1], "MinCPUErr.VAL_LESS_THAN_1")),
    mark.p3((2, 'shared', 1, "MinCPUErr.CPU_POLICY_NOT_DEDICATED")),
    mark.p3((2, None, 1, "MinCPUErr.CPU_POLICY_NOT_DEDICATED")),
])
def test_flavor_min_vcpus_invalid(vcpu_num, cpu_policy, min_vcpus, expected_err):
    """
    Test invalid settings of vcpu scheduler flavor specs.

    Args:
        vcpu_num (int): number of vcpus to set when creating flavor
        cpu_policy (str): cpu policy to set in extra specs
        min_vcpus (list|str): minimum vcpu number to set in flavor extra specs
        expected_err (str): Expected error strings upon cli rejection

    Test Steps:
        - Create a flavor with given number of vcpus
        - Attempt to set min_vcpu extra specs to given value
        - Check cli is rejected with expected error string
    Teardown:
        - Delete flavor
    """
    LOG.tc_step("Create flavor with {} vcpus".format(vcpu_num))
    flavor_id = nova_helper.create_flavor('vcpu_scheduler_invalid', vcpus=vcpu_num)[1]
    ResourceCleanup.add('flavor', flavor_id)
    if cpu_policy is not None:
        nova_helper.set_flavor_extra_specs(flavor=flavor_id, **{FlavorSpec.CPU_POLICY: cpu_policy})

    if isinstance(min_vcpus, int):
        min_vcpus = [min_vcpus]

    for min_vcpu in min_vcpus:
        extra_spec = {FlavorSpec.MIN_VCPUS: str(min_vcpu)}

        LOG.tc_step("Attempt to set min_vcpus to invalid value - {} in extra specs, and verify it is rejected".
                    format(min_vcpu))
        code, output = nova_helper.set_flavor_extra_specs(flavor=flavor_id, fail_ok=True, **extra_spec)

        assert 1 == code, "Set flavor extra spec request is not rejected."

        if expected_err:
            assert eval(expected_err) in output, "Expected error string is not found in CLI output."


@fixture(scope='module')
def ht_and_nonht_hosts():
    LOG.fixture_step("Look for hyper-threading enabled and disabled hosts")
    nova_hosts = host_helper.get_nova_hosts()
    ht_hosts = []
    non_ht_hosts = []
    for host in nova_hosts:
        if system_helper.is_hyperthreading_enabled(host):
            ht_hosts.append(host)
        else:
            non_ht_hosts.append(host)

    LOG.fixture_step('Hyper-threading enabled hosts: {}; Hyper-threading disabled hosts: {}'.
                     format(ht_hosts, non_ht_hosts))
    return ht_hosts, non_ht_hosts


@mark.parametrize(('vcpus', 'cpu_thread_pol', 'min_vcpus', 'numa_0'), [
    # mark.p2((6, 'require', None, 1)),  # Not allowed to set min_vcpus with require
    mark.p2((6, 'isolate', 3, 0)),
    mark.p2((2, 'prefer', 1, 0)),
    mark.p2((3, None, 2, 1)),  # should default to prefer behaviour
    mark.p2((4, 'isolate', 2, None)),
    mark.priorities('nightly', 'sx_nightly')((5, 'prefer', 3, None)),
])
def test_nova_actions_post_cpu_scale(vcpus, cpu_thread_pol, min_vcpus, numa_0, ht_and_nonht_hosts):
    """
    Test nova actions after scaling vcpus, and ensure vm topology persists
    Args:
        vcpus (int): number of vcpus
        cpu_thread_pol (str|None):
        min_vcpus (int):
        numa_0 (int|None):
        ht_and_nonht_hosts (tuple): HT and non-HT hosts on the system

    Returns:

    """
    ht_hosts, non_ht_hosts = ht_and_nonht_hosts

    LOG.tc_step("Create flavor with {} vcpus".format(vcpus))
    flavor_id = nova_helper.create_flavor(name='cpu_scale', vcpus=vcpus)[1]
    ResourceCleanup.add('flavor', flavor_id)

    specs = {FlavorSpec.CPU_POLICY: 'dedicated'}
    if cpu_thread_pol is not None:
        specs[FlavorSpec.CPU_THREAD_POLICY] = cpu_thread_pol
    if min_vcpus is not None:
        specs[FlavorSpec.MIN_VCPUS] = min_vcpus
    if numa_0 is not None:
        specs[FlavorSpec.NUMA_0] = numa_0

    LOG.tc_step("Set following extra specs: {}".format(specs))
    nova_helper.set_flavor_extra_specs(flavor_id, **specs)

    LOG.tc_step("Boot a vm with above flavor")
    vm_id = vm_helper.boot_vm(name='vcpu{}_min{}_{}'.format(vcpus, min_vcpus, cpu_thread_pol), flavor=flavor_id,
                              cleanup='function')[1]

    LOG.tc_step("Wait for vm pingable from NatBox and guest_agent process running on VM")
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    time.sleep(10)
    # # Workaround due to CGTS-5755
    # if min_vcpus:
    #     vm_helper.wait_for_process(process='guest_agent', vm_id=vm_id, disappear=False, timeout=120, fail_ok=False)

    vm_host = nova_helper.get_vm_host(vm_id)
    if cpu_thread_pol == 'require':
        assert vm_host in ht_hosts, "require VM is not on hyperthreaded host"

    LOG.tc_step("Check vm vcpus in nova show is as specified in flavor")
    expt_min_cpu = vcpus if min_vcpus is None else min_vcpus
    expt_max_cpu = expt_current_cpu = vcpus
    check_helper.check_vm_vcpus_via_nova_show(vm_id, expt_min_cpu, expt_current_cpu, expt_max_cpu)

    LOG.tc_step("Get used cpus for all hosts before scaling vm")
    host_allocated_cpus = host_helper.get_vcpus_for_computes(hosts=vm_host, rtn_val='used_now')[vm_host]

    expt_vcpu_num_change = 2 if (cpu_thread_pol == 'isolate' and vm_host in ht_hosts) else 1

    # Scale down test
    expt_total_increase = 0
    if expt_current_cpu > expt_min_cpu:
        LOG.tc_step("Scale down vm vcpus until it hits the lower limit and ensure scale is successful.")
        for i in range(expt_current_cpu - expt_min_cpu):
            LOG.tc_step("Scale down once and check vm vcpus change in nova show")
            vm_helper.scale_vm(vm_id, direction='down', resource='cpu')
            expt_current_cpu -= 1
            expt_total_increase -= expt_vcpu_num_change

    LOG.tc_step('Check total allocated vcpus for host and pcpus for vm is reduced by {}'.format(-expt_total_increase))
    prev_siblings = check_helper.check_topology_of_vm(vm_id, vcpus=vcpus, prev_total_cpus=host_allocated_cpus,
                                                      vm_host=vm_host, cpu_pol='dedicated', cpu_thr_pol=cpu_thread_pol,
                                                      expt_increase=expt_total_increase,
                                                      min_vcpus=expt_min_cpu,
                                                      current_vcpus=expt_current_cpu)[1]

    LOG.tc_step("VM is now at it's minimal vcpus, attempt to scale down and ensure it's rejected")
    code, output = vm_helper.scale_vm(vm_id, direction='down', resource='cpu', fail_ok=True)
    assert 1 == code, 'scale down cli is not rejected. Actual: {}'.format(output)

    LOG.tc_step("Check vm vcpus in nova show did not change")
    check_helper.check_vm_vcpus_via_nova_show(vm_id, expt_min_cpu, expt_current_cpu, expt_max_cpu)

    all_hosts = host_helper.get_nova_hosts()
    pre_action_vm_host = vm_host

    for actions in [['pause', 'unpause'], ['suspend', 'resume'], ['live_migrate'], ['cold_migrate'], ['stop', 'start']]:

        LOG.tc_step("Perform nova action(s) on scaled VM and check vm topology is correct: {}".format(actions))
        pre_action_hosts_cpus = host_helper.get_vcpus_for_computes(hosts=all_hosts, rtn_val='used_now')

        for action in actions:
            vm_helper.perform_action_on_vm(vm_id=vm_id, action=action)

        post_action_vm_host = nova_helper.get_vm_host(vm_id)
        host_allocated_cpus = pre_action_hosts_cpus[post_action_vm_host]
        expt_vcpu_num_change = 2 if (cpu_thread_pol == 'isolate' and post_action_vm_host in ht_hosts) else 1
        expt_vcpu_num_change = 0 if pre_action_vm_host == post_action_vm_host else expt_vcpu_num_change*expt_current_cpu
        prev_siblings = prev_siblings if actions[0] == 'live_migrate' else None

        prev_siblings = check_helper.check_topology_of_vm(vm_id, vcpus=vcpus,
                                                          prev_total_cpus=host_allocated_cpus,
                                                          vm_host=post_action_vm_host,
                                                          cpu_pol='dedicated',
                                                          cpu_thr_pol=cpu_thread_pol,
                                                          expt_increase=expt_vcpu_num_change,
                                                          prev_siblings=prev_siblings,
                                                          min_vcpus=expt_min_cpu,
                                                          current_vcpus=expt_current_cpu)[1]

        pre_action_vm_host = post_action_vm_host

    # Scale up post nova actions
    expt_total_increase = 0
    vm_host = pre_action_vm_host
    host_allocated_cpus = host_helper.get_vcpus_for_computes(hosts=vm_host, rtn_val='used_now')[vm_host]
    expt_vcpu_num_change = 2 if (cpu_thread_pol == 'isolate' and vm_host in ht_hosts) else 1
    if expt_current_cpu < expt_max_cpu:
        LOG.tc_step("Scale up vm vcpus until it hits the upper limit and ensure scale is successful.")
        for i in range(expt_max_cpu - expt_current_cpu):
            vm_helper.scale_vm(vm_id, direction='up', resource='cpu')
            expt_current_cpu += 1
            expt_total_increase += expt_vcpu_num_change

    LOG.tc_step('Check total allocated vcpus for host and pcpus for vm is increased by {}'.format(expt_total_increase))
    check_helper.check_topology_of_vm(vm_id, vcpus=vcpus, prev_total_cpus=host_allocated_cpus,
                                      vm_host=vm_host, cpu_pol='dedicated', cpu_thr_pol=cpu_thread_pol,
                                      expt_increase=expt_total_increase,
                                      min_vcpus=expt_min_cpu,
                                      current_vcpus=expt_current_cpu)

    LOG.tc_step("VM is now at it's minimal vcpus, attempt to scale down and ensure it's rejected")
    code, output = vm_helper.scale_vm(vm_id, direction='up', resource='cpu', fail_ok=True)
    assert 1 == code, 'scale up cli is not rejected. Actual: {}'.format(output)

    LOG.tc_step("Check vm vcpus in nova show did not change")
    check_helper.check_vm_vcpus_via_nova_show(vm_id, expt_min_cpu, expt_current_cpu, expt_max_cpu)

@fixture(scope='module')
def find_numa_node_and_cpu_count():
    storage_backing, target_hosts = nova_helper.get_storage_backing_with_max_hosts()
    vm_host = target_hosts[0]
    cpu_count = host_helper.get_logcores_counts(vm_host, proc_ids=(0, 1), thread=['0', '1'], functions='VMs')[0]
    LOG.info('cpu count: {}'.format(cpu_count))

    # increase quota
    vm_helper.ensure_vms_quotas(cores_num=(cpu_count + 1))

    return storage_backing, vm_host, cpu_count


def test_scaling_vm_negative(find_numa_node_and_cpu_count):
    """
        Tests the following:
            - that the resizing of a scaled-down vm to an unscalable flavor is rejected (TC5157)
            - that the attempted scaling up of a vm on a node that is out of pcpus returns a proper error (TC5159)

        Test Setup:
            - Find an online host and the number of logcores it has, and pass it onto the test

        Test Steps:
            - Create a scalable flavor with 3 cpus
            - Add numa_nodes related extra specs
            - Boot a vm with flavor
            - Scale the vm down once
            - Create an unscalable flavor and attempt to resize the vm to the new flavor
                - The resize operation should fail and return an appropiate error message
            - Create a vm that occupies all but one of the remaining vcpus
            - Scale up the first vm once, expect success
            - Scale up first vm again, expect failure and a relevant error message

        Teardown:
            - Delete created vms and flavors

        """

    inst_backing, vm_host, cpu_count = find_numa_node_and_cpu_count

    # make vm (3 vcpus)

    LOG.tc_step("Create flavor with 3 vcpus")
    first_specs = {FlavorSpec.MIN_VCPUS: 1, FlavorSpec.CPU_POLICY: 'dedicated', FlavorSpec.NUMA_0: 0}
    flavor_1 = nova_helper.create_flavor(vcpus=4, storage_backing=inst_backing)[1]
    nova_helper.set_flavor_extra_specs(flavor_1, **first_specs)
    ResourceCleanup.add('flavor', flavor_1)
    LOG.info("Boot a vm with above flavor")
    vm_1 = vm_helper.boot_vm(flavor=flavor_1, source='image', cleanup='function', vm_host=vm_host, fail_ok=False)[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_1)

    # scale down once

    LOG.info("Scale down the vm once")
    vm_helper.scale_vm(vm_1, direction='down', resource='cpu', fail_ok=False)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_1)

    # resize to unscalable flavor

    LOG.info("Create an unscalable flavor")
    unscale_flavor = nova_helper.create_flavor(vcpus=4, storage_backing=inst_backing)[1]
    ResourceCleanup.add('flavor', unscale_flavor)
    unscale_flavor_specs = {FlavorSpec.NUMA_0: 0}
    nova_helper.set_flavor_extra_specs(unscale_flavor, **unscale_flavor_specs)

    LOG.info("Attempt to resize vm to the flavor, assert that correct error message is returned")
    code, output = vm_helper.resize_vm(vm_1, unscale_flavor, fail_ok=True)
    expt_error = "Unable to resize to non-scalable flavor with scaled-down vCPUs.  Scale up and retry."
    assert code != 0, "Resize to unscalable flavor failed when it should have succeeded"
    assert re.search(expt_error, output), "Error message incorrect: expected {} in output when output is {}"\
        .format(expt_error, output)

    # scale down again

    LOG.info("Scale down the vm a second time")
    vm_helper.scale_vm(vm_1, direction='down', resource='cpu', fail_ok=False)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_1)

    # make another vm

    LOG.tc_step("Create a flavor to occupy vcpus ")
    occupy_amount = cpu_count - 3
    second_specs = {FlavorSpec.CPU_POLICY: 'dedicated', FlavorSpec.NUMA_0: 0}
    flavor_2 = nova_helper.create_flavor(vcpus=occupy_amount, storage_backing=inst_backing)[1]
    ResourceCleanup.add('flavor', flavor_2)
    nova_helper.set_flavor_extra_specs(flavor_2, **second_specs)

    LOG.tc_step("Boot a vm with above flavor to occupy all but one vcpu")
    vm_helper.boot_vm(flavor=flavor_2, source='image', cleanup='function', vm_host=vm_host, fail_ok=False)

    # scale first vm up once (pass)

    LOG.info("Scale up the first vm the first time")
    vm_helper.scale_vm(vm_1, direction='up', resource='cpu', fail_ok=False)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_1)

    # scale first vm up again (fail)

    LOG.info("Scale up the first vm a second time, expect an appropiate error message")
    exit_code, output = vm_helper.scale_vm(vm_1, direction='up', resource='cpu', fail_ok=True)
    expt_upscale_error = "Insufficient compute resources: no free pcpu available on NUMA node."
    assert exit_code != 0, "Scale VM up was successful when failure was expected"
    assert re.search(expt_upscale_error, output), "Error message incorrect: expected {} in output when output is {}"\
        .format(expt_error, output)
