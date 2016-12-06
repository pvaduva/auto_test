import random
import time

from utils import table_parser, cli, exceptions
from utils.ssh import ControllerClient
from utils.tis_log import LOG

from consts.auth import Tenant
from consts.timeout import VolumeTimeout
from consts.cgcs import GuestImages

from keywords import common, glance_helper, keystone_helper


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
                bootable=None, rtn_val='ID', auth_info=Tenant.ADMIN, con_ssh=None):
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
        table_ = table_parser.filter_table(table_, strict=name_strict, **{'Name': name})

    if criteria:
        table_ = table_parser.filter_table(table_, **criteria)

    if name is None and not criteria:
        LOG.warning("No criteria specified, return {}s for all volumes for specific tenant".format(rtn_val))

    return table_parser.get_column(table_, rtn_val)


def get_volumes_attached_to_vms(volumes=None, vms=None, header='ID', con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Filter out the volumes that are attached to a vm.
    Args:
        volumes (list or str): list of volumes ids to filter out from. When None, filter from all volumes
        vms (list or str): get volumes attached to given vm(s). When None, filter volumes attached to any vm
        header (str): header of the column in the table to return
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (list): a list of values from the column specified or [] if no match found

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

    return table_parser.get_column(table_, header)


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
        bootable (bool): When False, the source id params will be ignored. i.e., a un-bootable volume will be created.
        fail_ok (bool):
        auth_info (dict):
        con_ssh (SSHClient):
        rtn_exist(bool): whether to return an existing available volume with matching name and bootable state.
        guest_image (str): guest image name if image_id unspecified. valid values: cgcs-guest, ubuntu, centos_7, centos_6

    Returns (tuple):  (return_code, volume_id or err msg)
        (-1, existing_vol_id)   # returns existing volume_id instead of creating a new one. Applies when rtn_exist=True.
        (0, vol_id)     # Volume created successfully and in available state.
        (1, <stderr>)   # Create volume cli rejected with sterr
        (2, vol_id)   # volume created, but not in available state.
        (3, vol_id]: if volume created, but not in given bootable state.

    Notes:
        snapshot_id > source_vol_id > image_id if more than one source ids are provided.
    """

    bootable_str = str(bootable).lower()

    if rtn_exist and name is not None:
        vol_ids = get_volumes(name=name, status='available', bootable=bootable_str)
        if vol_ids:
            LOG.info('Volume(s) with name {} and bootable state {} exists and in available state, return an existing '
                     'volume.'.format(name, bootable))
            return -1, vol_ids[0]

    if name is None:
        name = 'vol-{}'.format(common.get_tenant_name())

    name = common.get_unique_name(name, resource_type='volume', existing_names=get_volumes(rtn_val='Name'))
    subcmd = ''
    source_arg = ''
    if bootable:
        if snapshot_id:
            source_arg = '--snapshot-id ' + snapshot_id
        elif source_vol_id:
            source_arg = '--source-volid ' + source_vol_id
        else:
            guest_image = guest_image if guest_image else 'cgcs-guest'
            image_id = image_id if image_id is not None else glance_helper.get_image_id_from_name(guest_image,
                                                                                                  strict=True)
            if size is None:
                if 'cgcs-guest' in guest_image:
                    size = 1
                else:
                    size = GuestImages.IMAGE_FILES[guest_image][1]

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
    if str(bootable).lower() != actual_bootable.lower():
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


def create_qos_specs(qos_name=None, fail_ok=False, consumer=None, auth_info=Tenant.ADMIN, con_ssh=None, **specs):
    """
    Create QoS with given name and specs

    Args:
        qos_name (str):
        fail_ok (bool):
        consumer (str): Valid consumer of QoS specs are: ['front-end', 'back-end', 'both']
        auth_info (dict):
        con_ssh (SSHClient):
        **specs: QoS specs
            format: **{<spec_name1>: <spec_value1>, <spec_name2>: <spec_value2>}

    Returns (tuple):
        (0, QoS <id> created successfully with specs: <specs dict>)
        (1, <std_err>)

    """
    if consumer is None and not specs:
        raise ValueError("'consumer' or 'specs' have to be specified.")

    valid_consumers = ['front-end', 'back-end', 'both']
    if consumer is not None and consumer.lower() not in valid_consumers:
        raise ValueError("Invalid consumer value {}. Choose from: {}".format(consumer, valid_consumers))

    if qos_name is None:
        qos_name = 'qos-auto'
    qos_name = common.get_unique_name(qos_name, get_qos_list(rtn_val='name'), resource_type='qos')
    args_ = qos_name

    if consumer:
        specs['consumer'] = consumer

    LOG.info("Creating QoS {} with specs: {}".format(qos_name, specs))

    for key in specs:
        args_ += ' {}={}'.format(key, specs[key])

    code, output = cli.cinder('qos-create', args_, ssh_client=con_ssh, auth_info=auth_info, rtn_list=True,
                              fail_ok=fail_ok)

    if code > 0:
        return 1, output

    LOG.info("Check created QoS specs are correct")
    qos_tab = table_parser.table(output)
    post_qos_specs = eval(table_parser.get_value_two_col_table(qos_tab, 'specs'))
    post_consumer = table_parser.get_value_two_col_table(qos_tab, 'consumer')

    for spec_name in specs:
        expected_val = str(specs[spec_name])
        if spec_name == 'consumer':
            actual_val = post_consumer
        else:
            actual_val = post_qos_specs[spec_name]

        if expected_val != actual_val:
            err_msg = "{} is not as expected. Expect: {}, actual: {}".format(spec_name, expected_val, actual_val)
            raise exceptions.CinderError(err_msg)

    qos_id = table_parser.get_value_two_col_table(qos_tab, 'id')

    LOG.info("QoS {} created successfully with specs: {}".format(qos_id, specs))
    return 0, qos_id


def delete_qos(qos_id, force=None, check_first=True, fail_ok=False, auth_info=Tenant.ADMIN, con_ssh=None):
    """
    Delete given QoS via cinder qos-delete

    Args:
        qos_id (str):
        force (bool):
        check_first (bool):
        fail_ok (bool):
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (tuple):
        (0, QoS spec <qos_id> is successfully deleted)
        (1, <std_err>)
        (2, QoS <qos_id> still exists in cinder qos-list after deletion)

    """

    LOG.info("Delete QoS spec {}".format(qos_id))

    if check_first:
        qos_list = get_qos_list()
        if qos_id not in qos_list:
            msg = "QoS spec {} does not exist in cinder qos-list. Do nothing.".format(qos_id)
            LOG.info(msg)
            return -1, msg

    args_ = qos_id

    if force is not None:
        args_ = '--force {} '.format(force) + args_

    code, output = cli.cinder('qos-delete', args_, fail_ok=fail_ok, ssh_client=con_ssh, auth_info=auth_info,
                              rtn_list=True)

    if code == 1:
        return code, output

    post_qos_list = get_qos_list()
    if qos_id in post_qos_list:
        err_msg = "QoS {} still exists in cinder qos-list after deletion".format(qos_id)
        if fail_ok:
            LOG.warning(err_msg)
            return 2, err_msg
        else:
            raise exceptions.CinderError(err_msg)

    succ_msg = "QoS spec {} is successfully deleted".format(qos_id)
    LOG.info(succ_msg)
    return 0, succ_msg


def delete_qos_list(qos_ids, force=False, check_first=True, fail_ok=False, auth_info=Tenant.ADMIN, con_ssh=None):
    """
    Delete given list of QoS'

    Args:
        qos_ids (list|str):
        force (bool):
        check_first (bool):
        fail_ok (bool):
        auth_info (dict):
        con_ssh (SSHClient):

    Returns:

    """
    if isinstance(qos_ids, str):
        qos_ids = [qos_ids]

    qos_ids_to_del = list(qos_ids)
    if check_first:
        existing_qos_list = get_qos_list()
        qos_to_del_list = list(set(existing_qos_list) & set(qos_ids))
        if not qos_to_del_list:
            msg = "None of the QoS specs {} exist in cinder qos-list. Do nothing.".format(qos_ids)
            LOG.info(msg)
            return -1, msg

    qos_delete_rejected_list = []
    for qos in qos_ids_to_del:
        args = '' if force is None else '--force {} '.format(force) + qos
        code, output = cli.cinder('qos-delete', args, fail_ok=fail_ok, ssh_client=con_ssh, auth_info=auth_info,
                                  rtn_list=True)
        if code > 0:
            qos_delete_rejected_list.append(qos)

    qos_list_to_check = list(set(qos_ids) - set(qos_delete_rejected_list))

    qos_undeleted_list = []
    if qos_list_to_check:
        qos_undeleted_list = wait_for_qos_deleted(qos_ids=qos_list_to_check, fail_ok=fail_ok, con_ssh=con_ssh)[1]

    if qos_delete_rejected_list or qos_undeleted_list:
        err_msg = "Some QoS's failed to delete. cli rejected: {}. Still exist after deletion: {}".format(
                qos_delete_rejected_list, qos_undeleted_list)

        if fail_ok:
            LOG.info(err_msg)
            return 1, err_msg
        else:
            raise exceptions.CinderError(err_msg)

    succ_msg = "QoS's successfully deleted: {}".format(qos_ids)
    LOG.info(succ_msg)
    return 0, succ_msg


def wait_for_qos_deleted(qos_ids, timeout=10, check_interval=1, fail_ok=False, con_ssh=None):
    """
    Wait for given list of QoS to be gone from cinder qos-list
    Args:
        qos_ids (list):
        timeout (int):
        check_interval (int):
        fail_ok (bool):
        con_ssh (SSHClient):

    Returns (tuple):
        (True, [])          All given QoS ids are gone from cinder qos-list
        (False, [undeleted_qos_list])       Some given QoS' still exist in cinder qos-list

    """

    LOG.info("Waiting for QoS' to be deleted from system: {}".format(qos_ids))

    qos_undeleted = list(qos_ids)
    end_time = time.time() + timeout

    while time.time() < end_time:
        existing_qos_list = get_qos_list(con_ssh=con_ssh)
        qos_undeleted = list(set(existing_qos_list) & set(qos_undeleted))

        if not qos_undeleted:
            msg = "QoS' all gone from cinder qos-list: {}".format(qos_ids)
            LOG.info(msg)
            return True, []

        time.sleep(check_interval)

    err_msg = "Timed out waiting for QoS' to be gone from cinder qos-list: {}".format(qos_undeleted)
    if fail_ok:
        LOG.warning(err_msg)
        return False, qos_undeleted
    else:
        raise exceptions.CinderError(err_msg)


def create_volume_type(name=None, public=None, rtn_val='ID', fail_ok=False, auth_info=Tenant.ADMIN, con_ssh=None):
    """
    Create a volume type with given name

    Args:
        name (str): name for the volume type
        public (bool):
        rtn_val (str): 'ID' or 'Name'
        fail_ok (bool):
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (tuple):
        (0, <vol_type_id>)      - volume type created successfully
        (1, <std_err>)          - cli rejected
        (2, <vol_type_id>)      - volume type public flag is not as expected

    """

    LOG.info("Creating volume type.")

    if name is None:
        name = 'vol_type_auto'

    args = common.get_unique_name(name, get_volume_types())

    if public is not None:
        args = '--is-public {} {}'.format(public, args)

    code, output = cli.cinder('type-create', args, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                              rtn_list=True)

    if code == 1:
        return 1, output

    LOG.info("Check is_public property for create volume type")
    table_ = table_parser.table(output)
    vol_type = table_parser.get_column(table_, rtn_val)[0]

    actual_pub = table_parser.get_column(table_, 'Is_Public')[0]
    expt_pub = 'False' if public is False else 'True'
    if actual_pub != expt_pub:
        err_msg = "volume type is_public should be {} instead of {}".format(expt_pub, actual_pub)
        if fail_ok:
            LOG.warning(err_msg)
            return 2, vol_type
        else:
            raise exceptions.CinderError(err_msg)

    LOG.info("Volume type is created successfully")
    return 0, vol_type


def delete_volume_type(vol_type_id, check_first=True, fail_ok=False, auth_info=Tenant.ADMIN,  con_ssh=None):
    """
    Delete given volume type

    Args:
        vol_type_id:
        check_first:
        fail_ok:
        auth_info:
        con_ssh:

    Returns (tuple):
        (-1, Volume type <id> does not exist in cinder type-list. Do nothing.)
        (0, Volume type is successfully deleted)
        (1, <std_err>)
        (2, Volume type <id> still exists in cinder type-list after deletion)

    """

    LOG.info("Delete volume type {} started".format(vol_type_id))

    if check_first:
        vol_types = get_volume_types()
        if vol_type_id not in vol_types:
            msg = "Volume type {} does not exist in cinder type-list. Do nothing.".format(vol_type_id)
            LOG.info(msg)
            return -1, msg

    code, output = cli.cinder('type-delete', vol_type_id, fail_ok=fail_ok, ssh_client=con_ssh, auth_info=auth_info,
                              rtn_list=True)

    if code == 1:
        return code, output

    post_vol_types = get_volume_types()
    if vol_type_id in post_vol_types:
        err_msg = "Volume type {} still exists in cinder type-list after deletion".format(vol_type_id)
        if fail_ok:
            LOG.warning(err_msg)
            return 2, err_msg
        else:
            raise exceptions.CinderError(err_msg)

    succ_msg = "Volume type is successfully deleted"
    LOG.info(succ_msg)
    return 0, succ_msg


def delete_volume_types(vol_types, check_first=True, fail_ok=False, auth_info=Tenant.ADMIN, con_ssh=None):
    """
    Delete given volume type

    Args:
        vol_types (list): list of volume type id's to delete
        check_first (bool):
        fail_ok (bool):
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (tuple):
        (-1, None of the volume types <ids> exist in cinder qos-list. Do nothing.)
        (0, Volume types successfully deleted: <ids>)
        (1, <std_err>)
        (2, Volume types delete rejected: <ids>; volume types still in cinder type-list after deletion: <ids>)

    """

    LOG.info("Delete volume types started")

    vol_types_to_del = list(vol_types)
    if check_first:
        existing_vol_types = get_volume_types()
        vol_types_to_del = list(set(existing_vol_types) & set(vol_types))
        if not vol_types_to_del:
            msg = "None of the volume types {} exist in cinder qos-list. Do nothing.".format(vol_types)
            LOG.info(msg)
            return -1, msg

    types_rejected = []
    for vol_type in vol_types_to_del:
        code, output = cli.cinder('type-delete', vol_type, fail_ok=True, ssh_client=con_ssh, auth_info=auth_info,
                                  rtn_list=True)
        if code == 1:
            types_rejected.append(vol_type)

    LOG.info("Check volume types are gone from cinder type-list")
    types_to_check = list(set(vol_types_to_del) - set(types_rejected))
    types_undeleted = []
    if types_to_check:
        post_del_types = get_volume_types()
        types_undeleted = list(set(post_del_types) & set(types_to_check))

    if types_rejected or types_undeleted:
        err_msg = "Volume types delete rejected: {}; volume types still in cinder type-list after deletion: {}".\
            format(types_rejected, types_undeleted)
        if fail_ok:
            LOG.warning(err_msg)
            return 2, err_msg
        else:
            raise exceptions.CinderError(err_msg)

    succ_msg = "Volume types successfully deleted: {}".format(vol_types)
    LOG.info(succ_msg)
    return 0, succ_msg


def get_volume_types(ids=None, public=None, name=None, strict=True, rtn_val='ID', con_ssh=None, auth_info=Tenant.ADMIN):

    table_ = table_parser.table(cli.cinder('type-list', ssh_client=con_ssh, auth_info=auth_info))

    filters = {}
    if ids is not None:
        filters['ID'] = ids
    if public is not None:
        filters['Is_Public'] = public

    if filters:
        table_ = table_parser.filter_table(table_, **filters)

    if name is not None:
        table_ = table_parser.filter_table(table_, strict=strict, **{'Name': name})

    vol_types = table_parser.get_column(table_, rtn_val)

    return vol_types


def get_qos_list(rtn_val='id', ids=None, name=None, consumer=None, strict=True, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Get qos list based on given filters

    Args:
        rtn_val (str): 'id' or 'name'
        ids (list): list of qos ids to filter out from
        name (str): name of the qos' to filter for
        consumer (str): consumer of the qos' to filter for
        strict (bool):
        con_ssh:
        auth_info:

    Returns (list): list of qos IDs found. If not found, [] is returned

    """

    kwargs_raw = {
        'ID': ids,
        'Name': name,
        'Consumer': consumer,
    }

    kwargs = {}
    for key, val in kwargs_raw.items():
        if val is not None:
            kwargs[key] = val

    table_ = table_parser.table(cli.cinder('qos-list', ssh_client=con_ssh, auth_info=auth_info))

    if kwargs:
        table_ = table_parser.filter_table(table_, strict=strict, **kwargs)

    qos_specs_ids = table_parser.get_values(table_, rtn_val)

    return qos_specs_ids


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


def is_volumes_pool_sufficient(min_size=30):
    """

    Args:
        min_size (int): Minimum requirement for cinder volume pool size in Gbs. Default 30G.

    Returns (bool):

    """
    con_ssh = ControllerClient.get_active_controller()
    lvs_pool = con_ssh.exec_sudo_cmd(cmd="lvs | grep --color='never' cinder-volumes-pool")[1]
    # Sample output:
    # cinder-volumes-pool                         cinder-volumes twi-aotz-- 19.95g                          64.31  33.38
    #   volume-05fa416d-d37b-4d57-a6ff-ab4fe49deece cinder-volumes Vwi-a-tz--  1.00g cinder-volumes-pool    64.16
    #   volume-1b04fa7f-b839-4cf9-a177-e676ec6cf9b7 cinder-volumes Vwi-a-tz--  1.00g cinder-volumes-pool    64.16
    if lvs_pool:
        pool_size = float(lvs_pool.splitlines()[0].strip().split()[3].strip()[:-1])
        return pool_size >= min_size

    # assume enough volumes in ceph:
    return True
