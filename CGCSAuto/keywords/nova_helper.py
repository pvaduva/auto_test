import random
import time

import re

from utils import cli, exceptions, table_parser
from utils import table_parser
from utils.tis_log import LOG
from consts.auth import Tenant, Primary
from consts.cgcs import BOOT_FROM_VOLUME, UUID
from consts.timeout import VolumeTimeout
from keywords.common import _Count


def create_flavor(name=None, flavor_id='auto', vcpus=1, ram=512, root_disk=1, ephemeral=None, swap=None,
                  is_public=None, rxtx_factor=None, fail_ok=False, auth_info=Tenant.ADMIN, con_ssh=None):
    """

    Args:
        name:
        flavor_id:
        vcpus:
        ram:
        root_disk:
        ephemeral:
        swap:
        is_public:
        rxtx_factor:
        fail_ok:
        auth_info:
        con_ssh:

    Returns (list): [rtn_code (int), flavor_id/err_msg (str)]
        [0, <flavor_id>]: flavor created successfully
        [1, <stderr>]: create flavor cli rejected

    """
    LOG.info("Processing create flavor arguments...")
    candidate_args = {
        '--ephemeral': ephemeral,
        '--swap': swap,
        '--rxtx-factor': rxtx_factor,
        '--is-public': is_public
    }

    if name is None:
        name = 'flavor'

    table_ = table_parser.table(cli.nova('flavor-list', ssh_client=con_ssh, auth_info=auth_info))
    existing_names = table_parser.get_column(table_, 'Name')

    flavor_name = None
    for i in range(10):
        tmp_name = '-'.join([name, str(_Count.get_flavor_count())])
        if tmp_name not in existing_names:
            flavor_name = tmp_name
            break
    else:
        exceptions.FlavorError("Unable to get a proper name for flavor creation.")

    mandatory_args = ' '.join([flavor_name, flavor_id, str(ram), str(root_disk), str(vcpus)])

    optional_args = ''
    for key, value in candidate_args.items():
        if value is not None:
            optional_args = ' '.join([optional_args.strip(), key, str(value)])
    subcmd = ' '.join([optional_args, mandatory_args])

    LOG.info("Creating flavor...")
    exit_code, output = cli.nova('flavor-create', subcmd, ssh_client=con_ssh, fail_ok=fail_ok, auth_info=auth_info,
                                 rtn_list=True)

    if exit_code == 1:
        LOG.warning("Create flavor request rejected.")
        return [1, output]

    table_ = table_parser.table(output)
    flavor_id = table_parser.get_column(table_, 'ID')[0]
    LOG.info("Flavor {} created successfully.".format(flavor_name))
    return [0, flavor_id]


def get_flavor(name=None, memory=None, disk=None, ephemeral=None, swap=None, vcpu=None, rxtx=None, is_public=None,
               con_ssh=None, auth_info=None):
    req_dict = {'Name': name,
                'Memory_MB': memory,
                'Disk': disk,
                'Ephemeral': ephemeral,
                'Swap': swap,
                'VCPUs': vcpu,
                'RXTX_Factor': rxtx,
                'IS_PUBLIC': is_public,
                }

    final_dict = {}
    for key, val in req_dict.items():
        if val is not None:
            final_dict[key] = val

    table_ = table_parser.table(cli.nova('flavor-list', ssh_client=con_ssh, auth_info=auth_info))

    if not final_dict:
        ids = table_parser.get_column(table_, 'ID')
    else:
        ids = table_parser.get_values(table_, 'ID', **final_dict)
    if not ids:
        return ''
    return random.choice(ids)


