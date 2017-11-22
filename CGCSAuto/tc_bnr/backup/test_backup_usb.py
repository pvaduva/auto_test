
import re
import os
# import socket
from pytest import fixture, skip
from utils.tis_log import LOG
from keywords import install_helper, cinder_helper, glance_helper, common, system_helper
from consts.cgcs import TIS_BLD_DIR_REGEX, BackupRestore
from consts.auth import Tenant, SvcCgcsAuto, HostLinuxCreds
from consts.filepaths import BuildServerPath, WRSROOT_HOME
from utils.ssh import ControllerClient
# from CGCSAuto.utils import local_host
from consts.proj_vars import InstallVars, ProjVar, BackupVars
from consts.build_server import Server
from keywords import html_helper


@fixture(scope='session')
def pre_system_backup():

    LOG.tc_func_start("BACKUP_TEST")
    lab = InstallVars.get_install_var('LAB')

    LOG.info("Preparing lab for system backup....")
    backup_dest = BackupVars.get_backup_var("BACKUP_DEST")

    _backup_info = {'backup_dest': backup_dest,
                    'usb_parts_info': None,
                    'backup_dest_full_path': None,
                    'dest_server': None
                    }

    if backup_dest == 'usb':
        assert system_helper.get_active_controller_name() == 'controller-0', "controller-0 is not the active controller"
        LOG.tc_step("Checking if  a USB flash drive is plugged in controller-0 node... ")
        usb_device = install_helper.get_usb_device_name()
        assert usb_device, "No USB found in controller-0"
        parts_info = install_helper.get_usb_device_partition_info(usb_device=usb_device)

        part1 = "{}1".format(usb_device)
        part2 = "{}2".format(usb_device)

        if len(parts_info) < 3:
            skip("USB {} is not partitioned;  Create two partitions using fdisk; partition 1 = {}1, "
                 "size = 2G, bootable; partition 2 = {}2, size equal to the avaialble space."
                 .format(usb_device, usb_device, usb_device))

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
        _backup_info['usb_parts_info'] = parts_info
        _backup_info['backup_dest_full_path'] = BackupRestore.USB_BACKUP_PATH

    elif backup_dest == 'local':
        # save backup files in Test Server which local
        backup_dest_path = BackupVars.get_backup_var('BACKUP_DEST_PATH')
        backup_dest_full_path = '{}/{}'.format(backup_dest_path, lab['short_name'])
        # ssh to test server
        test_server_attr = dict()
        test_server_attr['name'] = SvcCgcsAuto.HOSTNAME.split('.')[0]
        test_server_attr['server_ip'] = SvcCgcsAuto.SERVER
        test_server_attr['prompt'] = r'\[{}@{} {}\]\$ '\
            .format(SvcCgcsAuto.USER, test_server_attr['name'], SvcCgcsAuto.USER)

        test_server_conn = install_helper.establish_ssh_connection(test_server_attr['name'],
                                                                   user=SvcCgcsAuto.USER,
                                                                   password=SvcCgcsAuto.PASSWORD,
                                                                   initial_prompt=test_server_attr['prompt'])

        test_server_conn.set_prompt(test_server_attr['prompt'])
        test_server_conn.deploy_ssh_key(install_helper.get_ssh_public_key())
        test_server_attr['ssh_conn'] = test_server_conn
        test_server_obj = Server(**test_server_attr)
        _backup_info['dest_server'] = test_server_obj
        # test if backup path for the lab exist in Test server
        if test_server_conn.exec_cmd("test -e {}".format(backup_dest_full_path))[0]:
            test_server_conn.exec_cmd("mkdir -p {}".format(backup_dest_full_path))
            # delete any existing files
        test_server_conn.exec_cmd("rm -rf {}/*".format(backup_dest_full_path))

        _backup_info['usb_parts_info'] = None
        _backup_info['backup_dest_full_path'] = backup_dest_full_path

    return _backup_info


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

    backup_info = pre_system_backup
    lab = InstallVars.get_install_var('LAB')
    LOG.tc_step("System backup: lab={}; backup dest = {} backup destination path = {} ..."
                .format(lab['name'], backup_info['backup_dest'], backup_info['backup_dest_full_path']))
    dest_server = backup_info['dest_server']
    copy_to_usb = None
    usb_part2 = None
    # usb_part1 = None

    backup_dest = backup_info['backup_dest']
    if backup_dest == 'usb':
        usb_partition_info = backup_info['usb_parts_info']
        for k, v in usb_partition_info.items():
            if k[-1:] == "1":
                usb_part1 = k
            elif k[-1:] == '2':
                usb_part2 = k
        copy_to_usb = usb_part2

    install_helper.backup_system(backup_dest=backup_dest, backup_dest_path=backup_info['backup_dest_full_path'],
                                 dest_server=dest_server, copy_to_usb=copy_to_usb)

    # storage lab start backup image files separately if it's a storage lab
    # if number of storage nodes is greater than 0
    if len(system_helper.get_storage_nodes()) > 0:

        LOG.tc_step("Storage lab detected. copying images to backup.")
        image_ids = glance_helper.get_images()
        # img_file = ''
        for img_id in image_ids:
            install_helper.export_image(img_id, backup_dest=backup_dest,
                                        backup_dest_path=backup_info['backup_dest_full_path'], dest_server=dest_server,
                                        copy_to_usb=copy_to_usb)

    # execute backup available volume command
    LOG.tc_step("Cinder Volumes backup ...")

    vol_ids = cinder_helper.get_volumes(auth_info=Tenant.ADMIN)
    if len(vol_ids) > 0:
        LOG.info("Exporting cinder volumes: {}".format(vol_ids))
        exported = install_helper.export_cinder_volumes(backup_dest=backup_dest,
                                                        backup_dest_path=backup_info['backup_dest_full_path'],
                                                        dest_server=dest_server, copy_to_usb=copy_to_usb)

        assert len(exported) > 0, "Fail to export all volumes"
        assert len(exported) == len(vol_ids), "Some volumes failed export: {}".format(set(vol_ids)-set(exported))
    else:
        LOG.info("No cinder volumes are avaialbe in the system; skipping cinder volume export...")

    # Copying ystem backup lSO file for future restore
    assert backup_load_iso_image(backup_info)


