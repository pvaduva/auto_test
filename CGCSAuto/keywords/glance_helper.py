import random
import time
import re
import json

from pytest import skip

from utils import table_parser, cli, exceptions
from utils.tis_log import LOG
from utils.ssh import ControllerClient, NATBoxClient
from consts.auth import Tenant, SvcCgcsAuto, HostLinuxCreds
from consts.timeout import ImageTimeout
from consts.cgcs import Prompt, GuestImages
from consts.proj_vars import ProjVar
from keywords import common, storage_helper, system_helper, host_helper


def get_images(images=None, rtn_val='id', auth_info=Tenant.ADMIN, con_ssh=None, strict=True, exclude=False, **kwargs):
    """
    Get a list of image id(s) that matches the criteria
    Args:
        images (str|list): ids of images to filter from
        rtn_val(str): id or name
        auth_info (dict):
        con_ssh (SSHClient):
        strict (bool): match full string or substring for the value(s) given in kwargs.
            This is only applicable if kwargs key-val pair(s) are provided.
        exclude (bool): whether to exclude item containing the string/pattern in kwargs.
            e.g., search for images that don't contain 'raw'
        **kwargs: header-value pair(s) to filter out images from given image list. e.g., Status='active', Name='centos'

    Returns (list): list of image ids

    """
    table_ = table_parser.table(cli.glance('image-list', ssh_client=con_ssh, auth_info=auth_info))
    if images:
        table_ = table_parser.filter_table(table_, ID=images)

    if not kwargs:
        return table_parser.get_column(table_, rtn_val)

    return table_parser.get_values(table_, rtn_val, strict=strict, exclude=exclude, **kwargs)


def get_image_id_from_name(name=None, strict=False, fail_ok=True, con_ssh=None, auth_info=None):
    """

    Args:
        name (list or str):
        strict:
        fail_ok (bool): whether to raise exception if no image found with provided name
        con_ssh:
        auth_info (dict:

    Returns:
        Return a random image_id that match the name. else return an empty string

    """
    table_ = table_parser.table(cli.glance('image-list', ssh_client=con_ssh, auth_info=auth_info))
    if name is None:
        name = GuestImages.DEFAULT_GUEST

    image_ids = table_parser.get_values(table_, 'ID', strict=strict, Name=name)
    image_id = '' if not image_ids else image_ids[0]

    if not image_id:
        msg = "No existing image found with name: {}".format(name)
        if fail_ok:
            LOG.warning(msg)
        else:
            raise exceptions.CommonError(msg)

    return image_id


def get_avail_image_space(con_ssh):
    """
    Get available disk space in GB on /opt/cgcs which is where glance images are saved at
    Args:
        con_ssh:

    Returns (float): e.g., 9.2

    """
    size = con_ssh.exec_cmd("df | grep '/opt/cgcs' | awk '{{print $4}}'", fail_ok=False)[1]
    size = float(size.strip()) / (1024 * 1024)
    return size


def is_image_storage_sufficient(img_file_path=None, guest_os=None, min_diff=0.05, con_ssh=None, image_host_ssh=None):
    """
    Check if glance image storage disk is sufficient to create new glance image from specified image
    Args:
        img_file_path (str): e.g., /home/wrsroot/images/tis-centos-guest.img
        guest_os (str): used if img_file_path is not provided. e,g., ubuntu_14, ge_edge, cgcs-guest, etc
        min_diff: minimum difference required between available space and specifiec size. e.g., 0.1G
        con_ssh (SSHClient): tis active controller ssh client
        image_host_ssh (SSHClient): such as test server ssh where image file was stored

    Returns (bool):

    """

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()
    if image_host_ssh is None:
        image_host_ssh = con_ssh

    file_size = get_image_size(img_file_path=img_file_path, guest_os=guest_os, ssh_client=image_host_ssh)
    avail_size = get_avail_image_space(con_ssh=con_ssh)

    return avail_size - file_size >= min_diff


