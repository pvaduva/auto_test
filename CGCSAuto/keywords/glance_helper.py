import random
import time

from utils import table_parser, cli, exceptions
from utils.tis_log import LOG
from utils.ssh import ControllerClient
from consts.auth import Tenant, SvcCgcsAuto
from consts.timeout import ImageTimeout
from consts.cgcs import IMAGE_DIR, Prompt
from keywords.common import Count


def get_images(images=None, auth_info=Tenant.ADMIN, con_ssh=None, strict=True, exclude=False, **kwargs):
    """
    Get a list of image id(s) that matches the criteria
    Args:
        images (str|list): ids of images to filter from
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
        return table_parser.get_column(table_, 'ID')

    return table_parser.get_values(table_, 'ID', strict=strict, exclude=exclude, **kwargs)


def get_image_id_from_name(name=None, strict=False, con_ssh=None, auth_info=None):
    """

    Args:
        name (list or str):
        strict:
        con_ssh:
        auth_info (dict:

    Returns:
        Return a random image_id that match the name. else return an empty string

    """
    table_ = table_parser.table(cli.glance('image-list', ssh_client=con_ssh, auth_info=auth_info))
    if name is None:
        image_id = random.choice(table_parser.get_column(table_, 'ID'))
    else:
        image_ids = table_parser.get_values(table_, 'ID', strict=strict, Name=name)
        image_id = '' if not image_ids else random.choice(image_ids)

    return image_id


def create_image(name=None, image_id=None, source_image_file=None,
                 disk_format=None, container_format=None, min_disk=None, min_ram=None, public=None,
                 protected=None, cache_raw=False, store=None, wait=None, timeout=ImageTimeout.CREATE, con_ssh=None,
                 auth_info=Tenant.ADMIN, fail_ok=False, **properties):
    """
    Create an image with given criteria.

    Args:
        name (str): string to be included in image name
        image_id (str): id for the image to be created
        source_image_file (str): local image file to create image from. '/home/wrsroot/images/cgcs-guest.img' if unset
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

    file_path = source_image_file if source_image_file else IMAGE_DIR + '/cgcs-guest.img'

    source_str = file_path

    known_imgs = ['cgcs-guest', 'centos', 'ubuntu', 'cirros']
    name = name if name else 'auto'
    for img_str in known_imgs:
        if img_str in source_str:
            name_prefix = img_str
            break
    else:
        name_prefix = source_str.split(sep='/')[-1]
        name_prefix = name_prefix.split(sep='.')[0]

    name = '_'.join([name_prefix, name, str(Count.get_image_count())])

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
        '--wait': wait
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

    code, output = cli.glance('image-create', optional_args_str, ssh_client=con_ssh, fail_ok=fail_ok,
                              auth_info=auth_info, timeout=timeout, rtn_list=True)

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


def _scp_guest_image(img_os='ubuntu', dest_dir=IMAGE_DIR, con_ssh=None):
    """

    Args:
        img_os (str): guest image os type. valid values: ubuntu, centos7, centos6
        dest_dir (str): where to save the downloaded image. Default is '~/images'
        con_ssh (SSHClient):

    Returns (str): full file name of downloaded image. e.g., '~/images/ubuntu.img'

    """
    valid_img_os_types = ['ubuntu', 'centos6', 'centos7']
    if img_os not in valid_img_os_types:
        raise ValueError("Invalid image OS type provided. Valid values: {}".format(valid_img_os_types))

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    # image_loc_dict = {
    #     'ubuntu': ['ubuntu.img',
    #                'https://cloud-images.ubuntu.com/precise/current/precise-server-cloudimg-amd64-disk1.img'],
    #     'centos6': ['centos6.qcow2', 'http://cloud.centos.org/centos/6/images/CentOS-6-x86_64-GenericCloud.qcow2'],
    #     'centos7': ['centos7.qcow2', 'http://cloud.centos.org/centos/7/images/CentOS-7-x86_64-GenericCloud.qcow2']
    # }

    image_loc_dict = {
        'ubuntu': 'ubuntu.img',
        'centos6': 'centos6.img',
        'centos7': 'centos7.img',
    }

    dest_name = image_loc_dict[img_os]

    if dest_dir.endswith('/'):
        dest_dir = dest_dir[:-1]

    dest_path = '{}/{}'.format(dest_dir, dest_name)

    if con_ssh.file_exists(file_path=dest_path):
        LOG.info('image file {} already exists. Return existing image path'.format(dest_path))
        return dest_path

    LOG.debug('Create directory for image storage if not already exists')
    cmd = 'mkdir -p {}'.format(dest_dir)
    con_ssh.exec_cmd(cmd, fail_ok=False)

    # LOG.info('wget image from {} to {}/{}'.format(img_url, img_dest, new_name))
    # cmd = 'wget {} --no-check-certificate -P {} -O {}'.format(img_url, img_dest, new_name)
    # con_ssh.exec_cmd(cmd, expect_timeout=7200, fail_ok=False)

    source_path = '{}/images/{}'.format(SvcCgcsAuto.HOME, dest_name)
    LOG.info('scp image from test server to active controller')
    scp_cmd = 'scp -oStrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null {}@{}:{} {}'.format(
            SvcCgcsAuto.USER, SvcCgcsAuto.SERVER, source_path, dest_dir)

    con_ssh.send(scp_cmd)
    index = con_ssh.expect([con_ssh.prompt, Prompt.PASSWORD_PROMPT, Prompt.ADD_HOST], timeout=3600)
    if index == 2:
        con_ssh.send('yes')
        index = con_ssh.expect([con_ssh.prompt, Prompt.PASSWORD_PROMPT], timeout=3600)
    if index == 1:
        con_ssh.send(SvcCgcsAuto.PASSWORD)
        index = con_ssh.expect()
    if index != 0:
        raise exceptions.SSHException("Failed to scp files")

    # common._scp_base(cmd, remote_password=SvcCgcsAuto.PASSWORD, timeout=3600)

    if not con_ssh.file_exists(file_path=dest_path):
        raise exceptions.CommonError("image {} does not exist after download".format(dest_path))

    LOG.info("{} image downloaded successfully and saved to {}".format(img_os, dest_path))
    return dest_path