def backup_load_iso_image(backup_info):
    """

    Args:
        backup_info

    Returns:

    """
    # lab = InstallVars.get_install_var('LAB')
    backup_dest = backup_info['backup_dest']
    backup_dest_path = backup_info['backup_dest_full_path']

    version = system_helper.get_system_software_version()
    load_path = BuildServerPath.LATEST_HOST_BUILD_PATHS[version.strip()]
    if load_path.strip()[-1:] == '/':
        load_path = load_path.strip()[:-1]
    build_id = ProjVar.get_var('BUILD_ID')
    assert re.match(TIS_BLD_DIR_REGEX, build_id), "Invalid Build Id pattern"
    load_path.replace("latest_build", build_id)

    with install_helper.ssh_to_build_server() as build_server_conn:

        cmd = "test -e " + load_path
        assert build_server_conn.exec_cmd(cmd, rm_date=False)[0] == 0,  'The system build {} not found in {}:{}'.\
            format(build_id, BuildServerPath.DEFAULT_BUILD_SERVER, load_path)

        iso_file_path = os.path.join(load_path, "export", install_helper.UPGRADE_LOAD_ISO_FILE)
        pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.get_password())
        # build_server_conn.rsync("-L " + iso_file_path, lab['controller-0 ip'],
        build_server_conn.rsync("-L " + iso_file_path, html_helper.get_ip_addr(),
                                os.path.join(WRSROOT_HOME, "bootimage.iso"), pre_opts=pre_opts)

    if backup_dest == 'usb':
        usb_part1 = None
        usb_partition_info = install_helper.get_usb_device_partition_info()
        for k, v in usb_partition_info.items():
            if k[-1:] == "1":
                usb_part1 = k
        if not usb_part1:
            LOG.info("No partition exist for burning load iso image in usb: {}".format(usb_partition_info))
            return False

        # Check if the ISO is uploaded to controller-0
        con_ssh = ControllerClient.get_active_controller()
        cmd = "test -e " + os.path.join(WRSROOT_HOME, "bootimage.iso")
        assert con_ssh.exec_cmd(cmd)[0] == 0,  'The bootimage.iso file not found in {}'.format(WRSROOT_HOME)

        LOG.tc_step("Burning backup load ISO to /dev/{}  ...".format(usb_part1))
        # Write the ISO to USB
        cmd = "echo {} | sudo -S dd if={} of=/dev/{} bs=1M oflag=direct; sync"\
            .format(HostLinuxCreds.get_password(), os.path.join(WRSROOT_HOME, "bootimage.iso"), usb_part1)

        rc,  output = con_ssh.exec_cmd(cmd, expect_timeout=900)
        if rc == 0:
            LOG.info(" The backup build iso file copied to USB for restore. {}".format(output))
            return True
        else:
            LOG.error("Failed to copy backup build iso file to USB {}: {}".format(usb_part1, output))
            return False

    else:
        LOG.tc_step("Copying  load image ISO to local test server: {} ...".format(backup_dest_path))
        common.scp_from_active_controller_to_test_server(os.path.join(WRSROOT_HOME, "bootimage.iso"), backup_dest_path)
        LOG.info(" The backup build iso file copied to local test server: {}".format(backup_dest_path))
        return True

