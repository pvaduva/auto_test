import math
import re
import time

from consts.auth import Tenant, HostLinuxCreds
from consts.cgcs import UUID, Prompt, Networks
from consts.timeout import SysInvTimeout
from utils import cli, table_parser, exceptions
from utils.ssh import ControllerClient
from utils.tis_log import LOG


class System:
    def __init__(self, controller_ssh=None):
        if controller_ssh is None:
            controller_ssh = ControllerClient.get_active_controller()
        self.CON_SSH = controller_ssh
        self.IS_SMALL_SYS = is_small_footprint(controller_ssh)
        nodes = _get_nodes(controller_ssh)
        self.CONTROLLERS = nodes['controllers']
        self.COMPUTES = nodes['computes']
        self.STORAGES = nodes['storages']
        LOG.info(("Information for system {}: "
                  "\nSmall footprint: {}\nController nodes: {}\nCompute nodes: {}\nStorage nodes: {}").
                 format(controller_ssh.host, self.IS_SMALL_SYS, self.CONTROLLERS, self.COMPUTES, self.STORAGES))

    def get_system_info(self):
        system = {}
        alarms = get_alarms_table(self.CON_SSH)
        system['alarms_and_events'] = alarms
        # TODO: add networks, providernets, interfaces, flavors, images, volumes, vms info?

    # TODO: add methods to set nodes for install delete tests


def get_hostname(con_ssh=None):
    return _get_info_non_cli(r'cat /etc/hostname', con_ssh=con_ssh)


def get_buildinfo(con_ssh=None):
    return _get_info_non_cli(r'cat /etc/build.info', con_ssh=con_ssh)


def _get_info_non_cli(cmd, con_ssh=None):
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()
    exitcode, output = con_ssh.exec_cmd(cmd, rm_date=True)
    if not exitcode == 0:
        raise exceptions.SSHExecCommandFailed("Command failed to execute.")

    return output


def is_storage_system(con_ssh=None):
    return bool(get_storage_nodes(con_ssh=con_ssh))


def is_two_node_cpe(con_ssh=None):
    """
    Whether it is two node CPE system
    Args:
        con_ssh:

    Returns (bool):

    """
    return is_small_footprint(controller_ssh=con_ssh) and len(get_controllers(con_ssh=con_ssh)) == 2


def is_simplex(con_ssh=None):
    return is_small_footprint(controller_ssh=con_ssh) and len(get_controllers(con_ssh=con_ssh)) == 1


def is_small_footprint(controller_ssh=None, controller='controller-0'):
    """
    Whether it is two node CPE system or Simplex system where controller has both controller and compute functions
    Args:
        controller_ssh (SSHClient):
        controller (str): controller to check

    Returns (bool): True if CPE or Simplex, else False

    """
    table_ = table_parser.table(cli.system('host-show', controller, ssh_client=controller_ssh))
    subfunc = table_parser.get_value_two_col_table(table_, 'subfunctions')

    combined = 'controller' in subfunc and 'compute' in subfunc

    str_ = 'not' if not combined else ''

    LOG.info("This is {} small footprint system.".format(str_))
    return combined


def get_storage_nodes(con_ssh=None):
    """
    Get hostnames with 'storage' personality from system host-list
    Args:
        con_ssh (SSHClient):

    Returns (list): list of hostnames. Empty list [] returns when no storage nodes.

    """
    return get_hostnames(personality='storage', con_ssh=con_ssh)


def get_controllers(con_ssh=None):
    """
    Get hostnames with 'controller' personality from system host-list
    Args:
        con_ssh (SSHClient):

    Returns (list): list of hostnames

    """
    return get_hostnames(personality='controller', con_ssh=con_ssh)


def get_computes(con_ssh=None):
    """
    Get hostnames with 'compute' personality from system host-list
    Args:
        con_ssh (SSHClient):

    Returns (list): list of hostnames. Empty list [] returns when no compute nodes.

    """
    nodes = _get_nodes(con_ssh)
    return nodes['computes']


def get_hostnames(personality=None, administrative=None, operational=None, availability=None, name=None,
                  strict=True, exclude=False, con_ssh=None):
    """
    Get hostnames with given criteria
    Args:
        personality (str):
        administrative (str|list):
        operational (str|list):
        availability (str|list):
        name (str):
        strict (bool):
        exclude (bool):
        con_ssh (dict):

    Returns (list): hostnames

    """
    table_ = table_parser.table(cli.system('host-list', ssh_client=con_ssh))
    filters = {'hostname': name,
               'personality': personality,
               'administrative': administrative,
               'operational': operational,
               'availability': availability}
    hostnames = table_parser.get_values(table_, 'hostname', strict=strict, exclude=exclude, **filters)
    LOG.info("Filtered hostnames: {}".format(hostnames))

    return hostnames


def _get_nodes(con_ssh=None):
    """

    Args:
        con_ssh:

    Returns: (dict)
        {'controllers':
                {'controller-0': {'id' = id_, 'uuid' = uuid, 'mgmt_ip' = ip, 'mgmt_mac' = mac},
                 'controller-1': {...}
                 },
         'computes':
                {'compute-0': {...},
                 'compute-1': {...}
                 }.
         'storages':
                {'storage-0': {...},
                 'storage-1': {...}
                }
        }

    """
    table_ = table_parser.table(cli.system('host-list', ssh_client=con_ssh))
    nodes = {}

    for personality in ['controller', 'compute', 'storage']:
        nodes[personality+'s'] = {}
        hostnames = table_parser.get_values(table_, 'hostname', personality=personality)
        for hostname in hostnames:
            host_table = table_parser.table(cli.system('host-show', hostname))
            uuid = table_parser.get_values(host_table, 'Value', Property='uuid')[0]
            id_ = table_parser.get_values(host_table, 'Value', Property='id')[0]
            mgmt_ip = table_parser.get_values(host_table, 'Value', Property='mgmt_ip')[0]
            mgmt_mac = table_parser.get_values(host_table, 'Value', Property='mgmt_mac')[0]
            nodes[personality+'s'][hostname] = {'id': id_,
                                                'uuid': uuid,
                                                'mgmt_ip': mgmt_ip,
                                                'mgmt_mac': mgmt_mac}

    return nodes


def get_active_controller_name(con_ssh=None, source_auth_info=False):
    """
    This assumes system has 1 active controller
    Args:
        con_ssh:
        source_auth_info

    Returns: hostname of the active controller
        Further info such as ip, uuid can be obtained via System.CONTROLLERS[hostname]['uuid']
    """
    return _get_active_standby(controller='active', con_ssh=con_ssh, source_auth_info=source_auth_info)[0]


def get_standby_controller_name(con_ssh=None):
    """
    This assumes system has 1 standby controller
    Args:
        con_ssh:

    Returns (str): hostname of the active controller
        Further info such as ip, uuid can be obtained via System.CONTROLLERS[hostname]['uuid']
    """
    standby = _get_active_standby(controller='standby', con_ssh=con_ssh)
    return '' if len(standby) == 0 else standby[0]


def _get_active_standby(controller='active', con_ssh=None, source_auth_info=False):
    table_ = table_parser.table(cli.system('servicegroup-list', ssh_client=con_ssh))
    table_ = table_parser.filter_table(table_, service_group_name='controller-services')
    controllers = table_parser.get_values(table_, 'hostname', state=controller, strict=False)
    LOG.debug(" {} controller(s): {}".format(controller, controllers))
    if isinstance(controllers, str):
        controllers = [controllers]

    return controllers


def get_active_standby_controllers(con_ssh=None):
    """
    Get active controller name and standby controller name (if any)
    Args:
        con_ssh (SSHClient):

    Returns (tuple): such as ('controller-0', 'controller-1'), when non-active controller is in bad state or degraded
        state, or any scenarios where standby controller does not exist, this function will return
        (<active_con_name>, None)

    """
    table_ = table_parser.table(cli.system('servicegroup-list', ssh_client=con_ssh))

    table_ = table_parser.filter_table(table_, service_group_name='controller-services')
    active_con = table_parser.get_values(table_, 'hostname', state='active', strict=False)[0]
    standby_con = table_parser.get_values(table_, 'hostname', state='standby', strict=False)

    standby_con = standby_con[0] if standby_con else None
    return active_con, standby_con


def get_alarms_table(uuid=True, show_suppress=False, query_key=None, query_value=None, query_type=None, con_ssh=None,
                     auth_info=Tenant.ADMIN):
    """
    Get active alarms_and_events dictionary with given criteria
    Args:
        uuid (bool): whether to show uuid
        show_suppress (bool): whether to show suppressed alarms_and_events
        query_key (str): one of these: 'event_log_id', 'entity_instance_id', 'uuid', 'severity',
        query_value (str): expected value for given key
        query_type (str): data type of value. one of these: 'string', 'integer', 'float', 'boolean'
        con_ssh (SSHClient):
        auth_info (dict):

    Returns:
        dict: events table in format: {'headers': <headers list>, 'values': <list of table rows>}
    """
    args = '--nowrap'
    args = __process_query_args(args, query_key, query_value, query_type)
    if uuid:
        args += ' --uuid'
    if show_suppress:
        args += ' --include_suppress'

    table_ = table_parser.table(cli.system('alarm-list', args, ssh_client=con_ssh, auth_info=auth_info),
                                combine_multiline_entry=True)

    table_ = _compose_alarm_table(table_, uuid=uuid)

    return table_


def _compose_alarm_table(output, uuid=False):
    if not output['headers']:
        headers = ['UUID', 'Alarm ID', 'Reason Text', 'Entity ID', 'Severity', 'Time Stamp']
        if not uuid:
            headers.remove('UUID')
        values = []
        output['headers'] = headers
        output['values'] = values

    return output


def get_alarms(rtn_vals=('Alarm ID', 'Entity ID'), alarm_id=None, reason_text=None, entity_id=None,
               severity=None, time_stamp=None, strict=False, show_suppress=False, query_key=None, query_value=None,
               query_type=None, con_ssh=None, auth_info=Tenant.ADMIN, combine_entries=True):
    """
    Get a list of alarms with values for specified fields.
    Args:
        rtn_vals (tuple): fields to get values for
        alarm_id (str): filter out the table using given alarm id (strict=True). if None, table will not be filtered.
        reason_text (str): reason text to filter out the table (strict defined in param)
        entity_id (str): entity instance id to filter out the table (strict defined in param)
        severity (str): severity such as 'critical', 'major'
        time_stamp (str):
        strict (bool): whether to perform strict filter on reason text, entity_id, severity, or time_stamp
        show_suppress (bool): whether to show suppressed alarms. Default to False.
        query_key (str): key in --query <key>=<value> passed to system alarm-list
        query_value (str): value in --query <key>=<value> passed to system alarm-list
        query_type (str): 'string', 'integer', 'float', or 'boolean'
        con_ssh (SSHClient):
        auth_info (dict):
        combine_entries (bool): return list of strings when set to True, else return a list of tuples.
            e.g., when True, returns ["800.003 cluster=829851fa", "250.001 host=controller-0"]
                  when False, returns [("800.003", "cluster=829851fa"), ("250.001", "host=controller-0")]

    Returns (list): list of alarms with values of specified fields

    """

    table_ = get_alarms_table(show_suppress=show_suppress, query_key=query_key, query_value=query_value,
                              query_type=query_type, con_ssh=con_ssh, auth_info=auth_info)

    if alarm_id:
        table_ = table_parser.filter_table(table_, **{'Alarm ID': alarm_id})

    kwargs_dict = {
        'Reason Text': reason_text,
        'Entity ID': entity_id,
        'Severity': severity,
        'Time Stamp': time_stamp
    }

    kwargs = {}
    for key, value in kwargs_dict.items():
        if value is not None:
            kwargs[key] = value

    if kwargs:
        table_ = table_parser.filter_table(table_, strict=strict, **kwargs)

    rtn_vals_list = []
    for val in rtn_vals:
        vals = table_parser.get_column(table_, val)
        rtn_vals_list.append(vals)

    rtn_vals_list = zip(*rtn_vals_list)
    if combine_entries:
        rtn_vals_list = ['::::'.join(vals) for vals in rtn_vals_list]

    return rtn_vals_list


