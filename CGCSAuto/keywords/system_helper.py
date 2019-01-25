import math
import re
import time
import copy

from pytest import skip

from consts.auth import Tenant, HostLinuxCreds
from consts.cgcs import UUID, Prompt, Networks, SysType, EventLogID, PLATFORM_NET_TYPES
from consts.proj_vars import ProjVar
from consts.timeout import SysInvTimeout
from utils import cli, table_parser, exceptions
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG


def get_buildinfo(con_ssh=None, use_telnet=False, con_telnet=None):
    return _get_info_non_cli('cat /etc/build.info', con_ssh=con_ssh,  use_telnet=use_telnet,
                             con_telnet=con_telnet)


def _get_info_non_cli(cmd, con_ssh=None, use_telnet=False, con_telnet=None):
    if not use_telnet:
        if con_ssh is None:
            con_ssh = ControllerClient.get_active_controller()
        exitcode, output = con_ssh.exec_cmd(cmd, rm_date=True)
    else:
        exitcode, output = con_telnet.exec_cmd(cmd)

    if not exitcode == 0:
        raise exceptions.SSHExecCommandFailed("Command failed to execute.")

    return output


def get_sys_type(con_ssh=None, use_telnet=False, con_telnet=None):
    """
    Please do NOT call this function in testcase/keyword. This is used to set global variable SYS_TYPE in ProjVar.
    Use ProjVar.get_var('SYS_TYPE') in testcase/keyword instead.
    Args:
        con_ssh:
        use_telnet:
        con_telnet:

    Returns:

    """
    auth_info = Tenant.get('admin')
    is_aio = is_small_footprint(controller_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet,
                                auth_info=auth_info)
    if is_aio:
        sys_type = SysType.AIO_DX
        if len(get_controllers(con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet,
                               auth_info=auth_info)) == 1:
            sys_type = SysType.AIO_SX
    elif get_storage_nodes(con_ssh=con_ssh):
        sys_type = SysType.STORAGE
    else:
        sys_type = SysType.REGULAR

    # TODO: multi-region
    LOG.info("=============System type: {} ==============".format(sys_type))
    return sys_type


def is_storage_system(con_ssh=None, use_telnet=False, con_telnet=None, auth_info=Tenant.get('admin')):
    sys_type = ProjVar.get_var('SYS_TYPE')
    if sys_type:
        if not (ProjVar.get_var('IS_DC') and auth_info and
                ProjVar.get_var('PRIMARY_SUBCLOUD') != auth_info.get('region', None)):
            return SysType.STORAGE == sys_type
    else:
        return bool(get_storage_nodes(con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet,
                                      auth_info=auth_info))


def is_two_node_cpe(con_ssh=None, use_telnet=False, con_telnet=None, auth_info=Tenant.get('admin')):
    """
    Whether it is two node CPE system
    Args:
        con_ssh:
        use_telnet
        con_telnet
        auth_info

    Returns (bool):

    """
    sys_type = ProjVar.get_var('SYS_TYPE')
    if sys_type:
        if not (ProjVar.get_var('IS_DC') and auth_info and
                ProjVar.get_var('PRIMARY_SUBCLOUD') != auth_info.get('region', None)):
            return SysType.AIO_DX == sys_type
    else:
        return is_small_footprint(controller_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet) \
           and len(get_controllers(con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet)) == 2


def is_simplex(con_ssh=None, use_telnet=False, con_telnet=None, auth_info=Tenant.get('admin')):

    sys_type = ProjVar.get_var('SYS_TYPE')
    if sys_type:
        if not (ProjVar.get_var('IS_DC') and auth_info and
                ProjVar.get_var('PRIMARY_SUBCLOUD') != auth_info.get('region', None)):
            return SysType.AIO_SX == sys_type
    else:
        return is_small_footprint(controller_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet,
                                  auth_info=auth_info) and \
               len(get_controllers(con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet,
                                   auth_info=auth_info)) == 1


def is_small_footprint(controller_ssh=None, controller='controller-0', use_telnet=False, con_telnet=None,
                       auth_info=Tenant.get('admin')):
    """
    Whether it is two node CPE system or Simplex system where controller has both controller and compute functions
    Args:
        controller_ssh (SSHClient):
        controller (str): controller to check
        use_telnet
        con_telnet
        auth_info

    Returns (bool): True if CPE or Simplex, else False

    """
    sys_type = ProjVar.get_var('SYS_TYPE')
    if sys_type:
        if not (ProjVar.get_var('IS_DC') and auth_info and
                ProjVar.get_var('PRIMARY_SUBCLOUD') != auth_info.get('region', None)):
            return 'aio' in sys_type.lower()

    table_ = table_parser.table(cli.system('host-show', controller, ssh_client=controller_ssh, timeout=60,
                                           use_telnet=use_telnet, con_telnet=con_telnet, auth_info=auth_info))
    subfunc = table_parser.get_value_two_col_table(table_, 'subfunctions')

    combined = 'controller' in subfunc and re.search('compute|worker', subfunc)

    str_ = 'not ' if not combined else ''

    LOG.info("This is {}small footprint system.".format(str_))
    return combined


def get_storage_nodes(con_ssh=None, use_telnet=False, con_telnet=None, auth_info=Tenant.get('admin')):
    """
    Get hostnames with 'storage' personality from system host-list
    Args:
        con_ssh (SSHClient):
        use_telnet
        con_telnet
        auth_info

    Returns (list): list of hostnames. Empty list [] returns when no storage nodes.

    """
    return get_hostnames(personality='storage', con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet,
                         auth_info=auth_info)


def get_controllers(administrative=None, operational=None, availability=None, con_ssh=None, use_telnet=False,
                    con_telnet=None, auth_info=Tenant.get('admin')):
    """
    Get hostnames with 'controller' personality from system host-list
    Args:
        administrative
        operational
        availability
        con_ssh (SSHClient):
        use_telnet
        con_telnet
        auth_info

    Returns (list): list of hostnames

    """
    return get_hostnames(personality='controller', con_ssh=con_ssh, use_telnet=use_telnet,
                         administrative=administrative, operational=operational, availability=availability,
                         con_telnet=con_telnet, auth_info=auth_info)


def get_computes(administrative=None, operational=None, availability=None, con_ssh=None,
                 use_telnet=False, con_telnet=None, auth_info=Tenant.get('admin')):
    """
    Get hostnames with 'compute' personality from system host-list
    Args:
        administrative
        operational
        availability
        con_ssh (SSHClient):
        use_telnet
        con_telnet
        auth_info

    Returns (list): list of hostnames. Empty list [] returns when no compute nodes.

    """
    return get_hostnames(personality='compute', con_ssh=con_ssh, use_telnet=use_telnet,
                         administrative=administrative, operational=operational, availability=availability,
                         con_telnet=con_telnet, auth_info=auth_info)


def get_hostnames(personality=None, administrative=None, operational=None, availability=None, name=None,
                  strict=True, exclude=False, con_ssh=None, use_telnet=False, con_telnet=None,
                  auth_info=Tenant.get('admin'), hosts=None):
    """
    Get hostnames with given criteria
    Args:
        personality (str|list|tuple):
        administrative (str|list|tuple):
        operational (str|list|tuple):
        availability (str|list|tuple):
        name (str):
        strict (bool):
        exclude (bool):
        con_ssh (dict):
        use_telnet
        con_telnet
        auth_info
        hosts (None|list): filter out these hosts only

    Returns (list): hostnames

    """
    if not con_ssh:
        con_name = auth_info.get('region') if (auth_info and ProjVar.get_var('IS_DC')) else None
        con_ssh = ControllerClient.get_active_controller(name=con_name)

    table_ = table_parser.table(cli.system('host-list', ssh_client=con_ssh, use_telnet=use_telnet,
                                           con_telnet=con_telnet, auth_info=auth_info))

    table_ = table_parser.filter_table(table_, exclude=True, hostname='None')
    if hosts:
        table_ = table_parser.filter_table(table_, hostname=hosts)

    if personality:
        compute_personality = 'compute|worker'
        if personality == 'compute':
            personality = compute_personality
        elif 'compute' in personality:
            personality = list(personality)
            compute_index = personality.index('compute')
            personality[compute_index] = compute_personality

    filters = {'hostname': name,
               'personality': personality,
               'administrative': administrative,
               'operational': operational,
               'availability': availability}
    hostnames = table_parser.get_values(table_, 'hostname', strict=strict, exclude=exclude, regex=True, **filters)
    LOG.debug("Filtered hostnames: {}".format(hostnames))

    return hostnames


def get_hostnames_per_personality(availability=None, con_ssh=None, auth_info=Tenant.get('admin'), source_rc=False,
                                  use_telnet=False, con_telnet=None, rtn_tuple=False):
    """
    Args:
        availability
        con_ssh:
        auth_info
        source_rc
        use_telnet
        con_telnet
        rtn_tuple (bool): whether to return tuple instead of dict. i.e., <controllers>, <computes>, <storages>

    Returns (dict|tuple):
    e.g., {'controller': ['controller-0', 'controller-1'], 'compute': ['compute-0', 'compute-1], 'storage': []}

    """
    table_ = table_parser.table(cli.system('host-list', ssh_client=con_ssh, auth_info=auth_info,
                                           source_openrc=source_rc, use_telnet=use_telnet, con_telnet=con_telnet))
    personalities = ('controller', 'compute', 'storage')
    res = {}
    for personality in personalities:
        personality_tmp = 'compute|worker' if personality == 'compute' else personality
        hosts = table_parser.get_values(table_, 'hostname', personality=personality_tmp, availability=availability,
                                        regex=True)
        hosts = [host for host in hosts if host.lower() != 'none']
        res[personality] = hosts

    if rtn_tuple:
        res = res['controller'], res['compute'], res['storage']

    return res


def get_active_controller_name(con_ssh=None, use_telnet=False, con_telnet=None, auth_info=Tenant.get('admin')):
    """
    This assumes system has 1 active controller
    Args:
        con_ssh:
        use_telnet
        con_telnet
        auth_info

    Returns: hostname of the active controller
        Further info such as ip, uuid can be obtained via System.CONTROLLERS[hostname]['uuid']
    """
    return _get_active_standby(controller='active', con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet,
                               auth_info=auth_info)[0]


def get_standby_controller_name(con_ssh=None, use_telnet=False, con_telnet=None, auth_info=Tenant.get('admin')):
    """
    This assumes system has 1 standby controller
    Args:
        con_ssh:
        use_telnet
        con_telnet
        auth_info

    Returns (str): hostname of the active controller
        Further info such as ip, uuid can be obtained via System.CONTROLLERS[hostname]['uuid']
    """
    standby = _get_active_standby(controller='standby', con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet,
                                  auth_info=auth_info)
    return '' if len(standby) == 0 else standby[0]


def _get_active_standby(controller='active', con_ssh=None, use_telnet=False, con_telnet=None,
                        auth_info=Tenant.get('admin')):
    table_ = table_parser.table(cli.system('servicegroup-list', ssh_client=con_ssh, use_telnet=use_telnet,
                                           con_telnet=con_telnet, auth_info=auth_info))

    table_ = table_parser.filter_table(table_, service_group_name='controller-services')
    controllers = table_parser.get_values(table_, 'hostname', state=controller, strict=False)
    LOG.debug(" {} controller(s): {}".format(controller, controllers))

    if isinstance(controllers, str):
        controllers = [controllers]

    return controllers


def get_active_standby_controllers(con_ssh=None, use_telnet=False, con_telnet=None, auth_info=Tenant.get('admin')):
    """
    Get active controller name and standby controller name (if any)
    Args:
        con_ssh (SSHClient):
        use_telnet
        con_telnet
        auth_info

    Returns (tuple): such as ('controller-0', 'controller-1'), when non-active controller is in bad state or degraded
        state, or any scenarios where standby controller does not exist, this function will return
        (<active_con_name>, None)

    """
    table_ = table_parser.table(cli.system('servicegroup-list', ssh_client=con_ssh, auth_info=auth_info,
                                           use_telnet=use_telnet, con_telnet=con_telnet))

    table_ = table_parser.filter_table(table_, service_group_name='controller-services')
    active_con = table_parser.get_values(table_, 'hostname', state='active', strict=False)[0]
    standby_con = table_parser.get_values(table_, 'hostname', state='standby', strict=False)

    standby_con = standby_con[0] if standby_con else None
    return active_con, standby_con


