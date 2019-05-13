import time

from utils import table_parser, cli, exceptions
from utils.tis_log import LOG
from utils.clients.ssh import get_cli_client
from consts.cgcs import GuestImages, HeatStackStatus, HEAT_CUSTOM_TEMPLATES
from consts.filepaths import TestServerPath
from keywords import network_helper, common
from testfixtures.fixture_resources import ResourceCleanup


def _wait_for_heat_stack_deleted(stack_name=None, timeout=120, check_interval=3, con_ssh=None, auth_info=None):
    """
    This will wait for the heat stack to be deleted
    Args:
        stack_name(str): Heat stack name to check for state
        con_ssh (SSHClient): If None, active controller ssh will be used.
        auth_info (dict): Tenant dict. If None, primary tenant will be used.

    Returns:

    """
    LOG.info("Waiting for {} to be deleted...".format(stack_name))
    end_time = time.time() + timeout
    while time.time() < end_time:
        stack_status = get_stack_status(stack_name=stack_name, auth_info=auth_info, con_ssh=con_ssh)
        if not stack_status:
            return True
        elif stack_status[0] == HeatStackStatus.DELETE_FAILED:
            LOG.warning('Heat stack in DELETE_FAILED state')
            return False

        time.sleep(check_interval)

    msg = "Heat stack {} did not get deleted within timeout".format(stack_name)

    LOG.warning(msg)
    return False


def wait_for_heat_status(stack_name=None, status=HeatStackStatus.CREATE_COMPLETE, timeout=300, check_interval=5,
                         fail_ok=False, con_ssh=None, auth_info=None):
    """
    This will wait for the desired state of the heat stack or timeout
    Args:
        stack_name(str): Heat stack name to check for state
        status(str): Status to check for
        timeout (int)
        check_interval (int)
        fail_ok (bool
        con_ssh (SSHClient): If None, active controller ssh will be used.
        auth_info (dict): Tenant dict. If None, primary tenant will be used.

    Returns (tuple): <res_bool>, <msg>

    """
    LOG.info("Waiting for {} to be shown in {} ...".format(stack_name, status))
    end_time = time.time() + timeout

    fail_status = current_status = None
    if status == HeatStackStatus.CREATE_COMPLETE:
        fail_status = HeatStackStatus.CREATE_FAILED
    elif status == HeatStackStatus.UPDATE_COMPLETE:
        fail_status = HeatStackStatus.UPDATE_FAILED

    while time.time() < end_time:
        current_status = get_stack_status(stack_name=stack_name, auth_info=auth_info, con_ssh=con_ssh)[0]
        if status == current_status:
            return True, 'Heat stack {} has reached {} status'.format(stack_name, status)
        elif fail_status == current_status:
            stack_id = get_stack_value(stack=stack_name, rtn_val='id', auth_info=auth_info, con_ssh=con_ssh)
            get_stack_resources(stack=stack_id, auth_info=auth_info, con_ssh=con_ssh)

            err = "Heat stack {} failed to reach {}, actual status: {}".format(stack_name, status, fail_status)
            if fail_ok:
                LOG.warning(err)
                return False, err
            raise exceptions.HeatError(err)

        time.sleep(check_interval)

    stack_id = get_stack_value(stack=stack_name, rtn_val='id', auth_info=auth_info, con_ssh=con_ssh)
    get_stack_resources(stack=stack_id, auth_info=auth_info, con_ssh=con_ssh)
    err_msg = "Heat stack {} did not reach {} within {}s. Actual status: {}".format(stack_name, status, timeout,
                                                                                    current_status)
    if fail_ok:
        LOG.warning(err_msg)
        return False, err_msg
    raise exceptions.HeatError(err_msg)


