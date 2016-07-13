from pytest import mark, skip

from utils.tis_log import LOG

from keywords import vm_helper, glance_helper, cinder_helper

from testfixtures.resource_mgmt import ResourceCleanup


@mark.sanity
@mark.parametrize(('vm_name', 'image_name'), [
    ('test-wrl-avp-1', 'wrl5-avp'),
    ('test-wrl-virtio-0', 'wrl5-virtio'),
])
def test_attach_cinder_volume_to_instance(vm_name, image_name):
    """
    Validate that cinder volume can be attached to VM created using wrl5_avp and wrl5_virtio image

    Args:
        vm_name (str)
        image_name (str)

    Test Steps:
        - Create cinder volume
        - Boot VM use WRL image
        - Attach cinder volume to WRL virtuo/avp instance

    Teardown:
        - Delete VM
        - Delete cinder volume
    """

    # the test will be skipped if it cannot find the expected image to be load to the vm
    wrl5_id = glance_helper.get_image_id_from_name(image_name)
    if not wrl5_id:
        skip("No image named {} exists".format(image_name))

    LOG.tc_step("Boot up VM from image {} that was setup by default".format(image_name))
    sourceid = glance_helper.get_image_id_from_name(image_name)
    vm_id = vm_helper.boot_vm(name=vm_name, source='image', source_id=sourceid)[1]

    # added to resource mangement for vm teardown
    ResourceCleanup.add('vm', vm_id)

    LOG.tc_step("create cinder volume")
    volume_id = cinder_helper.create_volume(name='wrl-cinder')[1]
    # added to resource mangement for volume teardown
    ResourceCleanup.add('volume', volume_id)

    # boot a cinder volume and attached it to vm
    LOG.tc_step("Attach cinder Volume to VM")
    vm_helper.attach_vol_to_vm(vm_id,vol_id=volume_id)
    # teardown: delete vm and volume will happen automatically
