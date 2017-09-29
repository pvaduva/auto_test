import time
import re
import os
from pytest import fixture, skip, mark
from utils.tis_log import LOG
from keywords import network_helper, install_helper, cinder_helper, host_helper, glance_helper, common, system_helper
from consts import timeout
from consts.cgcs import PREFIX_BACKUP_FILE, TIS_BLD_DIR_REGEX
from testfixtures.recover_hosts import HostsToRecover
from consts.auth import Tenant, SvcCgcsAuto, HostLinuxCreds
from consts.filepaths import BuildServerPath, WRSROOT_HOME
from utils.ssh import ControllerClient
from consts.timeout import VolumeTimeout
from consts.proj_vars import InstallVars, ProjVar


@fixture(scope='session')
def pre_system_backup():

    LOG.tc_func_start("BACKUP_TEST")
    hostnames = system_helper.get_hostnames()
    cpe = system_helper.is_small_footprint()
    LOG.info("Preparing lab for system backup....")
    assert system_helper.get_active_controller_name() == 'controller-0', "controller-0 is not the active controller"
    LOG.tc_step("Checking if  a USB flash drive is plugged in controller-0 node... ")
    usb_device = install_helper.get_usb_device_name()
    assert usb_device, "No USB found in controller-0"
    parts_info = install_helper.get_usb_device_partition_info(usb_device=usb_device)

    part1 = "{}1".format(usb_device)
    part2 = "{}2".format(usb_device)

    if len(parts_info) < 3:
        #rc, parts_info = install_helper.usb_create_partition_for_backup(usb_device=usb_device)
        skip("USB {} is not partitioned;  Create two partitions using fdisk; partition 1 = {}1, size = 2G, bootable;"
             " partition 2 = {}2, size equal to the avaialble space.".format(usb_device, usb_device, usb_device))

    devices = parts_info.keys()
    LOG.info("Size of {} = {}".format(part1, install_helper.get_usb_partition_size(part1)))
    if not (part1 in devices and install_helper.get_usb_partition_size(part1) >= 2):

        skip("Insufficient size in {}; at least 2G is required. {}".format(part1, parts_info))

    if not (part2 in devices and install_helper.get_usb_partition_size(part2) >= 10):
        skip("Insufficient size in {}; at least 2G is required. {}".format(part1, parts_info))


    if not install_helper.mount_usb(part2):
         skip("Fail to mount USB for backups")

    LOG.tc_step("Erasing existing files from USB ... ")

    assert install_helper.delete_backup_files_from_usb(part2), "Fail to erase existing file from USB"

    return parts_info


def test_create_backup(pre_system_backup):
    """
    Test create backup on the system and it's avaliable and in-use volumes.
    copy backup files to USB flash drive

    Args:


    Setup:
        - create system backup use config_controller (create system,image tgz)
        - backup image separately if its storage lab that use CEPH
        - back up all available and in-use volumes from the lab

    Test Steps:
        - check system and img tgz are created for system backup
        - check all images are back up in storage
        - check all volumes tgz are created for backup

    Teardown:
        - Delete vm if booted
        - Delete created flavor (module)

    """
    usb_partition_info =  pre_system_backup
    usb_part2 = None
    usb_part1 = None
    for k, v in usb_partition_info.items():
        if k[-1:] == "1":
            usb_part1 = k
        elif k[-1:] == '2':
            usb_part2 = k

    LOG.tc_step("System backup ...")
    install_helper.backup_system(copy_to_usb=usb_part2)

    # storage lab start backup image files separately if it's a storage lab
    # if number of storage nodes is greater than 0
    if len(system_helper.get_storage_nodes()) > 0:

        LOG.tc_step("Storage lab detected. copying images to backup.")

        image_ids = glance_helper.get_images()
        img_file = ''
        for img_id in image_ids:
            install_helper.export_image(img_id, copy_to_usb=usb_part2)

    # execute backup available volume command
    LOG.tc_step("Cinder Volumes backup ...")

    vol_ids = cinder_helper.get_volumes(auth_info=Tenant.ADMIN)
    vol_files = ''
    if len(vol_ids) > 0:
        LOG.info("Exporting cinder volumes: {}".format(vol_ids))
        exported = install_helper.export_cinder_volumes(copy_to_usb=usb_part2)
        assert len(exported) > 0, "Fail to export all volumes"
        assert len(exported) == len(vol_ids), "Some volumes failed export: {}".format(set(vol_ids)-set(exported))
    else:
        LOG.info("No cinder volumes are avaialbe in the system; skipping cinder volume export...")

    # Burning USB with current system backup lSO file for future restore

    if usb_part1:
        LOG.tc_step("Burning backup load ISO to /dev/{}  ...".format(usb_part1))
        assert burn_usb_backup_load_image(usb_part1), "Fail to Burn backup load ISO file to USB {}".format(usb_part1)


def burn_usb_backup_load_image(usb_device):
    ''' Burn usb with given load image.
    '''

    if not  install_helper.get_usb_partition_size(usb_device) >= 2:
        LOG.info("USB partition  size  is too small for load iso file")
        return False

    lab = InstallVars.get_install_var('LAB')
    version = system_helper.get_system_software_version()
    load_path = BuildServerPath.LATEST_HOST_BUILD_PATHS[version.strip()]
    if load_path.strip()[-1:] == '/':
        load_path = load_path.strip()[:-1]
    build_id = ProjVar.get_var('BUILD_ID')
    assert re.match(TIS_BLD_DIR_REGEX, build_id), "Invalid Build Id pattern"
    load_path.replace("latest_build", build_id)

    with install_helper.ssh_to_build_server() as build_server_conn:
        pre_opts = "sshpass -p '{0}'".format(HostLinuxCreds.get_password())

        cmd = "test -e " + load_path
        assert build_server_conn.exec_cmd(cmd, rm_date=False)[0] == 0,  'The system build {} not found in {}:{}'.\
            format(build_id, BuildServerPath.DEFAULT_BUILD_SERVER, load_path)

        iso_file_path = os.path.join(load_path, "export", install_helper.UPGRADE_LOAD_ISO_FILE)
        pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.get_password())
        build_server_conn.rsync("-L " + iso_file_path,
                          lab['controller-0 ip'],
                          os.path.join(WRSROOT_HOME, "bootimage.iso"), pre_opts=pre_opts)


    # Check if the ISO is uploaded to controller-0
    con_ssh = ControllerClient.get_active_controller()
    cmd = "test -e " + os.path.join(WRSROOT_HOME, "bootimage.iso")
    assert con_ssh.exec_cmd(cmd)[0] == 0,  'The bootimage.iso file not found in {}'.format(WRSROOT_HOME)

    # Write the ISO to USB
    cmd = "echo {} | sudo -S dd if={} of=/dev/{} bs=1M oflag=direct; sync"\
        .format(HostLinuxCreds.get_password(), os.path.join(WRSROOT_HOME, "bootimage.iso"), usb_device)

    rc,  output = con_ssh.exec_cmd(cmd, expect_timeout=900)
    if rc == 0:
        LOG.info(" The backup build iso file copied to USB for restore. {}".format(output))
        return True
    else:
        LOG.error("Failed to copy backup build iso file to USB {}: {}".format(usb_device, output))
        return False
