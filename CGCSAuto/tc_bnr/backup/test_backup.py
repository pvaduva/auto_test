import os
import re
import time
import random
import configparser
import pexpect.exceptions

from pytest import fixture, skip

from consts.auth import Tenant, SvcCgcsAuto, HostLinuxCreds
from consts.build_server import Server
from consts.cgcs import TIS_BLD_DIR_REGEX, BackupRestore, PREFIX_BACKUP_FILE
from consts.filepaths import BuildServerPath, WRSROOT_HOME
from consts.proj_vars import InstallVars, ProjVar, BackupVars

from keywords import cinder_helper
from keywords import common
from keywords import host_helper
from keywords import html_helper
from keywords import install_helper
from keywords import keystone_helper
from keywords import glance_helper
from keywords import nova_helper
from keywords import system_helper
from keywords import vm_helper

from utils.clients.ssh import ControllerClient, NATBoxClient
from utils.tis_log import LOG
from setups import collect_tis_logs

cinder_export_deprecated = '2018-09-12'


def collect_logs(msg):
    """
    Collect logs on the current system

    Args:

    Returns:
    """
    active_controller = ControllerClient.get_active_controller()
    try:
        LOG.info('collecting logs: ' + msg)
        collect_tis_logs(active_controller)
    except pexpect.exceptions.TIMEOUT:
        active_controller.flush()
        active_controller.exec_cmd('cat /etc/buid.info')


@fixture(scope='function')
def pre_system_backup():
    """
    Actions before system backup, including:
        - check the USB device is ready if it is the destination
        - create folder for the backup files on destination server
        - collect logs on the current system

    Args:

    Returns:
    """
    lab = InstallVars.get_install_var('LAB')

    LOG.info("Preparing lab for system backup....")
    backup_dest = BackupVars.get_backup_var("BACKUP_DEST")

    NATBoxClient.set_natbox_client()

    _backup_info = {'backup_dest': backup_dest,
                    'usb_parts_info': None,
                    'backup_dest_full_path': None,
                    'dest_server': None
                    }

    if backup_dest == 'usb':
        _backup_info['dest'] = 'usb'
        active_controller_name = system_helper.get_active_controller_name()
        if active_controller_name != 'controller-0':
            msg = "controller-0 is not the active controller"
            LOG.info(msg + ", try to swact the host")
            host_helper.swact_host(active_controller_name)
            active_controller_name = system_helper.get_active_controller_name()
            assert active_controller_name == 'controller-0', msg

        LOG.fixture_step("Checking if  a USB flash drive is plugged in controller-0 node... ")
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
        _backup_info['dest'] = 'local'

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

    collect_logs('before_br')

    _backup_info['is_storage_lab'] = (len(system_helper.get_storage_nodes()) > 0)
    return _backup_info


def backup_sysconfig_images(backup_info):
    """
    Backup system images on storage lab

    Args:
        backup_info - settings for doing system backup

    Returns:
        None
    """

    backup_dest = backup_info['backup_dest']
    backup_dest_path = backup_info['backup_dest_full_path']
    dest_server = backup_info['dest_server']
    copy_to_usb = backup_info['copy_to_usb']

    install_helper.backup_system(backup_dest=backup_dest, backup_dest_path=backup_dest_path,
                                 dest_server=dest_server, copy_to_usb=copy_to_usb)

    # storage lab start backup image files separately if it's a storage lab
    # if number of storage nodes is greater than 0
    if len(system_helper.get_storage_nodes()) > 0:
        LOG.tc_step("Storage lab detected. copying images to backup.")
        image_ids = glance_helper.get_images()
        for img_id in image_ids:
            prop_key = 'store'
            image_properties = glance_helper.get_image_properties(img_id, prop_key, rtn_dict=True)
            LOG.debug('image store backends:{}'.format(image_properties))

            if image_properties and image_properties.get(prop_key, None) == 'rbd':
                LOG.info('rbd based image, exporting it: {}, store:{}'.format(img_id, image_properties))

                install_helper.export_image(img_id, backup_dest=backup_info['backup_dest'],
                                            backup_dest_path=backup_info['backup_dest_full_path'],
                                            dest_server=backup_info['dest_server'],
                                            copy_to_usb=backup_info['copy_to_usb'])
            else:
                LOG.warn('No property found!!! for image {}, properties:{}'.format(img_id, image_properties))
                prop_key = 'direct_url'
                direct_url = glance_helper.get_image_properties(img_id, prop_key)[0]
                LOG.info(
                    'found direct_url, still consider it as rbd based image, exporting it: {}, stores:{}'.format(
                        img_id, image_properties))

                if direct_url and direct_url.startswith('rbd://'):
                    install_helper.export_image(img_id, backup_dest=backup_dest,
                                                backup_dest_path=backup_dest_path,
                                                dest_server=dest_server,
                                                copy_to_usb=copy_to_usb)
                else:
                    LOG.warn('non-rbd based image, skip it:  {}, store:{}'.format(img_id, image_properties))


