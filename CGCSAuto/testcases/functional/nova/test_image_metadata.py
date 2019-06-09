import random
from pytest import mark, param
from utils.tis_log import LOG
from consts.cgcs import ImageMetadata
from keywords import glance_helper


@mark.parametrize(('property_key', 'values', 'disk_format', 'container_format'), [
    param(ImageMetadata.AUTO_RECOVERY, [random.choice(['true', 'false']), random.choice(['True', 'False']),
                                        random.choice(['TRUE', 'FALSE']), random.choice(['TruE', 'faLSe'])],
          'qcow2', 'bare', marks=mark.p3),
    param(ImageMetadata.AUTO_RECOVERY, [random.choice(['true', 'false']), random.choice(['True', 'False']),
                                        random.choice(['TRUE', 'FALSE']), random.choice(['TruE', 'faLSe'])],
          'raw', 'bare', marks=mark.p3),
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
                                              cleanup='function', **{property_key: value})[1]

        LOG.tc_step("Verify image property is set correctly via glance image-show.")
        actual_property_val = glance_helper.get_image_properties(image_id, property_key)[0]
        assert value.lower() == actual_property_val.lower(), \
            "Actual image property {} value - {} is different than set value - {}".format(
                    property_key, actual_property_val, value)
