import re

from pytest import fixture, mark, param

from utils.tis_log import LOG
from consts.cgcs import FlavorSpec
from keywords import nova_helper


@fixture(scope='module', autouse=True)
def flavor_to_test():
    flavor_id = nova_helper.create_flavor(cleanup='module')[1]

    return flavor_id


@mark.p3
def test_flavor_default_specs():
    """
    Test "aggregate_instance_extra_specs:storage": "local_image" is by default included in newly created flavor

    Test Steps:
       - Create a new flavor
       - Check "aggregate_instance_extra_specs:storage": "local_image" is included in extra specs of the flavor
    """
    LOG.tc_step("Create flavor with minimal input.")
    flavor = nova_helper.create_flavor(cleanup='function', add_default_specs=False)[1]

    extra_specs = nova_helper.get_flavor_properties(flavor=flavor)
    LOG.tc_step("Check local_image storage is by default included in flavor extra specs")
    assert not extra_specs, "Flavor {} extra specs is not empty by default: {}".format(flavor, extra_specs)


@mark.parametrize(('extra_spec_name', 'values'), [
    # param(FlavorSpec.STORAGE_BACKING, ['remote', 'local_image'], marks=mark.p3),     # feature deprecated
    param(FlavorSpec.VCPU_MODEL, ['Nehalem', 'SandyBridge', 'Westmere', 'Haswell'], marks=mark.p3),
    param(FlavorSpec.CPU_POLICY, ['dedicated', 'shared'], marks=mark.p3),
    # param(FlavorSpec.NUMA_NODES, [1], marks=mark.p3),    # feature deprecated
    param(FlavorSpec.AUTO_RECOVERY, ['true', 'false', 'TRUE', 'FALSE'], marks=mark.p3),
])
def test_set_flavor_extra_specs(flavor_to_test, extra_spec_name, values):
    """
    Args:
        flavor_to_test:
        extra_spec_name:
        values:

    Setups:
        - Create a basic flavor

    Test Steps:
        - Set specific extra spec to given values for the basic flavor
        - Check extra spec is now included in the flavor

    Teardown:
        - Delete the basic flavor
    """
    for value in values:
        value = str(value)
        extra_spec = {extra_spec_name: value}

        LOG.tc_step("Set flavor extra spec to: {} and verify extra spec is set successfully.".format(extra_spec))
        nova_helper.set_flavor(flavor=flavor_to_test, **extra_spec)

        post_extra_spec = nova_helper.get_flavor_properties(flavor=flavor_to_test)
        assert post_extra_spec[extra_spec_name] == value, "Actual flavor extra specs: {}".format(post_extra_spec)


# Deprecated - flavor spec validation
# TC6497
def _test_create_flavor_with_excessive_vcpu_negative():

    """
    Test that flavor creation fails and sends a human-readable error message if a flavor with >128 vCPUs is attempted
    to be created.

    Test Steps:
       - Create a new flavor with 129 vCPUs
       - Check that create_flavor returns an error exit code and a proper readable output message is generated
    """

    # Create a flavor with over 128 vcpus
    vcpu_num = 129
    LOG.tc_step("Create flavor with over 128 vCPUs - {}".format(vcpu_num))
    exitcode, output = nova_helper.create_flavor(vcpus=129, fail_ok=True, cleanup='function')

    # Check if create_flavor returns erroneous exit code and error output is a proper human-readable message
    expt_err = "Invalid input .* vcpus.*{}.* is greater than the maximum of 128".format(vcpu_num)

    LOG.tc_step("Check flavor creation fails and proper error message displayed")

    assert 1 == exitcode
    assert re.search(expt_err, output), "\nExpected pattern:{}\nActual output: {}".format(expt_err, output)
