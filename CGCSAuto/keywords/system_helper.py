import math
import time

from consts.auth import Tenant
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
        alarms = get_alarms(self.CON_SSH)
        system['alarms'] = alarms
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


def is_small_footprint(controller_ssh=None):
    table_ = table_parser.table(cli.system('host-show', '1', ssh_client=controller_ssh))
    subfunc = table_parser.get_value_two_col_table(table_, 'subfunctions')

    combined = 'controller' in subfunc and 'compute' in subfunc

    str_ = 'not' if not combined else ''

    LOG.info("This is {} small footprint system.".format(str_))
    return combined


def get_storage_nodes(con_ssh=None):
    table_ = table_parser.table(cli.system('host-list', ssh_client=con_ssh))
    nodes = table_parser.get_values(table_, 'hostname', strict=True, personality='storage')

    return nodes


def get_controllers(con_ssh=None):
    nodes = _get_nodes(con_ssh)
    return nodes['controllers']


def get_computes(con_ssh=None):
    nodes = _get_nodes(con_ssh)
    return nodes['computes']


def get_hostnames(con_ssh=None):
    table_ = table_parser.table(cli.system('host-list', ssh_client=con_ssh))
    return table_parser.get_column(table_, 'hostname')


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


def get_active_controller_name(con_ssh=None):
    """
    This assumes system has 1 active controller
    Args:
        con_ssh:

    Returns: hostname of the active controller
        Further info such as ip, uuid can be obtained via System.CONTROLLERS[hostname]['uuid']
    """
    return _get_active_standby(controller='active', con_ssh=con_ssh)[0]


def get_standby_controller_name(con_ssh=None):
    """
    This assumes system has 1 standby controller
    Args:
        con_ssh:

    Returns: hostname of the active controller
        Further info such as ip, uuid can be obtained via System.CONTROLLERS[hostname]['uuid']
    """
    standby = _get_active_standby(controller='standby', con_ssh=con_ssh)
    return '' if len(standby) == 0 else standby[0]


def _get_active_standby(controller='active', con_ssh=None):
    table_ = table_parser.table(cli.system('servicegroup-list', ssh_client=con_ssh))
    table_ = table_parser.filter_table(table_, service_group_name='controller-services')
    controllers = table_parser.get_values(table_, 'hostname', state=controller, strict=False)
    LOG.debug(" {} controller(s): {}".format(controller, controllers))
    if isinstance(controllers, str):
        controllers = [controllers]

    return controllers


def get_interfaces(host, con_ssh=None):
    table_ = table_parser.table(cli.system('host-if-list --nowrap', host, ssh_client=con_ssh))
    return table_


def get_alarms(uuid=False, show_suppress=False, query_key=None, query_value=None, query_type=None, con_ssh=None,
               auth_info=Tenant.ADMIN):
    """
    Get active alarms dictionary with given criteria
    Args:
        uuid (bool): whether to show uuid
        show_suppress (bool): whether to show suppressed alarms
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
    return table_


def get_suppressed_alarms(uuid=False, con_ssh=None, auth_info=Tenant.ADMIN):

    """
    Get suppressed alarms as dictionary
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


def unsuppress_all(ssh_con=None, fail_ok=False, auth_info=Tenant.ADMIN):
    """

    Args:
        ssh_con:
        fail_ok:
        auth_info:

    Returns:

    """
    args = '--nowrap --nopaging'
    table_events = table_parser.table(cli.system('event-unsuppress-all',positional_args=args, ssh_client=ssh_con,
                                                 fail_ok=fail_ok,auth_info=auth_info, rtn_list=True))
    get_suppress_list = table_events
    suppressed_list = table_parser.get_values(table_=get_suppress_list, target_header='Suppressed Alarm ID\'s',
                                              strict=True, **{'Status': 'suppressed'})
    if len(suppressed_list) == 0:
        return 0, "Successfully unsuppressed"
    msg = "Suppressed was unsuccessfull"
    if fail_ok:
        LOG.warning(msg)
        return 2, msg
    raise exceptions.NeutronError(msg)


