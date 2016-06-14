import re
import ipaddress

import math

from utils import table_parser, cli, exceptions
from utils.tis_log import LOG
from consts.auth import Tenant
from consts.cgcs import MGMT_IP, DNS_NAMESERVERS
from keywords import common, keystone_helper


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


def create_subnet(net_id, name=None, cidr=None, gateway=None, dhcp=None, dns_servers=None,
                  alloc_pool=None, ip_version=None, subnet_pool=None, tenant_name=None, fail_ok=False, auth_info=None,
                  con_ssh=None):
    """
    Create a subnet for given tenant under specified network

    Args:
        net_id (str): id of the network to create subnet for
        name (str): name of the subnet
        cidr (str): such as "192.168.3.0/24"
        tenant_name: such as tenant1, tenant2.
        gateway (str): gateway ip of this subnet
        dhcp (bool): whether or not to enable DHCP
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
        args += ' --dns-nameservers {}'.format(dns_servers)

    args_dict = {
        '--tenant-id': keystone_helper.get_tenant_ids(tenant_name, con_ssh=con_ssh)[0] if tenant_name else None,
        '--gateway': gateway,
        '--ip-version': ip_version,
        '--subnetpool': subnet_pool,
        'allocation-pool': "start={},end={}".format(alloc_pool['start'], alloc_pool['end']) if alloc_pool else None
    }

    for key, value in args_dict.items():
        if value is not None:
            args += ' {} {}'.format(key, value)

    LOG.info("Creating subnet for network: {}. Args: {}".format(net_id, args))
    code, output = cli.neutron('subnet-create', args, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                               rtn_list=True)

    if code == 1:
        return 1, '', output

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
    LOG.info(succ_msg)
    return 0, subnet_id, succ_msg


def delete_subnet(subnet_id, auth_info=Tenant.ADMIN, con_ssh=None, fail_ok=False):
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


def get_subnets(name=None, cidr=None, strict=True, regex=False, auth_info=None, con_ssh=None):
    """
    Get subnets ids based on given criteria.

    Args:
        name (str): name of the subnet
        cidr (str): cidr of the subnet
        strict (bool): whether to perform strict search on given name and cidr
        regex (bool): whether to use regext to search
        auth_info (dict):
        con_ssh (SSHClient):

    Returns (list): a list of subnet ids

    """
    table_ = table_parser.table(cli.neutron('subnet-list', ssh_client=con_ssh, auth_info=auth_info))
    if name is not None:
        table_ = table_parser.filter_table(table_, strict=strict, regex=regex, name=name)
    if cidr is not None:
        table_ = table_parser.filter_table(table_, strict=strict, regex=regex, cidr=cidr)

    return table_parser.get_column(table_, 'id')


def get_net_info(net_id, field='status', strict=True, auto_info=None, con_ssh=None):
    """
    Get specified info for given network

    Args:
        net_id (str): network id
        field (str): such as 'status', 'subnets', 'wrs-net:vlan_id' or 'vlan_id' if strict=False
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


def delete_floating_ip(floating_ip, fip_val='ip', auth_info=Tenant.ADMIN, con_ssh=None, fail_ok=False):
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
        floating_ip = get_floating_ids_from_ips(floating_ips=floating_ip, auth_info=Tenant.ADMIN, con_ssh=con_ssh)
    args = floating_ip

    code, output = cli.neutron('floatingip-delete', positional_args=args, ssh_client=con_ssh, auth_info=auth_info,
                               fail_ok=fail_ok, rtn_list=True)

    if code == 1:
        return 1, output

    post_deletion_ips = get_floating_ids_from_ips(con_ssh=con_ssh, auth_info=Tenant.ADMIN)
    if floating_ip in post_deletion_ips:
        msg = "Floating ip {} still exists in floatingip-list.".format(floating_ip)
        if fail_ok:
            LOG.warning(msg)
            return 2, msg
        raise exceptions.NeutronError(msg)

    succ_msg = "Floating ip {} is successfully deleted.".format(floating_ip)
    LOG.info(succ_msg)
    return 0, succ_msg


