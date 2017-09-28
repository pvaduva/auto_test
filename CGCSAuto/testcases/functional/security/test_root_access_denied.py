######################################################
#  sshd - "PermitRootLogin" and "Match Address" Test #
######################################################


from pytest import fixture, raises
from consts.filepaths import WRSROOT_HOME
from consts.proj_vars import ProjVar
from keywords import common
from utils.tis_log import LOG
from utils.ssh import SSHClient, CONTROLLER_PROMPT, ControllerClient


@fixture(scope='module')
def keyfile_setup(request):
    """
    setup the public key file on the lab under /home/root/.ssh/authorized_keys

    Args:
        request: pytset arg

    Returns (str):

    """
    # copy the authorized key from test server to lab under /home/root/.ssh/authorized_keys
    LOG.fixture_step("copy id_rsa.pub key file from test server to lab")
    source = '/folk/svc-cgcsauto/.ssh/id_rsa.pub'
    destination = WRSROOT_HOME
    common.scp_from_test_server_to_active_controller(source_path=source, dest_dir=destination)

    con_ssh = ControllerClient.get_active_controller()
    wrsroot_keyfile = WRSROOT_HOME + '/id_rsa.pub'
    LOG.fixture_step("Logging in as root")
    with con_ssh.login_as_root() as root_ssh:
        LOG.info("Logged in as root")
        root_ssh.exec_cmd('mkdir -p /home/root/.ssh')
        root_ssh.exec_cmd('touch /home/root/.ssh/authorized_keys')
        root_ssh.exec_cmd('cat '+wrsroot_keyfile+'  >> /home/root/.ssh/authorized_keys')

    def delete_keyfile():
        LOG.fixture_step("cleanup files from the lab as root")
        con_ssh = ControllerClient.get_active_controller()
        # clean up id_rsa.pub from wrsroot folder and authorized_keys in /home/root/.ssh/
        con_ssh.exec_cmd('rm /home/wrsroot/id_rsa.pub')
        con_ssh.exec_sudo_cmd('rm -f /home/root/.ssh/authorized_keys')

    request.addfinalizer(delete_keyfile)


def test_root_access_denied(keyfile_setup):
    """
    Verify SSH root access to the regular lab is rejected after the change to sshd_config

    Skip Condition:
        - N/A

    Test Setup:

    Test Steps:
        -Generate an SSH key-pair ssh-keygen -t rsa
        - Copy the Public key over the Lab controller scp ~/.ssh/<id_rsa.pub> wrsroot@<lab.ip>
        - Copy the public key from your wrsroot account into the “authorized_keys” file of the “root” account
            *login to controller
            *do sudo su to get to root
            *create folder/file: /root/.ssh/authorized_keys if they do not exist
            *cat /home/wrsroot/<id_rsa.pub/  >> /root/.ssh/authorized_keys

        - This adds your key into the roots authorized_ssh key
        - Now login from your desktop using Ssh –I <public_key> root@<lab.ip>
        - on attempting to ssh with root(with/without password). The user will now get  "Permission denied" Error.

    """

    # attempt to access the lab as root
    lab = ProjVar.get_var("LAB")
    con_ssh = SSHClient(lab['floating ip'], 'root', 'Li69nux*', CONTROLLER_PROMPT)

    # this is expected to fail with permission denied exception
    LOG.tc_step("check permission denied exception is raised when logging in as root")
    with raises(Exception) as excinfo:
        con_ssh.connect(retry=False, retry_timeout=30)
        con_ssh.close()
    assert 'permission denied' in str(excinfo.value)