def is_cinder_export_supported(build_info):
    """
    Check if CLI 'cinder export' is no longer supported on the specified load

    Args:
        build_info - build information

    Return:
         True - CLI 'cinder export' is still supported
         False - CLI 'cinder export' is not suppported anymore
    """

    return build_info.get('BUILD_ID', '9999') < cinder_export_deprecated


def backup_cinder_volumes(backup_info):
    """
    Backup cinder volumes

    Args:
        backup_info - settings for doing system backup

    Returns:
        None
    """

    LOG.tc_step("Cinder Volumes backup ...")

    backup_dest = backup_info.get('backup_dest', None)
    dest_server = backup_info.get('dest_server', None)
    copy_to_usb = backup_info.get('copy_to_usb', None)
    cinder_backup = backup_info.get('cinder_backup', False)

    if not is_cinder_export_supported(get_build_info()):
        LOG.warning('cinder export is NOT supported on this load, forced to use "cinder backup-xxxx"')
        cinder_backup = True

    vol_ids = cinder_helper.get_volumes(auth_info=Tenant.get('admin'), status='Available')
    vol_ids += cinder_helper.get_volumes(auth_info=Tenant.get('admin'), status='in-use')
    if len(vol_ids) > 0:
        LOG.info("Exporting cinder volumes: {}".format(vol_ids))
        exported = install_helper.export_cinder_volumes(backup_dest=backup_dest,
                                                        backup_dest_path=backup_info['backup_dest_full_path'],
                                                        dest_server=dest_server,
                                                        copy_to_usb=copy_to_usb,
                                                        con_ssh=backup_info['con_ssh'],
                                                        cinder_backup=cinder_backup)

        assert len(exported) > 0, "None volume was successfully exported"
        assert len(exported) == len(vol_ids), "Some volumes failed export: {}".format(set(vol_ids)-set(exported))
    else:
        LOG.info("No cinder volumes are avaialbe or in-use states in the system; skipping cinder volume export...")


def test_backup(pre_system_backup):
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
    LOG.info('Before backup, perform configuration changes and launch VMs')

    con_ssh = ControllerClient.get_active_controller()
    backup_info['con_ssh'] = con_ssh

    is_ceph = backup_info.get('is_storage_lab', False)
    LOG.debug('This is a {} lab'.format('Storage/Ceph' if is_ceph else 'Non-Storage/Ceph'))

    if is_ceph:
        con_ssh.exec_sudo_cmd('touch /etc/ceph/ceph.client.None.keyring')
        pre_backup_test(backup_info, con_ssh)

    lab = InstallVars.get_install_var('LAB')
    LOG.tc_step("System backup: lab={}; backup dest = {} backup destination path = {} ..."
                .format(lab['name'], backup_info['backup_dest'], backup_info['backup_dest_full_path']))
    copy_to_usb = None
    usb_part2 = None

    backup_dest = backup_info['backup_dest']
    if backup_dest == 'usb':
        usb_partition_info = backup_info['usb_parts_info']
        for k, v in usb_partition_info.items():
            if k[-1:] == "1":
                pass
                # usb_part1 = k
            elif k[-1:] == '2':
                usb_part2 = k
        copy_to_usb = usb_part2

    backup_info['copy_to_usb'] = copy_to_usb
    backup_info['backup_file_prefix'] = get_backup_file_name_prefix(backup_info)
    backup_info['cinder_backup'] = BackupVars.get_backup_var('cinder_backup')
    reinstall_storage = BackupVars.get_backup_var('reinstall_storage')

    if reinstall_storage:
        if is_ceph:
            backup_cinder_volumes(backup_info)

        backup_sysconfig_images(backup_info)
    else:
        # if is_ceph:
        #     backup_cinder_volumes(backup_info)

        backup_sysconfig_images(backup_info)

    collect_logs('after_backup')

    if system_helper.is_avs(con_ssh=con_ssh):
        # Copying system backup ISO file for future restore
        assert backup_load_iso_image(backup_info)


