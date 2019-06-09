from pytest import skip

from consts.auth import Tenant
from utils import table_parser, cli
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG
from keywords import kube_helper


def get_alarms(header='alarm_id', name=None, strict=False, auth_info=Tenant.get('admin'), con_ssh=None):
    """

    Args:
        header
        name:
        strict:
        auth_info:
        con_ssh:

    Returns:

    """

    table_ = table_parser.table(cli.openstack('alarm list', ssh_client=con_ssh, auth_info=auth_info)[1],
                                combine_multiline_entry=True)
    if name is None:
        return table_parser.get_column(table_, header)

    return table_parser.get_values(table_, header, Name=name, strict=strict)


def delete_samples():
    """
    Calls sudo /usr/bin/ceilometer-expirer. Deletes all expired samples.
    Returns (int):
        0 if successfully called

    """
    LOG.info("Deleting expired ceilometer resources.")
    ssh_client = ControllerClient.get_active_controller()
    ssh_client.exec_sudo_cmd('/usr/bin/ceilometer-expirer', fail_ok=False, expect_timeout=90)


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

    if event_type or filters:
        if event_type:
            filters['event_type'] = event_type

        extra_args = ['{}={}'.format(k, v) for k, v in filters.items()]
        args += ' --filter {}'.format(';'.join(extra_args))

    table_ = table_parser.table(cli.openstack('event list', args, ssh_client=con_ssh, auth_info=auth_info)[1])
    return table_parser.get_values(table_, header)


def set_retention_period(period, name='event_time_to_live', fail_ok=True, check_first=True, con_ssh=None,
                         auth_info=Tenant.get('admin_platform')):
    """
    Sets the PM retention period in K8S settings
    Args:
        period (int): the length of time to set the retention period (in seconds)
        name
        fail_ok: True or False
        check_first: True or False
        con_ssh (SSHClient):
        auth_info (dict): could be Tenant.get('admin'), Tenant.get('tenant1')

    Returns (tuple): (rtn_code (int), msg (str))
        (-1, "Retention period not specified")
        (-1, "The retention period is already set to that")
        (0, "Current retention period is: <retention_period>")
        (1, "Current retention period is still: <retention_period>")

    US100247
    US99793
    system helm-override-update --reset-values panko database --set conf.panko.database.event_time_to_live=45678
    system application-apply stx-openstack

    """
    from keywords import container_helper

    if not isinstance(period, int):
        raise ValueError("Retention period has to be an integer. Value provided: {}".format(period))

    if check_first:
        retention = get_retention_period(name=name, con_ssh=con_ssh)
        if period == retention:
            msg = "The retention period is already set to {}".format(period)
            LOG.info(msg)
            return 1, msg

    app_name = 'stx-openstack'
    section = 'database'

    if name in 'metering_time_to_live':
        skip("Ceilometer metering_time_to_live is no longer available in 'system service-parameter-list'")
        name = 'metering_time_to_live'
        service = 'ceilometer'
    elif name == 'alarm_history_time_to_live':
        skip("Skip for now on containerized load")
        service = 'aodh'
    elif name == 'event_time_to_live':
        service = 'panko'
        section = 'openstack'
        name = 'conf.panko.database.event_time_to_live'
    else:
        raise ValueError("Unknown name: {}".format(name))

    code, output = container_helper.update_helm_override(chart=service, namespace=section, reset_vals=False,
                                                         kv_pairs={name: period}, auth_info=auth_info, con_ssh=con_ssh)

    assert code == 0 or fail_ok, 'Failed to update helm override unexpectedly, message:{}'.format(output)

    if code != 0:
        LOG.info('Update helm override failed as expected')
        return code, output

    override_info = container_helper.get_helm_override_values(chart=service, namespace=section, fields='user_overrides',
                                                              auth_info=auth_info, con_ssh=con_ssh)
    LOG.debug('override_info:{}'.format(override_info))

    code, output = container_helper.apply_app(app_name=app_name, check_first=False, applied_timeout=1800, fail_ok=False,
                                              con_ssh=con_ssh, auth_info=auth_info)
    assert code == 0 or fail_ok, 'Failed to apply application:{0} unexpectedly, message:{1}'.format(app_name, output)

    return code, output


def get_retention_period(name='event_time_to_live', con_ssh=None):
    LOG.info('Getting retention period')
    value = kube_helper.get_openstack_configs('panko', conf_file='/etc/panko/panko.conf',
                                              con_ssh=con_ssh, configs={'database': name})
    return value[0] if value else None
