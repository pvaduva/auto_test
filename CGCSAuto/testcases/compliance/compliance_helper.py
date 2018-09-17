import re
from contextlib import contextmanager

from utils.tis_log import LOG
from utils.clients.ssh import ContainerClient
from consts.compliance import VM_ROUTE_VIA
from consts.auth import Tenant
from keywords import network_helper


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
