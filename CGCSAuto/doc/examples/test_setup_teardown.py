from pytest import fixture

from utils.tis_log import LOG
from keywords import nova_helper


@fixture()
def flavor_(request):
    # Create a flavor as test setup
    flavor_id = nova_helper.create_flavor()[1]
    
    # Test teardown function
    def delete():
        nova_helper.delete_flavors(flavor_id)
    # Add delete function to teardown
    request.addfinalizer(delete)
    
    # Pass the flavor_id to test function
    return flavor_id


def test_flavor_set_storage(flavor_):
    """
    Test set flavor storage specs
    
    Test Setup:
        - Create a flavor
    Test Steps:
        - Set flavor storage spec to local_lvm and check it is set successfully
        - Set flavor storage spec to local_image and check it is set successfully
    Test Teardown:
        - Delete the created flavor
    """
    storage_spec = "aggregate_instance_extra_specs:storage"
    
    LOG.tc_step("Set flavor storage spec to local_lvm and check it is set successfully")
    local_lvm_spec = {storage_spec: "local_lvm"}
    nova_helper.set_flavor_extra_specs(flavor=flavor_, **local_lvm_spec)
    extra_spec_storage_1 = nova_helper.get_flavor_extra_specs(flavor=flavor_)[storage_spec]
    assert extra_spec_storage_1 == 'local_lvm', "Actual storage spec: {}".format(extra_spec_storage_1)

    LOG.tc_step("Set flavor storage spec to local_image and check it is set successfully")
    local_lvm_spec = {storage_spec: "local_image"}
    nova_helper.set_flavor_extra_specs(flavor=flavor_, **local_lvm_spec)
    extra_spec_storage_2 = nova_helper.get_flavor_extra_specs(flavor=flavor_)[storage_spec]
    assert extra_spec_storage_2 == 'local_image', "Actual storage spec: {}".format(extra_spec_storage_2)