def set_flavor_extra_specs(flavor, con_ssh=None, auth_info=Tenant.ADMIN, fail_ok=False, **extra_specs):
    """

    Args:
        flavor:
        con_ssh:
        auth_info:
        fail_ok:
        **extra_specs:

    Returns (list): [rtn_code (int), message (str)]
        [0, '']: required extra spec(s) added successfully
        [1, <stderr>]: add extra spec cli rejected
        [2, 'Required extra spec <spec_name> is not found in the extra specs list']: post action check failed
        [3, 'Extra spec value for <spec_name> is not <spec_value>']: post action check failed

    """
    LOG.info("Setting flavor extra specs...")
    if not extra_specs:
        raise ValueError("extra_specs is not provided. At least one name=value pair is required.")

    extra_specs_args = ''
    for key, value in extra_specs.items():
        extra_specs_args = extra_specs_args + ' ' + key.strip() + '=' + value.strip()
    exit_code, output = cli.nova('flavor-key', '{} set {}'.format(flavor, extra_specs_args),
                                 ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok, rtn_list=True)

    if exit_code == 1:
        LOG.warning("Set extra specs request rejected.")
        # if exit_code = 1, means fail_ok is set to True, thus no need to check fail_ok flag again

    extra_specs = get_flavor_extra_specs(flavor, con_ssh=con_ssh, auth_info=auth_info)
    for key, value in extra_specs.items():
        if key not in extra_specs:
            rtn = [2, "Required extra spec {} is not found in the extra specs list".format(key)]
            break
        if extra_specs[key] != value:
            rtn = [3, "Extra spec value for {} is not {}".format(key, value)]
            break
    else:
        LOG.info("Flavor {} extra specs set: {}".format(flavor, extra_specs))
        rtn = [0, '']

    if not fail_ok and rtn[0] != 0:
        raise exceptions.HostPostCheckFailed(rtn[1])

    return rtn


def get_flavor_extra_specs(flavor, con_ssh=None, auth_info=Tenant.ADMIN):
    """

    Args:
        flavor:
        con_ssh:
        auth_info:

    Returns (dict): e.g., {"aggregate_instance_extra_specs:storage": "local_image", "hw:mem_page_size": "2048"}

    """
    table_ = table_parser.table(cli.nova('flavor-show', flavor, ssh_client=con_ssh, auth_info=auth_info))
    extra_specs = eval(table_parser.get_value_two_col_table(table_, 'extra_specs'))

    return extra_specs


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
        table_= table_parser.filter_table(table_, **criteria)

    if name is None and not criteria:
        LOG.warning("No criteria specified, return a full list of volume ids for a tenant")

    return table_parser.get_column(table_, 'ID')


def get_image_id_from_name(name=None, strict=False, con_ssh=None, auth_info=None):
    table_ = table_parser.table(cli.glance('image-list', ssh_client=con_ssh, auth_info=auth_info))
    if name is None:
        image_id = random.choice(table_parser.get_column(table_, 'ID'))
    else:
        image_ids = table_parser.get_values(table_, 'ID', strict=strict, Name=name)
        image_id = '' if not image_ids else random.choice(image_ids)
    return image_id


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
            image_id = image_id if image_id is not None else get_image_id_from_name('cgcs-guest')
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


def _volume_in_cinder(vol_id,column='ID', timeout=VolumeTimeout.STATUS_CHANGE, fail_ok=True,
                              check_interval=3,con_ssh=None, auth_info=None):
    """
        check if a volume id exist within a cinder list
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        table_ = table_parser.table(cli.cinder('list', ssh_client=con_ssh, auth_info=auth_info))
        ids_list = table_parser.get_column(table_, column)
        print(ids_list)
        if vol_id not in ids_list:
            return True
        time.sleep(check_interval)
    else:
        if fail_ok:
            return False
        raise exceptions.TimeoutException("Timed out waiting for {} to not be in column {}. "
                                          "Actual still in column".format(vol_id, column))


def volume_exists(vm_id, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Args:
        vm_id:
        con_ssh:
        auth_info

    Returns:
        return
    """
    exit_code, output = cli.cinder('show', vm_id, fail_ok=True, ssh_client=con_ssh, auth_info=auth_info)
    return exit_code == 0