def get_image_file_info(img_file_path=None, guest_os=None, ssh_client=None):
    """
    Get image file info as dictionary
    Args:
        img_file_path (str): e.g., /home/wrsroot/images/tis-centos-guest.img
        guest_os (str): has to be specified if img_file_path is unspecified. e.g., 'tis-centos-guest'
        ssh_client (SSHClient): e.g.,  test server ssh

    Returns (dict): image info dict.
    Examples:
        {
            "virtual-size": 688914432,
            "filename": "images/cgcs-guest.img",
            "format": "raw",
            "actual-size": 688918528,
            "dirty-flag": false
        }

    """
    if not img_file_path:
        if guest_os is None:
            raise ValueError("Either img_file_path or guest_os has to be provided")
        else:
            img_file_info = GuestImages.IMAGE_FILES.get(guest_os, None)
            if not img_file_info:
                raise ValueError("Invalid guest_os provided. Choose from: {}".format(GuestImages.IMAGE_FILES.keys()))
            # Assume ssh_client is test server client and image path is test server path
            img_file_path = "{}/{}".format(GuestImages.IMAGE_DIR_REMOTE, img_file_info[0])

    def _get_img_dict(ssh_):
        img_info = ssh_.exec_cmd("qemu-img info --output json {}".format(img_file_path), fail_ok=False)[1]
        return json.loads(img_info)

    if ssh_client is None:
        with host_helper.ssh_to_test_server() as ssh_client:
            img_dict = _get_img_dict(ssh_=ssh_client)
    else:
        img_dict = _get_img_dict(ssh_=ssh_client)

    LOG.info("Image {} info: {}".format(img_file_path, img_dict))
    return img_dict


def get_image_size(img_file_path=None, guest_os=None, virtual_size=False, ssh_client=None):
    """
    Get image virtual or actual size in GB via qemu-img info
    Args:
        img_file_path (str): e.g., /home/wrsroot/images/tis-centos-guest.img
        guest_os (str): has to be specified if img_file_path is unspecified. e.g., 'tis-centos-guest'
        virtual_size:
        ssh_client:

    Returns (float): image size in GB
    """
    key = "virtual-size" if virtual_size else "actual-size"
    img_size = get_image_file_info(img_file_path=img_file_path, guest_os=guest_os, ssh_client=ssh_client)[key]
    img_size = float(img_size) / (1024 * 1024 * 1024)
    return img_size


def get_avail_image_conversion_space(con_ssh=None):
    """
    Get available disk space in GB on /opt/img-conversions
    Args:
        con_ssh:

    Returns (float): e.g., 19.2

    """
    size = con_ssh.exec_cmd("df | grep '/opt/img-conversions' | awk '{{print $4}}'")[1]
    size = float(size.strip()) / (1024 * 1024)
    return size


def is_image_conversion_sufficient(img_file_path=None, guest_os=None, min_diff=0.05, con_ssh=None, img_host_ssh=None):
    """
    Check if image conversion space is sufficient to convert given image to raw format
    Args:
        img_file_path (str): e.g., /home/wrsroot/images/tis-centos-guest.img
        guest_os (str): has to be specified if img_file_path is unspecified. e.g., 'tis-centos-guest'
        min_diff (int): in GB
        con_ssh:
        img_host_ssh

    Returns (bool):

    """
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    if not system_helper.get_storage_nodes(con_ssh=con_ssh):
        return True

    avail_size = get_avail_image_conversion_space(con_ssh=con_ssh)
    file_size = get_image_size(img_file_path=img_file_path, guest_os=guest_os, virtual_size=True,
                               ssh_client=img_host_ssh)

    return avail_size - file_size >= min_diff


def ensure_image_storage_sufficient(guest_os, con_ssh=None):
    with host_helper.ssh_to_test_server() as img_ssh:
        if not is_image_storage_sufficient(guest_os=guest_os, con_ssh=con_ssh, image_host_ssh=img_ssh):
            images_to_del = get_images(exclude=True, Name=GuestImages.DEFAULT_GUEST, con_ssh=con_ssh)
            if images_to_del:
                LOG.info("Delete non-default images due to insufficient image storage media to create required image")
                delete_images(images_to_del, check_first=False, con_ssh=con_ssh)
                if not is_image_storage_sufficient(guest_os=guest_os, con_ssh=con_ssh, image_host_ssh=img_ssh):
                    LOG.info("Insufficient image storage media to create {} image even after deleting non-default "
                             "glance images".format(guest_os))
                    return False
            else:
                LOG.info("Insufficient image storage media to create {} image".format(guest_os))
                return False

        return True


