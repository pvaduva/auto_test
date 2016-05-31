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
    table_ = table_parser.table(cli.system('host-if-list', host, ssh_client=con_ssh))
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
    table_ = table_parser.table(cli.system('alarm-suppress-list', args, ssh_client=con_ssh, auth_info=auth_info))
    return table_


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


def wait_for_events(timeout=30, num=5, uuid=False, show_only=None, query_key=None, query_value=None, query_type=None,
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


def set_retention_period(fail_ok=True, con_ssh=None, auth_info=Tenant.ADMIN, retention_period=None):
    """
    Modify the Retention Period of the system performance manager.

    Args:
        fail_ok (bool):
        con_ssh (SSHClient):
        auth_info (dict):
        retention_period (int):   retention period in seconds

    Returns: (int, str)
         0  - success
         1  - error

    Test Steps:
        - Set the value via system pm_modify retention_secs=<new_retention_period_in_seconds

    Notes:
        -
    """
    if retention_period is None:
        raise ValueError("Please specify the Retention Period.")

    args_ = ' retention_secs="{}"'.format(int(retention_period))
    code, output = cli.system('pm-modify', args_, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                              rtn_list=True, timeout=60)

    if code == 1:
        return 1, output
    elif code == 0:
        return 0, ''
    else:
        # should not get here: cli.system() should already have been handled these cases
        pass


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
