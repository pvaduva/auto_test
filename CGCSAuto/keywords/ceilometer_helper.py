import time

from consts.auth import Tenant
from consts.timeout import CMDTimeout, CeilTimeout
from utils import exceptions
from utils import table_parser, cli
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG


def get_alarms(name=None, strict=False, auth_info=Tenant.ADMIN, con_ssh=None):
    """

    Args:
        name:
        strict:
        auth_info:
        con_ssh:

    Returns:

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


def get_samples(header='Resource ID', limit=10, meter=None, query=None, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Gets the values from the header column from the list of samples
    Args:
        header (str): the header of the column to get values from
        limit (int): the max number of entries to return
        meter (str|None): Name of meter to show samples for
        con_ssh (SSHClient):
        auth_info (dict):
        query (str): format: key[op]data_type::value; list.
            data_type is optional, but if supplied must be string, integer, float, or boolean.

    Returns (list): The values from the header column for all samples that match kwargs

    """
    args_ = '--limit={}'.format(limit)

    if meter is not None:
        args_ += ' --meter {}'.format(meter)

    if query is not None:
        args_ += ' --query {}'.format(query)

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
    ssh_client.exec_sudo_cmd('/usr/bin/ceilometer-expirer', fail_ok=False, expect_timeout=90)


def wait_for_sample_expire(meter, timeout=CeilTimeout.EXPIRE, fail_ok=False, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Wait for given sample to disappear from 'ceilometer sample-list'
    Args:
        meter (str): filter out samples
        timeout (int): max wait time in seconds
        fail_ok (bool): whether to raise exception if sample did not expire before timeout reaches
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (bool):

    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        samples = get_samples(meter=meter, con_ssh=con_ssh, auth_info=auth_info)
        if not samples:
            LOG.info("Sample {} is not listed in 'ceilometer sample-list'".format(meter))
            return True
        time.sleep(3)

    err_msg = "Sample {} is still listed after {} seconds".format(meter, timeout)
    if fail_ok:
        LOG.warning(err_msg)
        return False
    raise exceptions.CeilometerError(err_msg)


def get_statistics_table(meter, period=None, groupby=None, aggregate=None, query=None, auth_info=Tenant.ADMIN,
                         con_ssh=None):
    """
    Get ceilometer statistics with given criteria
    Args:
        meter (str): Name of meter to list statistics for
        period (int): seconds over which to group samples
        groupby (str): field for group by
        aggregate (str): <FUNC>[<-<PARAM>]
        query (str): format: key[op]data_type::value; list.
            data_type is optional, but if supplied must be string, integer, float, or boolean.
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (dict): table. format: {'headers': [<headers>], 'values': [[<row[0] values>], ...]}

    """
    args_ = '--meter {}'.format(meter)

    if query is not None:
        args_ = '--query {} '.format(query) + args_

    if period is not None:
        args_ += ' --period {}'.format(period)

    if groupby is not None:
        args_ += ' --groupby {}'.format(groupby)

    if aggregate is not None:
        args_ += ' --aggregate {}'.format(aggregate)

    table_ = table_parser.table(cli.ceilometer('statistics', args_, auth_info=auth_info, ssh_client=con_ssh))

    return table_


def get_meters_table(limit=None, unique=None, meter=None, resource=None, auth_info=Tenant.ADMIN, con_ssh=None, query=None):
    """

    Args:
        limit:
        unique:
        meter:
        auth_info:
        con_ssh:
        query(str): format: key[op]data_type::value; list.
            data_type is optional, but if supplied must be string, integer, float, or boolean.
            valid keys: ['project', 'source', 'user']
    Returns:

    """
    args_ = ''

    if limit is not None:
        args_ += ' --limit {}'.format(limit)

    if unique is not None:
        args_ += ' --unique {}'.format(unique)

    if query is not None:
        args_ += ' --query {}'.format(query)

    if meter is not None:
        args_ += ' --query meter={}'.format(meter)

    if resource is not None:
        args_ += ' --query resource={}'.format(resource)

    table_ = table_parser.table(cli.ceilometer('meter-list', args_, auth_info=auth_info, ssh_client=con_ssh))

    return table_


def alarm_list(header='State', con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Get a list of alarms that can be tracked by Ceilometer
    Args:
        header (str): the column to get the values from
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (list): a list of all the values in the header column of the returned resources

    """
    table_ = table_parser.table(cli.ceilometer('alarm-list', auth_info=auth_info, ssh_client=con_ssh))

    values = table_parser.get_values(table_, target_header=header)

    return values


def get_events(event_type, limit=None, header='message_id', con_ssh=None, auth_info=None,
               **filters):
    """

    Args:
        event_type:
        limit
        header:
        con_ssh:
        auth_info:

    Returns:

    """
    args = ''
    if limit:
        args = '--limit {}'.format(limit)
    args += ' --filter event_type={}'.format(event_type)
    for key, val in filters.items():
        args += ';{}={}'.format(key, val)

    table_ = table_parser.table(cli.openstack('event list', args, ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_values(table_, header)
