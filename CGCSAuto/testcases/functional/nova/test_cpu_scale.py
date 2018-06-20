import time

from pytest import mark, fixture, skip

from utils.tis_log import LOG

from consts.cgcs import FlavorSpec
from consts.cli_errs import MinCPUErr       # Do not remove this import, used by eval()
from keywords import nova_helper, vm_helper, host_helper, check_helper, system_helper
from testfixtures.fixture_resources import ResourceCleanup, GuestLogs


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
    LOG.fixture_step("Look for hyper-threading enabled and disabled hosts, get VMs cores for each host")
    storage_backing, target_hosts = nova_helper.get_storage_backing_with_max_hosts()
    ht_hosts = {}
    non_ht_hosts = {}
    max_vcpus_proc0 = 0
    max_vcpus_proc1 = 0
    for host in target_hosts:
        vm_cores_per_proc = host_helper.get_host_cpu_cores_for_function(host, function='VMs', thread=None)
        max_vcpus_proc0 = max(max_vcpus_proc0, len(vm_cores_per_proc[0]))
        max_vcpus_proc1 = max(max_vcpus_proc1, len(vm_cores_per_proc.get(1, [])))

        host_helper.get_host_cpu_cores_for_function(host, function='VMs')
        if system_helper.is_hyperthreading_enabled(host):
            ht_hosts[host] = vm_cores_per_proc
        else:
            non_ht_hosts[host] = vm_cores_per_proc

    LOG.fixture_step("Increase quota of allotted cores")
    vm_helper.ensure_vms_quotas(cores_num=(max(max_vcpus_proc0, max_vcpus_proc1) + 1))

    LOG.fixture_step('Hyper-threading enabled hosts: {}; Hyper-threading disabled hosts: {}'.
                     format(ht_hosts, non_ht_hosts))
    return ht_hosts, non_ht_hosts, {0: max_vcpus_proc0, 1: max_vcpus_proc1}, storage_backing


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
    ht_hosts, non_ht_hosts, max_vcpus_per_proc, storage_backing = ht_and_nonht_hosts
    max_vcpus = max(max_vcpus_per_proc[0], max_vcpus_per_proc[1]) if numa_0 is None else max_vcpus_per_proc[numa_0]
    if max_vcpus < vcpus:
        proc = 'processor {}'.format(numa_0) if numa_0 is not None else 'any processor'
        skip("Test requires {} vcpus on {} while only {} available".format(vcpus, proc, max_vcpus))

    LOG.tc_step("Create flavor with {} vcpus".format(vcpus))
    flavor_id = nova_helper.create_flavor(name='cpu_scale', vcpus=vcpus, storage_backing=storage_backing)[1]
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

    GuestLogs.add(vm_id)
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

    all_hosts = host_helper.get_up_hypervisors()
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
    GuestLogs.remove(vm_id)