def backup_load_iso_image(backup_info):
    """
    Save a copy of the bootimage.iso for later restore.

    Args:
        backup_info

    Returns:
        True - the ISO is successfully copied to backup server
             - False otherwise
    """

    backup_dest = backup_info['backup_dest']
    backup_dest_path = backup_info['backup_dest_full_path']

    load_path = ProjVar.get_var('BUILD_PATH')
    build_id = ProjVar.get_var('BUILD_ID')
    assert re.match(TIS_BLD_DIR_REGEX, build_id), "Invalid Build Id pattern"

    build_server = ProjVar.get_var('BUILD_SERVER')
    if not (build_server and build_server.strip()):
        build_server = BuildServerPath.DEFAULT_BUILD_SERVER     # default

    with host_helper.ssh_to_build_server(bld_srv=build_server) as build_server_conn:

        cmd = "test -e " + load_path
        assert build_server_conn.exec_cmd(cmd, rm_date=False)[0] == 0,  'The system build {} not found in {}:{}'.\
            format(build_id, build_server, load_path)

        iso_file_path = os.path.join(load_path, "export", install_helper.UPGRADE_LOAD_ISO_FILE)

        if not build_server_conn.exec_cmd("test -e " + iso_file_path):
            LOG.warn("No ISO found on path:{}".format(iso_file_path))
            return True

        pre_opts = 'sshpass -p "{0}"'.format(HostLinuxCreds.get_password())
        # build_server_conn.rsync("-L " + iso_file_path, lab['controller-0 ip'],
        build_server_conn.rsync("-L " + iso_file_path, html_helper.get_ip_addr(),
                                os.path.join(WRSROOT_HOME, "bootimage.iso"),
                                pre_opts=pre_opts,
                                timeout=360)

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


def get_build_info():
    """
    Read in and parse the /etc/build.info and return a dictionary.

    Return:
        dictionary contains all information from /etc/buid.info
    """

    build_info = {}
    try:
        LOG.info('Getting build information')
        output = r'[dummy-head]\n' + system_helper.get_buildinfo()

        LOG.info('output:{}'.format(output))

        config = configparser.ConfigParser()
        config.read_string(output)

        for section in config.sections():
            LOG.info('section:{}'.format(section))
            for name, value in config.items(section):
                LOG.info('name:{}, value:{}'.format(name, value))
                build_info.update(name=value)

    except Exception as e:
        LOG.warn('failed to read build.info:{}'.format(e))

    return build_info


def adjust_cinder_quota(con_ssh, increase, backup_info):
    """
    Increase the quota for number of volumes for the tenant as which System Backup will be done.
    By default, it's 'tenant1'

    Args:
        con_ssh
            - current ssh connection

        increase
            - number of volumes to bump up

        backup_info
            - options for backup

    Return:
        increase
            - actual increased

        free_space
            - free space left for cinder volumes

        max_per_volume_size
            - max limit for an individual volume
    """

    if backup_info.get('is_storage_lab', False):
        free_space, total_space, unit = -1, -1, 1
    else:
        free_space, total_space, unit = cinder_helper.get_lvm_usage(con_ssh)

    LOG.info('lvm space: free:{}, total:{}'.format(free_space, total_space))

    quotas = ['gigabytes', 'per-volume-gigabytes', 'volumes']
    tenant = backup_info['tenant']
    cinder_quotas = vm_helper.get_quotas(quotas=quotas, auth_info=tenant, con_ssh=con_ssh)
    LOG.info('Cinder quotas:{}'.format(cinder_quotas))

    max_total_volume_size = int(cinder_quotas[0])
    max_per_volume_size = int(cinder_quotas[1])
    max_volumes = int(cinder_quotas[2])

    current_volumes = cinder_helper.get_volumes(auth_info=Tenant.get('admin'), con_ssh=con_ssh)

    LOG.info('Cinder VOLUME usage: current number of volumes:{}, quotas for {}: {}, '.format(
        len(current_volumes), quotas, cinder_quotas))

    if 0 < max_total_volume_size < free_space:
        free_space = max_total_volume_size

    new_volume_limit = len(current_volumes) + increase
    if 0 <= max_volumes < new_volume_limit:
        LOG.info('Not enough quota for number of cinder volumes, increase it to:{} from:{}'.format(
            new_volume_limit, max_volumes))
        code, output = vm_helper.set_quotas(tenant, con_ssh=con_ssh, volumes=new_volume_limit, fail_ok=True)
        if code > 0:
            LOG.info('Failed to increase the Cinder quota for number of volumes to:{} from:{}, error:{}'.format(
                new_volume_limit, max_volumes, output))
            increase = max_volumes - len(current_volumes)

    return increase, free_space, max_per_volume_size


