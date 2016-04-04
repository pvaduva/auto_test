import os

from utils import exceptions
from utils.ssh import SSHClient, CONTROLLER_PROMPT, ControllerClient, NATBoxClient, ssh_to_controller0
from consts.auth import Primary, Tenant
from consts.cgcs import Prompt
import setup_consts


def create_tmp_dir():
    os.makedirs(setup_consts.TEMP_DIR, exist_ok=True)


def setup_tis_ssh():
    con_ssh = ControllerClient.get_active_controller(fail_ok=True)
    lab = setup_consts.LAB
    if con_ssh is None:
        con_ssh = SSHClient(lab['floating ip'], 'wrsroot', 'li69nux', CONTROLLER_PROMPT)
        con_ssh.connect()
        ControllerClient.set_active_controller(con_ssh)
    if 'auth_url' in lab:
        Tenant._set_url(lab['auth_url'])
    return con_ssh


def setup_primary_tenant():
    Primary.set_primary(setup_consts.PRIMARY_TENANT)


def setup_natbox_ssh():
    natbox_ip = setup_consts.NatBox.NAT_BOX_HW['ip']
    NATBoxClient.set_natbox_client(natbox_ip)
    __copy_keyfile_to_natbox(natbox_ip)


def __copy_keyfile_to_natbox(natbox_ip):
    con_ssh = ControllerClient.get_active_controller()
    con_0_ssh = ssh_to_controller0(ssh_client=con_ssh)

    keyfile_path = setup_consts.KEYFILE_PATH
    cmd_1 = 'cp /home/wrsroot/.ssh/id_rsa ' + keyfile_path
    cmd_2 = 'chmod 600 ' + keyfile_path
    cmd_3 = 'scp {} {}@{}:~/'.format(keyfile_path, setup_consts.NATBOX['user'], natbox_ip)

    rtn_1 = con_0_ssh.exec_cmd(cmd_1)[0]
    if not rtn_1 == 0:
        raise exceptions.CommonError("Failed to create new keyfile on controller")
    rtn_2 = con_0_ssh.exec_cmd(cmd_2)[0]
    if not rtn_2 == 0:
        raise exceptions.CommonError("Failed to update permission for created keyfile")

    con_0_ssh.send(cmd_3)
    rtn_3_index = con_0_ssh.expect(['.*\(yes/no\)\?.*', Prompt.PASSWORD_PROMPT])
    if rtn_3_index == 0:
        con_0_ssh.send('yes')
        con_0_ssh.expect(Prompt.PASSWORD_PROMPT)
    con_0_ssh.send(setup_consts.NATBOX['password'])
    con_0_ssh.expect()
    if not con_0_ssh.get_exit_code() == 0:
        raise exceptions.CommonError("Failed to copy keyfile to Nat Box")


#__skipsetup_called = False
#def skipcondition_setup():
#    global __skipsetup_called
#    if not __skipsetup_called:
#        setup_tis_ssh()
#        setup_primary_tenant()
#        __skipsetup_called = True
