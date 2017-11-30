import re
from time import sleep

from pytest import fixture, mark, skip
from utils.tis_log import LOG
from utils import table_parser, cli, exceptions
from consts.auth import Tenant
from consts.reasons import SkipStorageBacking

from keywords import vm_helper, nova_helper, host_helper, cinder_helper, glance_helper, storage_helper
from testfixtures.fixture_resources import ResourceCleanup


def create_snapshot_from_instance(vm_id, name):
    exit_code, output = cli.nova('image-create --poll {} {}'.format(vm_id, name), auth_info=Tenant.ADMIN,
                                 fail_ok=True, timeout=400)
    image_names = glance_helper.get_images(rtn_val='name')
    if name in image_names:  # covers if image creation wasn't completely successful but somehow still produces an image
        img_id = glance_helper.get_image_id_from_name(name=name, strict=True, auth_info=Tenant.ADMIN, fail_ok=False)
        ResourceCleanup.add('image', img_id)
        image_show_table = table_parser.table(cli.glance('image-show', img_id))
        snap_size = int(table_parser.get_value_two_col_table(image_show_table, 'size'))
        LOG.info("size of snapshot {} is {} or around {} GiB".format(name, snap_size, (snap_size / 1073741824)))
    else:
        snap_size = 0
    return exit_code, output, snap_size


@mark.parametrize('inst_backing', [
    'local_image',
    # 'local_lvm'
])
def test_snapshot_large_vm_negative(add_admin_role_module, inst_backing):
    """
        Tests that the system rejects snapshot creation if there is not enough room for it and that an appropiate error
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

    host_list = host_helper.get_hosts_by_storage_aggregate(storage_backing=inst_backing)
    if not host_list:
        skip(SkipStorageBacking.NO_HOST_WITH_BACKING.format(inst_backing))

    # Check if glance-image storage backing is present in system and skip if it is
    if 'ceph' in storage_helper.get_configured_system_storage_backend():
        table_ = table_parser.table(cli.system('storage-backend-show ceph'))
        glance_pool = table_parser.get_value_two_col_table(table_, 'glance_pool_gib')
        if glance_pool:
            skip("Skip lab with ceph-backed glance image storage")

    vm_host = host_list[0]
    snaptable_ = table_parser.table(cli.system("storage-usage-list", auth_info=Tenant.ADMIN))

    snapshot_space = table_parser.get_values(snaptable_, "free capacity (Gib)", **{'service': 'glance', 'backend name': 'file'})[0]
    snapshot_space_gb = int(float(snapshot_space))
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

        LOG.info(
            "vm_size: {}  dump_amount_gb: {}  snapshot_space: {} GiB".format(vm_size, dump_amount_gb, snapshot_space))

    written_disk_size = float(df_output) / (1024 * 1024)
    LOG.info("written_disk_size: {} GiB".format(written_disk_size))
    snapshot_range_min = written_disk_size - 0.1
    snapshot_range_max = written_disk_size + 0.1

    # Make first snapshot
    storage_before = float(table_parser.get_values(snaptable_, "free capacity (Gib)", **{'service': 'glance', 'backend name': 'file'})[0])
    LOG.tc_step("Create snapshots, current {} GiB of free space".format(storage_before))
    exit_code, output, original_snap_size = create_snapshot_from_instance(vm_id, name="snapshot0")
    assert exit_code == 0, "First snapshot failed"

    snaptable_ = table_parser.table(cli.system("storage-usage-list", auth_info=Tenant.ADMIN))
    storage_left = float(table_parser.get_values(snaptable_, "free capacity (Gib)", **{'service': 'glance', 'backend name': 'file'})[0])

    space_taken = storage_before - storage_left
    assert snapshot_range_min <= space_taken <= snapshot_range_max, "Space occupied by snapshot not in expected range, size is {}"\
        .format(space_taken)

    LOG.tc_step("First snapshot created, {} GiB of storage left, attempt second snapshot".format(storage_left))
    exit_code, output, snap_size = create_snapshot_from_instance(vm_id, name="snapshot1")
    sleep(10)

    snaptable_ = table_parser.table(cli.system("storage-usage-list", auth_info=Tenant.ADMIN))
    storage_after = float(table_parser.get_values(snaptable_, "free capacity (Gib)", **{'service': 'glance', 'backend name': 'file'})[0])
    assert exit_code != 0, "Snapshot succeeded when it was expected to fail"
    assert storage_left - 0.02 <= storage_after <= storage_left + 0.02, \
        "Free capacity has changed to {} even though 2nd snapshot failed (expected to be 0.01 within)".format(storage_after, storage_left)

    expt_err = "Not enough space on the storage media for image {}".format((output.split())[-1])
    with host_helper.ssh_to_host(vm_host) as host_ssh:
        grepcmd = "grep '{}' /var/log/nova/nova-compute.log".format(expt_err)
        host_ssh.exec_cmd(grepcmd, fail_ok=False)
