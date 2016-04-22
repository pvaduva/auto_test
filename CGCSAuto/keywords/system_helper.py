import re

from consts import cgcs
from consts.auth import Tenant
from utils import cli
from utils import exceptions
from utils import table_parser
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
    return _get_info_non_cli(r'cat /etc/hostname')


def get_buildinfo(con_ssh=None):
    return _get_info_non_cli(r'cat /etc/build.info')


def _get_info_non_cli(cmd, con_ssh=None):
    if con_ssh is None:
        con_ssh = ControllerClient.get_active_controller()
    exitcode, output = con_ssh.exec_cmd(cmd)
    if not exitcode == 0:
        raise exceptions.SSHExecCommandFailed("Command failed to execute.")

    # remove date output if any
    output = output.splitlines()
    if re.search(cgcs.DATE_OUTPUT, output[-1]):
        output = output[:-1]
    output = ''.join(output)

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
    table_ = table_parser.table(cli.system('host-if-list', host))
    return table_


def get_alarms(con_ssh=None):
    table_ = table_parser.table(cli.system('alarm-list', ssh_client=con_ssh))
    return table_


def get_events(cli_args=' --limit 5', con_ssh=None):
    table_ = table_parser.table(cli.system('event-list ' + cli_args, ssh_client=con_ssh))
    return table_


def host_exists(host, field='hostname', con_ssh=None):
    if not field.lower() in ['hostname', 'id']:
        raise ValueError("field has to be either \'hostname\' or \'id\'")

    table_ = table_parser.table(cli.system('host-list', ssh_client=None))

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
                              rtn_list=True)

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
                              rtn_list=True)

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

    tables_ = table_parser.tables(con_ssh.exec_cmd('vm-topology -s {}'.format(show_args), expect_timeout=30)[1])
    return tables_
