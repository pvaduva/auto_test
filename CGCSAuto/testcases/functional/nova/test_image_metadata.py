import random
from pytest import fixture, mark
from utils.tis_log import LOG
from consts.cgcs import ImageMetadata
from keywords import nova_helper, glance_helper
from testfixtures.resource_mgmt import ResourceCleanup


@mark.parametrize(('property_key', 'values', 'disk_format', 'container_format'), [
    mark.p2((ImageMetadata.AUTO_RECOVERRY, [random.choice(['true', 'false']), random.choice(['True', 'False']),
                                            random.choice(['TRUE', 'FALSE']), random.choice(['TruE', 'faLSe'])],
             'qcow2', 'bare')),
    mark.p2((ImageMetadata.AUTO_RECOVERRY, [random.choice(['true', 'false']), random.choice(['True', 'False']),
                                            random.choice(['TRUE', 'FALSE']), random.choice(['TruE', 'faLSe'])],
             'raw', 'bare')),
])
def test_create_image_with_metadata(property_key, values, disk_format, container_format):
    """
    Create image with given metadata/property.

    Args:
        property_key (str): the key for the property, such as sw_wrs_auto_recovery
        values (list): list of values to test for the specific key
        disk_format (str): such as 'raw', 'qcow2'
        container_format (str): such as bare

    Test Steps;
        - Create image with given disk format, container format, property key and value pair
        - Verify property value is correctly set via glance image-show

    Teardown:
        - Delete created images

    """
    for value in values:
        LOG.tc_step("Creating image with property {}={}, disk_format={}, container_format={}".
                    format(property_key, value, disk_format, container_format))
        image_id = glance_helper.create_image(disk_format=disk_format, container_format=container_format,
                                              **{property_key: value})[1]
        ResourceCleanup.add('image', resource_id=image_id)

        LOG.tc_step("Verify image property is set correctly via glance image-show.")
        actual_property_val = glance_helper.get_image_properties(image_id, property_key)[property_key]
        assert value.lower() == actual_property_val.lower(), \
            "Actual image property {} value - {} is different than set value - {}".format(
                    property_key, actual_property_val, value)
