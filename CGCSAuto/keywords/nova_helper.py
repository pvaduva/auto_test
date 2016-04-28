import random
import re

from utils import cli, exceptions
from utils import table_parser
from utils.tis_log import LOG
from consts.auth import Tenant
from consts.cgcs import BOOT_FROM_VOLUME, UUID
from keywords import keystone_helper, host_helper
from keywords.common import Count


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

    Returns (tuple): (rtn_code (int), flavor_id/err_msg (str))
        (0, <flavor_id>): flavor created successfully
        (1, <stderr>): create flavor cli rejected

    """
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

    LOG.info("Creating flavor {}...".format(flavor_name))
    exit_code, output = cli.nova('flavor-create', subcmd, ssh_client=con_ssh, fail_ok=fail_ok, auth_info=auth_info,
                                 rtn_list=True)

    if exit_code == 1:
        return 1, output

    table_ = table_parser.table(output)
    flavor_id = table_parser.get_column(table_, 'ID')[0]
    LOG.info("Flavor {} created successfully.".format(flavor_name))
    return 0, flavor_id


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
        return -1, 'None of the flavor(s) exists. Do nothing.'

    if flavors_deleted:
        LOG.warning("Some flavor(s) do no exist on system. Skip them: {}".format(flavors_deleted))

    LOG.info("Flavor(s) to delete: {}".format(flavors_to_del))
    results = {}
    fail = False
    for flavor in flavors_to_del:
        LOG.info("Deleting flavor {}...".format(flavor))
        # Always get the result for individual flavor, so deletion will be attempted to all flavors instead of failing
        # right away upon one failure
        rtn_code, output = cli.nova('flavor-delete', flavor, fail_ok=True, ssh_client=con_ssh, auth_info=auth_info)
        if rtn_code == 1:
            result = (1, output)
            fail = True
        elif flavor_exists(flavor, con_ssh=con_ssh, auth_info=auth_info):
            result = (2, "Flavor {} still exists on system after deleted.".format(flavor))
            fail = True
        else:
            result = (0, 'Flavor is successfully deleted')
        results[flavor] = result
    if fail:
        if fail_ok:
            return 1, results
        raise exceptions.FlavorError("Failed to delete flavor(s). Details: {}".format(results))

    success_msg = "Flavor(s) deleted successfully."
    LOG.info(success_msg)
    return 0, success_msg


def get_flavor_id(name=None, memory=None, disk=None, ephemeral=None, swap=None, vcpu=None, rxtx=None, is_public=None,
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

    Returns (tuple): (rtn_code (int), message (str))
        (0, 'Flavor extra specs set successfully.'): required extra spec(s) added successfully
        (1, <stderr>): add extra spec cli rejected
        (2, 'Required extra spec <spec_name> is not found in the extra specs list'): post action check failed
        (3, 'Extra spec value for <spec_name> is not <spec_value>'): post action check failed

    """
    if not extra_specs:
        raise ValueError("extra_specs is not provided. At least one name=value pair is required.")

    LOG.info("Setting flavor extra specs: {}".format(extra_specs))
    extra_specs_args = ''
    for key, value in extra_specs.items():
        extra_specs_args += " {}={}".format(key, value)
    exit_code, output = cli.nova('flavor-key', '{} set {}'.format(flavor, extra_specs_args),
                                 ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok, rtn_list=True)

    if exit_code == 1:
        return 1, output

    extra_specs = get_flavor_extra_specs(flavor, con_ssh=con_ssh, auth_info=auth_info)
    for key, value in extra_specs.items():
        if key not in extra_specs:
            code = 2
            msg = "Required extra spec {} is not found in the extra specs list".format(key)
            break
        if extra_specs[key] != value:
            code = 3
            msg = "Extra spec value for {} is not {}".format(key, value)
            break
    else:
        code = 0
        msg = "Flavor extra specs set successfully."

    if code > 0:
        if fail_ok:
            LOG.warning(msg)
        else:
            raise exceptions.FlavorError(msg)
    else:
        LOG.info(msg)

    return code, msg


