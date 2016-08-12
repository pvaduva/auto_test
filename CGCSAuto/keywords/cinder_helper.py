import random
import time

from consts.auth import Tenant
from utils import table_parser, cli, exceptions
from utils.tis_log import LOG
from consts.timeout import VolumeTimeout
from keywords import glance_helper, keystone_helper


def get_any_volume(status='available', bootable=True, auth_info=None, con_ssh=None, new_name=None):
    """
    Get an id of any volume that meets the criteria. Create one if none exists.

    Args:
        vols (list|None): volumes list to get volume from. All volumes for given tenant if None.
        status (str):
        bootable (str|bool):
        auth_info (dict):
        con_ssh (SSHClient):
        new_name (str): This is only used if no existing volume found and new volume needs to be created

    Returns:
        str: volume id

    """
    volumes = get_volumes(status=status, bootable=bootable, auth_info=auth_info, con_ssh=con_ssh)
    if volumes:
        return 0, random.choice(volumes)
    else:
        return 1, create_volume(bootable=bootable, auth_info=auth_info, con_ssh=con_ssh, name=new_name,
                                rtn_exist=False)[1]


def get_volumes(vols=None, name=None, name_strict=False, vol_type=None, size=None, status=None, attached_vm=None,
                bootable=None, auth_info=Tenant.ADMIN, con_ssh=None):
    """
    Return a list of volume ids based on the given criteria

    Args:
        vols (list or str):
        name (str):
        name_strict (bool):
        vol_type (str):
        size (str):
        status:(str)
        attached_vm (str):
        bootable (str|bool): true or false
        auth_info (dict): could be Tenant.ADMIN,Tenant.TENANT_1,Tenant.TENANT_2
        con_ssh (str):

    Returns (list): a list of volume ids based on the given criteria
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

    table_ = table_parser.table(cli.cinder('list --all-tenants', auth_info=auth_info, ssh_client=con_ssh))

    if name is not None:
        table_ = table_parser.filter_table(table_, strict=name_strict, **{'Display Name': name})

    if criteria:
        table_ = table_parser.filter_table(table_, **criteria)

    if name is None and not criteria:
        LOG.warning("No criteria specified, return ids for all volumes for specific tenant")

    return table_parser.get_column(table_, 'ID')


def get_volumes_attached_to_vms(volumes=None, vms=None, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Filter out the volumes that are attached to a vm.
    Args:
        volumes (list or str): list of volumes ids to filter out from. When None, filter from all volumes
        vms (list or str): get volumes attached to given vm(s). When None, filter volumes attached to any vm
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (list): a list of volumes ids or [] if no match found

    """
    table_ = table_parser.table(cli.cinder('list --all-tenants', auth_info=auth_info, ssh_client=con_ssh))

    # Filter from given volumes if provided
    if volumes is not None:
        table_ = table_parser.filter_table(table_, ID=volumes)

    # Filter from given vms if provided
    if vms is not None:
        table_ = table_parser.filter_table(table_, **{'Attached to': vms})
    # Otherwise filter out volumes attached to any vm
    else:
        table_ = table_parser.filter_table(table_, strict=False, regex=True, **{'Attached to': '.*\S.*'})

    return table_parser.get_column(table_, 'ID')


