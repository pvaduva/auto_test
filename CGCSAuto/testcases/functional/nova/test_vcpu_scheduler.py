from pytest import mark

from utils.tis_log import LOG

from consts.cgcs import FlavorSpec
from consts.cli_errs import VCPUSchedulerErr
from keywords import nova_helper, vm_helper, host_helper
from testfixtures.resource_mgmt import ResourceCleanup


@mark.parametrize(('vcpu_num', 'vcpu_schedulers'), [
    mark.p2((4, ["fifo:98:3;fifo:99:1;rr:1:2", "fifo:98:3;fifo:99:1;fifo:97:2"])),
    mark.p1((2, ["fifo:9:1", "rr:19:1", "other:2:1"])),
])
def test_flavor_vcpu_scheduler_valid(vcpu_num, vcpu_schedulers):
    """
    Test valid settings of vcpu scheduler flavor specs.

    Args:
        vcpu_num (int): number of vcpus to set when creating flavor
        vcpu_schedulers (list|str): vpu schedulers to set in flavor extra specs

    Test Steps:
        - Create a flavor with given number of vcpus
        - Set vcpu_scheduler extra specs to given values
        - Check vcpu_scheduler setting is included in the flavor

    Teardown:
        - Delete flavor
    """
    LOG.tc_step("Create flavor with {} vcpus".format(vcpu_num))
    flavor_id = nova_helper.create_flavor('vcpu_scheduler_valid', vcpus=vcpu_num)[1]
    ResourceCleanup.add('flavor', flavor_id)

    if isinstance(vcpu_schedulers, str):
        vcpu_schedulers = [vcpu_schedulers]

    for vcpu_scheduler in vcpu_schedulers:
        vcpu_scheduler = '''"{}"'''.format(vcpu_scheduler)
        extra_spec = {FlavorSpec.VCPU_SCHEDULER: vcpu_scheduler}

        LOG.tc_step("Set flavor extra spec to: {} and verify extra spec is set successfully.".format(extra_spec))
        nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_spec)

        post_extra_spec = nova_helper.get_flavor_extra_specs(flavor=flavor_id)
        assert post_extra_spec[FlavorSpec.VCPU_SCHEDULER] == eval(vcpu_scheduler), "Actual flavor extra specs: {}".\
            format(post_extra_spec)

def id_gen(val):
    if isinstance(val, list):
        val = '-'.join(val)
    return val.replace(";", "_")

@mark.parametrize(('vcpu_num', 'vcpu_schedulers', 'expected_err'), [
    mark.p2((1, "fifo:9:1", None)),    # CGTS-2462
    mark.p2((4, ["fifo:20:1;rr:4-6:4", "fifo:20:1;rr:6:4"], "VCPU_VAL_OUT_OF_RANGE")),
    mark.p2((3, ["fifo:20:1;rr:-1:2"], "INVALID_PRIORITY")),
    mark.p3((3, "fifo:20:1;rr:10:0", "CANNOT_SET_VCPU0")),
    mark.p3((4, ["fifo:20:1;rr:4-6:2", "fifo:20:1;rr:4-6", "fifo:"], "PRIORITY_NOT_INTEGER")),
    mark.p3((3, "fifo:20:1;rr:4-6:3'", "INVALID_FORMAT")),
    mark.p3((3, "fifo:20:1;roarr:10:2", "UNSUPPORTED_POLICY")),
    mark.p3((3, "fifo:20;rr:10:1", "POLICY_MUST_SPECIFIED_LAST")),
    mark.p3((3, "fifo", "MISSING_PARAMETER")),
    mark.p3((3, "fifo:20:1_roarr:10", "TOO_MANY_PARAMETERS")),
    mark.p3((3, "fifo:20:1;roarr:10:1", "VCPU_MULTIPLE_ASSIGNMENT")),
], ids=id_gen)
def test_flavor_vcpu_scheduler_invalid(vcpu_num, vcpu_schedulers, expected_err):
    """
    Test invalid settings of vcpu scheduler flavor specs.

    Args:
        vcpu_num (int): number of vcpus to set when creating flavor
        vcpu_schedulers (list|str): vpu schedulers to set in flavor extra specs

    Test Steps:
        - Create a flavor with given number of vcpus
        - Attempt to set vcpu_scheduler extra specs to given invalid values
        - Check cli is rejected with valid reason
    Teardown:
        - Delete flavor
    """
    LOG.tc_step("Create flavor with {} vcpus".format(vcpu_num))
    flavor_id = nova_helper.create_flavor('vcpu_scheduler_invalid', vcpus=vcpu_num)[1]
    ResourceCleanup.add('flavor', flavor_id)

    if isinstance(vcpu_schedulers, str):
        vcpu_schedulers = [vcpu_schedulers]

    for vcpu_scheduler in vcpu_schedulers:
        vcpu_scheduler = '''"{}"'''.format(vcpu_scheduler)
        extra_spec = {FlavorSpec.VCPU_SCHEDULER: vcpu_scheduler}

        LOG.tc_step("Attempt to set vcpu_scheduler to invalid value - {} in extra specs, and verify it is rejected".
                    format(vcpu_scheduler))
        code, output = nova_helper.set_flavor_extra_specs(flavor=flavor_id, fail_ok=True, **extra_spec)

        assert 1 == code, "Set flavor extra spec request is not rejected."

        if expected_err:
            assert eval("VCPUSchedulerErr." + expected_err) in output, "Expected error string is not found in CLI output."