def get_alarms_table(uuid=True, show_suppress=False, query_key=None, query_value=None, query_type=None, con_ssh=None,
                     mgmt_affecting=None, auth_info=Tenant.get('admin'), use_telnet=False, con_telnet=None, retry=0):
    """
    Get active alarms_and_events dictionary with given criteria
    Args:
        uuid (bool): whether to show uuid
        show_suppress (bool): whether to show suppressed alarms_and_events
        query_key (str): one of these: 'event_log_id', 'entity_instance_id', 'uuid', 'severity',
        query_value (str): expected value for given key
        query_type (str): data type of value. one of these: 'string', 'integer', 'float', 'boolean'
        mgmt_affecting (bool)
        con_ssh (SSHClient):
        auth_info (dict):
        use_telnet
        con_telnet
        retry (None|int): number of times to retry if the alarm-list cli got rejected

    Returns:
        dict: events table in format: {'headers': <headers list>, 'values': <list of table rows>}
    """
    args = '--nowrap'
    args = __process_query_args(args, query_key, query_value, query_type)
    if uuid:
        args += ' --uuid'
    if show_suppress:
        args += ' --include_suppress'
    if mgmt_affecting:
        args += ' --mgmt_affecting'

    fail_ok = True
    if not retry:
        fail_ok = False
        retry = 0

    output = None
    for i in range(retry+1):
        code, output = cli.fm('alarm-list', args, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                              rtn_list=True, use_telnet=use_telnet, con_telnet=con_telnet)
        if code == 0:
            table_ = table_parser.table(output, combine_multiline_entry=True)
            table_ = _compose_alarm_table(table_, uuid=uuid)
            return table_

        if i < retry:
            time.sleep(5)
    else:
        raise exceptions.CLIRejected('fm alarm-list cli got rejected after {} retries: {}'.format(retry, output))


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
               query_type=None, mgmt_affecting=None, con_ssh=None, auth_info=Tenant.get('admin'), combine_entries=True,
               use_telnet=False, con_telnet=None):
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
        query_key (str): key in --query <key>=<value> passed to fm alarm-list
        query_value (str): value in --query <key>=<value> passed to fm alarm-list
        query_type (str): 'string', 'integer', 'float', or 'boolean'
        mgmt_affecting (bool)
        con_ssh (SSHClient):
        auth_info (dict):
        combine_entries (bool): return list of strings when set to True, else return a list of tuples.
            e.g., when True, returns ["800.003 cluster=829851fa", "250.001 host=controller-0"]
                  when False, returns [("800.003", "cluster=829851fa"), ("250.001", "host=controller-0")]
        use_telnet
        con_telnet

    Returns (list): list of alarms with values of specified fields

    """

    table_ = get_alarms_table(show_suppress=show_suppress, query_key=query_key, query_value=query_value,
                              query_type=query_type, con_ssh=con_ssh, auth_info=auth_info,
                              use_telnet=use_telnet, con_telnet=con_telnet, mgmt_affecting=mgmt_affecting)

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
    else:
        rtn_vals_list = list(rtn_vals_list)

    return rtn_vals_list


def get_suppressed_alarms(uuid=False, con_ssh=None, auth_info=Tenant.get('admin')):

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
    table_ = table_parser.table(cli.fm('event-suppress-list', args, ssh_client=con_ssh, auth_info=auth_info))
    return table_


def unsuppress_all_events(ssh_con=None, fail_ok=False, auth_info=Tenant.get('admin')):
    """

    Args:
        ssh_con:
        fail_ok:
        auth_info:

    Returns (tuple): (<code>(int), <msg>(str))

    """
    LOG.info("Un-suppress all events")
    args = '--nowrap --nopaging'
    code, output = cli.fm('event-unsuppress-all',  positional_args=args, ssh_client=ssh_con, fail_ok=fail_ok,
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
        suppressed_list = table_parser.get_values(table_, target_header="Suppressed Alarm ID's",
                                                  **{'Status': 'suppressed'})

    if suppressed_list:
        msg = "Unsuppress-all failed. Suppressed Alarm IDs: {}".format(suppressed_list)
        if fail_ok:
            LOG.warning(msg)
            return 2, msg
        raise exceptions.NeutronError(msg)

    succ_msg = "All events unsuppressed successfully."
    LOG.info(succ_msg)
    return 0, succ_msg


def get_events(rtn_vals=('Event Log ID', 'Entity Instance ID'), limit=10, event_id=None, entity_id=None,
               severity=None, show_suppress=False, start=None, end=None, state=None, show_uuid=True,
               strict=False, time_stamp=None, reason_text=None, uuid=None,
               con_ssh=None, auth_info=Tenant.get('admin'), combine_entries=True, use_telnet=False, con_telnet=None):
    """
    Get a list of alarms with values for specified fields.
    Args:
        rtn_vals (tuple|list|str): fields to get values for
        limit (int)
        event_id (str): filter event using event log id
        reason_text (str): reason text to filter out the table (strict defined in param)
        entity_id (str): entity instance id to filter out the table (strict defined in param)
        severity (str): severity such as 'critical', 'major'
        show_suppress (bool): whether to show suppressed events. Default to False.
        show_uuid (bool): Whether to show uuid in event table
        start (str): display events after this time stamp
        end (str): display events prior to this time stamp
        state (str): filter with events state
        time_stamp (str): exact timestamp for the event, filter after events displayed
        uuid (str)
        strict (bool): whether to perform strict filter on reason text, or time_stamp
        con_ssh (SSHClient):
        auth_info (dict):
        combine_entries (bool): return list of strings when set to True, else return a list of tuples.
            e.g., when True, returns ["800.003::::cluster=829851fa", "250.001::::host=controller-0"]
                  when False, returns [("800.003", "cluster=829851fa"), ("250.001", "host=controller-0")]
        use_telnet
        con_telnet

    Returns (list): list of events with values of specified fields

    """

    table_ = get_events_table(show_uuid=show_uuid, limit=limit, event_log_id=event_id, entity_instance_id=entity_id,
                              show_suppress=show_suppress, con_ssh=con_ssh, auth_info=auth_info,
                              use_telnet=use_telnet, con_telnet=con_telnet, start=start, end=end, severity=severity)

    kwargs_dict = {
        'Reason Text': reason_text,
        'Time Stamp': time_stamp,
        'UUID': uuid,
        'State': state,
    }

    kwargs = {}
    for key, value in kwargs_dict.items():
        if value is not None:
            kwargs[key] = value

    if kwargs:
        table_ = table_parser.filter_table(table_, strict=strict, **kwargs)

    rtn_vals_list = []
    if isinstance(rtn_vals, str):
        rtn_vals = (rtn_vals, )
    for header in rtn_vals:
        vals = table_parser.get_column(table_, header)
        if not vals:
            vals = []
        rtn_vals_list.append(vals)

    LOG.warning('{}'.format(rtn_vals_list))
    rtn_vals_list = list(zip(*rtn_vals_list))
    if combine_entries:
        rtn_vals_list = ['::::'.join(vals) for vals in rtn_vals_list]

    return rtn_vals_list


def get_events_table(limit=5, show_uuid=False, show_only=None, show_suppress=False, event_log_id=None,
                     entity_type_id=None, entity_instance_id=None, severity=None, start=None, end=None, query_key=None,
                     query_value=None, query_type=None, con_ssh=None, auth_info=Tenant.get('admin'), use_telnet=False,
                     con_telnet=None, regex=False, **kwargs):
    """
    Get a list of events with given criteria as dictionary
    Args:
        limit (int): max number of event logs to return
        show_uuid (bool): whether to show uuid
        show_only (str): 'alarms_and_events' or 'logs' to return only alarms_and_events or logs
        show_suppress (bool): whether or not to show suppressed alarms_and_events
        query_key (str): OBSOLETE. one of these: 'event_log_id', 'entity_instance_id', 'uuid', 'severity',
        query_value (str): OBSOLETE. expected value for given key
        query_type (str): OBSOLETE. data type of value. one of these: 'string', 'integer', 'float', 'boolean'
        event_log_id (str|None): event log id passed to system eventlog -q event_log_id=<event_log_id>
        entity_type_id (str|None): entity_type_id passed to system eventlog -q entity_type_id=<entity_type_id>
        entity_instance_id (str|None): entity_instance_id passed to
            system eventlog -q entity_instance_id=<entity_instance_id>
        severity (str|None):
        start (str|None): start date/time passed to '--query' in format "20170410"/"20170410 01:23:34"
        end (str|None): end date/time passed to '--query' in format "20170410"/"20170410 01:23:34"
        con_ssh (SSHClient):
        auth_info (dict):
        use_telnet
        con_telnet
        regex (bool):
        **kwargs: filter table after table returned

    Returns:
        dict: events table in format: {'headers': <headers list>, 'values': <list of table rows>}
    """
    args = '-l {}'.format(limit)
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
        'start': '{}'.format(start) if start else None,
        'end': '{}'.format(end) if end else None
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
    if show_uuid:
        args += ' --uuid'
    if show_only:
        args += ' --{}'.format(show_only.lower())
    if show_suppress:
        args += ' --include_suppress'

    table_ = table_parser.table(cli.fm('event-list ', args, ssh_client=con_ssh, auth_info=auth_info,
                                       use_telnet=use_telnet, con_telnet=con_telnet,))

    if kwargs:
        table_ = table_parser.filter_table(table_, regex=regex, **kwargs)

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
                    fail_ok=True, rtn_val='Event Log ID', con_ssh=None, auth_info=Tenant.get('admin'), regex=False,
                    use_telnet=False, con_telnet=None,
                    strict=True, check_interval=3, event_log_id=None, entity_type_id=None, entity_instance_id=None,
                    severity=None, start=None, end=None, **kwargs):
    """
    Wait for event(s) to appear in fm event-list
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
        entity_instance_id (str|None): entity_instance_id passed to
            system eventlog -q entity_instance_id=<entity_instance_id>
        severity (str|None):
        start (str|None): start date/time passed to '--query' in format "20170410"/"20170410 01:23:34"
        end (str|None): end date/time passed to '--query' in format "20170410"/"20170410 01:23:34"
        use_telnet
        con_telnet

        **kwargs: criteria to filter out event(s) from the events list table

    Returns:
        list: list of event log ids (or whatever specified in rtn_value) for matching events.

    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        events_tab = get_events_table(limit=num, show_uuid=uuid, show_only=show_only, event_log_id=event_log_id,
                                      entity_type_id=entity_type_id, entity_instance_id=entity_instance_id,
                                      severity=severity, start=start, end=end, query_key=query_key,
                                      query_value=query_value, query_type=query_type,
                                      con_ssh=con_ssh, auth_info=auth_info, use_telnet=use_telnet,
                                      con_telnet=con_telnet)
        events_tab = table_parser.filter_table(events_tab, strict=strict, regex=regex, **kwargs)
        events = table_parser.get_column(events_tab, rtn_val)
        if events:
            LOG.info("Event(s) appeared in event-list: {}".format(events))
            return events

        time.sleep(check_interval)

    msg = "Event(s) did not appear in fm event-list within timeout."
    if fail_ok:
        LOG.warning(msg)
        return []
    else:
        raise exceptions.TimeoutException(msg)


