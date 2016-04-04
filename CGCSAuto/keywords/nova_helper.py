import random
import re
import time

from utils import cli, exceptions
from utils import table_parser
from utils.tis_log import LOG
from consts.auth import Tenant, Primary
from consts.cgcs import BOOT_FROM_VOLUME, UUID
from consts.timeout import VolumeTimeout
from keywords import cinder_helper
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


def _wait_for_vm_in_nova_list(vm_id,column='ID', timeout=VolumeTimeout.STATUS_CHANGE, fail_ok=True,
                              check_interval=3,con_ssh=None, auth_info=None):
    """
        similar to _wait_for_volume_in_cinder_list
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        table_ = table_parser.table(cli.nova('list', ssh_client=con_ssh, auth_info=auth_info))
        ids_list = table_parser.get_column(table_, column)

        if vm_id not in ids_list:
            return True
        time.sleep(check_interval)
    else:
        if fail_ok:
            return False
        raise exceptions.TimeoutException("Timed out waiting for {} to not be in column {}. "
                                          "Actual still in column".format(vm_id, column))


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


def delete_vm(vm_id, delete_volumes=True, fail_ok=False, con_ssh=None, auth_info=None):
    """
    Args:
        vm_id
        delete_volumes: (boolean) delete all attached volumes if set to True
        fail_ok:
        con_ssh
        auth_info
    Returns:
        [-1,''] if VM does not exist
        [0,''] VM is successfully deleted.
        [1,output] if delete vm cli errored when executing
        [2,vm_id] if delete vm cli executed but still show up in nova list


    [wrsroot@controller-0 ~(keystone_tenant1)]$ nova delete 74e37830-97a2-4d9d-b892-ad58bc4148a7
    Request to delete server 74e37830-97a2-4d9d-b892-ad58bc4148a7 has been accepted.

    """
    status = []
    # check if vm exist
    if vm_id is not None:
        vm_exist = vm_exists(vm_id)
        if not vm_exist:
            LOG.info("To be deleted VM: {} does not exists return [-1,''].".format(vm_id))
            return [-1, '']

    # list attached volumes to vm
    volume_list = cinder_helper.get_volumes(attached_vm=vm_id)
    if not volume_list:
        LOG.info("There are no volumes attached to VM {}".format(vm_id))

    # delete vm
    vm_exit_code, vm_cmd_output = cli.nova('delete', vm_id, ssh_client=con_ssh, fail_ok=fail_ok, rtn_list=True,
                                           auth_info=auth_info)
    if vm_exit_code == 1:
        return [1, vm_cmd_output]

    # check if the vm is deleted
    vol_status = _wait_for_vm_in_nova_list(vm_id, column='ID', fail_ok=fail_ok)
    if not vol_status:
        if fail_ok:
            LOG.warning("Delete VM {} command is executed but still shows up in nova list".format(vm_id))
            return [2, vm_id]
        raise exceptions.VolumeError("Delete VM {} command is executed but "
                                     "still shows up in nova list".format(vm_id))

    # delete volumes that were attached to the vm
    if delete_volumes:
        for volume_id in volume_list:
            vol_exit_code, vol_cmd_output = cinder_helper.delete_volume(volume_id, fail_ok=True)
            if vol_exit_code == 1:
                LOG.warning("Delete Volume {} failed due to: {}".format(volume_id,vol_cmd_output))

        LOG.info("All Volumes attached to VM {} are deleted".format(vm_id))

    LOG.info("VM is deleted successfully.")
    return [0, '']


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
