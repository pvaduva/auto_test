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
        self.SMALL_SYS = is_small_footprint(controller_ssh)
        nodes = _get_nodes(controller_ssh)
        self.CONTROLLERS = nodes['controllers']
        self.COMPUTES = nodes['computes']
        self.STORAGES = nodes['storages']
        LOG.info(("Information for system {}: "
                  "\nSmall footprint: {}\nController nodes: {}\nCompute nodes: {}\nStorage nodes: {}").
                 format(controller_ssh.host, self.SMALL_SYS, self.CONTROLLERS, self.COMPUTES, self.STORAGES))

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

    LOG.debug("This is {} small footprint system.".format(str_))
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


def get_hosts_by_storage_aggregate(storage_backing='local_image', con_ssh=None):
    """
    Return a list of hosts that supports the given storage backing
    Args:
        storage_backing (str): 'local_image', 'local_lvm', or 'remote'
        con_ssh (SSHClient):

    Returns: (list)
        such as ['compute-0', 'compute-2', 'compute-1', 'compute-3']
        or [] if no host supports this storage backing

    """
    storage_backing = storage_backing.strip().lower()
    if 'image' in storage_backing:
        aggregate = 'local_storage_image_hosts'
    elif 'lvm' in storage_backing:
        aggregate = 'local_storage_lvm_hosts'
    elif 'remote' in storage_backing:
        aggregate = 'remote_storage_hosts'
    else:
        raise ValueError("Invalid storage backing provided. "
                         "Please use one of these: 'local_image', 'local_lvm', 'remote'")

    table_ = table_parser.table(cli.nova('aggregate-details', aggregate, ssh_client=con_ssh,
                                         auth_info=Tenant.ADMIN))
    hosts = table_parser.get_values(table_, 'Hosts', Name=aggregate)[0]
    hosts = hosts.split(',')
    if len(hosts) == 0 or hosts == ['']:
        hosts = []
    else:
        hosts = [eval(host) for host in hosts]

    LOG.info("Hosts with {} backing: {}".format(storage_backing, hosts))
    return hosts


def get_local_storage_backing(host, con_ssh=None):
    table_ = table_parser.table(cli.system('host-lvg-show', host + ' nova-local', ssh_client=con_ssh))
    return eval(table_parser.get_value_two_col_table(table_, 'parameters'))['instance_backing']