def get_suppressed_alarms(uuid=False, con_ssh=None, auth_info=Tenant.ADMIN):

    """
    Get suppressed alarms_and_events as dictionary
    Args:
        uuid (bool): whether to show uuid
        con_ssh (SSHClient):
        auth_info (dict):

    Returns:
        dict: events table in format: {'headers': <headers list>, 'values': <list of table rows>}
    """
    args = ''
    if uuid:
        args += ' --uuid'
    args += ' --nowrap --nopaging'
    table_ = table_parser.table(cli.system('event-suppress-list', args, ssh_client=con_ssh, auth_info=auth_info))
    return table_


def unsuppress_all_events(ssh_con=None, fail_ok=False, auth_info=Tenant.ADMIN):
    """

    Args:
        ssh_con:
        fail_ok:
        auth_info:

    Returns (tuple): (<code>(int), <msg>(str))

    """
    LOG.info("Un-suppress all events")
    args = '--nowrap --nopaging'
    code, output = cli.system('event-unsuppress-all',  positional_args=args, ssh_client=ssh_con, fail_ok=fail_ok,
                              auth_info=auth_info, rtn_list=True)

    if code == 1:
        return 1, output

    if not output:
        msg = "No suppressed events to un-suppress"
        LOG.warning(msg)
        return -1, msg

    table_ = table_parser.table(output)
    if not table_['values']:
        suppressed_list = []
    else:
        suppressed_list = table_parser.get_values(table_, target_header="Suppressed Alarm ID's", **{'Status': 'suppressed'})

    if suppressed_list:
        msg = "Unsuppress-all failed. Suppressed Alarm IDs: {}".format(suppressed_list)
        if fail_ok:
            LOG.warning(msg)
            return 2, msg
        raise exceptions.NeutronError(msg)

    succ_msg = "All events unsuppressed successfully."
    LOG.info(succ_msg)
    return 0, succ_msg