def create_volume(name=None, desc=None, image_id=None, source_vol_id=None, snapshot_id=None, vol_type=None, size=None,
                  avail_zone=None, metadata=None, bootable=True, fail_ok=False, auth_info=None, con_ssh=None,
                  rtn_exist=False, guest_image=None):
    """
    Create a volume with given criteria.

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
        rtn_exist(bool): whether to return an existing available volume with matching name and bootable state.
        guest_image (str): guest image name if image_id unspecified. valid values: cgcs-guest, ubuntu, centos7, centos6

    Returns (tuple):  (return_code, volume_id or err msg)
        (-1, existing_vol_id)   # returns existing volume_id instead of creating a new one. Applies when rtn_exist=True.
        (0, vol_id)     # Volume created successfully and in available state.
        (1, <stderr>)   # Create volume cli rejected with sterr
        (2, vol_id)   # volume created, but not in available state.
        (3, vol_id]: if volume created, but not in given bootable state.

    Notes:
        snapshot_id > source_vol_id > image_id if more than one source ids are provided.
    """
    bootable = str(bootable).lower()

    if rtn_exist and name is not None:
        vol_ids = get_volumes(name=name, status='available', bootable=bootable)
        if vol_ids:
            LOG.info('Volume(s) with name {} and bootable state {} exists and in available state, return an existing '
                     'volume.'.format(name, bootable))
            return -1, vol_ids[0]

    subcmd = ''
    source_arg = ''
    if bootable:
        if snapshot_id:
            source_arg = '--snapshot-id ' + snapshot_id
        elif source_vol_id:
            source_arg = '--source-volid ' + source_vol_id
        else:
            guest_image = guest_image if guest_image else 'cgcs-guest'
            image_id = image_id if image_id is not None else glance_helper.get_image_id_from_name(guest_image)
            if size is None:
                size = 1 if 'cgcs-guest' in guest_image else 9

            source_arg = '--image-id ' + image_id

    optional_args = {'--display-name': name,
                     '--display-description': desc,
                     '--volume-type': vol_type,
                     '--availability-zone': avail_zone,
                     '--metadata': metadata}

    for key, value in optional_args.items():
        if value is not None:
            subcmd = ' '.join([subcmd.strip(), key, value.lower().strip()])

    size = 1 if size is None else size

    subcmd = ' '.join([subcmd, source_arg, str(size)])
    LOG.info("Creating volume: {}".format(name))
    exit_code, cmd_output = cli.cinder('create', subcmd, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                                       rtn_list=True)
    if exit_code == 1:
        return 1, cmd_output

    LOG.info("Post action check started for create volume.")

    table_ = table_parser.table(cmd_output)
    volume_id = table_parser.get_value_two_col_table(table_, 'id')

    if not _wait_for_volume_status(vol_id=volume_id, status='available',auth_info=auth_info, fail_ok=fail_ok):
        LOG.warning("Volume is created, but not in available state.")
        return 2, volume_id

    actual_bootable = get_volume_states(volume_id, fields='bootable', con_ssh=con_ssh, auth_info=auth_info)['bootable']
    if bootable != actual_bootable:
        if fail_ok:
            LOG.warning("Volume bootable state is not {}".format(bootable))
            return 3, volume_id
        raise exceptions.VolumeError("Volume {} bootable value should be {} instead of {}".
                                         format(volume_id, bootable, actual_bootable))

    LOG.info("Volume is created and in available state: {}".format(volume_id))
    return 0, volume_id


def get_volume_states(vol_id, fields, con_ssh=None, auth_info=Tenant.ADMIN):
    """

    Args:
        vol_id (str):
        fields (list or str):
        con_ssh (str):
        auth_info (dict):

    Returns (dict):
        A dict with field as key and value as value

    """
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
    """

    Args:
        vol_id (str):
        status (str):
        timeout (int):
        fail_ok (bool):
        check_interval (int):
        con_ssh (str):
        auth_info (dict):

    Returns:
        True if the status of the volume is same as the status(str) that was passed into the function \n
        false if timed out or otherwise

    """

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

    Returns:
        A string of snapshot id. Return None if no matching snapshot found.

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


def _wait_for_volumes_deleted(volumes, timeout=VolumeTimeout.DELETE, fail_ok=True,
                              check_interval=3, con_ssh=None, auth_info=Tenant.ADMIN):
    """
        check if a specific field still exist in a specified column for cinder list

    Args:
        volumes(list or str): ids of volumes
        timeout (int):
        fail_ok (bool):
        check_interval (int):
        con_ssh:
        auth_info (dict):

    Returns (tuple):    (result(boot), volumes_deleted(tuple))

    """
    if isinstance(volumes, str):
        volumes = [volumes]

    vols_to_check = list(volumes)
    vols_deleted = []
    end_time = time.time() + timeout
    while time.time() < end_time:
        table_ = table_parser.table(cli.cinder('list --all-tenants', ssh_client=con_ssh, auth_info=auth_info))
        existing_vols = table_parser.get_column(table_, 'ID')

        for vol in vols_to_check:
            if vol not in existing_vols:
                vols_to_check.remove(vol)
                vols_deleted.append(vol)

        if not vols_to_check:
            return True, tuple(vols_deleted)

        time.sleep(check_interval)
    else:
        if fail_ok:
            return False, tuple(vols_deleted)
        raise exceptions.TimeoutException("Timed out waiting for all given volumes to be removed from cinder list. "
                                          "Given volumes: {}. Volumes still exist: {}.".format(volumes, vols_to_check))