def create_image(name=None, image_id=None, source_image_file=None,
                 disk_format=None, container_format=None, min_disk=None, min_ram=None, public=None,
                 protected=None, cache_raw=False, store=None, wait=None, timeout=ImageTimeout.CREATE, con_ssh=None,
                 auth_info=Tenant.ADMIN, fail_ok=False, **properties):
    """
    Create an image with given criteria.

    Args:
        name (str): string to be included in image name
        image_id (str): id for the image to be created
        source_image_file (str): local image file to create image from. DefaultImage will be used if unset
        disk_format (str): One of these: ami, ari, aki, vhd, vmdk, raw, qcow2, vdi, iso
        container_format (str):  One of these: ami, ari, aki, bare, ovf
        min_disk (int): Minimum size of disk needed to boot image (in gigabytes)
        min_ram (int):  Minimum amount of ram needed to boot image (in megabytes)
        public (bool): Make image accessible to the public. True if unset.
        protected (bool): Prevent image from being deleted.
        cache_raw (bool): Convert the image to RAW in the background and store it for fast access
        store (str): Store to upload image to
        wait: Wait for the convertion of the image to RAW to finish before returning the image
        timeout (int): max seconds to wait for cli return
        con_ssh (SSHClient):
        auth_info (dict):
        fail_ok (bool):
        **properties: key=value pair(s) of properties to associate with the image

    Returns (tuple): (rtn_code(int), message(str))      # 1, 2 only applicable if fail_ok=True
        - (0, <id>, "Image <id> is created successfully")
        - (1, <id or ''>, <stderr>)     # glance image-create cli rejected
        - (2, <id>, "Image status is not active.")
    """

    # Use source image url if url is provided. Else use local img file.

    default_guest_img = GuestImages.IMAGE_FILES[GuestImages.DEFAULT_GUEST][2]
    file_path = source_image_file if source_image_file else "{}/{}".format(GuestImages.IMAGE_DIR, default_guest_img)
    if 'win' in file_path and 'os_type' not in properties:
        properties['os_type'] = 'windows'
    elif 'ge_edge' in file_path and 'hw_firmware_type' not in properties:
        properties['hw_firmware_type'] = 'uefi'

    source_str = file_path

    known_imgs = ['cgcs-guest', 'tis-centos-guest', 'ubuntu', 'cirros', 'opensuse', 'rhel', 'centos', 'win', 'ge_edge',
                  'vxworks']
    name = name if name else 'auto'
    for img_str in known_imgs:
        if img_str in name:
            break
        elif img_str in source_str:
            name = img_str + '_' + name
            break
    else:
        name_prefix = source_str.split(sep='/')[-1]
        name_prefix = name_prefix.split(sep='.')[0]
        name = name_prefix + '_' + name

    name = common.get_unique_name(name_str=name, existing_names=get_images(), resource_type='image')

    LOG.info("Creating glance image: {}".format(name))

    optional_args = {
        '--id': image_id,
        '--name': name,
        '--visibility': 'private' if public is False else 'public',
        '--protected': protected,
        '--store': store,
        '--disk-format': disk_format if disk_format else 'qcow2',
        '--container-format': container_format if container_format else 'bare',
        '--min-disk': min_disk,
        '--min-ram': min_ram,
        '--file': file_path,
        '--wait': 0 if wait else 1
    }
    optional_args_str = ''
    if cache_raw:
        optional_args_str += ' --cache-raw'
    if properties:
        for key, value in properties.items():
            optional_args_str = "{} --property {}={}".format(optional_args_str, key, value)

    for key, value in optional_args.items():
        if value is not None:
            optional_args_str = ' '.join([optional_args_str, key, str(value)])
    try:
        code, output = cli.glance('image-create', optional_args_str, ssh_client=con_ssh, fail_ok=fail_ok,
                                  auth_info=auth_info, timeout=timeout, rtn_list=True)
    except:
        # This is added to help debugging image-create failure in case of insufficient space
        if con_ssh is None:
            con_ssh = ControllerClient.get_active_controller()
        con_ssh.exec_cmd('df -h', fail_ok=True, get_exit_code=False)
        raise

    table_ = table_parser.table(output)
    actual_id = table_parser.get_value_two_col_table(table_, 'id')

    if code == 1:
        return 1, actual_id, output

    in_active = wait_for_image_states(actual_id, con_ssh=con_ssh, auth_info=auth_info, fail_ok=fail_ok)
    if not in_active:
        return 2, actual_id, "Image status is not active."

    if image_id and image_id != actual_id:
        msg = "Actual image id - {} is different than requested id - {}.".format(actual_id, image_id)
        if fail_ok:
            return 3, actual_id, msg
        raise exceptions.ImageError(msg)

    msg = "Image {} is created successfully".format(actual_id)
    LOG.info(msg)
    return 0, actual_id, msg