def get_floating_ips(auth_info=Tenant.ADMIN, con_ssh=None):
    """
    Get all floating ips.

    Args:
        auth_info (dict): if tenant auth_info is given instead of admin, only floating ips for this tenant will be
            returned.
        con_ssh (SSHClient):

    Returns (list): list of floating ips

    """
    table_ = table_parser.table(cli.neutron('floatingip-list', ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_column(table_, 'floating_ip_address')


def get_floating_ids_from_ips(floating_ips=None, con_ssh=None, auth_info=Tenant.ADMIN):
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


def disassociate_floating_ip(floating_ip, fip_val='ip', auth_info=Tenant.ADMIN, con_ssh=None, fail_ok=False):
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
        floating_ip = get_floating_ids_from_ips(floating_ips=floating_ip, auth_info=Tenant.ADMIN, con_ssh=con_ssh)[0]
    args = floating_ip
    code, output = cli.neutron('floatingip-disassociate', args, ssh_client=con_ssh, auth_info=auth_info,
                               fail_ok=fail_ok, rtn_list=True)

    if code == 1:
        return 1, output

    succ_msg = "Floating ip {} is successfully disassociated with fixed ip".format(floating_ip)
    LOG.info(succ_msg)
    return 0, succ_msg


def associate_floating_ip(floating_ip, vm, fip_val='ip', vm_val='id', auth_info=Tenant.ADMIN, con_ssh=None,
                          fail_ok=False):
    """
    Associate a floating ip to management net ip of given vm.

    Args:
        floating_ip (str): ip or id of the floating ip
        vm (str): vm id or ip
        fip_val (str): ip or id
        vm_val (str): id or ip
        auth_info (dict):
        con_ssh (SSHClient):
        fail_ok (bool):

    Returns (tuple): (rtn_code(int), msg(str))
        (0, "port <port_id> is successfully associated with floating ip <floatingip_id>")
        (1, <stderr>)

    """
    # convert vm to vm mgmt ip
    if vm_val == 'id':
        vm = get_mgmt_ips_for_vms(vm, con_ssh=con_ssh)[0]
    args = '--fixed-ip-address {}'.format(vm)

    # convert floatingip to id
    if fip_val == 'ip':
        floating_ip = get_floating_ids_from_ips(floating_ips=floating_ip, auth_info=Tenant.ADMIN, con_ssh=con_ssh)[0]
    args += ' ' + floating_ip

    port = get_vm_port(vm=vm, vm_val='ip', con_ssh=con_ssh)
    args += ' ' + port

    code, output = cli.neutron('floatingip-associate', args, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok,
                               rtn_list=True)
    if code == 1:
        return 1, output

    succ_msg = "port {} is successfully associated with floating ip {}".format(port, floating_ip)
    LOG.info(succ_msg)
    return 0, succ_msg


def get_vm_port(vm, vm_val='id', con_ssh=None, auth_info=Tenant.ADMIN):
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


def get_provider_net(name=None, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Get the neutron provider net list based on name if given for ADMIN user.

    Args:
        con_ssh (SSHClient): If None, active controller ssh will be used.
        auth_info (dict): Tenant dict. If None, primary tenant will be used.
        name (str): Given name for the provider network to filter

        Returns (str): Neutron provider net id of admin user.


    """
    table_ = table_parser.table(cli.neutron('providernet-list', ssh_client=con_ssh, auth_info=auth_info))
    if name is None:
        return table_parser.get_values(table_, 'id')

    return table_parser.get_values(table_, 'id', strict=False, name=name)


def get_provider_net_range(name=None, con_ssh=None, auth_info=Tenant.ADMIN):
    """
    Get the neutron provider net ranges based on name if given for ADMIN user.

    Args:
        con_ssh (SSHClient): If None, active controller ssh will be used.
        auth_info (dict): Tenant dict. If None, primary tenant will be used.
        name (str): Given name for the provider network to filter

    Returns (dict): Neutron provider network ranges of admin user.

    """
    table_ = table_parser.table(cli.neutron('providernet-list', ssh_client=con_ssh, auth_info=auth_info))
    if name is None:
        ranges = table_parser.get_values(table_, 'ranges')
    else:
        ranges = table_parser.get_values(table_, 'ranges', strict=False, name=name)

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


def get_mgmt_ips_for_vms(vms=None, con_ssh=None, auth_info=Tenant.ADMIN, rtn_dict=False, use_fip=False):
    """
    This function returns the management IPs for all VMs on the system.
    We make the assumption that the management IPs start with "192".
    Args:
        vms (str|list|None): vm ids list. If None, management ips for ALL vms with given Tenant(via auth_info) will be
            returned.
        con_ssh (SSHClient): active controller SSHClient object
        auth_info (dict): use admin by default unless specified
        rtn_dict (bool): return list if False, return dict if True
        use_fip (bool): Whether to return only floating ip(s) if any vm has floating ip(s) associated with it

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

    if use_fip:
        floatingips = get_floating_ips(auth_info=Tenant.ADMIN, con_ssh=con_ssh)

    for i in range(len(vm_ids)):
        vm_id = vm_ids[i]
        mgmt_ips_for_vm = mgmt_ip_reg.findall(vm_nets[i])
        if not mgmt_ips_for_vm:
            LOG.warning("No management ip found for vm {}".format(vm_id))
        else:
            if use_fip:
                vm_fips = []
                # ping floating ips only if any associated to vm, otherwise ping all the mgmt ips
                if len(mgmt_ips_for_vm) > 1:
                    for ip in mgmt_ips_for_vm:
                        if ip in floatingips:
                            vm_fips.append(ip)
                    if vm_fips:
                        mgmt_ips_for_vm = vm_fips

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


def get_tenant_router(router_name=None, auth_info=None, con_ssh=None):
    if router_name is None:
        tenant_name = common.get_tenant_name(auth_info=auth_info)
        router_name = tenant_name + '-router'

    table_ = table_parser.table(cli.neutron('router-list', ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_values(table_, 'id', name=router_name)[0]


def get_router_info(router_id=None, field='status', strict=True, auth_info=Tenant.ADMIN, con_ssh=None):
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

    table_ = table_parser.table(cli.neutron('router-show', router_id, ssh_client=con_ssh, auth_info=auth_info))
    return table_parser.get_value_two_col_table(table_, field, strict)


def create_router(name=None, tenant=None, distributed=None, ha=None, admin_state_down=False, fail_ok=False,
                  auth_info=Tenant.ADMIN, con_ssh=None):
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
        '--tenant-id': tenant_id if auth_info == Tenant.ADMIN else None,
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


def get_router_subnets(router_id, auth_info=Tenant.ADMIN, con_ssh=None):
    router_ports_tab = table_parser.table(cli.neutron('router-port-list', router_id, ssh_client=con_ssh,
                                                      auth_info=auth_info))

    fixed_ips = table_parser.get_column(router_ports_tab, 'fixed_ips')
    subnets_ids = list(set([eval(item)['subnet_id'] for item in fixed_ips]))

    return subnets_ids


def get_next_subnet_cidr(net_id, ip_pattern='\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', con_ssh=None):
    LOG.info("Creating subnet of tenant-mgmt-net to add interface to router.")

    nets_tab = table_parser.table(cli.neutron('net-list', ssh_client=con_ssh, auth_info=Tenant.ADMIN))
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


def delete_router(router_id, del_ifs=True, auth_info=Tenant.ADMIN, con_ssh=None, fail_ok=False):

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

    routers = get_router_ids(auth_info=auth_info, con_ssh=con_ssh)
    if router_id in routers:
        msg = "Router {} is still showing in neutron router-list".format(router_id)
        if fail_ok:
            LOG.warning(msg)
            return 2, msg

    succ_msg = "Router {} is successfully deleted.".format(router_id)
    LOG.info(succ_msg)
    return 0, succ_msg


def add_router_interface(router_id=None, subnet=None, port=None, auth_info=None, con_ssh=None, fail_ok=False):
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
        return 1, output, if_source

    if subnet is not None and not router_subnet_exists(router_id, subnet):
        msg = "Subnet {} is not shown in router-port-list for router {}".format(subnet, router_id)
        if fail_ok:
            LOG.warning(msg)
            return 2, msg, if_source
        raise exceptions.NeutronError(msg)

    # TODO: Add check if port is used to add interface.

    succ_msg = "Interface is successfully added to router {}".format(router_id)
    LOG.info(succ_msg)
    return 0, succ_msg, if_source


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

    if subnet is not None and router_subnet_exists(router_id, subnet):
        msg = "Subnet {} is still shown in router-port-list for router {}".format(subnet, router_id)
        if fail_ok:
            LOG.warning(msg)
            return 2, msg
        raise exceptions.NeutronError(msg)

    succ_msg = "Interface is deleted successfully for router {}.".format(router_id)
    LOG.info(succ_msg)
    return 0, succ_msg


def router_subnet_exists(router_id, subnet_id, con_ssh=None, auth_info=Tenant.ADMIN):
    subnets_ids = get_router_subnets(router_id, auth_info=auth_info, con_ssh=con_ssh)

    return subnet_id in subnets_ids


def set_router_gateway(router_id=None, extnet_id=None, enable_snat=True, fixed_ip=None, fail_ok=False,
                       auth_info=Tenant.ADMIN, con_ssh=None, clear_first=True):
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
        args += ' --fixed-ip {}'.format(fixed_ip)

    if router_id is None:
        router_id = get_tenant_router(con_ssh=con_ssh)

    if not extnet_id:
        extnet_id = get_ext_networks(con_ssh=con_ssh)[0]

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


def clear_router_gateway(router_id=None, fail_ok=False, auth_info=Tenant.ADMIN, con_ssh=None, check_first=True):
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


def _update_router(field, value, val_type=None, router_id=None, fail_ok=False, con_ssh=None, auth_info=Tenant.ADMIN):
    """

    Args:
        field (str): valid fields: distributed, external_gateway_info
        value:
        val_type:
        router_id:
        fail_ok:
        con_ssh:
        auth_info:

    Returns:

    """

    if router_id is None:
        router_id = get_tenant_router(con_ssh=con_ssh)

    if not isinstance(router_id, str):
        raise ValueError("Expecting string value for router_id. Get {}".format(type(router_id)))

    LOG.info("Updating router {}: {}={}".format(router_id, field, value))

    if val_type is not None:
        val_type_str = 'type={} '.format(val_type)
    else:
        val_type_str = ''

    args = '{} --{} {}{}'.format(router_id, field, val_type_str, value)

    return cli.neutron('router-update', args, ssh_client=con_ssh, auth_info=auth_info, fail_ok=fail_ok, rtn_list=True)


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


def update_router_ext_gateway_snat(router_id=None, ext_net_id=None, enable_snat=True, fail_ok=False, con_ssh=None,
                                   auth_info=Tenant.ADMIN):
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
    code, output = _update_router(field='external_gateway_info', val_type='dict', value=arg, router_id=router_id,
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


def update_router_distributed(router_id=None, distributed=True, fail_ok=False, auth_info=Tenant.ADMIN, con_ssh=None):
    code, output = _update_router(field='distributed', value=distributed, router_id=router_id,
                                  fail_ok=fail_ok, con_ssh=con_ssh, auth_info=auth_info)
    if code == 1:
        return 1, output

    post_distributed_val = get_router_info(router_id, 'distributed', auth_info=Tenant.ADMIN, con_ssh=con_ssh)
    if post_distributed_val.lower() != str(distributed).lower():
        msg = "Router {} is not updated to distributed={}".format(router_id, distributed)
        if fail_ok:
            return 2, msg
        raise exceptions.NeutronError(msg)

    succ_msg = "Router is successfully updated to distributed={}".format(distributed)
    LOG.info(succ_msg)
    return 0, succ_msg


def update_quotas(tenant=None, con_ssh=None, auth_info=Tenant.ADMIN, fail_ok=False, **kwargs):
    """
    Update neutron quota(s).

    Args:
        tenant (str):
        con_ssh (SSHClient):
        auth_info (dict):
        fail_ok (bool):
        **kwargs: key(str)=value(int) pair(s) to update. such as: network=100, port=50
            possible keys: network, subnet, port, router, floatingip, security-group, security-group-rule, vip, pool,
                            member, health-monitor

    Returns (tuple):
        - (0, "Neutron quota(s) updated successfully to: <kwargs>.")
        - (1, <stderr>)
        - (2, "<quota_name> is not set to <specified_value>")

    """
    if tenant is None:
        tenant = Tenant.get_primary()['tenant']
    tenant_id = keystone_helper.get_tenant_ids(tenant_name=tenant, con_ssh=con_ssh)[0]

    if not kwargs:
        raise ValueError("Please specify at least one quota=value pair via kwargs.")

    args_ = ''
    for key in kwargs:
        args_ += '--{} {} '.format(key, kwargs[key])

    args_ += tenant_id

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

    succ_msg = "Neutron quota(s) updated successfully to: {}.".format(kwargs)
    LOG.info(succ_msg)
    return 0, succ_msg
