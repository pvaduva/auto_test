import ipaddress
import math
import re
import time
from collections import Counter
from contextlib import contextmanager

from consts.auth import Tenant
from consts.cgcs import Networks, DNS_NAMESERVERS, PING_LOSS_RATE, MELLANOX4, VSHELL_PING_LOSS_RATE, DevClassID, UUID
from consts.filepaths import UserData
from consts.proj_vars import ProjVar
from consts.timeout import VMTimeout
from keywords import common, keystone_helper, host_helper, system_helper, nova_helper
from testfixtures.fixture_resources import ResourceCleanup
from utils import table_parser, cli, exceptions
from utils.clients.ssh import NATBoxClient, get_cli_client
from utils.tis_log import LOG


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


def create_network(name=None, shared=None, tenant_name=None, network_type=None, segmentation_id=None, qos=None,
                   physical_network=None, vlan_transparent=None, port_security=None, avail_zone=None, external=None,
                   default=None, tags=None, fail_ok=False, auth_info=None, con_ssh=None, cleanup=''):

    """
    Create a network for given tenant

    Args:
        name (str): name of the network
        shared (bool)
        tenant_name: such as tenant1, tenant2.
        network_type (str): The physical mechanism by which the virtual network is implemented
        segmentation_id (None|str): w VLAN ID for VLAN networks
        physical_network (str): Name of the physical network over which the virtual
                        network is implemented
        vlan_transparent(None|bool): Create a VLAN transparent network
        port_security (None|bool)
        avail_zone (None|str)
        external (None|bool)
        default (None|bool): applicable only if external=True.
        tags (None|False|str|list|tuple)
        fail_ok (bool):
        auth_info (dict): run 'openstack network create' cli using these authorization info
        con_ssh (SSHClient):

    Returns (tuple): (rnt_code (int), net_id (str), message (str))

    """
    if name is None:
        name = common.get_unique_name(name_str='net')

    args = name
    if tenant_name is not None:
        tenant_id = keystone_helper.get_tenant_ids(tenant_name, con_ssh=con_ssh)[0]
        args += ' --project ' + tenant_id

    if shared is not None:
        args += ' --share' if shared else ' --no-share'
    if vlan_transparent is not None:
        args += ' --transparent-vlan' if vlan_transparent else ' --no-transparent-vlan'
    if port_security is not None:
        args += ' --enable-port-security' if port_security else ' --disable-port-security'

    if external:
        args += ' --external'
        if default is not None:
            args += ' --default' if default else ' --no-default'
    elif external is False:
        args += ' --internal'

    if tags is False:
        args += ' --no-tag'
    elif tags:
        if isinstance(tags, str):
            tags = [tags]
        for tag in tags:
            args += ' --tag ' + tag

    if segmentation_id:
        args += ' --provider:segmentation_id ' + segmentation_id
    if network_type:
        args += ' --provider:network_type ' + network_type
    if physical_network:
        args += ' --provider:physical_network ' + physical_network
    if avail_zone:
        args += ' --availability-zone-hint ' + avail_zone
    if qos:
        args += ' --wrs-tm:qos ' + qos

    LOG.info("Creating network: Args: {}".format(args))
    code, output = cli.openstack('network create', args, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                                 rtn_list=True)
    if code == 1:
        return 1, output

    table_ = table_parser.table(output)
    net_tenant_id = table_parser.get_value_two_col_table(table_, 'project_id')
    net_id = table_parser.get_value_two_col_table(table_, 'id')

    expt_tenant_name = tenant_name if tenant_name else common.get_tenant_name(auth_info)
    if net_tenant_id != keystone_helper.get_tenant_ids(expt_tenant_name)[0]:
        msg = "Network {} is not for tenant: {}".format(net_id, expt_tenant_name)
        raise exceptions.NeutronError(msg)

    succ_msg = "Network {} is successfully created for tenant {}".format(net_id, expt_tenant_name)
    if cleanup:
        ResourceCleanup.add('network', net_id, scope=cleanup)
    LOG.info(succ_msg)
    return 0, net_id


def create_subnet(net_id, name=None, cidr=None, gateway=None, dhcp=None, no_gateway=False, dns_servers=None,
                  alloc_pool=None, ip_version=None, subnet_pool=None, tenant_name=None, fail_ok=False, auth_info=None,
                  con_ssh=None, cleanup=''):
    """
    Create a subnet for given tenant under specified network

    Args:
        net_id (str): id of the network to create subnet for
        name (str): name of the subnet
        cidr (str): such as "192.168.3.0/24"
        tenant_name: such as tenant1, tenant2.
        gateway (str): gateway ip of this subnet
        dhcp (bool): whether or not to enable DHCP
        no_gateway (bool)
        dns_servers (str|list): DNS name servers. Such as ["147.11.57.133", "128.224.144.130", "147.11.57.128"]
        alloc_pool (dict): {'start': <start_ip>, 'end': 'end_ip'}
        ip_version (int): 4, or 6
        subnet_pool (str): ID or name of subnetpool from which this subnet will obtain a CIDR.
        fail_ok (bool):
        auth_info (dict): run the neutron subnet-create cli using these authorization info
        con_ssh (SSHClient):

    Returns (tuple): (rnt_code (int), subnet_id (str), message (str))

    """

    if cidr is None and subnet_pool is None:
        raise ValueError("Either cidr or subnet_pool has to be specified.")

    args = net_id

    if cidr:
        args += ' ' + cidr

    if name is None:
        name = get_net_name_from_id(net_id, con_ssh=con_ssh, auth_info=auth_info) + 'sub'
    name = "{}-{}".format(name, common.Count.get_subnet_count())

    args += ' --name ' + name

    if dhcp is False:
        args += ' --disable-dhcp'
    elif dhcp is True:
        args += ' --enable-dhcp'

    if isinstance(dns_servers, list):
        args += ' --dns-nameservers list=true {}'.format(' '.join(dns_servers))
    elif dns_servers is not None:
        args += ' --dns-nameserver {}'.format(dns_servers)

    if no_gateway:
        args += ' --no-gateway'
    else:
        raise ValueError("Can't have both gateway and no-gateway for subnet.")

    args_dict = {
        '--tenant-id': keystone_helper.get_tenant_ids(tenant_name, con_ssh=con_ssh)[0] if tenant_name else None,
        '--gateway': gateway,
        '--ip-version': ip_version,
        '--subnetpool': subnet_pool,
        '--allocation-pool': "start={},end={}".format(alloc_pool['start'], alloc_pool['end']) if alloc_pool else None,
        '--ipv6-ra-mode': "dhcpv6-stateful " if ip_version == 6 else None,
        '--ipv6-address-mode': "dhcpv6-stateful " if ip_version == 6 else None
    }

    for key, value in args_dict.items():
        if value is not None:
            args += ' {} {}'.format(key, value)

    LOG.info("Creating subnet for network: {}. Args: {}".format(net_id, args))
    code, output = cli.neutron('subnet-create', args, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                               rtn_list=True)

    if code == 1:
        return 1, output

    table_ = table_parser.table(output)
    subnet_tenant_id = table_parser.get_value_two_col_table(table_, 'tenant_id')
    subnet_id = table_parser.get_value_two_col_table(table_, 'id')

    expt_tenant_name = tenant_name if tenant_name else common.get_tenant_name(auth_info)
    if subnet_tenant_id != keystone_helper.get_tenant_ids(expt_tenant_name)[0]:
        msg = "Subnet {} is not for tenant: {}".format(subnet_id, expt_tenant_name)
        if fail_ok:
            LOG.warning(msg)
            return 2, subnet_id, msg
        raise exceptions.NeutronError(msg)

    succ_msg = "Subnet {} is successfully created for tenant {}".format(subnet_id, expt_tenant_name)
    if cleanup:
        ResourceCleanup.add('subnet', subnet_id, scope=cleanup)
    LOG.info(succ_msg)
    return 0, subnet_id


def delete_subnet(subnet_id, auth_info=Tenant.get('admin'), con_ssh=None, fail_ok=False):
    LOG.info("Deleting subnet {}".format(subnet_id))
    code, output = cli.neutron('subnet-delete', subnet_id, ssh_client=con_ssh, auth_info=auth_info, rtn_list=True,
                               fail_ok=True)

    if code == 1:
        return 1, output

    if subnet_id in get_subnets(auth_info=auth_info, con_ssh=con_ssh):
        msg = "Subnet {} is still listed in neutron subnet-list".format(subnet_id)
        if fail_ok:
            LOG.warning(msg)
            return 2, msg
        raise exceptions.NeutronError(msg)

    succ_msg = "Subnet {} is successfully deleted.".format(subnet_id)
    return 0, succ_msg


def update_subnet(subnet, unset=False, allocation_pool=None, dns_server=None, host_route=None, service_type=None,
                  tag=None, name=None, dhcp=None, gateway=None, description=None, auth_info=Tenant.get('admin'),
                  fail_ok=False, con_ssh=None):
    """
    set/unset given setup
    Args:
        subnet (str):
        unset (bool): set or unset
        allocation_pool (None|str|tuple|list):
        dns_server (None|str|tuple|list):
        host_route (None|str|tuple|list):
        service_type (None|str|tuple|list):
        tag (None|bool):
        name (str|None):
        dhcp (None|bool):
        gateway (str|None): valid str: <ip> or 'none'
        description:
        auth_info:
        fail_ok:
        con_ssh:

    Returns:

    """
    LOG.info("Update subnet {}".format(subnet))
    set_no = ['no', '', False]
    unset_all = ['all', True]

    arg_dict = {
        'allocation-pool': allocation_pool,
        'dns-nameserver': dns_server,
        'host-route': host_route,
        'service-type': service_type,
        'tag': tag if tag not in set_no+unset_all else None,
    }

    if unset:
        arg_dict.update(**{'all-tag': True if tag in unset_all else None})
        cmd = 'unset'
    else:
        set_only_dict = {
            'name': name,
            'dhcp': True if dhcp is True else None,
            'gateway': gateway,
            'description': description,
            'no-dhcp': True if dhcp in set_no else None,
            'no-tag': True if tag in set_no else None,
            'no-dns-nameservers': True if dns_server in set_no else None,
            'no-host-route': True if host_route in set_no else None,
            'no-allocation-pool': True if allocation_pool in set_no else None
        }
        arg_dict.update(**set_only_dict)
        cmd = 'set'

    arg_str = common.parse_args(args_dict=arg_dict, repeat_arg=True)
    arg_str += ' {}'.format(subnet)

    code, output = cli.openstack('subnet {}'.format(cmd), arg_str, ssh_client=con_ssh, auth_info=auth_info,
                                 rtn_list=True, fail_ok=fail_ok)

    if code > 0:
        return 1, output

    LOG.info("Subnet {} updated successfully".format(subnet))
    return 0, subnet


def get_subnets(name=None, cidr=None, strict=True, regex=False, rtn_val='id', auth_info=None, con_ssh=None):
    """
    Get subnets ids based on given criteria.

    Args:
        name (str): name of the subnet
        cidr (str): cidr of the subnet
        strict (bool): whether to perform strict search on given name and cidr
        regex (bool): whether to use regext to search
        rtn_val
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (list): a list of subnet ids

    """
    table_ = table_parser.table(cli.neutron('subnet-list', ssh_client=con_ssh, auth_info=auth_info))
    if name is not None:
        table_ = table_parser.filter_table(table_, strict=strict, regex=regex, name=name)
    if cidr is not None:
        table_ = table_parser.filter_table(table_, strict=strict, regex=regex, cidr=cidr)

    return table_parser.get_column(table_, rtn_val)


def get_net_info(net_id, field='status', strict=True, auto_info=Tenant.get('admin'), con_ssh=None):
    """
    Get specified info for given network

    Args:
        net_id (str): network id
        field (str): such as 'status', 'subnets'
        strict (bool): whether to perform strict search for the name of the field
        auto_info (dict):
        con_ssh (SSHClient):

    Returns (str|list): Value of the specified field. When field=subnets, return a list of subnet ids

    """
    table_ = table_parser.table(cli.neutron('net-show', net_id, ssh_client=con_ssh, auth_info=auto_info))
    value = table_parser.get_value_two_col_table(table_, field, strict=strict, merge_lines=False)

    if field == 'subnets':
        if isinstance(value, str):
            value = [value]

    return value


def get_net_show_values(net_id, fields, strict=True, rtn_dict=False, con_ssh=None):
    if isinstance(fields, str):
        fields = [fields]
    table_ = table_parser.table(cli.openstack('network show', net_id, ssh_client=con_ssh))
    res = {}
    for field in fields:
        val = table_parser.get_value_two_col_table(table_, field, strict=strict, merge_lines=True)
        if field == 'subnets':
            val = val.split(',')
            val = [val_.strip() for val_ in val]
        res[field] = val

    if rtn_dict:
        return res
    else:
        return list(res.values())


def set_network(net_id, name=None, enable=None, share=None, enable_port_security=None, external=None, default=None,
                provider_net_type=None, provider_phy_net=None, provider_segment=None, transparent_vlan=None,
                auth_info=Tenant.get('admin'), fail_ok=False, con_ssh=None, **kwargs):
    """
    Update network with given parameters
    Args:
        net_id (str):
        name (str|None): name to update to. Don't update name when None.
        enable (bool|None): True to add --enable. False to add --disable. Don't update enable/disable when None.
        share (bool|None):
        enable_port_security (bool|None):
        external (bool|None):
        default (bool|None):
        provider_net_type (str|None):
        provider_phy_net (str|None):
        provider_segment (str|int|None):
        transparent_vlan (bool|None):
        auth_info (dict):
        fail_ok (bool):
        con_ssh (SSHClient):
        **kwargs: additional key/val pairs that are not listed in 'openstack network update -h'.
            e,g.,{'wrs-tm:qos': <qos_id>}

    Returns (tuple): (code, msg)
        (0, "Network <net_id> is successfully updated")   Network updated successfully
        (1, <std_err>)    'openstack network update' cli is rejected

    """
    args_dict = {
        '--name': (name, {'name': name}),
        '--enable': ('store_true' if enable is True else None, {'admin_state_up': 'UP'}),
        '--disable': ('store_true' if enable is False else None, {'admin_state_up': 'DOWN'}),
        '--share': ('store_true' if share is True else None, {'shared': 'True'}),
        '--no-share': ('store_true' if share is False else None, {'shared': 'False'}),
        '--enable-port-security': ('store_true' if enable_port_security is True else None, {}),
        '--disable-port-security': ('store_true' if enable_port_security is False else None, {}),
        '--external': ('store_true' if external is True else None, {'router:external': 'External'}),
        '--internal': ('store_true' if external is False else None, {'router:external': 'Internal'}),
        '--default': ('store_true' if default is True else None, {'is_default': 'True'}),
        '--no-default': ('store_true' if default is False else None, {'is_default': 'False'}),
        '--transparent-vlan': ('store_true' if transparent_vlan is True else None, {'vlan_transparent': 'True'}),
        '--no-transparent-vlan': ('store_true' if transparent_vlan is False else None, {'vlan_transparent': 'False'}),
        '--provider-network-type': (provider_net_type, {'provider:network_type': provider_net_type}),
        '--provider-physical-network': (provider_phy_net, {'provider:physical_network': provider_phy_net}),
        '--provider-segment': (provider_segment, {'provider:segmentation_id': provider_segment}),
    }
    checks = {}
    args_str = ''
    for arg in args_dict:
        val, check = args_dict[arg]
        if val is not None:
            set_val = '' if val == 'store_true' else ' {}'.format(val)
            args_str += ' {}{}'.format(arg, set_val)
            if check:
                checks.update(**check)
            else:
                LOG.info("Unknown check field in 'openstack network show' for arg {}".format(arg))

    for key, val_ in kwargs.items():
        val_ = ' {}'.format(val_) if val_ else ''
        field_name = key.split('--', 1)[-1]
        arg = '--{}'.format(field_name)
        args_str += ' {}{}'.format(arg, val_)
        if val_:
            checks.update(**kwargs)
        else:
            LOG.info("Unknown check field in 'openstack network show' for arg {}".format(arg))

    if not args_str:
        raise ValueError("Nothing to update. Please specify at least one None value")

    LOG.info("Attempt to update network {} with following args: {}".format(net_id, args_str))
    code, out = cli.openstack('network set', '{} {}'.format(args_str, net_id), ssh_client=con_ssh, rtn_list=True,
                              fail_ok=fail_ok, auth_info=auth_info)
    if code > 0:
        return 1, out

    if checks:
        LOG.info("Check the values are updated to following in network show: {}".format(checks))
        actual_res = get_net_show_values(net_id, fields=list(checks.keys()), rtn_dict=True)
        failed = {}
        for field in checks:
            expt_val = checks[field]
            actual_val = actual_res[field]
            if expt_val != actual_val:
                failed[field] = (expt_val, actual_val)

        # Fail directly. If a field is not allowed to be updated, the cli should be rejected
        assert not failed, "Actual value is different than set value in following fields: {}".format(failed)

    msg = "Network {} is successfully updated".format(net_id)
    return 0, msg


def __compose_args(optional_args_dict, *other_args):
    args = []
    for key, val in optional_args_dict.items():
        if val is not None:
            arg = key + ' ' + val
            args.append(arg)
    return ' '.join(args + list(other_args))


def create_security_group(name, project=None, description=None, auth_info=None, fail_ok=False, cleanup='function'):
    """
    Create a security group
    Args:
        name (str):
        description (str):
        auth_info (dict):
            create under this project
        fail_ok (bool):
        cleanup (str):

    Returns (str|tuple):
        str identifier for the newly created security group
        or if fail_ok=True, return tuple:
        (0, identifier) succeeded
        (1, msg) failed
    """
    if auth_info is None:
        auth_info = Tenant.get_primary()

    args_dict = {
        # '--project-domain': auth_info["region"],
        '--descritpion': description
    }

    if project is not None:
        args_dict['--project'] = project

    table_ = cli.openstack("security group create", __compose_args(args_dict, name),
                           fail_ok=fail_ok, auth_info=auth_info)
    if fail_ok:
        code, table_ = table_
        if code:
            return code, table_
    table_ = table_parser.table(table_)
    identifier = table_parser.get_value_two_col_table(table_, 'id')
    if cleanup:
        ResourceCleanup.add('security_group', identifier, scope=cleanup)
    LOG.info("Security group created: name={} id={}".format(name, identifier))
    if fail_ok:
        return 0, identifier
    return identifier


def delete_security_group(group_id, fail_ok=False, auth_info=Tenant.get('admin')):
    """
    Delete a security group
    Args:
        group_id (str): security group to be deleted
        auth_info (dict):

    Returns (tuple): (code, msg)
        (0, msg): succeeded
        (1, err_msg): failed
    """
    LOG.info("Deleting security group {}".format(group_id))
    return cli.openstack("security group delete", group_id, fail_ok=fail_ok, auth_info=auth_info)


def update_net_qos(net_id, qos_id=None, fail_ok=False, auth_info=Tenant.get('admin'), con_ssh=None):
    """
    Update network qos to given value
    Args:
        net_id (str): network to update
        qos_id (str|None): when None, remove the qos from network
        fail_ok (bool):
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (tuple): (code, msg)
        (0, "Network <net_id> qos is successfully updated to <qos_id>")
        (1, <std_err>)  openstack network update cli rejected

    """
    if qos_id:
        kwargs = {'--wrs-tm:qos': qos_id}
        arg_str = '--wrs-tm:qos {}'.format(qos_id)
    else:
        kwargs = {'--no-qos': None}
        arg_str = '--no-qos'

    # code, msg = update_network(net_id=net_id, fail_ok=fail_ok, auth_info=auth_info, con_ssh=con_ssh, **kwargs)

    code, msg = cli.neutron('net-update', '{} {}'.format(arg_str, net_id), fail_ok=fail_ok, ssh_client=con_ssh,
                            auth_info=auth_info, rtn_list=True)
    if code > 0:
        return code, msg

    if '--no-qos' in kwargs:
        actual_qos = get_net_info(net_id, field='wrs-tm:qos', auto_info=auth_info, con_ssh=con_ssh)
        assert not actual_qos, "Qos {} is not removed from {}".format(actual_qos, net_id)

    msg = "Network {} qos is successfully updated to {}".format(net_id, qos_id)
    LOG.info(msg)
    return 0, msg


