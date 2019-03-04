import time
from keywords import glance_helper, cinder_helper, vm_helper
from consts.cgcs import ImageMetadata
from utils.tis_log import LOG


def test_db_purge():

    end_time = time.time() + 7200

    count = 1
    while time.time() < end_time:

        LOG.tc_step("Iteration-{}: Creating and deleting image, volume, vm".format(count))
        LOG.info("------ Creating image, volume, vm")
        image_id = glance_helper.create_image(name='glance-purge', cleanup='function',
                                              **{ImageMetadata.AUTO_RECOVERY: 'true'})[1]
        vol_id = cinder_helper.create_volume(name='cinder-purge', image_id=image_id)[1]
        vm_id = vm_helper.boot_vm(name='nova-purge', source='volume', source_id=vol_id)[1]

        time.sleep(60)

        LOG.info("------ Deleting vm, volume, image")
        vm_helper.delete_vms(vms=vm_id)
        cinder_helper.delete_volumes(volumes=vol_id)
        glance_helper.delete_images(images=image_id)

        time.sleep(60)
        count += 1
