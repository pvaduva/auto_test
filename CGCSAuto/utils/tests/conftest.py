import pytest
from consts.lab import Labs
from consts.lab import NatBox

from consts.auth import Primary
from utils.ssh import ControllerClient, SSHClient, CONTROLLER_PROMPT
from utils.ssh import NATBoxClient

con_ssh = None


@pytest.fixture(scope='session', autouse=True)
def setup_tis_ssh():
    global con_ssh
    con_ssh = SSHClient(Labs.PV0['floating ip'], 'wrsroot', 'li69nux', CONTROLLER_PROMPT)
    con_ssh.connect()
    ControllerClient.set_active_controller(con_ssh)


@pytest.fixture(scope='session', autouse=True)
def setup_primary_tenant():
    Primary.set_primary('tenant2')


@pytest.fixture(scope='session', autouse=True)
def setup_natbox_ssh():
    NATBoxClient.set_natbox_client(NatBox.NAT_BOX_HW['ip'])


@pytest.fixture(scope='function', autouse=True)
def reconnect_before_test():
    con_ssh.connect()


@pytest.fixture(scope='function', autouse=False)
def tis_ssh():
    return con_ssh