def get_events(num=5, uuid=False, show_only=None, show_suppress=False, query_key=None, query_value=None,
               query_type=None, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Get a list of events with given criteria as dictionary
    Args:
        num (int): max number of event logs to return
        uuid (bool): whether to show uuid
        show_only (str): 'alarms' or 'logs' to return only alarms or logs
        show_suppress (bool): whether or not to show suppressed alarms
        query_key (str): one of these: 'event_log_id', 'entity_instance_id', 'uuid', 'severity',
        query_value (str): expected value for given key
        query_type (str): data type of value. one of these: 'string', 'integer', 'float', 'boolean'
        con_ssh (SSHClient):
        auth_info (dict):

    Returns:
        dict: events table in format: {'headers': <headers list>, 'values': <list of table rows>}
    """
    args = '-l {}'.format(num)
    args = __process_query_args(args, query_key, query_value, query_type)
    args += ' --nowrap --nopaging'
    if uuid:
        args += ' --uuid'
    if show_only:
        args += ' --{}'.format(show_only.lower())
    if show_suppress:
        args += ' --include_suppress'

    table_ = table_parser.table(cli.system('event-list ', args, ssh_client=con_ssh, auth_info=auth_info))
    return table_


def __process_query_args(args, query_key, query_value, query_type):
    if query_key:
        if not query_value:
            raise ValueError("Query value is not supplied for key - {}".format(query_key))
        data_type_arg = '' if not query_type else "{}::".format(query_type.lower())
        args += ' -q {}={}{}'.format(query_key.lower(), data_type_arg, query_value.lower())
    return args


def wait_for_events(timeout=30, num=10, uuid=False, show_only=None, query_key=None, query_value=None, query_type=None,
                    fail_ok=True, rtn_val='Event Log ID', con_ssh=None, auth_info=Tenant.ADMIN, regex=False,
                    strict=True, check_interval=3, **kwargs):
    """
    Wait for event(s) to appear in system event-list
    Args:
        timeout (int): max time to wait in seconds
        num (int): max number of event logs to return
        uuid (bool): whether to show uuid
        show_only (str): 'alarms' or 'logs' to return only alarms or logs
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
        **kwargs: criteria to filter out event(s) from the events list table

    Returns:
        list: list of event log ids (or whatever specified in rtn_value) for matching events.

    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        events_tab = get_events(num=num, uuid=uuid, show_only=show_only, query_key=query_key, query_value=query_value,
                                query_type=query_type, con_ssh=con_ssh, auth_info=auth_info)
        events_tab = table_parser.filter_table(events_tab, strict=strict, regex=regex, **kwargs)
        events = table_parser.get_column(events_tab, rtn_val)
        if events:
            LOG.info("Event(s) appeared in event-list: {}".format(events))
            return events

        time.sleep(check_interval)

    criteria = ['{}={}'.format(key, value) for key, value in kwargs.items()]
    criteria = ';'.join(criteria)
    criteria += ";{}={}".format(query_key, query_value) if query_key else ''

    msg = "Event(s) did not appear in system event-list within timeout. Criteria: {}".format(criteria)
    if fail_ok:
        LOG.warning(msg)
        return []
    else:
        raise exceptions.TimeoutException(msg)


def host_exists(host, field='hostname', con_ssh=None):
    if not field.lower() in ['hostname', 'id']:
        raise ValueError("field has to be either \'hostname\' or \'id\'")

    table_ = table_parser.table(cli.system('host-list', ssh_client=con_ssh))

    hosts = table_parser.get_column(table_, field)
    return host in hosts


def get_storage_monitors_count():
    # Only 2 storage monitor available. At least 2 unlocked and enabled hosts with monitors are required.
    # Please ensure hosts with monitors are unlocked and enabled - candidates: controller-0, controller-1,
    raise NotImplementedError


def get_local_storage_backing(host, con_ssh=None):
    table_ = table_parser.table(cli.system('host-lvg-show', host + ' nova-local', ssh_client=con_ssh))
    return eval(table_parser.get_value_two_col_table(table_, 'parameters'))['instance_backing']


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


def set_retention_period(fail_ok=True, check_first=True, con_ssh=None, auth_info=Tenant.ADMIN, period=None):
    """
    Sets the PM retention period
    Args:
        period (int): the length of time to set the retention period (in seconds)
        fail_ok: True or False
        check_first: True or False
        con_ssh (str):
        auth_info (dict): could be Tenant.ADMIN,Tenant.TENANT_1,Tenant.TENANT_2

    Returns (tuple): (rtn_code (int), msg (str))
        (-1, "Retention period not specified")
        (-1, "The retention period is already set to that")
        (0, "Current retention period is: <retention_period>")
        (1, "Current retention period is still: <retention_period>")

    """

    if not isinstance(period, int):
        raise ValueError("Retention period has to be an integer. Value provided: {}".format(period))
    if check_first:
        retention = get_retention_period()
        if period == retention:
            msg = "The retention period is already set to {}".format(period)
            LOG.info(msg)
            return -1, msg

    code, output = cli.system('pm-modify', 'retention_secs={}'.format(period), auth_info=auth_info, ssh_client=con_ssh,
                              timeout=SysInvTimeout.RETENTION_PERIOD_MDOIFY, fail_ok=fail_ok, rtn_list=True)

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


    Returns (tuple): a list of DNS servers will be returned

    """
    table_ = table_parser.table(cli.system('dns-show', ssh_client=con_ssh))
    return tuple(table_parser.get_value_two_col_table(table_, 'nameservers').strip().split(sep=','))


def set_dns_servers(fail_ok=True, con_ssh=None, auth_info=Tenant.ADMIN, nameservers=None):
    """
    Set the DNS servers


    Args:
        fail_ok:
        con_ssh:
        auth_info:
        nameservers (list): list of IP addresses (in plain text) of new DNS servers to change to


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

    args_ = 'nameservers="{}" action=apply'.format(','.join(nameservers))

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


def get_vm_topology_tables(*table_names, con_ssh=None):
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()

    show_args = ','.join(table_names)

    tables_ = table_parser.tables(con_ssh.exec_cmd('vm-topology -s {}'.format(show_args), expect_timeout=30)[1],
                                  combine_multiline_entry=False)
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


def __suppress_unsuppress_alarm(alarm_id, suppress=True, check_first=False, fail_ok=False, con_ssh=None):
    # TODO: Update after Jira fix.CGTS-4356
    """
    suppress alarm by uuid
    Args:
        alarm_id: string
        fail_ok : Boolean
        con_ssh : (SSHClient)
        suppress boolean True or false

    Returns:
        success 0 ,and output Message
    """

    suppressed_alarms_tab = get_suppressed_alarms(uuid=True, con_ssh=con_ssh)

    alarm_status = "unsuppressed" if suppress else "suppressed"
    cmd = "event-suppress" if suppress else "alarm-unsuppress"
    alarm_filter = {"Suppressed Alarm ID's": alarm_id}

    if check_first:
        pre_status = table_parser.get_values(table_=suppressed_alarms_tab, target_header='Status', strict=True,
                                             **alarm_filter)[0]
        if pre_status.lower() != alarm_status:
            msg = "Alarm is already {}. Do nothing".format(pre_status)
            LOG.info(msg)
            return -1, msg

    code, output = cli.system(cmd, '--alarm_id ' + alarm_id, ssh_client=con_ssh, rtn_list=True, fail_ok=fail_ok)

    if code == 1:
        return 1, output

    post_suppressed_alarms_tab = get_suppressed_alarms(uuid=True, con_ssh=con_ssh)
    post_status = table_parser.get_values(table_=post_suppressed_alarms_tab, target_header="Status", strict=True,
                                          **{"UUID": alarm_id})
    expt_status = "suppressed" if suppress else "unsuppressed"
    if post_status[0].lower() != expt_status:
        msg = "Alarm {} is not {}".format(alarm_id, expt_status)
        if fail_ok:
            LOG.warning(msg)
        raise exceptions.TiSError(msg)

    succ_msg = "Alarm {} is {} successfully".format(alarm_id, expt_status)
    LOG.info(succ_msg)
    return 0, succ_msg


def suppress_alarm(alarm_id, check_first=False, fail_ok=False, con_ssh=None):
    return __suppress_unsuppress_alarm(alarm_id, True, check_first=check_first, fail_ok=fail_ok, con_ssh=con_ssh)


def unsuppress_alarm(alarm_id, check_first=False, fail_ok=False, con_ssh=None):
    return __suppress_unsuppress_alarm(alarm_id, False, check_first=check_first, fail_ok=fail_ok, con_ssh=con_ssh)


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
    LOG.info("Setting 4k memory to: {}".format(smallpage_num))
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


def get_host_mem_values(host, headers, proc_id, con_ssh=None, auth_info=Tenant.ADMIN):
    table_ = table_parser.table(cli.system('host-memory-list --nowrap', host, ssh_client=con_ssh, auth_info=auth_info))

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

    Returns:

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

    table_ = table_parser.table(cli.system(cmd, ssh_client=con_ssh, fail_ok=False, auth_info=Tenant.ADMIN, rtn_list=False))
    uuid = table_parser.get_value_two_col_table(table_, 'uuid')

    return uuid


def to_delete_apply_storage_profile(host, profile=None, con_ssh=None, fail_ok=False):
    """
    Apply a storage profile

    Args:
        host (str): hostname or id
        profile (str): name or id of storage-profile
        con_ssh (SSHClient):

    Returns (dict): proc_id(str) and num_of_cores(int) pairs. e.g.,: {'0': 1, '1': 1}

    """
    if not profile:
        raise ValueError('Name or uuid must be provided to apply that storage-profile')

    cmd = 'host-apply-storprofile {} {}'.format(host, profile)
    LOG.debug('cmd={}'.format(cmd))
    code, output = cli.system(cmd, ssh_client=con_ssh, fail_ok=fail_ok, rtn_list=True, auth_info=Tenant.ADMIN)

    return code, output


def delete_stroage_profile(profile='', con_ssh=None):
    """
    Delete a storage profile

    Args:
        profile_name (str): name of the profile to create
        con_ssh (SSHClient):

    Returns (): no return if success, will raise exception otherwise

    """
    if not profile:
        raise ValueError('Name or uuid must be provided to delete the storage-profile')

    cmd = 'storprofile-delete {}'.format(profile)

    cli.system(cmd, ssh_client=con_ssh, fail_ok=False, auth_info=Tenant.ADMIN, rtn_list=False)