@mark.parametrize(('vcpu_num', 'vcpu_scheduler'), [
    # Note: Don't use same priority number for different vcpus in one testcase. e.g., Don't: "fifo:66:1;rr:66:2"
    mark.sanity((2, "fifo:99:1")),
    mark.p1((3, "fifo:3:1;rr:1:2"))
])
def test_boot_vm_vcpu_scheduler(vcpu_num, vcpu_scheduler):
    """
    Test that vm is created with the expected VCPU Scheduler Policy settings using the virsh command

    Args:
        vcpu_num (int):
        vcpu_scheduler (str):

    Test Steps:
        - Create a flavor with given number of vcpus
        - Set flavor extra specs with given vcpu_scheduler setting
        - Boot a vm with above flavor
        - Verify vm is created with the expected VCPU Scheduler Policy settings via virsh command on nova host
        - Verify vm vcpu policy and priority in real-time process attributes via chrt cmd
    Teardowns;
        - Delete created vm
        - Delete created flavor
    """
    LOG.tc_step("Create flavor with {} vcpus".format(vcpu_num))
    flavor_id = nova_helper.create_flavor('vcpu_scheduler', vcpus=vcpu_num)[1]
    ResourceCleanup.add('flavor', flavor_id)

    LOG.tc_step("Set flavor vcpu_scheduler spec to: {}".format(vcpu_scheduler))
    vcpu_scheduler_flavor = '''"{}"'''.format(vcpu_scheduler)
    extra_spec = {FlavorSpec.VCPU_SCHEDULER: vcpu_scheduler_flavor}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_spec)

    LOG.tc_step("Boot a vm with above flavor.")
    vm_id = vm_helper.boot_vm(flavor=flavor_id)[1]
    ResourceCleanup.add('vm', vm_id)

    instance_name, host = nova_helper.get_vm_nova_show_values(vm_id, fields=[":instance_name", ":host"], strict=False)

    with host_helper.ssh_to_host(host) as host_ssh:
        actual_vcpus = host_helper.get_values_virsh_xmldump(instance_name, host_ssh, 'cputune/vcpupin',
                                                            target_type='dict')
        vm_pid = vm_helper.get_vm_pid(instance_name, host_ssh)

        vcpus_scheduler = vcpu_scheduler.split(sep=';')
        for item in vcpus_scheduler:
            expt_policy, expt_priority, expt_vcpu_id = item.split(':')
            LOG.tc_step("Check vcpu {} has policy set to {} and priority set to {} for vm {} via virsh cmd".format(
                        expt_vcpu_id, expt_policy, expt_priority, vm_id))

            for actual_vcpu_dict in actual_vcpus:
                if expt_vcpu_id == actual_vcpu_dict['vcpu']:
                    assert expt_policy == actual_vcpu_dict['policy'], "CPU policy for vcpu {} does not match the " \
                                                                      "setting".format(expt_vcpu_id)
                    assert expt_priority == actual_vcpu_dict['priority'], "Priority for vcpu {} does not match the " \
                                                                          "setting".format(expt_vcpu_id)
                    break

            LOG.tc_step("Check vcpu policy and priority in real-time process attributes via chrt cmd")
            code, output = host_ssh.exec_sudo_cmd('''chrt -ap {} | grep --color='never' -B1 "priority: {}$"'''.
                                                  format(vm_pid, expt_priority))
            assert 0 == code, "Expected priority {} is not found in chrt output".format(expt_priority)

            expt_policy_in_chrt = "SCHED_{}".format(expt_policy.upper())
            assert expt_policy_in_chrt in output, "Expected policy string {} is not found with priority {}".format(
                    expt_policy_in_chrt, expt_priority)