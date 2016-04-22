import random
import re
import ipaddress

from utils import table_parser, cli
from utils.tis_log import LOG
from consts.auth import Tenant
from consts.cgcs import MGMT_IP
from keywords import common


def is_valid_ip_address(ip=None):
    """
    Validate the input IP address

    Args:
        ip:  IPv4 or IPv6 address

    Returns:
        True: valid IPv4 or IPv6 address
        False: otherwise
    """
    if get_ip_address_str(ip):
        return True
    else:
        return False


def get_ip_address_str(ip=None):
    """
    Get the representation of the input IP address

    Args:
        ip:  IPv4 or IPv6 address

    Returns:
        str: string representation of the input IP address if it's valid
        None: otherwise
    """
    try:
        ipaddr = ipaddress.ip_address(ip)
        return str(ipaddr)
    except ValueError:
        # invalid IPv4 or IPv6 address
        return None


def create_network(name, admin_state='up', qos_policy=None, vlan_transparent=None, **subnet):
    raise NotImplementedError


def _get_net_id(net_name, con_ssh=None, auth_info=None):
    table_ = table_parser.table(cli.neutron('net-list', ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_values(table_, 'id', name=net_name)


def get_mgmt_net_id(con_ssh=None, auth_info=None):
    """
    Get the management net id of given tenant.

    Args:
        con_ssh (SSHClient): If None, active controller ssh will be used.
        auth_info (dict): Tenant dict. If None, primary tenant will be used.

    Returns (str): Management network id of a specific tenant.

    """
    if auth_info is None:
        auth_info = Tenant.get_primary()

    tenant = auth_info['tenant']
    mgmt_net_name = '-'.join([tenant, 'mgmt', 'net'])
    return _get_net_id(mgmt_net_name, con_ssh=con_ssh, auth_info=auth_info)[0]


def get_tenant_net_id(net_name=None, con_ssh=None, auth_info=None):
    """
    Get one tenant network id that matches the given net_name of a specific tenant.

    Args:
        net_name (str): name of the tenant network. This can be a substring of the tenant net name, such as 'net1',
            and it will return id for <tenant>-net1
        con_ssh (SSHClient):
        auth_info (dict): If None, primary tenant will be used.

    Returns (str): A tenant network id for given tenant network name.
        If multiple ids matches the given name, only one will be returned, and the choice will be random.

    """
    net_ids = get_tenant_net_ids(net_names=net_name, con_ssh=con_ssh, auth_info=auth_info)
    return random.choice(net_ids)


def get_tenant_net_ids(net_names=None, con_ssh=None, auth_info=None):
    """
    Get a list of tenant network ids that match the given net_names for a specific tenant.

    Args:
        net_names (str or list): list of tenant network name(s) to get id(s) for
        con_ssh (SSHClient):
        auth_info (dict): If None, primary tenant will be used

    Returns (list): list of tenant nets. such as (<id for tenant2-net1>, <id for tenant2-net8>)

    """
    table_ = table_parser.table(cli.neutron('net-list', ssh_client=con_ssh, auth_info=auth_info))
    if net_names is None:
        tenant_name = common.get_tenant_name(auth_info=auth_info)
        name = tenant_name + '-net'
        return table_parser.get_values(table_, 'id', strict=False, name=name)
    else:
        if isinstance(net_names, str):
            net_names = [net_names]
        table_ = table_parser.filter_table(table_, name=net_names, strict=False)
        return table_parser.get_column(table_, 'id')


def get_mgmt_ips_for_vms(vms=None, con_ssh=None, auth_info=Tenant.ADMIN, rtn_dict=False):
    """
    This function returns the management IPs for all VMs on the system.
    We make the assumption that the management IPs start with "192".
    Args:
        vms (str|tuple|None): vm ids list. If None, management ips for ALL vms with given Tenant(via auth_info) will be
            returned.
        con_ssh (SSHClient): active controller SSHClient object
        auth_info (dict): use admin by default unless specified
        rtn_dict (bool): return tuple if False, return dict if True

    Returns (tuple|dict):
        a list of all VM management IPs   # rtn_dict=False
        dictionary with vm IDs as the keys, and mgmt ips as values    # rtn_dict=True
    """

    table_ = table_parser.table(cli.nova('list', '--all-tenant', ssh_client=con_ssh, auth_info=auth_info))
    if vms:
        table_ = table_parser.filter_table(table_, ID=vms)
    elif vms is not None:
        raise ValueError("Invalid value for vms: {}".format(vms))
    all_ips = []
    all_ips_dict = {}
    mgmt_ip_reg = re.compile(MGMT_IP)
    vm_ids = table_parser.get_column(table_, 'ID')
    if not vm_ids:
        raise ValueError("No vm is on the system. Please boot vm(s) first.")
    vm_nets = table_parser.get_column(table_, 'Networks')

    for i in range(len(vm_ids)):
        vm_id = vm_ids[i]
        mgmt_ips_for_vm = tuple(mgmt_ip_reg.findall(vm_nets[i]))
        if not mgmt_ips_for_vm:
            LOG.warning("No management ip found for vm {}".format(vm_id))
        else:
            all_ips_dict[vm_id] = mgmt_ips_for_vm
            all_ips += mgmt_ips_for_vm

    if not all_ips:
        raise ValueError("No management ip found for any of these vms: {}".format(vm_ids))

    LOG.info("Management IPs dict: {}".format(all_ips_dict))

    if rtn_dict:
        return all_ips_dict
    else:
        return tuple(all_ips)
