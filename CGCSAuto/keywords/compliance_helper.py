import re
from contextlib import contextmanager

from pytest import skip

from utils import cli, table_parser
from utils.tis_log import LOG
from utils.clients.ssh import ContainerClient, SSHClient
from consts.compliance import VM_ROUTE_VIA, Dovetail, USER_PASSWORD
from consts.auth import Tenant, ComplianceCreds, CumulusCreds
from consts.cgcs import Prompt
from consts.proj_vars import ProjVar
from keywords import network_helper, nova_helper, keystone_helper, cinder_helper


def add_route_for_vm_access(compliance_client):
    """
    Add ip route on compliance test node to access vm from it
    Args:
        compliance_client:

    Returns:

    """
    LOG.fixture_step("Add routes to access VM from compliance server if not already done")
    cidrs = network_helper.get_subnets(name="tenant[1|2].*-mgmt0-subnet0|external-subnet0", regex=True,
                                       rtn_val='cidr', auth_info=Tenant.get('admin'))
    cidrs_to_add = [r'{}.0/24'.format(re.findall(r'(.*).\d+/\d+', item)[0]) for item in cidrs]
    for cidr in cidrs_to_add:
        if compliance_client.exec_cmd('ip route | grep "{}"'.format(cidr))[0] != 0:
            compliance_client.exec_sudo_cmd('ip route add {} via {}'.format(cidr, VM_ROUTE_VIA))


@contextmanager
def start_container_shell(host_client, docker_cmd, prompt='.*root@.*# .*', remove=False):
    """

    Args:
        host_client (SSHClient):
        docker_cmd (str):
        prompt (str):
        remove (bool): whether to remove the container after exiting

    """
    docker_conn = ContainerClient(host_client, entry_cmd=docker_cmd, initial_prompt=prompt)
    docker_conn.connect()
    docker_id = None
    if remove:
        docker_id = docker_conn.exec_cmd('docker ps -q')[1]

    try:
        yield docker_conn
    finally:
        docker_conn.close()
        if remove:
            host_client.exec_cmd('docker rm {}'.format(docker_id))


@contextmanager
def ssh_to_compliance_server(server=None, user=None, password=None, prompt=None):
    """
    ssh to given compliance server

    Args:
        server:
        user (str):
        password (str):
        prompt (str|None): expected prompt. such as: cumulus@tis-compliance-test-node:~$

    Yields (SSHClient): ssh client for given compliance server and user

    """
    if server is None:
        server = ComplianceCreds.get_host()
    if user is None:
        user = ComplianceCreds.get_user()
    if password is None:
        password = ComplianceCreds.get_password()

    set_ps1 = False
    if prompt is None:
        prompt = r'.*{}@.*:.*\$ '.format(user)
        set_ps1 = True
    server_conn = SSHClient(server, user=user, password=password, initial_prompt=prompt)
    server_conn.connect()
    if set_ps1:
        server_conn.exec_cmd(r'export PS1="\u@\h:\w\$ "')

    try:
        yield server_conn
    finally:
        server_conn.close()


@contextmanager
def ssh_to_cumulus_server(server=None, user=None, password=None, prompt=None):
    if server is None:
        server = CumulusCreds.HOST
    if user is None:
        user = CumulusCreds.LINUX_USER
    if password is None:
        password = CumulusCreds.LINUX_PASSWORD

    if prompt is None:
        prompt = Prompt.CONTROLLER_PROMPT

    server_conn = SSHClient(server, user=user, password=password, initial_prompt=prompt)
    server_conn.connect()

    try:
        yield server_conn
    finally:
        server_conn.close()


def get_expt_mgmt_net():
    lab_name = ProjVar.get_var('LAB')['name'].replace('_', '-')
    for lab_ in Dovetail.DOVETAIL_LABS:
        if lab_name == lab_.replace('_', '-'):
            return '{}-MGMT-net'.format(lab_)

    return None


