from pytest import fixture, mark
from time import sleep

from utils import table_parser, cli, exceptions
from utils.tis_log import LOG

from consts.auth import Tenant
from consts.cgcs import VMStatus, FlavorSpec, NetworkingVmMapping
from keywords import vm_helper, nova_helper, host_helper, glance_helper,system_helper,cinder_helper

from testfixtures.resource_mgmt import ResourceCleanup


def wrl_images_not_exist():
    "Return True if there are no image called wrl5-avp or wrl5-virtio"
    wrl5_avp_id = glance_helper.get_image_id_from_name('wrl5-avp')
    wrl5_virtio_id = glance_helper.get_image_id_from_name('wrl5-virtio')
    return not wrl5_avp_id or not wrl5_virtio_id


@mark.skipif(wrl_images_not_exist(), reason="There are no image called wrl5-avp or wrl5-virtio in Lab")
@mark.sanity
@mark.parametrize(('vm_name', 'image_name'), [
    mark.p1(('test-wrl-avp-1', 'wrl5-avp')),
    mark.p1(('test-wrl-virtio-0', 'wrl5-virtio')),
])
def test_attach_cinder_volume_to_instance(vm_name,image_name):
    """
    Validate that cinder volume can be attached to VM created using wrl5_avp and wrl5_virtio image

    Args:
        None
    Setup:
        - Standard 4 blade config: 2 controllers + 2 compute
        - Lab booted and configure step complete

    Test Steps:
        - Boot cinder volume
        - Boot VM use WRL image
        - Attach cinder volume to WRL virtuo/avp instance

    Teardown:
        - Delete VM
        - Delete cinder volume
    """

    # the test will be skipped if it cannot find the expected image to be load to the vm

    LOG.tc_step("Boot up VM from image {} that was setup by default".format(image_name))
    sourceid = glance_helper.get_image_id_from_name(image_name)
    vm_id = vm_helper.boot_vm(name = vm_name, source = 'image',source_id = sourceid)[1]

    # added to resource mangement for vm teardown
    ResourceCleanup.add('vm', vm_id)

    LOG.tc_step("create cinder volume")
    volume_id = cinder_helper.create_volume(name='wrl-cinder')[1]
    # added to resource mangement for volume teardown
    ResourceCleanup.add('volume', volume_id)

    # boot a cinder volume and attached it to vm
    LOG.tc_step("Attach cinder Volume to VM")
    vm_helper.attach_vol_to_vm(vm_id,vol_id = volume_id)
    # teardown: delete vm and volume will happen automatically


