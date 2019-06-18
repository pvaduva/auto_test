"""
This test checks the target for the presence of a USB device.  It checks
whether the device is large enough for the test to execute.  It then formats
the USB as NTFS, creates partitions and a device label.  The device is then
mounted and a large image is copied over to the USB (virtual size 13G).  That
image is then imported into glance and a VM is booted from the image using a
newly created flavour.
"""


from pytest import skip

from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient
from consts.stx import FlavorSpec

from keywords import vm_helper, nova_helper, glance_helper, host_helper, system_helper
from testfixtures.fixture_resources import ResourceCleanup


def locate_usb(host_type="controller", min_size=13):
    """
    Try to locate a USB device on a host of the type specified.

    Arguments:
    - host_type (string) - e.g. controller, compute, storage
    - min_size (int) - minimum size of USB required (GiB)

    Returns:
    - hostname, e.g. controller-0
    - usb_device, e.g. /dev/sdb
    """

    LOG.tc_step("Check all hosts of type {} for USB devices".format(host_type))
    hosts = system_helper.get_hosts(personality=host_type)
    for host in hosts:
        with host_helper.ssh_to_host(host) as host_ssh:
            cmd = "ls --color=none -ltrd /dev/disk/by-id/usb*"
            rc, out = host_ssh.exec_cmd(cmd)
            if rc == 0:
                usb_device = "/dev/" + (out.splitlines()[0])[-3:]
                LOG.info("Found USB device {} on host {}".format(usb_device, host))
                cmd = "blockdev --getsize64 {}".format(usb_device)
                usb_bytes = host_ssh.exec_sudo_cmd(cmd)[1]
                gib = int(usb_bytes) / (1024 * 1024 * 1024)
                if gib > min_size:
                    LOG.info("Size of USB device is sufficient for test")
                    return host, usb_device
                else:
                    skip("Size of USB device is insufficient for test")

    return (None, None)


def umount_usb(host_ssh, mount_point="/media/ntfs"):
    """
    Unmount a USB device.

    Arguments:
    - host_ssh - ssh session to host with USB
    - mount_point (string) - e.g. /media/ntfs

    Returns
    - Nothing
    """

    LOG.tc_step("Unmounting {}".format(mount_point))
    cmd = "umount {}".format(mount_point)
    rc = host_ssh.exec_sudo_cmd(cmd)[0]
    assert rc == 0 or rc == 32
    if rc == 0:
        LOG.info("Umount was successful")
    if rc == 32:
        LOG.info("Umount was unsuccessful.  Maybe device was already unmounted?")


def wipe_usb(host_ssh, usb_device):
    """
    Wipe a USB device, including all existing partitions.

    Arguments:
    - host_ssh - ssh session to host with USB
    - usb_device (string) - name of usb device

    Returns:
    - nothing
    """

    LOG.tc_step("Wipe the USB completely")
    cmd = "dd if=/dev/zero of={} bs=1k count=2048".format(usb_device)
    rc = host_ssh.exec_sudo_cmd(cmd, fail_ok=False)[0]
    assert rc == 0, "USB wipe failed"


def create_usb_label(host_ssh, usb_device=None, label="msdos"):
    """
    Create a label on a USB device.

    Arguments:
    - host_ssh - ssh session to host with USB
    - usb_device (string) - e.g. /dev/sdb
    - label (string) - e.g. "msdos"

    Returns:
    - Nothing
    """

    LOG.tc_step("Create label and partition table on the USB")
    cmd = "parted {} mklabel {} -s".format(usb_device, label)
    rc = host_ssh.exec_sudo_cmd(cmd, fail_ok=False)[0]
    assert rc == 0, "Label creation failed"


def create_usb_partition(host_ssh, usb_device, startpt="0", endpt="0"):
    """
    Create a partition on a USB device.

    Arguments:
    - host_ssh - ssh session to host with USB
    - usb_device (string) - e.g. /dev/sdb
    - startpt (string) - partition start point, e.g. "0"
    - endpt (string) - partition end point, e.g. "2048"

    Returns:
    - Nothing
    """

    cmd = "parted -a none {} mkpart primary ntfs {} {}".format(usb_device, startpt, endpt)
    rc = host_ssh.exec_sudo_cmd(cmd)[0]
    assert rc == 0, "Primary partition creation failed"


def format_usb(host_ssh, usb_device, partition):
    """
    This formats a particular partition on a usb device.

    Arguments:
    - host_ssh - ssh session to host with USB
    - usb_device (string) - e.g. /dev/sdb
    - partition (string) - e.g. "2" for /dev/sdb2

    Returns:
    - Nothing
    """

    LOG.tc_step("Format device {} as NTFS".format(usb_device + partition))
    cmd = "mkfs.ntfs -f {}{}".format(usb_device, partition)
    rc = host_ssh.exec_sudo_cmd(cmd)[0]
    assert rc == 0, "Failed to format device"


