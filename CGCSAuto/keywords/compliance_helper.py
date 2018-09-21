import re
from contextlib import contextmanager

from pytest import skip

from utils.tis_log import LOG
from utils.clients.ssh import ContainerClient, SSHClient
from consts.compliance import VM_ROUTE_VIA, Dovetail
from consts.auth import Tenant, ComplianceCreds, CumulusCreds
from consts.cgcs import Prompt
from consts.proj_vars import ProjVar
from keywords import network_helper, vm_helper, nova_helper


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
    cidrs_to_add = [r'{}.0/24'.format(re.findall('(.*).\d+/\d+', item)[0]) for item in cidrs]
    for cidr in cidrs_to_add:
        if compliance_client.exec_cmd('ip route | grep "{}"'.format(cidr))[0] != 0:
            compliance_client.exec_sudo_cmd('ip route add {} via {}'.format(cidr, VM_ROUTE_VIA))


@contextmanager
def start_container_shell(host_client, docker_cmd, prompt='.*root@.*# .*'):
    """

    Args:
        host_client (SSHClient):
        docker_cmd (str):
        prompt (str):

    """
    docker_conn = ContainerClient(host_client, entry_cmd=docker_cmd, initial_prompt=prompt)
    docker_conn.connect()

    try:
        yield docker_conn
    finally:
        docker_conn.close()


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
        prompt = '.*{}@.*:.*\$ '.format(user)
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
    expt_mgmt_net = get_expt_mgmt_net()
    if not expt_mgmt_net:
        skip('{} mgmt net is not found in Cumulus tis-lab project'.format(ProjVar.get_var('LAB')['name']))

    with ssh_to_cumulus_server() as cumulus_con:
        cumulus_auth = CumulusCreds.TENANT_TIS_LAB
        vm_id = nova_helper.get_vm_id_from_name(vm_name='dovetail', fail_ok=False, con_ssh=cumulus_con,
                                                auth_info=cumulus_auth)
        dovetail_nics = network_helper.get_vm_nics(vm_id=vm_id, con_ssh=cumulus_con, auth_info=cumulus_auth)
        mgmt_nic = [nic for nic in dovetail_nics if 'nic2' in nic][0]['nic2']
        mgmt_net_name = mgmt_nic['network']
        if mgmt_net_name == expt_mgmt_net:
            LOG.info("{} interface already attached to Dovetail vm".format(mgmt_net_name))
            return

        mgmt_net_id = network_helper.get_net_id_from_name(net_name=expt_mgmt_net, con_ssh=cumulus_con,
                                                          auth_info=cumulus_auth)
        LOG.info("Attach {} from dovetail vm".format(expt_mgmt_net))
        vm_helper.attach_interface(vm_id=vm_id, net_id=mgmt_net_id, vif_model='virtio', auth_info=cumulus_auth,
                                   con_ssh=cumulus_con)

        LOG.info("Detach {} for lab under test".format(mgmt_net_name))
        vm_helper.detach_interface(vm_id=vm_id, port_id=mgmt_nic['port_id'], con_ssh=cumulus_con,
                                   auth_info=cumulus_auth)

        dovetail_nics = network_helper.get_vm_nics(vm_id=vm_id, con_ssh=cumulus_con, auth_info=cumulus_auth)
        mgmt_nic = [nic for nic in dovetail_nics if 'nic2' in nic][0]['nic2']
        assert expt_mgmt_net == mgmt_nic['network']

    ComplianceCreds.set_host(Dovetail.TEST_NODE)
    ComplianceCreds.set_user(Dovetail.USERNAME)
    ComplianceCreds.set_password(Dovetail.PASSWORD)
    with ssh_to_compliance_server() as dovetail_ssh:
        eth_name = network_helper.get_eth_for_mac(dovetail_ssh, mac_addr=mgmt_nic['mac_address'])
        dovetail_ssh.exec_sudo_cmd('ip link set dev {} up'.format(eth_name))
        dovetail_ssh.exec_sudo_cmd('dhclient {}'.format(eth_name), expect_timeout=180)
        dovetail_ssh.exec_cmd('ip addr')
        network_helper.ping_server(server='192.168.204.3', ssh_client=dovetail_ssh, fail_ok=False)