def delete_alarms(alarms=None, fail_ok=False, con_ssh=None, auth_info=Tenant.get('admin'),
                  use_telnet=False, con_telnet=None):
    """
    Delete active alarms_and_events

    Args:
        alarms (list|str): UUID(s) of alarms_and_events to delete
        fail_ok (bool): whether or not to raise exception if any alarm failed to delete
        con_ssh (SSHClient):
        auth_info (dict):
        use_telnet
        con_telnet

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
        code, out = cli.fm('alarm-delete', alarm, ssh_client=con_ssh, auth_info=auth_info, rtn_list=True,
                           use_telnet=use_telnet, con_telnet=con_telnet)
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
                        use_telnet=False, con_telnet=None, fail_ok=False, con_ssh=None,
                        auth_info=Tenant.get('admin')):
    """
    Wait for given alarm to disappear from fm alarm-list
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
        use_telnet
        con_telnet

    Returns (bool): True if alarm is gone else False

    """

    LOG.info("Waiting for alarm {} to disappear from fm alarm-list".format(alarm_id))
    build_ver = get_system_software_version(con_ssh=con_ssh, use_telnet=use_telnet,
                                            con_telnet=con_telnet)

    alarmcmd = 'alarm-list'
    if build_ver != '15.12':
        alarmcmd += ' --nowrap'

    end_time = time.time() + timeout
    while time.time() < end_time:
        alarms_tab = table_parser.table(cli.fm(alarmcmd, ssh_client=con_ssh, auth_info=auth_info,
                                               use_telnet=use_telnet, con_telnet=con_telnet))
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
                    LOG.info("Alarm {} with {} is not displayed in fm alarm-list".format(alarm_id, kwargs))
                    return True

        else:
            LOG.info("Alarm {} is not displayed in fm alarm-list".format(alarm_id))
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
                   check_interval=3, regex=False, strict=False, fail_ok=False, con_ssh=None,
                   auth_info=Tenant.get('admin'), use_telnet=False, con_telnet=None):
    """
    Wait for given alarm to appear
    Args:
        rtn_val:
        alarm_id (str): such as 200.009
        entity_id (str|list|tuple): entity instance id for the alarm (strict as defined in param)
        reason (str): reason text for the alarm (strict as defined in param)
        severity (str): severity of the alarm to wait for
        timeout (int): max seconds to wait for alarm to appear
        check_interval (int): how frequent to check
        regex (bool): whether to use regex when matching entity instance id and reason
        strict (bool): whether to perform strict match on entity instance id and reason
        fail_ok (bool): whether to raise exception if alarm did not disappear within timeout
        con_ssh (SSHClient):
        auth_info (dict):
        use_telnet
        con_telnet

    Returns (tuple): (<res_bool>, <rtn_val>). Such as (True, '200.009') or (False, None)

    """

    kwargs = {}
    if alarm_id:
        kwargs['Alarm ID'] = alarm_id
    if reason:
        kwargs['Reason Text'] = reason
    if severity:
        kwargs['Severity'] = severity

    if entity_id and isinstance(entity_id, str):
        entity_id = [entity_id]

    end_time = time.time() + timeout
    while time.time() < end_time:
        current_alarms_tab = get_alarms_table(con_ssh=con_ssh, auth_info=auth_info,
                                              use_telnet=use_telnet, con_telnet=con_telnet)
        if kwargs:
            current_alarms_tab = table_parser.filter_table(table_=current_alarms_tab, strict=strict, regex=regex,
                                                           **kwargs)
        if entity_id:
            val = []
            for entity in entity_id:
                entity_filter = {'Entity ID': entity}
                val_ = table_parser.get_values(current_alarms_tab, rtn_val, strict=strict, regex=regex, **entity_filter)
                if not val_:
                    LOG.info("Alarm for entity {} has not appeared".format(entity))
                    time.sleep(check_interval)
                    continue
                val += val_
        else:
            val = table_parser.get_values(current_alarms_tab, rtn_val)

        if val:
            LOG.info('Expected alarm appeared. Filters: {}'.format(kwargs))
            return True, val

        time.sleep(check_interval)

    entity_str = ' for entity {}'.format(entity_id) if entity_id else ''
    err_msg = "Alarm {}{} did not appear in fm alarm-list within {} seconds".format(kwargs, entity_str, timeout)
    if fail_ok:
        LOG.warning(err_msg)
        return False, None

    raise exceptions.TimeoutException(err_msg)


def wait_for_alarms_gone(alarms, timeout=120, check_interval=3, fail_ok=False, con_ssh=None,
                         auth_info=Tenant.get('admin'), use_telnet=False, con_telnet=None):
    """
    Wait for given alarms_and_events to be gone from fm alarm-list
    Args:
        alarms (list): list of tuple. [(<alarm_id1>, <entity_id1>), ...]
        timeout (int):
        check_interval (int):
        fail_ok (bool):
        con_ssh (SSHClient):
        auth_info (dict):
        use_telnet
        con_telnet

    Returns (tuple): (res(bool), remaining_alarms(list of tuple))

    """
    pre_alarms = list(alarms)   # Don't update the original list
    LOG.info("Waiting for alarms_and_events to disappear from fm alarm-list: {}".format(pre_alarms))
    alarms_to_check = pre_alarms.copy()

    alarms_cleared = []

    def _update_alarms(alarms_to_check_, alarms_cleared_):
        current_alarms_tab = get_alarms_table(con_ssh=con_ssh, auth_info=auth_info,
                                              use_telnet=use_telnet, con_telnet=con_telnet)
        current_alarms = _get_alarms(current_alarms_tab)

        for alarm in pre_alarms:
            if alarm not in current_alarms:
                LOG.info("Removing alarm {} from current alarms_and_events list: {}".format(alarm, alarms_to_check))
                alarms_to_check_.remove(alarm)
                alarms_cleared_.append(alarm)

    _update_alarms(alarms_to_check_=alarms_to_check, alarms_cleared_=alarms_cleared)
    if not alarms_to_check:
        LOG.info("Following alarms_and_events cleared: {}".format(alarms_cleared))
        return True, []

    end_time = time.time() + timeout
    while time.time() < end_time:
        pre_alarms = alarms_to_check.copy()
        time.sleep(check_interval)
        _update_alarms(alarms_to_check_=alarms_to_check, alarms_cleared_=alarms_cleared)
        if not alarms_to_check:
            LOG.info("Following alarms_and_events cleared: {}".format(alarms_cleared))
            return True, []
    else:
        err_msg = "Following alarms_and_events did not clear within {} seconds: {}".format(timeout, alarms_to_check)
        if fail_ok:
            LOG.warning(err_msg)
            return False, alarms_to_check
        else:
            raise exceptions.TimeoutException(err_msg)


def wait_for_all_alarms_gone(timeout=120, check_interval=3, fail_ok=False, con_ssh=None,
                             auth_info=Tenant.get('admin'), use_telnet=False, con_telnet=None):
    """
    Wait for all alarms_and_events to be cleared from fm alarm-list
    Args:
        timeout (int):
        check_interval (int):
        fail_ok (bool):
        con_ssh (SSHClient):
        auth_info (dict):
        use_telnet
        con_telnet

    Returns (tuple): (res(bool), remaining_alarms(tuple))

    """

    LOG.info("Waiting for all existing alarms_and_events to disappear from fm alarm-list: {}".format(get_alarms()))

    end_time = time.time() + timeout
    while time.time() < end_time:
        current_alarms_tab = get_alarms_table(con_ssh=con_ssh, auth_info=auth_info,
                                              use_telnet=use_telnet, con_telnet=con_telnet)
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


def modify_system(fail_ok=True, con_ssh=None, auth_info=Tenant.get('admin'), **kwargs):
    """
    Modify the System configs/info.

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

    attr_values_ = ['--{}="{}"'.format(attr, value) for attr, value in kwargs.items()]
    args_ = ' '.join(attr_values_)

    code, output = cli.system('modify', args_, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok, rtn_list=True)

    if code == 1:
        return 1, output

    return 0, ''


def get_system_value(field='name', auth_info=Tenant.get('admin'), con_ssh=None, use_telnet=False, con_telnet=None):

    table_ = table_parser.table(cli.system('show', ssh_client=con_ssh, use_telnet=use_telnet, auth_info=auth_info,
                                           con_telnet=con_telnet))

    value = table_parser.get_value_two_col_table(table_, field=field)
    return value


