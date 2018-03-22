import math
from pytest import mark, skip, fixture
from utils import cli
from utils.tis_log import LOG
from utils.ssh import ControllerClient
from consts.cgcs import ImageStatus
from keywords import vm_helper, nova_helper, glance_helper, cinder_helper
from testfixtures.fixture_resources import ResourceCleanup


def test_create_snapshot_using_boot_from_image_vm():
    """
    This test creates a snapshot from a VM that is booted from image using
    nova image-create.  Nova image-create will create a glance image that can
    be used to boot a VM.

    Assumptions:
    * There are so images available on the system

    Test Steps:
    1.  Boot a vm from image
    2.  Run nova image-create <vm-id> <name> to save a snapshot of a vm in the
        form of a glance image
    3.  Run glance image-download --file <snapshot-img-filename> <snapshot-img-uuid> to download the snapshot image
    4.  Delete the downloaded image
    5.  Boot a VM using the snapshot that was created
   
    Teardown:
    1.  Delete VMs
    2.  Delete snapshots in the form a glance image
    """

    con_ssh = ControllerClient.get_active_controller()

    LOG.tc_step("Boot a VM from image")
    vm_id = vm_helper.boot_vm(source="image", cleanup='function')[1]
    assert vm_id, "Failed to boot VM"
    vm_name = nova_helper.get_vm_name_from_id(vm_id)
    snapshot_name = vm_name + "_snapshot"

    # nova image-create generates a glance image
    LOG.tc_step("Create a snapshot based on that VM")
    cmd = "image-create {} {}".format(vm_id, snapshot_name)
    cli.nova(cmd, ssh_client=con_ssh, rtn_list=True, fail_ok=False)
    # exception will be thrown if nova cmd rejected
    image_id = glance_helper.get_image_id_from_name(name=snapshot_name, strict=True, fail_ok=False)
    ResourceCleanup.add('image', image_id)

    LOG.tc_step("Wait for the snapshot to become active")
    glance_helper.wait_for_image_states(image_id, status=ImageStatus.ACTIVE)

    image_filename = '/home/wrsroot/images/temp'
    LOG.tc_step("Download the image snapshot")
    cmd = "image-download --file {} {}".format(image_filename, image_id)
    # Throw exception if glance cmd rejected
    cli.glance(cmd, ssh_client=con_ssh, fail_ok=False)

    # Downloading should be good enough for validation.  If the file is
    # zero-size, download will report failure.
    LOG.tc_step("Delete the downloaded image")
    con_ssh.exec_cmd("rm {}".format(image_filename), fail_ok=False)

    # Second form of validation is to boot a VM from the snapshot
    LOG.tc_step("Boot a VM from snapshot")
    snapshot_vm = "from_" + snapshot_name
    vm_helper.boot_vm(name=snapshot_vm, source="image", source_id=image_id, cleanup='function', fail_ok=False)