def update_dovetail_mgmt_interface():
    """
    Update dovetail vm mgmt interface on cumulus system.
    Since cumulus system is on different version. This helper function requires use cli matches the cumulus tis.

    Returns:

    """
    expt_mgmt_net = get_expt_mgmt_net()
    if not expt_mgmt_net:
        skip('{} mgmt net is not found in Cumulus tis-lab project'.format(ProjVar.get_var('LAB')['name']))

    with ssh_to_cumulus_server() as cumulus_con:
        cumulus_auth = CumulusCreds.TENANT_TIS_LAB
        vm_id = nova_helper.get_vm_id_from_name(vm_name='dovetail', fail_ok=False, con_ssh=cumulus_con,
                                                auth_info=cumulus_auth)

        dovetail_networks = nova_helper.get_vms(vms=vm_id, return_val='Networks', con_ssh=cumulus_con,
                                                auth_info=cumulus_auth)[0]

        actual_nets = dovetail_networks.split(sep=';')
        prev_mgmt_nets = []
        for net in actual_nets:
            net_name, net_ip = net.split('=')
            if '-MGMT-net' in net_name:
                prev_mgmt_nets.append(net_name)

        attach = True
        if expt_mgmt_net in prev_mgmt_nets:
            attach = False
            prev_mgmt_nets.remove(expt_mgmt_net)
            LOG.info("{} interface already attached to Dovetail vm".format(expt_mgmt_net))

        if prev_mgmt_nets:
            LOG.info("Detach interface(s) {} from dovetail vm".format(prev_mgmt_nets))
            vm_ports_table = table_parser.table(cli.nova('interface-list', vm_id, ssh_client=cumulus_con,
                                                         auth_info=cumulus_auth))
            for prev_mgmt_net in prev_mgmt_nets:
                prev_net_id = network_helper.get_net_id_from_name(net_name=prev_mgmt_net, con_ssh=cumulus_con,
                                                                  auth_info=cumulus_auth)

                prev_port = table_parser.get_values(vm_ports_table, 'Port ID', **{'Net ID': prev_net_id})[0]
                detach_arg = '{} {}'.format(vm_id, prev_port)
                cli.nova('interface-detach', detach_arg, ssh_client=cumulus_con, auth_info=cumulus_auth)

        mgmt_net_id = network_helper.get_net_id_from_name(net_name=expt_mgmt_net, con_ssh=cumulus_con,
                                                          auth_info=cumulus_auth)
        if attach:
            LOG.info("Attach {} to dovetail vm".format(expt_mgmt_net))
            args = '--net-id {} {}'.format(mgmt_net_id, vm_id)
            cli.nova('interface-attach', args, ssh_client=cumulus_con, auth_info=cumulus_auth)

        vm_ports_table = table_parser.table(cli.nova('interface-list', vm_id, ssh_client=cumulus_con,
                                                     auth_info=cumulus_auth))
        mgmt_mac = table_parser.get_values(vm_ports_table, 'MAC Addr', **{'Net ID': mgmt_net_id})[0]

    ComplianceCreds.set_host(Dovetail.TEST_NODE)
    ComplianceCreds.set_user(Dovetail.USERNAME)
    ComplianceCreds.set_password(Dovetail.PASSWORD)
    with ssh_to_compliance_server() as dovetail_ssh:
        if not attach and network_helper.ping_server('192.168.204.3', ssh_client=dovetail_ssh, fail_ok=True)[0] == 0:
            return
        LOG.info("Bring up dovetail mgmt interface and assign ip")
        eth_name = network_helper.get_eth_for_mac(dovetail_ssh, mac_addr=mgmt_mac)
        dovetail_ssh.exec_sudo_cmd('ip link set dev {} up'.format(eth_name))
        dovetail_ssh.exec_sudo_cmd('dhclient {}'.format(eth_name), expect_timeout=180)
        dovetail_ssh.exec_cmd('ip addr')
        network_helper.ping_server(server='192.168.204.3', ssh_client=dovetail_ssh, fail_ok=False)


def create_tenants_and_update_quotas(new_tenants_index=(3, 6), add_swift_role=False):
    """
    Create tenant3-6 and update quotas for admin and the new tenants

    """
    projects = ['admin']
    roles = ['_member_', 'admin']
    if add_swift_role:
        roles.append('SwiftOperator')

    if new_tenants_index:
        for i in range(new_tenants_index[0], new_tenants_index[1]+1):
            name = 'tenant{}'.format(i)
            keystone_helper.create_project(name=name, description=name, rtn_exist=True)
            keystone_helper.create_user(name=name, rtn_exist=True, password=USER_PASSWORD)
            for role in roles:
                if role == 'SwiftOperator' and name == 'admin':
                    continue
                user = 'admin' if role == 'admin' else name
                keystone_helper.add_or_remove_role(role=role, project=name, user=user)
            projects.append(name)

    for project in projects:
        nova_helper.update_quotas(tenant=project, instances=20, cores=50)
        cinder_helper.update_quotas(tenant=project, volumes=30, snapshots=20)
        network_helper.update_quotas(tenant_name=project, port=500, floatingip=50, subnet=100, network=100)
