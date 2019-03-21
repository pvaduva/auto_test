import math
import time

from pytest import skip, mark

from consts.cgcs import ImageStatus
from consts.auth import Tenant
from consts.reasons import SkipStorageBacking
from keywords import vm_helper, nova_helper, glance_helper, cinder_helper, host_helper, storage_helper, common
from testfixtures.fixture_resources import ResourceCleanup
from utils import cli, table_parser
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG


@mark.dc
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
    nova_cmd = "image-create {} {}".format(vm_id, snapshot_name)
    cli.nova(nova_cmd, ssh_client=con_ssh, rtn_list=True, fail_ok=False)
    # exception will be thrown if nova cmd rejected
    image_id = glance_helper.get_image_id_from_name(name=snapshot_name, strict=True, fail_ok=False)
    ResourceCleanup.add('image', image_id)

    LOG.tc_step("Wait for the snapshot to become active")
    glance_helper.wait_for_image_states(image_id, status=ImageStatus.ACTIVE)

    image_filename = '/home/wrsroot/images/temp'
    LOG.tc_step("Download the image snapshot")
    glance_cmd = "image-download --file {} {}".format(image_filename, image_id)
    # Throw exception if glance cmd rejected
    cli.glance(glance_cmd, ssh_client=con_ssh, fail_ok=False)

    # Downloading should be good enough for validation.  If the file is
    # zero-size, download will report failure.
    LOG.tc_step("Delete the downloaded image")
    con_ssh.exec_cmd("rm {}".format(image_filename), fail_ok=False)

    # Second form of validation is to boot a VM from the snapshot
    LOG.tc_step("Boot a VM from snapshot")
    snapshot_vm = "from_" + snapshot_name
    vm_helper.boot_vm(name=snapshot_vm, source="image", source_id=image_id, cleanup='function', fail_ok=False)


@mark.dc
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
    image_uuid = vol_size = None
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
    # Check if lab has emc-vnx volume types. Use volume type = iscsi; Creating snapshot with emc-vnx(EMS San)
    # is not supported yet.
    volume_types = cinder_helper.get_volume_types(rtn_val='Name')
    vol_type = 'iscsi' if any('emc' in t for t in volume_types) else None
    vol_id = cinder_helper.create_volume(image_id=image_uuid, size=vol_size, vol_type=vol_type, fail_ok=False)[1]
    ResourceCleanup.add('volume', vol_id)

    LOG.tc_step("Boot VM using newly created bootable volume")
    vm_id = vm_helper.boot_vm(source="volume", source_id=vol_id, cleanup='function')[1]
    vm_name = nova_helper.get_vm_name_from_id(vm_id)
    snapshot_name = vm_name + "_snapshot"

    # nova image-create generates a glance image of 0 size
    # real snapshot is stored in cinder
    LOG.tc_step("Create a snapshot based on that VM")
    nova_cmd = "image-create {} {}".format(vm_id, snapshot_name)
    cli.nova(nova_cmd, ssh_client=con_ssh, rtn_list=True, fail_ok=False)
    image_id = glance_helper.get_image_id_from_name(name=snapshot_name)
    ResourceCleanup.add('image', image_id)

    LOG.tc_step("Wait for the snapshot to become active")
    glance_helper.wait_for_image_states(image_id, status=ImageStatus.ACTIVE, fail_ok=False)

    cinder_snapshotname = "snapshot for {}".format(snapshot_name)
    LOG.tc_step("Get snapshot ID of {}".format(cinder_snapshotname))
    snapshot_id = cinder_helper.get_vol_snapshot(name=cinder_snapshotname)
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
    glance_helper.wait_for_image_states(image_id, status=ImageStatus.ACTIVE, fail_ok=False, timeout=240)
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
    image_uuid = vol_size = None
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
    # Check if lab has emc-vnx volume types. Use volume type = iscsi; Creating snapshot with emc-vnx(EMS San)
    # is not supported yet.
    volume_types = cinder_helper.get_volume_types(rtn_val='Name')
    vol_type = 'iscsi' if any('emc' in t for t in volume_types) else None
    vol_id = cinder_helper.create_volume(image_id=image_uuid, size=vol_size, vol_type=vol_type, fail_ok=False,
                                         cleanup='function')[1]

    LOG.tc_step("Boot VM using newly created bootable volume")
    vm_id = vm_helper.boot_vm(source="volume", source_id=vol_id, cleanup='function')[1]
    assert vm_id, "Failed to boot VM"
    vm_name = nova_helper.get_vm_name_from_id(vm_id)
    snapshot_name = vm_name + "_snapshot"

    # nova image-create generates a glance image of 0 size
    # real snapshot is stored in cinder
    LOG.tc_step("Create a snapshot based on that VM")
    nova_cmd = "image-create {} {}".format(vm_id, snapshot_name)
    cli.nova(nova_cmd, ssh_client=con_ssh, rtn_list=True, fail_ok=False)

    LOG.tc_step("Wait for the snapshot to become active")
    image_id = glance_helper.get_image_id_from_name(name=snapshot_name)
    ResourceCleanup.add('image', image_id)
    glance_helper.wait_for_image_states(image_id, status=ImageStatus.ACTIVE)

    cinder_snapshotname = "snapshot for {}".format(snapshot_name)
    LOG.tc_step("Get snapshot ID of {}".format(cinder_snapshotname))
    snapshot_id = cinder_helper.get_vol_snapshot(name=cinder_snapshotname)
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


