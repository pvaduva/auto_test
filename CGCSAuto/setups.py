import os

from utils import exceptions
from utils.tis_log import LOG
from utils.ssh import SSHClient, CONTROLLER_PROMPT, ControllerClient, NATBoxClient, ssh_to_controller0
from consts.auth import Tenant
from consts.cgcs import Prompt
from keywords import vm_helper, security_helper
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
    primary_tenant = setup_consts.PRIMARY_TENANT
    Tenant.set_primary(primary_tenant)
    LOG.info("Primary Tenant for test session is set to {}".format(primary_tenant['tenant']))


def setup_natbox_ssh():
    natbox_ip = setup_consts.NatBox.NAT_BOX_HW['ip']
    NATBoxClient.set_natbox_client(natbox_ip)
    __copy_keyfile_to_natbox(natbox_ip)


def __copy_keyfile_to_natbox(natbox_ip):
    con_ssh = ControllerClient.get_active_controller()
    con_0_ssh = ssh_to_controller0(ssh_client=con_ssh)
    if not con_0_ssh.file_exists('/home/wrsroot/.ssh/id_rsa'):
        passphrase_prompt_1 = '.*Enter passphrase.*'
        passphrase_prompt_2 = '.*Enter same passphrase again.*'

        con_0_ssh.send('ssh-keygen')
        index = con_0_ssh.expect([passphrase_prompt_1, '.*Enter file in which to save the key.*'])
        if index == 1:
            con_0_ssh.send()
            con_0_ssh.expect(passphrase_prompt_1)
        con_0_ssh.send()    # Enter empty passphrase
        con_0_ssh.expect(passphrase_prompt_2)
        con_0_ssh.send()    # Repeat passphrase
        con_0_ssh.expect(Prompt.CONTROLLER_0)

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
        raise exceptions.CommonError("Failed to copy keyfile to NatBox")


def boot_vms():
    # boot some vms for the whole test session if boot_vms flag is set to True
    if not setup_consts.BOOT_VMS:
        return

    con_ssh = ControllerClient.get_active_controller()
    if con_ssh.file_exists('~/instances_group0/launch_tenant1-avp1.sh'):
        vm_helper.launch_vms_via_script(vm_type='avp', num_vms=1, tenant_name='tenant1')
        vm_helper.launch_vms_via_script(vm_type='virtio', num_vms=1, tenant_name='tenant2')
    else:
        vm_helper.get_any_vms(count=1, auth_info=Tenant.TENANT_1)
        vm_helper.get_any_vms(count=1, auth_info=Tenant.TENANT_2)