def test_create_snapshot_using_boot_from_volume_vm():
    """
    This test creates a snapshot from a VM that is booted from volume using
    nova image-create.  Nova image-create will create a glance image that can
    be used to boot a VM, but the snapshot seen in glance will be empty, since
    the real image is stored in cinder.

    Test Steps:
    1.  Run cinder create --image <img-uuid> --size <size> <bootable_vol>
    2.  Boot a VM using the bootable volume
    3.  Run nova image-create <vm-id> <name> to save a snapshot of the vm
    4.  Run cinder snapshot-list to list the snapshot of the VM
    5.  Run cinder create --snapshot-id <snapshot-from-VM> --name <vol-name>
<size>
    6.  Run cinder upload-to-image <vol-uuid> <image-name> to create a image
    7.  Glance image-download to download the snapshot.

    Teardown:
    1.  Delete VMs
    2.  Delete volumes
    3.  Delete snapshots

    Possible Improvements:
    1.  Could update test to use non-raw images, but determining size of of
    image is more complex if the original file is no longer on the filesystem.
    """

    con_ssh = ControllerClient.get_active_controller()

    LOG.tc_step("Get available images")
    image_list = glance_helper.get_images()

    if len(image_list) == 0:
        skip("The test requires some images to be present")

    # Filter out zero-sized images and non-raw images (latter is lazy)
    for image in image_list:
        image_uuid = image
        image_prop_s = glance_helper.get_image_properties(image_uuid, "size")
        image_prop_d = glance_helper.get_image_properties(image_uuid, "disk_format")
        if image_prop_s['size'] == "0" or image_prop_d['disk_format'] != "raw":
            continue
        else:
            divisor = 1024 * 1024 * 1024
            image_size = int(image_prop_s['size'])
            vol_size = int(math.ceil(image_size / divisor))
            break
    else:
        skip("No usable images found")

    LOG.tc_step("Create a cinder bootable volume")
    vol_id = cinder_helper.create_volume(image_id=image_uuid, size=vol_size, fail_ok=False)[1]
    ResourceCleanup.add('volume', vol_id)

    LOG.tc_step("Boot VM using newly created bootable volume")
    vm_id = vm_helper.boot_vm(source="volume", source_id=vol_id, cleanup='function')[1]
    vm_name = nova_helper.get_vm_name_from_id(vm_id)
    snapshot_name = vm_name + "_snapshot"

    # nova image-create generates a glance image of 0 size
    # real snapshot is stored in cinder
    LOG.tc_step("Create a snapshot based on that VM")
    cmd = "image-create {} {}".format(vm_id, snapshot_name)
    cli.nova(cmd, ssh_client=con_ssh, rtn_list=True, fail_ok=False)
    image_id = glance_helper.get_image_id_from_name(name=snapshot_name)
    ResourceCleanup.add('image', image_id)

    LOG.tc_step("Wait for the snapshot to become active")
    glance_helper.wait_for_image_states(image_id, status=ImageStatus.ACTIVE, fail_ok=False)

    cinder_snapshotname = "snapshot for {}".format(snapshot_name)
    LOG.tc_step("Get snapshot ID of {}".format(cinder_snapshotname))
    snapshot_id = cinder_helper.get_snapshot_id(name=cinder_snapshotname)
    assert snapshot_id, "Snapshot was not found"
    ResourceCleanup.add('vol_snapshot', snapshot_id)
    vol_name = "vol_from_snapshot"

    # Creates volume from snapshot
    LOG.tc_step("Create cinder snapshot")
    snapshot_vol_id = cinder_helper.create_volume(name=vol_name, snapshot_id=snapshot_id, cleanup='function')[1]

    # Creates an image
    LOG.tc_step("Upload cinder volume to image")
    image_name = "cinder_upload"
    cmd = "upload-to-image {} {}".format(snapshot_vol_id, image_name)
    rc, out = cli.cinder(cmd, ssh_client=con_ssh, rtn_list=True)
    assert rc == 0, "Upload of volume to image failed"
    image_id = glance_helper.get_image_id_from_name(name=cinder_snapshotname)
    ResourceCleanup.add('image', image_id)
    print("Uploading volume to image {}".format(image_id))

    LOG.tc_step("Wait for the uploaded image to become active")
    image_id = glance_helper.get_image_id_from_name(name=image_name)
    ResourceCleanup.add('image', image_id)
    glance_helper.wait_for_image_states(image_id, status=ImageStatus.SAVING, fail_ok=True, timeout=30)
    glance_helper.wait_for_image_states(image_id, status=ImageStatus.ACTIVE, fail_ok=False, timeout=120)
    print("Waiting for {} to be active".format(image_id))

    image_filename = '/home/wrsroot/images/temp'
    LOG.tc_step("Download the image snapshot")
    image_id = glance_helper.get_image_id_from_name(name=snapshot_name)
    cmd = "image-download --file {} {}".format(image_filename, image_id)
    cli.glance(cmd, ssh_client=con_ssh, fail_ok=False)

    # Downloading should be good enough for validation.  If the file is
    # zero-size, download will report failure.
    LOG.tc_step("Delete the downloaded image")
    con_ssh.exec_cmd("rm {}".format(image_filename), fail_ok=False)


