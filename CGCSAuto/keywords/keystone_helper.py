import time

from utils import cli, exceptions, table_parser
from utils.tis_log import LOG
from utils.ssh import ControllerClient

from consts.auth import Tenant
from keywords import common


def get_role_ids(role_name, con_ssh=None):
    table_ = table_parser.table(cli.openstack('role list', ssh_client=con_ssh, auth_info=Tenant.ADMIN))
    return table_parser.get_values(table_, 'ID', Name=role_name)


def get_tenant_ids(tenant_name=None, con_ssh=None):
    """
    Return a list of tenant id(s) with given tenant name.

    Args:
        tenant_name (str): openstack tenant name. e.g., 'admin', 'tenant1'. If None, the primary tenant will be used.
        con_ssh (SSHClient): If None, active controller client will be used, assuming set_active_controller was called.

    Returns (list): list of tenant id(s)

    """
    if tenant_name is None:
        tenant_name = Tenant.get_primary()['tenant']
    table_ = table_parser.table(cli.openstack('project list', ssh_client=con_ssh, auth_info=Tenant.ADMIN))
    return table_parser.get_values(table_, 'ID', Name=tenant_name)


def get_user_ids(user_name=None, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Return a list of user id(s) with given user name.

    Args:
        user_name (str): openstack user name. If None, the current user for primary tenant will be used
        con_ssh (SSHClient):

    Returns (list): list of user id(s)

    """
    if user_name is None:
        user_name = Tenant.get_primary()['user']
    table_ = table_parser.table(cli.openstack('user list', ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_values(table_, 'ID', Name=user_name)


def add_or_remove_role(add_=True, role='admin', project=None, user=None, domain=None, group=None, group_domain=None,
                       project_domain=None, user_domain=None, inherited=None, check_first=True, fail_ok=False,
                       con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Add or remove given role for specified user and tenant. e.g., add admin role to tenant2 user on tenant2 project

    Args:
        add_(bool): whether to add or remove
        role (str): an existing role from openstack role list
        project (str): tenant name. When unset, the primary tenant name will be used
        user (str): an existing user that belongs to given tenant
        domain (str): Include <domain> (name or ID)
        group (str): Include <group> (name or ID)
        group_domain (str): Domain the group belongs to (name or ID). This can be used in case collisions
                between group names exist.
        project_domain (str): Domain the project belongs to (name or ID). This can be used in case collisions
                between project names exist.
        user_domain (str): Domain the user belongs to (name or ID). This can be used in case collisions
                between user names exist.
        inherited (bool): Specifies if the role grant is inheritable to the sub projects
        check_first (bool): whether to check if role already exists for given user and tenant
        fail_ok (bool): whether to throw exception on failure
        con_ssh (SSHClient): active controller ssh session
        auth_info (dict): auth info to use to executing the add role cli

    Returns (tuple):

    """
    tenant_dict = {}

    if project is None:
        tenant_dict = Tenant.get_primary()
        project = tenant_dict['tenant']

    if user is None:
        user = tenant_dict.get('user', project)

    if check_first:
        existing_roles = get_assigned_roles(role=role, project=project, user=user, user_domain=user_domain, group=group,
                                            group_domain=group_domain, domain=domain,
                                            project_domain=project_domain, inherited=inherited, effective_only=False,
                                            con_ssh=con_ssh, auth_info=auth_info)
        if existing_roles:
            if add_:
                msg = "Role already exists with given criteria: {}".format(existing_roles)
                LOG.info(msg)
                return -1, msg
        else:
            if not add_:
                msg = "Role with given criteria does not exist. Do nothing."
                LOG.info(msg)
                return -1, msg

    msg_str = 'Add' if add_ else 'Remov'
    LOG.info("{}ing {} role to {} user under {} project".format(msg_str, role, user, project))

    sub_cmd = "--user {} --project {}".format(user, project)
    if inherited is True:
        sub_cmd += ' --inherited'

    optional_args = {
        'domain': domain,
        'group': group,
        'group-domain': group_domain,
        'project-domain': project_domain,
        'user-domain': user_domain,
    }

    for key, val in optional_args.items():
        if val is not None:
            sub_cmd += ' --{} {}'.format(key, val)

    sub_cmd += ' {}'.format(role)

    cmd = 'role add' if add_ else 'role remove'
    res, out = cli.openstack(cmd, sub_cmd, rtn_list=True, fail_ok=fail_ok, ssh_client=con_ssh,
                             auth_info=auth_info)

    if res == 1:
        return 1, out

    LOG.info("{} cli accepted. Check role is {}ed successfully".format(cmd, msg_str))
    post_roles = get_assigned_roles(role=role, project=project, user=user, user_domain=user_domain, group=group,
                                    group_domain=group_domain, domain=domain,
                                    project_domain=project_domain, inherited=inherited, effective_only=True,
                                    con_ssh=con_ssh, auth_info=auth_info)

    err_msg = ''
    if add_ and not post_roles:
        err_msg = "No role is added with given criteria"
    elif post_roles and not add_:
        err_msg = "Role is not removed"
    if err_msg:
        if fail_ok:
            LOG.warning(err_msg)
            return 2, err_msg
        else:
            raise exceptions.KeystoneError(err_msg)

    succ_msg = "Role is successfully {}ed".format(msg_str)
    LOG.info(succ_msg)
    return 0, succ_msg


def get_assigned_roles(rtn_val='Role', names=True, role=None, user=None, project=None, user_domain=None, group=None,
                       group_domain=None, domain=None, project_domain=None, inherited=None, effective_only=None,
                       con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Get values from 'openstack role assignment list' table

    Args:
        rtn_val (str): role assignment table header to determine which values to return
        names (bool): whether to display role assignment with name (default is ID)
        role (str): an existing role from openstack role list
        project (str): tenant name. When unset, the primary tenant name will be used
        user (str): an existing user that belongs to given tenant
        domain (str): Include <domain> (name or ID)
        group (str): Include <group> (name or ID)
        group_domain (str): Domain the group belongs to (name or ID). This can be used in case collisions
                between group names exist.
        project_domain (str): Domain the project belongs to (name or ID). This can be used in case collisions
                between project names exist.
        user_domain (str): Domain the user belongs to (name or ID). This can be used in case collisions
                between user names exist.
        inherited (bool): Specifies if the role grant is inheritable to the sub projects
        effective_only (bool): Whether to show effective roles only
        con_ssh (SSHClient): active controller ssh session
        auth_info (dict): auth info to use to executing the add role cli

    Returns (list): list of values

    """
    sub_cmd = ''
    if names:
        sub_cmd += ' --names'
    if effective_only:
        sub_cmd += ' --effective'
    if inherited:
        sub_cmd += ' --inherited'

    optional_args = {
        'role': role,
        'user': user,
        'project': project,
        'domain': domain,
        'group': group,
        'group-domain': group_domain,
        'project-domain': project_domain,
        'user-domain': user_domain,
    }

    for key, val in optional_args.items():
        if val is not None:
            sub_cmd += ' --{} {}'.format(key, val)

    role_assignment_tab = table_parser.table(cli.openstack('role assignment list', sub_cmd, ssh_client=con_ssh,
                                                           auth_info=auth_info))

    if not role_assignment_tab['headers']:
        LOG.info("No role assignment is found with criteria: {}".format(sub_cmd))
        return []

    return table_parser.get_column(role_assignment_tab, rtn_val)


def update_user(user, name=None, project=None, password=None, project_doamin=None, email=None, description=None,
                enable=None, fail_ok=False, auth_info=Tenant.ADMIN, con_ssh=None):

    LOG.info("Updating {}...".format(user))
    arg = ''
    optional_args = {
        'name': name,
        'project': project,
        'password': password,
        'project-domain': project_doamin,
        'email': email,
        'description': description,
    }
    for key, val in optional_args.items():
        if val is not None:
            arg += "--{} '{}' ".format(key, val)

    if enable is not None:
        arg += '--{} '.format('enable' if enable else 'disable')

    if not arg.strip():
        raise ValueError("Please specify the param(s) and value(s) to change to")

    arg += user

    code, output = cli.openstack('user set', arg, auth_info=auth_info, ssh_client=con_ssh, fail_ok=fail_ok,
                                 rtn_list=True)

    if code == 1:
        return code, output

    if name or project or password:
        tenant_dictname = user.upper()
        Tenant.update_tenant_dict(tenant_dictname, username=name, password=password, tenant=project)

    msg = 'User {} updated successfully'.format(user)
    LOG.info(msg)
    return 0, msg


def get_endpoints(rtn_val='ID', endpoint_id=None, service_name=None, service_type=None, enabled=None, interface="admin",
                  region=None, url=None, strict=False, auth_info=Tenant.ADMIN, con_ssh=None):
    """
    Get a list of endpoints with given arguments
    Args:
        rtn_val (str): valid header of openstack endpoints list table. 'ID'
        endpoint_id (str): id of the endpoint
        service_name (str): Service name of endpoint like novaav3, neutron, keystone. vim, heat, swift, etc
        service_type(str): Service type
        enabled (str): True/False
        interface (str): Interface of endpoints. valid entries: admin, internal, public
        region (str): RegionOne or RegionTwo
        url (str): url of endpoint
        strict(bool):
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (list):

    """
    table_ = table_parser.table(cli.openstack('endpoint list', ssh_client=con_ssh, auth_info=auth_info))

    args_dict = {
        'ID': endpoint_id,
        'Service Name': service_name,
        'Service Type': service_type,
        'Enabled': enabled,
        'Interface': interface,
        'URL': url,
        'Region': region,
    }

    kwargs = {}
    for key, value in args_dict.items():
        if value:
            kwargs[key] = value

    endpoints = table_parser.get_values(table_, rtn_val, strict=strict, regex=True, merge_lines=True, **kwargs)
    return endpoints


def get_endpoints_value(endpoint_id, target_field, con_ssh=None):
    """
    Gets the  endpoint target field value for given  endpoint Id
    Args:
        endpoint_id: the endpoint id to get the value of
        target_field: the target field name to retrieve value of
        con_ssh:

    Returns: list of endpoint field values

    """
    args = endpoint_id
    table_ = table_parser.table(cli.openstack('endpoint show', args,  ssh_client=con_ssh, auth_info=Tenant.ADMIN))
    return table_parser.get_value_two_col_table(table_, target_field)


def is_https_lab(con_ssh=None, source_admin=True, auth_info=Tenant.ADMIN):
    if not con_ssh:
        con_ssh = ControllerClient.get_active_controller()
    table_ = table_parser.table(cli.openstack('endpoint list', source_admin_=source_admin, ssh_client=con_ssh,
                                              auth_info=auth_info))
    con_ssh.exec_cmd('unset OS_REGION_NAME')    # Workaround for CGTS-8348
    filters = {'Service Name': 'keystone', 'Service Type': 'identity', 'Interface': 'public'}
    keystone_pub = table_parser.get_values(table_=table_, target_header='URL', **filters)[0]
    return 'https' in keystone_pub


def delete_users(user, fail_ok=False):
    """
    Delete the given openstack user
    Args:
        user: user name to delete
        fail_ok: if the deletion expected to fail

    Returns: tuple, (code, msg)
    """
    return cli.openstack('user delete', user, auth_info=Tenant.ADMIN, fail_ok=fail_ok)

