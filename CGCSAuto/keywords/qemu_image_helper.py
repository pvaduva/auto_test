"""
This module provides helper functions for qemu-img commands
"""

from utils import cli, exceptions
from utils.tis_log import LOG


def image_info(image_filename, conn_ssh=None, fail_ok=False):
    """
    Provides information about the disk image filename, like file format, virtual size and disk size
    Args:
        image_filename (str); the disk image file name
        conn_ssh:
        fail_ok:

    Returns:
        0, dict { image: <image name>, format: <format>, virtual size: <size>, disk size: <size}
        1, error msg

    """
    img_info = {}
    cmd = 'info {}'.format(image_filename)
    rc, output = cli.qemu_img(cmd, fail_ok=True)
    if rc == 0:
        lines = output.split('\n')
        for line in lines:
            key = line.split(':')[0].strip()
            value = line.split(':')[1].strip()
            img_info[key] = value

        return 0, img_info
    else:
        msg = "qemu-img info failed: {}".format(output)
        LOG.warning(msg)
        if fail_ok:
            return 1, msg
        else:
            raise exceptions.CommonError(msg)


def convert_image_format(src_image_filename, dest_image_filename, dest_format, source_format=None, conn_ssh=None,
                         fail_ok=False):
    """
    Converts the src_image_filename to  dest_image_filename using format dest_format
    Args:
       src_image_filename (str):  the source disk image filename to be converted
       dest_image_filename (str): the destination disk image filename
       dest_format (str): image format to convert to. Valid formats are: qcow2, qed, raw, vdi, vpc, vmdk
       source_format(str): optional - source image file format
       conn_ssh:
       fail_ok:

    Returns:

    """

    args_ = ''
    if source_format:
       args_ += ' -f {}'.format(source_format)


    cmd = 'convert {} {} {}'.format(args_, src_image_filename, dest_image_filename)
    rc, output = cli.qemu_img(cmd, fail_ok=True)
    if rc == 0:
        return 0, "Disk image {} converted to {} format successfully".format(dest_image_filename, dest_format)
    else:
        msg = "qemu-img convert failed: {}".format(output)
        LOG.warning(msg)
        if fail_ok:
            return 1, msg
        else:
            raise exceptions.CommonError(msg)