def unset_flavor_extra_specs(flavor, extra_specs, check_first=True, con_ssh=None, auth_info=Tenant.ADMIN, fail_ok=False):
    """
    Unset specific extra spec(s) from given flavor.

    Args:
        flavor (str): id of the flavor
        con_ssh (SSHClient):
        auth_info (dict):
        fail_ok (bool):
        extra_specs (str|list): extra spec(s) to be removed. At least one should be provided.

    Returns (tuple): (rtn_code (int), message (str))
        (0, 'Flavor extra specs unset successfully.'): required extra spec(s) removed successfully
        (1, <stderr>): unset extra spec cli rejected
        (2, '<spec_name> is still in the extra specs list'): post action check failed

    """

    LOG.info("Unsetting flavor extra spec(s): {}".format(extra_specs))

    if isinstance(extra_specs, str):
        extra_specs = [extra_specs]

    if check_first:
        keys_to_del = []
        existing_specs = get_flavor_extra_specs(flavor, con_ssh=con_ssh, auth_info=auth_info)
        for key in extra_specs:
            if key in existing_specs:
                keys_to_del.append(key)
        if not keys_to_del:
            msg = "Extra spec(s) {} not exist in flavor. Do nothing.".format(extra_specs)
            LOG.info(msg)
            return -1, msg

        extra_specs = keys_to_del

    extra_specs_args = ' '.join(extra_specs)
    exit_code, output = cli.nova('flavor-key', '{} unset {}'.format(flavor, extra_specs_args),
                                 ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok, rtn_list=True)
    if exit_code == 1:
        return 1, output

    post_extra_specs = get_flavor_extra_specs(flavor, con_ssh=con_ssh, auth_info=auth_info)
    for key in extra_specs:
        if key in post_extra_specs:
            err_msg = "{} is still in the extra specs list after unset.".format(key)
            if fail_ok:
                LOG.warning(err_msg)
                return 2, err_msg
            raise exceptions.FlavorError(err_msg)
    else:
        success_msg = "Flavor extra specs unset successfully."
        LOG.info(success_msg)
        return 0, success_msg


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

    Returns (list): list of all vms on the system

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
    Returns (dict):
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


def get_vm_storage_type(vm_id, con_ssh=None):
    flavor_output = get_vm_nova_show_value(vm_id=vm_id, field='flavor', strict=True, con_ssh=con_ssh, auth_info=Tenant.ADMIN)
    flavor_id = re.search(r'\((.*)\)', flavor_output).group(1)

    table_ = table_parser.table(cli.nova('flavor-show', flavor_id, ssh_client=con_ssh, auth_info=Tenant.ADMIN))
    extra_specs = eval(table_parser.get_value_two_col_table(table_, 'extra_specs'))
    return extra_specs['aggregate_instance_extra_specs:storage']


def get_vms(return_val='ID', con_ssh=None, auth_info=None, all_vms=False):
    """
    get a list of VM IDs or Names for given tenant in auth_info param.

    Args:
        return_val (str): 'ID' or 'Name'
        con_ssh (SSHClient): controller SSHClient.
        auth_info (dict): such as ones in auth.py: auth.ADMIN, auth.TENANT1
        all_vms (bool): whether to return VMs for all tenants if admin auth_info is given

    Returns (list): list of VMs for tenant(s).

    """
    positional_args = ''
    if all_vms is True:
        if auth_info is None:
            auth_info = Tenant.get_primary()
        if auth_info['tenant'] == 'admin':
            positional_args = '--all-tenant'
    table_ = table_parser.table(cli.nova('list', positional_args=positional_args, ssh_client=con_ssh,
                                         auth_info=auth_info))
    return table_parser.get_column(table_, return_val)