def test_attempt_to_delete_volume_associated_with_snapshot():
    """
    This is a negative test to verify that volumes with associated snapshots
    cannot be deleted.

    Test Steps:
    1.  Create a volume
    2.  Launch a VM with that volume
    3.  Create a snapshot based on that VM
    4.  Delete the VM, leaving behind the volume and snapshot
    5.  Attempt to delete volume.  Rejeted.
    6.  Delete the snapshot.
    7.  Delete the volume.

    Teardown:
    1.  Delete VMs
    2.  Delete volumes
    3.  Delete snapshots
    4.  Delete images

    Possible Improvements:
    1.  Could update test to use non-raw images, but determining size of of
    image is more complex if the original file is no longer on the filesystem.
    """

    con_ssh = ControllerClient.get_active_controller()

    LOG.tc_step("Get available images")
    image_list = glance_helper.get_images()

    if len(image_list) == 0:
        skip("The test requires some images to be present")

    # Filter out zero-sized images and non-raw images (latter is lazy)
    for image in image_list:
        image_uuid = image
        image_prop_s = glance_helper.get_image_properties(image_uuid, "size")
        image_prop_d = glance_helper.get_image_properties(image_uuid, "disk_format")
        if image_prop_s['size'] == "0" or image_prop_d['disk_format'] != "raw":
            continue
        else:
            divisor = 1024 * 1024 * 1024
            image_size = int(image_prop_s['size'])
            vol_size = int(math.ceil(image_size / divisor))
            break

    else:
        skip("No usable images found")

    LOG.tc_step("Create a cinder bootable volume")
    vol_id = cinder_helper.create_volume(image_id=image_uuid, size=vol_size, fail_ok=False, cleanup='function')[1]

    LOG.tc_step("Boot VM using newly created bootable volume")
    vm_id = vm_helper.boot_vm(source="volume", source_id=vol_id, cleanup='function')[1]
    assert vm_id, "Failed to boot VM"
    vm_name = nova_helper.get_vm_name_from_id(vm_id)
    snapshot_name = vm_name + "_snapshot"

    # nova image-create generates a glance image of 0 size
    # real snapshot is stored in cinder
    LOG.tc_step("Create a snapshot based on that VM")
    cmd = "image-create {} {}".format(vm_id, snapshot_name)
    cli.nova(cmd, ssh_client=con_ssh, rtn_list=True, fail_ok=False)

    LOG.tc_step("Wait for the snapshot to become active")
    image_id = glance_helper.get_image_id_from_name(name=snapshot_name)
    ResourceCleanup.add('image', image_id)
    glance_helper.wait_for_image_states(image_id, status=ImageStatus.ACTIVE)

    cinder_snapshotname = "snapshot for {}".format(snapshot_name)
    LOG.tc_step("Get snapshot ID of {}".format(cinder_snapshotname))
    snapshot_id = cinder_helper.get_snapshot_id(name=cinder_snapshotname)
    ResourceCleanup.add('vol_snapshot', snapshot_id)
    assert snapshot_id, "Snapshot was not found"

    # We're deleting the VM, but leaving the volume and the snapshot
    LOG.tc_step("Delete the VM")
    vm_helper.delete_vms(vms=vm_id, fail_ok=False)

    LOG.tc_step("Attempting to delete the volume with associated snapshot")
    rc, out = cinder_helper.delete_volumes(vol_id, fail_ok=True)
    assert rc == 1, "Volume deletion was expected to fail but instead succeeded"

    LOG.tc_step("Delete the snapshot")
    cinder_helper.delete_volume_snapshots(snapshot_id, fail_ok=False)

    LOG.tc_step("Re-attempt volume deletion")
    # This step has been failing on ip33-36 and sm-1 due to volume delete rejected. After a minute or so,
    # it was accepted though.
    cinder_helper.delete_volumes(vol_id, fail_ok=False)