def get_events_table(num=5, uuid=False, show_only=None, show_suppress=False, event_log_id=None, entity_type_id=None,
                     entity_instance_id=None, severity=None, start=None, end=None, query_key=None,
                     query_value=None, query_type=None, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Get a list of events with given criteria as dictionary
    Args:
        num (int): max number of event logs to return
        uuid (bool): whether to show uuid
        show_only (str): 'alarms_and_events' or 'logs' to return only alarms_and_events or logs
        show_suppress (bool): whether or not to show suppressed alarms_and_events
        query_key (str): OBSOLETE. one of these: 'event_log_id', 'entity_instance_id', 'uuid', 'severity',
        query_value (str): OBSOLETE. expected value for given key
        query_type (str): OBSOLETE. data type of value. one of these: 'string', 'integer', 'float', 'boolean'
        event_log_id (str|None): event log id passed to system eventlog -q event_log_id=<event_log_id>
        entity_type_id (str|None): entity_type_id passed to system eventlog -q entity_type_id=<entity_type_id>
        entity_instance_id (str|None): entity_instance_id passed to system eventlog -q entity_instance_id=<entity_instance_id>
        severity (str|None):
        start (str|None): start date/time passed to '--query' in format "20170410"/"20170410 01:23:34"
        end (str|None): end date/time passed to '--query' in format "20170410"/"20170410 01:23:34"
        con_ssh (SSHClient):
        auth_info (dict):

    Returns:
        dict: events table in format: {'headers': <headers list>, 'values': <list of table rows>}
    """
    args = '-l {}'.format(num)
    if query_key is not None:
        if query_key in ['event_log_id', 'entity_type_id', 'entity_instance_id', 'severity', 'start', 'end']:
            if eval(query_key) is not None:
                LOG.warning("query_key/value params ignored since {} is already specified".format(query_key))
                query_key = query_value = query_type = None

    # args = __process_query_args(args, query_key, query_value, query_type)
    query_dict = {
        'event_log_id': event_log_id,
        'entity_type_id': entity_type_id,
        'entity_instance_id': entity_instance_id,
        'severity': severity,
        'start': '"{}"'.format(start) if start else None,
        'end': '"{}"'.format(end) if end else None
    }

    queries = []
    for q_key, q_val in query_dict.items():
        if q_val is not None:
            queries.append('{}={}'.format(q_key, str(q_val)))

    if query_key is not None:
        if not query_value:
            raise ValueError("Query value is not supplied for key - {}".format(query_key))
        data_type_arg = '' if not query_type else "{}::".format(query_type.lower())
        queries.append('{}={}{}'.format(query_key.lower(), data_type_arg, query_value))

    query_string = ';'.join(queries)
    if query_string:
        args += " -q '{}'".format(query_string)

    args += ' --nowrap --nopaging'
    if uuid:
        args += ' --uuid'
    if show_only:
        args += ' --{}'.format(show_only.lower())
    if show_suppress:
        args += ' --include_suppress'

    table_ = table_parser.table(cli.system('event-list ', args, ssh_client=con_ssh, auth_info=auth_info))
    # table_ = _compose_events_table(table_, uuid=uuid)
    return table_


def _compose_events_table(output, uuid=False):
    if not output['headers']:
        headers = ['UUID', 'Time Stamp', 'State', 'Event Log ID', 'Reason Text', 'Entity Instance ID', 'Severity']
        if not uuid:
            headers.remove('UUID')
        values = []
        output['headers'] = headers
        output['values'] = values

    return output


def __process_query_args(args, query_key, query_value, query_type):
    if query_key:
        if not query_value:
            raise ValueError("Query value is not supplied for key - {}".format(query_key))
        data_type_arg = '' if not query_type else "{}::".format(query_type.lower())
        args += ' -q {}={}"{}"'.format(query_key.lower(), data_type_arg, query_value.lower())
    return args


def wait_for_events(timeout=60, num=30, uuid=False, show_only=None, query_key=None, query_value=None, query_type=None,
                    fail_ok=True, rtn_val='Event Log ID', con_ssh=None, auth_info=Tenant.ADMIN, regex=False,
                    strict=True, check_interval=3, event_log_id=None, entity_type_id=None, entity_instance_id=None,
                    severity=None, start=None, end=None, **kwargs):
    """
    Wait for event(s) to appear in system event-list
    Args:
        timeout (int): max time to wait in seconds
        num (int): max number of event logs to return
        uuid (bool): whether to show uuid
        show_only (str): 'alarms_and_events' or 'logs' to return only alarms_and_events or logs
        query_key (str): one of these: 'event_log_id', 'entity_instance_id', 'uuid', 'severity',
        query_value (str): expected value for given key
        query_type (str): data type of value. one of these: 'string', 'integer', 'float', 'boolean'
        fail_ok (bool): whether to return False if event(s) did not appear within timeout
        rtn_val (str): list of values to return. Defaults to 'Event Log ID'
        con_ssh (SSHClient):
        auth_info (dict):
        regex (bool): Whether to use regex or string operation to search/match the value in kwargs
        strict (bool): whether it's a strict match (case is always ignored regardless of this flag)
        check_interval (int): how often to check the event logs
        event_log_id (str|None): event log id passed to system eventlog -q event_log_id=<event_log_id>
        entity_type_id (str|None): entity_type_id passed to system eventlog -q entity_type_id=<entity_type_id>
        entity_instance_id (str|None): entity_instance_id passed to system eventlog -q entity_instance_id=<entity_instance_id>
        severity (str|None):
        start (str|None): start date/time passed to '--query' in format "20170410"/"20170410 01:23:34"
        end (str|None): end date/time passed to '--query' in format "20170410"/"20170410 01:23:34"

        **kwargs: criteria to filter out event(s) from the events list table

    Returns:
        list: list of event log ids (or whatever specified in rtn_value) for matching events.

    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        events_tab = get_events_table(num=num, uuid=uuid, show_only=show_only, event_log_id=event_log_id,
                                      entity_type_id=entity_type_id, entity_instance_id=entity_instance_id,
                                      severity=severity, start=start, end=end, query_key=query_key,
                                      query_value=query_value, query_type=query_type,
                                      con_ssh=con_ssh, auth_info=auth_info)
        events_tab = table_parser.filter_table(events_tab, strict=strict, regex=regex, **kwargs)
        events = table_parser.get_column(events_tab, rtn_val)
        if events:
            LOG.info("Event(s) appeared in event-list: {}".format(events))
            return events

        time.sleep(check_interval)

    msg = "Event(s) did not appear in system event-list within timeout."
    if fail_ok:
        LOG.warning(msg)
        return []
    else:
        raise exceptions.TimeoutException(msg)


def delete_alarms(alarms=None, fail_ok=False, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Delete active alarms_and_events

    Args:
        alarms (list|str): UUID(s) of alarms_and_events to delete
        fail_ok (bool): whether or not to raise exception if any alarm failed to delete
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (tuple): (rtn_code(int), message(str))
        0, "Alarms deleted successfully"
        1, "Some alarm(s) still exist on system after attempt to delete: <alarms_uuids>"

    """
    if alarms is None:
        alarms_tab = get_alarms_table(uuid=True)
        alarms = []
        if alarms_tab['headers']:
            alarms = table_parser.get_column(alarms_tab, 'UUID')

    if isinstance(alarms, str):
        alarms = [alarms]

    LOG.info("Deleting following alarms_and_events: {}".format(alarms))

    res = {}
    failed_clis = []
    for alarm in alarms:
        code, out = cli.system('alarm-delete', alarm, ssh_client=con_ssh, auth_info=auth_info, rtn_list=True)
        res[alarm] = code, out

        if code != 0:
            failed_clis.append(alarm)

    post_alarms_tab = get_alarms_table(uuid=True)
    if post_alarms_tab['headers']:
        post_alarms = table_parser.get_column(post_alarms_tab, 'UUID')
    else:
        post_alarms = []

    undeleted_alarms = list(set(alarms) & set(post_alarms))
    if undeleted_alarms:
        err_msg = "Some alarm(s) still exist on system after attempt to delete: {}\nAlarm delete results: {}".\
            format(undeleted_alarms, res)

        if fail_ok:
            return 1, err_msg
        raise exceptions.SysinvError(err_msg)

    elif failed_clis:
        LOG.warning("Some alarm-delete cli(s) rejected, but alarm no longer exists.\nAlarm delete results: {}".
                    format(res))

    succ_msg = "Alarms deleted successfully"
    LOG.info(succ_msg)
    return 0, succ_msg


def wait_for_alarm_gone(alarm_id, entity_id=None, reason_text=None, strict=False, timeout=120, check_interval=3,
                        fail_ok=False, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Wait for given alarm to disappear from system alarm-list
    Args:
        alarm_id (str): such as 200.009
        entity_id (str): entity instance id for the alarm (strict as defined in param)
        reason_text (str): reason text for the alarm (strict as defined in param)
        strict (bool): whether to perform strict string match on entity instance id and reason
        timeout (int): max seconds to wait for alarm to disappear
        check_interval (int): how frequent to check
        fail_ok (bool): whether to raise exception if alarm did not disappear within timeout
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (bool): True if alarm is gone else False

    """

    LOG.info("Waiting for alarm {} to disappear from system alarm-list".format(alarm_id))
    build_ver = get_system_software_version(con_ssh=con_ssh)

    alarmcmd = 'alarm-list'
    if build_ver != '15.12':
        alarmcmd += ' --nowrap'

    end_time = time.time() + timeout
    while time.time() < end_time:
        #alarms_tab = table_parser.table(cli.system('alarm-list --nowrap', ssh_client=con_ssh, auth_info=auth_info))
        alarms_tab = table_parser.table(cli.system(alarmcmd, ssh_client=con_ssh, auth_info=auth_info))
        alarms_tab = _compose_alarm_table(alarms_tab, uuid=False)

        alarm_tab = table_parser.filter_table(alarms_tab, **{'Alarm ID': alarm_id})
        if table_parser.get_all_rows(alarm_tab):
            kwargs = {}
            if entity_id:
                kwargs['Entity ID'] = entity_id
            if reason_text:
                kwargs['Reason Text'] = reason_text

            if kwargs:
                alarms = table_parser.get_values(alarm_tab, target_header='Alarm ID', strict=strict, **kwargs)
                if not alarms:
                    LOG.info("Alarm {} with {} is not displayed in system alarm-list".format(alarm_id, kwargs))
                    return True

        else:
            LOG.info("Alarm {} is not displayed in system alarm-list".format(alarm_id))
            return True

        time.sleep(check_interval)

    else:
        err_msg = "Timed out waiting for alarm {} to disappear".format(alarm_id)
        if fail_ok:
            LOG.warning(err_msg)
            return False
        else:
            raise exceptions.TimeoutException(err_msg)


def _get_alarms(alarms_tab):
    alarm_ids = table_parser.get_column(alarms_tab, 'Alarm_ID')
    entity_ids = table_parser.get_column(alarms_tab, 'Entity ID')
    alarms = list(zip(alarm_ids, entity_ids))
    return alarms


def wait_for_alarm(rtn_val='Alarm ID', alarm_id=None, entity_id=None, reason=None, severity=None, timeout=60,
                   check_interval=3, regex=False, strict=False, fail_ok=False, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Wait for given alarm to appear
    Args:
        rtn_val:
        alarm_id (str): such as 200.009
        entity_id (str): entity instance id for the alarm (strict as defined in param)
        reason (str): reason text for the alarm (strict as defined in param)
        severity (str): severity of the alarm to wait for
        timeout (int): max seconds to wait for alarm to appear
        check_interval (int): how frequent to check
        regex (bool): whether to use regex when matching entity instance id and reason
        strict (bool): whether to perform strict match on entity instance id and reason
        fail_ok (bool): whether to raise exception if alarm did not disappear within timeout
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (tuple): (<res_bool>, <rtn_val>). Such as (True, '200.009') or (False, None)

    """

    kwargs = {}
    if alarm_id:
        kwargs['Alarm ID'] = alarm_id
    if entity_id:
        kwargs['Entity ID'] = entity_id
    if reason:
        kwargs['Reason Text'] = reason
    if severity:
        kwargs['Severity'] = severity

    end_time = time.time() + timeout
    while time.time() < end_time:
        current_alarms_tab = get_alarms_table(con_ssh=con_ssh, auth_info=auth_info)
        val = table_parser.get_values(current_alarms_tab, rtn_val, strict=strict, regex=regex, **kwargs)
        if val:
            LOG.info('Expected alarm appeared. Filters: {}'.format(kwargs))
            return True, val

        time.sleep(check_interval)

    err_msg = "Alarm {} did not appear in system alarm-list within {} seconds".format(kwargs, timeout)
    if fail_ok:
        LOG.warning(err_msg)
        return False, None

    raise exceptions.TimeoutException(err_msg)


def wait_for_alarms_gone(alarms, timeout=120, check_interval=3, fail_ok=False, con_ssh=None,
                         auth_info=Tenant.ADMIN):
    """
    Wait for given alarms_and_events to be gone from system alarm-list
    Args:
        alarms (list): list of tuple. [(<alarm_id1>, <entity_id1>), ...]
        timeout (int):
        check_interval (int):
        fail_ok (bool):
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (tuple): (res(bool), remaining_alarms(tuple))

    """
    pre_alarms = list(alarms)   # Don't update the original list
    LOG.info("Waiting for alarms_and_events to disappear from system alarm-list: {}".format(pre_alarms))
    alarms_to_check = pre_alarms.copy()

    alarms_cleared = []
    end_time = time.time() + timeout
    while time.time() < end_time:
        current_alarms_tab = get_alarms_table(con_ssh=con_ssh, auth_info=auth_info)
        current_alarms = _get_alarms(current_alarms_tab)

        for alarm in pre_alarms:
            if alarm not in current_alarms:
                LOG.info("Removing alarm {} from current alarms_and_events list: {}".format(alarm, alarms_to_check))
                alarms_to_check.remove(alarm)
                alarms_cleared.append(alarm)

        if not alarms_to_check:
            LOG.info("Following alarms_and_events cleared: {}".format(alarms_cleared))
            return True, []

        pre_alarms = alarms_to_check.copy()
        time.sleep(check_interval)

    else:
        err_msg = "Following alarms_and_events did not clear within {} seconds: {}".format(timeout, alarms_to_check)
        if fail_ok:
            LOG.warning(err_msg)
            return False, alarms_to_check
        else:
            raise exceptions.TimeoutException(err_msg)

def wait_for_all_alarms_gone(timeout=120, check_interval=3, fail_ok=False, con_ssh=None,
                         auth_info=Tenant.ADMIN):
    """
    Wait for all alarms_and_events to be cleared from system alarm-list
    Args:
        timeout (int):
        check_interval (int):
        fail_ok (bool):
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (tuple): (res(bool), remaining_alarms(tuple))

    """

    LOG.info("Waiting for all existing alarms_and_events to disappear from system alarm-list: {}".format(get_alarms()))

    end_time = time.time() + timeout
    while time.time() < end_time:
        current_alarms_tab = get_alarms_table(con_ssh=con_ssh, auth_info=auth_info)
        current_alarms = _get_alarms(current_alarms_tab)

        if len(current_alarms) == 0:
            return True, []
        else:
            time.sleep(check_interval)

    else:
        existing_alarms = get_alarms()
        err_msg = "Alarms did not clear within {} seconds: {}".format(timeout, existing_alarms)
        if fail_ok:
            LOG.warning(err_msg)
            return False, existing_alarms
        else:
            raise exceptions.TimeoutException(err_msg)


def host_exists(host, field='hostname', con_ssh=None):
    """

    Args:
        host:
        field:
        con_ssh:

    Returns (bool): whether given host exists in system host-list

    """
    if not field.lower() in ['hostname', 'id']:
        raise ValueError("field has to be either \'hostname\' or \'id\'")

    table_ = table_parser.table(cli.system('host-list', ssh_client=con_ssh))

    hosts = table_parser.get_column(table_, field)
    return host in hosts


def get_storage_monitors_count():
    # Only 2 storage monitor available. At least 2 unlocked and enabled hosts with monitors are required.
    # Please ensure hosts with monitors are unlocked and enabled - candidates: controller-0, controller-1,
    raise NotImplementedError


def set_system_info(fail_ok=True, con_ssh=None, auth_info=Tenant.ADMIN, **kwargs):
    """
    Modify the System Information.

    Args:
        fail_ok (bool):
        con_ssh (SSHClient):
        auth_info (dict):
        **kwargs:   attribute-value pairs

    Returns: (int, str)
         0  - success
         1  - error

    Test Steps:
        - Set the value via system modify <attr>=<value> [,<attr>=<value]

    Notes:
        Currently only the following are allowed to change:
        name
        description
        location
        contact

        The following attributes are readonly and not allowed CLI user to change:
            system_type
            software_version
            uuid
            created_at
            updated_at
    """
    if not kwargs:
        raise ValueError("Please specify at least one systeminfo_attr=value pair via kwargs.")

    attr_values_ = ['{}="{}"'.format(attr, value) for attr, value in kwargs.items()]
    args_ = ' '.join(attr_values_)

    code, output = cli.system('modify', args_, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok, rtn_list=True)

    if code == 1:
        return 1, output
    elif code == 0:
        return 0, ''
    else:
        # should not get here; cli.system() should already handle these cases
        pass


def get_system_name(fail_ok=True, con_ssh=None):

    table_ = table_parser.table(cli.system('show'))
    system_name = table_parser.get_value_two_col_table(table_, 'name')
    return system_name


def set_retention_period(fail_ok=True, check_first=True, con_ssh=None, auth_info=Tenant.ADMIN, period=None):
    """
    Sets the PM retention period
    Args:
        period (int): the length of time to set the retention period (in seconds)
        fail_ok: True or False
        check_first: True or False
        con_ssh (str):
        auth_info (dict): could be Tenant.ADMIN,Tenant.TENANT1,Tenant.TENANT2

    Returns (tuple): (rtn_code (int), msg (str))
        (-1, "Retention period not specified")
        (-1, "The retention period is already set to that")
        (0, "Current retention period is: <retention_period>")
        (1, "Current retention period is still: <retention_period>")

    US100247
    US99793
    """

    if not isinstance(period, int):
        raise ValueError("Retention period has to be an integer. Value provided: {}".format(period))
    if check_first:
        retention = get_retention_period()
        if period == retention:
            msg = "The retention period is already set to {}".format(period)
            LOG.info(msg)
            return -1, msg

    code, output = cli.system('pm-modify', 'retention_secs={}'.format(period), auth_info=auth_info,
                              ssh_client=con_ssh, timeout=SysInvTimeout.RETENTION_PERIOD_MODIFY, fail_ok=fail_ok,
                              rtn_list=True)

    if code == 1:
        return 1, output

    new_retention = get_retention_period()

    if period != new_retention:
        err_msg = "Current retention period is still: {}".format(new_retention)
        if fail_ok:
            LOG.warning(err_msg)
            return 2, err_msg
        raise exceptions.CeilometerError(err_msg)

    return 0, "Retention period is successfully set to: {}".format(new_retention)


def get_retention_period(con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Returns the current retention period
    Args:
        con_ssh (SSHClient):
        auth_info (dict)

    Returns (int): Current PM retention period

    """
    table_ = table_parser.table(cli.system('pm-show', ssh_client=con_ssh, auth_info=auth_info))
    ret_per = table_parser.get_value_two_col_table(table_, 'retention_secs')
    return int(ret_per)


def get_dns_servers(con_ssh=None):
    """
    Get the DNS servers currently in-use in the System

    Args:
        con_ssh

    Returns (tuple): a list of DNS servers will be returned

    """
    table_ = table_parser.table(cli.system('dns-show', ssh_client=con_ssh))
    return table_parser.get_value_two_col_table(table_, 'nameservers').strip().split(sep=',')


def set_dns_servers(fail_ok=True, con_ssh=None, auth_info=Tenant.ADMIN, nameservers=None, with_action_option=None):
    """
    Set the DNS servers


    Args:
        fail_ok:
        con_ssh:
        auth_info:
        nameservers (list): list of IP addresses (in plain text) of new DNS servers to change to
        with_action_option: whether invoke the CLI with or without "action" option
                            - None      no "action" option at all
                            - apply     system dns-modify <> action=apply
                            - install   system dns-modify <> action=install
                            - anystr    system dns-modify <> action=anystring...
    Returns:

    Skip Conditions:

    Prerequisites:

    Test Setups:
        - Do nothing and delegate to the class fixture to save the currently in-use DNS servers for restoration
            after testing

    Test Steps:
        - Set the DNS severs
        - Check if the DNS servers are changed correctly
        - Verify the DNS servers are working (assuming valid DNS are input for testing purpose)
        - Check if new DNS are saved to the persistent storage

    Test Teardown:
        - Do nothing and delegate to the class fixture for restoring the original DNS servers after testing

    """
    if not nameservers or len(nameservers) < 1:
        raise ValueError("Please specify DNS server(s).")

    args_ = 'nameservers="{}"'.format(','.join(nameservers))

    # args_ += ' action={}'.format(with_action_option) if with_action_option is not None else ''
    if with_action_option is not None:
        args_ += ' action={}'.format(with_action_option)

    LOG.info('args_:{}'.format(args_))
    code, output = cli.system('dns-modify', args_, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                              rtn_list=True, timeout=SysInvTimeout.DNS_MODIFY)

    if code == 1:
        return 1, output
    elif code == 0:
        return 0, ''
    else:
        # should not get here: cli.system() should already have been handled these cases
        pass


def get_vm_topology_tables(*table_names, con_ssh=None, combine_multiline=False, exclude_one_col_table=True):
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    show_args = ','.join(table_names)

    tables_ = table_parser.tables(con_ssh.exec_cmd('vm-topology -s {}'.format(show_args), expect_timeout=30)[1],
                                  combine_multiline_entry=combine_multiline)

    if exclude_one_col_table:
        new_tables = []
        for table_ in tables_:
            if len(table_['headers']) > 1:
                new_tables.append(table_)
        return new_tables

    return tables_


def set_host_1g_pages(host, proc_id=0, hugepage_num=None, fail_ok=False, auth_info=Tenant.ADMIN, con_ssh=None):
    """
    Modify host memory to given number of 1G hugepages on specified processor.

    Args:
        host (str): hostname
        proc_id (int): such as 0, 1
        hugepage_num (int): such as 0, 4. When None is set, the MAX hugepage number will be calculated and used.
        fail_ok (bool): whether to raise exception when fails to modify
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (tuple):

    """
    LOG.info("Setting 1G memory to: {}".format(hugepage_num))
    mem_vals = get_host_mem_values(
            host, ['vm_total_4K', 'vm_hp_total_2M', 'vm_hp_total_1G', 'vm_hp_avail_2M', 'mem_avail(MiB)', ],
            proc_id=proc_id, con_ssh=con_ssh, auth_info=auth_info)

    pre_4k_total, pre_2m_total, pre_1g_total, pre_2m_avail, pre_mem_avail = [int(val) for val in mem_vals]

    # set max hugepage num if hugepage_num is unset
    if hugepage_num is None:
        hugepage_num = int(pre_mem_avail/1024)

    diff = hugepage_num - pre_1g_total

    expt_2m = None
    # expt_4k = None
    if diff > 0:
        expt_2m = min(diff * 512, pre_2m_avail)

    args_dict = {
        # '-m': expt_4k,
        '-2M': expt_2m,
        '-1G': hugepage_num,
    }
    args_str = ''
    for key, value in args_dict.items():
        if value is not None:
            args_str = ' '.join([args_str, key, str(value)])

    code, output = cli.system('host-memory-modify {}'.format(args_str), "{} {}".format(host, proc_id),
                              ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok, rtn_list=True)

    if code == 1:
        return 1, output
    else:
        LOG.info("system host-memory-modify ran successfully.")
        return 0, "1G memory is modified to {} in pending.".format(hugepage_num)


def __suppress_unsuppress_event(alarm_id, suppress=True, check_first=False, fail_ok=False, con_ssh=None):
    """
    suppress/unsuppress an event by uuid
    Args:
        alarm_id (str):
        fail_ok (bool):
        con_ssh (SSHClient)
        suppress(bool) True or false

    Returns (tuple): (rtn_code, message)
        (0, )
    """

    suppressed_alarms_tab = get_suppressed_alarms(uuid=True, con_ssh=con_ssh)

    alarm_status = "unsuppressed" if suppress else "suppressed"
    cmd = "event-suppress" if suppress else "event-unsuppress"
    alarm_filter = {"Suppressed Event ID's": alarm_id}

    if check_first:
        if not suppressed_alarms_tab['values']:
            pre_status = "unsuppressed"
        else:
            pre_status = table_parser.get_values(table_=suppressed_alarms_tab, target_header='Status', strict=True,
                                                 **alarm_filter)[0]
        if pre_status.lower() != alarm_status:
            msg = "Event is already {}. Do nothing".format(pre_status)
            LOG.info(msg)
            return -1, msg

    code, output = cli.system(cmd, '--alarm_id ' + alarm_id, ssh_client=con_ssh, rtn_list=True, fail_ok=fail_ok)

    if code == 1:
        return 1, output

    post_suppressed_alarms_tab = get_suppressed_alarms(uuid=True, con_ssh=con_ssh)
    if not post_suppressed_alarms_tab['values']:
        post_status = ["unsuppressed"]
    else:
        post_status = table_parser.get_values(table_=post_suppressed_alarms_tab, target_header="Status", strict=True,
                                              **{"Event id": alarm_id})
    expt_status = "suppressed" if suppress else "unsuppressed"
    if post_status[0].lower() != expt_status:
        msg = "Alarm {} is not {}".format(alarm_id, expt_status)
        if fail_ok:
            LOG.warning(msg)
            return 2, msg
        raise exceptions.TiSError(msg)

    succ_msg = "Event {} is {} successfully".format(alarm_id, expt_status)
    LOG.info(succ_msg)
    return 0, succ_msg


def suppress_event(alarm_id, check_first=False, fail_ok=False, con_ssh=None):
    return __suppress_unsuppress_event(alarm_id, True, check_first=check_first, fail_ok=fail_ok, con_ssh=con_ssh)


def unsuppress_event(alarm_id, check_first=False, fail_ok=False, con_ssh=None):
    return __suppress_unsuppress_event(alarm_id, False, check_first=check_first, fail_ok=fail_ok, con_ssh=con_ssh)


def generate_event(event_id='300.005', state='set', severity='critical', reason_text='Generated for testing',
                   entity_id='CGCSAuto', unknown_text='unknown1', unknown_two='unknown2', con_ssh=None):

    cmd = '''fmClientCli -c  "### ###{}###{}###{}###{}### ###{}### ###{}###{}### ###True###True###"'''.\
        format(event_id, state, reason_text, entity_id, severity, unknown_text, unknown_two)

    LOG.info("Generate system event: {}".format(cmd))
    if not con_ssh:
        con_ssh = ControllerClient.get_active_controller()

    output = con_ssh.exec_cmd(cmd, fail_ok=False)[1]
    event_uuid = re.findall(UUID, output)[0]
    LOG.info("Event {} generated successfully".format(event_uuid))

    return event_uuid


def set_host_4k_pages(host, proc_id=1, smallpage_num=None, fail_ok=False, auth_info=Tenant.ADMIN, con_ssh=None):
    """
    Modify host memory on given processor to the closest 4k pages value

    Args:
        host (str): hostname
        proc_id (int): such as 0, 1
        smallpage_num (int): such as 0, 4. When None is set, the MAX small number will be calculated and used.
        fail_ok:
        auth_info:
        con_ssh:

    Returns (tuple):

    """
    LOG.info("Setting host {}'s proc_id {} to contain {} 4k pages".format(host, proc_id, smallpage_num))
    mem_vals = get_host_mem_values(
            host, ['vm_total_4K', 'vm_hp_total_2M', 'vm_hp_total_1G', 'vm_hp_avail_2M', 'mem_avail(MiB)', ],
            proc_id=proc_id, con_ssh=con_ssh, auth_info=auth_info)

    page_4k_total, page_2m_total, page_1g_total, page_2m_avail, mem_avail = [int(val) for val in mem_vals]

    # set max smallpage num if smallpage_num is unset
    if smallpage_num is None:
        smallpage_num = int(mem_avail*1024/4)

    diff_page = smallpage_num - page_4k_total

    new_2m = None
    new_1g = None

    if diff_page > 0:
        num_2m_avail_to_4k_page = int(page_2m_avail*2*256)
        if num_2m_avail_to_4k_page < diff_page:
            # change all 2M page to smallpage and available 1G hugepage
            new_2m = 0
            new_1g = page_1g_total - math.ceil((diff_page - num_2m_avail_to_4k_page) * 4 / 1024 / 1024)
        else:
            new_2m = page_2m_total - math.ceil(diff_page * 4 / 1024 / 2)

    args_dict = {
        '-2M': new_2m,
        '-1G': new_1g,
    }
    args_str = ''
    for key, value in args_dict.items():
        if value is not None:
            args_str = ' '.join([args_str, key, str(value)])

    code, output = cli.system('host-memory-modify {}'.format(args_str), "{} {}".format(host, proc_id),
                              ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok, rtn_list=True)

    if code == 1:
        return 1, output
    else:
        LOG.info("system host-memory-modify ran successfully.")
        return 0, "4k memory is modified to {} in pending.".format(smallpage_num)


def get_host_mem_values(host, headers, proc_id, wait_for_avail_update=True, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Get host memory values
    Args:
        host (str): hostname
        headers (list):
        proc_id (int|str): such as 0, '1'
        wait_for_avail_update (bool): wait for mem_avail to be smaller than mem_total in case host just unlocked as per
            CGTS-7499
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (list):

    """

    cmd = 'host-memory-list --nowrap'
    table_ = table_parser.table(cli.system(cmd, host, ssh_client=con_ssh, auth_info=auth_info))

    if wait_for_avail_update:
        end_time = time.time() + 240
        while time.time() < end_time:
            total_mems = [int(mem) for mem in table_parser.get_column(table_, 'mem_total(MiB)')]
            avail_mems = [int(mem) for mem in table_parser.get_column(table_, 'mem_avail(MiB)')]

            for i in range(len(total_mems)):
                if total_mems[i] <= avail_mems[i]:
                    break
            else:
                LOG.debug("mem_total is larger than mem_avail")
                break

            LOG.info("mem_total is no larger than mem_avail, wait for mem_avail to update")
            time.sleep(5)
            table_ = table_parser.table(cli.system(cmd, host, ssh_client=con_ssh, auth_info=auth_info))
        else:
            raise SystemError("mem_total is no larger than mem_avail in 4 minutes")

    res = []
    for header in headers:
        value = table_parser.get_values(table_, header, strict=False, **{'processor': str(proc_id)})[0]
        res.append(value)

    return res


def get_host_used_mem_values(host, proc_id=0, auth_info=Tenant.ADMIN, con_ssh=None):
    """
    Return number of MiB used by a specific host
    Args:
        host:
        proc_id:
        auth_info:
        con_ssh:

    Returns (int):

    """
    mem_vals = get_host_mem_values(
        host, ['mem_total(MiB)', 'mem_avail(MiB)', 'avs_hp_size(MiB)', 'avs_hp_total'],
        proc_id=proc_id, con_ssh=con_ssh, auth_info=auth_info)

    mem_total, mem_avail, avs_hp_size, avs_hp_total = [int(val) for val in mem_vals]

    used_mem = mem_total - mem_avail - avs_hp_size * avs_hp_total

    return used_mem


def get_processors_shared_cpu_nums(host, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Get number of shared cores for each processor of given host.

    Args:
        host (str): hostname
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (dict): proc_id(str) and num_of_cores(int) pairs. e.g.,: {'0': 1, '1': 1}

    """
    table_ = table_parser.table(cli.system('host-cpu-list', host, ssh_client=con_ssh, auth_info=auth_info))
    proc_ids = set(table_parser.get_column(table_, 'processor'))
    table_ = table_parser.filter_table(table_, assigned_function='Shared')

    results = {}
    for proc_id in proc_ids:
        cores = len(table_parser.get_values(table_, 'log_core', processor=proc_id))
        results[proc_id] = cores

    return results


def is_hyperthreading_enabled(host, con_ssh=None):
    table_ = table_parser.table(cli.system('host-cpu-list', host, ssh_client=con_ssh))
    return len(set(table_parser.get_column(table_, 'thread'))) > 1


def create_storage_profile(host, profile_name='', con_ssh=None):
    """
    Create a storage profile

    Args:
        host (str): hostname or id
        profile_name (str): name of the profile to create
        con_ssh (SSHClient):

    Returns (str): uuid of the profile created if success, '' otherwise

    """
    if not profile_name:
        profile_name = time.strftime('storprof_%Y%m%d_%H%M%S_', time.localtime())

    cmd = 'storprofile-add {} {}'.format(profile_name, host)

    table_ = table_parser.table(cli.system(cmd, ssh_client=con_ssh, fail_ok=False, auth_info=Tenant.ADMIN,
                                           rtn_list=False))
    uuid = table_parser.get_value_two_col_table(table_, 'uuid')

    return uuid

#
# def to_delete_apply_storage_profile(host, profile=None, con_ssh=None, fail_ok=False):
#     """
#     Apply a storage profile
#
#     Args:
#         host (str): hostname or id
#         profile (str): name or id of storage-profile
#         fail_ok (bool):
#         con_ssh (SSHClient):
#
#     Returns (dict): proc_id(str) and num_of_cores(int) pairs. e.g.,: {'0': 1, '1': 1}
#
#     """
#     if not profile:
#         raise ValueError('Name or uuid must be provided to apply that storage-profile')
#
#     cmd = 'host-apply-storprofile {} {}'.format(host, profile)
#     LOG.debug('cmd={}'.format(cmd))
#     code, output = cli.system(cmd, ssh_client=con_ssh, fail_ok=fail_ok, rtn_list=True, auth_info=Tenant.ADMIN)
#
#     return code, output


def delete_storage_profile(profile='', con_ssh=None):
    """
    Delete a storage profile

    Args:
        profile (str): name of the profile to create
        con_ssh (SSHClient):

    Returns (): no return if success, will raise exception otherwise

    """
    if not profile:
        raise ValueError('Name or uuid must be provided to delete the storage-profile')

    cmd = 'storprofile-delete {}'.format(profile)

    cli.system(cmd, ssh_client=con_ssh, fail_ok=False, auth_info=Tenant.ADMIN, rtn_list=False)


def get_host_cpu_list_table(host, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Get the parsed version of the output from system host-cpu-list <host>
    Args:
        host (str): host's name
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (dict): output of system host-cpu-list <host> parsed by table_parser

    """
    output = cli.system('host-cpu-list', host, ssh_client=con_ssh, auth_info=auth_info)
    table_ = table_parser.table(output)
    return table_


def get_host_mem_list(host, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Get the parsed version of the output from system host-memory-list <host>
        Args:
            host (str): host's name
            con_ssh (SSHClient):
            auth_info (dict):

        Returns (dict): output of system host-memory-list <host> parsed by table_parser

        """
    output = cli.system('host-memory-list', host, ssh_client=con_ssh, auth_info=auth_info)
    table_ = table_parser.table(output)
    return table_


def get_host_cpu_show_table(host, proc_num, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Get the parsed version of the output from system host-cpu-show <host> <proc_num>
    Args:
        host (str): host's name
        proc_num (int): logical core number
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (dict): output of system host-cpu-show <host> <proc_num> parsed by table_parser

    """
    pos_args = "{} {}".format(host, proc_num)
    output = cli.system('host-cpu-show', positional_args=pos_args, ssh_client=con_ssh, auth_info=auth_info)
    table_ = table_parser.table(output)
    return table_


def get_host_memory_table(host, proc_num, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Get the parsed version of the output from system host-memory-list <host> <proc_num>
    Args:
        host (str): host's name
        proc_num (int): processor number
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (dict): output of system host-memory-show <host> <proc_num> parsed by table_parser

    """
    pos_args = "{} {}".format(host, proc_num)
    output = cli.system('host-memory-show', positional_args=pos_args, ssh_client=con_ssh, auth_info=auth_info)
    table_ = table_parser.table(output)
    return table_


def get_host_ports_values(host, header='name', if_name=None, pci_addr=None, proc=None, dev_type=None, strict=True,
                          regex=False, con_ssh=None, auth_info=Tenant.ADMIN, **kwargs):
    """
    Get
    Args:
        host:
        header:
        if_name:
        pci_addr:
        proc:
        dev_type:
        strict:
        regex:
        con_ssh:
        auth_info:
        **kwargs:

    Returns (list):

    """
    table_ = table_parser.table(cli.system('host-port-list --nowrap', host, ssh_client=con_ssh, auth_info=auth_info))

    args_tmp = {
        'name': if_name,
        'pci address': pci_addr,
        'processor': proc,
        'device type': dev_type
    }

    for key, value in args_tmp.items():
        if value is not None:
            kwargs[key] = value

    return table_parser.get_values(table_, header, strict=strict, regex=regex, **kwargs)


def get_host_interfaces_table(host, show_all=False, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Get system host-if-list <host> table
    Args:
        host (str):
        show_all (bool):
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (dict):

    """
    args = ''
    args += ' --a' if show_all else ''
    args += ' ' + host

    table_ = table_parser.table(cli.system('host-if-list --nowrap', args, ssh_client=con_ssh, auth_info=auth_info))
    return table_


def get_host_interfaces_info(host, rtn_val='name', net_type=None, if_type=None, uses_ifs=None, used_by_ifs=None,
                             show_all=False, strict=True, regex=False, con_ssh=None, auth_info=Tenant.ADMIN,
                             exclude=False, **kwargs):
    """
    Get specified interfaces info for given host via system host-if-list

    Args:
        host (str):
        rtn_val (str): header for return info
        net_type (str): valid values: 'data', 'infra', 'mgmt', 'None' (string 'None' as opposed to None type)
        if_type (str): possible values: 'ethernet', 'ae', 'vlan'
        uses_ifs (str):
        used_by_ifs (str):
        show_all (bool): whether or not to show unused interfaces
        exclude (bool): whether or not to exclude the interfaces filtered
        strict (bool):
        regex (bool):
        con_ssh (SSHClient):
        auth_info (dict):
        **kwargs: extraheader=value pairs to further filter out info. such as attributes='MTU=1500'.

    Returns (list|dict):

    """
    table_ = get_host_interfaces_table(host=host, show_all=show_all, con_ssh=con_ssh, auth_info=auth_info)

    args_tmp = {
        'network type': net_type,
        'type': if_type,
        'uses i/f': uses_ifs,
        'used by i/f': used_by_ifs
    }

    for key, value in args_tmp.items():
        if value is not None:
            kwargs[key] = value

    info = table_parser.get_values(table_, rtn_val, strict=strict, regex=regex, exclude=exclude, **kwargs)
    if rtn_val in ['ports', 'used by i/f', 'uses i/f']:
        info = [eval(item) for item in info]

    return info


def get_host_ports_for_net_type(host, net_type='data', rtn_list=True, con_ssh=None, auth_info=Tenant.ADMIN):
    """

    Args:
        host:
        net_type:
        rtn_list:
        con_ssh:
        auth_info:

    Returns (dict):

    """
    table_ = get_host_interfaces_table(host=host, con_ssh=con_ssh, auth_info=auth_info)
    net_ifs_names = table_parser.get_values(table_, 'name', **{'network type': net_type})
    total_ports = {}
    for if_name in net_ifs_names:
        ports = eval(table_parser.get_values(table_, 'ports', name=if_name)[0])

        if not ports:
            uses_ifs = eval(table_parser.get_values(table_, 'uses i/f', name=if_name)[0])
            for use_if in uses_ifs:
                useif_ports = eval(table_parser.get_values(table_, 'ports', name=use_if)[0])
                ports += useif_ports

        total_ports[if_name] = ports

    LOG.info("{} network ports for host are: {}".format(net_type, total_ports))

    if rtn_list:
        total_ports_list = []
        for ports in list(total_ports.values()):
            total_ports_list += ports

        total_ports_list = list(set(total_ports_list))
        return total_ports_list

    return total_ports


def get_host_port_pci_address(host, interface, con_ssh=None, auth_info=Tenant.ADMIN):
    """

    Args:
        host:
        interface:
        con_ssh:
        auth_info:

    Returns (str): pci address of interface

    """
    table_ = table_parser.table(cli.system('host-port-list --nowrap', host, ssh_client=con_ssh, auth_info=auth_info))
    pci_addresses = table_parser.get_values(table_, 'pci address', name=interface)

    pci_address = pci_addresses.pop()

    LOG.info("pci address of interface {} for host is: {}".format(interface, pci_address))

    return pci_address


def get_host_port_pci_address_for_net_type(host, net_type='mgmt', rtn_list=True, con_ssh=None, auth_info=Tenant.ADMIN):
    """

    Args:
        host:
        net_type:
        rtn_list:
        con_ssh:
        auth_info:

    Returns (list):

    """
    ports = get_host_ports_for_net_type(host, net_type=net_type, rtn_list=rtn_list, con_ssh=con_ssh,
                                        auth_info=auth_info)
    pci_addresses = []
    for port in ports:
        pci_address = get_host_port_pci_address(host, port, con_ssh=con_ssh, auth_info=auth_info)
        pci_addresses.append(pci_address)

    return pci_addresses


def get_host_if_show_values(host, interface, fields, con_ssh=None, auth_info=Tenant.ADMIN):
    args = "{} {}".format(host, interface)
    table_ = table_parser.table(cli.system('host-if-show', args, ssh_client=con_ssh, auth_info=auth_info))

    if isinstance(fields, str):
        fields = [fields]

    res = []
    for field in fields:
        res.append(table_parser.get_value_two_col_table(table_, field))

    return res


def get_hosts_interfaces_info(hosts, fields, con_ssh=None, auth_info=Tenant.ADMIN, strict=True, **interface_filters):
    if isinstance(hosts, str):
        hosts = [hosts]

    res = {}
    for host in hosts:
        interfaces = get_host_interfaces_info(host, rtn_val='name', strict=strict, **interface_filters)
        host_res = {}
        for interface in interfaces:
            values = get_host_if_show_values(host, interface, fields=fields, con_ssh=con_ssh, auth_info=auth_info)
            host_res[interface] = values

        res[host] = host_res

    return res


def get_service_parameter_values(rtn_value='value', service=None, section=None, name=None, con_ssh=None):
    """
    Returns the list of values from system service-parameter-list
    service, section, name can be used to filter the table
    Args:
        rtn_value (str): field to return valueds for. Default to 'value'
        service (str):
        section (str):
        name (str):
        con_ssh:

    Returns (list):

    """
    kwargs = {}
    if service:
        kwargs['service'] = service
    if section:
        kwargs['section'] = section
    if name:
        kwargs['name'] = name

    table_ = table_parser.table(cli.system('service-parameter-list', ssh_client=con_ssh))
    return table_parser.get_values(table_, rtn_value, **kwargs)


def create_service_parameter(service, section, name, value, con_ssh=None, fail_ok=False,
                             check_first=True, modify_existing=True):
    """
    Add service-parameter
    system service-parameter-add (service) (section) (name)=(value)
    Args:
        service (str): Required
        section (str): Required
        name (str): Required
        value (str): Required
        con_ssh:
        fail_ok:
        check_first (bool): Check if the service parameter exists before
        modify_existing (bool): Whether to modify the service parameter if it already exists

    Returns (tuple): (rtn_code, err_msg or param_uuid)

    """
    if check_first:
        val = get_service_parameter_values(service=service, section=section, name=name, con_ssh=con_ssh)
        if val:
            msg = "The service parameter {} {} {} already exists".format(service, section, name)
            LOG.info(msg)
            if modify_existing:
                return modify_service_parameter(service, section, name, value,
                                                con_ssh=con_ssh, fail_ok=fail_ok, check_first=False)
            return -1, msg

    LOG.info("Creating service parameter")
    args = service + ' ' + section + ' ' + name + '=' + value
    res, out = cli.system('service-parameter-add', args, ssh_client=con_ssh, fail_ok=fail_ok, rtn_list=True)

    if res == 1:
        return 1, out

    LOG.info("Verifying the service parameter value")
    val = get_service_parameter_values(service=service, section=section, name=name, con_ssh=con_ssh)[0]
    if val != value:
        msg = 'The service parameter was not added with the correct value'
        if fail_ok:
            return 2, msg
        raise exceptions.SysinvError(msg)
    LOG.info("Service parameter was added with the correct value")
    uuid = get_service_parameter_values(rtn_value='uuid', service=service, section=section, name=name,
                                        con_ssh=con_ssh)[0]

    return 0, uuid


def modify_service_parameter(service, section, name, value, con_ssh=None, fail_ok=False,
                             check_first=True, create=True):
    """
    Modify a service parameter
    Args:
        service (str): Required
        section (str): Required
        name (str): Required
        value (str): Required
        con_ssh:
        fail_ok:
        check_first (bool): Check if the parameter exists first
        create (bool): Whether to create the parameter if it does not exist

    Returns (tuple): (rtn_code, message)

    """
    if check_first:
        val = get_service_parameter_values(service=service, section=section, name=name, con_ssh=con_ssh)
        if not val:
            msg = "The service parameter {} {} {} doesn't exist".format(service, section, name)
            LOG.info(msg)
            if create:
                return create_service_parameter(service, section, name, value,
                                                con_ssh=con_ssh, fail_ok=fail_ok, check_first=False)
            return -1, msg
        if val[0] == value:
            msg = "The service parameter value is already set to {}".format(val)
            return -1, msg

    LOG.info("Modifying service parameter")
    args = service + ' ' + section + ' ' + name + '=' + value
    res, out = cli.system('service-parameter-modify', args, ssh_client=con_ssh, fail_ok=fail_ok, rtn_list=True)

    if res == 1:
        return 1, out

    LOG.info("Verifying the service parameter value")
    val = get_service_parameter_values(service=service, section=section, name=name, con_ssh=con_ssh)[0]
    if val != value:
        msg = 'The service parameter was not modified to the correct value'
        if fail_ok:
            return 2, msg
        raise exceptions.SysinvError(msg)
    msg = "Service parameter modified to {}".format(val)
    LOG.info(msg)
    return 0, msg


def delete_service_parameter(uuid, con_ssh=None, fail_ok=False, check_first=True):
    """
    Delete a service parameter
    Args:
        uuid (str): Required
        con_ssh:
        fail_ok:
        check_first (bool): Check if the service parameter exists before

    Returns (tuple):

    """
    if check_first:
        uuids = get_service_parameter_values(rtn_value='uuid', con_ssh=con_ssh)
        if uuid not in uuids:
            return -1, "There is no service parameter with uuid {}".format(uuid)

    res, out = cli.system('service-parameter-delete', uuid, ssh_client=con_ssh, fail_ok=fail_ok, rtn_list=True)

    if res == 1:
        return 1, out

    LOG.info("Deleting service parameter")
    uuids = get_service_parameter_values(rtn_value='uuid', con_ssh=con_ssh)
    if uuid in uuids:
        err_msg = "Service parameter was not deleted"
        if fail_ok:
            return 2, err_msg
        raise exceptions.SysinvError(err_msg)
    msg = "The service parameter {} was deleted".format(uuid)
    LOG.info(msg)
    return 0, msg


def apply_service_parameters(service, wait_for_config=True, timeout=300, con_ssh=None, fail_ok=False):
    """
    Apply service parameters
    Args:
        service (str): Required
        wait_for_config (bool): Wait for config out of date alarms to clear
        timeout (int):
        con_ssh:
        fail_ok:

    Returns (tuple): (rtn_code, message)

    """
    LOG.info("Applying service parameters {}".format(service))
    res, out = cli.system('service-parameter-apply', service, rtn_list=True, fail_ok=fail_ok, ssh_client=con_ssh)

    if res == 1:
        return res, out

    alarm_id = '250.001'
    time.sleep(10)

    if wait_for_config:
        LOG.info("Waiting for config-out-of-date alarms to clear. "
                 "There may be cli errors when active controller's config updates")
        end_time = time.time() + timeout
        while time.time() < end_time:
            table_ = get_alarms_table(uuid=True, con_ssh=con_ssh)
            alarms_tab = table_parser.filter_table(table_, **{'Alarm ID': alarm_id})
            alarms_tab = _compose_alarm_table(alarms_tab, uuid=True)
            uuids = table_parser.get_values(alarms_tab, 'uuid')
            if not uuids:
                LOG.info("Config has been applied")
                break
            time.sleep(5)
        else:
            err_msg = "The config has not finished applying after timeout"
            if fail_ok:
                return 2, err_msg
            raise exceptions.TimeoutException(err_msg)

    return 0, "The {} service parameter was applied".format(service)


def get_hosts_by_personality(con_ssh=None, source_admin=False):
    """
    get hosts by different personality
    Args:
        con_ssh (SSHClient):
        source_admin (bool): whether to source to admin user when running commands. Normally used by
            stand-alone utils without using pytest.

    Returns (tuple): (controllers_list, computes_list, storages_list)
        Examples: for CPE with 2 controllers, returns:
            ([controller-0, controller-1], [], [])

    """
    source_cred = Tenant.ADMIN if source_admin else None
    hosts_tab = table_parser.table(cli.system('host-list', ssh_client=con_ssh, source_creden_=source_cred))
    controllers = table_parser.get_values(hosts_tab, 'hostname', personality='controller')
    computes = table_parser.get_values(hosts_tab, 'hostname', personality='compute')
    storages = table_parser.get_values(hosts_tab, 'hostname', personality='storage')

    return controllers, computes, storages


def are_hosts_unlocked(con_ssh=None):

    table_ = table_parser.table(cli.system('host-list', ssh_client=con_ssh))
    return "locked" not in (table_parser.get_column(table_, 'administrative'))


def get_system_health_query_upgrade(con_ssh=None):

    output = (cli.system('health-query-upgrade', ssh_client=con_ssh)).splitlines()
    failed = {}
    ok = {}
    for line in output:
        if ":" in line:
            k, v = line.split(":")
            if "[OK]" in v.strip():
                ok[k.strip()] = v.strip()
            elif "[Fail]" in v.strip():
                failed[k.strip()] = v.strip()
        elif "Missing manifests" in line:
            failed[line] = line
    if len(failed) > 0:
        return 1, failed
    else:
        return 0, None


def get_system_health_query(con_ssh=None):

    output = (cli.system('health-query', ssh_client=con_ssh)).splitlines()
    failed = {}
    ok = {}
    for line in output:
        if ":" in line:
            k, v = line.split(":")
            if "[OK]" in v.strip():
                ok[k.strip()] = v.strip()
            elif "[Fail]" in v.strip():
                failed[k.strip()] = v.strip()
    if len(failed) > 0:
        return 1, failed
    else:
        return 0, None


def system_upgrade_start(con_ssh=None, force=False, fail_ok=False):
    """

    Args:
        con_ssh:
        force:
        fail_ok:

    Returns (tuple):
        (0, output)
        (1, <stderr>) : "if fail_ok is true # cli returns stderr.
        (2, <stderr>) : "applicable only if fail_ok is true. upgrade-start rejected:
        An upgrade is already in progress."
    """
    if force:
        rc, output = cli.system("upgrade-start", positional_args='--force', fail_ok=True, ssh_client=con_ssh)
    else:
        rc, output = cli.system("upgrade-start", fail_ok=True, ssh_client=con_ssh)

    if rc == 0:
        LOG.info("system upgrade-start ran successfully.")
        return 0, output

    else:
        if "An upgrade is already in progress" in output:
            # upgrade already in progress
            LOG.warning("Upgrade is already in progress. No need to start")
            if fail_ok:
                return 2, output
            else:
                raise exceptions.CLIRejected(output)
        else:
            err_msg = "CLI system command failed: {}".format(output)
            LOG.warning(err_msg)
            if fail_ok:
                return 1, output
            else:
                raise exceptions.CLIRejected(err_msg)


def system_upgrade_show(con_ssh=None):

    """

    Args:
        con_ssh:

    Returns (tuple):
        (0, dict/list)
        (1, <stderr>)   # cli returns stderr.

    """

    rc, output = cli.system("upgrade-show", fail_ok=True, ssh_client=con_ssh)

    if rc == 0:
        return rc, table_parser.table(output)
    else:
        return rc, output


def activate_upgrade(con_ssh=None, fail_ok=False):
    """
    Activates upgrade
    Args:
        con_ssh (SSHClient):
        fail_ok (bool):

    Returns (tuple):
        (0, dict/list)
        (1, <stderr>)   # cli returns stderr, applicable if fail_ok is true

    """
    rc, output = cli.system('upgrade-activate', ssh_client=con_ssh, fail_ok=True, rtn_list=True)
    if rc != 0:
        err_msg = "CLI system uprade-activate failed: {}".format(output)
        LOG.warning(err_msg)
        if fail_ok:
            return rc, output
        else:
            raise exceptions.CLIRejected(err_msg)

    if not wait_for_alarm_gone("250.001", con_ssh=con_ssh, timeout=900, check_interval=60, fail_ok=True):

        alarms = get_alarms(alarm_id="250.001")
        err_msg = "After activating upgrade alarms are not cleared : {}".format(alarms)
        LOG.warning(err_msg)
        if fail_ok:
            return 1, err_msg
        else:
            raise exceptions.HostError(err_msg)

    if not wait_for_upgrade_activate_complete(fail_ok=True):
        err_msg = "Upgrade activate failed"
        LOG.warning(err_msg)
        if fail_ok:
            return 1, err_msg
        else:
            raise exceptions.HostError(err_msg)

    LOG.info("Upgrade activation complete")
    return 0, None


def get_hosts_upgrade_status(con_ssh=None):
    return table_parser.table(cli.system('host-upgrade-list', ssh_client=con_ssh))


def get_upgrade_state(con_ssh=None):

    output = cli.system('upgrade-show', ssh_client=con_ssh)

    if ("+" and "-" and "|") in output:
        table_ = table_parser.table(output)
        table_ = table_parser.filter_table(table_, Property="state")
        return table_parser.get_column(table_, "Value")
    else:
        return output


def wait_for_upgrade_activate_complete(timeout=300, check_interval=60, fail_ok=False):
    end_time = time.time() + timeout
    while time.time() < end_time:
        upgrade_state = get_upgrade_state()
        if "activation-complete" in upgrade_state:
            LOG.info('Upgrade activation-complete')
            return True

        time.sleep(check_interval)

    err_msg = "Upgrade activation did not complete after waiting for {} seconds. Current state is {}".\
        format(timeout, upgrade_state)
    if fail_ok:
        LOG.warning(err_msg)
        return False, None
    raise exceptions.TimeoutException(err_msg)


def complete_upgrade(con_ssh=None, fail_ok=False):
    """
    Completes upgrade
    Args:
        con_ssh (SSHClient):
        fail_ok (bool):

    Returns (tuple):
        (0, dict/list)
        (1, <stderr>)   # cli returns stderr, applicable if fail_ok is true

    """
    rc, output = cli.system('upgrade-complete', ssh_client=con_ssh, fail_ok=True, rtn_list=True)
    if rc != 0:
        err_msg = "CLI system upgrade-complete rejected: {}".format(output)
        LOG.warning(err_msg)
        if fail_ok:
            return 1, output
        else:
            raise exceptions.CLIRejected(err_msg)

    return 0, "Upgrade complete"


def is_patch_current(con_ssh=None):
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    output = con_ssh.exec_cmd('system health-query')[1]

    patch_line = [l for l in output.splitlines() if "patch" in l]
    return 'OK' in patch_line.pop()


def get_system_software_version(con_ssh=None):
    """

    Args:
        con_ssh:

    Returns (str): e.g., 16.10

    """
    build_info = get_buildinfo(con_ssh=con_ssh)
    sw_line = [l for l in build_info.splitlines() if "SW_VERSION" in l]
    return ((sw_line.pop()).split("=")[1]).replace('"', '')


def import_load(load_path, timeout=120, con_ssh=None, fail_ok=False, source_creden_=None):
    rc, output = cli.system('load-import', load_path, ssh_client=con_ssh, fail_ok=True, source_creden_=source_creden_)

    if rc == 0:
        table_ = table_parser.table(output)
        id_ = (table_parser.get_values(table_, "Value", Property='id')).pop()
        soft_ver = (table_parser.get_values(table_, "Value", Property='software_version')).pop()
        LOG.info('Waiting to finish importing  load id {} version {}'.format(id_, soft_ver))

        end_time = time.time() + timeout

        while time.time() < end_time:

            state = get_imported_load_state(id_, load_version=soft_ver, con_ssh=con_ssh, source_creden_=source_creden_)
            LOG.info("Import state {}".format(state))
            if "imported" in state:
                LOG.info("Importing load {} is completed".format(soft_ver))
                return [rc, id_, soft_ver]

            time.sleep(3)

        err_msg = "Timeout waiting to complete importing load {}".format(soft_ver)
        LOG.warning(err_msg)
        if fail_ok:
            return [1, err_msg]
        else:
            raise exceptions.TimeoutException(err_msg)
    else:
        err_msg = "CLI command rejected: {}".format(output)
        if fail_ok:
            return [1, err_msg]
        else:
            raise exceptions.CLIRejected(err_msg)


def get_imported_load_id(load_version=None, con_ssh=None, source_creden_=None):
    table_ = table_parser.table(cli.system('load-list', ssh_client=con_ssh, source_creden_=source_creden_))
    if load_version:
        table_ = table_parser.filter_table(table_, state='imported', software_version=load_version)
    else:
        table_ = table_parser.filter_table(table_, state='imported')

    return table_parser.get_values(table_, 'id')[0]


def get_imported_load_state(load_id, load_version=None, con_ssh=None, source_creden_=None):
    table_ = table_parser.table(cli.system('load-list', ssh_client=con_ssh, source_creden_=source_creden_))
    if load_version:
        table_ = table_parser.filter_table(table_, id=load_id, software_version=load_version)
    else:
        table_ = table_parser.filter_table(table_, id=load_id)

    return (table_parser.get_values(table_, 'state')).pop()


def get_imported_load_version( con_ssh=None, source_creden_=None):
    table_ = table_parser.table(cli.system('load-list', ssh_client=con_ssh, source_creden_=source_creden_))
    table_ = table_parser.filter_table(table_, state='imported')

    return table_parser.get_values(table_, 'software_version')


def get_active_load_id(con_ssh=None, source_creden_=None):
    table_ = table_parser.table(cli.system('load-list', ssh_client=con_ssh, source_creden_=source_creden_))

    table_ = table_parser.filter_table(table_, state="active")
    return table_parser.get_values(table_, 'id')


def get_software_loads(rtn_vals=('sw_id', 'state', 'software_version'), sw_id=None, state=None, software_version=None,
                       strict=False, con_ssh=None, source_creden_=None):

    table_ = table_parser.table(cli.system('load-list', ssh_client=con_ssh, source_creden_=source_creden_))

    kwargs_dict = {
        'sw_id': sw_id,
        'state': state,
        'software_version': software_version,
    }

    kwargs = {}
    for key, value in kwargs_dict.items():
        if value is not None:
            kwargs[key] = value

    if kwargs:
        table_ = table_parser.filter_table(table_, strict=strict, **kwargs)

    rtn_vals_list = []
    for val in rtn_vals:
        vals = table_parser.get_column(table_, val)
        rtn_vals_list.append(vals)

    rtn_vals_list = zip(*rtn_vals_list)

    rtn_vals_list = [' '.join(vals) for vals in rtn_vals_list]

    return rtn_vals_list


def delete_imported_load(load_version=None, con_ssh=None, fail_ok=False, source_creden_=None):
    load_id = get_imported_load_id(load_version=load_version, con_ssh=con_ssh, source_creden_=source_creden_)

    rc, output = cli.system('load-delete', load_id, ssh_client=con_ssh,
                            fail_ok=True, source_creden_=source_creden_)
    if rc == 1:
        return 1, output

    if not wait_for_delete_imported_load(load_id, con_ssh=con_ssh,  fail_ok=True):
        err_msg = "Unable to delete imported load {}".format(load_id)
        LOG.warning(err_msg)
        if fail_ok:
            return 1, err_msg
        else:
            raise exceptions.HostError(err_msg)


def wait_for_delete_imported_load(load_id, timeout=120, check_interval=5, fail_ok=False, con_ssh=None,
                                  auth_info=Tenant.ADMIN):

    LOG.info("Waiting for imported load  {} to be deleted from the load-list ".format(load_id))
    end_time = time.time() + timeout
    while time.time() < end_time:
        table_ = table_parser.table(cli.system('load-list', ssh_client=con_ssh, auth_info=auth_info))

        table_ = table_parser.filter_table(table_, **{'id': load_id})
        if len(table_parser.get_values(table_, 'id')) == 0:
            return True
        else:
            if 'deleting' in table_parser.get_column(table_, 'state'):
                rc, output = cli.system('load-delete', load_id, ssh_client=con_ssh, fail_ok=True)
        time.sleep(check_interval)

    else:
        err_msg = "Timed out waiting for load {} to get deleted".format(load_id)
        if fail_ok:
            LOG.warning(err_msg)
            return False
        else:
            raise exceptions.TimeoutException(err_msg)


def install_upgrade_license(license_path, timeout=30, con_ssh=None):
    """
    Installs upgrade license on controller-0
    Args:
        con_ssh (SSHClient): " SSH connection to controller-0"
        license_path (str): " license full path in controller-0"
        timeout (int);

    Returns (int): 0 - success; 1 - failure

    """
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    cmd = "sudo license-install " + license_path
    con_ssh.send(cmd)
    end_time = time.time() + timeout
    rc = 1
    while time.time() < end_time:
        index = con_ssh.expect([con_ssh.prompt, Prompt.PASSWORD_PROMPT, Prompt.Y_N_PROMPT], timeout=timeout)
        if index == 2:
            con_ssh.send('y')

        if index == 1:
            con_ssh.send(HostLinuxCreds.get_password())

        if index == 0:
            rc = con_ssh.exec_cmd("echo $?")[0]
            con_ssh.flush()
            break

    return rc


def abort_upgrade(con_ssh=None, timeout=60, fail_ok=False):
    """
    Aborts upgrade
    Args:
        con_ssh (SSHClient):
        timeout (int)
        fail_ok (bool):

    Returns (tuple):
        (0, dict/list)
        (1, <stderr>)   # cli returns stderr, applicable if fail_ok is true

    """
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    cmd = "source /etc/nova/openrc; system upgrade-abort"
    con_ssh.send(cmd)
    end_time = time.time() + timeout
    rc = 1
    while time.time() < end_time:
        index = con_ssh.expect([con_ssh.prompt,  Prompt.YES_N_PROMPT], timeout=timeout)
        if index == 1:
            con_ssh.send('yes')
            index = con_ssh.expect([con_ssh.prompt, Prompt.CONFIRM_PROMPT], timeout=timeout)
            if index == 1:
               con_ssh.send('abort')
               index = con_ssh.expect([con_ssh.prompt, Prompt.CONFIRM_PROMPT], timeout=timeout)
        if index == 0:
            rc = con_ssh.exec_cmd("echo $?")[0]
            con_ssh.flush()
            break

    if rc != 0:
        err_msg = "CLI system upgrade-abort rejected"
        LOG.warning(err_msg)
        if fail_ok:
            return 1, err_msg
        else:
            raise exceptions.CLIRejected(err_msg)

    table_ = system_upgrade_show()[1]
    state = table_parser.get_value_two_col_table(table_, "state")
    if "aborting" in state:
        return 0, "Upgrade aborting"
    else:
        err_msg = "Upgrade abort failed"
        if fail_ok:
            LOG.warn(err_msg)
            return 1, err_msg
        else:
            raise exceptions.CLIRejected(err_msg)


def get_host_device_list_values(host, field='name', con_ssh=None, auth_info=Tenant.ADMIN, strict=True, regex=False,
                                **kwargs):
    """
    Get the parsed version of the output from system host-device-list <host>
    Args:
        host (str): host's name
        field (str): field name to return value for
        con_ssh (SSHClient):
        auth_info (dict):
        strict (bool): whether to perform strict search on filter
        regex (bool): whether to use regular expression to search the value in kwargs
        kwargs: key-value pairs to filter the table

    Returns (list): output of system host-device-list <host> parsed by table_parser

    """
    table_ = table_parser.table(cli.system('host-device-list', host, ssh_client=con_ssh, auth_info=auth_info))

    return table_parser.get_values(table_, target_header=field, strict=strict, regex=regex, **kwargs)


def get_host_device_values(host, device, fields, con_ssh=None, auth_info=Tenant.ADMIN):
    args = "{} {}".format(host, device)
    table_ = table_parser.table(cli.system('host-device-show', args, ssh_client=con_ssh, auth_info=auth_info))

    if isinstance(fields, str):
        fields = [fields]

    res = []
    for field in fields:
        res.append(table_parser.get_value_two_col_table(table_, field))

    return res


def get_host_device_pci_name(host, device,  con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Gets host's Co-processor pci device name
    Args:
        host (str): The host id or hostname
        device (str): is the pci device address
        con_ssh:
        auth_info:

    Returns: (str)
        The pci name of the device

    """
    return get_host_device_values(host, device, 'name', con_ssh=con_ssh, auth_info=auth_info)[0]


def get_host_device_pci_status(host, device,  con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Gets host's Co-processor pci device status
    Args:
        host (str): The host id or hostname
        device (str): is the pci device address or name
        con_ssh:
        auth_info:

    Returns: (str)
        The pci device status

    """
    return get_host_device_values(host, device, 'enabled', con_ssh=con_ssh, auth_info=auth_info)[0]


def modify_host_device_pci_name(host, device, name, con_ssh=None, fail_ok=False, check_first=True):
    """
    Modify a host device pci name
    Args:
        host (str): Required - the host id or hostname
        device (str): Required - the pci address or pci name
        name (str): Required - new pci name
        con_ssh:
        fail_ok:
        check_first (bool): Check if the parameter exists first


    Returns (tuple): (rtn_code, message)

    """
    if check_first:
        val = get_host_device_values(host, device, 'name', con_ssh=con_ssh)
        if not val:
            msg = " Host {} does not have device {} listed".format(host, device)
            LOG.info(msg)
            return 1, msg

        if val[0] == name:
            msg = "The device pci name is already set to {}".format(val)
            return 1, msg

    LOG.info("Modifying device pci name")
    args = " {} {} --name {}".format(host, device, name)

    res, out = cli.system('host-device-modify', args, ssh_client=con_ssh, fail_ok=fail_ok, rtn_list=True)

    if res == 1:
        return 1, out

    LOG.info("Verifying the host device new pci name")
    val = get_host_device_values(host, name, 'name', con_ssh=con_ssh)
    if not val:
        msg = 'The host device pci name was not modified to the correct value'
        if fail_ok:
            return 2, msg
        raise exceptions.SysinvError(msg)
    msg = "Host device pci name modified to {}".format(name)
    LOG.info(msg)
    return 0, msg


def modify_host_device_status(host, device, status,  con_ssh=None, fail_ok=False, check_first=True):
    """
    Modify a host device pci name
    Args:
        host (str): Required - the host id or hostname
        device (str): Required - the pci address or pci name
        status (str): Required - new pci status True or False
        con_ssh:
        fail_ok:
        check_first (bool): Check if the parameter exists first


    Returns (tuple): (rtn_code, message)

    """
    if check_first:
        val = get_host_device_values(host, device, 'enabled', con_ssh=con_ssh)
        if not val:
            msg = " Host {} does not have device {} listed".format(host, device)
            LOG.info(msg)
            return 1, msg

        if val[0] == status:
            msg = "The device availability status is already set to {}".format(status)
            return 1, msg

    LOG.info("Modifying device availability status")
    args = " {} {} --enabled {}".format(host, device, status)

    res, out = cli.system('host-device-modify', args, ssh_client=con_ssh, fail_ok=fail_ok, rtn_list=True)

    if res == 1:
        return 1, out

    LOG.info("Verifying the host device enabled status")
    val = get_host_device_values(host, device, 'enabled', con_ssh=con_ssh)
    if val[0] != status:
        msg = 'The host device enabled status was not modified to the correct value'
        if fail_ok:
            return 2, msg
        raise exceptions.SysinvError(msg)
    msg = "Host device availability status is modified to {}".format(status)
    LOG.info(msg)
    return 0, msg


def get_controller_fs_values(con_ssh=None, auth_info=Tenant.ADMIN):

    table_ = table_parser.table(cli.system('controllerfs-show',  ssh_client=con_ssh, auth_info=auth_info))

    rows = table_parser.get_all_rows(table_)
    values = {}
    for row in rows:
        values[row[0].strip()] = row[1].strip()
    return values


def wait_for_services_enable(timeout=300, fail_ok=False, con_ssh=None):
    """
    Wait for services to be enabled-active in system service-list
    Args:
        timeout (int): max wait time in seconds
        fail_ok (bool): whether return False or raise exception when some services fail to reach enabled-active state
        con_ssh (SSHClient):

    Returns (tuple): (<res>(bool), <msg>(str))
        (True, "All services are enabled-active")
        (False, "Some services are not enabled-active: <failed_rows>")      Applicable if fail_ok=True

    """
    LOG.info("Wait for services to be enabled-active in system service-list")
    end_time = time.time() + timeout
    while time.time() < end_time:
        service_list_tab = table_parser.table(cli.system('service-list', ssh_client=con_ssh)[1])
        states = table_parser.get_column(service_list_tab, 'state')
        if all(state == 'enabled-active' for state in states):
            LOG.info("All services are enabled-active in system service-list")
            return True, "All services are enabled-active"

    LOG.warning("Not all services are enabled-ative within {} seconds".format(timeout))
    inactive_services_tab = table_parser.filter_table(service_list_tab, exclude=True, state='enabled-active')
    msg = "Some services are not enabled-active: {}".format(table_parser.get_all_rows(inactive_services_tab))
    if fail_ok:
        return False, msg
    raise exceptions.SysinvError(msg)


def is_infra_network_conifgured(con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Whether infra network is configured in the system
    Args:
        con_ssh (SSHClient):
        auth_info (dict)

    Returns:
        (bool): True if infra network is configured, else False
         value dict:
    """
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()
    output = cli.system('infra-show', ssh_client=con_ssh, auth_info=auth_info )
    if "Infrastructure network not configured" in output:
        return False,  None
    table_ = table_parser.table(output)
    rows = table_parser.get_all_rows(table_)
    values = {}
    for row in rows:
        values[row[0].strip()] = row[1].strip()
    return True, values


def add_infra_network(infra_network_cidr=None, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Adds infra network to the system
    Args:
        infra_network_cidr:
        con_ssh:
        auth_info:

    Returns:

    """

    if infra_network_cidr is None:
        infra_network_cidr = Networks.INFRA_NETWORK_CIDR

    output = cli.system('infra-add', infra_network_cidr,  ssh_client=con_ssh, auth_info=auth_info)
    if "Infrastructure network not configured" in output:
        msg = "Infra Network already configured in the system"
        LOG.info(msg)
        return False,  None
    table_ = table_parser.table(output)
    rows = table_parser.get_all_rows(table_)
    values = {}
    for row in rows:
        values[row[0].strip()] = row[1].strip()
    return True, values


def enable_murano(con_ssh=None, auth_info=Tenant.ADMIN, fail_ok=False):
    """
    Enable Murano Services
    Args:
        con_ssh:
        con_ssh (SSHClient):
        auth_info (dict):
        fail_ok: whether return False or raise exception when some services fail to reach enabled-active state

    Returns:

    """

    res, output = cli.system('service-enable murano', ssh_client=con_ssh, auth_info=auth_info,
                             fail_ok=fail_ok, rtn_list=True)
    if res == 1:
        return 1, output

    msg = "Enabled Murano Service"

    return 0, msg


def disable_murano(con_ssh=None, auth_info=Tenant.ADMIN, fail_ok=False):
    """
    Disable Murano Services
    Args:
        con_ssh (SSHClient):
        auth_info (dict):
        fail_ok: whether return False or raise exception when some services fail to reach enabled-active state

    Returns:

    """

    res, output = cli.system('service-disable murano', ssh_client=con_ssh, auth_info=auth_info,
                             fail_ok=fail_ok, rtn_list=True)
    if res == 1:
        return 1, output

    msg = "Enabled Murano Service"

    return 0, msg


def get_host_addr_list(host, rtn_val='address', ifname=None, id=None, con_ssh=None, auth_info=Tenant.ADMIN, fail_ok=False):
    """
    Disable Murano Services
    Args:
        con_ssh (SSHClient):
        ifname:
        id:
        rtn_val:
        auth_info (dict):
        fail_ok: whether return False or raise exception when some services fail to reach enabled-active state

    Returns:

    """

    table_ = table_parser.table(cli.system('host-addr-list', host,  ssh_client=con_ssh, auth_info=auth_info,
                                     fail_ok=fail_ok, rtn_list=True)[1])
    args_dict = {
        'id': id,
        'ifname': ifname,
    }
    kwargs = {}
    for key, value in args_dict.items():
        if value:
            kwargs[key] = value

    address = table_parser.get_values(table_, rtn_val, strict=True, regex=True, merge_lines=True, **kwargs)
    return address