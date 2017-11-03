import time
import math
from pytest import mark, skip, fixture
from utils import cli
from utils.tis_log import LOG
from consts.cgcs import FlavorSpec, VMStatus, GuestImages
from consts.reasons import SkipReason
from utils.ssh import ControllerClient
from keywords import vm_helper, nova_helper, glance_helper, cinder_helper, check_helper, host_helper
from testfixtures.fixture_resources import ResourceCleanup

global images_list
global volumes_list
images_list = []
volumes_list = []
snapshots_list = []

@fixture()
def delete_resources(request):
    def teardown():
        """
        Delete any created image, snapshots and volumes.
        """

        global images_list
        global volumes_list
        global snapshots_list

        con_ssh = ControllerClient.get_active_controller()

        if len(images_list) != 0:
            glance_helper.delete_images(images_list)

        if len(snapshots_list) != 0:
            for snapshot in snapshots_list:
                cmd = "snapshot-delete {}".format(snapshot)
                rc, out = cli.cinder(cmd, ssh_client=con_ssh, rtn_list=True, fail_ok=True)
                assert rc == 0, "Cinder snapshot deletion failed"

        if len(volumes_list) != 0:
            cinder_helper.delete_volumes(volumes_list)

    request.addfinalizer(teardown)


@mark.usefixtures('delete_resources')
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

    global images_list
    images_list = []

    con_ssh = ControllerClient.get_active_controller()

    LOG.tc_step("Boot a VM from image")
    vm_id = vm_helper.boot_vm(source="image", cleanup='function')[1]
    assert vm_id, "Failed to boot VM"
    vm_name = nova_helper.get_vm_name_from_id(vm_id)
    snapshot_name = vm_name + "_snapshot"

    # nova image-create generates a glance image
    LOG.tc_step("Create a snapshot based on that VM")
    cmd = "image-create {} {}".format(vm_id, snapshot_name)
    rc, out = cli.nova(cmd, ssh_client=con_ssh, rtn_list=True)
    assert rc == 0, "Image snapshot creation failed"

    LOG.tc_step("Wait for the snapshot to become active")
    image_id = glance_helper.get_image_id_from_name(name=snapshot_name)
    glance_helper.wait_for_image_states(image_id, status='active')
    images_list.append(image_id)

    image_filename = '/home/wrsroot/images/temp'
    LOG.tc_step("Download the image snapshot")
    image_id = glance_helper.get_image_id_from_name(name=snapshot_name)
    cmd = "image-download --file {} --progress {}".format(image_filename, image_id)
    rc, out = cli.glance(cmd, ssh_client=con_ssh, rtn_list=True)
    assert rc == 0, "Nova image download did not succeed"

    # Downloading should be good enough for validation.  If the file is
    # zero-size, download will report failure.
    LOG.tc_step("Delete the downloaded image")
    rc, out = con_ssh.exec_cmd("rm {}".format(image_filename))
    assert rc == 0, "Downloaded image could not be deleted"

    # Second form of validation is to boot a VM from the snapshot
    LOG.tc_step("Boot a VM from snapshot")
    snapshot_vm = "from_" + snapshot_name
    snapshot_vmid = vm_helper.boot_vm(name=snapshot_vm, source="image", source_id=image_id, cleanup='function')[1]
    assert snapshot_vmid, "Unable to boot VM from snapshot"


