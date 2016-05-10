import re

from utils import exceptions
from utils.tis_log import LOG
from utils.ssh import SSHClient, CONTROLLER_PROMPT, ControllerClient, NATBoxClient
from consts.auth import Tenant
from consts.cgcs import Prompt
from consts.lab import Labs, add_lab_entry, NatBoxes
from consts.proj_vars import ProjVar
from keywords import vm_helper, host_helper
from keywords.common import scp_to_local


def setup_tis_ssh(lab):
    con_ssh = ControllerClient.get_active_controller(fail_ok=True)

    if con_ssh is None:
        con_ssh = SSHClient(lab['floating ip'], 'wrsroot', 'li69nux', CONTROLLER_PROMPT)
        con_ssh.connect()
        ControllerClient.set_active_controller(con_ssh)
    if 'auth_url' in lab:
        Tenant._set_url(lab['auth_url'])
    return con_ssh


def set_env_vars(con_ssh):
    prompt_cmd = con_ssh.exec_cmd("echo $PROMPT_COMMAND")[1]
    tmout_val = con_ssh.exec_cmd("echo $TMOUT")[1]
    hist_time = con_ssh.exec_cmd("echo $HISTTIMEFORMAT")[1]
    source = False
    if not prompt_cmd:
        con_ssh.exec_cmd('''echo 'export PROMPT_COMMAND="date"' >> ~/.bashrc''')
        source = True
    elif prompt_cmd != 'date':
        con_ssh.exec_cmd('''sed -i 's#PROMPT_COMMAND=.*#PROMPT_COMMAND="date"#' ~/.bashrc''')
        source = True

    if tmout_val != '0':
        con_ssh.exec_cmd("echo 'export TMOUT=0' >> ~/.bashrc")
        source = True

    if '%Y-%m-%d %T' not in hist_time:
        con_ssh.exec_cmd('''echo 'export HISTTIMEFORMAT="%Y-%m-%d %T "' >> ~/.bashrc''')
        source = True

    if source:
        con_ssh.exec_cmd("source ~/.bashrc")
        LOG.debug("Environment variable(s) updated.")


def setup_primary_tenant(tenant):
    Tenant.set_primary(tenant)
    LOG.info("Primary Tenant for test session is set to {}".format(tenant['tenant']))


def setup_natbox_ssh(keyfile_path, natbox):
    natbox_ip = natbox['ip']
    NATBoxClient.set_natbox_client(natbox_ip)
    __copy_keyfile_to_natbox(natbox, keyfile_path)


def __copy_keyfile_to_natbox(natbox, keyfile_path):
    # con_ssh = ControllerClient.get_active_controller()
    with host_helper.ssh_to_host('controller-0') as con_0_ssh:
        # con_0_ssh = ssh_to_controller0(ssh_client=con_ssh)
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

        cmd_1 = 'cp /home/wrsroot/.ssh/id_rsa ' + keyfile_path
        cmd_2 = 'chmod 600 ' + keyfile_path
        cmd_3 = 'scp {} {}@{}:~/'.format(keyfile_path, natbox['user'], natbox['ip'])

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
        con_0_ssh.send(natbox['password'])
        con_0_ssh.expect()
        if not con_0_ssh.get_exit_code() == 0:
            raise exceptions.CommonError("Failed to copy keyfile to NatBox")


def boot_vms(is_boot):
    # boot some vms for the whole test session if boot_vms flag is set to True
    if is_boot:
        con_ssh = ControllerClient.get_active_controller()
        if con_ssh.file_exists('~/instances_group0/launch_tenant1-avp1.sh'):
            vm_helper.launch_vms_via_script(vm_type='avp', num_vms=1, tenant_name='tenant1')
            vm_helper.launch_vms_via_script(vm_type='virtio', num_vms=1, tenant_name='tenant2')
        else:
            vm_helper.get_any_vms(count=1, auth_info=Tenant.TENANT_1)
            vm_helper.get_any_vms(count=1, auth_info=Tenant.TENANT_2)


def get_lab_dict(labname):
    labname = labname.strip().lower()
    labs = [getattr(Labs, item) for item in dir(Labs) if not item.startswith('__')]

    for lab in labs:
        if labname.replace('-', '_') in lab['name'].replace('-', '_').lower().strip() or labname == lab['floating ip']:
            return lab
    else:
        if labname.startswith('128.224'):
            return add_lab_entry(labname)

        lab_dict_names = [item for item in dir(Labs) if not item.startswith('__')]
        raise ValueError("{} is not found! All labs: {}".format(labname, lab_dict_names))


def get_natbox_dict(natboxname):
    natboxname = natboxname.lower().strip()
    natboxes = [getattr(NatBoxes, item) for item in dir(NatBoxes) if not item.startswith('_')]

    for natbox in natboxes:
        if natboxname.replace('-', '_') in natbox['name'].replace('-', '_') or natboxname == natbox['ip']:
            return natbox
    else:
        raise ValueError("{} is not a valid input.".format(natboxname))


def get_tenant_dict(tenantname):
    tenantname = tenantname.lower().strip().replace('_', '').replace('-', '')
    tenants = [getattr(Tenant, item) for item in dir(Tenant) if not item.startswith('_') and item.isupper()]

    for tenant in tenants:
        if tenantname == tenant['tenant'].replace('_', '').replace('-', ''):
            return tenant
    else:
        raise ValueError("{} is not a valid input".format(tenantname))


def collect_tis_logs(con_ssh=None):
    LOG.info("Collecting all hosts logs...")
    con_ssh.send('collect all')

    expect_list = ['.*password for wrsroot:', 'collecting data.', con_ssh.prompt]
    index_1 = con_ssh.expect(expect_list, timeout=10)
    if index_1 == 2:
        LOG.error("Something is wrong with collect all. Check ssh console log for detail.")
        return
    elif index_1 == 0:
        con_ssh.send(con_ssh.password)
        con_ssh.expect('collecting data')

    index_2 = con_ssh.expect(['/scratch/ALL_NODES.*', con_ssh.prompt], timeout=900)
    if index_2 == 0:
        output = con_ssh.cmd_output
        con_ssh.expect()
        logpath = re.findall('.*(/scratch/ALL_NODES_.*.tar).*', output)[0]
        LOG.info("\n################### TiS server log path: {} #######################".format(logpath))
    else:
        LOG.error("Collecting logs failed. No ALL_NODES logs found.")
        return

    lab_ip = ProjVar.get_var('LAB')['floating ip']
    dest_path = ProjVar.get_var('LOG_DIR')
    try:
        LOG.info("Copying log file from lab {} to local {}".format(lab_ip, dest_path))
        scp_to_local(logpath, lab_ip, dest_path=dest_path)
        LOG.info("CGCS logs {} are successfully copied to local directory: {}".format(logpath, dest_path))
    except Exception as e:
        raise
        # LOG.error("Failed to copy log file to localhost. Details: {}".format(e))