# TC5157 + TC5159
def test_scaling_vm_negative(ht_and_nonht_hosts, add_admin_role_func):
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
                - The resize operation should fail and return an appropriate error message (TC5157 passes here)
            - Create a vm that occupies all but one of the remaining vcpus
            - Scale up the first vm once, expect success
            - Scale up first vm again, expect failure and a relevant error message (TC5159 passes here)
            - Delete the second vm to free cpus
            - Scale up first vm, expect success
            - Re-attempt a resize, which should be successful this time (additional steps for test completeness)

        Teardown:
            - Delete created vms and flavors

        """

    ht_hosts, non_ht_hosts, max_vcpus_per_proc, storage_backing = ht_and_nonht_hosts
    if max_vcpus_per_proc[0] < 4:
        skip("Less than 4 VMs cores on processor 0 of any hypervisor")

    proc0_vm_cores = vm_host = None
    for hosts_info in (non_ht_hosts, ht_hosts):
        for host in hosts_info:
            vm_cores_per_proc = hosts_info[host]
            proc0_vm_cores = len(vm_cores_per_proc[0])
            if proc0_vm_cores >= 4:
                vm_host = host
                break
        if vm_host:
            break

    # make vm (4 vcpus)
    LOG.tc_step("Create flavor with 4 vcpus")
    first_specs = {FlavorSpec.MIN_VCPUS: 1, FlavorSpec.CPU_POLICY: 'dedicated', FlavorSpec.NUMA_0: 0}
    flavor_1 = nova_helper.create_flavor(vcpus=4, storage_backing=storage_backing)[1]
    ResourceCleanup.add('flavor', flavor_1)
    nova_helper.set_flavor_extra_specs(flavor_1, **first_specs)
    LOG.tc_step("Boot a vm with above flavor")
    vm_1 = vm_helper.boot_vm(flavor=flavor_1, source='image', cleanup='function', avail_zone='nova',
                             vm_host=vm_host, fail_ok=False)[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_1)

    GuestLogs.add(vm_1)
    # scale down once
    LOG.tc_step("Scale down the vm once")
    vm_helper.scale_vm(vm_1, direction='down', resource='cpu', fail_ok=False)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_1)
    check_helper.check_vm_vcpus_via_nova_show(vm_1, 1, 3, 4)

    # resize to unscalable flavor
    LOG.tc_step("Create an unscalable flavor")
    unscale_flavor = nova_helper.create_flavor(vcpus=4, storage_backing=storage_backing)[1]
    ResourceCleanup.add('flavor', unscale_flavor)
    unscale_flavor_specs = {FlavorSpec.CPU_POLICY: 'dedicated', FlavorSpec.NUMA_0: 0}
    nova_helper.set_flavor_extra_specs(unscale_flavor, **unscale_flavor_specs)

    # TC5157 condition tested here
    LOG.tc_step("Attempt to resize vm to the flavor, assert that correct error message is returned")
    code, output = vm_helper.resize_vm(vm_1, unscale_flavor, fail_ok=True)
    expt_error = "Unable to resize to non-scalable flavor with scaled-down vCPUs.  Scale up and retry."
    assert code == 1, "CLI command was not rejected as expected. Exit code is {}, msg is {}".format(code, output)
    assert expt_error in output, "Error message incorrect: expected {} in output when output is {}"\
        .format(expt_error, output)

    # scale down again
    LOG.tc_step("Scale down the vm a second time")
    vm_helper.scale_vm(vm_1, direction='down', resource='cpu', fail_ok=False)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_1)
    check_helper.check_vm_vcpus_via_nova_show(vm_1, 1, 2, 4)

    # make another vm
    LOG.tc_step("Create a flavor to occupy vcpus ")
    occupy_amount = proc0_vm_cores - 3
    second_specs = {FlavorSpec.CPU_POLICY: 'dedicated', FlavorSpec.NUMA_0: 0}
    flavor_2 = nova_helper.create_flavor(vcpus=occupy_amount, storage_backing=storage_backing)[1]
    ResourceCleanup.add('flavor', flavor_2)
    nova_helper.set_flavor_extra_specs(flavor_2, **second_specs)

    LOG.tc_step("Boot a vm with above flavor to occupy all but one vcpu")
    vm_2 = vm_helper.boot_vm(flavor=flavor_2, source='image', cleanup='function', avail_zone='nova',
                             vm_host=vm_host, fail_ok=False)[1]

    # scale first vm up once (pass)
    LOG.tc_step("Scale up the first vm the first time")
    vm_helper.scale_vm(vm_1, direction='up', resource='cpu', fail_ok=False)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_1)
    check_helper.check_vm_vcpus_via_nova_show(vm_1, 1, 3, 4)

    # scale first vm up again (fail). TC5159 condition tested here.
    LOG.tc_step("Scale up the first vm a second time, expect an appropiate error message")
    exit_code, output = vm_helper.scale_vm(vm_1, direction='up', resource='cpu', fail_ok=True)
    expt_upscale_error = "Insufficient compute resources: no free pcpu available on "
    assert exit_code == 1, "Scale VM up was successful when rejection was expected"
    assert expt_upscale_error in output, "Error message incorrect: expected {} in output when output is {}"\
        .format(expt_upscale_error, output)

    # delete VM to clear vcpus, scale first vm up again and resize the VM (should be successful this time)
    LOG.tc_step("Delete second VM")
    vm_helper.delete_vms(vms=vm_2)

    LOG.tc_step("Scale up the first vm again (expect success)")
    vm_helper.scale_vm(vm_1, direction='up', resource='cpu', fail_ok=False)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_1)
    check_helper.check_vm_vcpus_via_nova_show(vm_1, 1, 4, 4)

    LOG.tc_step("Resize vm (expect success)")
    vm_helper.resize_vm(vm_1, unscale_flavor, fail_ok=False)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_1)
    check_helper.check_vm_vcpus_via_nova_show(vm_1, 4, 4, 4)

    GuestLogs.remove(vm_1)


# TC2904 + TC2905 + TC5156
def _test_resize_scaled_down_vm(ht_and_nonht_hosts):
    """
        Tests the following:
            - that the resizing of a scaled-down vm to a scalable flavor with less cpus is successful (TC2904)
            - that the resizing of a scaled-down vm to a scalable flavor with more cpus is successful (TC2905)
            - That scaling down an instance and deleting it does not change the user quota (TC5156)
        Test Setup:
            - Find an online host and the number of logcores it has, and pass it onto the test

        Test Steps:
            - Create a scalable flavor with 3 cpus
            - Add vm scaling related extra specs
            - Boot a vm with flavor
            - Scale the vm down once
            - Resize to a flavor with less cpus
                - The resize operation should succeed  (TC2904 passes here)
            - Boot a vm with flavor
            - Scale the vm down once
            - resize to a flavor with more cpus
                - verify that it has more cpus, but offline ones are stil offline
                - resize should succeed (TC2905 passes here)
            - check the original user quota
                - Create a scalable flavor with 5 cpus
                - Add min vcpu related extra specs
                - Boot a vm with flavor
                    -verify that usage quota is 5
                - Scale the vm down three times
                    -verify that usage quota is 2
                - Delete the vm
                    - verify that usage quota returns to 0
                    - verify that the quota returns to its original value
        Teardown:
            - Delete created vms and flavors

        """

    ht_hosts, non_ht_hosts, max_vcpus_per_proc, storage_backing = ht_and_nonht_hosts
    if max_vcpus_per_proc[0] < 5 and max_vcpus_per_proc[1] < 5:
        skip("Less than 5 VMs cores on processor 0 and processor 1 of any hypervisor")

    # get the usage quota before the vm is created, used by TC5156
    LOG.tc_step('getting original usage quota')
    quota_origin = nova_helper.get_quotas('cores', detail='in_use')[0]

    # make vm (4 vcpus)
    LOG.tc_step("Create flavor with 4 vcpus")
    first_specs = {FlavorSpec.MIN_VCPUS: 1, FlavorSpec.CPU_POLICY: 'dedicated'}
    flavor_1 = nova_helper.create_flavor(vcpus=4, storage_backing=storage_backing)[1]
    ResourceCleanup.add('flavor', flavor_1)
    nova_helper.set_flavor_extra_specs(flavor_1, **first_specs)
    LOG.tc_step("Boot a vm with above flavor")
    vm_1 = vm_helper.boot_vm(flavor=flavor_1, cleanup='function', fail_ok=False)[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_1)
    GuestLogs.add(vm_1)

    # scale down once
    LOG.tc_step("Scale down the vm once")
    vm_helper.scale_vm(vm_1, direction='down', resource='cpu', fail_ok=False)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_1)
    check_helper.check_vm_vcpus_via_nova_show(vm_1, 1, 3, 4)

    # resize down to a scalable flavor
    LOG.tc_step("Create a scalable flavor with fewer cpus")
    scale_flavor = nova_helper.create_flavor(vcpus=2, storage_backing=storage_backing)[1]
    ResourceCleanup.add('flavor', scale_flavor)
    scale_flavor_specs = {FlavorSpec.MIN_VCPUS: 1, FlavorSpec.CPU_POLICY: 'dedicated'}
    nova_helper.set_flavor_extra_specs(scale_flavor, **scale_flavor_specs)

    # TC2904 condition tested here
    LOG.tc_step("Attempt to resize vm to the flavor, assert that resize is successful")
    vm_helper.resize_vm(vm_1, scale_flavor)
    check_helper.check_topology_of_vm(vm_id=vm_1, vcpus=2, prev_total_cpus=4, min_vcpus=1, cpu_pol='ded',
                                      expt_increase=-2)

    # scale down once to start TC2905
    LOG.tc_step("Scale down the vm once")
    vm_helper.scale_vm(vm_1, direction='down', resource='cpu', fail_ok=False)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_1)
    check_helper.check_vm_vcpus_via_nova_show(vm_1, 1, 1, 2)

    # resize up to scalable flavor
    LOG.tc_step("Create a scalable flavor with more cpus")
    scale_up_flavor = nova_helper.create_flavor(vcpus=5, storage_backing=storage_backing)[1]
    ResourceCleanup.add('flavor', scale_up_flavor)
    scale_up_flavor_specs = {FlavorSpec.MIN_VCPUS: 1, FlavorSpec.CPU_POLICY: 'dedicated'}
    nova_helper.set_flavor_extra_specs(scale_up_flavor, **scale_up_flavor_specs)

    # TC2905 condition tested here
    LOG.tc_step("Attempt to resize vm to the flavor, assert that resize is successful")
    vm_helper.resize_vm(vm_1, scale_up_flavor)
    check_helper.check_topology_of_vm(vm_id=vm_1, vcpus=5, prev_total_cpus=1, min_vcpus=1, cpu_pol='ded', expt_increase=3, current_vcpus=4)

    # get new usage quota, make sure it matches the number of vcpus in the vm
    LOG.tc_step('getting new usage quota')
    quota_with_vm_resize = nova_helper.get_quotas('cores', detail='in_use')[0]
    assert quota_with_vm_resize - quota_origin == 4

    # Scale VM up for next test case
    LOG.tc_step("Scale up the vm")
    vm_helper.scale_vm(vm_1, direction='up', resource='cpu')
    vm_helper.wait_for_vm_pingable_from_natbox(vm_1)
    check_helper.check_vm_vcpus_via_nova_show(vm_1, 1, 5, 5)

    # get new usage quota, make sure it matches the number of vcpus in the vm
    LOG.tc_step('getting new usage quota')
    quota_with_vm = nova_helper.get_quotas('cores', detail='in_use')[0]
    assert quota_with_vm - quota_origin == 5

    # scale down three times
    LOG.tc_step("Scale down the vm three times")
    for i in range(3):
        vm_helper.scale_vm(vm_1, direction='down', resource='cpu')
    vm_helper.wait_for_vm_pingable_from_natbox(vm_1)
    check_helper.check_vm_vcpus_via_nova_show(vm_1, 1, 2, 5)

    # check that the quota went down the appropiate amount (from 5 to 2)
    LOG.tc_step('getting new usage quota')
    quota_after_scale = nova_helper.get_quotas('cores', detail='in_use')[0]
    assert quota_with_vm - quota_after_scale == 3

    # delete vm and get new usage quota. TC5156 condition tested here
    LOG.tc_step("Delete first VM")
    vm_helper.delete_vms(vms=vm_1)
    GuestLogs.remove(vm_1)
    quota_deleted_vm = nova_helper.get_quotas('cores', detail='in_use')[0]
    assert quota_deleted_vm == quota_origin


def test_reject_scale_down_offline_cpu(ht_and_nonht_hosts):
    """
        Tests the following:
        - That requesting to scale down when the guest cpu is alread offline is met with the appropriate error (TC5158)

        Test Setup:
            - Find an online host and the number of logcores it has, and pass it onto the test

        Test Steps:
            - Create a scalable flavor with 4 cpus
            - Boot a vm with flavor
            - Request to scale the vm down
            - Request to scale the vm down, modify to select already-offline cpu
                 - verify that the request is rejected with the appropiate error
        Teardown:
            - Delete created vms and flavors
    """

    ht_hosts, non_ht_hosts, max_vcpus_per_proc, storage_backing = ht_and_nonht_hosts
    if max_vcpus_per_proc[0] < 4 and max_vcpus_per_proc[1] < 4:
        skip("Less than 4 VMs cores on processor 0 of any hypervisor")

    # make vm (4 vcpus)
    LOG.tc_step("Create flavor with 4 vcpus")
    first_specs = {FlavorSpec.MIN_VCPUS: 1, FlavorSpec.CPU_POLICY: 'dedicated'}
    flavor_1 = nova_helper.create_flavor(vcpus=4, storage_backing=storage_backing)[1]
    ResourceCleanup.add('flavor', flavor_1)
    nova_helper.set_flavor_extra_specs(flavor_1, **first_specs)
    LOG.tc_step("Boot a vm with above flavor")
    vm_1 = vm_helper.boot_vm(flavor=flavor_1, cleanup='function', fail_ok=False)[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_1)
    GuestLogs.add(vm_1)

    # scale down once
    LOG.tc_step("Scale down the vm once")
    vm_helper.scale_vm(vm_1, direction='down', resource='cpu', fail_ok=False)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_1)
    check_helper.check_vm_vcpus_via_nova_show(vm_1, 1, 3, 4)

    # edit guest to scale down disabled cpu
    LOG.tc_step("modify guest to select offline cpu for scaling down")
    # ssh into the guest, replace return $CPU_NUM with 3 in /usr/sbin/app_scale_helper cpu_scale_down()'
    with vm_helper.ssh_to_vm_from_natbox(vm_id=vm_1) as vm_ssh:
        vm_ssh.exec_sudo_cmd("sed -i 's/return $CPU_NUM/return 3/g' /usr/sbin/app_scale_helper")
        vm_ssh.exec_sudo_cmd("cat /usr/sbin/app_scale_helper | grep -i 'return 3'", fail_ok=False)

    # TC5158 condition tested here
    LOG.tc_step("Attempt to scale vm down, assert that correct error message is returned")
    code, output = vm_helper.scale_vm(vm_1, direction='down', resource='cpu', fail_ok=True)
    expt_error = "Cpu 3 is already offline or out of range."
    assert code == 1, "CLI command was not rejected as expected. Exit code is {}, msg is {}".format(code, output)
    assert expt_error in output, "Error message incorrect: expected {} in output when output is {}"\
        .format(expt_error, output)
    GuestLogs.remove(vm_1)