def get_stack_value(stack, rtn_val='stack_status_reason', con_ssh=None, auth_info=None):
    table_ = table_parser.table(cli.openstack('stack show', stack, ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_value_two_col_table(table_=table_, field=rtn_val)


def get_stacks(name=None, con_ssh=None, auth_info=None, all_=True):
    """
    Get the stacks list based on name if given for a given tenant.

    Args:
        con_ssh (SSHClient): If None, active controller ssh will be used.
        auth_info (dict): Tenant dict. If None, primary tenant will be used.
        all_ (bool): whether to display all stacks for admin user
        name (str): Given name for the heat stack

    Returns (str): Heat stack id of a specific tenant.

    """
    args = ''
    if auth_info is not None:
        if auth_info['user'] == 'admin' and all_:
            args = '--a'
    table_ = table_parser.table(cli.openstack('stack list', positional_args=args, ssh_client=con_ssh,
                                              auth_info=auth_info))
    if name is not None:
        return table_parser.get_values(table_, 'id', stack_name=name)
    else:
        return table_parser.get_column(table_, 'id')


def get_stack_status(stack_name, con_ssh=None, auth_info=None, all_=True):
    """
    Get the stacks status based on name if given for a given tenant.

    Args:
        con_ssh (SSHClient): If None, active controller ssh will be used.
        auth_info (dict): Tenant dict. If None, primary tenant will be used.
        stack_name (str): Given name for the heat stack
        all_ (bool): Whether to list all stacks for admin user

    Returns (str): Heat stack status of a specific tenant.

    """
    args = ''
    if auth_info is not None:
        if auth_info['user'] == 'admin' and all_:
            args = '--a'
    table_ = table_parser.table(cli.openstack('stack list', args, ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_values(table_, 'Stack Status', ** {'Stack Name': stack_name})


def get_stack_resources(stack, rtn_val='resource_name', auth_info=None, con_ssh=None, **kwargs):
    """

    Args:
        stack (str): id (or name) for the heat stack. ID is required if admin user is used to display tenant resource.
        rtn_val: values to return
        auth_info:
        con_ssh:
        kwargs: key/value pair to filer out the values to return

    Returns (list):

    """
    table_ = table_parser.table(cli.openstack('stack resource list --long', stack, auth_info=auth_info,
                                              ssh_client=con_ssh))
    return table_parser.get_values(table_, target_header=rtn_val, **kwargs)


def delete_stack(stack_name, fail_ok=False, check_first=False, con_ssh=None, auth_info=None):
    """
    Delete the given heat stack for a given tenant.

    Args:
        con_ssh (SSHClient): If None, active controller ssh will be used.
        fail_ok (bool):
        check_first (bool): whether or not to check the stack existence before attempt to delete
        auth_info (dict): Tenant dict. If None, primary tenant will be used.
        stack_name (str): Given name for the heat stack

    Returns (tuple): Status and msg of the heat deletion.

    """

    if not stack_name:
        raise ValueError("stack_name is not provided.")

    if check_first:
        if not get_stack_status(stack_name, con_ssh=con_ssh, auth_info=auth_info):
            msg = "Heat stack {} doesn't exist on the system. Do nothing.".format(stack_name)
            LOG.info(msg)
            return -1, msg

    LOG.info("Deleting Heat Stack %s", stack_name)
    exitcode, output = cli.heat('stack-delete -y', stack_name, ssh_client=con_ssh, auth_info=auth_info,
                                fail_ok=fail_ok, rtn_code=True)
    if exitcode == 1:
        LOG.warning("Delete heat stack request rejected.")
        return 1, output

    if not _wait_for_heat_stack_deleted(stack_name=stack_name, auth_info=auth_info):
        stack_id = get_stack_value(stack=stack_name, rtn_val='id', auth_info=auth_info, con_ssh=con_ssh)
        get_stack_resources(stack=stack_id, auth_info=auth_info, con_ssh=con_ssh)

        msg = "heat stack {} is not removed after stack-delete.".format(stack_name)
        if fail_ok:
            LOG.warning(msg)
            return 2, msg
        raise exceptions.HeatError(msg)

    succ_msg = "Heat stack {} is successfully deleted.".format(stack_name)
    LOG.info(succ_msg)
    return 0, succ_msg


def get_heat_params(param_name=None):
    """
    Generate parameters for heat based on keywords

    Args:
        param_name (str): template to be used to create heat stack.

    Returns (str): return None if failure or the val for the given param

    """
    if param_name is 'NETWORK':
        net_id = network_helper.get_mgmt_net_id()
        return network_helper.get_net_name_from_id(net_id=net_id)
    elif param_name is 'FLAVOR':
        return 'small_ded'
    elif param_name is 'IMAGE':
        return GuestImages.DEFAULT_GUEST
    else:
        return None


def create_stack(stack_name, params_string, fail_ok=False, con_ssh=None, auth_info=None, cleanup='function',
                 timeout=300):
    """
    Create the given heat stack for a given tenant.

    Args:
        con_ssh (SSHClient): If None, active controller ssh will be used.
        fail_ok (bool):
        params_string: Parameters to pass to the heat create cmd. ex: -f <stack.yaml> -P IMAGE=tis <stack_name>
        auth_info (dict): Tenant dict. If None, primary tenant will be used.
        stack_name (str): Given name for the heat stack
        cleanup (str|None)

    Returns (tuple): Status and msg of the heat deletion.
    """

    if not params_string:
        raise ValueError("Parameters not provided.")

    LOG.info("Create Heat Stack %s", params_string)
    exitcode, output = cli.heat('stack-create', params_string, ssh_client=con_ssh, auth_info=auth_info,
                                fail_ok=fail_ok, timeout=timeout, rtn_code=True)
    if exitcode == 1:
        LOG.warning("Create heat stack request rejected.")
        return 1, output

    if cleanup:
        ResourceCleanup.add('heat_stack', resource_id=stack_name, scope=cleanup)

    LOG.info("Wait for Heat Stack Status to reach CREATE_COMPLETE for stack %s", stack_name)
    res, msg = wait_for_heat_status(stack_name=stack_name, status=HeatStackStatus.CREATE_COMPLETE,
                                    auth_info=auth_info, fail_ok=fail_ok)
    if not res:
        return 2, msg

    LOG.info("Stack {} created successfully".format(stack_name))
    return 0, stack_name


def update_stack(stack_name, params_string, fail_ok=False, con_ssh=None, auth_info=None, timeout=300):
    """
    Update the given heat stack for a given tenant.

    Args:
        con_ssh (SSHClient): If None, active controller ssh will be used.
        fail_ok (bool):
        params_string: Parameters to pass to the heat create cmd. ex: -f <stack.yaml> -P IMAGE=tis <stack_name>
        auth_info (dict): Tenant dict. If None, primary tenant will be used.
        stack_name (str): Given name for the heat stack

    Returns (tuple): Status and msg of the heat deletion.
    """

    if not params_string:
        raise ValueError("Parameters not provided.")

    LOG.info("Create Heat Stack %s", params_string)
    exitcode, output = cli.heat('stack-update', params_string, ssh_client=con_ssh, auth_info=auth_info,
                                fail_ok=fail_ok, rtn_code=True)
    if exitcode == 1:
        LOG.warning("Create heat stack request rejected.")
        return 1, output

    LOG.info("Wait for Heat Stack Status to reach UPDATE_COMPLETE for stack %s", stack_name)
    res, msg = wait_for_heat_status(stack_name=stack_name, status=HeatStackStatus.UPDATE_COMPLETE,
                                    auth_info=auth_info, fail_ok=fail_ok,timeout=timeout)
    if not res:
        return 2, msg

    LOG.info("Stack {} updated successfully".format(stack_name))
    return 0, stack_name


def get_custom_heat_files(file_name, file_dir=HEAT_CUSTOM_TEMPLATES, cli_client=None):
    """

    Args:
        file_name:
        file_dir:
        cli_client:

    Returns:

    """
    file_path = '{}/{}'.format(file_dir, file_name)

    if cli_client is None:
        cli_client = get_cli_client()

    if not cli_client.file_exists(file_path=file_path):
        LOG.debug('Create userdata directory if not already exists')
        cmd = 'mkdir -p {}'.format(file_dir)
        cli_client.exec_cmd(cmd, fail_ok=False)
        source_file = TestServerPath.CUSTOM_HEAT_TEMPLATES + file_name
        dest_path = common.scp_from_test_server_to_user_file_dir(source_path=source_file, dest_dir=file_dir,
                                                                 dest_name=file_name, timeout=300, con_ssh=cli_client)
        if dest_path is None:
            raise exceptions.CommonError("Heat template file {} does not exist after download".format(file_path))

    return file_path
