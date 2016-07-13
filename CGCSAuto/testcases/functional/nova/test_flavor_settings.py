from pytest import fixture, mark
from utils.tis_log import LOG
from consts.cgcs import FlavorSpec
from keywords import nova_helper
from testfixtures.resource_mgmt import ResourceCleanup


@fixture(scope='module', autouse=True)
def flavor_to_test():
    flavor_id = nova_helper.create_flavor(check_storage_backing=False)[1]
    ResourceCleanup.add('flavor', flavor_id, scope='module')

    return flavor_id


def test_flavor_default_specs():
    """
    Test "aggregate_instance_extra_specs:storage": "local_image" is by default included in newly created flavor

    Test Steps:
       - Create a new flavor
       - Check "aggregate_instance_extra_specs:storage": "local_image" is included in extra specs of the flavor
    """
    LOG.tc_step("Create flavor with minimal input.")
    flavor = nova_helper.create_flavor(check_storage_backing=False)[1]
    ResourceCleanup.add('flavor', flavor)

    extra_specs = nova_helper.get_flavor_extra_specs(flavor=flavor)
    expected_spec = '"aggregate_instance_extra_specs:storage": "local_image"'
    LOG.tc_step("Check local_image storage is by default included in flavor extra specs")
    assert extra_specs["aggregate_instance_extra_specs:storage"] == 'local_image', \
        "Flavor {} extra specs does not include: {}".format(flavor, expected_spec)


def obsolete_test_flavor_set_storage(flavor_to_test):
    """
    Test set flavor storage specs

    Test Steps:
        - Set flavor storage spec to local_lvm and check it is set successfully
        - Set flavor storage spec to remote and check it is set successfully
        - Set flavor storage spec to local_image and check it is set successfully

    """
    LOG.tc_step("Set flavor storage spec to local_lvm and check it is set successfully")
    local_lvm_spec = {"aggregate_instance_extra_specs:storage": "local_lvm"}
    nova_helper.set_flavor_extra_specs(flavor=flavor_to_test, **local_lvm_spec)
    extra_spec_storage_1 = nova_helper.get_flavor_extra_specs(flavor=flavor_to_test)["aggregate_instance_extra_specs:storage"]
    assert extra_spec_storage_1 == 'local_lvm', "Actual storage spec: {}".format(extra_spec_storage_1)

    LOG.tc_step("Set flavor storage spec to remote and check it is set successfully")
    local_lvm_spec = {"aggregate_instance_extra_specs:storage": "remote"}
    nova_helper.set_flavor_extra_specs(flavor=flavor_to_test, **local_lvm_spec)
    extra_spec_storage_2 = nova_helper.get_flavor_extra_specs(flavor=flavor_to_test)["aggregate_instance_extra_specs:storage"]
    assert extra_spec_storage_2 == 'remote',  "Actual storage spec: {}".format(extra_spec_storage_2)

    LOG.tc_step("Set flavor storage spec to local_image and check it is set successfully")
    local_lvm_spec = {"aggregate_instance_extra_specs:storage": "local_image"}
    nova_helper.set_flavor_extra_specs(flavor=flavor_to_test, **local_lvm_spec)
    extra_spec_storage_3 = nova_helper.get_flavor_extra_specs(flavor=flavor_to_test)["aggregate_instance_extra_specs:storage"]
    assert extra_spec_storage_3 == 'local_image', "Actual storage spec: {}".format(extra_spec_storage_3)


@mark.parametrize(('extra_spec_name', 'values'), [
    ((FlavorSpec.STORAGE_BACKING, ['local_lvm', 'remote', 'local_image'])),
    ((FlavorSpec.VCPU_MODEL, ['Nehalem', 'SandyBridge', 'Westmere', 'Haswell'])),
    ((FlavorSpec.CPU_POLICY, ['dedicated', 'shared'])),
    ((FlavorSpec.NUMA_NODES, [1])),
    mark.p2((FlavorSpec.AUTO_RECOVERY, ['true', 'false', 'TRUE', 'FALSE'])),
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
        nova_helper.set_flavor_extra_specs(flavor=flavor_to_test, **extra_spec)

        post_extra_spec = nova_helper.get_flavor_extra_specs(flavor=flavor_to_test)
        assert post_extra_spec[extra_spec_name] == value, "Actual flavor extra specs: {}".format(post_extra_spec)

