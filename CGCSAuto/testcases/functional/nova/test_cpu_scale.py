from pytest import mark

from utils.tis_log import LOG

from consts.cgcs import FlavorSpec
from consts.cli_errs import MinCPUErr
from keywords import nova_helper, vm_helper, host_helper
from testfixtures.resource_mgmt import ResourceCleanup


@mark.parametrize(('vcpu_num', 'cpu_policy', 'min_vcpus', 'expected_err'), [
    mark.p2((1, 'dedicated', 2, MinCPUErr.VAL_LARGER_THAN_VCPUS)),
    mark.p3((1, 'dedicated', [0, -1], MinCPUErr.VAL_LESS_THAN_1)),
    mark.p3((2, 'shared', 1, MinCPUErr.CPU_POLICY_NOT_DEDICATED)),
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
            assert expected_err in output, "Expected error string is not found in CLI output."