def wait_for_image_states(image_id, status='active', timeout=ImageTimeout.STATUS_CHANGE, check_interval=3,
                          fail_ok=True, con_ssh=None, auth_info=None):
    end_time = time.time() + timeout
    while time.time() < end_time:
        table_ = table_parser.table(cli.glance('image-show', image_id, ssh_client=con_ssh, auth_info=auth_info))
        actual_status = table_parser.get_value_two_col_table(table_, 'status')
        # table_ = table_parser.table(cli.glance('image-list', ssh_client=con_ssh, auth_info=auth_info))
        # actual_status = table_parser.get_values(table_, 'Status', ID=image_id)[0]

        if status.lower() == actual_status.lower():
            LOG.info("Image {} has reached status: {}".format(image_id, status))
            return True

        time.sleep(check_interval)

    else:
        msg = "Timed out waiting for image {} status to change to {}. Actual status: {}".format(image_id, status,
                                                                                                actual_status)
        if fail_ok:
            LOG.warning(msg)
            return False
        raise exceptions.TimeoutException(msg)


def _wait_for_images_deleted(images, timeout=ImageTimeout.STATUS_CHANGE, fail_ok=True,
                             check_interval=3, con_ssh=None, auth_info=Tenant.ADMIN):
    """
        check if a specific field still exist in a specified column of glance image-list

    Args:
        images (list|str):
        timeout (int):
        fail_ok (bool):
        check_interval (int):
        con_ssh:
        auth_info (dict):

    Returns (bool): Return True if the specific image_id is found within the timeout period. False otherwise

    """
    if isinstance(images, str):
        images = [images]

    imgs_to_check = list(images)
    imgs_deleted = []
    end_time = time.time() + timeout
    while time.time() < end_time:
        table_ = table_parser.table(cli.glance('image-list', ssh_client=con_ssh, auth_info=auth_info))
        existing_imgs = table_parser.get_column(table_, 'ID')

        for img in imgs_to_check:
            if img not in existing_imgs:
                imgs_to_check.remove(img)
                imgs_deleted.append(img)

        if not imgs_to_check:
            return True, tuple(imgs_deleted)

        time.sleep(check_interval)
    else:
        if fail_ok:
            return False, tuple(imgs_deleted)
        raise exceptions.TimeoutException("Timed out waiting for all given images to be removed from glance image-list"
                                          ". Given images: {}. Images still exist: {}.".format(images, imgs_to_check))