def pb_create_volumes(con_ssh, volume_names=None, volume_sizes=None, backup_info=None):
    """
    Create volumes before doing System Backup.

    Args:
        con_ssh:
            - current ssh connection

        volume_names:
            - names of volumes to create

        volume_sizes:
            - sizes of volumes to create

        backup_info:
            - options for doing system backup

    Return:
        a dictionary of information for created volumes, including id, name, and size of volumes
    """
    LOG.info('Create VOLUMEs')

    if not volume_names:
        volume_names = ['vol_2G', 'vol_5G', 'vol_10G', 'vol_20G']

    if not volume_sizes:
        volume_sizes = [nm.split('_')[1][:-1] for nm in volume_names]
        if len(volume_sizes) < len(volume_names):
            volume_sizes = list(range(2, (2 + len(volume_names) * 2), 2))
            volume_sizes = volume_sizes[:len(volume_names) + 1]

    num_volumes, total_volume_size, per_volume_size = adjust_cinder_quota(con_ssh, len(volume_names), backup_info)

    volumes = {}
    count_volumes = 0
    if total_volume_size < 0:
        total_volume_size = 1 + sum([int(n) for n in volume_sizes])
    free_space = total_volume_size

    for name, size in zip(volume_names, volume_sizes):
        size = int(size)
        if 0 < per_volume_size < size:
            LOG.warn('The size of requested VOLUME is bigger than allowed, abort, requested:{}, allowed:{}'.format(
                size, per_volume_size))
            continue

        free_space -= size
        if free_space <= 0:
            LOG.warn('No more space in cinder-volumes for requested:{}, limit:{}, left free:{}'.format(
                size, total_volume_size, free_space))
            break

        LOG.info('-OK, attempt to create volume of size:{:05.3f}, free space left:{:05.3f}'.format(size, free_space))
        volme_id = cinder_helper.create_volume(name=name, size=size, auth_info=Tenant.TENANT1)

        volumes.update({volme_id: {'name': name, 'size': size}})

        count_volumes += 1
        if 0 < num_volumes < count_volumes:
            LOG.info('Too many of volumes created, abort')
            break

    LOG.info('OK, created {} volumes, total size:{}, volumes:{}'.format(count_volumes, total_volume_size, volumes))
    return volumes


def adjust_vm_quota(vm_count, con_ssh, backup_info=None):
    """
    Increase the quotas for creating VM if needed for the tenant in testing.
    The following quotas if any will be changed:
        instances
        cores       - make sure quota allows 2 cores for each VM
        ram         - make sure 2M for each VM

    Args:
        vm_count:
            - number of VMs

        con_ssh:
            - current ssh connection

        backup_info:
            - backup options for doing System Backup

    Return:
        None
    """

    tenant = backup_info['tenant']
    quota_details = vm_helper.get_quota_details_info('compute', resources='instances', tenant=tenant)['instances']
    min_instances_quota = vm_count + quota_details['in use'] + quota_details['reserved']

    if min_instances_quota > quota_details['limit']:
        LOG.info('Insufficient quota for instances, increase to: {}'.format(min_instances_quota))
        vm_helper.ensure_vms_quotas(vms_num=min_instances_quota, tenant=tenant, con_ssh=con_ssh)