def set_retention_period(period, name='metering_time_to_live', fail_ok=True, check_first=True, con_ssh=None,
                         auth_info=Tenant.get('admin')):
    """
    Sets the PM retention period
    Args:
        period (int): the length of time to set the retention period (in seconds)
        name
        fail_ok: True or False
        check_first: True or False
        con_ssh (SSHClient):
        auth_info (dict): could be Tenant.get('admin'),Tenant.TENANT1,Tenant.TENANT2

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
        retention = get_retention_period(name=name)
        if period == retention:
            msg = "The retention period is already set to {}".format(period)
            LOG.info(msg)
            return -1, msg

    section = 'database'
    if name in 'metering_time_to_live':
        skip("Ceilometer metering_time_to_live is no longer available in 'system service-parameter-list'")
        name = 'metering_time_to_live'
        service = 'ceilometer'
    elif name == 'alarm_history_time_to_live':
        service = 'aodh'
    elif name == 'event_time_to_live':
        service = 'panko'
    else:
        raise ValueError("Unknown name: {}".format(name))

    args = '{} {} {}={}'.format(service, section, name, period)
    code, output = cli.system('service-parameter-modify', args, auth_info=auth_info, ssh_client=con_ssh,
                              timeout=SysInvTimeout.RETENTION_PERIOD_MODIFY, fail_ok=fail_ok, rtn_list=True)

    if code == 1:
        return 1, output

    code, output = cli.system('service-parameter-apply', service, auth_info=auth_info, ssh_client=con_ssh,
                              timeout=SysInvTimeout.RETENTION_PERIOD_MODIFY, fail_ok=fail_ok, rtn_list=True)
    if code == 1:
        return 2, output

    LOG.info("Start post check after applying new value for {}".format(name))
    new_retention = get_retention_period(name=name)

    if period != new_retention:
        err_msg = "Current retention period is still: {}".format(new_retention)
        if fail_ok:
            LOG.warning(err_msg)
            return 3, err_msg
        raise exceptions.CeilometerError(err_msg)

    conf_file = '/etc/{}/{}.conf'.format(service, service)
    wait_for_file_update(file_path=conf_file, grep_str=name, expt_val=period, fail_ok=False, ssh_client=con_ssh)

    return 0, "{} {} is successfully set to: {}".format(service, name, new_retention)


def wait_for_file_update(file_path, grep_str, expt_val, timeout=300, fail_ok=False, ssh_client=None):
    LOG.info("Wait for {} to be updated to {} in {}".format(grep_str, expt_val, file_path))
    if not ssh_client:
        ssh_client = ControllerClient.get_active_controller()

    pattern = '{}.*=(.*)'.format(grep_str)
    end_time = time.time() + timeout
    value = None
    while time.time() < end_time:
        output = ssh_client.exec_sudo_cmd('grep "^{}" {}'.format(grep_str, file_path), fail_ok=False)[1]
        value = int((re.findall(pattern, output)[0]).strip())
        if expt_val == value:
            return True, value
        time.sleep(5)

    msg = "Timed out waiting for {} to reach {} in {}. Actual: {}".format(grep_str, expt_val, file_path, value)
    if fail_ok:
        LOG.warning(msg)
        return False, value
    raise exceptions.SysinvError(msg)


def get_retention_period(name='metering_time_to_live', con_ssh=None):
    """
    Returns the current retention period
    Args:
        name (str): choose from: metering_time_to_live, event_time_to_live, alarm_history_time_to_live
        con_ssh (SSHClient):

    Returns (int): Current PM retention period

    """
    if name == 'metering_time_to_live':
        skip("Ceilometer metering_time_to_live no longer exists")
    ret_per = get_service_parameter_values(name=name, rtn_value='value', con_ssh=con_ssh)[0]
    return int(ret_per)


def get_dns_servers(auth_info=Tenant.get('admin'), con_ssh=None):
    """
    Get the DNS servers currently in-use in the System

    Args:
        auth_info(dict)
        con_ssh

    Returns (list): a list of DNS servers will be returned

    """
    table_ = table_parser.table(cli.system('dns-show', ssh_client=con_ssh, auth_info=auth_info))
    dns_servers = table_parser.get_value_two_col_table(table_, 'nameservers').strip().split(sep=',')

    region = ''
    if isinstance(auth_info, dict):
        region = auth_info.get('region', None)
        region = ' for {}'.format(region) if region else ''
    LOG.info('Current dns servers{}: {}'.format(region, dns_servers))
    return dns_servers


def set_dns_servers(nameservers, with_action_option=None, check_first=True, fail_ok=True, con_ssh=None,
                    auth_info=Tenant.get('admin'), ):
    """
    Set the DNS servers

    Args:
        fail_ok:
        check_first
        con_ssh:
        auth_info:
        nameservers (list|tuple): list of IP addresses (in plain text) of new DNS servers to change to
        with_action_option: whether invoke the CLI with or without "action" option
                            - None      no "action" option at all
                            - install   system dns-modify <> action=install
                            - anystr    system dns-modify <> action=anystring...
    Returns (tuple):
        (-1, <dns_servers>)
        (0, <dns_servers>)
        (1, <std_err>)

    """
    if not nameservers:
        raise ValueError("Please specify DNS server(s).")

    if check_first:
        dns_servers = get_dns_servers(con_ssh=con_ssh, auth_info=auth_info)
        if dns_servers == nameservers:
            msg = 'DNS servers already set to {}. Do nothing.'.format(dns_servers)
            LOG.info(msg)
            return -1, dns_servers

    args_ = 'nameservers="{}"'.format(','.join(nameservers))

    if with_action_option is not None:
        args_ += ' action={}'.format(with_action_option)

    LOG.info('args_:{}'.format(args_))
    code, output = cli.system('dns-modify', args_, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                              rtn_list=True, timeout=SysInvTimeout.DNS_MODIFY)
    if code == 1:
        return 1, output

    post_dns_servers = get_dns_servers(auth_info=auth_info, con_ssh=con_ssh)
    if post_dns_servers != nameservers:
        raise exceptions.SysinvError('dns servers expected: {}; actual: {}'.format(nameservers, post_dns_servers))

    LOG.info("DNS servers successfully updated to: {}".format(nameservers))
    return 0, nameservers


def get_vm_topology_tables(*table_names, con_ssh=None, combine_multiline=False, exclude_one_col_table=True,
                           auth_info=Tenant.get('admin')):
    if con_ssh is None:
        con_name = auth_info.get('region') if (auth_info and ProjVar.get_var('IS_DC')) else None
        con_ssh = ControllerClient.get_active_controller(name=con_name)

    show_args = ','.join(table_names)

    tables_ = table_parser.tables(con_ssh.exec_sudo_cmd('vm-topology --show {}'.
                                                        format(show_args), expect_timeout=30)[1],
                                  combine_multiline_entry=combine_multiline)

    if exclude_one_col_table:
        new_tables = []
        for table_ in tables_:
            if len(table_['headers']) > 1:
                new_tables.append(table_)
        return new_tables

    return tables_


def set_host_1g_pages(host, proc_id=0, hugepage_num=None, fail_ok=False, auth_info=Tenant.get('admin'), con_ssh=None):
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
            proc_id=proc_id, con_ssh=con_ssh, auth_info=auth_info)[int(proc_id)]

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

    code, output = cli.fm(cmd, '--alarm_id ' + alarm_id, ssh_client=con_ssh, rtn_list=True, fail_ok=fail_ok)

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


def set_host_4k_pages(host, proc_id=1, smallpage_num=None, fail_ok=False, auth_info=Tenant.get('admin'), con_ssh=None):
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
            proc_id=proc_id, con_ssh=con_ssh, auth_info=auth_info)[proc_id]

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


def get_host_mem_values(host, headers, proc_id=None, wait_for_update=True, con_ssh=None, auth_info=Tenant.get('admin'),
                        rtn_dict=True):
    """
    Get host memory values
    Args:
        host (str): hostname
        headers (list|tuple):
        proc_id (int|str|None|tuple|list): such as 0, '1'
        wait_for_update (bool): wait for vm_hp_pending_2M and vm_hp_pending_1G to be None (CGTS-7499)
        con_ssh (SSHClient):
        auth_info (dict):
        rtn_dict

    Returns (dict|list):  {<proc>(int): <mems>(list), ... } or [<proc0_mems>(list), <proc1_mems>(list), ...]
        e.g., {0: [62018, 1]}

    """

    cmd = 'host-memory-list --nowrap'
    table_ = table_parser.table(cli.system(cmd, host, ssh_client=con_ssh, auth_info=auth_info))

    if isinstance(proc_id, (str, int)):
        proc_id = [int(proc_id)]
    elif proc_id is None:
        proc_id = [int(proc) for proc in table_parser.get_column(table_, 'processor')]
    else:
        proc_id = [int(proc) for proc in proc_id]

    if wait_for_update:
        end_time = time.time() + 330
        while time.time() < end_time:
            pending_2m = [eval(mem) for mem in table_parser.get_column(table_, 'vm_hp_pending_2M')]
            pending_1g = [eval(mem) for mem in table_parser.get_column(table_, 'vm_hp_pending_1G')]

            for i in range(len(pending_2m)):
                if (pending_2m[i] is not None) or (pending_1g[i] is not None):
                    break
            else:
                LOG.debug("No pending 2M or 1G mem pages")
                break

            LOG.info("Pending 2M or 1G pages, wait for mem page to update")
            time.sleep(30)
            table_ = table_parser.table(cli.system(cmd, host, ssh_client=con_ssh, auth_info=auth_info))
        else:
            raise exceptions.SysinvError("Pending 2M or 1G pages after 5 minutes")

    res = {}
    res_list = []
    for proc in sorted(proc_id):
        vals = []
        for header in headers:
            value = table_parser.get_values(table_, header, strict=False, **{'processor': str(proc)})[0]
            try:
                value = eval(value)
            finally:
                vals.append(value)
        if rtn_dict:
            res[proc] = vals
        else:
            res_list.append(vals)

    if rtn_dict:
        return res
    else:
        return res_list


def get_host_used_mem_values(host, proc_id=0, auth_info=Tenant.get('admin'), con_ssh=None):
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
        proc_id=proc_id, con_ssh=con_ssh, auth_info=auth_info)[int(proc_id)]

    mem_total, mem_avail, avs_hp_size, avs_hp_total = [int(val) for val in mem_vals]

    used_mem = mem_total - mem_avail - avs_hp_size * avs_hp_total

    return used_mem


def get_processors_shared_cpu_nums(host, con_ssh=None, auth_info=Tenant.get('admin')):
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

    table_ = table_parser.table(cli.system(cmd, ssh_client=con_ssh, fail_ok=False, auth_info=Tenant.get('admin'),
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
#     code, output = cli.system(cmd, ssh_client=con_ssh, fail_ok=fail_ok, rtn_list=True, auth_info=Tenant.get('admin'))
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

    cli.system(cmd, ssh_client=con_ssh, fail_ok=False, auth_info=Tenant.get('admin'), rtn_list=False)


def get_host_cpu_list_table(host, con_ssh=None, auth_info=Tenant.get('admin')):
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


def get_host_mem_list(host, con_ssh=None, auth_info=Tenant.get('admin')):
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


def get_host_cpu_show_table(host, proc_num, con_ssh=None, auth_info=Tenant.get('admin')):
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


def get_host_memory_table(host, proc_num, con_ssh=None, auth_info=Tenant.get('admin')):
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
                          regex=False, con_ssh=None, auth_info=Tenant.get('admin'), **kwargs):
    """
    Get
    Args:
        host:
        header (str|list):
        if_name:
        pci_addr:
        proc:
        dev_type:
        strict:
        regex:
        con_ssh:
        auth_info:
        **kwargs:

    Returns (list|dict): list if header is string, dict if header is list.

    """
    table_ = table_parser.table(cli.system('host-port-list --nowrap', host, ssh_client=con_ssh, auth_info=auth_info))

    args_tmp = {
        'name': if_name,
        'pci address': pci_addr,
        'processor': proc,
        'device_type': dev_type
    }

    for key, value in args_tmp.items():
        if value is not None:
            kwargs[key] = value

    rtn_dict = True
    if isinstance(header, str):
        rtn_dict = False
        header = [header]

    table_ = table_parser.filter_table(table_, strict=strict, regex=regex, **kwargs)
    res = {}
    for header_ in header:
        vals = table_parser.get_column(table_, header_)
        res[header_] = vals

    if not rtn_dict:
        res = res[header[0]]

    return res


def get_host_interfaces_table(host, show_all=False, con_ssh=None, use_telnet=False, con_telnet=None,
                              auth_info=Tenant.get('admin')):
    """
    Get system host-if-list <host> table
    Args:
        host (str):
        show_all (bool):
        con_ssh (SSHClient):
        auth_info (dict):
        use_telnet
        con_telnet

    Returns (dict):

    """
    args = ''
    args += ' --a' if show_all else ''
    args += ' ' + host

    table_ = table_parser.table(cli.system('host-if-list --nowrap', args, ssh_client=con_ssh,
                                           use_telnet=use_telnet, con_telnet=con_telnet,
                                           auth_info=auth_info))
    return table_


def get_host_interfaces(host, rtn_val='name', net_type=None, if_type=None, uses_ifs=None, used_by_ifs=None,
                        show_all=False, strict=True, regex=False, con_ssh=None, auth_info=Tenant.get('admin'),
                        exclude=False, **kwargs):
    """
    Get specified interfaces info for given host via system host-if-list

    Args:
        host (str):
        rtn_val (str|tuple): header for return info
        net_type (str|list|tuple): valid values: 'oam', 'data', 'infra', 'mgmt', 'None'(string instead of None type)
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

    Returns (list):

    """
    table_ = get_host_interfaces_table(host=host, show_all=show_all, con_ssh=con_ssh, auth_info=auth_info)

    if isinstance(net_type, str):
        net_type = [net_type]
    networks = if_classes = None
    if net_type is not None:
        networks = []
        if_classes = []
        for net in net_type:
            network = ''
            if_class = net
            if net in PLATFORM_NET_TYPES:
                if_class = 'platform'
                network = net
            networks.append(network)
            if_classes.append(if_class)

    args_tmp = {
        'class': if_classes,
        'type': if_type,
        'uses i/f': uses_ifs,
        'used by i/f': used_by_ifs
    }

    for key, value in args_tmp.items():
        if value is not None:
            kwargs[key] = value

    table_ = table_parser.filter_table(table_, strict=strict, regex=regex, exclude=exclude, **kwargs)

    # exclude the platform interface that does not have desired net_type
    if if_classes is not None and 'platform' in if_classes:
        platform_ifs = table_parser.get_values(table_, target_header='name', **{'class': 'platform'})
        for pform_if in platform_ifs:
            if_nets = get_host_if_show_values(host=host, interface=pform_if, fields='networks', con_ssh=con_ssh)[0]
            if_nets = [if_net.strip() for if_net in if_nets.split(sep=',')]
            if not (set(if_nets) & set(networks)):
                table_ = table_parser.filter_table(table_, strict=True, exclude=(not exclude), name=pform_if)

    convert = False
    if isinstance(rtn_val, str):
        rtn_val = [rtn_val]
        convert = True

    vals = []
    for header in rtn_val:
        values = table_parser.get_column(table_, header=header)
        if header in ['ports', 'used by i/f', 'uses i/f']:
            values = [eval(item) for item in values]
        vals.append(values)

    if convert:
        vals = vals[0]
    elif len(vals) > 1:
        vals = list(zip(*vals))

    return vals


def get_host_ports_for_net_type(host, net_type='data', ports_only=True, con_ssh=None, auth_info=Tenant.get('admin')):
    """

    Args:
        host:
        net_type:
        ports_only: whether to include dev_name as well
        con_ssh:
        auth_info:

    Returns (list):

    """
    table_ = get_host_interfaces_table(host=host, con_ssh=con_ssh, auth_info=auth_info)
    table_origin = copy.deepcopy(table_)
    if net_type:
        if_class = net_type
        network = ''
        if net_type in PLATFORM_NET_TYPES:
            if_class = 'platform'
            network = net_type

        table_ = table_parser.filter_table(table_, **{'class': if_class})
        # exclude unmatched platform interfaces from the table.
        if 'platform' == if_class:
            platform_ifs = table_parser.get_values(table_, target_header='name', **{'class': 'platform'})
            for pform_if in platform_ifs:
                if_nets = get_host_if_show_values(host=host, interface=pform_if, fields='networks', con_ssh=con_ssh)[0]
                if_nets = [if_net.strip() for if_net in if_nets.split(sep=',')]
                if network not in if_nets:
                    table_ = table_parser.filter_table(table_, strict=True, exclude=True, name=pform_if)

    net_ifs_names = table_parser.get_column(table_, 'name')
    total_ports = []
    for if_name in net_ifs_names:
        if_type = table_parser.get_values(table_, 'type', name=if_name)[0]
        if if_type == 'ethernet':
            ports = eval(table_parser.get_values(table_, 'ports', name=if_name)[0])
            dev_name = ports[0] if len(ports) == 1 else if_name
        else:
            dev_name = if_name
            ports = []
            uses_ifs = eval(table_parser.get_values(table_, 'uses i/f', name=if_name)[0])
            for use_if in uses_ifs:
                use_if_type = table_parser.get_values(table_origin, 'type', name=use_if)[0]
                if use_if_type == 'ethernet':
                    useif_ports = eval(table_parser.get_values(table_origin, 'ports', name=use_if)[0])
                else:
                    # uses if is ae
                    useif_ports = eval(table_parser.get_values(table_origin, 'uses i/f', name=use_if)[0])
                ports += useif_ports

            if if_type == 'vlan':
                vlan_id = table_parser.get_values(table_, 'vlan id', name=if_name)[0]
                if ports:
                    dev_name = ports[0] if len(ports) == 1 else uses_ifs[0]
                dev_name = '{}.{}'.format(dev_name, vlan_id)

        if ports_only:
            total_ports += ports
        else:
            total_ports.append((dev_name, sorted(ports)))

    LOG.info("{} {} network ports are: {}".format(host, net_type, total_ports))
    if ports_only:
        total_ports = list(set(total_ports))

    return total_ports


def get_host_port_pci_address(host, interface, con_ssh=None, auth_info=Tenant.get('admin')):
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


def get_host_port_pci_address_for_net_type(host, net_type='mgmt', rtn_list=True, con_ssh=None,
                                           auth_info=Tenant.get('admin')):
    """

    Args:
        host:
        net_type:
        rtn_list:
        con_ssh:
        auth_info:

    Returns (list):

    """
    ports = get_host_ports_for_net_type(host, net_type=net_type, ports_only=rtn_list, con_ssh=con_ssh,
                                        auth_info=auth_info)
    pci_addresses = []
    for port in ports:
        pci_address = get_host_port_pci_address(host, port, con_ssh=con_ssh, auth_info=auth_info)
        pci_addresses.append(pci_address)

    return pci_addresses


def get_host_mgmt_pci_address(host, con_ssh=None, auth_info=Tenant.get('admin')):
    """

    Args:
        host:
        con_ssh:
        auth_info:

    Returns:

    """
    from keywords.host_helper import get_hostshow_value
    mgmt_ip = get_hostshow_value(host=host, field='mgmt_ip', con_ssh=con_ssh, auth_info=auth_info)
    mgmt_ports = get_host_ifnames_by_address(host, address=mgmt_ip)
    pci_addresses = []
    for port in mgmt_ports:
        pci_address = get_host_port_pci_address(host, port, con_ssh=con_ssh, auth_info=auth_info)
        pci_addresses.append(pci_address)

    return


def get_host_if_show_values(host, interface, fields, con_ssh=None, auth_info=Tenant.get('admin')):
    args = "{} {}".format(host, interface)
    table_ = table_parser.table(cli.system('host-if-show', args, ssh_client=con_ssh, auth_info=auth_info))

    if isinstance(fields, str):
        fields = [fields]

    res = []
    for field in fields:
        res.append(table_parser.get_value_two_col_table(table_, field))

    return res


def get_hosts_interfaces_info(hosts, fields, con_ssh=None, auth_info=Tenant.get('admin'), strict=True,
                              **interface_filters):
    if isinstance(hosts, str):
        hosts = [hosts]

    res = {}
    for host in hosts:
        interfaces = get_host_interfaces(host, rtn_val='name', strict=strict, **interface_filters)
        host_res = {}
        for interface in interfaces:
            values = get_host_if_show_values(host, interface, fields=fields, con_ssh=con_ssh, auth_info=auth_info)
            host_res[interface] = values

        res[host] = host_res

    return res


def get_host_ethernet_port_table(host, con_ssh=None, use_telnet=False, con_telnet=None, auth_info=Tenant.get('admin')):
    """
    Get system host-if-list <host> table
    Args:
        host (str):
        con_ssh (SSHClient):
        auth_info (dict):
        use_telnet
        con_telnet

    Returns (dict):

    """
    args = ''
    args += ' ' + host

    table_ = table_parser.table(cli.system('host-ethernet-port-list --nowrap', args, ssh_client=con_ssh,
                                           use_telnet=use_telnet, con_telnet=con_telnet,
                                           auth_info=auth_info))
    return table_


def get_service_parameter_values(service=None, section=None, name=None, rtn_value='value', con_ssh=None):
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

    table_ = table_parser.table(cli.system('service-parameter-list --nowrap', ssh_client=con_ssh))
    return table_parser.get_values(table_, rtn_value, **kwargs)


def create_service_parameter(service, section, name, value, con_ssh=None, fail_ok=False,
                             check_first=True, modify_existing=True, verify=True, apply=False):
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
        verify: this enables to skip the verification. sometimes not all values are displayed in the
                 service-parameter-list, ex password
        apply (bool): whether to apply service parameter after add

    Returns (tuple): (rtn_code, err_msg or param_uuid)

    """
    if check_first:
        val = get_service_parameter_values(service=service, section=section, name=name, con_ssh=con_ssh)
        if val:
            val = val[0]
            msg = "The service parameter {} {} {} already exists. value: {}".format(service, section, name, val)
            LOG.info(msg)
            if value != val and modify_existing:
                return modify_service_parameter(service, section, name, value, create=False, apply=apply,
                                                con_ssh=con_ssh, fail_ok=fail_ok, check_first=False, verify=verify)
            return -1, msg

    LOG.info("Creating service parameter")
    args = service + ' ' + section + ' ' + name + '=' + value
    res, out = cli.system('service-parameter-add', args, ssh_client=con_ssh, fail_ok=fail_ok, rtn_list=True)

    if res == 1:
        return 1, out

    LOG.info("Verifying the service parameter value")
    val = get_service_parameter_values(service=service, section=section, name=name, con_ssh=con_ssh)[0]
    value = value.strip('\"')
    if verify:
        if val != value:
            msg = 'The service parameter was not added with the correct value {} to {}'.format(val, value)
            if fail_ok:
                return 2, msg
            raise exceptions.SysinvError(msg)
    LOG.info("Service parameter was added with the correct value")
    uuid = get_service_parameter_values(rtn_value='uuid', service=service, section=section, name=name,
                                        con_ssh=con_ssh)[0]
    if apply:
        apply_service_parameters(service, wait_for_config=True, con_ssh=con_ssh)

    return 0, uuid


