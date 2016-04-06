import random
import re
import time

from consts.auth import Tenant, Primary
from consts.cgcs import BOOT_FROM_VOLUME, UUID
from consts.timeout import VolumeTimeout
from keywords.common import Count
from utils import cli, exceptions
from utils import table_parser
from utils.tis_log import LOG


def create_flavor(name=None, flavor_id='auto', vcpus=1, ram=512, root_disk=1, ephemeral=None, swap=None,
                  is_public=None, rxtx_factor=None, fail_ok=False, auth_info=Tenant.ADMIN, con_ssh=None):
    """
    Create a flavor with given critria.

    Args:
        name (str): substring of flavor name. Whole name will be <name>-<auto_count>. e,g., 'myflavor-1'. If None, name
            will be set to 'flavor'.
        flavor_id (str): auto generated by default unless specified.
        vcpus (int):
        ram (int):
        root_disk (int):
        ephemeral (int):
        swap (int):
        is_public (bool):
        rxtx_factor (str):
        fail_ok (bool): whether it's okay to fail to create a flavor. Default to False.
        auth_info (dict): This is set to Admin by default. Can be set to other tenant for negative test.
        con_ssh (SSHClient):

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
        tmp_name = '-'.join([name, str(Count.get_flavor_count())])
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


def flavor_exists(flavor, header='ID', con_ssh=None, auth_info=None):
    table_ = table_parser.table(cli.nova('flavor-list', ssh_client=con_ssh, auth_info=auth_info))
    return flavor in table_parser.get_column(table_, header=header)


def delete_flavors(flavor_ids, fail_ok=False, con_ssh=None, auth_info=Tenant.ADMIN):
    if isinstance(flavor_ids, str):
        flavor_ids = [flavor_ids]
    flavors_to_del = []
    flavors_deleted = []
    for flavor in flavor_ids:
        if flavor_exists(flavor, con_ssh=con_ssh, auth_info=auth_info):
            flavors_to_del.append(flavor)
        else:
            flavors_deleted.append(flavor)

    if not flavors_to_del:
        msg = "None of the flavor(s) provided exist on system: {}. Do nothing.".format(flavor_ids)
        LOG.info(msg)
        return [-1, {}]

    if flavors_deleted:
        LOG.warning("Some flavor(s) do no exist on system: {}".format(flavors_deleted))

    LOG.info("Flavor(s) to delete: {}".format(flavors_to_del))
    results = {}
    fail = False
    for flavor in flavors_to_del:
        LOG.info("Deleting flavor {}...".format(flavor))
        # Always get the result for individual flavor, so deletion will be attempted to all flavors instead of failing
        # right away upon one failure
        rtn_code, output = cli.nova('flavor-delete', flavor, fail_ok=True, ssh_client=con_ssh, auth_info=auth_info)
        if rtn_code == 1:
            result = [1, output]
            fail = True
        elif flavor_exists(flavor, con_ssh=con_ssh, auth_info=auth_info):
            result = [2, "Flavor {} still exists on system after deleted.".format(flavor)]
            fail = True
        else:
            result = [0, '']
        results[flavor] = result
    if fail:
        if fail_ok:
            return [1, results]
        raise exceptions.FlavorError("Failed to delete flavor(s). Details: {}".format(results))

    LOG.info("Flavor(s) deleted successfully: {}".format(flavor_ids))
    # Return empty dict upon successfully deleting all flavors
    return [0, {}]


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


def get_field_by_vms(vm_ids=None, field="Status", con_ssh=None, auth_info=None):
    """
    get a dictionary in the form {vm_id:field,vm_id:field...} for a specific field

    Args:
        vm_ids (list or str):a list of vm ids OR a vm id in string
        field (str): A specific field header Such as Name,Status,Power State
        con_ssh (str):
        auth_info (dict):
    Returns:
        A dict with vm_ids as key and an field's value as value.
        If the list is Empty return all the Ids with their status

    """
    ids_status = {}
    # list is empty then return the whole list with their status
    if not vm_ids:
        vm_ids = get_vms(con_ssh=con_ssh)

    if isinstance(vm_ids, str):
        vm_ids = [vm_ids]

    table_ = table_parser.table(cli.nova('list', '--all-tenant', ssh_client=con_ssh, auth_info=auth_info))

    for vm in vm_ids:
        ids_status[vm] = table_parser.get_values(table_=table_, target_header=field, ID=vm)

    return ids_status


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


def get_vm_volumes(vm_id, con_ssh=None, auth_info=None):
    """
    Get volume ids attached to given vm.

    Args:
        vm_id (str):
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (list): list of volume ids attached to specific vm

    """
    table_ = table_parser.table(cli.nova('show', vm_id, ssh_client=con_ssh, auth_info=auth_info))
    return _get_vm_volumes(table_)


def get_vm_info(vm_id, field, strict=False, con_ssh=None, auth_info=Tenant.ADMIN):
    table_ = table_parser.table(cli.nova('show', vm_id, ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_value_two_col_table(table_, field, strict)


def get_vm_host(vm_id, con_ssh=None):
    return get_vm_info(vm_id, ':host', strict=False, con_ssh=con_ssh, auth_info=Tenant.ADMIN)


def get_hypervisor_hosts(con_ssh=None):
    table_ = table_parser.table(cli.nova('hypervisor-list', ssh_client=con_ssh, auth_info=Tenant.ADMIN))
    return table_parser.get_column(table_, 'Hypervisor hostname')


def get_vms_on_hypervisor(hostname, con_ssh=None):
    """

    Args:
        hostname (str):Name of a compute node
        con_ssh:

    Returns (list): A list of VMs' ID under a hypervisor

    """
    table_ = table_parser.table(cli.nova('hypervisor-servers', hostname, ssh_client=con_ssh, auth_info=Tenant.ADMIN))
    return table_parser.get_column(table_, 'ID')


def get_vms_by_hypervisors(con_ssh=None):
    """

    Args:
        con_ssh:

    Returns (dict):return a dictionary where the host(hypervisor) is the key
    and value are a list of VMs under the host

    """
    host_vms = {}
    for host in get_hypervisor_hosts(con_ssh=con_ssh):
        host_vms[host] = get_vms_on_hypervisor(host, con_ssh)

    return host_vms


def _wait_for_vm_in_nova_list(vm_id, column='ID', timeout=VolumeTimeout.STATUS_CHANGE, fail_ok=True,
                              check_interval=3, con_ssh=None, auth_info=None):
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
    Return True if VM with given id exists. Else False.

    Args:
        vm_id (str):
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (bool):
    """
    exit_code, output = cli.nova('show', vm_id, fail_ok=True, ssh_client=con_ssh, auth_info=auth_info)
    return exit_code == 0