def pb_launch_vms(con_ssh, image_ids, backup_info=None):
    """
    Launch VMs before doing System Backup

    Args
        con_ssh:
            - current ssh connection

        image_ids:
            - IDs of images, for which boot-from-image VMs will be launched

        backup_info:
            - options for doing System Backup

    Return:
        VMs created
    """

    vms_added = []

    if not image_ids:
        LOG.warn('No images to backup, backup_info:{}'.format(backup_info))
    else:
        LOG.info('-currently active images: {}'.format(image_ids))
        properties = ['name', 'status', 'visibility']
        for image_id in image_ids:
            name, status, visibility = glance_helper.get_image_properties(image_id, properties)
            if status == 'active' and name and 'centos-guest' in name:
                vm_type = 'virtio'
                LOG.info('launch VM of type:{} from image:{}, image-id:{}'.format(vm_type, name, image_id))
                vms_added += vm_helper.launch_vms(
                    vm_type,
                    image=image_id,
                    boot_source='image',
                    auth_info=Tenant.TENANT1,
                    con_ssh=con_ssh)[0]
                LOG.info('-OK, 1 VM from image boot up {}'.format(vms_added[-1]))
                break
            else:
                LOG.info('skip booting VMs from image:{}, id:{}'.format(name, image_id))

    vm_types = ['virtio']
    if system_helper.is_avs(con_ssh=con_ssh):
        vm_types += ['vswitch', 'dpdk', 'vhost']

    LOG.info('-launch VMs for different types:{}'.format(vm_types))

    LOG.info('-first make sure we have enough quota')
    vm_count = len(vms_added) + len(vm_types)
    adjust_vm_quota(vm_count, con_ssh, backup_info=backup_info)

    for vm_type in vm_types:
        vms_added += vm_helper.launch_vms(vm_type, auth_info=Tenant.TENANT1, con_ssh=con_ssh)[0]

    vms_added.append(vm_helper.boot_vm(auth_info=Tenant.TENANT1, con_ssh=con_ssh)[1])

    return vms_added


def pre_backup_setup(backup_info, con_ssh):
    """
    Setup before doing System Backup, including clean up existing VMs, snapshots, volumes and create volumes and VMs
    for B&R test purpose.

    Args:
        backup_info:
            - options to do system backup

        con_ssh:
            - current ssh connection

    Return:
         information of created VMs, Volumes, and Images
    """
    tenant = Tenant.TENANT1
    backup_info['tenant'] = tenant

    tenant_id = keystone_helper.get_tenant_ids(tenant_name=tenant['user'], con_ssh=con_ssh)[0]
    LOG.info('Using tenant:{} in the pre-backup test, details:{}'.format(tenant_id, tenant))
    LOG.info('Deleting VMs for pre-backup system-wide test')
    vm_helper.delete_vms()

    LOG.info('Deleting Volumes snapshots if any')
    cinder_helper.delete_volume_snapshots(auth_info=Tenant.get('admin'), con_ssh=con_ssh)

    LOG.info('Deleting Volumes')
    volumes = cinder_helper.get_volumes()
    LOG.info('-deleting volumes:{}'.format(volumes))
    cinder_helper.delete_volumes(volumes, timeout=180)

    LOG.info('Make sure we have glance images to backup')
    image_ids = glance_helper.get_images()

    LOG.info('Launching VMs')
    vms_added = pb_launch_vms(con_ssh, image_ids, backup_info=backup_info)

    LOG.info('Creating different sizes of VMs')
    volumes_added = pb_create_volumes(con_ssh, backup_info=backup_info)

    return {'vms': vms_added, 'volumes': volumes_added, 'images': image_ids}