def modify_service_parameter(service, section, name, value, apply=False, con_ssh=None, fail_ok=False,
                             check_first=True, create=True, verify=True):
    """
    Modify a service parameter
    Args:
        service (str): Required
        section (str): Required
        name (str): Required
        value (str): Required
        apply
        con_ssh:
        fail_ok:
        check_first (bool): Check if the parameter exists first
        create (bool): Whether to create the parameter if it does not exist
        verify: this enables to skip the verification. sometimes not all values are displayed in the
                 service-parameter-list, ex password

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

    auth_info = dict(Tenant.get('admin'))
    if service == 'identity' and section == 'config' and name == 'token_expiration':
        auth_info['region'] = 'RegionOne'
    res, out = cli.system('service-parameter-modify', args, ssh_client=con_ssh, fail_ok=fail_ok, rtn_list=True,
                          auth_info=auth_info)

    if res == 1:
        return 1, out

    LOG.info("Verifying the service parameter value")
    val = get_service_parameter_values(service=service, section=section, name=name, con_ssh=con_ssh)[0]
    value = value.strip('\"')
    if verify:
        if val != value:
            msg = 'The service parameter was not modified to the correct value'
            if fail_ok:
                return 2, msg
            raise exceptions.SysinvError(msg)
    msg = "Service parameter modified to {}".format(val)
    LOG.info(msg)

    if apply:
        apply_service_parameters(service, wait_for_config=True, con_ssh=con_ssh, auth_info=auth_info)

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


def apply_service_parameters(service, wait_for_config=True, timeout=300, con_ssh=None, auth_info=Tenant.get('admin'),
                             fail_ok=False):
    """
    Apply service parameters
    Args:
        service (str): Required
        wait_for_config (bool): Wait for config out of date alarms to clear
        timeout (int):
        con_ssh:
        auth_info
        fail_ok:

    Returns (tuple): (rtn_code, message)

    """
    LOG.info("Applying service parameters {}".format(service))
    res, out = cli.system('service-parameter-apply', service, rtn_list=True, fail_ok=fail_ok, auth_info=auth_info,
                          ssh_client=con_ssh)

    if res == 1:
        return res, out

    alarm_id = '250.001'
    time.sleep(10)

    if wait_for_config:
        LOG.info("Waiting for config-out-of-date alarms to clear. "
                 "There may be cli errors when active controller's config updates")
        end_time = time.time() + timeout
        while time.time() < end_time:
            table_ = get_alarms_table(uuid=True, con_ssh=con_ssh, retry=3)
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


def are_hosts_unlocked(con_ssh=None, auth_info=Tenant.get('admin')):

    table_ = table_parser.table(cli.system('host-list', ssh_client=con_ssh, auth_info=auth_info))
    return "locked" not in (table_parser.get_column(table_, 'administrative'))


def get_system_health_query_upgrade(con_ssh=None):
    """
    Queries the  health of a system in use.
    Args:
        con_ssh:

    Returns: tuple
        (0, None, None) - success - all heath checks are OK.
        (1, dict(error msg), None ) -  health query reported 1 or more failures with no recommmended actions.
        (2, dict(error msg), dict(actions) -  health query reported failures with recommended actions to resolve failure
    """

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
            elif "Hosts missing placement configuration" in k:
                failed[k.strip()] = v.strip()
            elif "Incomplete configuration" in k:
                failed[k.strip()] = v.strip()
            elif "Locked or disabled hosts" in k:
                failed[k.strip()] = v.strip()
        elif "Missing manifests" in line:
            failed[line] = line
        elif "alarms found" in line:
            if len(line.split(',')) > 1:
                failed["management affecting"] = int(line.split(',')[1].strip()[1])

    if len(failed) == 0:
        LOG.info("system health is OK to start upgrade......")
        return 0, None,  None

    actions = {"lock_unlock": [[], ''],
               "force_upgrade": [False, ''],
               "swact": [False, ''],
               }

    for k, v in failed.items():
        if "No alarms" in k:
            # alarms = True
            table_ = table_parser.table(cli.fm('alarm-list --uuid'))
            alarm_severity_list = table_parser.get_column(table_, "Severity")
            if len(alarm_severity_list) > 0 \
                    and "major" not in alarm_severity_list \
                    and "critical" not in alarm_severity_list:
                # minor alarm present
                LOG.warn("System health query upgrade found minor alarms: {}".format(alarm_severity_list))
                actions["force_upgrade"] = [True, "Minor alarms present"]

        elif "management affecting" in k:
            if v == 0:
                # non management affecting alarm present  use  foce upgrade
                LOG.warning("System health query upgrade found non management affecting alarms: {}".format(k))
                actions["force_upgrade"] = [True, "Non management affecting  alarms present"]

            else:
                # major/critical alarm present,  management affecting
                LOG.error("System health query upgrade found major or critical alarms.")
                return 1, failed, None

        elif "Missing manifests" in k:
            # manifest = True

            if "controller-1" in k:
                if "controller-1" not in actions["lock_unlock"][0]:
                    actions["lock_unlock"][0].append("controller-1")
            if "controller-0" in k:
                if "controller-0" not in actions["lock_unlock"][0]:
                    actions["lock_unlock"][0].append("controller-0")

            actions["lock_unlock"][1] += "Missing manifests;"

        elif any(s in k for s in ("Cinder configuration", "Incomplete configuration")):
            # cinder_config = True
            actions["swact"] = [True, actions["swact"][1] + "Invalid Cinder configuration;"]

        elif "Placement Services Enabled" in k or "Hosts missing placement configuration" in k:
            # placement_services = True
            if "controller-1" in v:
                if "controller-1" not in actions["lock_unlock"][0]:
                    actions["lock_unlock"][0].append("controller-1")
            if "controller-0" in v:
                if "controller-0" not in actions["lock_unlock"][0]:
                    actions["lock_unlock"][0].append("controller-0")
            actions["lock_unlock"][1] += "Missing placement configuration;"
        else:
            err_msg = "System health query upgrade failed: {}".format(failed)
            LOG.error(err_msg)
            return 1, failed,  None

    return 2, failed, actions


def get_system_health_query(con_ssh=None):

    output = (cli.system('health-query', ssh_client=con_ssh, source_openrc=True, fail_ok=False)).splitlines()
    failed = []
    for line in output:
        if "[Fail]" in line:
            failed_item = line.split(sep=': ')[0]
            failed.append(failed_item.strip())

    if failed:
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
    upgrade_state = None
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


def get_installed_build_info_dict(con_ssh=None, use_telnet=False, con_telnet=None):

    build_info_dict = {}
    build_info = get_buildinfo(con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet)
    pattern = re.compile('(.*)="(.*)"')
    for line in build_info.splitlines():
        res = pattern.match(line)
        if res:
            key, val = res.groups()
            build_info_dict[key.strip()] = val.strip()

    return build_info_dict


def get_system_software_version(con_ssh=None, use_telnet=False, con_telnet=None, use_existing=True):
    """

    Args:
        con_ssh:
        use_telnet
        con_telnet
        use_existing

    Returns (str): e.g., 16.10

    """
    sw_versions = ProjVar.get_var('SW_VERSION')
    if use_existing and sw_versions:
        return sw_versions[-1]

    info_dict = get_installed_build_info_dict(con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet)
    sw_version = info_dict.get('SW_VERSION')
    if sw_version not in sw_versions:
        ProjVar.set_var(append=True, SW_VERSION=sw_version)

    return sw_version


def import_load(load_path, timeout=120, con_ssh=None, fail_ok=False, source_creden_=None, upgrade_ver=None):
    # TODO: Need to support remote_cli. i.e., no hardcoded load_path, etc
    if upgrade_ver >= '17.07':
        load_path = '/home/wrsroot/bootimage.sig'
        rc, output = cli.system('load-import /home/wrsroot/bootimage.iso ', load_path, ssh_client=con_ssh, fail_ok=True,
                                source_openrc=source_creden_)
    else:
        rc, output = cli.system('load-import', load_path, ssh_client=con_ssh, fail_ok=True,
                                source_openrc=source_creden_)
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
    table_ = table_parser.table(cli.system('load-list', ssh_client=con_ssh, source_openrc=source_creden_))
    if load_version:
        table_ = table_parser.filter_table(table_, state='imported', software_version=load_version)
    else:
        table_ = table_parser.filter_table(table_, state='imported')

    return table_parser.get_values(table_, 'id')[0]


def get_imported_load_state(load_id, load_version=None, con_ssh=None, source_creden_=None):
    table_ = table_parser.table(cli.system('load-list', ssh_client=con_ssh, source_openrc=source_creden_))
    if load_version:
        table_ = table_parser.filter_table(table_, id=load_id, software_version=load_version)
    else:
        table_ = table_parser.filter_table(table_, id=load_id)

    return (table_parser.get_values(table_, 'state')).pop()


def get_imported_load_version(con_ssh=None, source_creden_=None):
    table_ = table_parser.table(cli.system('load-list', ssh_client=con_ssh, source_openrc=source_creden_))
    table_ = table_parser.filter_table(table_, state='imported')

    return table_parser.get_values(table_, 'software_version')


def get_active_load_id(con_ssh=None, source_creden_=None):
    table_ = table_parser.table(cli.system('load-list', ssh_client=con_ssh, source_openrc=source_creden_))

    table_ = table_parser.filter_table(table_, state="active")
    return table_parser.get_values(table_, 'id')


def get_software_loads(rtn_vals=('id', 'state', 'software_version'), sw_id=None, state=None, software_version=None,
                       strict=False, con_ssh=None, source_creden_=None):

    table_ = table_parser.table(cli.system('load-list', ssh_client=con_ssh, source_openrc=source_creden_))

    kwargs_dict = {
        'id': sw_id,
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
                            fail_ok=True, source_openrc=source_creden_)
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
                                  auth_info=Tenant.get('admin')):

    LOG.info("Waiting for imported load  {} to be deleted from the load-list ".format(load_id))
    end_time = time.time() + timeout
    while time.time() < end_time:
        table_ = table_parser.table(cli.system('load-list', ssh_client=con_ssh, auth_info=auth_info))

        table_ = table_parser.filter_table(table_, **{'id': load_id})
        if len(table_parser.get_values(table_, 'id')) == 0:
            return True
        else:
            if 'deleting' in table_parser.get_column(table_, 'state'):
                cli.system('load-delete', load_id, ssh_client=con_ssh, fail_ok=True)
        time.sleep(check_interval)

    else:
        err_msg = "Timed out waiting for load {} to get deleted".format(load_id)
        if fail_ok:
            LOG.warning(err_msg)
            return False
        else:
            raise exceptions.TimeoutException(err_msg)


def install_license(license_path, timeout=30, con_ssh=None):

    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    cmd = "test -e {}".format(license_path)
    rc = con_ssh.exec_cmd(cmd, fail_ok=True)[0]

    if rc != 0:
        msg = "The {} file missing from active controller".format(license_path)
        return rc, msg

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


def install_upgrade_license(license_path, timeout=30, con_ssh=None):
    return install_license(license_path, timeout=timeout, con_ssh=con_ssh)


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


def get_controller_fs_values(con_ssh=None, auth_info=Tenant.get('admin')):

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
    service_list_tab = None
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


def is_infra_network_configured(con_ssh=None, auth_info=Tenant.get('admin')):
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
    output = cli.system('infra-show', ssh_client=con_ssh, auth_info=auth_info)
    if "Infrastructure network not configured" in output:
        return False,  None
    table_ = table_parser.table(output)
    rows = table_parser.get_all_rows(table_)
    values = {}
    for row in rows:
        values[row[0].strip()] = row[1].strip()
    return True, values


def add_infra_network(infra_network_cidr=None, con_ssh=None, auth_info=Tenant.get('admin')):
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


def enable_murano(con_ssh=None, auth_info=Tenant.get('admin'), fail_ok=False):
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


def disable_murano(con_ssh=None, auth_info=Tenant.get('admin'), fail_ok=False):
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

    msg = "Disabled Murano Service"

    return 0, msg


def get_host_ifnames_by_address(host, rtn_val='ifname', address=None, id_=None, fail_ok=False, con_ssh=None,
                                auth_info=Tenant.get('admin')):
    """
    Get the host ifname by address.
    Args:
        host
        con_ssh (SSHClient):
        address:
        id_:
        rtn_val:
        auth_info (dict):
        fail_ok: whether return False or raise exception when some services fail to reach enabled-active state

    Returns (list):

    """

    table_ = table_parser.table(cli.system('host-addr-list', host,  ssh_client=con_ssh, auth_info=auth_info,
                                fail_ok=fail_ok, rtn_list=True)[1])
    args_dict = {
        'uuid': id_,
        'address': address,
    }
    kwargs = {}
    for key, value in args_dict.items():
        if value:
            kwargs[key] = value

    ifnames = table_parser.get_values(table_, rtn_val, strict=True, regex=True, merge_lines=True, **kwargs)
    return ifnames


def get_host_addr_list(host, rtn_val='address', ifname=None, id_=None, con_ssh=None, auth_info=Tenant.get('admin'),
                       fail_ok=False):
    """
    Disable Murano Services
    Args:
        host
        con_ssh (SSHClient):
        ifname:
        id_:
        rtn_val:
        auth_info (dict):
        fail_ok: whether return False or raise exception when some services fail to reach enabled-active state

    Returns:

    """

    table_ = table_parser.table(cli.system('host-addr-list', host,  ssh_client=con_ssh, auth_info=auth_info,
                                fail_ok=fail_ok, rtn_list=True)[1])
    args_dict = {
        'id': id_,
        'ifname': ifname,
    }
    kwargs = {}
    for key, value in args_dict.items():
        if value:
            kwargs[key] = value

    address = table_parser.get_values(table_, rtn_val, strict=True, regex=True, merge_lines=True, **kwargs)
    return address


def get_host_disks_table(host, con_ssh=None, use_telnet=False, con_telnet=None, auth_info=Tenant.get('admin')):
    """
    Get system host-disk-list <host> table
    Args:
        host (str):
        con_ssh (SSHClient):
        use_telnet
        con_telnet
        auth_info (dict):

    Returns (dict):

    """
    args = ''
    args += ' ' + host

    table_ = table_parser.table(cli.system('host-disk-list --nowrap', args, ssh_client=con_ssh,
                                           use_telnet=use_telnet, con_telnet=con_telnet,
                                           auth_info=auth_info))
    return table_


def get_network_values(header='uuid', uuid=None, ntype=None, mtu=None, link_capacity=None,  dynamic=None, vlan=None,
                       pool_uuid=None, auth_info=Tenant.get('admin'), con_ssh=None,  strict=True, regex=None, **kwargs):
    """
    Get
    Args:
        header: 'uuid' (default)
        uuid:
        ntype: (mapped as ntype)
        mtu:
        link_capacity:
        dynamic:
        vlan:
        pool_uuid:
        auth_info:
        con_ssh:
        strict:
        regex:
        **kwargs:

    Returns (list):
    """
    table_ = table_parser.table(cli.system('network-list', 
                                           ssh_client=con_ssh, 
                                           auth_info=auth_info))
    args_temp = {
        'uuid': uuid,
        'ntype': ntype,
        'mtu': mtu,
        'link-capacity': link_capacity,
        'dynamic': dynamic,
        'vlan': vlan,
        'pool_uuid': pool_uuid
    }
    for key, value in args_temp.items():
        if value is not None:
            kwargs[key] = value
    return table_parser.get_values(table_, header, strict=strict, regex=regex, **kwargs)


def get_cluster_values(header='uuid', uuid=None, cluster_uuid=None, ntype=None, name=None,
                       auth_info=Tenant.get('admin'), con_ssh=None, strict=True, regex=None, **kwargs):
    """
    Get cluster values from system cluster-list
    Args:
        header: 'uuid' (default)
        uuid:
        cluster_uuid:
        ntype: (mapped as ntype)
        name:
        auth_info:
        con_ssh:
        strict:
        regex:
        **kwargs:

    Returns (list):

    """
    table_ = table_parser.table(cli.system('cluster-list', ssh_client=con_ssh, auth_info=auth_info))
    args_temp = {
        'uuid': uuid,
        'cluster_uuid': cluster_uuid,
        'ntype': ntype,
        'name': name,
    }
    for key, value in args_temp.items():
        if value is not None:
            kwargs[key] = value
    return table_parser.get_values(table_, header, strict=strict, regex=regex, **kwargs)


def get_disk_values(host, header='uuid', uuid=None, device_node=None, device_num=None,
                    device_type=None, size_gib=None,
                    available_gib=None, rpm=None, serial_id=None,
                    device_path=None, auth_info=Tenant.get('admin'),
                    con_ssh=None, strict=True, regex=None,
                    **kwargs):
    """
    Get disk values from system host-disk-list
    Args:
        host: (mandatory)
        header: 'uuid' (default value)
        uuid: 
        device_node:
        device_num:
        device_type:
        size_gib:
        available_gib:
        rpm:
        serial_id:
        device_path:
        auth_info:
        con_ssh:
        strict:
        regex:
        **kwargs:

    Returns (list):

    """
    table_ = table_parser.table(cli.system('host-disk-list ' + host,
                                           ssh_client=con_ssh,
                                           auth_info=auth_info))
    args_temp = {
        'uuid': uuid,
        'device_node': device_node,
        'device_num': device_num,
        'device_type': device_type,
        'size_gib': size_gib,
        'available_gib': available_gib,
        'rpm': rpm,
        'serial_id': serial_id,
        'device_path': device_path
    }
    for key, value in args_temp.items():
        if value is not None:
            kwargs[key] = value
    return table_parser.get_values(table_, header, strict=strict, regex=regex, **kwargs)


def get_host_lldp_agent_table(host, header='uuid', uuid=None, local_port=None, status=None, chassis_id=None,
                              port_id=None, system_name=None, system_description=None, auth_info=Tenant.get('admin'),
                              con_ssh=None, strict=True, regex=None, **kwargs):
    """
    Get lldp agent table via system host-lldp-agent-list <host>
    Args:
        host: (mandatory)
        header: 'uuid' (default)
        uuid:
        local_port:
        status:
        chassis_id:
        port_id:
        system_name:
        system_description:
        auth_info:
        con_ssh:
        strict:
        regex:
        **kwargs:

    Returns (list):

    """
    table_ = table_parser.table(cli.system('host-lldp-agent-list ' + host, ssh_client=con_ssh, auth_info=auth_info))

    args_temp = {
        'uuid': uuid,
        'local_port': local_port,
        'status': status,
        'chassis_id': chassis_id,
        'system_name': system_name,
        'system_description': system_description,
        'port_id': port_id,
    }
    for key, value in args_temp.items():
        if value is not None:
            kwargs[key] = value
    return table_parser.get_values(table_, header, strict=strict, regex=regex, **kwargs)


def get_host_lldp_neighbor_table(host, header='uuid', uuid=None, local_port=None, remote_port=None, chassis_id=None,
                                 management_address=None, system_name=None, system_description=None,
                                 auth_info=Tenant.get('admin'), con_ssh=None, strict=True, regex=None, **kwargs):
    """
    Get lldp neighbour table via system host-lldp-neighbor-list <host>
    Args:
        host (mandatory - make note of this)
        header: 'uuid' (default value)
        uuid:
        local_port:
        remote_port:
        chassis_id:
        management_address:
        system_name:
        system_description:
        auth_info:
        con_ssh:
        strict:
        regex:
        **kwargs:

    Returns (list):

    """
    table_ = table_parser.table(cli.system('host-lldp-neighbor-list ' + host,
                                           ssh_client=con_ssh,
                                           auth_info=auth_info))
    args_temp = {
        'uuid': uuid,
        'local_port': local_port,
        'remote_port': remote_port,
        'chassis_id': chassis_id,
        'system_name': system_name,
        'system_description': system_description,
        'management_address': management_address
    }
    for key, value in args_temp.items():
        if value is not None:
            kwargs[key] = value
    return table_parser.get_values(table_, header, strict=strict, regex=regex, **kwargs)


def get_service_list_table(header='id', service_id=None, service_name=None, hostname=None, state=None,
                           auth_info=Tenant.get('admin'), con_ssh=None, strict=True, regex=None, **kwargs):
    """
    Get service_list through service service-list command
    Args:
        header: 'id' (default value)
        service_id:
        service_name:
        hostname:
        state:
        auth_info:
        con_ssh:
        strict:
        regex:
        **kwargs:

    Returns (list):

    """
    table_ = table_parser.table(cli.system('service-list',
                                           ssh_client=con_ssh,
                                           auth_info=auth_info))
    args_temp = {
        'id': service_id,
        'service_name': service_name,
        'hostname': hostname,
        'state': state
    }
    for key, value in args_temp.items():
        if value is not None:
            kwargs[key] = value
    return table_parser.get_values(table_, header, strict=strict, regex=regex, **kwargs)


def get_servicenodes_list_table(header='id', servicenode_id=None, name=None, operational=None, availability=None,
                                ready_state=None, auth_info=Tenant.get('admin'), con_ssh=None, strict=True, regex=None,
                                **kwargs):
    """
    Get servicenodes list through service servicenode-list

    Args:
        header: 'id' (default)
        servicenode_id:
        name:
        operational:
        availability:
        ready_state:
        auth_info:
        con_ssh:
        strict:
        regex:
        **kwargs:

    Returns (list):

    """
    table_ = table_parser.table(cli.system('servicenode-list',
                                           ssh_client=con_ssh,
                                           auth_info=auth_info))
    args_temp = {
        'id': servicenode_id,
        'name': name,
        'operational': operational,
        'ready_state': ready_state,
        'availability': availability
    }
    for key, value in args_temp.items():
        if value is not None:
            kwargs[key] = value
    return table_parser.get_values(table_, header, strict=strict, regex=regex, **kwargs)


def get_servicegroups_list_table(header='uuid', uuid=None, service_group_name=None, hostname=None, state=None,
                                 auth_info=Tenant.get('admin'), con_ssh=None, strict=True, regex=None, **kwargs):
    """
    Get servicegroups list through service servicegroup-list command
    Args:
        header: 'uuid' (default)
        uuid:
        service_group_name:
        hostname:
        state:
        auth_info:
        con_ssh:
        strict:
        regex
        **kwargs:

    Returns (list):

    """
    table_ = table_parser.table(cli.system('servicegroup-list',
                                           ssh_client=con_ssh,
                                           auth_info=auth_info))
    args_temp = {
        'uuid': uuid,
        'service_group_name': service_group_name,
        'hostname': hostname,
        'state': state
    }
    for key, value in args_temp.items():
        if value is not None:
            kwargs[key] = value
    return table_parser.get_values(table_, header, strict=strict, regex=regex, **kwargs)


def create_snmp_comm(comm_string, rtn_val='uuid', fail_ok=False, con_ssh=None, auth_info=Tenant.get('admin')):
    """
    Create a new SNMP community string
    Args:
        comm_string (str): Community string to create
        rtn_val (str): property to return
        fail_ok (bool)
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (tuple):

    """
    args = '-c "{}"'.format(comm_string)
    code, out = cli.system('snmp-comm-add', args, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                           rtn_list=True)

    if code > 0:
        return 1, out

    val = table_parser.get_value_two_col_table(table_parser.table(out), field=rtn_val)

    return 0, val


def create_snmp_trapdest(comm_string, ip_addr, rtn_val='uuid', fail_ok=False, con_ssh=None,
                         auth_info=Tenant.get('admin')):
    """
    Create a new SNMP trap destination
    Args:
        comm_string (str): SNMP community string
        ip_addr (str): IP address of the trap destination
        rtn_val (str): property to return
        fail_ok (bool)
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (tuple):

    """
    args = '-c "{}" -i "{}"'.format(comm_string, ip_addr)
    code, out = cli.system('snmp-trapdest-add', args, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                           rtn_list=True)

    if code > 0:
        return 1, out

    val = table_parser.get_value_two_col_table(table_parser.table(out), field=rtn_val)

    return 0, val


def get_snmp_comms(con_ssh=None, auth_info=Tenant.get('admin')):
    """
    Get SNMP community strings
    Args:
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (list):

    """
    table_ = table_parser.table(cli.system('snmp-comm-list', ssh_client=con_ssh, auth_info=auth_info))

    return table_parser.get_values(table_, 'SNMP community')


def get_snmp_trapdests(rtn_val='IP Address', con_ssh=None, auth_info=Tenant.get('admin'), exclude_system=True,
                       **kwargs):
    """
    Get SNMP trap destination ips
    Args:
        rtn_val (str):
        con_ssh (SSHClient):
        auth_info (dict):
        exclude_system
        kwargs

    Returns (list):

    """
    table_ = table_parser.table(cli.system('snmp-comm-list', ssh_client=con_ssh, auth_info=auth_info))
    if exclude_system:
        table_ = table_parser.filter_table(table_, exclude=True, **{'SNMP Community': 'dcorchAlarmAggregator'})

    return table_parser.get_values(table_, rtn_val, **kwargs)


def delete_snmp_comm(comms, check_first=True, fail_ok=False, con_ssh=None, auth_info=Tenant.get('admin')):
    """
    Delete snmp community string
    Args:
        comms (str): Community string or uuid to delete
        check_first (bool)
        fail_ok (bool)
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (tuple):

    """
    if isinstance(comms, str):
        comms = comms.split(sep=' ')
    else:
        comms = list(comms)

    if check_first:
        current_comms = get_snmp_comms(con_ssh=con_ssh, auth_info=auth_info)
        comms = [comm for comm in comms if comm in current_comms]
        if not comms:
            msg = '"{}" SNMP community string does not exist. Do nothing.'.format(comms)
            LOG.info(msg)
            return -1, msg

    LOG.info('Deleting SNMP community strings: {}'.format(comms))
    comms = ' '.join(['"{}"'.format(comm) for comm in comms])
    code, out = cli.system('snmp-comm-delete', comms, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                           rtn_list=True)

    post_comms = get_snmp_comms(con_ssh=con_ssh, auth_info=auth_info)
    undeleted_comms = [comm for comm in comms if comm in post_comms]
    if undeleted_comms:
        raise exceptions.SysinvError("Community string still exist after deletion: {}".format(undeleted_comms))

    if code == 0:
        msg = 'SNMP community string "{}" is deleted successfully'.format(comms)
    else:
        msg = 'SNMP community string "{}" failed to delete'.format(comms)

    LOG.info(msg)
    return code, out


def delete_snmp_trapdest(ip_addrs, fail_ok=False, con_ssh=None, auth_info=Tenant.get('admin')):
    """
    Delete SNMP trap destination
    Args:
        ip_addrs (str|list): SNMP trap destination IP address(es)
        fail_ok (bool)
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (dict):

    """
    if isinstance(ip_addrs, str):
        ip_addrs = ip_addrs.split(sep=' ')

    arg = ''
    for ip_addr in ip_addrs:
        arg += '"{}" '.format(ip_addr)
    code, out = cli.system('snmp-trapdest-delete', arg, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                           rtn_list=True)

    return code, out


def get_oam_ips():
    LOG.info('In get_oam_ips.')
    table_ = table_parser.table(cli.system('oam-show'))
    oam_properties = table_parser.get_column(table_, 'Property')
    oam_values = table_parser.get_column(table_, 'Value')

    all_oam_ips_dict = {}
    for i in range(len(oam_properties)):
        oam_property = oam_properties[i]
        if oam_property == "oam_c0_ip":
            all_oam_ips_dict['oam_c0_ip'] = oam_values[i]
        if oam_property == "oam_c1_ip":
            all_oam_ips_dict['oam_c1_ip'] = oam_values[i]
        if oam_property == "oam_floating_ip":
            all_oam_ips_dict['oam_floating_ip'] = oam_values[i]

    return all_oam_ips_dict


def modify_oam_ips(arg_str, fail_ok=False):
    cmd = "oam-modify" + arg_str
    LOG.info('In modify_oam_ips. cmd:{}'.format(cmd))
    code, output = cli.system(cmd, rtn_list=True, fail_ok=fail_ok)
    if code != 0:
        return code, output

    msg = "OAM modified successfully."
    return 0, msg


def modify_spectre_meltdown_version(version='spectre_meltdown_all', check_first=True, con_ssh=None, fail_ok=False):
    """
    Modify spectre meltdown version
    Args:
        version (str): valid values: spectre_meltdown_v1, spectre_meltdown_all.
            Other values will be rejected by system modify cmd.
        check_first (bool):
        con_ssh:
        fail_ok (bool):

    Returns (tuple):
        (-1, "Security feature already set to <version>. Do nothing")
        (0, "System security_feature is successfully modified to: <version>")
        (1, <std_err>)

    """
    current_version = get_system_value(field='security_feature')
    if not current_version:
        skip('spectre_meltdown update feature is unavailable in current load')

    from keywords import host_helper
    hosts = get_hostnames(con_ssh=con_ssh)
    check_val = 'nopti nospectre_v2'
    if check_first and version == current_version:
        LOG.info("{} already set in 'system show'. Checking actual cmdline options on each host.".format(version))
        hosts_to_configure = []
        for host in hosts:
            cmdline_options = host_helper.get_host_cmdline_options(host=host)
            if 'v1' in version:
                if check_val not in cmdline_options:
                    hosts_to_configure.append(host)
            elif check_val in cmdline_options:
                hosts_to_configure.append(host)

        hosts = hosts_to_configure
        if not hosts_to_configure:
            msg = 'Security feature already set to {}. Do nothing.'.format(current_version)
            LOG.info(msg)
            return -1, msg

    LOG.info("Set spectre_meltdown version to {}".format(version))
    code, output = cli.system('modify -S {}'.format(version), ssh_client=con_ssh, fail_ok=fail_ok,
                              rtn_list=True)
    if code > 0:
        return 1, output

    conf_storage0 = False
    if 'storage-0' in hosts:
        hosts.remove('storage-0')
        conf_storage0 = True

    active_controller = get_active_controller_name(con_ssh=con_ssh)
    conf_active = False
    if active_controller in hosts:
        hosts.remove(active_controller)
        conf_active = True

    if hosts:
        LOG.info("Lock/unlock unconfigured hosts other than active controller: {}".format(hosts))
        try:
            for host in hosts:
                host_helper.lock_host(host=host, con_ssh=con_ssh)
        finally:
            host_helper.unlock_hosts(hosts=hosts, fail_ok=False, con_ssh=con_ssh)
            host_helper.wait_for_hosts_ready(hosts=hosts, con_ssh=con_ssh)

    if conf_storage0:
        LOG.info("Lock/unlock storage-0")
        try:
            host_helper.lock_host(host='storage-0', con_ssh=con_ssh)
        finally:
            host_helper.unlock_host(host='storage-0', con_ssh=con_ssh)

    if conf_active:
        LOG.info("Lock/unlock active controller (swact first if needed): {}".format(active_controller))
        try:
            host_helper.lock_host(host=active_controller, swact=True, con_ssh=con_ssh)
        finally:
            host_helper.unlock_host(host=active_controller, con_ssh=con_ssh)

    LOG.info("Check 'system show' is updated to {}".format(version))
    post_version = get_system_value(field='security_feature')
    assert version == post_version, 'Value is not {} after system modify'.format(version)

    LOG.info('Check cmdline options are updated on each host via /proc/cmdline')
    hosts.append(active_controller)
    for host in hosts:
        options = host_helper.get_host_cmdline_options(host=host)
        if 'v1' in version:
            assert check_val in options, '{} not in cmdline options after set to {}'.format(check_val, version)
        else:
            assert check_val not in options, '{} in cmdline options after set to {}'.format(check_val, version)

    msg = 'System spectre meltdown version is successfully modified to: {}'.format(version)
    LOG.info(msg)
    return 0, msg


def is_avs(con_ssh=None):
    vswitch_type = ProjVar.get_var('VSWITCH_TYPE')
    if vswitch_type is None:
        vswitch_type = get_system_value(field='vswitch_type', con_ssh=con_ssh)
        ProjVar.set_var(VSWITCH_TYPE=vswitch_type)
    return 'ovs' not in vswitch_type    # 'avs' or '' for avs; 'ovs-dpdk' for ovs.


def get_system_build_id(con_ssh=None, use_telnet=False, con_telnet=None,):
    """

    Args:
        con_ssh:
        use_telnet
        con_telnet

    Returns (str): e.g., 16.10

    """
    build_info = get_buildinfo(con_ssh=con_ssh, use_telnet=use_telnet, con_telnet=con_telnet,)
    build_line = [l for l in build_info.splitlines() if "BUILD_ID" in l]
    for line in build_line:
        if line.split("=")[0].strip() == 'BUILD_ID':
            return line.split("=")[1].strip().replace('"', '')
    else:
        return None


def get_controller_uptime(con_ssh):
    """
    Get uptime for all controllers. If no standby controller, then we only calculate for current active controller.
    Args:
        con_ssh

    Returns (int): in seconds
    """
    active_con, standby_con = get_active_standby_controllers(con_ssh=con_ssh)
    from keywords.host_helper import get_hostshow_value
    active_con_uptime = int(get_hostshow_value(host=active_con, field='uptime', con_ssh=con_ssh))

    con_uptime = active_con_uptime
    if standby_con:
        standby_con_uptime = int(get_hostshow_value(host=standby_con, field='uptime', con_ssh=con_ssh))
        con_uptime = min(active_con_uptime, standby_con_uptime)

    return con_uptime


def get_networks(rtn_val='type', con_ssh=None, **kwargs):
    """
    Get values from 'system network-list'
    Args:
        rtn_val:
        con_ssh:
        **kwargs:

    Returns (list):
    """
    table_ = table_parser.table(cli.system('network-list', positional_args='--nowrap', ssh_client=con_ssh))
    return table_parser.get_values(table_, target_header=rtn_val, **kwargs)


def enable_port_security_param():
    """
    Enable port security param
    Returns:

    """
    code = create_service_parameter(service='network', section='ml2', name='extension_drivers',
                                    value='port_security', apply=False)[0]
    if 0 == code:
        LOG.info("Apply network service parameter and lock/unlock computes")
        apply_service_parameters(service='network', wait_for_config=False)
        wait_and_clear_config_out_of_date_alarms(host_type='compute')


def get_ptp_vals(rtn_val='mode', rtn_dict=False, con_ssh=None):
    """
    Get values from system ptp-show table.
    Args:
        rtn_val (str|tuple|list):
        rtn_dict (bool): whether to return dict or list
        con_ssh:

    Returns (list|dict):

    """
    table_ = table_parser.table(cli.system('ptp-show', ssh_client=con_ssh))

    if isinstance(rtn_val, str):
        rtn_val = [rtn_val]

    vals = {} if rtn_dict else []
    for field in rtn_val:
        val = table_parser.get_value_two_col_table(table_, field=field, merge_lines=True)
        if rtn_dict:
            vals[field] = val
        else:
            vals.append(val)

    return vals


def modify_ptp(enabled=None, mode=None, transport=None, mechanism=None, fail_ok=False, con_ssh=None, clear_alarm=True,
               wait_with_best_effort=False, check_first=True, auth_info=Tenant.get('admin')):
    """
    Modify ptp with given parameters
    Args:
        enabled (bool|None):
        mode (str|None):
        transport (str|None):
        mechanism (str|None):
        fail_ok (bool):
        clear_alarm (bool):
        wait_with_best_effort (bool):
        check_first:
        auth_info (dict):
        con_ssh:

    Returns:

    """
    args_map = {
        'enabled': enabled,
        'mode': mode,
        'transport': transport,
        'mechanism': mechanism,
    }

    args_dict = {}
    for key, val in args_map.items():
        if val is not None:
            args_dict[key] = str(val)

    if not args_dict:
        raise ValueError("At least one parameter has to be specified.")

    arg_str = ' '.join(['--{} {}'.format(k, v) for k, v in args_dict.items()])

    if check_first:
        actual_val_list = get_ptp_vals(rtn_val=list(args_dict.keys()), con_ssh=con_ssh, rtn_dict=True)
        changeparm = False
        for field in args_dict:
            param_val = args_dict[field]
            actual_val = actual_val_list[field]
            if actual_val != param_val:
                changeparm = True
                break
        if not changeparm:
            return -1, 'No parameter chage'

    code, output = cli.system('ptp-modify', arg_str, ssh_client=con_ssh, fail_ok=fail_ok, auth_info=auth_info,
                              rtn_list=True)
    if code > 0:
        return 1, output

    if clear_alarm:
        wait_and_clear_config_out_of_date_alarms(host_type='controller', wait_with_best_effort=wait_with_best_effort,
                                                 con_ssh=con_ssh)

    post_args = get_ptp_vals(rtn_val=list(args_dict.keys()), con_ssh=con_ssh, rtn_dict=True)
    for field in args_dict:
        expt_val = args_dict[field]
        actual_val = post_args[field]
        if actual_val != expt_val:
            raise exceptions.SysinvError("{} in ptp-show is not as expected after modify. Expt: {}; actual: {}".
                                         format(field, expt_val, actual_val))

    msg = 'ptp modified successfully. {}'.format('Alarm not cleared yet.' if not clear_alarm else '')
    return 0, msg


def get_ntp_vals(rtn_val='ntpservers', rtn_dict=False, con_ssh=None, auth_info=Tenant.get('admin')):
    """
    Get values from system ntp-show table.
    Args:
        rtn_val (str|tuple|list):
        rtn_dict (bool)
        con_ssh:
        auth_info

    Returns (list|dict):

    """
    table_ = table_parser.table(cli.system('ntp-show', ssh_client=con_ssh, auth_info=auth_info))

    if isinstance(rtn_val, str):
        rtn_val = [rtn_val]

    vals = {} if rtn_dict else []
    for field in rtn_val:
        val = table_parser.get_value_two_col_table(table_, field=field, merge_lines=True)
        if rtn_dict:
            vals[field] = val
        else:
            vals.append(val)

    return vals


def get_ntp_servers(con_ssh=None, auth_info=Tenant.get('admin')):
    """
    Get ntp servers via system ntp-show
    Args:
        con_ssh:
        auth_info:

    Returns (list):

    """
    ntp_servers = get_ntp_vals(rtn_val='ntpservers', rtn_dict=False, con_ssh=con_ssh, auth_info=auth_info)
    ntp_servers = ntp_servers[0].split(',')
    return ntp_servers


def modify_ntp(enabled=None, ntp_servers=None, check_first=True, fail_ok=False, clear_alarm=True,
               wait_with_best_effort=False, con_ssh=None, auth_info=Tenant.get('admin'), **kwargs):
    """

    Args:
        enabled (bool|None):
        ntp_servers (str|None|list|tuple):
        check_first (bool)
        fail_ok (bool)
        clear_alarm (bool): Whether to wait and lock/unlock hosts to clear alarm
        wait_with_best_effort (bool): whether to wait for alarm with best effort only
        con_ssh:
        check_first:
        auth_info:
        **kwargs

    Returns (tuple):
        (0, <success_msg>)
        (1, <std_err>)      # cli rejected

    """
    arg = ''
    verify_args = {}
    if enabled is not None:
        arg += '--enabled {}'.format(enabled).lower()
        verify_args['enabled'] = str(enabled)

    if ntp_servers:
        if isinstance(ntp_servers, (tuple, list)):
            ntp_servers = ','.join(ntp_servers)
        arg += ' ntpservers="{}"'.format(ntp_servers)
        verify_args['ntpservers'] = ntp_servers

    if kwargs:
        for k, v in kwargs.items():
            arg += ' {}={}'.format(k, v)
            verify_args[k] = v

    if not arg:
        raise ValueError("Nothing to modify. enable, ntp_servers or kwwargs has to be provided")

    prev_args = None
    toggle_state = False
    if enabled is not None:
        prev_args = get_ntp_vals(rtn_val=list(verify_args.keys()), con_ssh=con_ssh, rtn_dict=True)
        if prev_args['enabled'] != verify_args['enabled']:
            toggle_state = True

    if check_first and not toggle_state:
        if not clear_alarm or (clear_alarm and not get_alarms(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, con_ssh=con_ssh,
                                                              entity_id='controller', auth_info=auth_info)):
            if not prev_args:
                prev_args = get_ntp_vals(rtn_val=list(verify_args.keys()), con_ssh=con_ssh, rtn_dict=True)

            for field in verify_args:
                expt_val = verify_args[field]
                actual_val = prev_args[field]
                if actual_val != expt_val:
                    break
            else:
                msg = 'NTP already configured with given criteria {}. Do nothing.'.format(verify_args)
                LOG.info(msg)
                return -1, msg

    code, out = cli.system('ntp-modify', arg.strip(), fail_ok=fail_ok, ssh_client=con_ssh, auth_info=auth_info,
                           rtn_list=True)
    if code > 0:
        return 1, out

    if clear_alarm:
        # config out-of-date alarm only on controller if only ntp servers are changed.
        # If ntp state changes, ALL hosts need to be lock/unlock.
        host_type = None if toggle_state else 'controller'
        wait_and_clear_config_out_of_date_alarms(host_type=host_type, con_ssh=con_ssh, auth_info=auth_info,
                                                 wait_with_best_effort=wait_with_best_effort)

    post_args = get_ntp_vals(rtn_val=list(verify_args.keys()), con_ssh=con_ssh, rtn_dict=True, auth_info=auth_info)
    for field in verify_args:
        expt_val = verify_args[field]
        actual_val = post_args[field]
        if actual_val != expt_val:
            raise exceptions.SysinvError("{} in ntp-show is not as expected after modify. Expt: {}; actual: {}".
                                         format(field, expt_val, actual_val))

    msg = 'ntp modified successfully. {}'.format('Alarm not cleared yet.' if not clear_alarm else '')
    return 0, msg


def wait_and_clear_config_out_of_date_alarms(hosts=None, host_type=None, lock_unlock=True, wait_timeout=60,
                                             wait_with_best_effort=False, clear_timeout=60,
                                             con_ssh=None, auth_info=Tenant.get('admin')):
    """
    Wait for config out-of-date alarms on given hosts and (lock/unlock and) wait for clear
    Args:
        hosts:
        host_type (str|list|tuple): valid types: controller, compute, storage
        lock_unlock (bool)
        wait_timeout (int)
        wait_with_best_effort (bool):
        clear_timeout (int)
        con_ssh:
        auth_info

    Returns:

    """
    from keywords.host_helper import get_up_hypervisors, lock_unlock_hosts

    if not hosts:
        host_groups = []
        if not host_type:
            host_type = ('controller', 'compute', 'storage')
        elif isinstance(host_type, str):
            host_type = [host_type]

        host_type_map = {
            'controller': get_controllers,
            'compute': get_up_hypervisors,
            'storage': get_storage_nodes
        }
        for host_type_ in host_type:
            hosts_for_type = host_type_map[host_type_](con_ssh=con_ssh, auth_info=auth_info)
            if hosts_for_type:
                host_groups.append(hosts_for_type)

        if not host_groups:
            raise exceptions.HostError("No valid hosts found for host_type: {}".format(host_type))

    else:
        if isinstance(hosts, str):
            hosts = [hosts]
        host_groups = [hosts]

    hosts_out_of_date = []
    all_hosts = []
    for hosts_ in host_groups:
        LOG.info("Wait for config out-of-date alarms for {} with best effort".format(hosts_))
        all_hosts += hosts_
        if wait_for_alarm(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, entity_id=hosts_, timeout=wait_timeout,
                          con_ssh=con_ssh, fail_ok=True, auth_info=auth_info)[0]:
            hosts_out_of_date += hosts_

    hosts_out_of_date = list(set(hosts_out_of_date))
    all_hosts = list(set(all_hosts))
    LOG.info("Config out-of-date hosts: {}".format(hosts_out_of_date))
    if hosts_out_of_date:
        if lock_unlock:
            LOG.info("Wait for 60 seconds, then lock/unlock config out-of-date hosts: {}".format(hosts_out_of_date))
            time.sleep(60)
            lock_unlock_hosts(hosts_out_of_date, con_ssh=con_ssh, auth_info=auth_info)

        LOG.info("Wait for config out-of-date alarm to clear on system")
        wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, timeout=clear_timeout, auth_info=auth_info,
                            con_ssh=con_ssh)

    if not wait_with_best_effort and all_hosts != hosts_out_of_date:
        raise exceptions.SysinvError("Expect config out of date: {}; actual: {}".format(all_hosts, hosts_out_of_date))


def get_timezone(auth_info=Tenant.get('admin'), con_ssh=None):
    return get_system_value(field='timezone', auth_info=auth_info, con_ssh=con_ssh)


def modify_timezone(timezone, check_first=True, fail_ok=False, clear_alarm=True, auth_info=Tenant.get('admin'),
                    con_ssh=None):
    """
    Modify timezone to given zone
    Args:
        timezone:
        check_first:
        fail_ok:
        clear_alarm:
        auth_info:
        con_ssh:

    Returns (tuple):

    """
    if check_first:
        current_timezone = get_timezone(auth_info=auth_info, con_ssh=con_ssh)
        if current_timezone == timezone:
            msg = "Timezone is already set to {}. Do nothing.".format(timezone)
            LOG.info(msg)
            return -1, msg

    LOG.info("Modifying Timezone to {}".format(timezone))
    code, out = modify_system(fail_ok=fail_ok, auth_info=auth_info, con_ssh=con_ssh, timezone=timezone)
    if code > 0:
        return 1, out

    if clear_alarm:
        if wait_for_alarm(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, timeout=30, con_ssh=con_ssh, fail_ok=True,
                          auth_info=auth_info)[0]:
            wait_for_alarm_gone(alarm_id=EventLogID.CONFIG_OUT_OF_DATE, timeout=180, con_ssh=con_ssh,
                                auth_info=auth_info)

    time.sleep(10)
    post_timezone = get_timezone(auth_info=auth_info, con_ssh=con_ssh)
    if post_timezone != timezone:
        msg = 'Timezone is {} instead of {} after modify'.format(post_timezone, timezone)
        if fail_ok:
            LOG.warning(msg)
            return 2, post_timezone

        raise exceptions.SysinvError(msg)

    LOG.info("Timezone is successfully modified to {}".format(timezone))
    return 0, timezone