def get_vm_nova_show_values(vm_id, fields, strict=False, con_ssh=None, auth_info=Tenant.ADMIN):
    table_ = table_parser.table(cli.nova('show', vm_id, ssh_client=con_ssh, auth_info=auth_info))
    values = []
    for field in fields:
        value = table_parser.get_value_two_col_table(table_, field, strict)
        values.append(value)
    return values


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

    Returns (tuple): list of volume ids attached to specific vm

    """
    table_ = table_parser.table(cli.nova('show', vm_id, ssh_client=con_ssh, auth_info=auth_info))
    return _get_vm_volumes(table_)


def get_vm_nova_show_value(vm_id, field, strict=False, con_ssh=None, auth_info=Tenant.ADMIN):
    table_ = table_parser.table(cli.nova('show', vm_id, ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_value_two_col_table(table_, field, strict)


def get_vms_info(vm_ids=None, field='Status', con_ssh=None, auth_info=Tenant.ADMIN):
    table_ = table_parser.table(cli.nova('list --all-tenant', ssh_client=con_ssh, auth_info=auth_info))
    if vm_ids:
        table_ = table_parser.filter_table(table_, ID=vm_ids)
    else:
        vm_ids = table_parser.get_column(table_, header='ID')

    info = table_parser.get_column(table_, header=field)
    return dict(zip(vm_ids, info))


def get_vm_flavor(vm_id, con_ssh=None, auth_info=Tenant.ADMIN):
    flavor_output = get_vm_nova_show_value(vm_id, field='flavor', strict=True, con_ssh=con_ssh, auth_info=auth_info)
    return re.search(r'\((.*)\)', flavor_output).group(1)


def get_vm_host(vm_id, con_ssh=None):
    return get_vm_nova_show_value(vm_id, ':host', strict=False, con_ssh=con_ssh, auth_info=Tenant.ADMIN)


def get_vms_on_hypervisor(hostname, con_ssh=None, rtn_val='ID'):
    """

    Args:
        rtn_val: ID or Name
        hostname (str):Name of a compute node
        con_ssh:

    Returns (list): A list of VMs' ID under a hypervisor

    """
    table_ = table_parser.table(cli.nova('hypervisor-servers', hostname, ssh_client=con_ssh, auth_info=Tenant.ADMIN))
    return table_parser.get_column(table_, rtn_val)


def get_vms_by_hypervisors(con_ssh=None, rtn_val='ID'):
    """

    Args:
        con_ssh (SSHClient):
        rtn_val (str): ID or Name. Whether to return Names or IDs

    Returns (dict):return a dictionary where the host(hypervisor) is the key
    and value are a list of VMs under the host

    """
    host_vms = {}
    for host in host_helper.get_hypervisors(con_ssh=con_ssh):
        host_vms[host] = get_vms_on_hypervisor(host, con_ssh, rtn_val=rtn_val)

    return host_vms


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
    """
    Args:
        novashow_table (dict):

    Returns (list: A list of volume ids from the novashow_table.

    """
    volumes = eval(table_parser.get_value_two_col_table(novashow_table, ':volumes_attached', strict=False))
    return [volume['id'] for volume in volumes]


def get_quotas(quotas=None, con_ssh=None, auth_info=None):
    if not quotas:
        quotas = 'instances'
    if isinstance(quotas, str):
        quotas = [quotas]
    table_ = table_parser.table(cli.nova('quota-show', ssh_client=con_ssh, auth_info=auth_info))
    values = []
    for item in quotas:
        values.append(int(table_parser.get_value_two_col_table(table_, item)))

    return values


def update_quotas(tenant=None, force=False, con_ssh=None, auth_info=Tenant.ADMIN, **kwargs):
    if tenant is None:
        tenant = Tenant.get_primary()['tenant']

    tenant_id = keystone_helper.get_tenant_ids(tenant_name=tenant, con_ssh=con_ssh)[0]
    if not kwargs:
        raise ValueError("Please specify at least one quota=value pair via kwargs.")

    args_ = ''
    for key in kwargs:
        args_ += '--{} {} '.format(key, kwargs[key])

    if force:
        args_ += '--force '
    args_ += tenant_id

    cli.nova('quota-update', args_, ssh_client=con_ssh, auth_info=auth_info)


def set_image_metadata(image, fail_ok=False, auth_info=Tenant.ADMIN, con_ssh=None, **kwargs):

    LOG.info("Setting image {} metadata to: {}".format(image, kwargs))
    if not kwargs:
        raise ValueError("At least one key-value pair")

    meta_args = ''
    args_dict = {}
    for key, value in kwargs.items():
        key = key.lower().strip()
        value = str(value).strip()
        args_dict[key] = value
        meta_data = "{}={}".format(key, value)
        meta_args = ' '.join([meta_args, meta_data])

    positional_args = ' '.join([image, 'set', meta_args])
    code, output = cli.nova('image-meta', positional_args, ssh_client=con_ssh, auth_info=auth_info,
                            fail_ok=fail_ok, rtn_list=True)

    if code == 1:
        return 1, output

    LOG.info("Checking image {} metadata is set to {}".format(image, kwargs))
    actual_metadata = get_image_metadata(image, list(args_dict.keys()), con_ssh=con_ssh)
    for key, value in args_dict.items():
        if key not in actual_metadata:
            msg = "Expected metadata {} is not listed in nova image-show {}".format(key, image)
            if fail_ok:
                LOG.warning(msg)
                return 2, msg
            raise exceptions.ImageError(msg)

        if actual_metadata[key] != value:
            msg = "Metadata {} value is not set to {} in nova image-show {}".format(key, value, image)
            if fail_ok:
                LOG.warning(msg)
                return 3, msg
            raise exceptions.ImageError(msg)

    msg = "Image metadata is successfully set."
    LOG.info(msg)
    return 0, msg


def get_image_metadata(image, meta_keys, auth_info=Tenant.ADMIN, con_ssh=None):
    """

    Args:
        image (str): id of image
        meta_keys (str|list): list of metadata key(s) to get value(s) for
        auth_info (dict): Admin by default
        con_ssh (SSHClient):

    Returns (dict): image metadata in a dictionary.
        Examples: {'hw_mem_page_size': any}
    """
    if isinstance(meta_keys, str):
        meta_keys = [meta_keys]

    for meta_key in meta_keys:
        str(meta_key).replace(':', '_')

    table_ = table_parser.table(cli.nova('image-show', image, ssh_client=con_ssh, auth_info=auth_info))
    results = {}
    for meta_key in meta_keys:
        meta_key = meta_key.strip()
        value = table_parser.get_value_two_col_table(table_, 'metadata '+meta_key, strict=False)
        if value:
            results[meta_key] = value

    return results


def delete_image_metadata(image, meta_keys, check_first=True, fail_ok=False, auth_info=Tenant.ADMIN, con_ssh=None):
    """
     Unset specific extra spec(s) from given flavor.

     Args:
         image (str): id of the flavor
         con_ssh (SSHClient):
         auth_info (dict):
         fail_ok (bool):
         meta_keys (str|list): metadata(s) to be removed. At least one should be provided.

     Returns (tuple): (rtn_code (int), message (str))
         (0, 'Image metadata unset successfully.'): required extra spec(s) removed successfully
         (1, <stderr>): unset image metadata cli rejected
         (2, '<metadata> is still in the extra specs list'): post action check failed

     """

    LOG.info("Deleting image metadata: {}".format(meta_keys))
    if check_first:
        if not get_image_metadata(image, meta_keys, auth_info=auth_info, con_ssh=con_ssh):
            msg = "Metadata {} not exist in nova image-show. Do nothing.".format(meta_keys)
            LOG.info(msg)
            return -1, msg

    if isinstance(meta_keys, str):
        meta_keys = [meta_keys]

    for meta_key in meta_keys:
        str(meta_key).replace(':', '_')

    meta_keys_args = ' '.join(meta_keys)
    exit_code, output = cli.nova('image-meta', '{} delete {}'.format(image, meta_keys_args), fail_ok=fail_ok,
                                 ssh_client=con_ssh, auth_info=auth_info, rtn_list=True)
    if exit_code == 1:
        return 1, output

    post_meta_keys = get_image_metadata(image, meta_keys, con_ssh=con_ssh, auth_info=auth_info)
    for key in meta_keys:
        if key in post_meta_keys:
            err_msg = "{} is still in the image metadata after deletion.".format(key)
            if fail_ok:
                LOG.warning(err_msg)
                return 2, err_msg
            raise exceptions.ImageError(err_msg)
    else:
        success_msg = "Image metadata unset successfully."
        LOG.info(success_msg)
        return 0, success_msg