def delete_volume(volume_id,fail_ok=False, con_ssh=None, auth_info=Tenant.TENANT_1):

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
            LOG.info('To be deleted Volume: {} does not exists return an empty string.'.format(volume_id))
            return [-1, '']

    # excute the delete command
    exit_code, cmd_output = cli.cinder('delete', volume_id, ssh_client=con_ssh, fail_ok=fail_ok, rtn_list=True,
                auth_info=auth_info)

    # check if the volume is deleted
    v_status = _volume_in_cinder(volume_id, column='ID')

    if v_status:
        return [0, '']
    else:
        LOG.warning("Volume is deleted, but still in deleting state.")
        return [1, volume_id]


def create_image(name, desc=None, source='image location', format='raw', min_disk=None, min_ram=None, copy_data=True,
                 live_mig_timeout=800, live_mig_max_downtime=500, public=False, protected=False,
                 instance_auto_recovery=True):
    raise NotImplementedError


def delete_image(name, desc=None, source='image location', format='raw', min_disk=None, min_ram=None, copy_data=True,
                 live_mig_timeout=800, live_mig_max_downtime=500, public=False, protected=False,
                 instance_auto_recovery=True):
    raise NotImplementedError


def create_server_group(name, policy=None, best_effort=False, max_group_size=None):
    raise NotImplementedError


def get_all_vms(return_val='ID', con_ssh=None):
    """
    Get VMs for all tenants in the systems

    Args:
        return_val:
        con_ssh:

    Returns:

    """
    table_ = table_parser.table(cli.nova('list', '--all-tenant', ssh_client=con_ssh, auth_info=Tenant.ADMIN))
    return table_parser.get_column(table_, return_val)


def get_vms(return_val='ID', con_ssh=None, auth_info=None, all_vms=False):
    """
    get a list of VM IDs or Names for given tenant in auth_info param.

    Args:
        return_val (str): 'ID' or 'Name'
        con_ssh (SSHClient): controller SSHClient.
        auth_info (dict): such as ones in auth.py: auth.ADMIN, auth.TENANT1
        all_vms (bool): whether to return VMs for all tenants if admin auth_info is given

    Returns: list of VMs for tenant(s).

    """
    positional_args = ''
    if all_vms is True:
        if auth_info is None:
            auth_info = Primary.get_primary()
        if auth_info['tenant'] == 'admin':
            positional_args = '--all-tenant'
    table_ = table_parser.table(cli.nova('list', positional_args=positional_args, ssh_client=con_ssh,
                                         auth_info=auth_info))
    return table_parser.get_column(table_, return_val)


def get_vm_id_from_name(vm_name, con_ssh=None):
    table_ = table_parser.table(cli.nova('list', '--all-tenant', ssh_client=con_ssh, auth_info=Tenant.ADMIN))
    return table_parser.get_values(table_, 'ID', Name=vm_name.strip())[0]


def get_vm_name_from_id(vm_id, con_ssh=None):
    table_ = table_parser.table(cli.nova('list', '--all-tenant', ssh_client=con_ssh, auth_info=Tenant.ADMIN))
    return table_parser.get_values(table_, 'Name', ID=vm_id)[0]


