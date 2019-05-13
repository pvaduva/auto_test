from consts import auth
from consts.proj_vars import ProjVar
from utils import cli
from utils.clients.ssh import SSHClient, ControllerClient
from utils.exceptions import CLIRejected
from utils.tis_log import LOG


def setup_module():
    global ssh_client
    ssh_client = SSHClient('128.224.150.141')
    ControllerClient.set_active_controller(ssh_client)
    ssh_client.connect()
    LOG.info("setup done")


def teardown_module():
    ssh_client.close()


def test_nova():
    LOG.tc_func_start()
    ProjVar.set_var(SOURCE_CREDENTIAL=True)
    cli.openstack('server list')
    cli.openstack('server list', auth_info=None)
    ProjVar.set_var(SOURCE_CREDENTIAL=None)
    LOG.tc_func_end()


def test_system():
    LOG.tc_func_start()
    cli.system('host-list')
    cli.system('host-show', 1)
    try:
        cli.system('host-list', auth_info=auth.Tenant.TENANT1)
        raise Exception("you should fail!")
    except CLIRejected:
        LOG.info("nova test passed without authentication")
    ProjVar.set_var(SOURCE_CREDENTIAL=True)
    cli.system('host-list', auth_info=None)
    ProjVar.set_var(SOURCE_CREDENTIAL=None)
    LOG.tc_func_end()


def test_auth_tenant():
    LOG.tc_func_start()
    cli.openstack('server list', auth_info=auth.Tenant.TENANT1)
    LOG.tc_func_end()

if __name__ == '__main__':
    ssh_client = SSHClient('128.224.150.142')
    ControllerClient.set_active_controller(ssh_client)
    ssh_client.connect()
    test_system()
    test_auth_tenant()
    test_nova()