def pb_migrate_test(backup_info, con_ssh, vm_ids=None):
    """
    Run migration test before doing system backup.

    Args:
        backup_info: 
            - options for doing backup

        con_ssh:
            - current ssh connection

        vm_ids
    Return:
        None
    """

    hyporvisors = host_helper.get_up_hypervisors(con_ssh=con_ssh)
    if len(hyporvisors) < 2:
        LOG.info('Only {} hyporvisors, it is not enougth to test migration'.format(len(hyporvisors)))
        LOG.info('Skip migration test')
        return 0
    else:
        LOG.debug('There {} hyporvisors'.format(len(hyporvisors)))

    LOG.info('Randomly choose some VMs and do migrate:')

    target = random.choice(vm_ids)
    LOG.info('-OK, test migration of VM:{}'.format(target))

    original_host = nova_helper.get_vm_host(target)
    LOG.info('Original host:{}'.format(original_host))

    vm_helper.live_migrate_vm(target)
    current_host = nova_helper.get_vm_host(target)
    LOG.info('After live-migration, host:{}'.format(original_host))

    if original_host == current_host:
        LOG.info('backup_info:{}'.format(backup_info))
        LOG.warn('VM is still on its original host, live-migration failed? original host:{}'.format(original_host))

    original_host = current_host
    vm_helper.cold_migrate_vm(target)
    current_host = nova_helper.get_vm_host(target)
    LOG.info('After code-migration, host:{}'.format(current_host))
    if original_host == current_host:
        LOG.warn('VM is still on its original host, code-migration failed? original host:{}'.format(original_host))


def lock_unlock_host(backup_info, con_ssh, vms):
    """
    Do lock & unlock hosts test before system backup.

    Args:
        backup_info:
            - options for system backup

        con_ssh:
            - current ssh connection to the target

        vms:
            - VMs on which their host to test
    Return:
        None
    """

    active_controller_name = system_helper.get_active_controller_name()

    target_vm = random.choice(vms)
    LOG.info('lock and unlock the host of VM:{}'.format(target_vm))

    target_host = nova_helper.get_vm_host(target_vm, con_ssh=con_ssh)
    if target_host == active_controller_name:
        if not system_helper.is_simplex():
            LOG.warning('Attempt to lock the active controller on a non-simplex system')
            host_helper.swact_host()

    active_controller_name = system_helper.get_active_controller_name()

    LOG.info('lock and unlock:{}'.format(target_host))

    host_helper.lock_host(target_host)
    if not system_helper.is_simplex():
        LOG.info('check if the VM is pingable')
        vm_helper.ping_vms_from_natbox(target_vm)
    else:
        LOG.info('skip pinging vm after locking the only node in a simlex system')

    LOG.info('unlock:{}'.format(target_host))
    host_helper.unlock_host(target_host)

    host_helper.wait_for_host_values(target_host,
                                     administrative='unlocked',
                                     availability='available',
                                     vim_progress_status='services-enabled')
    for tried in range(5):
        pingable, message = vm_helper.ping_vms_from_natbox(target_vm, fail_ok=(tried < 4))
        if pingable:
            LOG.info('failed to ping VM:{}, try again in 20 seconds'.format(target_vm))
            time.sleep(20)
        else:
            LOG.info('Succeeded to ping VM:{}'.format(target_vm))
            break
    if backup_info.get('dest', 'local') == 'usb':
        if active_controller_name != 'controller-0':
            LOG.info('current active_controller: ' + active_controller_name
                     + ', restore to controller-0 in case it was not after swact')
            host_helper.swact_host()
            active_controller_name = system_helper.get_active_controller_name()
            LOG.info('current active_controller should be restored to controller-0, actual:' + active_controller_name)


def pre_backup_test(backup_info, con_ssh):
    """
    Various (system) tests before doing system backup

    Args:
        backup_info:
            - options for system backup

        con_ssh:
            - current ssh connection to the target
    Return:
        None
    """

    LOG.tc_step('Pre-backup testing')
    LOG.info('Backup-info:{}'.format(backup_info))

    created = pre_backup_setup(backup_info, con_ssh)
    vms = created['vms']
    volumes = created['volumes']
    images = created['images']
    LOG.info('OK, createed VMs:{}, volumes:{}, images:{}'.format(vms, volumes, images))

    LOG.info('Do VM migration tests')
    pb_migrate_test(backup_info, con_ssh, vm_ids=vms)

    LOG.info('Lock and unlock computes')
    lock_unlock_host(backup_info, con_ssh, vms)


def get_backup_file_name_prefix(backup_info):
    """
    Construct the file name prefix for backup files

    Args:
        backup_info:
            - options for system backup

    Return:
        the core name of the backup files 
    """

    core_name = PREFIX_BACKUP_FILE
    if backup_info.get('dest', 'local') == 'usb':
        core_name += '.usb'
    if backup_info.get('is_storage_lab', False):
        core_name += '.ceph'

    return core_name
