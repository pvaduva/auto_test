import random
import time

from consts.auth import Tenant
from utils import table_parser, cli
from utils.tis_log import LOG
from utils.ssh import ControllerClient
from consts.timeout import CMDTimeout


def get_alarms(name=None, strict=False, auth_info=Tenant.ADMIN, con_ssh=None):
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

    table_ = table_parser.table(cli.ceilometer('alarm-list', auth_info=auth_info, ssh_client=con_ssh))
    if name is None:
        return table_

    return table_parser.get_values(table_, 'Alarm ID', Name='STACK1', strict=strict)



def get_resources(header='Resource ID', limit=10, timeout=CMDTimeout.RESOURCE_LIST, con_ssh=None,
                  auth_info=Tenant.ADMIN):
    """
    Get a list of resources that can be tracked by Ceilometer
    Args:
        header (str): the column to get the values from
        con_ssh (SSHClient):
        auth_info (dict):
        limit (int): maximum number of resources to list
        timeout (int):

    Returns (list): a list of all the values in the header column of the returned resources

    """
    table_ = table_parser.table(cli.ceilometer('resource-list', '--limit={}'.format(limit),
                                auth_info=auth_info, timeout=timeout, ssh_client=con_ssh))
    values = table_parser.get_values(table_, target_header=header)

    return values


def get_samples(header='Resource ID', limit=10, con_ssh=None, auth_info=Tenant.ADMIN, **kwargs):
    """
    Gets the values from the header column from the list of samples
    Args:
        header (str): the header of the column to get values from
        limit (int): the max number of entries to return
        con_ssh (SSHClient):
        auth_info (dict):
        **kwargs (dict): key/value pairs to filter the list

    Returns (list): The values from the header column for all samples that match kwargs

    """
    args_ = '--limit={} '.format(limit)
    for key in kwargs:
        args_ += '--{} {} '.format(key, kwargs[key])
    table_ = table_parser.table(cli.ceilometer('sample-list', args_, auth_info=auth_info, ssh_client=con_ssh))
    values = table_parser.get_values(table_, header)
    return values


def create_sample(resource_id, field='message_id', con_ssh=None, auth_info=Tenant.ADMIN, **kwargs):
    """
    Creates a sample
    Args:
        resource_id (str): Resource ID of a resource
        field (str): the property of the value to return
        con_ssh (SSHClient):
        auth_info (dict):
        **kwargs: key/value paris to add as positional arguments

    Returns (str): the value of the new sample corresponding to the field given

    """
    args_ = '-r {} '.format(resource_id)
    for key in kwargs:
        args_ += '--{} {} '.format(key, kwargs[key])
    table_ = table_parser.table(cli.ceilometer('sample-create', args_, auth_info=auth_info, ssh_client=con_ssh))
    return table_parser.get_value_two_col_table(table_, field)


def delete_samples():
    """
    Calls sudo /usr/bin/ceilometer-expirer. Deletes all expired samples.
    Returns (int):
        0 if successfully called

    """
    LOG.info("Deleting expired ceilometer resources.")
    ssh_client = ControllerClient.get_active_controller()
    ssh_client.exec_sudo_cmd('/usr/bin/ceilometer-expirer', fail_ok=False)