def get_vm_info(vm_id, field, strict=False, con_ssh=None, auth_info=Tenant.ADMIN):
    table_ = table_parser.table(cli.nova('show', vm_id, ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_value_two_col_table(table_, field, strict)


def get_vm_host(vm_id, con_ssh=None):
    return get_vm_info(vm_id, ':host', strict=False, con_ssh=con_ssh, auth_info=Tenant.ADMIN)


def get_hypervisor_hosts(con_ssh=None):
    table_ = table_parser.table(cli.nova('hypervisor-list', ssh_client=con_ssh, auth_info=Tenant.ADMIN))
    return table_parser.get_column(table_, 'Hypervisor hostname')


def get_vms_on_hypervisor(hostname, con_ssh=None):
    table_ = table_parser.table(cli.nova('hypervisor-servers', hostname, ssh_client=con_ssh, auth_info=Tenant.ADMIN))
    return table_parser.get_column(table_, 'ID')


def get_vms_by_hypervisors(con_ssh=None):
    host_vms = {}
    for host in get_hypervisor_hosts(con_ssh=con_ssh):
        host_vms[host] = get_vms_on_hypervisor(host, con_ssh)

    return host_vms


def vm_exists(vm_id, con_ssh=None, auth_info=Tenant.ADMIN):
    """

    Args:
        vm_id:
        con_ssh:
        auth_info

    Returns:

    """
    exit_code, output = cli.nova('show', vm_id, fail_ok=True, ssh_client=con_ssh, auth_info=auth_info)
    return exit_code == 0


def delete_vm(vm_id, volume_id=None, con_ssh=None, auth_info=None):
    """
    Args:
        vm_id
        volume_id: (str) if a volume id is provided delete that volume as well.
        con_ssh
        auth_info
    Returns:
        True if vm is deleted, False otherwise
    [wrsroot@controller-0 ~(keystone_tenant1)]$ nova delete 74e37830-97a2-4d9d-b892-ad58bc4148a7
    Request to delete server 74e37830-97a2-4d9d-b892-ad58bc4148a7 has been accepted.

    """
    #check of if vm exist
    #delete vm
    #delete volume if it's set
    #check if vm is deleted

    exit_code, output = cli.nova('delete', vm_id, fail_ok=True, ssh_client=con_ssh, auth_info=auth_info)
    if exit_code == 0 and volume_id is not None:
        volume_deleted = delete_volume(volume_id)
        if volume_deleted:
            return True
        else:
            raise False
    else:
        return True


def get_snapshot_id(status='available', vol_id=None, name=None, size=None, con_ssh=None, auth_info=None):
    table_ = table_parser.table(cli.cinder('snapshot-list', ssh_client=con_ssh, auth_info=auth_info))
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


def _get_vm_volumes(novashow_table):
    volumes = eval(table_parser.get_value_two_col_table(novashow_table, ':volumes_attached', strict=False))
    return [volume['id'] for volume in volumes]


def get_vm_boot_info(vm_id, auth_info=None, con_ssh=None):
    table_ = table_parser.table(cli.nova('show', vm_id, ssh_client=con_ssh, auth_info=auth_info))
    image = table_parser.get_value_two_col_table(table_, 'image')
    if BOOT_FROM_VOLUME in image:
        volumes = _get_vm_volumes(table_)
        if len(volumes) == 0:
            raise exceptions.VMError("Booted from volume, but no volume id found.")
        elif len(volumes) > 1:
            raise exceptions.VMError("VM booted from volume. Multiple volumes found! Did you attach extra volume?")
        return {'type': 'volume', 'id': volumes[0]}
    else:
        match = re.search(UUID, image)
        return {'type': 'image', 'id': match.group(0)}


def get_vm_image_name(vm_id, auth_info=None, con_ssh=None):
    boot_info = get_vm_boot_info(vm_id, auth_info=auth_info, con_ssh=con_ssh)
    if boot_info['type'] == 'image':
        image_id = boot_info['id']
        image_show_table = table_parser.table(cli.glance('image-show', image_id))
        image_name = table_parser.get_value_two_col_table(image_show_table, 'image_name', strict=False)
        if not image_name:
            image_name = table_parser.get_value_two_col_table(image_show_table, 'name')
    else:      # booted from volume
        vol_show_table = table_parser.table(cli.cinder('show', boot_info['id']))
        image_meta_data = table_parser.get_value_two_col_table(vol_show_table, 'volume_image_metadata')
        image_name = eval(image_meta_data)['image_name']

    return image_name