def create_snapshot_from_instance(vm_id, name):
    exit_code, output = cli.nova('image-create --poll {} {}'.format(vm_id, name), auth_info=Tenant.get('admin'),
                                 fail_ok=True, timeout=400)
    image_names = glance_helper.get_images(rtn_val='name')
    if name in image_names:  # covers if image creation wasn't completely successful but somehow still produces an image
        img_id = glance_helper.get_image_id_from_name(name=name, strict=True, auth_info=Tenant.get('admin'),
                                                      fail_ok=False)
        ResourceCleanup.add('image', img_id)
        image_show_table = table_parser.table(cli.glance('image-show', img_id))
        snap_size = int(table_parser.get_value_two_col_table(image_show_table, 'size'))
        LOG.info("size of snapshot {} is {} or around {} GiB".format(name, snap_size, (snap_size / 1073741824)))
    else:
        snap_size = 0
    return exit_code, output, snap_size


# Obsolete for ceph.
@mark.parametrize('inst_backing', [
    'local_image',
])
def _test_snapshot_large_vm_negative(add_admin_role_module, inst_backing):
    """
    Tests that the system rejects snapshot creation if there is not enough room for it and that an appropriate error
    message is written in the correct compute-log file for the host of the created VM

    Test steps:
        - Find out how much space is allotted for vm creation and for snapshots/images and determine a VM size based
          on that. The vm snapshots should be around 2/3 of the allowed free space.
        - Boot an instance and resize its disk to be larger than 2/3 of the amount of available glance image space.
        - Perform a data dump to fill the vm to make its snapshot larger.
        - Take an initial snapshot, verify that it is successful and the snapshot size is within estimates
        - Take a second snapshot, verify that it fails and the amount of glance image free disk space is unchanged

    Test Teardown:
        - Delete created VMs
        - Delete created images

    """

    host_list = host_helper.get_hosts_in_storage_backing(storage_backing=inst_backing)
    if not host_list:
        skip(SkipStorageBacking.NO_HOST_WITH_BACKING.format(inst_backing))

    # Check if glance-image storage backing is present in system and skip if it is
    backends = storage_helper.get_storage_backends()
    if 'ceph' in backends or 'external' in backends:
        auth_info = dict(Tenant.get('admin'))
        if 'external' in backends:
            auth_info['region'] = 'RegionOne'
        glance_pool = storage_helper.get_storage_backend_show_vals(backend='ceph', fields=('glance_pool_gib',),
                                                                   auth_info=auth_info)
        if glance_pool:
            skip("Skip lab with ceph-backed glance image storage")

    vm_host = host_list[0]
    backend_type = 'file'
    snapshot_space_gb = storage_helper.get_storage_usage(service='glance', backend_type=backend_type)
    if snapshot_space_gb > 20:
        skip("Lab glance image directory too large for timely test execution")

    vm_size = int(snapshot_space_gb) + 1

    # Make a big disk vm
    LOG.tc_step("Creating VM")
    flv_id = nova_helper.create_flavor(root_disk=vm_size, storage_backing=inst_backing)[1]
    ResourceCleanup.add('flavor', flv_id)
    vm_id = vm_helper.boot_vm(source='image', flavor=flv_id, vm_host=vm_host, avail_zone='nova', cleanup="function")[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    # Dump data in it
    LOG.tc_step("Fill vm localdisk")
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        df_cmd = "df | grep /dev/vda1 | awk '{print $3}'"

        df_output_before = vm_ssh.exec_sudo_cmd(df_cmd)[1]
        df_output_before_gb = float(df_output_before) / (1024 * 1024)
        LOG.info("Amount of written disk space in instance before dd is {} GiB".format(df_output_before_gb))

        resize_amount = vm_size - 1
        dump_amount_gb = int((vm_size * 2 / 3) - df_output_before_gb)

        resize_cmd = 'resize2fs /dev/vda1 {}m'.format((resize_amount * 1024))
        dump_cmd = 'dd if=/dev/urandom of=~/testfile bs=1024 count={}'.format((dump_amount_gb * 1024 * 1024))

        vm_ssh.exec_sudo_cmd(resize_cmd)
        LOG.tc_step("Executing data dump")
        vm_ssh.exec_sudo_cmd(dump_cmd, expect_timeout=180)
        df_output = vm_ssh.exec_sudo_cmd(df_cmd)[1]

        LOG.info("vm_size: {}  dump_amount_gb: {}  snapshot_space: {} GiB".
                 format(vm_size, dump_amount_gb, snapshot_space_gb))

    written_disk_size = float(df_output) / (1024 * 1024)
    LOG.info("written_disk_size: {} GiB".format(written_disk_size))
    snapshot_range_min = written_disk_size - 0.1
    snapshot_range_max = written_disk_size + 0.1

    # Make first snapshot
    storage_before = snapshot_space_gb
    LOG.tc_step("Create snapshots, current {} GiB of free space".format(storage_before))
    exit_code, output, original_snap_size = create_snapshot_from_instance(vm_id, name="snapshot0")
    assert exit_code == 0, "First snapshot failed"

    storage_left = storage_helper.get_storage_usage(service='glance', backend_type=backend_type)

    space_taken = storage_before - storage_left
    assert snapshot_range_min <= space_taken <= snapshot_range_max, \
        "Space occupied by snapshot not in expected range, size is {}".format(space_taken)

    init_time = common.get_date_in_format(date_format="%Y-%m-%d %T")
    LOG.tc_step("First snapshot created, {} GiB of storage left, attempt second snapshot".format(storage_left))
    exit_code, output, snap_size = create_snapshot_from_instance(vm_id, name="snapshot1")
    time.sleep(10)

    storage_after = storage_helper.get_storage_usage(service='glance', backend_type=backend_type)
    assert exit_code != 0, "Snapshot succeeded when it was expected to fail"
    assert storage_left - 0.02 <= storage_after <= storage_left + 0.02, \
        "Free capacity has changed to {} even though 2nd snapshot failed (expected to be 0.01 within)".\
        format(storage_after, storage_left)

    expt_err = "not enough disk space on the image storage media"
    with host_helper.ssh_to_host(vm_host) as host_ssh:
        grepcmd = """grep '{}' /var/log/nova/nova-compute.log | awk '$0 > "{}"'""".format(expt_err, init_time)
        host_ssh.exec_cmd(grepcmd, fail_ok=False)
