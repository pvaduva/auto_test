import random
import time

from consts.auth import Tenant
from consts.timeout import VolumeTimeout
from utils import table_parser, cli, exceptions
from utils.tis_log import LOG
from keywords import glance_helper


def get_volumes(vols=None, name=None, name_strict=False, vol_type=None, size=None, status=None, attached_vm=None,
                bootable='true', auth_info=None, con_ssh=None):
    """
    Return a list of volume ids based on the given criteria
    Args:
        vols:
        name:
        name_strict:
        vol_type:
        size:
        status:
        attached_vm:
        bootable:
        auth_info:
        con_ssh:

    Returns:

    """
    if bootable is not None:
        bootable = str(bootable).lower()
    optional_args = {
        'ID': vols,
        'Volume Type': vol_type,
        'Size': size,
        'Attached to': attached_vm,
        'Status': status,
        'Bootable': bootable
    }

    criteria = {}
    for key, value in optional_args.items():
        if value is not None:
            criteria[key] = value

    table_ = table_parser.table(cli.cinder('list', auth_info=auth_info, ssh_client=con_ssh))

    if name is not None:
        table_ = table_parser.filter_table(table_, strict=name_strict, **{'Display Name': name})

    if criteria:
        table_ = table_parser.filter_table(table_, **criteria)

    if name is None and not criteria:
        LOG.warning("No criteria specified, return a full list of volume ids for a tenant")

    return table_parser.get_column(table_, 'ID')


def create_volume(name=None, desc=None, image_id=None, source_vol_id=None, snapshot_id=None, vol_type=None, size=1,
                  avail_zone=None, metadata=None, bootable=True, fail_ok=False, auth_info=None, con_ssh=None,
                  rtn_exist=True):
    """

    Args:
        name (str): display name of the volume
        desc (str): description of the volume
        image_id (str): image_id to create volume from
        source_vol_id (str): source volume id to create volume from
        snapshot_id (str): snapshot_id to create volume from.
        vol_type (str): volume type such as 'raw'
        size (int): volume size in GBs
        avail_zone (str): availability zone
        metadata (str): metadata key and value pairs '[<key=value> [<key=value> ...]]'
        bootable: When False, the source id params will be ignored. i.e., a un-bootable volume will be created.
        fail_ok (bool):
        auth_info (dict):
        con_ssh (SSHClient):
        rtn_exist(bool):

    Returns:
        if fail_ok=False: (str) volume id
        if fail_ok=True: (list) [return_code, volume_id or err msg]
        [0, vol_id]: Volume created successfully
        [1, <stderr>]: cli is rejected with exit_code 1

    Notes: snapshot_id > source_vol_id > image_id if more than one source ids are provided.
    """
    if rtn_exist and name is not None:
        vol_ids = get_volumes(name=name, status='available', bootable='true')
        if vol_ids:
            LOG.info('Bootable volume(s) with name {} exists and in available state, return an existing volume.'.
                     format(name))
            return [-1, vol_ids[0]]

    subcmd = ''
    source_arg = ''
    if bootable:
        if snapshot_id:
            source_arg = '--snapshot-id ' + snapshot_id
        elif source_vol_id:
            source_arg = '--source-volid ' + source_vol_id
        else:
            image_id = image_id if image_id is not None else glance_helper.get_image_id_from_name('cgcs-guest')
            source_arg = '--image-id ' + image_id

    optional_args = {'--display-name': name,
                     '--display-description': desc,
                     '--volume-type': vol_type,
                     '--availability-zone': avail_zone,
                     '--metadata': metadata}

    for key, value in optional_args.items():
        if value is not None:
            subcmd = ' '.join([subcmd.strip(), key, value.lower().strip()])

    subcmd = ' '.join([subcmd, source_arg, str(size)])
    exit_code, cmd_output = cli.cinder('create', subcmd, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                                       rtn_list=True)

    LOG.info("Post action check started for create volume.")
    if exit_code == 1:
        return [1, cmd_output]

    table_ = table_parser.table(cmd_output)
    volume_id = table_parser.get_value_two_col_table(table_, 'id')

    if not _wait_for_volume_status(vol_id=volume_id, status='available', fail_ok=fail_ok):
        LOG.warning("Volume is created, but not in available state.")
        return [2, volume_id]

    bootable = str(bootable).lower()
    actual_bootable = get_volume_states(volume_id, fields='bootable', con_ssh=con_ssh, auth_info=auth_info)['bootable']
    if bootable != actual_bootable:
        if fail_ok:
            LOG.warning("Volume bootable state is not {}".format(bootable))
            return [3, volume_id]
        else:
            raise exceptions.VolumeError("Volume {} bootable value should be {} instead of {}".
                                         format(volume_id, bootable, actual_bootable))

    LOG.info("Volume is created and in available state: {}".format(volume_id))
    return [0, volume_id]


