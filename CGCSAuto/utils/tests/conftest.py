import pytest
from consts.lab import Labs
from consts.lab import NatBoxes

from consts.auth import Tenant, HostLinuxCreds
from utils.ssh import ControllerClient, SSHClient, CONTROLLER_PROMPT
from utils.ssh import NATBoxClient

con_ssh = None


@pytest.fixture(scope='session', autouse=True)
def setup_tis_ssh():
    global con_ssh
    con_ssh = SSHClient(Labs.PV0['floating ip'], HostLinuxCreds.USER, HostLinuxCreds.PASSWORD, CONTROLLER_PROMPT)
    con_ssh.connect()
    ControllerClient.set_active_controller(con_ssh)


@pytest.fixture(scope='session', autouse=True)
def setup_primary_tenant():
    Tenant.set_primary(Tenant.TENANT1)


@pytest.fixture(scope='session', autouse=False)
def setup_natbox_ssh():
    NATBoxClient.set_natbox_client(NatBoxes.NAT_BOX_HW['ip'])


@pytest.fixture(scope='function', autouse=True)
def reconnect_before_test():
    con_ssh.connect()


@pytest.fixture(scope='function', autouse=False)
def tis_ssh():
    return con_ssh