def mount_usb(host_ssh, usb_device=None, partition="2", mount_type="ntfs", mount_point="/media/ntfs"):
    """
    This creates a mount point and then mounts the desired device.

    Arguments:
    - host_ssh - ssh session to host with USB
    - usb_device (string) - e.g. /dev/sdb
    - mount_point (string) - where the usb should be mounted

    Returns:
    - Nothing
    """

    LOG.tc_step("Check if mount point exists")
    cmd = "test -d {}".format(mount_point)
    rc = host_ssh.exec_sudo_cmd(cmd)[0]
    if rc == 1:
        LOG.tc_step("Create mount point")
        cmd = "mkdir -p {}".format(mount_point)
        rc = host_ssh.exec_sudo_cmd(cmd)[0]
        assert rc == 0, "Mount point creation failed"

    LOG.tc_step("Mount ntfs device")
    cmd = "mount -t {} {} {}".format(mount_type, usb_device + partition, mount_point)
    rc = host_ssh.exec_sudo_cmd(cmd)[0]
    assert rc == 0, "Unable to mount device"


# Wendy says just testing one node is enough.
#@mark.parametrize("host_type", ['controller', 'compute', 'storage'])
def test_ntfs(host_type="controller"):
    """
    This test will test NTFS mount and NTFS formatted device creation on a TiS
    system.

    Arguments:
    - host_type (string) - host type to be tested, e.g. controller, compute,
      storage

    Returns:
    - Nothing

    Test Steps:
    1.  Check if desired host has USB inserted.  If not, skip
    2.  Wipe USB
    3.  Change label of device
    4.  Create partitions on NTFS device
    5.  Format partitions
    4.  Copy large image to NTFS mount point
    5.  Test mount and big file creation on NTFS mounted device
    """

    # Could pass these in through parametrize instead
    mount_type = "ntfs"
    mount_point = "/media/ntfs/"
    guest_os = 'win_2012'
    boot_source = "image"

    host, usb_device = locate_usb(host_type, min_size=13)
    if not host:
        skip("No USB hardware found on {} host type".format(host_type))

    hosts_with_image_backing = host_helper.get_hosts_in_storage_backing(storage_backing='image')
    if len(hosts_with_image_backing) == 0:
        skip("No hosts with image backing present")

    # if the host with the USB is not the active controler, swact controllers
    con_ssh = ControllerClient.get_active_controller()
    active_controller = system_helper.get_active_controller_name(con_ssh)
    if host != active_controller:
        host_helper.swact_host()

    with host_helper.ssh_to_host(host) as host_ssh:
        wipe_usb(host_ssh, usb_device)
        umount_usb(host_ssh, mount_point=mount_point)
        create_usb_label(host_ssh, usb_device, label="msdos")
        create_usb_partition(host_ssh, usb_device, startpt="0", endpt="2048")
        format_usb(host_ssh, usb_device, partition="1")
        create_usb_partition(host_ssh, usb_device, startpt="2049", endpt="100%")
        format_usb(host_ssh, usb_device, partition="2")
        mount_usb(host_ssh, usb_device, partition="2", mount_type=mount_type, mount_point=mount_point)

    LOG.tc_step("Copy the windows guest image to the mount point")
    src_img = glance_helper.scp_guest_image(img_os=guest_os, dest_dir=mount_point, con_ssh=con_ssh)

    LOG.tc_step("Create flavor for windows guest image")
    flv_id = nova_helper.create_flavor(name=guest_os, vcpus=4, ram=8192, storage_backing="local_image",
                                       guest_os=guest_os)[1]
    nova_helper.set_flavor(flv_id, **{FlavorSpec.CPU_POLICY: "dedicated"})
    ResourceCleanup.add("flavor", flv_id)

    LOG.tc_step("Import image into glance")
    glance_helper.create_image(name=guest_os, source_image_file=src_img, disk_format="qcow2",
                               container_format="bare", con_ssh=con_ssh, cleanup="function")

    LOG.tc_step("Boot VM")
    vm_id = vm_helper.boot_vm(name=guest_os, flavor=flv_id, guest_os=guest_os, source=boot_source, cleanup="function")[1]

    LOG.tc_step("Ping vm and ssh to it")
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        output = vm_ssh.exec_cmd('pwd', fail_ok=False)[1]
        LOG.info(output)