def get_vm_boot_info(vm_id, auth_info=None, con_ssh=None):
    """
    Get vm boot source and id.

    Args:
        vm_id (str):
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (dict): VM boot info dict. Format: {'type': <boot_source>, 'id': <source_id>}.
        <boot_source> is either 'volume' or 'image'

    """
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


def get_vm_image_name(vm_id, auth_info=Tenant.ADMIN, con_ssh=None):
    """

    Args:
        vm_id (str):
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (str): image name for the vm. If vm booted from volume, then image name in volume image metadata will be
        returned.

    """
    boot_info = get_vm_boot_info(vm_id, auth_info=auth_info, con_ssh=con_ssh)
    if boot_info['type'] == 'image':
        image_id = boot_info['id']
        image_show_table = table_parser.table(cli.glance('image-show', image_id))
        image_name = table_parser.get_value_two_col_table(image_show_table, 'image_name', strict=False)
        if not image_name:
            image_name = table_parser.get_value_two_col_table(image_show_table, 'name')
    else:      # booted from volume
        vol_show_table = table_parser.table(cli.cinder('show', boot_info['id'], auth_info=Tenant.ADMIN))
        image_meta_data = table_parser.get_value_two_col_table(vol_show_table, 'volume_image_metadata')
        image_name = eval(image_meta_data)['image_name']

    return image_name


def _get_vm_volumes(novashow_table):
    volumes = eval(table_parser.get_value_two_col_table(novashow_table, ':volumes_attached', strict=False))
    return [volume['id'] for volume in volumes]
