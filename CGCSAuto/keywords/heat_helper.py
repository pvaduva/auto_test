import random
import re

from keywords import common, nova_helper,ceilometer_helper,network_helper
from utils import table_parser, cli, exceptions
from utils.tis_log import LOG
from consts.auth import Tenant
from consts.cgcs import HOME
from consts.cgcs import HEAT_PATH
from utils.ssh import NATBoxClient, VMSSHClient, ControllerClient, SSHFromSSH
import os
import yaml
from consts.heat import Heat
import time


def _wait_for_heat_stack_deleted(stack_name=None, timeout=120, check_interval=3, con_ssh=None, auth_info=None):
    """
    This will wait for the heat stack to be deleted
    Args:
        stack_name(str): Heat stack name to check for state
        ccon_ssh (SSHClient): If None, active controller ssh will be used.
        auth_info (dict): Tenant dict. If None, primary tenant will be used.

    Returns:

    """
    LOG.info("Waiting for {} to be deleted...".format(stack_name))
    end_time = time.time() + timeout
    while time.time() < end_time:
        stack_status = get_stack_status(stack_name=stack_name, auth_info=auth_info)
        if not stack_status:
            return True

        time.sleep(check_interval)

    msg = "Heat stack {} did not get deleted within timeout".format(stack_name)

    LOG.warning(msg)
    return False


def wait_for_heat_state(stack_name=None, state=None, timeout=120, check_interval=3, con_ssh=None, auth_info=None):
    """
    This will wait for the desired state of the heat stack or timeout
    Args:
        stack_name(str): Heat stack name to check for state
        state(str): Status to check for
        ccon_ssh (SSHClient): If None, active controller ssh will be used.
        auth_info (dict): Tenant dict. If None, primary tenant will be used.

    Returns:

    """
    LOG.info("Waiting for {} to be shown in {} ...".format(stack_name,state))
    end_time = time.time() + timeout
    while time.time() < end_time:
        stack_status = get_stack_status(stack_name=stack_name, auth_info=auth_info)
        if state in stack_status:
            return True

        time.sleep(check_interval)

    msg = "Heat stack {} did not go to state {} within timeout".format(stack_name,state)

    LOG.warning(msg)
    return False


def get_stacks(name=None, con_ssh=None, auth_info=None):
    """
        Get the stacks list based on name if given for a given tenant.

        Args:
            con_ssh (SSHClient): If None, active controller ssh will be used.
            auth_info (dict): Tenant dict. If None, primary tenant will be used.
            name (str): Given name for the heat stack

        Returns (str): Heat stack id of a specific tenant.

    """

    table_ = table_parser.table(cli.heat('stack-list', ssh_client=con_ssh, auth_info=auth_info))
    if name is not None:
        return table_parser.get_values(table_, 'id', stack_name=name)
    else:
        return table_parser.get_column(table_, 'id')


def get_stack_status(stack_name=None, con_ssh=None, auth_info=None):
    """
        Get the stacks status based on name if given for a given tenant.

        Args:
            con_ssh (SSHClient): If None, active controller ssh will be used.
            auth_info (dict): Tenant dict. If None, primary tenant will be used.
            stack_name (str): Given name for the heat stack

        Returns (str): Heat stack status of a specific tenant.

    """

    table_ = table_parser.table(cli.heat('stack-list', ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_values(table_,'stack_status', stack_name=stack_name)


def delete_stack(stack_name, con_ssh=None, auth_info=None):
    """
        Delete the given heat stack for a given tenant.

        Args:
            con_ssh (SSHClient): If None, active controller ssh will be used.
            auth_info (dict): Tenant dict. If None, primary tenant will be used.
            stack_name (str): Given name for the heat stack

        Returns (list): Status and msg of the heat deletion.

    """

    if stack_name is None:
        return [1, "Stack name is missing in the arg"]

    LOG.info("Deleting Heat Stack %s", stack_name)
    exitcode, output = cli.heat('stack-delete', stack_name, ssh_client=con_ssh, auth_info=auth_info,
                                fail_ok=True, rtn_list=True)
    if exitcode == 1:
        LOG.warning("Delete heat stack request rejected.")
        return [1, output]

    return _wait_for_heat_stack_deleted(stack_name=stack_name, auth_info=auth_info)


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
        return 'small'
    elif param_name is 'IMAGE':
        return 'cgcs-guest'
    else:
        return None
