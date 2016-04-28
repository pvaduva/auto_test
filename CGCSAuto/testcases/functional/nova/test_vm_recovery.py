from pytest import fixture, mark

from utils.tis_log import LOG
from consts.timeout import VMTimeout
from consts.cgcs import FlavorSpec, ImageMetadata, VMStatus
from keywords import nova_helper, vm_helper, host_helper, cinder_helper, glance_helper
from testfixtures.resource_mgmt import ResourceCleanup


@mark.parametrize(('auto_recovery', 'disk_format', 'container_format'), [
    mark.p1(('true', 'qcow2', 'bare')),
    mark.p1(('False', 'raw', 'bare')),
])
def test_image_metadata_in_volume(auto_recovery, disk_format, container_format):
    """
    Create image with given metadata/property.

    Args:
        auto_recovery (str): value for sw_wrs_auto_recovery to set in image
        disk_format (str): such as 'raw', 'qcow2'
        container_format (str): such as bare

    Test Steps;
        - Create image with given disk format, container format, property key and value pair
        - Verify property value is correctly set via glance image-show

    Teardown:
        - Delete created images

    """
    property_key = ImageMetadata.AUTO_RECOVERRY

    LOG.tc_step("Create an image with property auto_recovery={}, disk_format={}, container_format={}".
                format(auto_recovery, disk_format, container_format))
    image_id = glance_helper.create_image(disk_format=disk_format, container_format=container_format,
                                          **{property_key: auto_recovery})[1]
    ResourceCleanup.add('image', resource_id=image_id)

    LOG.tc_step("Create a volume from the image")
    vol_id = cinder_helper.create_volume(name='auto_recov', image_id=image_id, rtn_exist=False)[1]
    ResourceCleanup.add('volume', vol_id)

    LOG.tc_step("Verify image properties are shown in cinder list")
    field = 'volume_image_metadata'
    vol_image_metadata_dict = eval(cinder_helper.get_volume_states(vol_id=vol_id, fields=field)[field])
    LOG.info("vol_image_metadata dict: {}".format(vol_image_metadata_dict))

    assert auto_recovery.lower() == vol_image_metadata_dict[property_key].lower(), \
        "Actual volume image property {} value - {} is different than value set in image - {}".format(
                property_key, vol_image_metadata_dict[property_key], auto_recovery)

    assert disk_format == vol_image_metadata_dict['disk_format']
    assert container_format == vol_image_metadata_dict['container_format']


@mark.parametrize(('flavor_auto_recovery', 'image_auto_recovery', 'disk_format', 'container_format', 'expt_result'), [
    mark.p1((None, None, 'raw', 'bare', True)),
    mark.p1(('false', 'true', 'qcow2', 'bare', False)),
    mark.p1(('true', 'false', 'raw', 'bare', True)),
    mark.p1(('false', None, 'raw', 'bare', False)),
    mark.p1((None, 'False', 'qcow2', 'bare', False)),
])
def test_vm_auto_recovery_setting(flavor_auto_recovery, image_auto_recovery, disk_format, container_format, expt_result):
    """
    Test auto recovery setting in vm with various auto recovery settings in flavor and image.

    Args:
        flavor_auto_recovery (str|None): None (unset) or true or false
        image_auto_recovery (str|None): None (unset) or true or false
        disk_format (str):
        container_format (str):
        expt_result (bool): Expected vm auto recovery behavior. False > disabled, True > enabled.

    Test Steps:
        - Create a flavor with auto recovery set to given value in extra spec
        - Create an image with auto recovery set to given value in metadata
        - Create a volume from above image
        - Boot a vm with the flavor and from the volume
        - Set vm state to error via nova reset-state
        - Verify vm auto recovery behavior is as expected

    Teardown:
        - Delete created vm, volume, image, flavor

    """

    LOG.tc_step("Create a flavor with auto_recovery set to {} in extra spec".format(flavor_auto_recovery))
    flavor_id = nova_helper.create_flavor(name='auto_rev-'+str(flavor_auto_recovery))[1]
    ResourceCleanup.add('flavor', flavor_id)
    if flavor_auto_recovery is not None:
        nova_helper.set_flavor_extra_specs(flavor=flavor_id, **{FlavorSpec.AUTO_RECOVERY: flavor_auto_recovery})

    property_key = ImageMetadata.AUTO_RECOVERRY
    LOG.tc_step("Create an image with property auto_recovery={}, disk_format={}, container_format={}".
                format(image_auto_recovery, disk_format, container_format))
    if image_auto_recovery is None:
        image_id = glance_helper.create_image(disk_format=disk_format, container_format=container_format)[1]
    else:
        image_id = glance_helper.create_image(disk_format=disk_format, container_format=container_format,
                                              **{property_key: image_auto_recovery})[1]
    ResourceCleanup.add('image', resource_id=image_id)

    LOG.tc_step("Create a volume from the image")
    vol_id = cinder_helper.create_volume(name='auto_recov', image_id=image_id, rtn_exist=False)[1]
    ResourceCleanup.add('volume', vol_id)

    LOG.tc_step("Boot a vm from volume with auto recovery - {} and using the flavor with auto recovery - {}".format(
            image_auto_recovery, flavor_auto_recovery))
    vm_id = vm_helper.boot_vm(name='auto_recov', flavor=flavor_id, source='volume', source_id=vol_id)[1]
    ResourceCleanup.add('vm', vm_id, del_vm_vols=False)

    LOG.tc_step("Verify vm auto recovery is {} by setting vm to error state.".format(expt_result))
    vm_helper.set_vm_state(vm_id=vm_id, error_state=True, fail_ok=False)
    res_bool, actual_val = vm_helper.wait_for_vm_values(vm_id=vm_id, status=VMStatus.ACTIVE, fail_ok=True,
                                                        timeout=300)

    assert expt_result == res_bool, "Expected auto_recovery: {}. Actual vm status: {}".format(
            expt_result, actual_val)
