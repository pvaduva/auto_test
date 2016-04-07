import random
import time

from utils import table_parser, cli, exceptions
from utils.tis_log import LOG
from consts.auth import Tenant
from consts.timeout import VolumeTimeout


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


def create_image(name, desc=None, source='image location', format='raw', min_disk=None, min_ram=None, copy_data=True,
                 live_mig_timeout=800, live_mig_max_downtime=500, public=False, protected=False,
                 instance_auto_recovery=True):
    raise NotImplementedError


def get_any_image(con_ssh=None, auth_info=None):
    table_ = table_parser.table(cli.glance('image-list', ssh_client=con_ssh, auth_info=auth_info))
    return random.choice(table_parser.get_column(table_, 'ID'))


def _wait_for_image_deleted(image_id,column='ID', timeout=VolumeTimeout.STATUS_CHANGE, fail_ok=True,
                            check_interval=3, con_ssh=None, auth_info=None):
    """

        check if a specific field still exist in a specified column of glance image-list

    Args:
        image_id (str):
        column (str):
        timeout (int):
        fail_ok (bool):
        check_interval (int):
        con_ssh:
        auth_info (dict):

    Returns (bool): Return True if the specific image_id is found within the timeout period. False otherwise

    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        table_ = table_parser.table(cli.glance('image-list', ssh_client=con_ssh, auth_info=auth_info))
        ids_list = table_parser.get_column(table_, column)

        if image_id not in ids_list:
            return True
        time.sleep(check_interval)
    else:
        if fail_ok:
            return False
        raise exceptions.TimeoutException("Timed out waiting for {} to not be in column {}. "
                                          "Actual still in column".format(image_id, column))


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


def delete_image(image_id, fail_ok=False, con_ssh=None, auth_info=Tenant.TENANT_1):
    """

    Args:
        image_id (str):
        fail_ok (bool):
        con_ssh:
        auth_info (dict):
    Returns:
        [-1,''] if image does not exist
        [0,''] image is successfully deleted.
        [1,output] if delete image cli errored when executing
        [2,vm_id] if delete image cli executed but still show up in nova list
    """

    # check if image exist
    if image_id is not None:
        v_exist = image_exists(image_id)
        if not v_exist:
            LOG.info("To be deleted Image: {} does not exists.".format(image_id))
            return [-1, '']

    # delete image
    exit_code, cmd_output = cli.glance('image-delete', image_id, ssh_client=con_ssh, fail_ok=fail_ok, rtn_list=True,
                                       auth_info=auth_info)

    if exit_code == 1:
        return [1, cmd_output]

    # check image is successfully deleted
    vol_status = _wait_for_image_deleted(image_id, column='ID', fail_ok=fail_ok)

    if not vol_status:
        if fail_ok:
            LOG.warning("deletion command is executed but '{}' still show up within glance image-list".format(image_id))
            return [2, image_id]
        raise exceptions.ImageError("deletion command is executed but '{}' "
                                    "still show up within glance image-list".format(image_id))

    LOG.info("Image {} is deleted .".format(image_id))
    return [0, '']