def image_exists(image_id, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Args:
        image_id:
        con_ssh:
        auth_info

    Returns:

    """
    exit_code, output = cli.glance('image-show', image_id, fail_ok=True, ssh_client=con_ssh, auth_info=auth_info)
    return exit_code == 0


def delete_images(images, timeout=ImageTimeout.DELETE, check_first=True, fail_ok=False, con_ssh=None,
                  auth_info=Tenant.ADMIN):
    """
    Delete given images

    Args:
        images (list|str): ids of images to delete
        timeout (int): max time wait for cli to return, and max time wait for images to remove from glance image-list
        check_first (bool): whether to check if images exist before attempt to delete
        fail_ok (bool):
        con_ssh (SSHClient):
        auth_info (dict):
    Returns (tuple):
        (-1, "None of the given image(s) exist on system. Do nothing.")
        (0, "image(s) deleted successfully")
        (1, <stderr>)    # if delete image cli returns stderr
        (2, "Delete image cli ran successfully but some image(s) <ids> did not disappear within <timeout> seconds")
    """
    if not images:
        return

    LOG.info("Deleting image(s): {}".format(images))

    if isinstance(images, str):
        images = [images]
    images_to_check = list(images)

    if check_first:
        imgs_to_del = get_images(images_to_check, auth_info=auth_info, con_ssh=con_ssh)
        if not imgs_to_del:
            msg = "None of the given image(s) exist on system. Do nothing."
            LOG.info(msg)
            return -1, msg

        if not imgs_to_del == images:
            LOG.info("Some image(s) don't exist. Given images: {}. images to delete: {}.".
                     format(images, imgs_to_del))
    else:
        imgs_to_del = images

    imgs_to_del_str = ' '.join(imgs_to_del)

    LOG.debug("images to delete: {}".format(imgs_to_del))
    exit_code, cmd_output = cli.glance('image-delete', imgs_to_del_str, ssh_client=con_ssh, fail_ok=fail_ok,
                                       rtn_list=True, auth_info=auth_info, timeout=timeout)

    if exit_code == 1:
        return 1, cmd_output

    LOG.info("Waiting for images to be removed from glance image-list: {}".format(imgs_to_del))
    all_deleted, images_deleted = _wait_for_images_deleted(imgs_to_del, fail_ok=fail_ok, con_ssh=con_ssh,
                                                           auth_info=auth_info, timeout=timeout)

    if not all_deleted:
        images_undeleted = set(imgs_to_del) - set(images_deleted)
        msg = "Delete image cli ran successfully but some image(s) {} did not disappear within {} seconds".\
            format(images_undeleted, timeout)
        return 2, msg

    LOG.info("image(s) are successfully deleted: {}".format(imgs_to_del))
    return 0, "image(s) deleted successfully"


def get_image_properties(image, property_keys, auth_info=Tenant.ADMIN, con_ssh=None):
    """

    Args:
        image (str): id of image
        property_keys (str|list): list of metadata key(s) to get value(s) for
        auth_info (dict): Admin by default
        con_ssh (SSHClient):

    Returns (dict): image metadata in a dictionary.
        Examples: {'hw_mem_page_size': small}
    """
    if isinstance(property_keys, str):
        property_keys = [property_keys]

    for property_key in property_keys:
        str(property_key).replace(':', '_')

    table_ = table_parser.table(cli.glance('image-show', image, ssh_client=con_ssh, auth_info=auth_info))
    results = {}
    for property_key in property_keys:
        property_key = property_key.strip()
        value = table_parser.get_value_two_col_table(table_, property_key, strict=True)
        if value:
            results[property_key] = value

    return results


def _scp_guest_image(img_os='ubuntu_14', dest_dir=GuestImages.IMAGE_DIR, timeout=3600, con_ssh=None):
    """

    Args:
        img_os (str): guest image os type. valid values: ubuntu, centos_7, centos_6
        dest_dir (str): where to save the downloaded image. Default is '~/images'
        con_ssh (SSHClient):

    Returns (str): full file name of downloaded image. e.g., '~/images/ubuntu_14.qcow2'

    """
    valid_img_os_types = list(GuestImages.IMAGE_FILES.keys())

    if img_os not in valid_img_os_types:
        raise ValueError("Invalid image OS type provided. Valid values: {}".format(valid_img_os_types))

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    dest_name = GuestImages.IMAGE_FILES[img_os][2]
    source_name = GuestImages.IMAGE_FILES[img_os][0]

    if dest_dir.endswith('/'):
        dest_dir = dest_dir[:-1]

    dest_path = '{}/{}'.format(dest_dir, dest_name)

    if con_ssh.file_exists(file_path=dest_path):
        LOG.info('image file {} already exists. Return existing image path'.format(dest_path))
        return dest_path

    LOG.debug('Create directory for image storage if not already exists')
    cmd = 'mkdir -p {}'.format(dest_dir)
    con_ssh.exec_cmd(cmd, fail_ok=False)

    source_path = '{}/images/{}'.format(SvcCgcsAuto.SANDBOX, source_name)
    source_ip = SvcCgcsAuto.SERVER
    source_user = SvcCgcsAuto.USER

    nat_name = ProjVar.get_var('NATBOX').get('name')
    if nat_name == 'localhost' or nat_name.startswith('128.224.'):
        nat_dest_path = '/tmp/{}'.format(dest_name)
        nat_ssh = NATBoxClient.get_natbox_client()
        if not nat_ssh.file_exists(nat_dest_path):
            LOG.info("scp image from test server to NatBox: {}".format(nat_name))
            nat_ssh.scp_on_dest(source_user=source_user, source_ip=source_ip, source_path=source_path,
                                dest_path=nat_dest_path, source_pswd=SvcCgcsAuto.PASSWORD, timeout=timeout)

        LOG.info('scp image from natbox {} to active controller'.format(nat_name))
        dest_user = HostLinuxCreds.get_user()
        dest_pswd = HostLinuxCreds.get_password()
        dest_ip = ProjVar.get_var('LAB').get('floating ip')
        nat_ssh.scp_on_source(source_path=nat_dest_path, dest_user=dest_user, dest_ip=dest_ip, dest_path=dest_path,
                              dest_password=dest_pswd, timeout=timeout)
        if not con_ssh.file_exists(dest_path):
            raise exceptions.CommonError("image {} does not exist after download".format(dest_path))
    else:
        LOG.info('scp image from test server to active controller')
        con_ssh.scp_on_dest(source_user=source_user, source_ip=source_ip, source_path=source_path,
                            dest_path=dest_path, source_pswd=SvcCgcsAuto.PASSWORD, timeout=timeout)

    LOG.info("{} image downloaded successfully and saved to {}".format(img_os, dest_path))
    return dest_path


def get_guest_image(guest_os, rm_image=True, check_disk=False):
    """
    Get or create a glance image with given guest OS
    Args:
        guest_os (str): valid values: ubuntu_12, ubuntu_14, centos_6, centos_7, opensuse_11, tis-centos-guest,
                cgcs-guest, vxworks-guest
        rm_image (bool): whether or not to rm image from /home/wrsroot/images after creating glance image
        check_disk (bool): whether to check if image storage disk is sufficient to create new glance image

    Returns (str): image_id

    """
    nat_name = ProjVar.get_var('NATBOX').get('name')
    if nat_name == 'localhost' or nat_name.startswith("128.224"):
        if re.search('win|rhel|opensuse', guest_os):
            skip("Skip tests with large images for vbox")

    LOG.info("Get or create a glance image with {} guest OS".format(guest_os))
    img_id = get_image_id_from_name(guest_os, strict=True)

    if not img_id:
        if check_disk:
            if not ensure_image_storage_sufficient(guest_os=guest_os):
                skip("Insufficient image storage space in /opt/cgcs/ to create {} image".format(guest_os))

        image_path = _scp_guest_image(img_os=guest_os)
        disk_format = 'raw' if guest_os == 'cgcs-guest' or 'vxworks-guest' else 'qcow2'
        try:
            img_id = create_image(name=guest_os, source_image_file=image_path, disk_format=disk_format,
                                  container_format='bare', fail_ok=False)[1]
        except:
            raise
        finally:
            if rm_image and not re.search('cgcs-guest|tis-centos|ubuntu_14', guest_os):
                con_ssh = ControllerClient.get_active_controller()
                con_ssh.exec_cmd('rm -f {}'.format(image_path), fail_ok=True, get_exit_code=False)

    return img_id