@mark.usefixtures('delete_resources')
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

    global snapshots_list
    global volumes_list
    global images_list

    snapshots_list = []
    volumes_list = []
    images_list = []

    con_ssh = ControllerClient.get_active_controller()

    LOG.tc_step("Get available images")
    image_list = glance_helper.get_images()

    if len(image_list) == 0:
        skip("The test requires some images to be present")

    # Filter out zero-sized images and non-raw images (latter is lazy)
    usable_image = False
    for image in image_list:
        image_uuid = image
        image_prop_s = glance_helper.get_image_properties(image_uuid, "size")
        image_prop_d = glance_helper.get_image_properties(image_uuid, "disk_format")
        if image_prop_s['size'] == "0" or image_prop_d['disk_format'] != "raw":
            continue
        else:
            usable_image = True
            divisor = 1024 * 1024 * 1024
            image_size = int(image_prop_s['size'])
            vol_size = int(math.ceil(image_size / divisor))
            break

    if not usable_image:
        skip("No usable images found")

    LOG.tc_step("Create a cinder bootable volume")
    vol_id = cinder_helper.create_volume(image_id=image_uuid, size=vol_size)[1]
    assert vol_id, "Cinder volume creation failed"
    #volumes_list.append(vol_id)

    LOG.tc_step("Boot VM using newly created bootable volume")
    vm_id = vm_helper.boot_vm(source="volume", source_id=vol_id, cleanup='function')[1]
    assert vm_id, "Failed to boot VM"
    vm_name = nova_helper.get_vm_name_from_id(vm_id)
    snapshot_name = vm_name + "_snapshot"

    # nova image-create generates a glance image of 0 size
    # real snapshot is stored in cinder
    LOG.tc_step("Create a snapshot based on that VM")
    cmd = "image-create {} {}".format(vm_id, snapshot_name)
    rc, out = cli.nova(cmd, ssh_client=con_ssh, rtn_list=True)
    assert rc == 0, "Image snapshot creation failed"

    LOG.tc_step("Wait for the snapshot to become active")
    image_id = glance_helper.get_image_id_from_name(name=snapshot_name)
    glance_helper.wait_for_image_states(image_id, status='active')
    images_list.append(image_id)

    cinder_snapshotname = "snapshot for {}".format(snapshot_name)
    LOG.tc_step("Get snapshot ID of {}".format(cinder_snapshotname))
    snapshot_id = cinder_helper.get_snapshot_id(name=cinder_snapshotname)
    assert snapshot_id, "Snapshot was not found"
    vol_name = "vol_from_snapshot"
    snapshots_list.append(snapshot_id)

    # Creates volume from snapshot
    LOG.tc_step("Create cinder snapshot")
    cmd = "create --snapshot-id {} --name {}".format(snapshot_id, vol_name)
    rc, out = cli.cinder(cmd, ssh_client=con_ssh, rtn_list=True)
    assert rc == 0, "Cinder snapshot creation failed"
    snapshot_vol_id = cinder_helper.get_volumes(name=vol_name)[0]
    cinder_helper._wait_for_volume_status(vol_id=snapshot_vol_id, status="available")
    volumes_list.append(snapshot_vol_id)

    # Creates an image
    LOG.tc_step("Upload cinder volume to image")
    image_name = "cinder_upload"
    cmd = "upload-to-image {} {}".format(snapshot_vol_id, image_name)
    rc, out = cli.cinder(cmd, ssh_client=con_ssh, rtn_list=True)
    assert rc == 0, "Upload of volume to image failed"
    image_id = glance_helper.get_image_id_from_name(name=cinder_snapshotname)
    print("Uploading volume to image {}".format(image_id))
    images_list.append(image_id)

    LOG.tc_step("Wait for the uploaded image to become active")
    image_id = glance_helper.get_image_id_from_name(name=image_name)
    glance_helper.wait_for_image_states(image_id, status='active')
    print("Waiting for {} to be active".format(image_id))
    images_list.append(image_id)

    image_filename = '/home/wrsroot/images/temp'
    LOG.tc_step("Download the image snapshot")
    image_id = glance_helper.get_image_id_from_name(name=snapshot_name)
    cmd = "image-download --file {} --progress {}".format(image_filename, image_id)
    rc, out = cli.glance(cmd, ssh_client=con_ssh, rtn_list=True)
    assert rc == 0, "Nova image download did not succeed"

    # Downloading should be good enough for validation.  If the file is
    # zero-size, download will report failure.
    LOG.tc_step("Delete the downloaded image")
    rc, out = con_ssh.exec_cmd("rm {}".format(image_filename))
    assert rc == 0, "Downloaded image could not be deleted"


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

    global snapshots_list
    global volumes_list
    global images_list

    snapshots_list = []
    volumes_list = []
    images_list = []

    con_ssh = ControllerClient.get_active_controller()

    LOG.tc_step("Get available images")
    image_list = glance_helper.get_images()

    if len(image_list) == 0:
        skip("The test requires some images to be present")

    # Filter out zero-sized images and non-raw images (latter is lazy)
    usable_image = False
    for image in image_list:
        image_uuid = image
        image_prop_s = glance_helper.get_image_properties(image_uuid, "size")
        image_prop_d = glance_helper.get_image_properties(image_uuid, "disk_format")
        if image_prop_s['size'] == "0" or image_prop_d['disk_format'] != "raw":
            continue
        else:
            usable_image = True
            divisor = 1024 * 1024 * 1024
            image_size = int(image_prop_s['size'])
            vol_size = int(math.ceil(image_size / divisor))
            break

    if not usable_image:
        skip("No usable images found")

    LOG.tc_step("Create a cinder bootable volume")
    vol_id = cinder_helper.create_volume(image_id=image_uuid, size=vol_size)[1]
    assert vol_id, "Cinder volume creation failed"

    LOG.tc_step("Boot VM using newly created bootable volume")
    vm_id = vm_helper.boot_vm(source="volume", source_id=vol_id, cleanup='function')[1]
    assert vm_id, "Failed to boot VM"
    vm_name = nova_helper.get_vm_name_from_id(vm_id)
    snapshot_name = vm_name + "_snapshot"

    # nova image-create generates a glance image of 0 size
    # real snapshot is stored in cinder
    LOG.tc_step("Create a snapshot based on that VM")
    cmd = "image-create {} {}".format(vm_id, snapshot_name)
    rc, out = cli.nova(cmd, ssh_client=con_ssh, rtn_list=True)
    assert rc == 0, "Image snapshot creation failed"

    LOG.tc_step("Wait for the snapshot to become active")
    image_id = glance_helper.get_image_id_from_name(name=snapshot_name)
    glance_helper.wait_for_image_states(image_id, status='active')
    images_list.append(image_id)

    cinder_snapshotname = "snapshot for {}".format(snapshot_name)
    LOG.tc_step("Get snapshot ID of {}".format(cinder_snapshotname))
    snapshot_id = cinder_helper.get_snapshot_id(name=cinder_snapshotname)
    assert snapshot_id, "Snapshot was not found"
    snapshots_list.append(snapshot_id)

    # We're deleting the VM, but leaving the volume and the snapshot
    LOG.tc_step("Delete the VM")
    rc, out = vm_helper.delete_vms(vms=vm_id)
    assert rc == 0, "VM deletion failed"

    LOG.tc_step("Attempting to delete the volume with associated snapshot")
    rc, out = cinder_helper.delete_volumes(vol_id, fail_ok=True)
    assert rc != 0, "Volume deletion was expected to fail but instead succeeded"

    LOG.tc_step("Delete the snapshot")
    cmd = "snapshot-delete {}".format(snapshot_id)
    rc, out = cli.cinder(cmd, ssh_client=con_ssh, rtn_list=True, fail_ok=True)
    assert rc == 0, "Cinder snapshot deletion failed"

    LOG.tc_step("Re-attempt volume deletion")
    rc, out = cinder_helper.delete_volumes(vol_id)
    assert rc == 0, "Volume deletion unexpectedly failed"


