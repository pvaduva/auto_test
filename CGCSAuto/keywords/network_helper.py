import re
import ipaddress

from utils import table_parser, cli, exceptions
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
    return bool(get_ip_address_str(ip))


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


def _get_net_ids(net_name, con_ssh=None, auth_info=None):
    table_ = table_parser.table(cli.neutron('net-list', ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_values(table_, 'id', name=net_name)


def get_ext_net_ids(con_ssh=None, auth_info=None):
    table_ = table_parser.table(cli.neutron('net-external-list', ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_column(table_, 'id')


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
    return _get_net_ids(mgmt_net_name, con_ssh=con_ssh, auth_info=auth_info)[0]


def get_tenant_net_id(net_name=None, con_ssh=None, auth_info=None):
    """
    Get tenant network id that matches the given net_name of a specific tenant.

    Args:
        net_name (str): name of the tenant network. This can be a substring of the tenant net name, such as 'net1',
            and it will return id for <tenant>-net1
        con_ssh (SSHClient):
        auth_info (dict): If None, primary tenant will be used.

    Returns (str): A tenant network id for given tenant network name.
        If multiple ids matches the given name, only the first will return

    """
    net_ids = get_tenant_net_ids(net_names=net_name, con_ssh=con_ssh, auth_info=auth_info)
    return net_ids[0]


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
        vms (str|list|None): vm ids list. If None, management ips for ALL vms with given Tenant(via auth_info) will be
            returned.
        con_ssh (SSHClient): active controller SSHClient object
        auth_info (dict): use admin by default unless specified
        rtn_dict (bool): return list if False, return dict if True

    Returns (list|dict):
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
        mgmt_ips_for_vm = mgmt_ip_reg.findall(vm_nets[i])
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
        return all_ips


def get_router_ids(auth_info=None, con_ssh=None):
    table_ = table_parser.table(cli.neutron('router-list', ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_column(table_, 'id')


def get_router_info(router_id=None, field='status', strict=True, auth_info=None, con_ssh=None):
    """
    Get value of specified field for given router via neutron router-show

    Args:
        router_id (str):
        field (str):
        strict (bool):
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (str): value of specified field for given router

    """
    if not router_id:
        router_id = get_router_ids(auth_info=auth_info, con_ssh=con_ssh)[0]

    table_ = table_parser.table(cli.neutron('router-show', router_id, ssh_client=con_ssh, auth_info=Tenant.ADMIN))
    return table_parser.get_value_two_col_table(table_, field, strict)


def set_router_gateway(router_id=None, extnet_id=None, enable_snat=True, fixed_ip=None, fail_ok=False,
                       auth_info=Tenant.ADMIN, con_ssh=None, clear_first=True):
    # Process args
    args = ''
    if not enable_snat:
        args += ' --disable-snat'

    if fixed_ip:
        args += ' --fixed-ip {}'.format(fixed_ip)

    if not router_id:
        router_id = get_router_ids(con_ssh=con_ssh, auth_info=None)[0]

    if not extnet_id:
        extnet_id = get_ext_net_ids(con_ssh=con_ssh, auth_info=None)[0]

    args = ' '.join([args, router_id, extnet_id])

    # Clear first if gateway already set
    if clear_first and get_router_ext_gateway_info(router_id):
        clear_router_gateway(router_id=router_id, check_first=False)

    code, output = cli.neutron('router-gateway-set', args, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                               rtn_list=True)

    if code == 1:
        return 1, output

    post_ext_gateway = get_router_ext_gateway_info(router_id)

    if not extnet_id == post_ext_gateway['network_id']:
        msg = "Failed to set gateway of external network {} for router {}".format(extnet_id, router_id)
        if fail_ok:
            LOG.warning(msg)
            return 2, msg
        raise exceptions.NeutronError(msg)

    if not enable_snat == post_ext_gateway['enable_snat']:
        expt_str = 'enabled' if enable_snat else 'disabled'
        msg = "snat is not {}".format(expt_str)
        if fail_ok:
            LOG.warning(msg)
            return 3, msg

    if fixed_ip and not fixed_ip == post_ext_gateway['external_fixed_ips'][0]['ip_address']:
        msg = "Fixed ip is not set to {}".format(fixed_ip)
        if fail_ok:
            LOG.warning(msg)
            return 4, msg
        raise exceptions.NeutronError(msg)

    succ_msg = "Router gateway is successfully set."
    LOG.info(succ_msg)
    return 0, succ_msg


def clear_router_gateway(router_id=None, fail_ok=False, auth_info=Tenant.ADMIN, con_ssh=None, check_first=True):
    """

    Args:
        router_id (str):
        fail_ok (bool):
        auth_info (dict):
        con_ssh (SSHClient):
        check_first (bool):

    Returns:

    """
    if not router_id:
        router_id = get_router_ids(con_ssh=con_ssh, auth_info=auth_info)[0]

    if check_first and not get_router_ext_gateway_info(router_id):
        msg = "No gateway found for router. Do nothing."
        LOG.info(msg)
        return -1, msg

    code, output = cli.neutron('router-gateway-clear', router_id, ssh_client=con_ssh, auth_info=auth_info,
                               fail_ok=fail_ok, rtn_list=True)

    if code == 1:
        return 1, output

    if get_router_ext_gateway_info(router_id):
        msg = "Failed to clear gateway for router {}".format(router_id)
        if fail_ok:
            LOG.warning(msg)
            return 2, msg
        raise exceptions.NeutronError(msg)

    msg = "Router gateway is successfully cleared."
    LOG.info(msg)
    return 0, msg


def _update_router(field, value, val_type=None, router_id=None, fail_ok=False, con_ssh=None, auth_info=Tenant.ADMIN):

    if router_id is None:
        router_id = get_router_ids(auth_info=None, con_ssh=con_ssh)

    LOG.info("Updating router {}: {}={}".format(router_id, field, value))

    if val_type is not None:
        val_type = 'type={} '.format(val_type)

    args = '{} --{} {}{}'.format(router_id, field, val_type, value)

    code, output = cli.neutron('router-update', args, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                               rtn_list=True)

    if code == 0:
        LOG.info("Router is successfully updated.")

    return code, output


def get_router_ext_gateway_info(router_id=None, auth_info=None, con_ssh=None):
    """
    Get router's external gateway info as a dictionary

    Args:
        router_id (str):
        auth_info (dict|None):
        con_ssh (SSHClient):

    Returns (dict): external gateway info as a dict.
        Examples:  {"network_id": "55e5967a-2138-4f27-a17c-d700af1c2429",
                    "enable_snat": True,
                    "external_fixed_ips": [{"subnet_id": "892d3ad8-9cbc-46db-88f3-84e151bbc116",
                                            "ip_address": "192.168.9.3"}]
                    }
    """
    info_str = get_router_info(router_id=router_id, field='external_gateway_info', auth_info=auth_info, con_ssh=con_ssh)
    if not info_str:
        return None

    # convert enable_snat value to bool
    true = True
    false = False
    return eval(info_str)


def update_router_ext_gateway_snat(router_id=None, ext_net_id=None, enable_snat=True, fail_ok=False, con_ssh=None,
                                   auth_info=Tenant.ADMIN):
    arg = 'network_id={},enable_snat={}'.format(ext_net_id, enable_snat)
    code, output = _update_router(field='external_gateway_info', val_type='dict', value=arg, router_id=router_id,
                                  fail_ok=fail_ok, con_ssh=con_ssh, auth_info=auth_info)
    if code == 1:
        return 1, output

    post_gateway_info = get_router_ext_gateway_info(router_id=router_id, auth_info=auth_info, con_ssh=con_ssh)
    if enable_snat != post_gateway_info['enable_snat']:
        msg = "enable_snat is not set to {}".format(enable_snat)
        LOG.warning(msg)
        return 2, msg

    return 0, output