def volume_exists(volume_id, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Args:
        volume_id:
        con_ssh:
        auth_info

    Returns:
        True if a volume id exist within cinder show, False otherwise
    """
    exit_code, output = cli.cinder('show', volume_id, fail_ok=True, ssh_client=con_ssh, auth_info=auth_info)
    return exit_code == 0


def delete_volumes(volumes=None, fail_ok=False, timeout=VolumeTimeout.DELETE, check_first=True, con_ssh=None,
                   auth_info=Tenant.ADMIN):
    """
    Delete volume(s).

    Args:
        volumes (list|str): ids of the volumes to delete. If None, all available volumes under given Tenant will be
            deleted. If given Tenant is admin, available volumes for all tenants will be deleted.
        fail_ok (bool): True or False
        timeout (int): CLI timeout and waiting for volumes disappear timeout in seconds.
        check_first (bool): Whether to check volumes existence before attempt to delete
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (tuple): (rtn_code (int), msg (str))
        (-1, "No volume to delete. Do nothing.") # No volume given and no volume exists on system for given tenant
        (-1, ""None of the given volume(s) exist on system. Do nothing."")    # None of the given volume(s) exists on
            system for given tenant
        (0, "Volume(s) deleted successfully")   # volume is successfully deleted.
        (1, <stderr>)   # Delete volume cli returns stderr
        (2, "Delete request(s) accepted but some volume(s) did not disappear within <timeout> seconds".)
        (3, "Delete request(s) rejected and post check failed for accepted request(s). \nCLI error: <stderr>"

    """
    if volumes is None:
        volumes = get_volumes(status='available', auth_info=auth_info, con_ssh=con_ssh)

    LOG.info("Deleting volume(s): {}".format(volumes))

    if not volumes:
        msg = "No volume to delete. Do nothing."
        LOG.info(msg)
        return -1, msg

    if isinstance(volumes, str):
        volumes = [volumes]
    volumes = list(volumes)

    if check_first:
        vols_to_del = get_volumes(vols=volumes, auth_info=auth_info, con_ssh=con_ssh)
        if not vols_to_del:
            msg = "None of the given volume(s) exist on system. Do nothing."
            LOG.info(msg)
            return -1, msg

        if not vols_to_del == volumes:
            LOG.info("Some volume(s) don't exist. Given volumes: {}. Volumes to delete: {}.".
                     format(volumes, vols_to_del))
    else:
        vols_to_del = volumes

    vols_to_del_str = ' '.join(vols_to_del)

    LOG.debug("Volumes to delete: {}".format(vols_to_del))
    exit_code, cmd_output = cli.cinder('delete', vols_to_del_str, ssh_client=con_ssh, fail_ok=fail_ok, rtn_list=True,
                                       auth_info=auth_info, timeout=timeout)

    vols_to_check = []
    if exit_code == 1:
        for vol in vols_to_del:
            # if cinder delete on a specific volume ran successfully, then it has no output regarding that vol
            if vol not in cmd_output:
                vols_to_check.append(vol)
    else:
        vols_to_check = vols_to_del

    LOG.info("Waiting for volumes to be removed from cinder list: {}".format(vols_to_check))
    all_deleted, vols_deleted = _wait_for_volumes_deleted(vols_to_check, fail_ok=True, con_ssh=con_ssh,
                                                          auth_info=auth_info, timeout=timeout)

    if exit_code == 1:
        if all_deleted:
            if fail_ok:
                return 1, cmd_output
            raise exceptions.CLIRejected(cmd_output)
        else:
            msg = "Delete request(s) rejected and post check failed for accepted request(s). \nCLI error: {}".\
                  format(cmd_output)
            if fail_ok:
                LOG.warning(msg)
                return 3, msg
            raise exceptions.VolumeError(msg)

    if not all_deleted:
        msg = "Delete request(s) accepted but some volume(s) did not disappear within {} seconds".format(timeout)
        if fail_ok:
            LOG.warning(msg)
            return 2, msg
        raise exceptions.VolumeError(msg)

    LOG.info("Volume(s) are successfully deleted: {}".format(vols_to_check))
    return 0, "Volume(s) deleted successfully"


def get_quotas(quotas=None, con_ssh=None, auth_info=None):
    if auth_info is None:
        auth_info = Tenant.get_primary()
    tenant_id = keystone_helper.get_tenant_ids(auth_info['tenant'], con_ssh=con_ssh)[0]

    if not quotas:
        quotas = 'volumes'
    if isinstance(quotas, str):
        quotas = [quotas]

    table_ = table_parser.table(cli.cinder('quota-show', tenant_id, ssh_client=con_ssh, auth_info=auth_info))

    values = []
    for item in quotas:
        values.append(int(table_parser.get_value_two_col_table(table_, item)))

    return values


def update_quotas(tenant=None, con_ssh=None, auth_info=Tenant.ADMIN, **kwargs):
    if tenant is None:
        tenant = Tenant.get_primary()['tenant']
    tenant_id = keystone_helper.get_tenant_ids(tenant_name=tenant, con_ssh=con_ssh)[0]

    if not kwargs:
        raise ValueError("Please specify at least one quota=value pair via kwargs.")

    args_ = ''
    for key in kwargs:
        args_ += '--{} {} '.format(key, kwargs[key])

    args_ += tenant_id

    cli.cinder('quota-update', args_, ssh_client=con_ssh, auth_info=auth_info)


def create_qos_specs(qos_specs_name=None, con_ssh=None, **kwargs):

    if qos_specs_name is None:
        qos_specs_name = 'default_qos_spec_name'

    if not kwargs:
        raise ValueError("Please specify at least one key=value pair via kwargs.")

    args_ = qos_specs_name

    for key in kwargs:
        args_ += ' {}={}'.format(key, kwargs[key])

    table_ = table_parser.table(cli.cinder('qos-create', args_, ssh_client=con_ssh, auth_info=Tenant.ADMIN))
    qos_specs_id = table_parser.get_value_two_col_table(table_, 'id')
    # qos_specs_name = table_parser.get_value_two_col_table(table_, 'name')

    return 0, qos_specs_id


def delete_qos_specs(qos_specs_id, force=False, con_ssh=None):

    args_ = ''
    args_ += ' --force {} '.format(force)
    args_ += qos_specs_id

    exit_code, cmd_output = cli.cinder('qos-delete', args_, fail_ok=False, ssh_client=con_ssh, auth_info=Tenant.ADMIN,
                                       rtn_list=True)

    return exit_code, cmd_output


def create_volume_type(vol_type_name=None, con_ssh=None):
    # must be an ADMIN to use volume type create
    # option to make vol_type_name an optional variable and create arbitrary volume type?

    if vol_type_name is None:
        vol_type_name = 'default_vol_type_name'

    table_ = table_parser.table(cli.cinder('type-create', vol_type_name, ssh_client=con_ssh, auth_info=Tenant.ADMIN))
    vol_type_id = table_parser.get_values(table_, 'ID')[0]

    return 0, vol_type_id


def delete_volume_type(vol_type_id, con_ssh=None):
    # must be an ADMIN to use volume type delete

    cli.cinder('type-delete', vol_type_id, ssh_client=con_ssh, auth_info=Tenant.ADMIN)


def get_type_list(con_ssh=None):
    # return a table of volume type list
    table_ = table_parser.table(cli.cinder('type-list', ssh_client=con_ssh, auth_info=Tenant.ADMIN))

    vol_type_id = table_parser.get_values(table_, 'ID')

    return vol_type_id


def get_qos_list(con_ssh=None):
    # must be an admin to perform cinder qos-list
    table_ = table_parser.table(cli.cinder('qos-list', ssh_client=con_ssh, auth_info=Tenant.ADMIN))
    qos_specs_id = table_parser.get_values(table_, 'ID')

    return qos_specs_id



def associate_qos_to_volume_type(qos_spec_id, vol_type_id, fail_ok=False, con_ssh=None):
    """
    Associates qos specs with specified volume type.
    # must be an admin to perform cinder qos-associate
    """
    # TODO a check for volume type
    # TODO a check qos spec

    args_ = qos_spec_id + ' ' + vol_type_id

    exit_code, cmd_output = cli.cinder('qos-associate', args_, fail_ok=fail_ok, ssh_client=con_ssh, rtn_list=True,
                                       auth_info=Tenant.ADMIN)

    if exit_code == 1:
        return 1, cmd_output

    return 0, "Volume type is associated to qos spec"


def disassociate_qos_to_volume_type(qos_spec_id, vol_type_id, fail_ok=False, con_ssh=None):
    """
    disassociates qos specs with specified volume type.
    # must be an admin to perform cinder qos-associate
    """

    args_ = qos_spec_id + ' ' + vol_type_id

    exit_code, cmd_output = cli.cinder('qos-disassociate', args_, fail_ok=fail_ok, ssh_client=con_ssh, rtn_list=True,
                                       auth_info=Tenant.ADMIN)

    if exit_code == 1:
        return 1, cmd_output

    return 0, "Volume type is associated to qos spec"


def get_qos_association(qos_spec_id, con_ssh=None):

    table_ = table_parser.table(cli.cinder('qos-get-association', qos_spec_id, ssh_client=con_ssh,
                                           auth_info=Tenant.ADMIN))

    return table_