def _get_net_ids(net_name, con_ssh=None, auth_info=None):
    table_ = table_parser.table(cli.neutron('net-list', ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_values(table_, 'id', name=net_name)


def get_net_name_from_id(net_id, con_ssh=None, auth_info=None):
    """
    Get network name from id

    Args:
        net_id (str):
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (str): name of a network

    """
    table_ = table_parser.table(cli.neutron('net-list', ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_values(table_, 'name', id=net_id)[0]


def get_net_id_from_name(net_name, con_ssh=None, auth_info=None):
    """
    Get network id from full name

    Args:
        net_name (str):
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (str): id of a network

    """
    table_ = table_parser.table(cli.neutron('net-list', ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_values(table_, 'id', strict=True, name=net_name)[0]


def get_ext_networks(con_ssh=None, auth_info=None):
    """
    Get ids of external networks

    Args:
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (list): list of ids of external networks

    """
    table_ = table_parser.table(cli.neutron('net-external-list', ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_column(table_, 'id')


def create_floating_ip(extnet_id=None, tenant_name=None, port_id=None, fixed_ip_addr=None, vm_id=None,
                       floating_ip_addr=None, fail_ok=False, con_ssh=None, auth_info=None):
    """
    Create a floating ip for given tenant

    Args:
       extnet_id (str): id of external network
       tenant_name (str): name of the tenant to create floating ip for. e.g., 'tenant1', 'tenant2'
       port_id (str): id of the port
       fixed_ip_addr (str): fixed ip address. such as 192.168.x.x
       vm_id (str): id of the vm to associate the created floating ip to. This arg will not be used if port_id is set
       floating_ip_addr (str): specific floating ip to create
       fail_ok (bool):
       con_ssh (SSHClient):
       auth_info (dict):

    Returns (str): floating IP. such as 192.168.x.x

    """
    if extnet_id is None:
        extnet_id = get_ext_networks(con_ssh=con_ssh)[0]
    args = extnet_id

    if tenant_name is not None:
        tenant_id = keystone_helper.get_tenant_ids(tenant_name=tenant_name, con_ssh=con_ssh)[0]
        args += " --tenant-id {}".format(tenant_id)

    # process port info
    if port_id is not None:
        args += " --port-id {}".format(port_id)
        if fixed_ip_addr is not None:
            args += " --fixed-ip-address {}".format(fixed_ip_addr)
    else:
        if vm_id is not None:
            vm_ip = get_mgmt_ips_for_vms(vm_id, con_ssh=con_ssh)[0]
            port = get_vm_port(vm=vm_id, con_ssh=con_ssh, vm_val='id')
            args += "--port-id {} --fixed-ip-address {}".format(port, vm_ip)

    if floating_ip_addr is not None:
        args += " --floating-ip-address {}".format(floating_ip_addr)

    code, output = cli.neutron(cmd='floatingip-create', positional_args=args, ssh_client=con_ssh, auth_info=auth_info,
                               fail_ok=fail_ok, rtn_list=True)
    if code == 1:
        return 1, output

    table_ = table_parser.table(output)
    actual_fip_addr = table_parser.get_value_two_col_table(table_, "floating_ip_address")

    if not actual_fip_addr:
        msg = "Floating IP is not found in the list"
        if fail_ok:
            LOG.warning(msg)
            return 2, msg
        raise exceptions.NeutronError(msg)

    if floating_ip_addr is not None and actual_fip_addr != floating_ip_addr:
        msg = "Floating IP address required: {}, actual: {}".format(floating_ip_addr, actual_fip_addr)
        if fail_ok:
            LOG.warning(msg)
            return 3, msg
        raise exceptions.NeutronError(msg)

    succ_msg = "Floating IP created successfully: {}".format(actual_fip_addr)
    LOG.info(succ_msg)
    return 0, actual_fip_addr


def delete_floating_ip(floating_ip, fip_val='ip', auth_info=Tenant.get('admin'), con_ssh=None, fail_ok=False):
    """
    Delete a floating ip

    Args:
        floating_ip (str): floating ip to delete.
        fip_val (str): value type of the floating ip provided. 'ip' or 'id'
        auth_info (dict):
        con_ssh (SSHClient):
        fail_ok (bool): whether to raise exception if fail to delete floating ip

    Returns (tuple): (rtn_code(int), msg(str))
        - (0, Floating ip <ip> is successfully deleted.)
        - (1, <stderr>)
        - (2, Floating ip <ip> still exists in floatingip-list.)

    """
    if fip_val == 'ip':
        floating_ip = get_floating_ids_from_ips(floating_ips=floating_ip, auth_info=Tenant.get('admin'), con_ssh=con_ssh)
    args = floating_ip

    code, output = cli.neutron('floatingip-delete', positional_args=args, ssh_client=con_ssh, auth_info=auth_info,
                               fail_ok=fail_ok, rtn_list=True)

    if code == 1:
        return 1, output

    post_deletion_ips = get_floating_ids_from_ips(con_ssh=con_ssh, auth_info=Tenant.get('admin'))
    if floating_ip in post_deletion_ips:
        msg = "Floating ip {} still exists in floatingip-list.".format(floating_ip)
        if fail_ok:
            LOG.warning(msg)
            return 2, msg
        raise exceptions.NeutronError(msg)

    succ_msg = "Floating ip {} is successfully deleted.".format(floating_ip)
    LOG.info(succ_msg)
    return 0, succ_msg


def get_floating_ips(fixed_ip=None, port_id=None, auth_info=Tenant.get('admin'), con_ssh=None):
    """
    Get all floating ips.

    Args:
        fixed_ip (str): fixed ip address
        port_id (str): port id
        auth_info (dict): if tenant auth_info is given instead of admin, only floating ips for this tenant will be
            returned.
        con_ssh (SSHClient):

    Returns (list): list of floating ips

    """
    table_ = table_parser.table(cli.neutron('floatingip-list', ssh_client=con_ssh, auth_info=auth_info))
    if not table_['headers']:  # no floating ip listed
        return []

    params_dict = {}
    if fixed_ip is not None:
        params_dict['fixed_ip_address'] = fixed_ip
    if port_id is not None:
        params_dict['port_id'] = port_id

    fips = table_parser.get_values(table_, 'floating_ip_address', **params_dict)
    LOG.info("Floating ips: {}".format(fips))
    return table_parser.get_values(table_, 'floating_ip_address', **params_dict)


def get_floating_ids_from_ips(floating_ips=None, con_ssh=None, auth_info=Tenant.get('admin')):
    """
    Get ids of floating ips

    Args:
        floating_ips (list|str): floating ip(s) to convert to id(s). If None, all floating ip ids will be returned.
        con_ssh:
        auth_info:

    Returns (list): list of id(s) of floating ip(s)

    """
    table_ = table_parser.table(cli.neutron('floatingip-list', ssh_client=con_ssh, auth_info=auth_info))
    if not table_['headers']:           # no floating ip listed
        return []

    if floating_ips is not None:
        table_ = table_parser.filter_table(table_, **{'floating_ip_address': floating_ips})
    return table_parser.get_column(table_, 'id')


def get_floating_ip_info(fip, fip_val='ip', field='fixed_ip_address', auth_info=Tenant.get('admin'), con_ssh=None):
    """
    Get floating ip info for given field.
    Args:
        fip (str):
        fip_val (str): 'ip' or 'id'
        field (str): field in "neutron floatingip-show" table.
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (str): value of given field for specific floating ip

    """
    if fip_val == 'ip':
        fips = get_floating_ids_from_ips(floating_ips=fip, con_ssh=con_ssh, auth_info=auth_info)
        if not fips:
            raise exceptions.NeutronError("floating ip {} cannot be found".format(fip))
        fip = fips[0]

    table_ = table_parser.table(cli.neutron('floatingip-show', fip, ssh_client=con_ssh, auth_info=auth_info))
    val = table_parser.get_value_two_col_table(table_, field)
    val = None if val in ['None', '', 'none'] else val
    return val


def disassociate_floating_ip(floating_ip, fip_val='ip', auth_info=Tenant.get('admin'), con_ssh=None, fail_ok=False):
    """
    Disassociate a floating ip

    Args:
        floating_ip (str): ip or id of the floating ip
        fip_val (str): type of the value of floating ip. 'ip' or 'id'
        auth_info (dict):
        con_ssh (SSHClient):
        fail_ok (bool):

    Returns (tuple): (rtn_code(int), msg(str))
        (0, "Floating ip <ip> is successfully disassociated with fixed ip")
        (1, <stderr>)

    """
    if fip_val == 'ip':
        floating_ip = get_floating_ids_from_ips(floating_ips=floating_ip, auth_info=Tenant.get('admin'), con_ssh=con_ssh)[0]
    args = floating_ip
    code, output = cli.neutron('floatingip-disassociate', args, ssh_client=con_ssh, auth_info=auth_info,
                               fail_ok=fail_ok, rtn_list=True)

    if code == 1:
        return 1, output

    fixed_ip = get_floating_ip_info(floating_ip, fip_val='id', field='fixed_ip_address', auth_info=auth_info,
                                    con_ssh=con_ssh)
    if fixed_ip is not None:
        err_msg = "Fixed ip address is {} instead of None for floating ip {}".format(fixed_ip, floating_ip)
        if fail_ok:
            return 2, err_msg
        else:
            raise exceptions.NeutronError(err_msg)

    succ_msg = "Floating ip {} is successfully disassociated with fixed ip".format(floating_ip)
    LOG.info(succ_msg)
    return 0, succ_msg


def associate_floating_ip(floating_ip, vm_id, fip_val='ip', vm_ip=None, auth_info=Tenant.get('admin'), con_ssh=None,
                          fail_ok=False):
    """
    Associate a floating ip to management net ip of given vm.

    Args:
        floating_ip (str): ip or id of the floating ip
        vm_id (str): vm id
        fip_val (str): ip or id
        vm_ip (str): management ip of a vm used to find the matching port to attach floating ip to
        auth_info (dict):
        con_ssh (SSHClient):
        fail_ok (bool):

    Returns (tuple): (rtn_code(int), msg(str))
        (0, "port <port_id> is successfully associated with floating ip <floatingip_id>")
        (1, <stderr>)

    """
    # get vm management ip if not given
    if vm_ip is None:
        vm_ip = get_mgmt_ips_for_vms(vm_id, con_ssh=con_ssh)[0]
    args = '--fixed-ip-address {}'.format(vm_ip)

    # convert floatingip to id
    fip_ip = None
    if fip_val == 'ip':
        fip_ip = floating_ip
        floating_ip = get_floating_ids_from_ips(floating_ips=floating_ip, auth_info=Tenant.get('admin'), con_ssh=con_ssh)[0]
    args += ' ' + floating_ip

    port = get_vm_port(vm=vm_ip, vm_val='ip', con_ssh=con_ssh)
    args += ' ' + port

    code, output = cli.neutron('floatingip-associate', args, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                               rtn_list=True)
    if code == 1:
        return 1, output

    succ_msg = "port {} is successfully associated with floating ip {}".format(port, floating_ip)

    if fip_val != 'ip':
        fip_ip = get_floating_ip_info(floating_ip, fip_val='id', field='floating_ip_address', con_ssh=con_ssh)
    _wait_for_ip_in_nova_list(vm_id, ip_addr=fip_ip, fail_ok=False, con_ssh=con_ssh)

    LOG.info(succ_msg)
    return 0, succ_msg


# TODO reduce timeout to 30s after issue fixed.
def _wait_for_ip_in_nova_list(vm_id, ip_addr, timeout=300, fail_ok=False, con_ssh=None, auth_info=Tenant.get('admin')):
    end_time = time.time() + timeout
    while time.time() < end_time:
        table_ = table_parser.table(cli.nova('list --a', ssh_client=con_ssh, auth_info=auth_info))
        if ip_addr in table_parser.get_values(table_, 'Networks', ID=vm_id, merge_lines=True)[0]:
            return True

    else:
        msg = "ip address {} is not found in nova show {} within {} seconds".format(ip_addr, vm_id, timeout)
        if fail_ok:
            return False
        raise exceptions.TimeoutException(msg)


def get_vm_port(vm, vm_val='id', con_ssh=None, auth_info=Tenant.get('admin')):
    """
    Get port id of a vm

    Args:
        vm (str): id or management ip of a vm
        vm_val (str): 'id' or 'ip'
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (str): id of a port

    """
    if vm_val == 'id':
        vm = get_mgmt_ips_for_vms(vms=vm, con_ssh=con_ssh)[0]

    table_ = table_parser.table(cli.neutron('port-list', ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_values(table_, 'id', strict=False, fixed_ips=vm+'"')[0]


def get_neutron_port(name=None, con_ssh=None, auth_info=None):
    """
    Get the neutron port list based on name if given for a given tenant.

    Args:
        con_ssh (SSHClient): If None, active controller ssh will be used.
        auth_info (dict): Tenant dict. If None, primary tenant will be used.
        name (str): Given name for the port

    Returns (str): Neutron port id of a specific tenant.

    """
    table_ = table_parser.table(cli.neutron('port-list', ssh_client=con_ssh, auth_info=auth_info))
    if name is None:
        return table_parser.get_values(table_, 'id')

    return table_parser.get_values(table_, 'id', strict=False, name=name)


def get_providernets(name=None, rtn_val='id', con_ssh=None, strict=False, regex=False, auth_info=Tenant.get('admin'),
                     merge_lines=False, **kwargs):
    """
    Get the neutron provider net list based on name if given

    Args:
        rtn_val (str): id or name
        con_ssh (SSHClient): If None, active controller ssh will be used.
        auth_info (dict): Tenant dict. If None, primary tenant will be used.
        name (str): Given name for the provider network to filter
        strict (bool): Whether to perform strict search on provider net name or kwargs values
        regex (bool): Whether to use regex to perform search on given values
        merge_lines

    Returns (str): Neutron provider net ids

    """
    table_ = table_parser.table(cli.neutron('providernet-list', ssh_client=con_ssh, auth_info=auth_info))
    if name is None:
        return table_parser.get_values(table_, rtn_val, merge_lines=merge_lines, **kwargs)

    return table_parser.get_values(table_, rtn_val, strict=strict, regex=regex, name=name, merge_lines=merge_lines,
                                   **kwargs)


def get_providernet_ranges(rtn_val='name', range_name=None, providernet_name=None, providernet_type=None, strict=False,
                           auth_info=Tenant.get('admin'), con_ssh=None):
    """

    Args:
        rtn_val (str): 'name' or 'id'
        range_name (str):
        providernet_name (str):
        providernet_type (str):
        strict (bool):
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (list): list of range names or ids

    """

    table_ = table_parser.table(cli.neutron('providernet-range-list', ssh_client=con_ssh, auth_info=auth_info))

    kwargs = {}
    if providernet_name is not None:
        kwargs['providernet'] = providernet_name

    if range_name is not None:
        kwargs['name'] = range_name

    if providernet_type is not None:
        kwargs['type'] = providernet_type

    return table_parser.get_values(table_, rtn_val, strict=strict, **kwargs)


def get_providernet_ranges_dict(providernet_name=None, con_ssh=None, auth_info=Tenant.get('admin')):
    """
    Get the neutron provider net ranges based on name if given for ADMIN user.

    Args:
        con_ssh (SSHClient): If None, active controller ssh will be used.
        auth_info (dict): Tenant dict. If None, primary tenant will be used.
        providernet_name (str): Given name for the provider network to filter

    Returns (dict): Neutron provider network ranges of admin user.

    """
    table_ = table_parser.table(cli.neutron('providernet-list', ssh_client=con_ssh, auth_info=auth_info))
    if providernet_name is None:
        ranges = table_parser.get_values(table_, 'ranges')
    else:
        ranges = table_parser.get_values(table_, 'ranges', strict=False, name=providernet_name)

    return ranges


def get_security_group(name=None, con_ssh=None, auth_info=None):
    """
        Get the neutron security group list based on name if given for given user.

        Args:
            con_ssh (SSHClient): If None, active controller ssh will be used.
            auth_info (dict): Tenant dict. If None, primary tenant will be used.
            name (str): Given name for the security group to filter

        Returns (str): Neutron security group id.

    """
    table_ = table_parser.table(cli.neutron('security-group-list', ssh_client=con_ssh, auth_info=auth_info))
    if name is None:
        return table_parser.get_values(table_, 'id')

    return table_parser.get_values(table_, 'id', strict=False, name=name)


def get_qos(name=None, con_ssh=None, auth_info=None):
    """
        Get the neutron qos list based on name if given for given user.

        Args:
            con_ssh (SSHClient): If None, active controller ssh will be used.
            auth_info (dict): Tenant dict. If None, primary tenant will be used.
            name (str): Given name for the qos list to filter
        Returns (str): Neutron qos policy id.

    """
    table_ = table_parser.table(cli.neutron('qos-list', ssh_client=con_ssh, auth_info=auth_info))
    if name is None:
        return table_parser.get_values(table_, 'id')

    return table_parser.get_values(table_, 'id', strict=False, name=name)


def get_qos_names(qos_ids=None, con_ssh=None, auth_info=None):
    """

    Args:
        qos_ids(str|list|None): QoS id to filter name.
        con_ssh(SSHClient):  If None, active controller ssh will be used.
        auth_info(dict): Tenant dict. If None, primary tenant will be used.

    Returns(list): List of neutron qos names filtered by qos_id.

    """
    table_ = table_parser.table(cli.neutron('qos-list', ssh_client=con_ssh, auth_info=auth_info))

    if qos_ids is None:
        return table_parser.get_column(table_, 'name')

    return table_parser.get_values(table_, 'name', strict=True, id=qos_ids)


def create_qos(name=None, tenant_name=None, description=None, scheduler=None, dscp=None, ratelimit=None, fail_ok=False,
               con_ssh=None, auth_info=Tenant.get('admin'), cleanup='function'):
    """
    Args:
        name(str): Name of the QoS to be created.
        tenant_name(str): Such as tenant1, tenant2. If none uses primary tenant.
        description(str): Description of the created QoS.
        scheduler(dict): Dictionary of scheduler policies formatted as {'policy': value}.
        dscp(dict): Dictionary of dscp policies formatted as {'policy': value}.
        ratelimit(dict): Dictionary of ratelimit policies formatted as {'policy': value}.
        fail_ok(bool):
        con_ssh(SSHClient):
        auth_info(dict): Run the neutron qos-create cli using this authorization info. Admin by default,
        cleanup (str):

    Returns(tuple): exit_code(int), qos_id(str)
                    (0, qos_id) qos successfully created.
                    (1, output) qos not created successfully
    """
    tenant_id = keystone_helper.get_tenant_ids(tenant_name=tenant_name, con_ssh=con_ssh)[0]
    check_dict = {}
    args = ''
    current_qos = get_qos_names(con_ssh=con_ssh, auth_info=auth_info)
    if name is None:
        if tenant_name is None:
            tenant_name = common.get_tenant_name(Tenant.get_primary())
            name = common.get_unique_name("{}-qos".format(tenant_name), existing_names=current_qos, resource_type='qos')
        else:
            name = common.get_unique_name("{}-qos".format(tenant_name), existing_names=current_qos, resource_type='qos')
    args_dict = {'name': name,
                 'tenant-id': tenant_id,
                 'description': description,
                 'scheduler': scheduler,
                 'dscp': dscp,
                 'ratelimit': ratelimit
                 }
    check_dict['policies'] = {}
    for key, value in args_dict.items():
        if value:
            if key in ('scheduler', 'dscp', 'ratelimit'):
                args += " --{}".format(key)
                for policy, val in value.items():
                    args += " {}={}".format(policy, val)
                    value[policy] = str(val)
                check_dict['policies'][key] = value
            else:
                args += " --{} '{}'".format(key, value)
                if key is 'tenant-id':
                    key = 'tenant_id'
                check_dict[key] = value

    LOG.info("Creating QoS with args: {}".format(args))
    exit_code, output = cli.neutron('qos-create', args, ssh_client=con_ssh, fail_ok=fail_ok, auth_info=auth_info,
                                    rtn_list=True)
    if exit_code == 1:
        return 1, output

    table_ = table_parser.table(output)
    for key, exp_value in check_dict.items():
        if key is 'policies':
            actual_value = eval(table_parser.get_value_two_col_table(table_, key))
        else:
            actual_value = table_parser.get_value_two_col_table(table_, key)
        if actual_value != exp_value:
            msg = "Qos created but {} expected to be {} but actually {}".format(key, exp_value, actual_value)
            raise exceptions.NeutronError(msg)

    qos_id = table_parser.get_value_two_col_table(table_, 'id')
    if cleanup:
        ResourceCleanup.add('network_qos', qos_id, scope=cleanup)
    LOG.info("QoS successfully created")
    return 0, qos_id


def delete_qos(qos_id, auth_info=Tenant.get('admin'), con_ssh=None, fail_ok=False):
    """

    Args:
        qos_id(str): QoS to be deleted
        auth_info(dict): tenant to be used, if none admin will be used
        con_ssh(SSHClient):
        fail_ok(bool):

    Returns: code(int), output(string)
            (0, "QoS <qos_id> successfully deleted" )
            (1, <std_err>)  openstack qos delete cli rejected
    """

    LOG.info("deleting QoS: {}".format(qos_id))
    code, output = cli.neutron('qos-delete', qos_id, auth_info=auth_info, ssh_client=con_ssh, fail_ok=fail_ok,
                               rtn_list=True)
    if code == 1:
        return 1, output

    if qos_id in get_qos(auth_info=auth_info, con_ssh=con_ssh):
        msg = "QoS {} still listed in neutron QoS list".format(qos_id)
        raise exceptions.NeutronError(msg)

    succ_msg = "QoS {} successfully deleted".format(qos_id)
    LOG.info(succ_msg)
    return 0, succ_msg


def get_internal_net_id(net_name=None, strict=False, con_ssh=None, auth_info=None):
    """
    Get internal network id that matches the given net_name of a specific tenant.

    Args:
        net_name (str): name of the internal network. This can be a substring of the tenant net name, such as 'net1',
            and it will return id for internal0-net1
        strict (bool): Whether to perform strict search on given net_name
        con_ssh (SSHClient):
        auth_info (dict): If None, primary tenant will be used.

    Returns (str): A tenant network id for given tenant network name.
        If multiple ids matches the given name, only the first will return

    """
    net_ids = get_internal_net_ids(net_names=net_name, strict=strict, con_ssh=con_ssh, auth_info=auth_info)
    if not net_ids:
        LOG.warning("No network found with name {}".format(net_name))
        return ''

    return net_ids[0]


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
    mgmt_ids = _get_net_ids(mgmt_net_name, con_ssh=con_ssh, auth_info=auth_info)
    if not mgmt_ids:
        raise exceptions.TiSError("No {} found via 'neutron net-list'. Please set up system".format(mgmt_net_name))
    return mgmt_ids[0]


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
    if not net_ids:
        LOG.warning("No network found with name {}".format(net_name))
        return ''

    return net_ids[0]


def get_tenant_net_ids(net_names=None, con_ssh=None, auth_info=None, rtn_val='id'):
    """
    Get a list of tenant network ids that match the given net_names for a specific tenant.

    Args:
        net_names (str or list): list of tenant network name(s) to get id(s) for
        con_ssh (SSHClient):
        auth_info (dict): If None, primary tenant will be used
        rtn_val (str): id or name

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
        return table_parser.get_column(table_, rtn_val)


def get_internal_net_ids(net_names=None, strict=False, regex=True, con_ssh=None, auth_info=None):
    """
    Get a list of internal network ids that match the given net_names for a specific tenant.

    Args:
        net_names (str or list): list of internal network name(s) to get id(s) for
        strict (bool): whether to perform a strict search on  given name
        regex (bool): whether to search using regular expression
        con_ssh (SSHClient):
        auth_info (dict): If None, primary tenant will be used

    Returns (list): list of tenant nets. such as (<id for tenant2-net1>, <id for tenant2-net8>)

    """
    table_ = table_parser.table(cli.neutron('net-list', ssh_client=con_ssh, auth_info=auth_info))
    if net_names is None:
        name = 'internal'
        return table_parser.get_values(table_, 'id', strict=False, name=name)
    else:
        if isinstance(net_names, str):
            net_names = [net_names]

        for i in range(len(net_names)):
            net_name = net_names[i]
            if 'internal' not in net_name:
                net_names[i] = 'internal.*{}'.format(net_name)

        table_ = table_parser.filter_table(table_, name=net_names, strict=strict, regex=regex)
        return table_parser.get_column(table_, 'id')


def get_data_ips_for_vms(vms=None, con_ssh=None, auth_info=Tenant.get('admin'), rtn_dict=False, exclude_nets=None):
    """
    This function returns the management IPs for all VMs on the system.
    We make the assumption that the management IPs start with "192".
    Args:
        vms (str|list|None): vm ids list. If None, management ips for ALL vms with given Tenant(via auth_info) will be
            returned.
        con_ssh (SSHClient): active controller SSHClient object
        auth_info (dict): use admin by default unless specified
        rtn_dict (bool): return list if False, return dict if True
        exclude_nets (list|str) network name(s) - exclude ips from given network name(s)

    Returns (list|dict):
        a list of all VM management IPs   # rtn_dict=False
        dictionary with vm IDs as the keys, and mgmt ips as values    # rtn_dict=True
    """
    return _get_net_ips_for_vms(netname_pattern=Networks.data_net_name_pattern(), ip_pattern=Networks.DATA_IP, vms=vms,
                                con_ssh=con_ssh, auth_info=auth_info, rtn_dict=rtn_dict, exclude_nets=exclude_nets)


def get_internal_ips_for_vms(vms=None, con_ssh=None, auth_info=Tenant.get('admin'), rtn_dict=False, exclude_nets=None):
    """
    This function returns the management IPs for all VMs on the system.
    We make the assumption that the management IPs start with "192".
    Args:
        vms (str|list|None): vm ids list. If None, management ips for ALL vms with given Tenant(via auth_info) will be
            returned.
        con_ssh (SSHClient): active controller SSHClient object
        auth_info (dict): use admin by default unless specified
        rtn_dict (bool): return list if False, return dict if True
        exclude_nets (list|str) network name(s) - exclude ips from given network name(s)

    Returns (list|dict):
        a list of all VM management IPs   # rtn_dict=False
        dictionary with vm IDs as the keys, and mgmt ips as values    # rtn_dict=True
    """
    return _get_net_ips_for_vms(netname_pattern=Networks.INTERNAL_NET_NAME, ip_pattern=Networks.INTERNAL_IP, vms=vms,
                                con_ssh=con_ssh, auth_info=auth_info, rtn_dict=rtn_dict, use_fip=False,
                                exclude_nets=exclude_nets)


def get_external_ips_for_vms(vms=None, con_ssh=None, auth_info=Tenant.get('admin'), rtn_dict=False, exclude_nets=None):
    return _get_net_ips_for_vms(netname_pattern=Networks.mgmt_net_name_pattern(), ip_pattern=Networks.EXT_IP, vms=vms,
                                con_ssh=con_ssh, auth_info=auth_info, rtn_dict=rtn_dict, exclude_nets=exclude_nets)


def get_mgmt_ips_for_vms(vms=None, con_ssh=None, auth_info=Tenant.get('admin'), rtn_dict=False, exclude_nets=None):
    """
    This function returns the management IPs for all VMs on the system.
    We make the assumption that the management IP pattern is "192.168.xxx.x(xx)".
    Args:
        vms (str|list|None): vm ids list. If None, management ips for ALL vms with given Tenant(via auth_info) will be
            returned.
        con_ssh (SSHClient): active controller SSHClient object
        auth_info (dict): use admin by default unless specified
        rtn_dict (bool): return list if False, return dict if True
        exclude_nets (list|str) network name(s) - exclude ips from given network name(s)

    Returns (list|dict):
        a list of all VM management IPs   # rtn_dict=False
        dictionary with vm IDs as the keys, and mgmt ips as values    # rtn_dict=True
    """
    return _get_net_ips_for_vms(netname_pattern=Networks.mgmt_net_name_pattern(), ip_pattern=Networks.MGMT_IP, vms=vms,
                                con_ssh=con_ssh, auth_info=auth_info, rtn_dict=rtn_dict, exclude_nets=exclude_nets)


def _get_net_ips_for_vms(netname_pattern, ip_pattern, vms=None, con_ssh=None, auth_info=Tenant.get('admin'), rtn_dict=False,
                         use_fip=False, exclude_nets=None):

    table_ = table_parser.table(cli.nova('list', '--all-tenants', ssh_client=con_ssh, auth_info=auth_info))
    if vms:
        table_ = table_parser.filter_table(table_, ID=vms)
    elif vms is not None:
        raise ValueError("Invalid value for vms: {}".format(vms))
    all_ips = []
    all_ips_dict = {}
    ip_reg = re.compile(ip_pattern)
    vm_ids = table_parser.get_column(table_, 'ID')
    if not vm_ids:
        raise ValueError("No vm is on the system. Please boot vm(s) first.")
    vms_nets = table_parser.get_column(table_, 'Networks')
    #
    # if use_fip:
    #     floatingips = get_floating_ips(auth_info=Tenant.get_tenant('admin'), con_ssh=con_ssh)

    if exclude_nets:
        if isinstance(exclude_nets, str):
            exclude_nets = [exclude_nets]

    for i in range(len(vm_ids)):
        vm_id = vm_ids[i]
        vm_nets = vms_nets[i].split(sep=';')
        targeted_ips_str = ''
        for vm_net in vm_nets:

            if exclude_nets:
                for net_to_exclude in exclude_nets:
                    if net_to_exclude in vm_net:
                        LOG.info("Excluding IPs from {}".format(net_to_exclude))
                        continue
            # find ips
            if re.search(netname_pattern, vm_net):
                targeted_ips_str += vm_net

        if not targeted_ips_str:
            LOG.warning("No network found for vm {} with net name sub-string: {}".format(vm_id, netname_pattern))
            continue

        ips_for_vm = ip_reg.findall(targeted_ips_str)
        if not ips_for_vm:
            LOG.warning("No ip found for vm {} with pattern {}".format(vm_id, ip_pattern))
            continue

        LOG.debug('targeted_ip_str: {}, ips for vm: {}'.format(targeted_ips_str, ips_for_vm))
        # if use_fip:
        #     vm_fips = []
        #     # ping floating ips only if any associated to vm, otherwise ping all the ips
        #     if len(ips_for_vm) > 1:
        #         for ip in ips_for_vm:
        #             if ip in floatingips:
        #                 vm_fips.append(ip)
        #         if vm_fips:
        #             ips_for_vm = vm_fips

        all_ips_dict[vm_id] = ips_for_vm
        all_ips += ips_for_vm

    if not all_ips:
        raise ValueError("No ip found for any of these vms {} with pattern: {}".format(vm_ids, ip_pattern))

    LOG.info("IPs dict: {}".format(all_ips_dict))

    if rtn_dict:
        return all_ips_dict
    else:
        return all_ips


def get_net_type_from_name(net_name):
    if re.search(Networks.INTERNAL_NET_NAME, net_name):
        net_type = 'internal'
    elif re.search(Networks.data_net_name_pattern(), net_name):
        net_type = 'data'
    elif re.search(Networks.mgmt_net_name_pattern(), net_name):
        net_type = 'mgmt'
    else:
        raise ValueError("Unknown net_type for net_name - {}".format(net_name))

    return net_type


def get_routers(name=None, distributed=None, ha=None, gateway_ip=None, strict=True, regex=False,
                auth_info=None, con_ssh=None):
    """
    Get router id(s) based on given criteria.
    Args:
        name (str): router name
        distributed (bool): filter out dvr or non-dvr router
        ha (bool): filter out HA router
        gateway_ip (str): ip of the router gateway such as "192.168.13.3"
        strict (bool): whether to perform strict search on router name
        regex
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (list): list of router id(s)

    """
    param_dict = {
        'distributed': distributed,
        'ha': ha,
        'external_gateway_info': gateway_ip,
    }

    final_params = {}
    for key, val in param_dict.items():
        if val is not None:
            final_params[key] = str(val)

    table_ = table_parser.table(cli.neutron('router-list', ssh_client=con_ssh, auth_info=auth_info),
                                combine_multiline_entry=True)
    if name is not None:
        table_ = table_parser.filter_table(table_, strict=strict, regex=regex, name=name)

    return table_parser.get_values(table_, 'id', **final_params)


def get_tenant_router(router_name=None, auth_info=None, con_ssh=None):
    """
    Get id of tenant router with specified name.

    Args:
        router_name (str): name of the router
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (str): router id

    """
    if router_name is None:
        tenant_name = common.get_tenant_name(auth_info=auth_info)
        router_name = tenant_name + '-router'

    table_ = table_parser.table(cli.neutron('router-list', ssh_client=con_ssh, auth_info=auth_info),
                                combine_multiline_entry=True)
    routers = table_parser.get_values(table_, 'id', name=router_name)
    if not routers:
        LOG.warning("No router with name {} found".format(router_name))
        return None
    return routers[0]


def get_router_info(router_id=None, field='status', strict=True, auth_info=Tenant.get('admin'), con_ssh=None):
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
    if router_id is None:
        router_id = get_tenant_router(con_ssh=con_ssh)

    table_ = table_parser.table(cli.neutron('router-show', router_id, ssh_client=con_ssh, auth_info=auth_info),
                                combine_multiline_entry=True)
    return table_parser.get_value_two_col_table(table_, field, strict)


def create_router(name=None, tenant=None, distributed=None, ha=None, admin_state_down=False, fail_ok=False,
                  auth_info=Tenant.get('admin'), con_ssh=None):
    # Process args
    if tenant is None:
        tenant = Tenant.get_primary()['tenant']

    if name is None:
        name = 'router'
        name = '-'.join([tenant, name, str(common.Count.get_router_count())])
    args = name

    if str(admin_state_down).lower() == 'true':
        args = '--admin-state-down ' + args

    tenant_id = keystone_helper.get_tenant_ids(tenant, con_ssh=con_ssh)[0]

    args_dict = {
        '--tenant-id': tenant_id if (auth_info == Tenant.get('admin') and tenant != Tenant.get('admin')) else None,
        '--distributed': distributed,
        '--ha': ha,
    }

    for key, value in args_dict.items():
        if value is not None:
            args = "{} {} {}".format(key, value, args)

    LOG.info("Creating router with args: {}".format(args))
    # send router-create cli
    code, output = cli.neutron('router-create', args, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                               rtn_list=True)

    # process result
    if code == 1:
        return 1, '', output

    table_ = table_parser.table(output)
    router_id = table_parser.get_value_two_col_table(table_, 'id')

    expt_values = {
        'admin_state_up': str(not admin_state_down),
        'distributed': 'True' if distributed else 'False',
        'ha': 'True' if ha else 'False',
        'tenant_id': tenant_id
    }

    for field, expt_val in expt_values.items():
        if table_parser.get_value_two_col_table(table_, field) != expt_val:
            msg = "{} is not set to {} for router {}".format(field, expt_val, router_id)
            if fail_ok:
                return 2, router_id, msg
            raise exceptions.NeutronError(msg)

    succ_msg = "Router {} is created successfully.".format(router_id)
    LOG.info(succ_msg)
    return 0, router_id, succ_msg


def get_router_subnets(router_id, rtn_val='subnet_id', mgmt_only=True, auth_info=Tenant.get('admin'), con_ssh=None):
    """

    Args:
        router_id:
        rtn_val (str): 'subnet_id' or 'ip_address'
        mgmt_only
        auth_info:
        con_ssh:

    Returns:

    """
    router_ports_tab = table_parser.table(cli.neutron('router-port-list', router_id, ssh_client=con_ssh,
                                                      auth_info=auth_info))

    fixed_ips = table_parser.get_column(router_ports_tab, 'fixed_ips')
    rtn_val = 'subnet_id' if 'id' in rtn_val else 'ip_address'
    subnets = list(set([eval(item)[rtn_val] for item in fixed_ips]))

    if rtn_val == 'ip_address' and mgmt_only:
        subnets = [ip_ for ip_ in subnets if re.match(Networks.MGMT_IP, ip_)]

    return subnets


def get_next_subnet_cidr(net_id, ip_pattern='\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', con_ssh=None):
    LOG.info("Creating subnet of tenant-mgmt-net to add interface to router.")

    nets_tab = table_parser.table(cli.neutron('net-list', ssh_client=con_ssh, auth_info=Tenant.get('admin')))
    existing_subnets = table_parser.get_values(nets_tab, 'subnets', id=net_id, merge_lines=False)[0]
    existing_subnets = ','.join(existing_subnets)

    # TODO: add ipv6 support
    mask = re.findall(ip_pattern + '/(\d{1,3})', existing_subnets)[0]
    increment = int(math.pow(2, math.ceil(math.log2(int(mask)))))

    ips = re.findall(ip_pattern, existing_subnets)
    ips = [ipaddress.ip_address(item) for item in ips]
    max_ip = ipaddress.ip_address(max(ips))

    cidr = "{}/{}".format(str(ipaddress.ip_address(int(max_ip) + increment)), mask)

    return cidr


def create_mgmt_subnet(net_id=None, name=None, cidr=None, gateway=None, dhcp=None, dns_servers=None,
                       alloc_pool=None, ip_version=None, subnet_pool=None, tenant_auth_info=None, fail_ok=False,
                       auth_info=None, con_ssh=None):
    if net_id is None:
        net_id = get_mgmt_net_id(con_ssh=con_ssh, auth_info=tenant_auth_info)

    if cidr is None:
        cidr = get_next_subnet_cidr(net_id=net_id, ip_pattern="192.168\.\d{1,3}\.\d{1,3}", con_ssh=con_ssh)

    tenant_name = common.get_tenant_name(tenant_auth_info)
    return create_subnet(net_id, name=name, cidr=cidr, gateway=gateway, dhcp=dhcp, dns_servers=dns_servers,
                         alloc_pool=alloc_pool, ip_version=ip_version, subnet_pool=subnet_pool, tenant_name=tenant_name,
                         fail_ok=fail_ok, auth_info=auth_info, con_ssh=con_ssh)


def delete_router(router_id, del_ifs=True, auth_info=Tenant.get('admin'), con_ssh=None, fail_ok=False):

    if del_ifs:
        LOG.info("Deleting subnet interfaces attached to router {}".format(router_id))
        router_subnets = get_router_subnets(router_id, con_ssh=con_ssh, auth_info=auth_info)
        ext_gateway_subnet = get_router_ext_gateway_subnet(router_id, auth_info=auth_info, con_ssh=con_ssh)
        for subnet in router_subnets:
            if subnet != ext_gateway_subnet:
                delete_router_interface(router_id, subnet=subnet, auth_info=auth_info, con_ssh=con_ssh)

    LOG.info("Deleting router {}...".format(router_id))
    code, output = cli.neutron('router-delete', router_id, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                               rtn_list=True)
    if code == 1:
        return 1, output

    routers = get_routers(auth_info=auth_info, con_ssh=con_ssh)
    if router_id in routers:
        msg = "Router {} is still showing in neutron router-list".format(router_id)
        if fail_ok:
            LOG.warning(msg)
            return 2, msg

    succ_msg = "Router {} is successfully deleted.".format(router_id)
    LOG.info(succ_msg)
    return 0, succ_msg


def add_router_interface(router_id=None, subnet=None, port=None, auth_info=None, con_ssh=None, fail_ok=False):
    """

    Args:
        router_id (str|None):
        subnet (str|None):
        port (str|None):
        auth_info (dict):
        con_ssh:
        fail_ok (bool):

    Returns (tuple):


    """
    if router_id is None:
        router_id = get_tenant_router(con_ssh=con_ssh)

    if subnet is None and port is None:
        # Create subnet of tenant-mgmt-net to attach to router
        # TODO: add ipv6 support
        subnet = create_mgmt_subnet(dns_servers=DNS_NAMESERVERS, ip_version=4, tenant_auth_info=auth_info,
                                    auth_info=auth_info, con_ssh=con_ssh)[1]

    arg = router_id
    if subnet is None:
        if_source = port
        arg += ' port={}'.format(port)
    else:
        if_source = subnet
        arg += ' subnet={}'.format(subnet)
    LOG.info("Adding router interface via: {}".format(arg))
    code, output = cli.neutron('router-interface-add', arg, ssh_client=con_ssh, auth_info=auth_info, rtn_list=True,
                               fail_ok=fail_ok)

    if code == 1:
        return 1, output

    if subnet is not None:
        if not re.match(UUID, subnet):
            subnet = get_subnets(name=subnet, auth_info=auth_info, con_ssh=con_ssh)[0]
        if not router_subnet_exists(router_id, subnet):
            msg = "Subnet {} is not shown in router-port-list for router {}".format(subnet, router_id)
            raise exceptions.NeutronError(msg)

    # TODO: Add check if port is used to add interface.

    succ_msg = "Interface is successfully added to router {}".format(router_id)
    LOG.info(succ_msg)
    return 0, if_source


def delete_router_interface(router_id, subnet=None, port=None, auth_info=None, con_ssh=None, fail_ok=False):
    args = router_id
    if subnet is None and port is None:
        raise ValueError("Either subnet or port has to be specified.")

    if subnet is None:
        args += ' port={}'.format(port)
    else:
        args += ' subnet={}'.format(subnet)

    LOG.info("Deleting router interface. Args: {}".format(args))
    code, output = cli.neutron('router-interface-delete', args, ssh_client=con_ssh, auth_info=auth_info, rtn_list=True,
                               fail_ok=fail_ok)

    if code == 1:
        return 1, output

    if subnet is not None:
        if not re.match(UUID, subnet):
            subnet = get_subnets(name=subnet, auth_info=auth_info, con_ssh=con_ssh)[0]

        if router_subnet_exists(router_id, subnet):
            msg = "Subnet {} is still shown in router-port-list for router {}".format(subnet, router_id)
            if fail_ok:
                LOG.warning(msg)
                return 2, msg
            raise exceptions.NeutronError(msg)

    succ_msg = "Interface is deleted successfully for router {}.".format(router_id)
    LOG.info(succ_msg)
    return 0, succ_msg


def router_subnet_exists(router_id, subnet_id, con_ssh=None, auth_info=Tenant.get('admin')):
    subnets_ids = get_router_subnets(router_id, auth_info=auth_info, con_ssh=con_ssh)

    return subnet_id in subnets_ids


def set_router_gateway(router_id=None, extnet_id=None, enable_snat=False, fixed_ip=None, fail_ok=False,
                       auth_info=Tenant.get('admin'), con_ssh=None, clear_first=True):
    """
    Set router gateway with given snat, ip settings.

    Args:
        router_id (str): id of the router to set gateway for. If None, tenant router for Primary tenant will be used.
        extnet_id (str): id of the external network for getting the gateway
        enable_snat (bool): whether to enable SNAT.
        fixed_ip (str): fixed ip to set
        fail_ok (bool):
        auth_info (dict): auth info for running the router-gateway-set cli
        con_ssh (SSHClient):
        clear_first (bool): Whether to clear the router gateway first if router already has a gateway set

    Returns (tuple): (rtn_code (int), message (str))    scenario 1,2,3,4 only returns if fail_ok=True
        - (0, "Router gateway is successfully set.")
        - (1, <stderr>)     -- cli is rejected
        - (2, "Failed to set gateway of external network <extnet_id> for router <router_id>")
        - (3, "snat is not <disabled/enabled>")
        - (4, "Fixed ip is not set to <fixed_ip>")

    """
    # Process args
    args = ''
    if not enable_snat:
        args += ' --disable-snat'

    if fixed_ip:
        args += ' --fixed-ip ip_address={}'.format(fixed_ip)

    if router_id is None:
        router_id = get_tenant_router(con_ssh=con_ssh)

    if not extnet_id:
        extnet_id = get_ext_networks(con_ssh=con_ssh, auth_info=auth_info)[0]

    args = ' '.join([args, router_id, extnet_id])

    # Clear first if gateway already set
    if clear_first and get_router_ext_gateway_info(router_id, auth_info=auth_info, con_ssh=con_ssh):
        clear_router_gateway(router_id=router_id, check_first=False, auth_info=auth_info, con_ssh=con_ssh)

    code, output = cli.neutron('router-gateway-set', args, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                               rtn_list=True)

    if code == 1:
        return 1, output

    post_ext_gateway = get_router_ext_gateway_info(router_id, auth_info=auth_info, con_ssh=con_ssh)

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
        raise exceptions.NeutronError(msg)

    if fixed_ip and not fixed_ip == post_ext_gateway['external_fixed_ips'][0]['ip_address']:
        msg = "Fixed ip is not set to {}".format(fixed_ip)
        if fail_ok:
            LOG.warning(msg)
            return 4, msg
        raise exceptions.NeutronError(msg)

    succ_msg = "Router gateway is successfully set."
    LOG.info(succ_msg)
    return 0, succ_msg


def clear_router_gateway(router_id=None, fail_ok=False, auth_info=Tenant.get('admin'), con_ssh=None, check_first=True):
    """
    Clear router gateway

    Args:
        router_id (str): id of router to clear gateway for. If None, tenant router for primary tenant will be used.
        fail_ok (bool):
        auth_info (dict): auth info for running the router-gateway-clear cli
        con_ssh (SSHClient):
        check_first (bool): whether to check if gateway is set for given router before clearing

    Returns (tuple): (rtn_code (int), message (str))
        - (0, "Router gateway is successfully cleared.")
        - (1, <stderr>)    -- cli is rejected
        - (2, "Failed to clear gateway for router <router_id>")

    """
    if router_id is None:
        router_id = get_tenant_router(con_ssh=con_ssh)

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


def __set_router_openstack(name=None, admin_state_up=None, distributed=None, no_routes=None, routes=None,
                           router_id=None, fail_ok=False, con_ssh=None, auth_info=Tenant.get('admin')):
    if router_id is None:
        router_id = get_tenant_router(con_ssh=con_ssh)

    if not isinstance(router_id, str):
        raise ValueError("Expecting string value for router_id. Get {}".format(type(router_id)))

    args = ''
    if name is not None:
        args += ' --name {}'.format(name)

    if routes is not None:
        if no_routes:
            raise ValueError("'Only one of the: routes', 'no_routes' can be specified.")
        if isinstance(routes, str):
            routes = [routes]

        for route in routes:
            args += ' --route ' + route

    elif no_routes:
        args += ' --clear-routes'

    if admin_state_up is True:
        args += ' --enable'
    elif admin_state_up is False:
        args += ' --disable'

    if distributed is True:
        args += ' --distributed'
    elif distributed is False:
        args += ' --centralized'

    if not args:
        raise ValueError("At least one of the args need to be specified.")

    LOG.info("Updating router {}: {}".format(router_id, args))

    args = '{} {}'.format(args.strip(), router_id)
    return cli.neutron('router-update', args, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok, rtn_list=True)


def _update_router(name=None, admin_state_up=None, distributed=None, no_routes=None, routes=None,
                   external_gateway_info=None, router_id=None, fail_ok=False, con_ssh=None, auth_info=Tenant.get('admin')):
    """

    Args:
        admin_state_up (bool|None):
        distributed (bool):
        no_routes (bool):
        routes (list|str):
        external_gateway_info (str): such as 'network_id=0fc6f9bc-6362-4c81-a9c9-d225778655ca,enable_snat=False'
        router_id (str):
        fail_ok:
        con_ssh:
        auth_info:

    Returns:

    """
    if external_gateway_info is None and common._execute_with_openstack_cli():
        return __set_router_openstack(name=name, admin_state_up=admin_state_up, distributed=distributed,
                                      no_routes=no_routes, routes=routes, router_id=router_id, fail_ok=fail_ok,
                                      con_ssh=con_ssh, auth_info=auth_info)

    if router_id is None:
        router_id = get_tenant_router(con_ssh=con_ssh)

    if not isinstance(router_id, str):
        raise ValueError("Expecting string value for router_id. Get {}".format(type(router_id)))

    args = ''
    if routes is not None:
        if no_routes:
            raise ValueError("'Only one of the: routes', 'no_routes' can be specified.")
        if isinstance(routes, str):
            routes = [routes]

        for route in routes:
            args += ' --route ' + route

    args_dict = {
        '--name': name,
        '--admin-state-up': admin_state_up,
        '--distributed': distributed,
        '--no-routes': no_routes,
        '--external-gateway-info type=dict': external_gateway_info,
    }

    for key, value in args_dict.items():
        if value is not None:
            args += ' {} {}'.format(key, value)

    if not args:
        raise ValueError("At least of the args need to be specified.")

    LOG.info("Updating router {}: {}".format(router_id, args))

    args = '{} {}'.format(router_id, args.strip())
    return cli.neutron('router-update', args, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok, rtn_list=True,
                       force_neutron=True)


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

    # convert enable_snat value to bool -- will be used when eval(info_str)
    true = True
    false = False
    null = None
    return eval(info_str)


def get_router_ext_gateway_subnet(router_id, auth_info=None, con_ssh=None):
    ext_gateway_info = get_router_ext_gateway_info(router_id, auth_info=auth_info, con_ssh=con_ssh)
    if ext_gateway_info is not None:
        return ext_gateway_info['external_fixed_ips'][0]['subnet_id']


def get_router_ext_gateway_subnet_ip_address(router_id, auth_info=None, con_ssh=None):
    ext_gateway_info = get_router_ext_gateway_info(router_id, auth_info=auth_info, con_ssh=con_ssh)
    if ext_gateway_info is not None:
        return ext_gateway_info['external_fixed_ips'][0]['ip_address']


def update_router_ext_gateway_snat(router_id=None, ext_net_id=None, enable_snat=False, fail_ok=False, con_ssh=None,
                                   auth_info=Tenant.get('admin')):
    """
    Update router external gateway SNAT

    Args:
        router_id (str): id of router to update
        ext_net_id (str): id of external network for updating gateway SNAT
        enable_snat (bool): whether to enable or disable SNAT
        fail_ok (bool):
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (tuple): (rtn_code (int), message (str))
        - (0, <stdout>)     -- router gateway is updated successfully with given SNAT setting
        - (1, <stderr>)     -- cli is rejected
        - (2, "enable_snat is not set to <value>")      -- SNAT is not enabled/disabled as specified

    """
    if ext_net_id is None:
        ext_net_id = get_ext_networks(con_ssh=con_ssh, auth_info=auth_info)[0]

    arg = 'network_id={},enable_snat={}'.format(ext_net_id, enable_snat)
    code, output = _update_router(external_gateway_info=arg, router_id=router_id,
                                  fail_ok=fail_ok, con_ssh=con_ssh, auth_info=auth_info)
    if code == 1:
        return 1, output

    post_gateway_info = get_router_ext_gateway_info(router_id=router_id, auth_info=auth_info, con_ssh=con_ssh)
    if enable_snat != post_gateway_info['enable_snat']:
        msg = "enable_snat is not set to {}".format(enable_snat)
        LOG.warning(msg)
        return 2, msg

    succ_msg = "Router external gateway info is successfully updated to enable_SNAT={}".format(enable_snat)
    LOG.info(succ_msg)
    return 0, succ_msg


def update_router_distributed(router_id=None, distributed=True, pre_admin_down=True, post_admin_up=True,
                              post_admin_up_on_failure=True, fail_ok=False, auth_info=Tenant.get('admin'), con_ssh=None):
    """
    Update router to distributed or centralized

    Args:
        router_id (str): id of the router to update
        distributed (bool): True if set to distributed, False if set to centralized
        pre_admin_down (bool|None): whether to set admin state down before updating the distributed state
        post_admin_up (bool): whether to set admin state up after updating the distributed state
        post_admin_up_on_failure (bool): whether to set admin state up if updating router failed
        fail_ok (bool): whether to throw exception if cli got rejected
        auth_info (dict):
        con_ssh (SSHClient):

    Returns:

    """
    if pre_admin_down:
        _update_router(admin_state_up=False, router_id=router_id, fail_ok=False, con_ssh=con_ssh,
                       auth_info=Tenant.get('admin'))

    try:
        code, output = _update_router(distributed=distributed, router_id=router_id, fail_ok=fail_ok, con_ssh=con_ssh,
                                      auth_info=auth_info)
        if post_admin_up:
            _update_router(admin_state_up=True, router_id=router_id, fail_ok=False, con_ssh=con_ssh,
                           auth_info=auth_info)
    except exceptions.CLIRejected:
        raise
    finally:
        if post_admin_up_on_failure:
            _update_router(admin_state_up=True, router_id=router_id, fail_ok=False, con_ssh=con_ssh,
                           auth_info=auth_info)

    if code == 1:
        return 1, output

    post_distributed_val = get_router_info(router_id, 'distributed', auth_info=Tenant.get('admin'), con_ssh=con_ssh)
    if post_distributed_val.lower() != str(distributed).lower():
        msg = "Router {} is not updated to distributed={}".format(router_id, distributed)
        if fail_ok:
            return 2, msg
        raise exceptions.NeutronError(msg)

    succ_msg = "Router is successfully updated to distributed={}".format(distributed)
    LOG.info(succ_msg)
    return 0, succ_msg


def get_quota(quota_name, tenant_name=None, tenant_id=None, con_ssh=None, auth_info=Tenant.get('admin')):

    if not tenant_id:
        if tenant_name is None:
            tenant_name = Tenant.get_primary()['tenant']
        tenant_id = keystone_helper.get_tenant_ids(tenant_name=tenant_name, con_ssh=con_ssh)[0]
    quotas_tab = table_parser.table(cli.neutron('quota-list', ssh_client=con_ssh, auth_info=auth_info))

    return int(table_parser.get_values(quotas_tab, quota_name, **{'tenant_id': tenant_id})[0])


def update_quotas(tenant_name=None, tenant_id=None, con_ssh=None, auth_info=Tenant.get('admin'), fail_ok=False,
                  sys_con_for_dc=True, **kwargs):
    """
    Update neutron quota(s).

    Args:
        tenant_name (str):
        tenant_id (str): id of tenant to update quota for. If both id and name are specified, tenant_id will be used.
        con_ssh (SSHClient):
        auth_info (dict):
        fail_ok (bool):
        sys_con_for_dc (bool): switch to use system controller for Distributed Cloud system
        **kwargs: key(str)=value(int) pair(s) to update. such as: network=100, port=50
            possible keys: network, subnet, port, router, floatingip, security-group, security-group-rule, vip, pool,
                            member, health-monitor

    Returns (tuple):
        - (0, "Neutron quota(s) updated successfully to: <kwargs>.")
        - (1, <stderr>)
        - (2, "<quota_name> is not set to <specified_value>")

    """
    if not tenant_id:
        if tenant_name is None:
            tenant_name = Tenant.get_primary()['tenant']
        tenant_id = keystone_helper.get_tenant_ids(tenant_name=tenant_name, con_ssh=con_ssh)[0]

    if not kwargs:
        raise ValueError("Please specify at least one quota=value pair via kwargs.")

    args_ = ''
    for key in kwargs:
        key = key.strip().replace('_', '-')
        args_ += '--{} {} '.format(key, kwargs[key])

    args_ += tenant_id

    if not auth_info:
        auth_info = Tenant.get_primary()

    if ProjVar.get_var('IS_DC') and sys_con_for_dc and auth_info['region'] != 'SystemController':
        auth_info = Tenant.get(auth_info['user'], dc_region='SystemController')

    code, output = cli.neutron('quota-update', args_, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                               rtn_list=True)

    if code == 1:
        return 1, output

    table_ = table_parser.table(output)
    for key, value in kwargs.items():
        field = key.replace('-', '_')
        if not int(table_parser.get_value_two_col_table(table_, field)) == int(value):
            msg = "{} is not set to {}".format(field, value)
            if fail_ok:
                LOG.warning(msg)
                return 2, msg
            raise exceptions.NeutronError(msg)

    succ_msg = "Neutron quota(s) updated successfully for tenant {} to: {}.".format(tenant_id, kwargs)
    LOG.info(succ_msg)
    return 0, succ_msg


def get_pci_devices_info(class_id, con_ssh=None, auth_info=None):
    """
    Get PCI devices with nova device-list/show.

    As in load "2017-01-17_22-01-49", the known supported devices are:
        Coleto Creek PCIe Co-processor  Device Id: 0443 Vendor Id:8086

    Args:
        class_id (str|list): Some possible values:
            0b4000 (Co-processor),
            0c0330 (USB controller),
            030000 (VGA compatible controller)
        con_ssh:
        auth_info:

    Returns (dict): nova pci devices dict.
        Format: {<pci_alias1>: {<host1>: {<nova device-show row dict for host>}, <host2>: {...}},
                 <pci_alias2>: {...},
                 ...}
        Examples:
            {'qat-dh895xcc-vf': {'compute-0': {'Device ID':'0443','Class Id':'0b4000', ...} 'compute-1': {...}}}

    """
    table_ = table_parser.table(cli.nova('device-list', ssh_client=con_ssh, auth_info=auth_info))
    table_ = table_parser.filter_table(table_, **{'class_id': class_id})
    LOG.info('output of nova device-list for {}: {}'.format(class_id, table_))

    devices = table_parser.get_column(table_, 'PCI Alias')
    LOG.info('PCI Alias from device-list:{}'.format(devices))

    nova_pci_devices = {}
    for alias in devices:
        table_ = table_parser.table(cli.nova('device-show {}'.format(alias)))
        # LOG.debug('output from nova device-show for device-id:{}\n{}'.format(alias, table_))

        table_dict = table_parser.row_dict_table(table_, key_header='Host', unique_key=True, lower_case=False)
        nova_pci_devices[alias] = table_dict
        # {'qat-dh895xcc-vf': {'compute-0': {'Device ID':'0443','Class Id':'0b4000', ...} 'compute-1': {...}}}

    LOG.info('nova_pci_devices: {}'.format(nova_pci_devices))

    return nova_pci_devices


def get_networks_on_providernet(providernet_id, rtn_val='id', con_ssh=None, auth_info=Tenant.get('admin'), strict=True,
                                regex=False, exclude=False, **kwargs):
    """

    Args:
        providernet_id(str):
        rtn_val(str): 'id' or 'name'
        con_ssh (SSHClient):
        auth_info (dict):
        strict (bool)
        regex (bool)
        exclude (bool): whether to return networks that are NOT on given providernet
        **kwargs: extra key/value pair to filter out the results

    Returns:
        statue (0 or 1) and the list of network ID
    """
    if not providernet_id:
        raise ValueError("No providernet_id provided.")

    table_ = table_parser.table(cli.neutron(cmd='net-list-on-providernet', positional_args=providernet_id,
                                            auth_info=auth_info, ssh_client=con_ssh))

    networks = table_parser.get_values(table_, rtn_val, strict=strict, regex=regex, exclude=exclude, **kwargs)

    LOG.info("Networks on providernet {} with args - '{}': {}".format(providernet_id, kwargs, networks))
    # return list(set(networks))
    return list(networks)


def filter_ips_with_subnet_vlan_id(ips, vlan_id=0, auth_info=Tenant.get('admin'), con_ssh=None):
    """
    Filter out ips with given subnet vlan id.
    This is mainly used by finding vlan 0 ip to ping from a list of internal net ips.
    Args:
        ips (list):
        vlan_id (int):
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (list): list of filtered ips. Empty list if none of the ips belongs to subnet with required the vlan id.

    """

    if common._execute_with_openstack_cli():
        return __filter_ips_with_subnet_vlan_id_openstack(ips, vlan_id=vlan_id, auth_info=auth_info, con_ssh=con_ssh)

    if not ips:
        raise ValueError("No ips provided.")

    table_ = table_parser.table(cli.neutron('subnet-list', ssh_client=con_ssh, auth_info=auth_info, force_neutron=True))
    table_ = table_parser.filter_table(table_, strict=True, **{'wrs-net:vlan_id': str(vlan_id)})

    cidrs = table_parser.get_column(table_, 'cidr')
    filtered_ips = []
    for ip in ips:
        for cidr in cidrs:
            if ipaddress.ip_address(ip) in ipaddress.ip_network(cidr):
                filtered_ips.append(ip)

    if not filtered_ips:
        LOG.warning("None of the ips from {} belongs to a subnet with vlan id {}".format(ips, vlan_id))
    else:
        LOG.info("IPs with vlan id {}: {}".format(vlan_id, filtered_ips))

    return filtered_ips


def __filter_ips_with_subnet_vlan_id_openstack(ips, vlan_id=0, auth_info=Tenant.get('admin'), con_ssh=None):
    """
    Filter out ips with given subnet vlan id.
    This is mainly used by finding vlan 0 ip to ping from a list of internal net ips.
    Args:
        ips (list):
        vlan_id (int):
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (list): list of filtered ips. Empty list if none of the ips belongs to subnet with required the vlan id.

    """
    if not ips:
        raise ValueError("No ips provided.")

    table_ = table_parser.table(cli.neutron('subnet-list', ssh_client=con_ssh, auth_info=auth_info))
    # table_ = table_parser.filter_table(table_, strict=True, **{'wrs-net:vlan_id': str(vlan_id)})

    cidrs = table_parser.get_column(table_, 'Subnet')
    # filtered_ips = []
    subnets = {}
    for ip in ips:
        for cidr in cidrs:
            if ipaddress.ip_address(ip) in ipaddress.ip_network(cidr):
                subnets[table_parser.get_values(table_, 'ID', Subnet=cidr)[0]] = ip
                # filtered_ips.append(ip)

    filtered_ips = []
    for subnet in subnets:
        subnet_show_tab = table_parser.table(cli.neutron('subnet-show', subnet, ssh_client=con_ssh,
                                                         auth_info=auth_info))
        if eval(table_parser.get_value_two_col_table(subnet_show_tab, 'wrs-net:vlan_id')) == vlan_id:
            filtered_ips.append(subnets[subnet])

    if not filtered_ips:
        LOG.warning("None of the ips from {} belongs to a subnet with vlan id {}".format(ips, vlan_id))
    else:
        LOG.info("IPs with vlan id {}: {}".format(vlan_id, filtered_ips))

    return filtered_ips


def get_eth_for_mac(ssh_client, mac_addr, timeout=VMTimeout.IF_ADD, vshell=False):
    """
    Get the eth name for given mac address on the ssh client provided
    Args:
        ssh_client (SSHClient): usually a vm_ssh
        mac_addr (str): such as "fa:16:3e:45:0d:ec"
        timeout (int): max time to wait for the given mac address appear in ip addr
        vshell (bool): if True, get eth name from "vshell port-list"

    Returns (str): The first matching eth name for given mac. such as "eth3"

    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        if not vshell:
            if mac_addr in ssh_client.exec_cmd('ip addr'.format(mac_addr))[1]:

                code, output = ssh_client.exec_cmd('ip addr | grep -B 1 {}'.format(mac_addr))
                # sample output:
                # 7: eth4: <BROADCAST,MULTICAST> mtu 1500 qdisc noop state DOWN qlen 1000
                # link/ether 90:e2:ba:60:c8:08 brd ff:ff:ff:ff:ff:ff

                return output.split(sep=':')[1].strip()
        else:
            code, output = ssh_client.exec_cmd('vshell port-list | grep {}'.format(mac_addr))
            # |uuid|id|type|name|socket|admin|oper|mtu|mac-address|pci-address|network-uuid|network-name
            return output.split(sep='|')[4].strip()
        time.sleep(1)
    else:
        LOG.warning("Cannot find provided mac address {} in 'ip addr'".format(mac_addr))
        return ''


def create_providernet_range(providernet, range_min, range_max, rtn_val='id', range_name=None, shared=True,
                             tenant_id=None, group=None, port=None, ttl=None, auth_info=Tenant.get('admin'), con_ssh=None,
                             fail_ok=False):
    """
    Create a provider net range for given providernet with specified min and max range values
    Args:
        providernet (str):
        range_min (int):
        range_max (int):
        rtn_val (str):
        range_name (str):
        shared (bool):
        tenant_id (str):
        group (str):
        port (int):
        ttl (int):
        auth_info (dict):
        con_ssh (SSHClient):
        fail_ok (bool):

    Returns (tuple):
        0, <range name or id>     - Range created successfully
        1, <std_err>              - Range create cli rejected

    """
    range_min = int(range_min)
    range_max = int(range_max)

    existing_ranges = get_providernet_ranges(rtn_val='name')
    if range_name is None:
        range_name = providernet + '-r-auto'

    range_name = common.get_unique_name(range_name, existing_names=existing_ranges)

    args = '--range {}-{} --name {}'.format(range_min, range_max, range_name)

    if shared:
        args += ' --shared'

    args_dict = {
        '--tenant-id': tenant_id,
        '--group': group,
        '--ttl': ttl,
        '--port': port
    }
    for key, val in args_dict.items():
        if val is not None:
            args += " {} {}".format(key, val)

    args += ' ' + providernet

    LOG.info("Creating range {} for providernet {}".format(range_name, providernet))
    code, output = cli.neutron('providernet-range-create', args, ssh_client=con_ssh, auth_info=auth_info,
                               fail_ok=fail_ok, rtn_list=True)

    if code == 1:
        return 1, output

    post_ranges_tab = table_parser.table(cli.neutron('providernet-range-list', ssh_client=con_ssh, auth_info=auth_info))
    post_range_tab = table_parser.filter_table(post_ranges_tab, name=range_name)
    post_min_range = int(table_parser.get_column(post_range_tab, 'minimum')[0])
    post_max_range = int(table_parser.get_column(post_range_tab, 'maximum')[0])

    if post_max_range != range_max or post_min_range != range_min:
        err_msg = "MIN or MAX range incorrect. Expected: {}-{}. Actual: {}-{}".format(
                range_min, range_max, post_min_range, post_max_range)
        raise exceptions.NeutronError(err_msg)

    LOG.info("Provider net range {}-{} is successfully created for providernet {}".format(
            range_min, range_max, providernet))

    if rtn_val == 'id':
        return 0, table_parser.get_column(post_range_tab, 'id')
    else:
        return 0, range_name


def delete_providernet_range(providernet_range, range_val='name', con_ssh=None, auth_info=Tenant.get('admin'), fail_ok=False):
    """
    Delete providernet range
    Args:
        providernet_range (str): providernet range name or id
        range_val (str): 'name' or 'id'
        con_ssh (SSHClient):
        auth_info (dict):
        fail_ok (bool):

    Returns (tuple): (code, output)
        (0, <stdout>)   successfully deleted
        (1, <stderr>)   cli rejected

    """

    if not providernet_range:
        raise ValueError("Range name cannot be empty")

    if range_val == 'id':
        providernet_range = get_providernet_range_name_from_id(providernet_range, con_ssh=con_ssh)

    LOG.info("Deleting provider net range {}".format(providernet_range))
    code, output = cli.neutron('providernet-range-delete', providernet_range, ssh_client=con_ssh, auth_info=auth_info,
                               rtn_list=True, fail_ok=fail_ok)

    if code == 1:
        return code, output

    table_ = table_parser.table(cli.neutron('providernet-range-list', ssh_client=con_ssh, auth_info=auth_info))
    providernet_range = table_parser.get_values(table_, 'id', strict=True, name=providernet_range)

    if providernet_range:
        raise exceptions.NeutronError("Range {} is not successfully deleted".format(providernet_range))

    LOG.info("Provider net range {} is successfully deleted".format(providernet_range))
    return 0, output


def get_providernet_range_name_from_id(range_id, auth_info=Tenant.get('admin'), con_ssh=None):
    table_ = table_parser.table(cli.neutron('providernet-range-list', ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_values(table_, 'name', id=range_id)[0]


def get_vm_nics(vm_id, con_ssh=None, auth_info=Tenant.get('admin')):
    """
    Get nics of vm as a list of dictionaries.

    Args:
        vm_id (str):
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (list): list of dictionaries. Such as:
        [{"vif_model": "virtio", "network": "external-net0", "port_id": "ba23cd33-b0c5-4e37-b331-013dfc12560b",
            "mtu": 1500, "mac_address": "fa:16:3e:72:d4:24", "vif_pci_address": ""},
        {"vif_model": "virtio", "network": "internal0-net0", "port_id": "2ccec5e9-bbd5-4007-9c28-9116da15d925",
            "mtu": 9000, "mac_address": "fa:16:3e:0d:5a:5e", "vif_pci_address": ""}]

    """
    table_ = table_parser.table(cli.nova('show', vm_id, auth_info=auth_info, ssh_client=con_ssh))
    nics = table_parser.get_value_two_col_table(table_, field='wrs-if:nics', merge_lines=False)
    if isinstance(nics, str):
        nics = [nics]
    nics = [eval(nic_) for nic_ in nics]

    return nics


def _get_interfaces_via_vshell(ssh_client, net_type='internal'):
    """
    Get interface uuids for given network type
    Args:
        ssh_client (SSHClient):
        net_type: 'data', 'mgmt', or 'internal'

    Returns (list): interface uuids

    """
    LOG.info("Getting {} interface-uuid via vshell address-list".format(net_type))
    table_ = table_parser.table(ssh_client.exec_cmd('vshell address-list', fail_ok=False)[1])
    interfaces = table_parser.get_values(table_, 'interface-uuid', regex=True, address=Networks.IP_PATTERN[net_type])

    return interfaces


__PING_LOSS_MATCH = re.compile(PING_LOSS_RATE)


def ping_server(server, ssh_client, num_pings=5, timeout=60,
                fail_ok=False, vshell=False, interface=None, retry=0, net_type='internal'):
    """

    Args:
        server (str): server ip to ping
        ssh_client (SSHClient): ping from this ssh client
        num_pings (int):
        timeout (int): max time to wait for ping response in seconds
        fail_ok (bool): whether to raise exception if packet loss rate is 100%
        vshell (bool): whether to ping via 'vshell ping' cmd
        interface (str): interface uuid. vm's internal interface-uuid will be used when unset
        retry (int):
        net_type (str): 'data', 'mgmt', or 'internal', only used for vshell=True and interface=None

    Returns (int): packet loss percentile, such as 100, 0, 25

    """
    output = packet_loss_rate = None
    for i in range(max(retry + 1, 0)):
        if not vshell:
            cmd = 'ping -c {} {}'.format(num_pings, server)
            code, output = ssh_client.exec_cmd(cmd=cmd, expect_timeout=timeout, fail_ok=True)
            if code != 0:
                packet_loss_rate = 100
            else:
                packet_loss_rate = __PING_LOSS_MATCH.findall(output)[-1]
        else:
            if not interface:
                interface = _get_interfaces_via_vshell(ssh_client, net_type=net_type)[0]
            cmd = 'vshell ping --count {} {} {}'.format(num_pings, server, interface)
            code, output = ssh_client.exec_cmd(cmd=cmd, expect_timeout=timeout)
            if code != 0:
                packet_loss_rate = 100
            else:
                if "ERROR" in output:
                    # usually due to incorrectly selected interface (no route to destination)
                    raise ValueError("vshell ping rejected, output={}".format(output))
                packet_loss_rate = re.findall(VSHELL_PING_LOSS_RATE, output)[-1]

        packet_loss_rate = int(packet_loss_rate)
        if packet_loss_rate < 100:
            if packet_loss_rate > 0:
                LOG.warning("Some packets dropped when ping from {} ssh session to {}. Packet loss rate: {}%".
                            format(ssh_client.host, server, packet_loss_rate))
            else:
                LOG.info("All packets received by {}".format(server))
            break

        LOG.info("retry in 3 seconds")
        time.sleep(3)
    else:
        msg = "Ping from {} to {} failed.".format(ssh_client.host, server)
        if not fail_ok:
            raise exceptions.VMNetworkError(msg)
        else:
            LOG.warning(msg)

    untransmitted_packets = re.findall("(\d+) packets transmitted,", output)
    if untransmitted_packets:
        untransmitted_packets = int(num_pings) - int(untransmitted_packets[0])
    else:
        untransmitted_packets = num_pings

    return packet_loss_rate, untransmitted_packets


def get_pci_vm_network(pci_type='pci-sriov', vlan_id=None, net_name=None, strict=False, con_ssh=None,
                       auth_info=Tenant.get('admin'), rtn_all=False):
    """

    Args:
        pci_type (str|tuple|list):
        vlan_id:
        net_name:
        strict:
        con_ssh:
        auth_info:

    Returns (None|str|list): None if no network for given pci type; 2 nets(list) if CX nics; 1 net otherwise.

    """
    if isinstance(pci_type, str):
        pci_type = [pci_type]

    hosts_and_pnets = host_helper.get_hosts_and_pnets_with_pci_devs(pci_type=pci_type, up_hosts_only=True,
                                                                    con_ssh=con_ssh, auth_info=auth_info)
    if not hosts_and_pnets:
        return None

    # print("hosts and pnets: {}".format(hosts_and_pnets))

    host = list(hosts_and_pnets.keys())[0]
    pnet_name = hosts_and_pnets[host][0]
    kwargs = {'vlan_id': vlan_id} if vlan_id is not None else {}
    nets = list(set(get_networks_on_providernet(pnet_name, rtn_val='name', **kwargs)))

    nets_list_all_types = []
    for pci_type_ in pci_type:
        if pci_type_ == 'pci-sriov':
            # Exclude network on first segment
            # The switch is setup with untagged frames for the first segment within the range.
            # This is suitable for PCI passthrough, but would not work for SRIOV
            first_seg = get_first_segment_of_providernet(pnet_name, pnet_val='name', con_ssh=con_ssh)
            untagged_net = get_net_on_segment(pnet_name, seg_id=first_seg, rtn_val='name', con_ssh=con_ssh)
            if untagged_net in nets:
                LOG.info("{} is on first segment of {} range with untagged frames. Remove for sriov.".
                         format(untagged_net, pnet_name))
                nets.remove(untagged_net)

        # print("pnet: {}; Nets: {}".format(pnet_name, nets))
        nets_for_type = _get_preferred_nets(nets=nets, net_name=net_name, strict=strict)
        if not nets_for_type:
            nets_list_all_types = []
            break

        nets_list_all_types.append(nets_for_type)

    final_nets = None
    cx_for_pcipt = False
    if nets_list_all_types:
        final_nets = set(nets_list_all_types[0])
        for nets_ in nets_list_all_types[1:]:
            final_nets.intersection_update(set(nets_))
        final_nets = list(final_nets)
        if final_nets:
            if 'pci-passthrough' in pci_type:
                port = system_helper.get_host_interfaces_info(host, rtn_val='ports', net_type=pci_type)[0]
                host_nic = system_helper.get_host_ports_values(host, header='device type', **{'name': port})[0]
                if re.match(MELLANOX4, host_nic):
                    cx_for_pcipt = True

            if not rtn_all:
                final_nets = final_nets[0:2] if cx_for_pcipt else final_nets[-1]

    if rtn_all:
        final_nets = final_nets, cx_for_pcipt

    return final_nets


def get_first_segment_of_providernet(providernet, pnet_val='id', con_ssh=None, auth_info=Tenant.get('admin')):
    """
    Get first segment id within the range of given providernet
    Args:
        providernet (str): pnet name or id
        pnet_val: 'id' or 'name' based on the value for providernet param
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (int): segment id

    """
    ranges = get_providernets(rtn_val='ranges', con_ssh=con_ssh, auth_info=auth_info, merge_lines=False,
                              **{pnet_val: providernet})[0]

    if isinstance(ranges, list):
        ranges = ranges[0]
    first_seg = eval(ranges)['minimum']
    return first_seg


def get_net_on_segment(providernet, seg_id, rtn_val='name', con_ssh=None, auth_info=Tenant.get('admin')):
    """
    Get network name on given prvidernet with specified segment id
    Args:
        providernet (str): pnet name or id
        seg_id (int): segment id
        rtn_val (str): 'name' or 'id'
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (str|None): network id/name or None if no network on given seg id

    """
    nets = get_networks_on_providernet(providernet_id=providernet, rtn_val=rtn_val, con_ssh=con_ssh,
                                       auth_info=auth_info, **{'segmentation_id': seg_id})

    net = nets[0] if nets else None
    return net


def get_pci_nets_with_min_hosts(min_hosts=2, pci_type='pci-sriov', up_hosts_only=True, vlan_id=0, net_name=None,
                                strict=False, con_ssh=None, auth_info=Tenant.get('admin')):
    """

    Args:
        min_hosts (int):
        pci_type (str): pci-sriov or pci-passthrough
        up_hosts_only (bool): whether or not to exclude down hypervisors
        vlan_id (int): vlan id to filter out the network
        net_name (str):
        strict (bool):
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (list): list of network names with given pci interfaces with given minimum host number

    """
    valid_types = ['pci-sriov', 'pci-passthrough']
    if pci_type not in valid_types:
        raise ValueError("pci_type has to be one of these: {}".format(valid_types))

    LOG.info("Searching for networks with {} interface on at least {} hosts".format(pci_type, min_hosts))
    hosts_and_pnets = host_helper.get_hosts_and_pnets_with_pci_devs(pci_type=pci_type, up_hosts_only=up_hosts_only,
                                                                    con_ssh=con_ssh, auth_info=auth_info)

    all_pci_pnets = []
    for pnets in hosts_and_pnets.values():
        all_pci_pnets = all_pci_pnets + pnets

    all_pci_pnets = list(set(all_pci_pnets))

    LOG.info("All pnets: {}".format(all_pci_pnets))

    specified_nets = []
    internal_nets = []
    tenant_nets = []
    mgmt_nets = []

    for pci_net in all_pci_pnets:
        hosts_with_pnet = []
        for host, pnets in hosts_and_pnets.items():
            if pci_net in pnets:
                hosts_with_pnet.append(host)

        if len(hosts_with_pnet) >= min_hosts:
            pnet_id = get_providernets(name=pci_net, rtn_val='id', strict=True, con_ssh=con_ssh, auth_info=auth_info)[0]
            nets_on_pnet = get_networks_on_providernet(providernet_id=pnet_id, rtn_val='name', con_ssh=con_ssh,
                                                       auth_info=auth_info, vlan_id=vlan_id)

            # TODO: US102722 wrs-net:vlan_id removed from neutron subnets
            other_nets = get_networks_on_providernet(providernet_id=pnet_id, rtn_val='name', con_ssh=con_ssh,
                                                     auth_info=auth_info, vlan_id=vlan_id, exclude=True)

            nets_on_pnet = nets_on_pnet + other_nets

            for net in nets_on_pnet:
                if net_name:
                    if strict:
                        if re.match(net_name, net):
                            specified_nets.append(net)
                    else:
                        if re.search(net_name, net):
                            specified_nets.append(net)
                # If net_name unspecified:
                elif re.search(Networks.INTERNAL_NET_NAME, net):
                    internal_nets.append(net)
                elif re.search(Networks.data_net_name_pattern(), net):
                    tenant_nets.append(net)
                elif re.search(Networks.mgmt_net_name_pattern(), net):
                    mgmt_nets.append(net)
                else:
                    LOG.warning("Unknown network with {} interface: {}. Ignore.".format(pci_type, net))

    for nets in (specified_nets, internal_nets, tenant_nets, mgmt_nets):
        if nets:
            nets_counts = Counter(nets)
            nets = sorted(nets_counts.keys(), key=nets_counts.get, reverse=True)
            LOG.info("Preferred networks for {} interfaces with at least {} hosts: {}".format(
                pci_type, min_hosts, nets))
            return nets

    LOG.warning("No networks found for {} interfaces with at least {} hosts".format(pci_type, min_hosts))
    return []


def _get_preferred_nets(nets, net_name=None, strict=False):
    specified_nets = []
    internal_nets = []
    tenant_nets = []
    mgmt_nets = []

    for net in nets:
        if net_name:
            if strict:
                if re.match(net_name, net):
                    specified_nets.append(net)
            else:
                if re.search(net_name, net):
                    specified_nets.append(net)
        # If net_name unspecified:
        elif re.search(Networks.INTERNAL_NET_NAME, net):
            internal_nets.append(net)
        elif re.search(Networks.data_net_name_pattern(), net):
            tenant_nets.append(net)
        elif re.search(Networks.mgmt_net_name_pattern(), net):
            mgmt_nets.append(net)
        else:
            LOG.warning("Unknown network: {}. Ignore.".format(net))

    for nets_ in (specified_nets, internal_nets, tenant_nets, mgmt_nets):
        if nets_:
            nets_counts = Counter(nets_)
            nets_ = sorted(nets_counts.keys(), key=nets_counts.get, reverse=True)
            LOG.info("Preferred networks selected: {}".format(nets_))
            return nets_


def create_port_forwarding_rule(router_id, inside_addr=None, inside_port=None, outside_port=None, protocol='tcp',
                                tenant=None, description=None, fail_ok=False, auth_info=Tenant.get('admin'), con_ssh=None):
    """

    Args:
        router_id (str): The router_id of the tenant router the portforwarding rule is created
        inside_addr(str): private ip address
        inside_port (int|str):  private protocol port number
        outside_port(int|str): The public layer4 protocol port number
        protocol(str): the protocol  tcp|udp|udp-lite|sctp|dccp
        tenant(str): The owner Tenant id.
        description(str): User specified text description. The default is "portforwarding"
        fail_ok:
        auth_info:
        con_ssh:

    Returns (tuple):
        0, <portforwarding rule id>, <success msg>    - Portforwarding rule created successfully
        1, '', <std_err>              - Portforwarding rule create cli rejected
        2, '', <std_err>  - Portforwarding rule create failed; one or more values required are not specified.


    """
    # Process args
    if tenant is None:
        tenant = Tenant.get_primary()['tenant']

    if description is None:
        description = '"portforwarding"'

    tenant_id = keystone_helper.get_tenant_ids(tenant, con_ssh=con_ssh)[0]

    mgmt_ips_for_vms = get_mgmt_ips_for_vms()

    if inside_addr not in mgmt_ips_for_vms:
        msg = "The inside_addr {} must be one of the  vm mgmt internal addresses: {}.".format(inside_addr,
                                                                                              mgmt_ips_for_vms)
        return 1,  msg

    args_dict = {
        '--tenant-id': tenant_id if auth_info == Tenant.get('admin') else None,
        '--inside_addr': inside_addr,
        '--inside-port': inside_port,
        '--outside-port': outside_port,
        '--protocol': protocol,
        '--description': description,
    }
    args = router_id

    for key, value in args_dict.items():
        if value is None:
            msg = 'A value must be specified for {}'.format(key)
            if fail_ok:
                return 1, '', msg
            raise exceptions.NeutronError(msg)
        else:
            args = "{} {} {}".format(key, value, args)

    LOG.info("Creating port forwarding with args: {}".format(args))
    # send portforwarding-create cli
    code, output = cli.neutron('portforwarding-create', args, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                               rtn_list=True)

    # process result
    if code == 1:
        msg = 'Fail to create port forwarding rules: {}'.format(output)
        if fail_ok:
            return 1, '', msg
        raise exceptions.NeutronError(msg)

    table_ = table_parser.table(output)
    portforwarding_id = table_parser.get_value_two_col_table(table_, 'id')

    expt_values = {
        'router_id': router_id,
        'tenant_id': tenant_id
    }

    for field, expt_val in expt_values.items():
        if table_parser.get_value_two_col_table(table_, field) != expt_val:
            msg = "{} is not set to {} for portforwarding {}".format(field, expt_val, router_id)
            if fail_ok:
                return 2, portforwarding_id, msg
            raise exceptions.NeutronError(msg)

    succ_msg = "Portforwarding {} is created successfully.".format(portforwarding_id)
    LOG.info(succ_msg)
    return 0, portforwarding_id, succ_msg


def create_port_forwarding_rule_for_vm(vm_id, inside_addr=None, inside_port=None, outside_port=None, protocol='tcp',
                                       description=None, fail_ok=False, auth_info=Tenant.get('admin'), con_ssh=None):
    """

    Args:
        vm_id (str): The id of vm the portforwarding rule is created for
        inside_addr(str): private ip address; default is mgmt address of vm.
        inside_port (str):  private protocol port number; default is 80 ( web port)
        outside_port(str): The public layer4 protocol port number; default is 8080
        protocol(str): the protocol  tcp|udp|udp-lite|sctp|dccp; default is tcp
        description(str): User specified text description. The default is "portforwarding"
        fail_ok:
        auth_info:
        con_ssh:

    Returns (tuple):
        0, <portforwarding rule id>, <success msg>    - Portforwarding rule created successfully
        1, '', <std_err>              - Portforwarding rule create cli rejected
        2, '', <std_err>  - Portforwarding rule create failed; one or more values required are not specified.


    """
    # Process args
    router_id = get_tenant_router()

    if inside_addr is None:
        inside_addr = get_mgmt_ips_for_vms(vm_id)[0]
    if inside_port is None:
        inside_port = "80"

    if outside_port is None:
        outside_port = "8080"

    return create_port_forwarding_rule(router_id, inside_addr=inside_addr, inside_port=inside_port,
                                       outside_port=outside_port, protocol=protocol,
                                       description=description, fail_ok=fail_ok, auth_info=auth_info,
                                       con_ssh=con_ssh)


def update_portforwarding_rule(portforwarding_id, inside_addr=None, inside_port=None, outside_port=None,
                               protocol=None, description=None, fail_ok=False,
                               auth_info=Tenant.get('admin'), con_ssh=None):
    """

    Args:
        portforwarding_id (str): Id or name of portfowarding rule to update
        inside_addr (str): Private ip address
        inside_port (str): Private layer4 protocol port
        outside_port (str): Public layer4 protocol port
        protocol (str): protocol name tcp|udp|udp-lite|sctp|dccp
        description (str): User specified text description
        fail_ok:
        auth_info:
        con_ssh:

    Returns (tuple):
        0,  <command ouput>    - Portforwarding rule updated successfully


    """

    if portforwarding_id is None or not isinstance(portforwarding_id, str):
        raise ValueError("Expecting string value for portforwarding_id. Get {}".format(type(portforwarding_id)))

    args = ''

    args_dict = {
        '--inside_addr': inside_addr,
        '--inside_port': inside_port,
        '--outside_port': outside_port,
        '--protocol': protocol,
        '--description': description,
    }

    for key, value in args_dict.items():
        if value is not None:
            args += ' {} {}'.format(key, value)

    if not args:
        raise ValueError("At least of the args need to be specified.")

    LOG.info("Updating router {}: {}".format(portforwarding_id, args))

    args = '{} {}'.format(portforwarding_id, args.strip())
    return cli.neutron('portforwarding-update', args, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                       rtn_list=True, force_neutron=True)


def delete_portforwarding_rules(pf_ids, auth_info=Tenant.get('admin'), con_ssh=None, fail_ok=False):
    """
    Deletes list of portforwarding rules

    Args:
        pf_ids(list): list of portforwarding rules to be deleted.
        auth_info:
        con_ssh:
        fail_ok:

    Returns (tuple):
        0,  <command output>    - Portforwarding rules delete successful

    """
    if pf_ids is None or len(pf_ids) == 0:
        return 0, None

    for pf_id in pf_ids:
        rc, output = delete_portforwarding_rule(pf_id, auth_info=auth_info, con_ssh=con_ssh, fail_ok=fail_ok)
        if rc != 0:
            return rc, output
    return 0, None


def delete_portforwarding_rule(portforwarding_id, auth_info=Tenant.get('admin'), con_ssh=None, fail_ok=False):
    """
    Deletes a single portforwarding rule
    Args:
        portforwarding_id (str): Id or name of portforwarding rule to delete.
        auth_info:
        con_ssh:
        fail_ok:

    Returns (tuple):
        0,  <command output>    - Portforwarding rules delete successful
        1, <err_msg> - Portforwarding rules delete cli rejected
        2, <err_msg> - Portforwarding rules delete fail

    """

    LOG.info("Deleting port-forwarding {}...".format(portforwarding_id))
    code, output = cli.neutron('portforwarding-delete', portforwarding_id, ssh_client=con_ssh, auth_info=auth_info,
                               fail_ok=fail_ok, rtn_list=True)
    if code != 0:
        msg = "CLI rejected. Fail to delete Port-forwarding {}; {}".format(portforwarding_id, output)
        LOG.warn(msg)
        if fail_ok:
            return code, msg
        else:
            raise exceptions.NeutronError(msg)

    portforwardings = get_portforwarding_rules(auth_info=auth_info, con_ssh=con_ssh)
    if portforwarding_id in portforwardings:
        msg = "Port-forwarding {} is still showing in neutron portforwarding-list".format(portforwarding_id)
        if fail_ok:
            LOG.warning(msg)
            return 2, msg

    succ_msg = "Port-forwarding {} is successfully deleted.".format(portforwarding_id)
    LOG.info(succ_msg)
    return 0, succ_msg


def get_portforwarding_rules(router_id=None, inside_addr=None, inside_port=None, outside_port=None,
                             protocol=None,  strict=True, auth_info=None, con_ssh=None):
    """
    Get porforwarding id(s) based on given criteria.
    Args:
        router_id (str): portforwarding router id
        inside_addr (str): portforwarding  inside_addr
        inside_port (str): portforwarding  inside_port
        outside_port (str): portforwarding   outside_port"
        protocol (str):  portforwarding  protocol
        strict (bool):
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (list): list of porforwarding id(s)

    """

    param_dict = {
        'router_id': router_id,
        'inside_addr': inside_addr,
        'inside_port': inside_port,
        'outside_port': outside_port,
        'protocol': protocol,
    }

    final_params = {}
    for key, val in param_dict.items():
        if val is not None:
            final_params[key] = str(val)

    table_ = table_parser.table(cli.neutron('portforwarding-list', ssh_client=con_ssh, auth_info=auth_info),
                                combine_multiline_entry=True)
    if not table_parser.get_all_rows(table_):
        return []

    if router_id is not None:
        table_ = table_parser.filter_table(table_, strict=strict, router_id=router_id)

    return table_parser.get_values(table_, 'id', **final_params)


def get_portforwarding_rule_info(portforwarding_id, field='inside_addr', strict=True, auth_info=Tenant.get('admin'),
                                 con_ssh=None):
    """
    Get value of specified field for given portforwarding rule

    Args:
        portforwarding_id (str): Id or name of portforwarding rule
        field (str): the name of the field attribute
        strict (bool):
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (str): value of specified field for given portforwarding rule

    """

    table_ = table_parser.table(cli.neutron('portforwarding-show', portforwarding_id, ssh_client=con_ssh,
                                            auth_info=auth_info), combine_multiline_entry=True)
    return table_parser.get_value_two_col_table(table_, field, strict)


def create_port(net_id, name=None, tenant=None, fixed_ips=None, device_id=None, device_owner=None, port_security=None,
                admin_state_down=None, mac_addr=None, vnic_type=None, security_groups=None, no_security_groups=None,
                extra_dhcp_opts=None, qos_pol=None, allowed_addr_pairs=None, no_allowed_addr_pairs=None, dns_name=None,
                wrs_vif=None, fail_ok=False, auth_info=None, con_ssh=None):
    """
    Create a port on given network

    Args:
        net_id (str): network id to create port for
        name (str): name of the new port
        tenant (str): tenant name. such as tenant1, tenant2
        fixed_ips (str|list): e.g., ["subnet_id=SUBNET_1,ip_address=IP_ADDR_1",
                                    "subnet_id=SUBNET_2,ip_address=IP_ADDR_2]
        device_id (str): device id of this port
        device_owner (str): Device owner of this port
        port_security (None|bool):
        admin_state_down (bool): Set admin state up to false
        mac_addr (str):  MAC address of this port
        vnic_type: one of the: <direct | direct-physical | macvtap | normal | baremetal>
        security_groups (str|list): Security group(s) associated with the port
        no_security_groups (bool): Associate no security groups with the port
        extra_dhcp_opts (str|list): Extra dhcp options to be assigned to this port:
                e.g., "opt_name=<dhcp_option_name>,opt_value=<value>,ip_version={4,6}"
        qos_pol (str):  Attach QoS policy ID or name to the resource
        allowed_addr_pairs (str|list):  Allowed address pair associated with the port.
                e.g., "ip_address=IP_ADDR[,mac_address=MAC_ADDR]"
        no_allowed_addr_pairs (bool): Associate no allowed address pairs with the port
        dns_name (str):  Assign DNS name to the port (requires DNS integration extension)
        wrs_vif
        fail_ok (bool):
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (tuple): (<rtn_code>, <err_msg|port_id>)
        (0, <port_id>)  - port created successfully
        (1, <std_err>)  - CLI rejected
        (2, "Network ID for created port is not as specified.")     - post create check fail

    """
    LOG.info("Creating port on network {}".format(net_id))
    if not net_id:
        raise ValueError("network id is required")
    tenant_id = keystone_helper.get_tenant_ids(tenant_name=tenant, con_ssh=con_ssh)[0] if tenant else None

    args = '--network {}'.format(net_id)
    args_dict = {
        '--admin-state-down': admin_state_down,
        '--no-security-groups': no_security_groups,
        '--no-allowed-address-pairs': no_allowed_addr_pairs,
        '--enable-port-security': True if port_security else None,
        '--disable-port-security': True if port_security is False else None,
    }

    for key, val in args_dict.items():
        if val:
            args += ' {}'.format(key)

    kwargs_dict = {
        '--tenant-id': tenant_id,
        '--device-id': device_id,
        '--device-owner': device_owner,
        '--mac-address': mac_addr,
        '--vnic-type': vnic_type,
        # '--binding-profile':
        '--qos-policy': qos_pol,
        '--dns-name': dns_name,
        '--wrs-binding:vif_model': wrs_vif,
    }

    for key, val in kwargs_dict.items():
        if val is not None:
            args += ' {} {}'.format(key, val)

    repeatable_dict = {
        '--extra-dhcp-opt': extra_dhcp_opts,
        '--fixed-ip': fixed_ips,
        '--allowed-address-pair': allowed_addr_pairs,
        '--security-group': security_groups,
    }

    for key, vals in repeatable_dict.items():
        if vals:
            if isinstance(vals, str):
                vals = [vals]
            for val in vals:
                args += ' {} {}'.format(key, val)

    args += ' {}'.format(name)

    code, output = cli.openstack('port create', args, ssh_client=con_ssh, fail_ok=fail_ok, rtn_list=True,
                                 auth_info=auth_info)

    if code == 1:
        return code, output

    port_tab = table_parser.table(output)
    port_net_id = table_parser.get_value_two_col_table(port_tab, 'network_id')
    port_id = table_parser.get_value_two_col_table(port_tab, 'id')
    if not net_id == port_net_id:
        err_msg = "Network ID for created port is not as specified. Expt:{}; Actual: {}".format(net_id, port_net_id)
        if fail_ok:
            LOG.warning(err_msg)
            return 2, port_id

    succ_msg = "Port {} is successfully created on network {}".format(port_id, net_id)
    LOG.info(succ_msg)
    return 0, port_id


def delete_port(port_id, fail_ok=False, auth_info=Tenant.get('admin'), con_ssh=None):
    """
    Delete given port
    Args:
        port_id (str):
        fail_ok (bool):
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (tuple): (<rtn_code>, <msg>)
        (0, "Port <port_id> is successfully deleted")
        (1, <std_err>)  - delete port cli rejected
        (2, "Port <port_id> still exists after deleting")   - post deletion check failed

    """
    LOG.info("Deleting port: {}".format(port_id))
    if not port_id:
        msg = "No port specified"
        LOG.warning(msg)
        return -1, msg

    code, output = cli.neutron('port-delete', port_id, ssh_client=con_ssh, fail_ok=fail_ok, rtn_list=True,
                               auth_info=auth_info, )

    if code == 1:
        return 1, output

    existing_ports = get_ports(rtn_val='id')
    if port_id in existing_ports:
        err_msg = "Port {} still exists after deleting".format(port_id)
        if fail_ok:
            LOG.warning(err_msg)
            return 2, err_msg
        raise exceptions.NeutronError(err_msg)

    succ_msg = "Port {} is successfully deleted".format(port_id)
    LOG.info(succ_msg)
    return 0, succ_msg


def get_ports(rtn_val='id', port_id=None, port_name=None, port_mac=None, ip_addr=None, subnet_id=None, strict=False,
              auth_info=Tenant.get('admin'), con_ssh=None, merge_lines=True):
    """
    Get a list of ports with given arguments
    Args:
        rtn_val (str): any valid header of neutron port-list table. 'id', 'name', 'mac_address', or 'fixed_ips'
        port_id (str): id of the port
        port_name (str): name of the port
        port_mac (str): mac address of the port
        ip_addr (str): ip of the port
        subnet_id (str): subnet of the port
        strict (bool):
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (list):

    """
    table_ = table_parser.table(cli.neutron('port-list', ssh_client=con_ssh, auth_info=auth_info))
    fixed_ips = ''
    if subnet_id:
        fixed_ips += subnet_id
    if ip_addr:
        fixed_ips += ".*{}".format(ip_addr)

    args_dict = {
        'id': port_id,
        'fixed_ips': fixed_ips,
        'name': port_name,
        'mac_address': port_mac,
    }
    kwargs = {}
    for key, value in args_dict.items():
        if value:
            kwargs[key] = value

    ports = table_parser.get_values(table_, rtn_val, strict=strict, regex=True, merge_lines=merge_lines, **kwargs)
    return ports


def get_pci_device_configured_vfs_value(device_id, con_ssh=None, auth_info=None):
    """
    Get PCI device configured vfs value for given device id

    Args:
        device_id (str):  device vf id
        con_ssh:
        auth_info:

    Returns:
        str :

    """
    _table = table_parser.table(cli.nova('device-list', ssh_client=con_ssh, auth_info=auth_info))
    LOG.info('output of nova device-list:{}'.format(_table))
    _table = table_parser.filter_table(_table, **{'Device Id': device_id})
    return table_parser.get_column(_table, 'pci_vfs_configured')[0]


def get_pci_device_used_vfs_value(device_id, con_ssh=None, auth_info=None):
    """
    Get PCI device used number of vfs value for given device id

    Args:
        device_id (str):  device vf id
        con_ssh:
        auth_info:

    Returns:
        str :

    """
    _table = table_parser.table(cli.nova('device-list', ssh_client=con_ssh, auth_info=auth_info))
    LOG.info('output of nova device-list:{}'.format(_table))
    _table = table_parser.filter_table(_table, **{'Device Id': device_id})
    LOG.info('output of nova device-list:{}'.format(_table))
    return table_parser.get_column(_table, 'pci_vfs_used')[0]


def get_pci_device_vfs_counts_for_host(host, device_id=None, fields=('pci_vfs_configured', 'pci_vfs_used'),
                                       con_ssh=None, auth_info=Tenant.get('admin')):
    """
    Get PCI device used number of vfs value for given device id

    Args:
        host (str): compute hostname
        device_id (str):  device vf id
        fields (tuple|str|list)
        con_ssh:
        auth_info:

    Returns:
        list

    """
    if device_id is None:
        device_id = get_pci_device_list_values(field='Device Id', con_ssh=con_ssh, auth_info=auth_info)[0]

    table_ = table_parser.table(cli.nova('device-show {}'.format(device_id), ssh_client=con_ssh, auth_info=auth_info))
    LOG.debug('output from nova device-show for device-id:{}\n{}'.format(device_id, table_))

    table_ = table_parser.filter_table(table_, host=host)
    counts = []
    if isinstance(fields, str):
        fields = [fields]

    for field in fields:
        counts.append(int(table_parser.get_column(table_, field)[0]))

    return counts


def get_pci_device_list_values(field='pci_vfs_used', con_ssh=None, auth_info=Tenant.get('admin'), **kwargs):
    table_ = table_parser.table(cli.nova('device-list', ssh_client=con_ssh, auth_info=auth_info))

    values = table_parser.get_values(table_, field, **kwargs)
    if field in ['pci_pfs_configured', 'pci_pfs_used', 'pci_vfs_configured', 'pci_vfs_used']:
        values = [int(value) for value in values]

    return values


def get_pci_device_list_info(con_ssh=None, header_key='pci alias', auth_info=Tenant.get('admin'), **kwargs):
    table_ = table_parser.table(cli.nova('device-list', ssh_client=con_ssh, auth_info=auth_info))
    if kwargs:
        table_ = table_parser.filter_table(table_, **kwargs)

    return table_parser.row_dict_table(table_, key_header=header_key)


def get_tenant_routers_for_vms(vms, con_ssh=None):
    """
    Get tenant routers for given vm

    Args:
        vms (str|list):
        con_ssh (SSHClient):

    Returns (list): list of router ids or names

    """
    if isinstance(vms, str):
        vms = [vms]

    auth_info = Tenant.get('admin')
    field = 'tenant_id'
    vms_tenants = []
    for vm in vms:
        vm_tenant = nova_helper.get_vm_nova_show_value(vm_id=vm, field=field, strict=True, con_ssh=con_ssh,
                                                       auth_info=auth_info)
        vms_tenants.append(vm_tenant)

    vms_tenants = list(set(vms_tenants))

    all_routers = get_routers(auth_info=auth_info)
    vms_routers = []
    for router in all_routers:
        router_tenant = get_router_info(router, field=field, strict=True, auth_info=auth_info, con_ssh=con_ssh)
        if router_tenant in vms_tenants:
            vms_routers.append(router)
            if len(vms_routers) == len(vms_tenants):
                break

    if len(vms_routers) < len(vms_tenants):
        LOG.error("Cannot find tenant router for all vms. VMS: {}. Matching routers: {}".format(vms, vms_routers))

    return vms_routers


def collect_networking_info(routers=None, vms=None, sep_file=None):
    LOG.info("Ping tenant(s) router's external and internal gateway IPs")

    if not routers:
        if vms:
            if isinstance(vms, str):
                vms = [vms]
            routers = get_tenant_routers_for_vms(vms=vms)
        else:
            routers = get_routers(name='tenant[12]-router', regex=True, auth_info=Tenant.get('admin'))
    elif isinstance(routers, str):
        routers = [routers]

    ips_to_ping = []
    for router_ in routers:
        router_ips = get_router_subnets(router_id=router_, rtn_val='ip_address', mgmt_only=True)
        ips_to_ping += router_ips

    res_bool, res_dict = ping_ips_from_natbox(ips_to_ping, num_pings=3, timeout=15)
    if sep_file:
        res_str = "succeeded" if res_bool else 'failed'
        content = "#### Ping router interfaces {} ####\n{}\n".format(res_str, res_dict)
        common.write_to_file(sep_file, content=content)

    if ProjVar.get_var('ALWAYS_COLLECT'):
        common.collect_software_logs()

    hosts = host_helper.get_up_hypervisors()
    for router in routers:
        router_host = get_router_info(router_id=router, field='wrs-net:host')
        if router_host and router_host not in hosts:
            hosts.append(router_host)
        LOG.info("Router {} is hosted on {}".format(router, router_host))

    if hosts:
        is_avs = system_helper.is_avs()
        vswitch_type = 'avs' if is_avs else 'ovs'
        LOG.info("Collect {}.info for {} router(s) on router host(s): ".format(vswitch_type, routers, hosts))
        for host in hosts:
            content = collect_vswitch_info_on_host(host, vswitch_type, collect_extra_ovs=(not is_avs))
            if sep_file:
                common.write_to_file(sep_file, content=content)


def ping_ips_from_natbox(ips, natbox_ssh=None, num_pings=5, timeout=30):
    if not natbox_ssh:
        natbox_ssh = NATBoxClient.get_natbox_client()

    res_dict = {}
    for ip_ in ips:
        packet_loss_rate = ping_server(server=ip_, ssh_client=natbox_ssh, num_pings=num_pings, timeout=timeout,
                                       fail_ok=True, vshell=False)[0]
        res_dict[ip_] = packet_loss_rate

    res_bool = not any(loss_rate == 100 for loss_rate in res_dict.values())
    # LOG.error("PING RES: {}".format(res_dict))
    if res_bool:
        LOG.info("Ping successful from NatBox: {}".format(ips))
    else:
        LOG.warning("Ping unsuccessful from NatBox: {}".format(res_dict))

    return res_bool, res_dict


def collect_vswitch_info_on_host(host, vswitch_type, collect_extra_ovs=False):
    """

    Args:
        host (str):
        vswitch_type (str): avs or ovs

    Returns:

    """
    with host_helper.ssh_to_host(host) as host_ssh:
        host_ssh.exec_sudo_cmd('/etc/collect.d/collect_{}'.format(vswitch_type), searchwindowsize=50,
                               get_exit_code=False)
        vswitch_info_path = '/scratch/var/extra/{}.info'.format(vswitch_type)
        vswitch_info = host_ssh.exec_cmd('cat {}'.format(vswitch_info_path), searchwindowsize=50)[1]
        content = '\n##### {} {}.info collected ##### \n{}\n'.format(host, vswitch_type, vswitch_info)
        host_ssh.exec_sudo_cmd('rm -f {}'.format(vswitch_info_path))
        if collect_extra_ovs:
            content += "\n#### Additional ovs cmds on {} #### ".format(host)
            for cmd in ('ovs-ofctl show br-int', 'ovs-ofctl dump-flows br-int', 'ovs-appctl dpif/dump-flows br-int'):
                output = host_ssh.exec_sudo_cmd(cmd)[1]
                content += '\nSent: sudo {}\nOutput:\n{}\n'.format(cmd, output)

        # vswitch log will be saved to /scratch/var/extra/avs.info on the compute host
    return content


def get_pci_device_numa_nodes(hosts):
    """
    Get processors of crypto PCI devices for given hosts

    Args:
        hosts (list): list of hosts to check

    Returns (dict): host, numa_nodes map. e.g., {'compute-0': ['0'], 'compute-1': ['0', '1']}

    """
    hosts_numa = {}
    for host in hosts:
        numa_nodes = host_helper.get_host_device_list_values(host, field='numa_node')
        hosts_numa[host] = numa_nodes

    LOG.info("Hosts numa_nodes map for PCI devices: {}".format(hosts_numa))
    return hosts_numa


def get_pci_procs(hosts, net_type='pci-sriov'):
    """
    Get processors of pci-sriov or pci-passthrough devices for given hosts

    Args:
        hosts (list): list of hosts to check
        net_type (str): pci-sriov or pci-passthrough

    Returns (dict): host, procs map. e.g., {'compute-0': ['0'], 'compute-1': ['0', '1']}

    """
    hosts_procs = {}
    for host in hosts:
        ports_list = system_helper.get_host_interfaces_info(host, rtn_val='ports', net_type=net_type)

        ports = []
        for port in ports_list:
            ports += port
        ports = list(set(ports))

        procs = system_helper.get_host_ports_values(host, header='processor', **{'name': ports})
        hosts_procs[host] = list(set(procs))

    LOG.info("Hosts procs map for {} devices: {}".format(net_type, hosts_procs))
    return hosts_procs


def wait_for_agents_alive(hosts=None, timeout=120, fail_ok=False, con_ssh=None, auth_info=Tenant.get('admin')):
    """
    Wait for neutron agents to be alive
    Args:
        hosts (str|list): hostname(s) to check. When None, all nova hypervisors will be checked
        timeout (int): max wait time in seconds
        fail_ok (bool): whether to return False or raise exception when non-alive agents exist
        con_ssh (SSHClient):
        auth_info (dict):

    Returns (tuple): (<res>(bool), <msg>(str))
        (True, "All agents for <hosts> are alive")
        (False, "Some agents are not alive: <non_alive_rows>")      Applicable when fail_ok=True

    """
    if hosts is None:
        hosts = host_helper.get_hypervisors(con_ssh=con_ssh)
    elif isinstance(hosts, str):
        hosts = [hosts]

    agents_tab = None
    LOG.info("Wait for neutron agents to be alive for {}".format(hosts))
    end_time = time.time() + timeout
    while time.time() < end_time:
        agents_tab = table_parser.table(cli.neutron('agent-list', ssh_client=con_ssh, auth_info=auth_info))
        agents_tab = table_parser.filter_table(agents_tab, host=hosts)
        alive_vals = table_parser.get_column(agents_tab, 'alive')
        if all(alive_val == ':-)' for alive_val in alive_vals):
            succ_msg = "All agents for {} are alive".format(hosts)
            LOG.info(succ_msg)
            return True, succ_msg

    LOG.warning("Some neutron agents are not alive")
    non_alive_tab = table_parser.filter_table(agents_tab, exclude=True, alive=':-)')
    non_alive_rows = table_parser.get_all_rows(non_alive_tab)
    msg = "Some agents are not alive: {}".format(non_alive_rows)
    if fail_ok:
        return False, msg
    raise exceptions.NeutronError(msg)


def get_trunks(rtn_val='id', trunk_id=None, trunk_name=None, parent_port=None, strict=False,
               auth_info=Tenant.get('admin'), con_ssh=None):
    """
    Get a list of trunks with given arguments
    Args:
        rtn_val (str): any valid header of neutron trunk list table. 'id', 'name', 'mac_address', or 'fixed_ips'
        trunk_id (str): id of the trunk
        trunk_name (str): name of the trunk
        parent_port (str): parent port of the trunk
        strict (bool):
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (list):

    """
    table_ = table_parser.table(cli.openstack('network trunk list', ssh_client=con_ssh, auth_info=auth_info))

    args_dict = {
        'id': trunk_id,
        'name': trunk_name,
        'parent_port': parent_port,
    }
    kwargs = {}
    for key, value in args_dict.items():
        if value:
            kwargs[key] = value

    trunks = table_parser.get_values(table_, rtn_val, strict=strict, regex=True, merge_lines=True, **kwargs)
    return trunks


def create_trunk(port_id, tenant_name=None, name=None, admin_state_up=True, sub_ports=None,
                 fail_ok=False, con_ssh=None, auth_info=Tenant.get('admin')):
    """Create a trunk via API.
    Args:
        port_id: Parent port of trunk.
        tenant_name: tenant name to create the trunk under.
        name: Name of the trunk.
        admin_state_up: Admin state of the trunk.
        sub_ports: List of subport dictionaries in format
            [[<ID of neutron port for subport>,
             segmentation_type(vlan),
             segmentation_id(<VLAN tag>)] []..]
        fail_ok
        con_ssh
        auth_info

    Return: List with trunk's data returned from Neutron API.
    """
    if port_id is None:
        raise ValueError("port_id has to be specified for parent port.")
    if name is None:
        name = common.get_unique_name(name_str='trunk')

    if tenant_name is None:
        tenant_name = Tenant.get_primary()['tenant']

    tenant_id = keystone_helper.get_tenant_ids(tenant_name, con_ssh=con_ssh)[0]
    args = '--parent-port ' + port_id
    args += " --project " + format(tenant_id)
    keys = ['port', 'segmentation-type', 'segmentation-id']
    if sub_ports is not None:
        for sub_port in sub_ports:
            tmp_list = []
            for key in keys:
                val = sub_port.get(key)
                if val is not None:
                    tmp_list.append('{}={}'.format(key, val))
            args += ' --subport '+','.join(tmp_list)

    if admin_state_up:
        args += ' --enable'
    else:
        args += ' --disable'
    args += ' ' + name

    LOG.info("Creating port trunk for port: {}. Args: {}".format(port_id, args))
    code, output = cli.openstack('network trunk create', args, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                                 rtn_list=True)

    if code == 1:
        return 1, '', output

    table_ = table_parser.table(output)
    trunk_tenant_id = table_parser.get_value_two_col_table(table_, 'tenant_id')
    trunk_id = table_parser.get_value_two_col_table(table_, 'id')

    expt_tenant_name = tenant_name if tenant_name else common.get_tenant_name(auth_info)
    if trunk_tenant_id != keystone_helper.get_tenant_ids(expt_tenant_name)[0]:
        msg = "Trunk {} is not for tenant: {}".format(trunk_id, expt_tenant_name)
        if fail_ok:
            LOG.warning(msg)
            return 2, trunk_id, msg
        raise exceptions.NeutronError(msg)

    succ_msg = "Trunk {} is successfully created for tenant {}".format(trunk_id, expt_tenant_name)
    LOG.info(succ_msg)
    return 0, trunk_id, succ_msg


def delete_trunk(trunk_id, fail_ok=False, auth_info=Tenant.get('admin'), con_ssh=None):
    """
    Delete given trunk
    Args:
        trunk_id (str):
        fail_ok (bool):
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (tuple): (<rtn_code>, <msg>)
        (0, "Port <trunk_id> is successfully deleted")
        (1, <std_err>)  - delete port cli rejected
        (2, "trunk <trunk_id> still exists after deleting")   - post deletion check failed

    """
    LOG.info("Deleting trunk: {}".format(trunk_id))
    if not trunk_id:
        msg = "No trunk specified"
        LOG.warning(msg)
        return -1, msg

    code, output = cli.openstack('network trunk delete', trunk_id, ssh_client=con_ssh, fail_ok=fail_ok, rtn_list=True,
                                 auth_info=auth_info, )

    if code == 1:
        return 1, output

    existing_trunks = get_trunks(rtn_val='id')
    if trunk_id in existing_trunks:
        err_msg = "Trunk {} still exists after deleting".format(trunk_id)
        if fail_ok:
            LOG.warning(err_msg)
            return 2, err_msg
        raise exceptions.NeutronError(err_msg)

    succ_msg = "Trunk {} is successfully deleted".format(trunk_id)
    LOG.info(succ_msg)
    return 0, succ_msg


def add_trunk_subports(trunk_id, sub_ports=None, fail_ok=False, con_ssh=None, auth_info=Tenant.get('admin')):
    """Add subports to a trunk via API.
    Args:
        trunk_id: Trunk id to add the subports
        sub_ports: List of subport dictionaries in format
            [[<ID of neutron port for subport>,
             segmentation_type(vlan),
             segmentation_id(<VLAN tag>)] []..]
        fail_ok
        con_ssh
        auth_info

    Return: list with return code and msg.
    """

    args = ''
    if trunk_id is None:
        raise ValueError("port_id has to be specified for parent port.")

    if sub_ports is None:
        raise ValueError("port_id has to be specified for parent port.")

    keys = ['port', 'segmentation-type', 'segmentation-id']
    args += trunk_id
    if sub_ports is not None:
        for sub_port in sub_ports:
            tmp_list = []
            for key in keys:
                val = sub_port.get(key)
                if val is not None:
                    tmp_list.append('{}={}'.format(key, val))
            args += ' --subport '+','.join(tmp_list)

    LOG.info("Adding subport to trunk: {}. Args: {}".format(trunk_id, args))
    code, output = cli.openstack('network trunk set', args, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                                 rtn_list=True)

    if code == 1:
        return 1, output

    msg = 'Subport is added successfully'
    return 0, msg


def remove_trunk_subports(trunk_id, tenant_name=None, sub_ports=None, fail_ok=False, con_ssh=None,
                          auth_info=Tenant.get('admin')):
    """Remove subports from a trunk via API.
    Args:
        trunk_id: Trunk id to remove the subports from
        tenant_name
        sub_ports: List of subport
        fail_ok
        con_ssh
        auth_info

    Return: list with return code and msg
    """
    args = ''
    if trunk_id is None:
        raise ValueError("port_id has to be specified for parent port.")

    if sub_ports is None:
        raise ValueError("port_id has to be specified for parent port.")

    args += trunk_id

    for sub_port in sub_ports:
        args += ' --subport'
        args += ' ' + sub_port

    LOG.info("Removing subport from trunk: {}. Args: {}".format(trunk_id, args))
    code, output = cli.openstack('network trunk unset', args, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                                 rtn_list=True)
    if code == 1:
        return 1, output

    msg = 'Subport is removed successfully'
    return 0, msg


def get_networks(name=None, cidr=None, strict=True, regex=False, auth_info=None, con_ssh=None):
    """
    Get networks ids based on given criteria.

    Args:
        name (str): name of the network
        cidr (str): cidr of the network
        strict (bool): whether to perform strict search on given name and cidr
        regex (bool): whether to use regext to search
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (list): a list of network ids

    """
    table_ = table_parser.table(cli.neutron('net-list', ssh_client=con_ssh, auth_info=auth_info))
    if name is not None:
        table_ = table_parser.filter_table(table_, strict=strict, regex=regex, name=name)
    if cidr is not None:
        table_ = table_parser.filter_table(table_, strict=strict, regex=regex, cidr=cidr)

    return table_parser.get_column(table_, 'id')


def delete_network(network_id, auth_info=Tenant.get('admin'), con_ssh=None, fail_ok=False):
    """
     Delete given network
     Args:
         network_id: network id to be deleted.
        con_ssh (SSHClient):
        auth_info (dict):
        fail_ok (bool): whether to return False or raise exception when non-alive agents exist

     Returns (list):

     """
    LOG.info("Deleting network {}".format(network_id))
    code, output = cli.neutron('net-delete', network_id, ssh_client=con_ssh, auth_info=auth_info, rtn_list=True,
                               fail_ok=True)

    if code == 1:
        return 1, output

    if network_id in get_networks(auth_info=auth_info, con_ssh=con_ssh):
        msg = "Network {} is still listed in neutron net-list".format(network_id)
        if fail_ok:
            LOG.warning(msg)
            return 2, msg
        raise exceptions.NeutronError(msg)

    succ_msg = "Network {} is successfully deleted.".format(network_id)
    return 0, succ_msg


def get_ip_for_eth(ssh_client, eth_name):
    """
    Get the IP addr for given eth on the ssh client provided
    Args:
        ssh_client (SSHClient): usually a vm_ssh
        eth_name (str): such as "eth1, eth1.1"

    Returns (str): The first matching ipv4 addr for given eth. such as "30.0.0.2"

    """
    if eth_name in ssh_client.exec_cmd('ip addr'.format(eth_name))[1]:
        output = ssh_client.exec_cmd('ip addr show {}'.format(eth_name), fail_ok=False)[1]
        if re.search('inet {}'.format(Networks.IPV4_IP), output):
            return re.findall('{}'.format(Networks.IPV4_IP), output)[0]
        else:
            LOG.warning("Cannot find ip address for interface{}".format(eth_name))
            return ''

    else:
        LOG.warning("Cannot find provided interface{} in 'ip addr'".format(eth_name))
        return ''


def _is_v4_only(ip_list):

    rtn_val = True
    for ip in ip_list:
        ip_addr = ipaddress.ip_address(ip)
        if ip_addr.version == 6:
            rtn_val = False
    return rtn_val


def get_internal_net_ids_on_vxlan_v4_v6(vxlan_provider_net_id, ip_version=4, mode='dynamic', con_ssh=None):
    """
    Get the networks ids that matches the vxlan underlay ip version
    Args:
        vxlan_provider_net_id: vxlan provider net id to get the networks info
        ip_version: 4 or 6 (IPV4 or IPV6)
        mode: mode of the vxlan: dynamic or static
        con_ssh (SSHClient):

    Returns (list): The list of networks name that matches the vxlan underlay (v4/v6) and the mode

    """
    rtn_networks = []
    networks = get_networks_on_providernet(providernet_id=vxlan_provider_net_id, rtn_val='id', con_ssh=con_ssh)
    if not networks:
        return rtn_networks
    provider_attributes = get_networks_on_providernet(providernet_id=vxlan_provider_net_id, con_ssh=con_ssh,
                                                      rtn_val='providernet_attributes')
    if not provider_attributes:
        return rtn_networks

    index = 0
    new_attr_list = []
    # In the case where some val could be 'null', need to change that to 'None'
    for attr in provider_attributes:
        new_attr = attr.replace('null', 'None')
        new_attr_list.append(new_attr)

    # getting the configured vxlan mode
    dic_attr_1 = eval(new_attr_list[0])
    vxlan_mode = dic_attr_1['mode']

    if mode == 'static' and vxlan_mode == mode:
        data_if_name = system_helper.get_host_interfaces_info('compute-0', net_type='data', con_ssh=con_ssh)
        address = system_helper.get_host_addr_list(host='compute-0', ifname=data_if_name, con_ssh=con_ssh)
        if ip_version == 4 and _is_v4_only(address):
            rtn_networks.append(networks[index])
        elif ip_version == 6 and not _is_v4_only(address):
            LOG.info("here in v6")
            rtn_networks = networks
        else:
            return rtn_networks
    elif mode == 'dynamic' and vxlan_mode == mode:
        for attr in provider_attributes:
            dic_attr = eval(attr)
            ip = dic_attr['group']
            ip_addr = ipaddress.ip_address(ip)
            if ip_addr.version == ip_version:
                rtn_networks.append(networks[index])
        index += 1

    return rtn_networks


def get_providernet_connectivity_test_results(rtn_val='status', seg_id=None, host=None, pnet_id=None,
                                              pnet_name=None, audit_id=None, auth_info=Tenant.get('admin'),
                                              con_ssh=None, strict=True, **filters):
    """

    Args:
        rtn_val (str|tuple|list):
        seg_id:
        host:
        pnet_id:
        pnet_name:
        audit_id:
        auth_info:
        con_ssh:
        strict:
        **filters:

    Returns:

    """
    args = []
    if audit_id:
        args.append('--audit-uuid {}'.format(audit_id))
    if seg_id:
        args.append('--segmentation_id {}'.format(seg_id))
    if host:
        args.append('--host_name {}'.format(host))
    if pnet_id:
        args.append('--providernet_id {}'.format(pnet_id))
    if pnet_name:
        args.append('providernet_name {}'.format(pnet_name))

    LOG.info("Getting neutron providnet-connectivity-test-list. Filters: {}".format(args))

    out = cli.neutron('providernet-connectivity-test-list', args, ssh_client=con_ssh, auth_info=auth_info)
    if not out:
        return None

    table_ = table_parser.table(out)

    is_str = False
    if isinstance(rtn_val, str):
        rtn_val = [rtn_val]
        is_str = True

    vals = []
    table_ = table_parser.filter_table(table_=table_, strict=strict, **filters)
    for field in rtn_val:
        vals.append(table_parser.get_values(table_, field, merge_lines=True))

    if is_str:
        vals = vals[0]

    return vals


def schedule_providernet_connectivity_test(seg_id=None, host=None, pnet=None, wait_for_test=True, timeout=600,
                                           fail_ok=False, auth_info=Tenant.get('admin'), con_ssh=None):
    args = []
    if host:
        args.append('--host {}'.format(host))
    if seg_id:
        args.append('--segmentation_id {}'.format(seg_id))
    if pnet:
        args.append('--providernet {}'.format(pnet))
    args = ' '.join(args)

    LOG.info("Scheduling providernet-connectivity-test. Args: {}".format(args))
    table_ = table_parser.table(cli.neutron('providernet-connectivity-test-schedule', args, auth_info=auth_info,
                                            ssh_client=con_ssh))
    audit_id = table_parser.get_value_two_col_table(table_, field='audit_uuid')

    if wait_for_test:
        LOG.info("Wait for test with audit uuid {} to be listed".format(audit_id))
        prev_vals = None
        end_time = time.time() + timeout
        while time.time() < end_time:
            vals = get_providernet_connectivity_test_results(audit_id=audit_id, con_ssh=con_ssh,
                                                             rtn_val='segmentation_ids')
            if vals and vals == prev_vals:
                LOG.info("providernet connectivity test scheduled successfully.")
                return 0, audit_id

            prev_vals = vals
            time.sleep(30)

        else:
            if prev_vals:
                LOG.warning("providernet connectivity test scheduled, but did not reach stable output in {} seconds".
                            format(timeout))
                return 2, audit_id
            else:
                if fail_ok:
                    return 1, "Failed to find results with scheduled UUID"
                raise exceptions.NeutronError("Providernet-connectivity-test with audit uuid {} is not listed within {} "
                                              "seconds after running 'neutron providernet-connectivity-test-schedule'".
                                              format(audit_id, timeout))

    else:
        return -1, audit_id


def get_dpdk_user_data(con_ssh=None):
    """
    copy the cloud-config userdata to TiS server.
    This userdata adds wrsroot/li69nux user to guest

    Args:
        con_ssh (SSHClient):

    Returns (str): TiS filepath of the userdata

    """
    file_dir = '{}/userdata'.format(ProjVar.get_var('USER_FILE_DIR'))
    file_name = UserData.DPDK_USER_DATA
    file_path = file_dir + file_name

    if con_ssh is None:
        con_ssh = get_cli_client()

    if con_ssh.file_exists(file_path=file_path):
        # LOG.info('userdata {} already exists. Return existing path'.format(file_path))
        # return file_path
        con_ssh.exec_cmd('rm -f {}'.format(file_path), fail_ok=False)

    LOG.debug('Create userdata directory if not already exists')
    cmd = 'mkdir -p {};touch {}'.format(file_dir, file_path)
    con_ssh.exec_cmd(cmd, fail_ok=False)

    content = "#wrs-config\nFUNCTIONS=hugepages,\n"
    con_ssh.exec_cmd('echo "{}" >> {}'.format(content, file_path), fail_ok=False)
    output = con_ssh.exec_cmd('cat {}'.format(file_path))[1]
    assert output in content

    return file_path


def get_ping_failure_duration(server, ssh_client, end_event, timeout=600, ipv6=False, start_event=None,
                              ping_interval=0.2, single_ping_timeout=1, cumulative=False, init_timeout=60):
    """
    Get ping failure duration in milliseconds
    Args:
        server (str): destination ip
        ssh_client (SSHClient): where the ping cmd sent from
        timeout (int): Max time to ping and gather ping loss duration before
        ipv6 (bool): whether to use ping IPv6 address
        start_event
        end_event: an event that signals the end of the ping
        ping_interval (int|float): interval between two pings in seconds
        single_ping_timeout (int): timeout for ping reply in seconds. Minimum is 1 second.
        cumulative (bool): Whether to accumulate the total loss time before end_event set
        init_timeout (int): Max time to wait before vm pingable

    Returns (int): ping failure duration in milliseconds. 0 if ping did not fail.

    """
    optional_args = ''
    if ipv6:
        optional_args += '6'

    fail_str = 'no answer yet'
    cmd = 'ping{} -i {} -W {} -D -O {} | grep -B 1 -A 1 --color=never "{}"'.format(
            optional_args, ping_interval, single_ping_timeout, server, fail_str)

    start_time = time.time()
    ping_init_end_time = start_time + init_timeout
    prompts = [ssh_client.prompt, fail_str]
    ssh_client.send_sudo(cmd=cmd)
    while time.time() < ping_init_end_time:
        index = ssh_client.expect(prompts, timeout=10, searchwindowsize=100, fail_ok=True)
        if index == 1:
            continue
        elif index == 0:
            raise exceptions.CommonError("Continuous ping cmd interrupted")

        LOG.info("Ping to {} succeeded".format(server))
        start_event.set()
        break
    else:
        raise exceptions.VMNetworkError("VM is not reachable within {} seconds".format(init_timeout))

    end_time = start_time + timeout
    while time.time() < end_time:
        if end_event.is_set():
            LOG.info("End event set. Stop continuous ping and process results")
            break

    #  End ping upon end_event set or timeout reaches
    ssh_client.send_control()
    try:
        ssh_client.expect(fail_ok=False)
    except:
        ssh_client.send_control()
        ssh_client.expect(fail_ok=False)

    # Process ping output to get the ping loss duration
    output = ssh_client.process_cmd_result(cmd='sudo {}'.format(cmd), get_exit_code=False)[1]
    lines = output.splitlines()
    prev_succ = ''
    duration = 0
    count = 0
    prev_line = ''
    succ_str = 'bytes from'
    post_succ = ''
    for line in lines:
        if succ_str in line:
            if prev_succ and (fail_str in prev_line):
                # Ping resumed after serious of lost ping
                count += 1
                post_succ = line
                tmp_duration = _parse_ping_timestamp(post_succ) - _parse_ping_timestamp(prev_succ)
                LOG.info("Count {} ping loss duration: {}".format(count, tmp_duration))
                if cumulative:
                    duration += tmp_duration
                elif tmp_duration > duration:
                    duration = tmp_duration
            prev_succ = line

        prev_line = line

    if not post_succ:
        LOG.warning("Ping did not resume within {} seconds".format(timeout))
        duration = -1
    else:
        LOG.info("Final ping loss duration: {}".format(duration))
    return duration


def _parse_ping_timestamp(output):
    timestamp = math.ceil(float(re.findall('\[(.*)\]', output)[0]) * 1000)
    return timestamp


def create_pci_alias_for_devices(dev_type, hosts=None, devices=None, alias_names=None, apply=True, con_ssh=None):
    """
    Create pci alias for given devices by adding nova pci-alias service parameters
    Args:
        dev_type (str): Valid values: 'gpu-pf', 'user'
        hosts (str|list|tuple|None): Check devices on given host(s). Check all hosts when None
        devices (str|list|tuple|None): Devices to add in pci-alias. When None, add all devices for given dev_type
        alias_names (str|list|tuple|None): Pci alias' to create. When None, name automatically.
        apply (bool): whether to apply after nova service parameters modify
        con_ssh:

    Returns (list): list of dict.
        e.g., [{'device_id': '1d2d', 'vendor_id': '8086', 'name': user_intel-1},
               {'device_id': '1d26', 'vendor_id': '8086', 'name': user_intel-2}, ... ]

    Examples:
        network_helper.create_pci_alias_for_devices(dev_type='user', hosts=('compute-2', 'compute-3'))
        network_helper.create_pci_alias_for_devices(dev_type='gpu-pf', devices='pci_0000_0c_00_0')

    """
    LOG.info("Prepare for adding pci alias")
    if not hosts:
        hosts = host_helper.get_hypervisors(con_ssh=con_ssh)

    if not devices:
        if 'gpu' in dev_type:
            class_id = DevClassID.GPU
        else:
            class_id = DevClassID.USB
        devices = host_helper.get_host_device_list_values(host=hosts[0], field='address', list_all=True, regex=True,
                                                          **{'class id': class_id})
    elif isinstance(devices, str):
        devices = [devices]

    if not alias_names:
        alias_names = [None] * len(devices)
    elif isinstance(alias_names, str):
        alias_names = [alias_names]

    if len(devices) != len(alias_names):
        raise ValueError("Number of devices do not match number of alias names provided")

    LOG.info("Ensure devices are enabled on hosts {}: {}".format(hosts, devices))
    host_helper.enable_disable_hosts_devices(hosts, devices)

    host = hosts[0]
    devices_to_create = []
    param_strs = []
    for i in range(len(devices)):
        device = devices[i]
        alias_name = alias_names[i]
        dev_id, vendor_id, vendor_name = host_helper.get_host_device_values(
                host=host, device=device, fields=('device id', 'vendor id', 'vendor name'))

        if not alias_name:
            alias_name = '{}_{}'.format(dev_type, vendor_name.split()[0].lower())
            alias_name = common.get_unique_name(name_str=alias_name)

        param = {'device_id': dev_id, 'vendor_id': vendor_id, 'name': alias_name}
        param_str = ','.join(['{}={}'.format(key, val) for key, val in param.items()])
        param_strs.append(param_str)

        pci_alias_dict = {'device id': dev_id, 'vendor id': vendor_id, 'pci alias': alias_name}
        devices_to_create.append(pci_alias_dict)

    LOG.info("Create nova pci alias service parameters: {}".format(devices_to_create))
    system_helper.create_service_parameter(service='nova', section='pci_alias', con_ssh=con_ssh,
                                           name=dev_type, value='"{}"'.format(';'.join(param_strs)))

    if apply:
        LOG.info("Apply service parameters")
        system_helper.apply_service_parameters(service='nova')
        LOG.info("Verify nova pci alias' are listed after applying service parameters: {}".format(devices_to_create))
        _check_pci_alias_created(devices_to_create, con_ssh=con_ssh)

    return devices_to_create


def _check_pci_alias_created(devices, con_ssh=None):
    pci_alias_dict = get_pci_device_list_info(con_ssh=con_ssh)
    for param_ in devices:
        pci_alias = param_.get('pci alias')
        assert pci_alias, "pci alias {} is not shown in nova device-list".format(pci_alias)
        created_alias = pci_alias_dict[pci_alias]
        assert param_.get('vendor id') == created_alias['vendor id']
        assert param_.get('device id') == created_alias['device id']


def create_port_pair(ingress_port, egress_port, name=None, description=None, service_func_param=None, fail_ok=False,
                     con_ssh=None, auth_info=None):
    """
    Create port pair

    Args:
        ingress_port (str):
        egress_port (str):
        name (str|None):
        description (str|None):
        service_func_param (str|None):
        fail_ok (bool):
        con_ssh:
        auth_info:

    Returns (tuple):
        (0, <port_pair_id>)     # successfully created
        (1, <std_err>)          # create CLI rejected

    """
    if not name:
        name = 'port_pair'
        name = common.get_unique_name(name_str=name)

    arg = '--ingress {} --egress {} {}'.format(ingress_port, egress_port, name)
    if description:
        arg = '--description {} {}'.format(description, arg)
    if service_func_param:
        arg = '--service-function-parameters {} {}'.format(service_func_param, arg)

    LOG.info("Creating port pair {}".format(name))
    code, output = cli.openstack(cmd='sfc port pair create', positional_args=arg, fail_ok=fail_ok,
                                 ssh_client=con_ssh, auth_info=auth_info, rtn_list=True)

    if code > 0:
        return 1, output

    table_ = table_parser.table(output)
    pair_id = table_parser.get_value_two_col_table(table_, field='ID')
    LOG.info("Port pair {} created successfully".format(pair_id))
    return 0, pair_id


def delete_port_pairs(port_pairs=None, value='ID', check_first=True, fail_ok=False, con_ssh=None, auth_info=None):
    """
    Delete port pairs
    Args:
        port_pairs (str|list|tuple|None):
        value: ID or Name
        check_first (bool):
        fail_ok (bool):
        con_ssh:
        auth_info:

    Returns (tuple): (<code>(int), <successfully_deleted_pairs>(list), <rejected_pairs>(list), <rejection_messages>list)
        (0, <successfully_deleted_pairs>(list), [], [])
        (1, <successfully_deleted_pairs_if_any>, <rejected_pairs>(list), <rejection_messages>list)    # fail_ok=True

    """
    if not port_pairs:
        port_pairs = get_port_pairs(rtn_val=value, auth_info=auth_info, con_ssh=con_ssh)
    else:
        if isinstance(port_pairs, str):
            port_pairs = [port_pairs]

        if check_first:
            existing_pairs = get_port_pairs(rtn_val=value, auth_info=auth_info, con_ssh=con_ssh)
            port_pairs = list(set(port_pairs) - set(existing_pairs))

    if not port_pairs:
        msg = 'Port pair(s) do not exist. Do nothing.'
        LOG.info(msg)
        return -1, [], [], []

    succ_pairs = []
    rejected_pairs = []
    errors = []
    LOG.info("Deleting port pair(s): {}".format(port_pairs))
    for port_pair in port_pairs:
        code, output = cli.openstack(cmd='sfc port pair delete', positional_args=port_pair, fail_ok=fail_ok,
                                     ssh_client=con_ssh, auth_info=auth_info, rtn_list=True)

        if code > 0:
            rejected_pairs.append(port_pair)
            errors.append(output)
        else:
            succ_pairs.append(port_pair)

    post_del_pairs = get_port_pairs(rtn_val=value, auth_info=auth_info, con_ssh=con_ssh)
    failed_pairs = list(set(succ_pairs) - set(post_del_pairs))

    assert not failed_pairs, "Some port-pair(s) still exist after deletion: {}".format(failed_pairs)
    if rejected_pairs:
        code = 1
        LOG.info("Deletion rejected for following port-pair(s): {}".format(rejected_pairs))
    else:
        code = 0
        LOG.info("Port pair(s) deleted successfully.")

    return code, succ_pairs, rejected_pairs, errors


def get_port_pairs(rtn_val='ID', con_ssh=None, auth_info=None, **filters):
    """
    Get port pairs
    Args:
        rtn_val (str): header of the table. ID or Name
        con_ssh:
        auth_info:
        **filters:

    Returns (list):

    """
    arg = '--print-empty'
    table_ = table_parser.table(cli.openstack(cmd='sfc port pair list', positional_args=arg, ssh_client=con_ssh,
                                              auth_info=auth_info))
    return table_parser.get_values(table_, target_header=rtn_val, **filters)


def create_port_pair_group(port_pairs=None, port_pair_val='ID', name=None, description=None, group_param=None,
                           fail_ok=False, con_ssh=None, auth_info=None):
    """
    Create a port pair group
    Args:
        port_pairs (str|list|tuple|None):
        port_pair_val (str): ID or Name
        name (str|None):
        description (str|None):
        group_param (str|None):
        fail_ok (bool):
        con_ssh:
        auth_info:

    Returns (tuple):
        (0, <port pair group id>)
        (1, <std_err>)

    """
    arg = ''
    if port_pairs:
        if isinstance(port_pairs, str):
            port_pairs = [port_pairs]
        port_pairs = list(port_pairs)
        for port_pair in port_pairs:
            arg += ' --port-pair {}'.format(port_pair)

    if description:
        arg += ' --description {}'.format(description)
    if group_param:
        arg += ' --port-pair-group-parameters {}'.format(group_param)

    if not name:
        name = 'port_pair_group'
        name = common.get_unique_name(name_str=name)
    arg = '{} {}'.format(arg, name)

    LOG.info("Creating port pair group {}".format(name))
    code, output = cli.openstack('sfc port pair group create', arg, ssh_client=con_ssh, auth_info=auth_info,
                                 fail_ok=fail_ok, rtn_list=True)
    if code > 0:
        return 1, output

    table_ = table_parser.table(output)
    group_id = table_parser.get_value_two_col_table(table_, 'ID')

    # Check specified port-pair(s) are in created group
    port_pairs_in_group = eval(table_parser.get_value_two_col_table(table_, 'Port Pair'))
    if port_pairs:
        if port_pair_val.lower() != 'id':
            pair_ids = []
            for port_pair in port_pairs:
                port_pair_id = get_port_pairs(Name=port_pair, con_ssh=con_ssh, auth_info=auth_info)[0]
                pair_ids.append(port_pair_id)
            port_pairs = pair_ids
        assert sorted(port_pairs_in_group) == sorted(port_pairs), "Port pairs expected in group: {}. Actual: {}".\
            format(port_pairs, port_pairs_in_group)
    else:
        assert not port_pairs_in_group, "Port pair(s) exist in group even though no port pair is specified"

    LOG.info("Port pair group {} created successfully".format(name))
    return 0, group_id


def set_port_pair_group(group, port_pairs=None, name=None, description=None, fail_ok=False, con_ssh=None,
                        auth_info=None):
    """
    Set port pair group with given values
    Args:
        group (str): port pair group to set
        port_pairs (list|str|tuple|None): port pair(s) to add
        name (str|None):
        description (str|None):
        fail_ok (bool):
        con_ssh:
        auth_info:

    Returns (tuple):
        (0, "Port pair group set successfully")
        (1, <std_err>)

    """
    LOG.info("Setting port pair group {}".format(group))
    arg = ''
    verify = {}
    if port_pairs is not None:
        if port_pairs:
            if isinstance(port_pairs, str):
                port_pairs = [port_pairs]
            port_pairs = list(port_pairs)
            for port_pair in port_pairs:
                arg += ' --port-pair {}'.format(port_pair)

            verify['Port Pair'] = port_pairs
        else:
            arg += ' --no-port-pair'
            verify['Port Pair'] = []

    if name is not None:
        arg += ' --name {}'.format(name)
        verify['Name'] = name
    if description is not None:
        arg += ' --description {}'.format(description)
        verify['Description'] = description

    arg = '{} {}'.format(arg, group)
    code, output = cli.openstack('sfc port pair group set', positional_args=arg, fail_ok=fail_ok, auth_info=auth_info,
                                 ssh_client=con_ssh, rtn_list=True)
    if code > 0:
        return 1, output

    LOG.info("Verify port pair group is set correctly")
    table_ = table_parser.table(output)
    for key, val in verify.items():
        actual_val = table_parser.get_value_two_col_table(table_, key)
        if isinstance(val, list):
            actual_val = eval(actual_val)
            if val:
                assert set(val) <= set(actual_val), "Port pair(s) set: {}; pairs in group: {}".format(val, actual_val)
                assert len(set(actual_val)) == len(actual_val), "Duplicated item found in Port pairs field: {}".\
                    format(actual_val)
            else:
                assert not actual_val, "Port pair still exist in group {} after setting to no: {}".\
                    format(group, actual_val)
        else:
            assert val == actual_val, "Value set for {} is {} ; actual: {}".format(key, val, actual_val)

    msg = "Port pair group set successfully"
    LOG.info("Port pair group set successfully")
    return 0, msg


def unset_port_pair_group(group, port_pairs='all', fail_ok=False, con_ssh=None, auth_info=None):
    """
    Remove port pair(s) from a group
    Args:
        group (str):
        port_pairs (str|list|tuple|None): port_pair(s). When 'all': remove all port pairs from group.
        fail_ok (bool):
        con_ssh:
        auth_info:

    Returns:
        (0, <remaining port pairs in group>(list))
        (1, <std_err>(str))

    """
    LOG.info("Unsetting port pair group {}".format(group))
    arg = ''
    if port_pairs == 'all':
        arg = '--all-port-pair'
    else:
        if isinstance(port_pairs, str):
            port_pairs = [port_pairs]
        port_pairs = list(port_pairs)

        for port_pair in port_pairs:
            arg += ' --port-pair {}'.format(port_pair)

    arg = '{} {}'.format(arg, group)

    code, output = cli.openstack('sfc port pair group unset', positional_args=arg, fail_ok=fail_ok, rtn_list=True,
                                 ssh_client=con_ssh, auth_info=auth_info)

    if code > 0:
        return 1, output

    LOG.info("Verify port pair group is unset correctly")
    table_ = table_parser.table(output)
    actual_pairs = eval(table_parser.get_value_two_col_table(table_, 'Port Pair'))
    if port_pairs == 'all':
        assert not actual_pairs
    else:
        unremoved_pairs = list(set(actual_pairs) & set(port_pairs))
        assert not unremoved_pairs

    LOG.info("Port pairs are successfully removed from group {}".format(group))
    return 0, actual_pairs


def delete_port_pair_group(group, check_first=True, fail_ok=False, auth_info=None, con_ssh=None):
    """
    Delete given port pair group
    Args:
        group (str):
        check_first (bool): Whether to check before deletion
        fail_ok (bool):
        auth_info:
        con_ssh:

    Returns (tuple):
        (-1, 'Port pair group <group> does not exist. Skip deleting.')      # check_first=True
        (0, 'Port pair group <group> successfully deleted')
        (1, <std_err>)      # CLI rejected. fail_ok=True

    """
    if check_first:
        group_id = get_port_pair_group_value(group=group, field='ID', auth_info=auth_info, con_ssh=con_ssh,
                                             fail_ok=True)
        if group_id is None:
            msg = 'Port pair group {} does not exist. Skip deleting.'.format(group)
            LOG.info(msg)
            return -1, msg

    LOG.info("Deleting port pair group {}".format(group))
    code, output = cli.openstack('sfc port pair group delete', group, ssh_client=con_ssh, fail_ok=fail_ok,
                                 auth_info=auth_info, rtn_list=True)

    if code > 0:
        return 1, output

    group_id = get_port_pair_group_value(group=group, field='ID', auth_info=auth_info, con_ssh=con_ssh,
                                         fail_ok=True)
    assert group_id is None, "Port pair group {} still exists after deletion".format(group)

    msg = 'Port pair group {} successfully deleted'.format(group)
    LOG.info(msg)
    return 0, msg


def get_port_pair_groups(rtn_val='ID', auth_info=None, con_ssh=None):
    """
    Get port pair groups
    Args:
        rtn_val (str): ID or Name
        auth_info:
        con_ssh:

    Returns (list):

    """
    table_ = table_parser.table(cli.openstack('sfc port pair group list --print-empty', auth_info=auth_info,
                                              ssh_client=con_ssh))

    return table_parser.get_column(table_, header=rtn_val)


def get_port_pair_group_value(group, field='Port Pair', fail_ok=False, auth_info=None, con_ssh=None):
    """
    Get port pair group value from 'openstack sfc port pair group show'
    Args:
        group (str):
        field (str):
        fail_ok (bool):
        auth_info:
        con_ssh:

    Returns (None|str|dict|list):
        None    # if group does not exist. Only when fail_ok=True
        str|dict|list   # value of given field.

    """
    code, output = cli.openstack('sfc port pair group show', group, auth_info=auth_info, ssh_client=con_ssh,
                                 fail_ok=fail_ok)
    if code > 0:
        return None

    table_ = table_parser.table(output)
    value = table_parser.get_value_two_col_table(table_, field=field, merge_lines=True)
    if 'port pair' in field.lower():
        value = eval(value)

    return value


def get_flow_classifiers(rtn_val='ID', auth_info=None, con_ssh=None):
    """
    Get flow classifiers
    Args:
        rtn_val (str): ID or Name
        auth_info:
        con_ssh:

    Returns (list):

    """
    table_ = table_parser.table(cli.openstack('sfc flow classifier list --print-empty', auth_info=auth_info,
                                              ssh_client=con_ssh))

    return table_parser.get_column(table_, header=rtn_val)


def get_port_chains(rtn_val='ID', auth_info=None, con_ssh=None):
    """
    Get flow classifiers
    Args:
        rtn_val (str): ID or Name
        auth_info:
        con_ssh:

    Returns (list):

    """
    table_ = table_parser.table(cli.openstack('sfc port chain list --print-empty', auth_info=auth_info,
                                              ssh_client=con_ssh))

    return table_parser.get_column(table_, header=rtn_val)


def create_port_chain(port_pair_groups, name=None, flow_classifiers=None, description=None, chain_param=None,
                      auth_info=None, fail_ok=False, con_ssh=None):
    """
    Create port chain
    Args:
        port_pair_groups (str|list|tuple):
        name (str|None):
        flow_classifiers (str|list|tuple|None):
        description (str|None):
        chain_param (str|None):
        auth_info:
        fail_ok:
        con_ssh:

    Returns (tuple):
        (1, <std_err>)      # CLI rejected. fail_ok=True
        (0, <port_chain_id>)

    """
    if isinstance(port_pair_groups, str):
        port_pair_groups = [port_pair_groups]
    arg = ' '.join(['--port-pair-group {}'.format(group) for group in port_pair_groups])

    if flow_classifiers:
        if isinstance(flow_classifiers, str):
            flow_classifiers = [flow_classifiers]
        flow_classifier_arg = ' '.join(['--flow-classifier {}'.format(item) for item in flow_classifiers])
        arg = '{} {}'.format(flow_classifier_arg, arg)

    if description:
        arg = '--description {} {}'.format(description, arg)

    if chain_param:
        arg = '--chain-parameters {} {}'.format(chain_param, arg)

    if not name:
        name = 'port_chain'
        name = common.get_unique_name(name_str=name)

    arg = '{} {}'.format(arg, name)

    LOG.info("Creating port chain {}".format(name))

    code, output = cli.openstack('sfc port chain create', arg, fail_ok=fail_ok, auth_info=auth_info, rtn_list=True,
                                 ssh_client=con_ssh)

    if code > 0:
        return 1, output

    table_ = table_parser.table(output, combine_multiline_entry=True)
    port_chain_id = table_parser.get_value_two_col_table(table_, 'ID')

    LOG.info("Port chain {} successfully created".format(name))
    return 0, port_chain_id


def update_port_chain(port_chain, port_pair_groups=None, flow_classifiers=None, fail_ok=False,
                      con_ssh=None, auth_info=None):
    """
    Set port chain with given values
    Args:
        port_chain (str): port chain to set
        port_pair_groups (list|str|tuple|None): port pair group(s) to add. Use '' if no port pair group is desired
        flow_classifiers (list|str|tuple|None): flow classifier(s) to add. Use '' if no flow classifier is desired
        fail_ok (bool):
        con_ssh:
        auth_info:

    Returns (tuple):
        (0, "Port chain set successfully")
        (1, <std_err>)

    """
    LOG.info("Setting port chain {}".format(port_chain))
    arg = ''
    verify = {}
    arg_dict = {'flow-classifier': flow_classifiers,
                'port-pair-group': port_pair_groups
                }
    for key, val in arg_dict.items():
        if val is not None:
            verify_key = key.replace('-', ' ') + 's'
            if val:
                if isinstance(val, str):
                    val = [val]
                val = list(val)
                for val_ in val:
                    arg += ' --{} {}'.format(key, val_)

                verify[verify_key] = val
            else:
                arg += ' --no-{}'.format(key)
                verify[verify_key] = []

    if not verify:
        raise ValueError('port_pair_groups or flow_classifiers has to be specified')

    arg = '{} {}'.format(arg, port_chain)
    code, output = cli.openstack('sfc port chain set', positional_args=arg, fail_ok=fail_ok, auth_info=auth_info,
                                 ssh_client=con_ssh, rtn_list=True)
    if code > 0:
        return 1, output

    LOG.info("Verify items in port chain {} are set correctly".format(port_chain))
    table_ = table_parser.table(cli.openstack('sfc port chain show', positional_args=port_chain, auth_info=auth_info,
                                ssh_client=con_ssh))
    for key, val in verify.items():
        actual_val = table_parser.get_value_two_col_table(table_, key)
        actual_val = eval(actual_val)

        # if isinstance(actual_val, str):
        #     actual_val = eval(actual_val)
        if val:
            assert set(val) <= set(actual_val), "Requested {}(s) to add to port chain: {}; Actual value: {}".\
                format(key, val, actual_val)
            assert len(set(actual_val)) == len(actual_val), "Duplicated item found in port chain {}s field: {}".\
                format(key, actual_val)
        else:
            assert not actual_val, "{} still exist in port chain after set to no: {}".format(key, actual_val)

    msg = "Port chain set successfully"
    LOG.info(msg)
    return 0, msg


def unset_port_chain(port_chain, flow_classifiers=None, port_pair_groups=None, fail_ok=False, con_ssh=None,
                     auth_info=None):
    """
    Remove port pair(s) from a group
    Args:
        port_chain (str):
        flow_classifiers (str|list|tuple|None): flow_classifier(s) to remove.
            When 'all': remove all flow_classifiers from group.
        port_pair_groups (str|list|tuple|None): port_pair_group(s) to remove.
        fail_ok (bool):
        con_ssh:
        auth_info:

    Returns:
        (0, "Port chain unset successfully")
        (1, <std_err>(str))

    """
    LOG.info("Unsetting port chain {}".format(port_chain))
    arg = ''
    verify = {}
    if flow_classifiers:
        if flow_classifiers == 'all':
            arg = '--all-flow-classifier'
            verify['Flow Classifiers'] = []
        else:
            if isinstance(flow_classifiers, str):
                flow_classifiers = [flow_classifiers]
            flow_classifiers = list(flow_classifiers)

            for flow_classifier in flow_classifiers:
                arg += ' --flow-classifier {}'.format(flow_classifier)
            verify['Flow Classifiers'] = list(flow_classifiers)

    if port_pair_groups:
        if isinstance(port_pair_groups, str):
            port_pair_groups = [port_pair_groups]
        for item in port_pair_groups:
            arg += ' --port-pair-group {}'.format(item)
        verify['Port Pair Groups'] = list(port_pair_groups)

    arg = '{} {}'.format(arg, port_chain)

    code, output = cli.openstack('sfc port chain unset', positional_args=arg, fail_ok=fail_ok, rtn_list=True,
                                 ssh_client=con_ssh, auth_info=auth_info)

    if code > 0:
        return 1, output

    LOG.info("Verify items in port chain {} are unset correctly".format(port_chain))
    table_ = table_parser.table(output)
    for key, val in verify.items():
        actual_val = eval(table_parser.get_value_two_col_table(table_, key))
        if not val:
            assert not actual_val, "{} still exists in port chain after unset all: {}".format(key, actual_val)
        else:
            unremoved_items = list(set(actual_val) & set(val))
            assert not unremoved_items, "{} still exists in port chain after unset: {}".format(key, unremoved_items)

    msg = "Port chain unset successfully"
    LOG.info(msg)
    return 0, msg


def delete_port_chain(port_chain, check_first=True, fail_ok=False, auth_info=None, con_ssh=None):
    """
    Delete given port pair group
    Args:
        port_chain (str):
        check_first (bool): Whether to check before deletion
        fail_ok (bool):
        auth_info:
        con_ssh:

    Returns (tuple):
        (-1, 'Port chain <chain> does not exist. Skip deleting.')      # check_first=True
        (0, 'Port chain <chain> successfully deleted')
        (1, <std_err>)      # CLI rejected. fail_ok=True

    """
    if check_first:
        chain_id = get_port_chain_value(port_chain=port_chain, field='ID', auth_info=auth_info, con_ssh=con_ssh,
                                        fail_ok=True)
        if chain_id is None:
            msg = 'Port chain {} does not exist. Skip deleting.'.format(port_chain)
            LOG.info(msg)
            return -1, msg

    LOG.info("Deleting port chain {}".format(port_chain))
    code, output = cli.openstack('sfc port chain delete', port_chain, ssh_client=con_ssh, fail_ok=fail_ok,
                                 auth_info=auth_info, rtn_list=True)

    if code > 0:
        return 1, output

    chain_id = get_port_chain_value(port_chain=port_chain, field='ID', auth_info=auth_info, con_ssh=con_ssh,
                                    fail_ok=True)
    assert chain_id is None, "Port chain {} still exists after deletion".format(port_chain)

    msg = 'Port chain {} successfully deleted'.format(port_chain)
    LOG.info(msg)
    return 0, msg


def get_port_chain_value(port_chain, field='Flow Classifiers', fail_ok=False, auth_info=None, con_ssh=None):
    """
    Get port chain value from 'openstack sfc port chain show'
    Args:
        port_chain (str):
        field (str):
        fail_ok (bool):
        auth_info:
        con_ssh:

    Returns (None|str|dict|list):
        None    # if chain does not exist. Only when fail_ok=True
        str|dict|list   # value of given field.

    """
    code, output = cli.openstack('sfc port chain show', port_chain, auth_info=auth_info, ssh_client=con_ssh,
                                 fail_ok=fail_ok)
    if code > 0:
        return None

    table_ = table_parser.table(output)
    value = table_parser.get_value_two_col_table(table_, field=field, merge_lines=True)
    if re.search('groups|classifiers', field.lower()):
        value = eval(value)

    return value


def get_flow_classifier_value(flow_classifier, field='Protocol', fail_ok=False, auth_info=None, con_ssh=None):
    """
        Get flow classifier value from 'openstack sfc flow classifier show'
        Args:
            flow_classifier (str):
            field (str):
            fail_ok (bool):
            auth_info:
            con_ssh:

        Returns (None|str|dict|list):
            None    # if flow classifier does not exist. Only when fail_ok=True
            str|dict|list   # value of given field.

        """
    code, output = cli.openstack('sfc flow classifier show', flow_classifier, auth_info=auth_info, ssh_client=con_ssh,
                                 fail_ok=fail_ok)
    if code > 0:
        return None

    table_ = table_parser.table(output)
    value = table_parser.get_value_two_col_table(table_, field=field, merge_lines=True)

    return value


def create_flow_classifier(name=None, description=None, protocol=None, ether_type=None, source_port=None,
                           dest_port=None, source_ip_prefix=None, dest_ip_prefix=None, logical_source_port=None,
                           logical_dest_port=None, l7_param=None, fail_ok=False, auth_info=None, con_ssh=None):
    """
    Create a flow classifier
    Args:
        name:
        description:
        protocol:
        ether_type:
        source_port:
        dest_port:
        source_ip_prefix:
        dest_ip_prefix:
        logical_source_port:
        logical_dest_port:
        l7_param:
        fail_ok:
        auth_info:
        con_ssh:

    Returns (tuple):
        (0, <flow_classifier_id>)
        (1, <std_err>)

    """
    arg_dict = {
        'description': description,
        'protocol': protocol,
        'ethertype': ether_type,
        'logical-source-port': logical_source_port,
        'logical-destination-port': logical_dest_port,
        'source-ip-prefix': source_ip_prefix,
        'destination-ip-prefix': dest_ip_prefix,
        'l7-parameters': l7_param,
        'source-port': source_port,
        'destination-port': dest_port,
    }

    args = []
    for key, val in arg_dict.items():
        if val is not None:
            args.append('--{} {}'.format(key, val))

    arg = ' '.join(args)
    if not name:
        name = 'flow_classifier'
        name = common.get_unique_name(name_str=name)

    arg += ' {}'.format(name)

    LOG.info("Creating flow classifier {}".format(name))
    code, output = cli.openstack('sfc flow classifier create', arg, auth_info=auth_info, fail_ok=fail_ok,
                                 rtn_list=True, ssh_client=con_ssh)

    if code > 0:
        return 1, output

    table_ = table_parser.table(output)
    id_ = table_parser.get_value_two_col_table(table_, 'ID')

    msg = "Flow classifier {} successfully created.".format(id_)
    LOG.info(msg)
    return 0, id_


def delete_flow_classifier(flow_classifier, check_first=True, fail_ok=False, auth_info=None, con_ssh=None):
    """
    Delete flow classifier
    Args:
        flow_classifier (str):
        check_first:
        fail_ok:
        auth_info:
        con_ssh:

    Returns (tuple):
        (-1, Flow classifier <flow_classifier> does not exist. Skip deletion.")
        (0, "Flow classifier <flow_classifier> successfully deleted")
        (1, <std_err>)

    """
    if check_first:
        info = get_flow_classifier_value(flow_classifier, field='ID', fail_ok=True, con_ssh=con_ssh,
                                         auth_info=auth_info)
        if info is None:
            msg = "Flow classifier {} does not exist. Skip deletion.".format(flow_classifier)
            LOG.info(msg)
            return -1, msg

    code, output = cli.openstack('sfc flow classifier delete', flow_classifier, auth_info=auth_info, fail_ok=fail_ok,
                                 ssh_client=con_ssh, rtn_list=True)
    if code > 0:
        return 1, output

    post_del_id = get_flow_classifier_value(flow_classifier, field='ID', auth_info=auth_info, con_ssh=con_ssh,
                                            fail_ok=True)
    assert post_del_id is None, "Flow classifier {} still exists after deletion".format(flow_classifier)

    msg = "Flow classifier {} successfully deleted".format(flow_classifier)
    LOG.info(msg)
    return 0, msg


@contextmanager
def vconsole(ssh_client):
    """
    Enter vconsole for the given ssh connection.
    raises if vconsole connection cannot be established

    Args:
        ssh_client (SSHClient):
            the connection to use for vconsole session

    Yields (function):
        executer function for vconsole

    """
    LOG.info("Entering vconsole")
    original_prompt = ssh_client.get_prompt()
    ssh_client.set_prompt("AVS> ")
    try:
        ssh_client.exec_sudo_cmd("vconsole", get_exit_code=False)
    except Exception as err:
        # vconsole failed to connect
        # this is usually because vswitch initialization failed
        # check instance logs
        ssh_client.set_prompt(original_prompt)
        ssh_client.flush(3)
        ssh_client.send_control('c')
        ssh_client.flush(10)
        raise err

    def v_exec(cmd, fail_ok=False):
        LOG.info("vconsole execute: {}".format(cmd))
        if cmd.strip().lower() == 'quit':
            raise ValueError("shall not exit vconsole without proper cleanup")

        code, output = ssh_client.exec_cmd(cmd, get_exit_code=False)
        if "done" in output.lower():
            return 0, output

        LOG.warning(output)
        if not fail_ok:
            assert 0, 'vconsole failed to execute "{}"'.format(cmd)
        return 1, output

    yield v_exec

    LOG.info("Exiting vconsole")
    ssh_client.set_prompt(original_prompt)
    ssh_client.exec_cmd("quit")