def get_volume_states(vol_id, fields, con_ssh=None, auth_info=None):
    table_ = table_parser.table(cli.cinder('show', vol_id, ssh_client=con_ssh, auth_info=auth_info))
    if isinstance(fields, str):
        fields = [fields]
    states = {}
    for field in fields:
        value = table_parser.get_value_two_col_table(table_, field=field)
        states[field] = value

    return states


def _wait_for_volume_status(vol_id, status='available', timeout=VolumeTimeout.STATUS_CHANGE, fail_ok=True,
                            check_interval=3, con_ssh=None, auth_info=None):

    end_time = time.time() + timeout
    current_status = ''
    while time.time() < end_time:
        table_ = table_parser.table(cli.cinder('show', vol_id, ssh_client=con_ssh, auth_info=auth_info))
        current_status = table_parser.get_value_two_col_table(table_, 'status')
        if current_status == status:
            return True
        elif current_status == 'error':
            show_vol_tab = table_parser.table(cli.cinder('show', vol_id, ssh_client=con_ssh, auth_info=auth_info))
            error_msg = table_parser.get_value_two_col_table(show_vol_tab, 'error')
            if fail_ok:
                LOG.warning("Volume {} is in error state! Details: {}".format(vol_id, error_msg))
                return False
            raise exceptions.VolumeError(error_msg)

        time.sleep(check_interval)
    else:
        if fail_ok:
            return False
        raise exceptions.TimeoutException("Timed out waiting for volume {} status to reach status: {}. "
                                          "Actual status: {}".format(vol_id, status, current_status))


def get_snapshot_id(status='available', vol_id=None, name=None, size=None, con_ssh=None, auth_info=None):
    """
    Get one volume snapshot id that matches the given criteria.

    Args:
        status (str): snapshot status. e.g., 'available', 'in use'
        vol_id (str): volume id the snapshot was created from
        name (str): snapshot name
        size (int):
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (str): snapshot id. Return None if no matching snapshot found.

    """
    table_ = table_parser.table(cli.cinder('snapshot-list', ssh_client=con_ssh, auth_info=auth_info))
    if size is not None:
        size = str(size)
    possible_args = {
        'status': status,
        "Volume ID": vol_id,
        'Status': status,
        'Display Name': name,
        'Size': size
    }

    args_ = {}
    for key, val in possible_args.items():
        if val:
            args_[key] = val
    ids = table_parser.get_values(table_, 'ID', **args_)
    if not ids:
        return None

    return random.choice(ids)


def _wait_for_volume_in_cinder_list(volume_id,column='ID', timeout=VolumeTimeout.STATUS_CHANGE, fail_ok=True,
            check_interval=3,con_ssh=None, auth_info=None):
    """
        check if a specific field still exist in a specified column
        an id in cinder list's ID column
        an id in nova list's ID column
        etc...
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        table_ = table_parser.table(cli.cinder('list', ssh_client=con_ssh, auth_info=auth_info))
        ids_list = table_parser.get_column(table_, column)

        if volume_id not in ids_list:
            return True
        time.sleep(check_interval)
    else:
        if fail_ok:
            return False
        raise exceptions.TimeoutException("Timed out waiting for {} to not be in column {}. "
                                          "Actual still in column".format(volume_id, column))


def volume_exists(volume_id, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Args:
        volume_id:
        con_ssh:
        auth_info

    Returns:
        return
    """
    exit_code, output = cli.cinder('show', volume_id, fail_ok=True, ssh_client=con_ssh, auth_info=auth_info)
    return exit_code == 0


def delete_volume(volume_id,fail_ok=False, con_ssh=None, auth_info=None):

    """
    Args:
        volume_id (str): id of the volume
        fail_ok (bool): raise local exception based off result from cli.cinder
        con_ssh (SSHClient):
    Returns:
        a boolean: True if volume successfully deleted, raise exception otherwise

    """
    # if volume doesn't exist return [-1,'']
    if volume_id is not None:
        v_exist = volume_exists(volume_id)
        if not v_exist:
            LOG.info("To be deleted Volume: {} does not exists.".format(volume_id))
            return [-1, '']

    # execute the delete command
    exit_code, cmd_output = cli.cinder('delete', volume_id, ssh_client=con_ssh, fail_ok=fail_ok, rtn_list=True,
                auth_info=auth_info)

    if exit_code == 1:
        return [1, cmd_output]

    # check if the volume is deleted
    vol_status = _wait_for_volume_in_cinder_list(volume_id, column='ID',fail_ok=fail_ok)

    if not vol_status:
        if fail_ok:
            LOG.warning("deletion command is executed but '{}' still show up within cinder list".format(volume_id))
            return [2, volume_id]
        raise exceptions.VolumeError("deletion command is executed but '{}' "
                                     "still show up within cinder list".format(volume_id))

    LOG.info("Volume {} is deleted .".format(volume_id))
    return [0, '']
