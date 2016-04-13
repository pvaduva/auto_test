from pytest import fixture, mark
from utils.tis_log import LOG
from keywords import nova_helper

created_flavors = []
@fixture(scope='module', autouse=True)
def delete_created_flavors(request):
    def delete():
        if created_flavors:
            nova_helper.delete_flavors(created_flavors)
    request.addfinalizer(delete)


def test_flavor_default_specs():
    """
    Test "aggregate_instance_extra_specs:storage": "local_image" is by default included in newly created flavor

    Test Steps:
       - Create a new flavor
       - Check "aggregate_instance_extra_specs:storage": "local_image" is included in extra specs of the flavor
    """
    LOG.tc_step("Create flavor with minimal input.")
    flavor = nova_helper.create_flavor()[1]
    created_flavors.append(flavor)
    extra_specs = nova_helper.get_flavor_extra_specs(flavor=flavor)
    expected_spec = '"aggregate_instance_extra_specs:storage": "local_image"'
    LOG.tc_step("Check local_image storage is by default included in flavor extra specs")
    assert extra_specs["aggregate_instance_extra_specs:storage"] == 'local_image', \
        "Flavor {} extra specs does not include: {}".format(flavor, expected_spec)


def test_flavor_set_storage():
    """
    Test set flavor storage specs

    Test Steps:
        - Set flavor storage spec to local_lvm and check it is set successfully
        - Set flavor storage spec to remote and check it is set successfully
        - Set flavor storage spec to local_image and check it is set successfully

    """
    LOG.tc_step("Create basic flavor.")
    flavor = nova_helper.create_flavor()[1]
    created_flavors.append(flavor)
    LOG.tc_step("Set flavor storage spec to local_lvm and check it is set successfully")
    local_lvm_spec = {"aggregate_instance_extra_specs:storage": "local_lvm"}
    nova_helper.set_flavor_extra_specs(flavor=flavor, **local_lvm_spec)
    extra_spec_storage_1 = nova_helper.get_flavor_extra_specs(flavor=flavor)["aggregate_instance_extra_specs:storage"]
    assert extra_spec_storage_1 == 'local_lvm', "Actual storage spec: {}".format(extra_spec_storage_1)

    LOG.tc_step("Set flavor storage spec to remote and check it is set successfully")
    local_lvm_spec = {"aggregate_instance_extra_specs:storage": "remote"}
    nova_helper.set_flavor_extra_specs(flavor=flavor, **local_lvm_spec)
    extra_spec_storage_2 = nova_helper.get_flavor_extra_specs(flavor=flavor)["aggregate_instance_extra_specs:storage"]
    assert extra_spec_storage_2 == 'remote',  "Actual storage spec: {}".format(extra_spec_storage_2)

    LOG.tc_step("Set flavor storage spec to local_image and check it is set successfully")
    local_lvm_spec = {"aggregate_instance_extra_specs:storage": "local_image"}
    nova_helper.set_flavor_extra_specs(flavor=flavor, **local_lvm_spec)
    extra_spec_storage_3 = nova_helper.get_flavor_extra_specs(flavor=flavor)["aggregate_instance_extra_specs:storage"]
    assert extra_spec_storage_3 == 'local_image', "Actual storage spec: {}".format(extra_spec_storage_3)
