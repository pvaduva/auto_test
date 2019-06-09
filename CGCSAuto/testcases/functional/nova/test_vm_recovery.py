from pytest import mark, param

from consts.cgcs import FlavorSpec, ImageMetadata, VMStatus
from consts.feature_marks import Features
from keywords import nova_helper, vm_helper, cinder_helper, glance_helper
from utils.tis_log import LOG


# Note auto recovery metadata in image will not passed to vm if vm is booted from Volume
@mark.features(Features.AUTO_RECOV)
@mark.parametrize(('auto_recovery', 'disk_format', 'container_format'), [
    # param('true', 'qcow2', 'bare'),   # default guest image is in raw format. This test now fails in pike.
    param('False', 'raw', 'bare', marks=mark.p3),
])
def test_autorecovery_image_metadata_in_volume(auto_recovery, disk_format, container_format):
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
    property_key = ImageMetadata.AUTO_RECOVERY

    LOG.tc_step("Create an image with property auto_recovery={}, disk_format={}, container_format={}".
                format(auto_recovery, disk_format, container_format))
    image_id = glance_helper.create_image(disk_format=disk_format, container_format=container_format,
                                          cleanup='function', **{property_key: auto_recovery})[1]

    LOG.tc_step("Create a volume from the image")
    vol_id = cinder_helper.create_volume(name='auto_recov', source_id=image_id, cleanup='function')[1]

    LOG.tc_step("Verify image properties are shown in cinder list")
    field = 'volume_image_metadata'
    vol_image_metadata_dict = cinder_helper.get_volume_show_values(vol_id, fields=field)[0]
    LOG.info("vol_image_metadata dict: {}".format(vol_image_metadata_dict))

    assert auto_recovery.lower() == vol_image_metadata_dict[property_key].lower(), \
        "Actual volume image property {} value - {} is different than value set in image - {}".format(
                property_key, vol_image_metadata_dict[property_key], auto_recovery)

    assert disk_format == vol_image_metadata_dict['disk_format']
    assert container_format == vol_image_metadata_dict['container_format']


@mark.features(Features.AUTO_RECOV)
@mark.parametrize(('cpu_policy', 'flavor_auto_recovery', 'image_auto_recovery', 'disk_format', 'container_format', 'expt_result'), [
    param(None, None, None, 'raw', 'bare', True, marks=mark.p1),
    param(None, 'false', 'true', 'qcow2', 'bare', False, marks=mark.p3),
    param(None, 'true', 'false', 'raw', 'bare', True, marks=mark.p3),
    param('dedicated', 'false', None, 'raw', 'bare', False, marks=mark.p3),
    param('dedicated', None, 'false', 'qcow2', 'bare', False, marks=mark.domain_sanity),
    param('shared', None, 'true', 'raw', 'bare', True, marks=mark.p3),
    param('shared', 'false', None, 'raw', 'bare', False, marks=mark.p3),
])
def test_vm_autorecovery(cpu_policy, flavor_auto_recovery, image_auto_recovery, disk_format,
                                           container_format, expt_result):
    """
    Test auto recovery setting in vm with various auto recovery settings in flavor and image.

    Args:
        cpu_policy (str|None): cpu policy to set in flavor
        flavor_auto_recovery (str|None): None (unset) or true or false
        image_auto_recovery (str|None): None (unset) or true or false
        disk_format (str):
        container_format (str):
        expt_result (bool): Expected vm auto recovery behavior. False > disabled, True > enabled.

    Test Steps:
        - Create a flavor with auto recovery and cpu policy set to given values in extra spec
        - Create an image with auto recovery set to given value in metadata
        - Boot a vm with the flavor and from the image
        - Set vm state to error via nova reset-state
        - Verify vm auto recovery behavior is as expected

    Teardown:
        - Delete created vm, volume, image, flavor

    """

    LOG.tc_step("Create a flavor with cpu_policy set to {} and auto_recovery set to {} in extra spec".format(
            cpu_policy, flavor_auto_recovery))
    flavor_id = nova_helper.create_flavor(name='auto_recover_'+str(flavor_auto_recovery), cleanup='function')[1]

    # Add extra specs as specified
    extra_specs = {}
    if cpu_policy is not None:
        extra_specs[FlavorSpec.CPU_POLICY] = cpu_policy
    if flavor_auto_recovery is not None:
        extra_specs[FlavorSpec.AUTO_RECOVERY] = flavor_auto_recovery

    if extra_specs:
        nova_helper.set_flavor(flavor=flavor_id, **extra_specs)

    property_key = ImageMetadata.AUTO_RECOVERY
    LOG.tc_step("Create an image with property auto_recovery={}, disk_format={}, container_format={}".
                format(image_auto_recovery, disk_format, container_format))
    if image_auto_recovery is None:
        image_id = glance_helper.create_image(disk_format=disk_format, container_format=container_format,
                                              cleanup='function')[1]
    else:
        image_id = glance_helper.create_image(disk_format=disk_format, container_format=container_format,
                                              cleanup='function', **{property_key: image_auto_recovery})[1]

    # auto recovery in image metadata will not work if vm booted from volume
    # LOG.tc_step("Create a volume from the image")
    # vol_id = cinder_helper.create_volume(name='auto_recov', image_id=image_id, rtn_exist=False)[1]
    # ResourceCleanup.add('volume', vol_id)

    LOG.tc_step("Boot a vm from image with auto recovery - {} and using the flavor with auto recovery - {}".format(
                image_auto_recovery, flavor_auto_recovery))
    vm_id = vm_helper.boot_vm(name='auto_recov', flavor=flavor_id, source='image', source_id=image_id,
                              cleanup='function')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    LOG.tc_step("Verify vm auto recovery is {} by setting vm to error state.".format(expt_result))
    vm_helper.set_vm_state(vm_id=vm_id, error_state=True, fail_ok=False)
    res_bool, actual_val = vm_helper.wait_for_vm_values(vm_id=vm_id, status=VMStatus.ACTIVE, fail_ok=True,
                                                        timeout=600)

    assert expt_result == res_bool, "Expected auto_recovery: {}. Actual vm status: {}".format(
            expt_result, actual_val)

    LOG.tc_step("Ensure vm is pingable after auto recovery")
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
